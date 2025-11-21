# -*- coding: utf-8 -*-
"""
隐藏知识库检索器
用于题库等需要隐藏来源的知识库检索

核心特性：
1. 独立检索和打分
2. 内容注入到上下文但不显示来源
3. 思考过程中不提及
4. 前端完全不可见
"""
from typing import List, Optional
from llama_index.core import QueryBundle
from llama_index.core.schema import NodeWithScore
from config import Settings
from utils.logger import logger
from utils.hidden_kb_logger import hidden_kb_logger


class HiddenKBRetriever:
    """
    隐藏知识库检索器
    
    用途：
    - 题库内容检索
    - 提升回答准确率但不暴露来源
    - 对用户完全透明
    """
    def __init__(self, retriever, name, reranker=None):
        self.retriever = retriever
        self.name = name
        self.reranker = reranker
        self.enabled = True

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None
    ) -> List[NodeWithScore]:
        """
        检索隐藏知识库
        
        Args:
            query: 查询文本
            top_k: 返回结果数量（None则使用配置）
        
        Returns:
            检索节点列表（已标记为隐藏）
        """
        if not self.enabled:
            logger.debug(f"[{self.name}] 检索器未启用，跳过检索")
            return []
        
        # 使用配置的默认值
        if top_k is None:
            top_k = getattr(Settings, 'HIDDEN_KB_RETRIEVAL_COUNT', 5)
        
        # 记录检索开始到专用日志
        hidden_kb_logger.log_retrieval_start(query, self.name)
        
        logger.info(f"[{self.name}] 开始检索 | 查询: {query[:50]}... | 返回数量: {top_k}")
        
        try:
            # 创建 QueryBundle
            query_bundle = QueryBundle(query_str=query)
            
            # 调用底层检索器（混合检索）
            nodes = self.retriever.retrieve(query_bundle)
            
            if not nodes:
                logger.info(f"[{self.name}] 未检索到相关内容")
                # 记录空结果到专用日志
                hidden_kb_logger.log_retrieval_result(query, [], self.name)
                return []
            
            logger.info(f"[{self.name}] 初始检索完成 | 返回 {len(nodes)} 条")
            
            # 重排序（如果有 reranker）
            if self.reranker:
                # 取前 N 条送入重排序
                rerank_top_n = getattr(Settings, 'HIDDEN_KB_RERANK_TOP_N', 10)
                reranker_input = nodes[:rerank_top_n]
                
                logger.info(f"[{self.name}] 开始重排序 | 输入: {len(reranker_input)} 条")
                
                # 记录重排序前的分数
                if reranker_input:
                    initial_scores = [f"{n.score:.4f}" for n in reranker_input[:3]]
                    logger.debug(f"[{self.name}] 重排序前Top3分数(RRF): {', '.join(initial_scores)}")
                
                # 执行重排序
                reranked_nodes = self.reranker.postprocess_nodes(
                    reranker_input,
                    query_bundle=query_bundle
                )
                
                logger.info(f"[{self.name}] 重排序完成 | 返回 {len(reranked_nodes)} 条")
                
                # 记录重排序后的分数
                if reranked_nodes:
                    rerank_scores = [f"{n.score:.4f}" for n in reranked_nodes[:3]]
                    logger.info(f"[{self.name}] 重排序后Top3分数(Reranker): {', '.join(rerank_scores)}")
                
                # 从重排序结果中取前 top_k 个
                selected_nodes = reranked_nodes[:top_k]
            else:
                # 没有 reranker，直接取前 top_k 个
                logger.debug(f"[{self.name}] 未配置 Reranker，使用 RRF 分数")
                selected_nodes = nodes[:top_k]
            
            # 标记为隐藏节点（添加元数据）
            for node in selected_nodes:
                node.node.metadata['is_hidden'] = True
                node.node.metadata['hidden_kb_name'] = self.name
            
            logger.info(
                f"[{self.name}] 检索完成 | "
                f"返回 {len(selected_nodes)} 条 | "
                f"最高分: {selected_nodes[0].score:.4f}"
            )
            
            # 记录详细得分（调试用）
            if len(selected_nodes) > 0:
                scores = [f"{n.score:.4f}" for n in selected_nodes[:3]]
                logger.debug(f"[{self.name}] Top3得分: {', '.join(scores)}")
            
            # 记录检索结果到专用日志
            hidden_kb_logger.log_retrieval_result(query, selected_nodes, self.name)
            
            return selected_nodes
            
        except Exception as e:
            logger.error(f"[{self.name}] 检索失败: {e}", exc_info=True)
            return []

    def silent_retrieve(
        self,
        query: str,
        top_k: Optional[int] = None
    ) -> List[NodeWithScore]:
        """
        静默检索（不记录详细日志）
        适用于批量或不需要详细日志的场景
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
        
        Returns:
            检索列表
        """
        if not self.enabled:
            return []
        
        try:
            if top_k is None:
                top_k = getattr(Settings, 'HIDDEN_KB_RETRIEVAL_COUNT', 5)
            
            query_bundle = QueryBundle(query_str=query)
            nodes = self.retriever.retrieve(query_bundle)
            
            if not nodes:
                return []
            
            selected_nodes = nodes[:top_k]
            
            for node in selected_nodes:
                node.node.metadata['is_hidden'] = True
                node.node.metadata['hidden_kb_name'] = self.name
            
            return selected_nodes
            
        except Exception as e:
            logger.error(f"[{self.name}] 检索失败: {e}", exc_info=True)
            return []

    def get_stats(self) -> dict:
        """
        获取检索器统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "name": self.name,
            "enabled": self.enabled,
            "retriever_type": type(self.retriever).__name__ if self.retriever else None
        }