# -*- coding: utf-8 -*-
"""
多知识库检索器
负责从免签库和通用库检索并合并结果，确保互不干扰
"""
from typing import List
from llama_index.core.schema import NodeWithScore
from config import Settings
from utils.logger import logger


class MultiKBRetriever:
    """
    多知识库检索器
    
    核心原则：
    1. 各库独立检索和打分
    2. 按配置策略合并结果
    3. 不修改原始得分
    """
    
    def __init__(
        self,
        general_retriever,
        visa_free_retriever,
        strategy: str = "adaptive"
    ):
        """
        初始化多库检索器
        
        Args:
            general_retriever: 通用知识库检索器
            visa_free_retriever: 免签知识库检索器
            strategy: 合并策略 ("adaptive" 或 "fixed")
        """
        self.general_retriever = general_retriever
        self.visa_free_retriever = visa_free_retriever
        self.strategy = strategy
        
        logger.info(f"多库检索器初始化完成 | 策略: {strategy}")
    
    def retrieve_from_both(
        self,
        query: str,
        visa_count: int = None,
        general_count: int = None
    ) -> List[NodeWithScore]:
        """
        从两个知识库检索并合并结果
        
        Args:
            query: 查询文本
            visa_count: 免签库取多少条（None则使用配置）
            general_count: 通用库取多少条（None则使用配置）
        
        Returns:
            合并后的节点列表（按分数排序）
        """
        # 使用配置的默认值
        if visa_count is None:
            visa_count = Settings.VISA_FREE_RETRIEVAL_COUNT
        if general_count is None:
            general_count = Settings.GENERAL_RETRIEVAL_COUNT
        
        logger.info(f"[双库检索] 查询: {query[:50]}...")
        logger.info(f"[双库检索] 策略: {self.strategy} | 免签:{visa_count}条 | 通用:{general_count}条")
        
        # 1. 独立检索免签库
        logger.info("[双库检索] 步骤1: 检索免签知识库...")
        if self.visa_free_retriever is None:
            logger.warning("[双库检索] 免签检索器未初始化，跳过免签库检索")
            visa_free_nodes = []
        else:
            visa_free_nodes = self.visa_free_retriever.retrieve(query)
            logger.info(f"[双库检索] 免签库检索完成 | 返回 {len(visa_free_nodes)} 条")
            if visa_free_nodes:
                visa_scores = [n.score for n in visa_free_nodes[:5]]
                logger.info(f"[双库检索] 免签库Top5得分: {[f'{s:.4f}' for s in visa_scores]}")
        
        # 2. 独立检索通用库
        logger.info("[双库检索] 步骤2: 检索通用知识库...")
        if self.general_retriever is None:
            logger.warning("[双库检索] 通用检索器未初始化，跳过通用库检索")
            general_nodes = []
        else:
            general_nodes = self.general_retriever.retrieve(query)
            logger.info(f"[双库检索] 通用库检索完成 | 返回 {len(general_nodes)} 条")
            if general_nodes:
                general_scores = [n.score for n in general_nodes[:5]]
                logger.info(f"[双库检索] 通用库Top5得分: {[f'{s:.4f}' for s in general_scores]}")
        
        # 3. 根据策略合并
        if self.strategy == "adaptive":
            merged = self._adaptive_merge(
                visa_free_nodes, general_nodes, visa_count, general_count
            )
        else:  # fixed
            merged = self._fixed_merge(
                visa_free_nodes, general_nodes, visa_count, general_count
            )
        
        logger.info(f"[双库检索] 合并完成 | 最终返回 {len(merged)} 条")
        if merged:
            final_scores = [n.score for n in merged[:5]]
            logger.info(f"[双库检索] 最终Top5得分: {[f'{s:.4f}' for s in final_scores]}")
        
        return merged
    
    def _adaptive_merge(
        self,
        visa_nodes: List[NodeWithScore],
        general_nodes: List[NodeWithScore],
        visa_count: int,
        general_count: int
    ) -> List[NodeWithScore]:
        """
        自适应合并策略：根据得分动态调整比例
        
        规则：
        - 如果某一边最高分 > 0.8 且比另一边高 20% 以上，优先该库（70%）
        - 否则按固定比例（50%:50%）
        """
        if not visa_nodes and not general_nodes:
            return []
        if not visa_nodes:
            return general_nodes[:general_count * 2]  # 只有通用库时多取一些
        if not general_nodes:
            return visa_nodes[:visa_count * 2]  # 只有免签库时多取一些
        
        visa_max_score = visa_nodes[0].score if visa_nodes else 0.0
        general_max_score = general_nodes[0].score if general_nodes else 0.0
        
        logger.info(f"[自适应策略] 免签最高分: {visa_max_score:.4f} | 通用最高分: {general_max_score:.4f}")
        
        # 判断是否需要调整比例
        if visa_max_score > 0.8 and visa_max_score > general_max_score * 1.2:
            # 免签库得分明显更高
            visa_count = int(visa_count * 1.4)  # 70%
            general_count = int(general_count * 0.6)  # 30%
            logger.info(f"[自适应策略] 免签库得分更高，调整比例 -> 免签:{visa_count} | 通用:{general_count}")
        elif general_max_score > 0.8 and general_max_score > visa_max_score * 1.2:
            # 通用库得分明显更高
            general_count = int(general_count * 1.4)  # 70%
            visa_count = int(visa_count * 0.6)  # 30%
            logger.info(f"[自适应策略] 通用库得分更高，调整比例 -> 免签:{visa_count} | 通用:{general_count}")
        else:
            logger.info(f"[自适应策略] 得分相近，保持默认比例 -> 免签:{visa_count} | 通用:{general_count}")
        
        return self._fixed_merge(visa_nodes, general_nodes, visa_count, general_count)
    
    def _fixed_merge(
        self,
        visa_nodes: List[NodeWithScore],
        general_nodes: List[NodeWithScore],
        visa_count: int,
        general_count: int
    ) -> List[NodeWithScore]:
        """
        固定比例合并策略
        
        实现记忆中的15条策略：
        - 前5条：免签库最高分
        - 中5条：通用库最高分
        - 后5条：从剩余文档中综合比较
        """
        # 1. 前N条：免签库最高分
        visa_top = visa_nodes[:visa_count] if visa_nodes else []
        
        # 2. 中N条：通用库最高分
        general_top = general_nodes[:general_count] if general_nodes else []
        
        # 3. 后N条：从剩余文档中综合比较
        visa_remaining = visa_nodes[visa_count:] if len(visa_nodes) > visa_count else []
        general_remaining = general_nodes[general_count:] if len(general_nodes) > general_count else []
        
        remaining_all = visa_remaining + general_remaining
        remaining_all.sort(key=lambda x: x.score, reverse=True)
        remaining_top = remaining_all[:visa_count]  # 后5条
        
        # 4. 合并所有结果
        merged_results = visa_top + general_top + remaining_top
        
        # 5. 按分数重新排序
        merged_results.sort(key=lambda x: x.score, reverse=True)
        
        # 统计来源分布
        visa_count_final = sum(1 for n in merged_results if self._is_visa_free_node(n))
        general_count_final = len(merged_results) - visa_count_final
        
        logger.info(
            f"[固定策略] 合并完成 | "
            f"免签库:{len(visa_top)}条 + 通用库:{len(general_top)}条 + 综合:{len(remaining_top)}条 = "
            f"总计:{len(merged_results)}条 (免签{visa_count_final} + 通用{general_count_final})"
        )
        
        return merged_results
    
    def _is_visa_free_node(self, node: NodeWithScore) -> bool:
        """判断节点是否来自免签库（通过文件名判断）"""
        file_name = node.node.metadata.get('file_name', '')
        # 简单判断：包含"免签"、"签证"等关键词
        return any(keyword in file_name for keyword in ['免签', '签证', 'visa'])
