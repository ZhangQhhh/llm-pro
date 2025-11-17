# -*- coding: utf-8 -*-
"""
多知识库检索器 V2
支持三库检索（通用库、免签库、航司库）+ 去重逻辑
"""
from typing import List
from llama_index.core import QueryBundle
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
    4. 自动去重（按node_id）
    
    支持三库：通用库、免签库、航司库
    """
    
    def __init__(
        self,
        general_retriever,
        visa_free_retriever=None,
        airline_retriever=None,
        strategy: str = "adaptive"
    ):
        """
        初始化多库检索器
        
        Args:
            general_retriever: 通用知识库检索器
            visa_free_retriever: 免签知识库检索器（可选）
            airline_retriever: 航司知识库检索器（可选）
            strategy: 合并策略 ("adaptive" 或 "fixed")
        """
        self.general_retriever = general_retriever
        self.visa_free_retriever = visa_free_retriever
        self.airline_retriever = airline_retriever
        self.strategy = strategy
        
        enabled_libs = []
        if general_retriever:
            enabled_libs.append("通用库")
        if visa_free_retriever:
            enabled_libs.append("免签库")
        if airline_retriever:
            enabled_libs.append("航司库")
        
        logger.info(f"多库检索器初始化完成 | 策略: {strategy} | 已启用: {', '.join(enabled_libs)}")
    
    def retrieve_from_both(
        self,
        query: str,
        visa_count: int = None,
        general_count: int = None
    ) -> List[NodeWithScore]:
        """
        从两个知识库检索并合并结果（免签 + 通用）
        
        Args:
            query: 查询文本
            visa_count: 免签库取多少条（None则使用配置）
            general_count: 通用库取多少条（None则使用配置）
        
        Returns:
            合并后的节点列表（按分数排序，已去重）
        """
        from llama_index.core import QueryBundle
        
        # 使用配置的默认值
        if visa_count is None:
            visa_count = Settings.VISA_FREE_RETRIEVAL_COUNT
        if general_count is None:
            general_count = Settings.GENERAL_RETRIEVAL_COUNT
        
        logger.info(f"[双库检索] 查询: {query[:50]}...")
        logger.info(f"[双库检索] 策略: {self.strategy} | 免签:{visa_count}条 | 通用:{general_count}条")
        
        # 创建 QueryBundle
        query_bundle = QueryBundle(query_str=query)
        
        # 1. 独立检索免签库
        logger.info("[双库检索] 步骤1: 检索免签知识库...")
        if self.visa_free_retriever is None:
            logger.warning("[双库检索] 免签检索器未初始化，跳过免签库检索")
            visa_free_nodes = []
        else:
            visa_free_nodes = self.visa_free_retriever.retrieve(query_bundle)
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
            general_nodes = self.general_retriever.retrieve(query_bundle)
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
        """
        if not visa_nodes and not general_nodes:
            return []
        
        # 比较最高分
        visa_max_score = visa_nodes[0].score if visa_nodes else 0.0
        general_max_score = general_nodes[0].score if general_nodes else 0.0
        
        logger.info(f"[自适应策略] 免签最高分: {visa_max_score:.4f} | 通用最高分: {general_max_score:.4f}")
        
        # 根据得分调整比例
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
        固定比例合并策略 + 去重
        
        实现：
        - 前N条：免签库最高分
        - 中N条：通用库最高分
        - 后N条：从剩余文档中综合比较
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
        remaining_top = remaining_all[:visa_count]  # 后N条
        
        # 4. 合并所有结果
        merged_results = visa_top + general_top + remaining_top
        
        # 5. 去重（按node_id）⭐
        seen_ids = set()
        unique_results = []
        for node in merged_results:
            node_id = node.node.node_id
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                unique_results.append(node)
        
        # 6. 按分数重新排序
        unique_results.sort(key=lambda x: x.score, reverse=True)
        
        # 统计来源分布
        visa_count_final = sum(1 for n in unique_results if self._is_visa_free_node(n))
        general_count_final = len(unique_results) - visa_count_final
        
        logger.info(
            f"[固定策略] 合并完成 | "
            f"免签库:{len(visa_top)}条 + 通用库:{len(general_top)}条 + 综合:{len(remaining_top)}条 | "
            f"去重前:{len(merged_results)}条 去重后:{len(unique_results)}条 "
            f"(免签{visa_count_final} + 通用{general_count_final})"
        )
        
        return unique_results
    
    def retrieve_airline_only(self, query: str) -> List[NodeWithScore]:
        """
        航司库检索（自动包含通用库保底）+ 去重
        
        策略：航司库 + 通用库（至少5条）
        - 前5条：航司库最高分
        - 中5条：通用库最高分（保底）
        - 后5条：从剩余文档中综合比较
        """
        from llama_index.core import QueryBundle
        
        if not self.airline_retriever:
            logger.warning("[航司检索] 航司检索器未初始化")
            return []
        
        logger.info(f"[航司检索] 查询: {query[:50]}...")
        logger.info("[航司检索] 策略: 航司库 + 通用库（保底5条）")
        
        # 创建 QueryBundle
        query_bundle = QueryBundle(query_str=query)
        
        # 1. 检索航司库
        airline_nodes = self.airline_retriever.retrieve(query_bundle)
        logger.info(f"[航司检索] 航司库返回 {len(airline_nodes)} 条")
        
        # 2. 检索通用库（保底）
        general_nodes = []
        if self.general_retriever:
            general_nodes = self.general_retriever.retrieve(query_bundle)
            logger.info(f"[航司检索] 通用库返回 {len(general_nodes)} 条（保底）")
        
        # 3. 合并策略：航司5条 + 通用5条 + 综合5条 = 15条
        airline_count = Settings.AIRLINE_RETRIEVAL_COUNT
        general_count = Settings.GENERAL_RETRIEVAL_COUNT
        
        airline_top = airline_nodes[:airline_count]
        general_top = general_nodes[:general_count]
        
        # 4. 从剩余文档中再取一些
        airline_remaining = airline_nodes[airline_count:]
        general_remaining = general_nodes[general_count:]
        remaining_all = airline_remaining + general_remaining
        remaining_all.sort(key=lambda x: x.score, reverse=True)
        remaining_top = remaining_all[:airline_count]
        
        # 5. 合并并去重（按node_id）⭐
        merged = airline_top + general_top + remaining_top
        
        # 去重：保留第一次出现的节点（得分最高的）
        seen_ids = set()
        unique_merged = []
        for node in merged:
            node_id = node.node.node_id
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                unique_merged.append(node)
        
        # 6. 按分数排序
        unique_merged.sort(key=lambda x: x.score, reverse=True)
        
        # 统计来源分布
        airline_final = sum(1 for n in unique_merged if self._is_airline_node(n))
        general_final = len(unique_merged) - airline_final
        
        logger.info(
            f"[航司检索] 合并完成 | 去重前:{len(merged)}条 去重后:{len(unique_merged)}条 "
            f"(航司{airline_final}条 + 通用{general_final}条)"
        )
        
        return unique_merged
    
    def retrieve_from_all_three(self, query: str) -> List[NodeWithScore]:
        """
        三库同时检索（航司 + 免签 + 通用）+ 去重 ⭐
        
        策略：按得分动态分配（确保高分文档优先）
        1. 从三个库分别检索
        2. 合并所有结果并按分数排序
        3. 取前30条最高分文档
        4. 去重（按node_id）
        5. 最终按分数排序返回
        
        Returns:
            去重后的节点列表（按分数排序，最多30条）
        """
        from llama_index.core import QueryBundle
        
        logger.info(f"[三库检索] 查询: {query[:50]}...")
        logger.info("[三库检索] 策略: 航司库 + 免签库 + 通用库（全覆盖）")
        
        # 创建 QueryBundle
        query_bundle = QueryBundle(query_str=query)
        
        # 1. 检索三个库
        airline_nodes = []
        if self.airline_retriever:
            airline_nodes = self.airline_retriever.retrieve(query_bundle)
            logger.info(f"[三库检索] 航司库返回 {len(airline_nodes)} 条")
        
        visa_nodes = []
        if self.visa_free_retriever:
            visa_nodes = self.visa_free_retriever.retrieve(query_bundle)
            logger.info(f"[三库检索] 免签库返回 {len(visa_nodes)} 条")
        
        general_nodes = []
        if self.general_retriever:
            general_nodes = self.general_retriever.retrieve(query_bundle)
            logger.info(f"[三库检索] 通用库返回 {len(general_nodes)} 条")
        
        # 2. 按得分动态分配策略（确保高分文档优先）
        # 合并所有结果并按分数排序
        all_nodes = airline_nodes + visa_nodes + general_nodes
        all_nodes.sort(key=lambda x: x.score, reverse=True)
        
        # 取前30条（按得分）
        merged = all_nodes[:30]
        
        logger.info(f"[三库检索] 按得分排序后取前30条")
        
        # 5. 去重（按node_id）⭐ 关键：避免重复
        seen_ids = set()
        unique_merged = []
        for node in merged:
            node_id = node.node.node_id
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                unique_merged.append(node)
        
        # 6. 按分数排序
        unique_merged.sort(key=lambda x: x.score, reverse=True)
        
        # 统计来源分布（互斥优先级：航司 > 免签 > 通用）
        airline_final = 0
        visa_final = 0
        general_final = 0
        
        for node in unique_merged:
            if self._is_airline_node(node):
                airline_final += 1
            elif self._is_visa_free_node(node):
                visa_final += 1
            else:
                general_final += 1
        
        logger.info(
            f"[三库检索] 合并完成 | 去重前:{len(merged)}条 去重后:{len(unique_merged)}条 | "
            f"航司{airline_final}条 + 免签{visa_final}条 + 通用{general_final}条"
        )
        
        return unique_merged
    
    def retrieve_with_dual_questions(
        self,
        original_query: str,
        rewritten_query: str,
        strategy: str = "airline_visa_free"
    ) -> tuple[List[NodeWithScore], List[NodeWithScore]]:
        """
        使用双问题检索：原问题检索通用库，改写问题检索免签/航司库
        
        Args:
            original_query: 原始问题（用于通用库）
            rewritten_query: 改写后的问题（用于免签/航司库）
            strategy: 检索策略 ("visa_free", "airline_visa_free", "both")
            
        Returns:
            (专业库节点列表, 通用库节点列表) - 两个列表分别对应不同的检索结果
        """
        from llama_index.core import QueryBundle
        
        logger.info(f"[双问题检索] 策略: {strategy}")
        logger.info(f"[双问题检索] 原问题: {original_query[:50]}...")
        logger.info(f"==================================================")
        logger.info(f"[双问题检索] 改写问题: {rewritten_query}")
        logger.info(f"==================================================")
        
        # 1. 用原问题检索通用库
        general_query_bundle = QueryBundle(query_str=original_query)
        general_nodes = []
        if self.general_retriever:
            general_nodes = self.general_retriever.retrieve(general_query_bundle)
            logger.info(f"[双问题检索] 通用库（原问题）返回 {len(general_nodes)} 条")
        
        # 2. 用改写问题检索专业库（免签/航司）
        rewritten_query_bundle = QueryBundle(query_str=rewritten_query)
        
        airline_nodes = []
        visa_nodes = []
        
        if strategy in ["airline_visa_free", "airline"]:
            # 检索航司库
            if self.airline_retriever:
                airline_nodes = self.airline_retriever.retrieve(rewritten_query_bundle)
                logger.info(f"[双问题检索] 航司库（改写问题）返回 {len(airline_nodes)} 条")
        
        if strategy in ["airline_visa_free", "visa_free", "both"]:
            # 检索免签库
            if self.visa_free_retriever:
                visa_nodes = self.visa_free_retriever.retrieve(rewritten_query_bundle)
                logger.info(f"[双问题检索] 免签库（改写问题）返回 {len(visa_nodes)} 条")
        
        # 3. 合并专业库结果（航司 + 免签）
        specialized_nodes = airline_nodes + visa_nodes
        
        # 去重专业库节点
        seen_ids = set()
        unique_specialized = []
        for node in specialized_nodes:
            node_id = node.node.node_id
            if node_id not in seen_ids:
                seen_ids.add(node_id)
                unique_specialized.append(node)
        
        # 按分数排序
        unique_specialized.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(
            f"[双问题检索] 专业库合并: 航司{len(airline_nodes)}条 + 免签{len(visa_nodes)}条 "
            f"= 去重后{len(unique_specialized)}条"
        )
        
        # 返回两个独立的列表：专业库节点 和 通用库节点
        return unique_specialized, general_nodes
    
    def _is_visa_free_node(self, node: NodeWithScore) -> bool:
        """判断节点是否来自免签库（通过文件名判断）"""
        file_name = node.node.metadata.get('file_name', '')
        # 简单判断：包含"免签"、"签证"等关键词
        return any(keyword in file_name for keyword in ['免签', '签证', 'visa'])
    
    def _is_airline_node(self, node: NodeWithScore) -> bool:
        """判断节点是否来自航司库（通过文件名判断）"""
        file_name = node.node.metadata.get('file_name', '')
        # 简单判断：包含"民航"、"机组"等关键词
        return any(keyword in file_name for keyword in ['民航', '机组', '航司', 'airline'])
    
    def retrieve(self, query: str) -> List[NodeWithScore]:
        """
        统一检索接口（兼容LlamaIndex标准接口）
        根据初始化时的retriever配置自动选择合适的检索策略
        
        Args:
            query: 查询文本
            
        Returns:
            检索节点列表
        """
        # 判断有哪些retriever可用
        has_visa_free = self.visa_free_retriever is not None
        has_airline = self.airline_retriever is not None
        
        # 根据可用的retriever选择策略
        if has_airline and has_visa_free:
            # 三库都有，使用三库检索
            logger.debug(f"[多库检索] 使用三库检索（通用+免签+航司）")
            return self.retrieve_from_all_three(query)
        elif has_visa_free:
            # 只有免签库，使用双库检索（通用+免签）
            logger.debug(f"[多库检索] 使用双库检索（通用+免签）")
            return self.retrieve_from_both(query)
        else:
            # 只有通用库，直接返回通用库结果
            logger.debug(f"[多库检索] 仅使用通用库")
            from llama_index.core import QueryBundle
            return self.general_retriever.retrieve(QueryBundle(query_str=query))
