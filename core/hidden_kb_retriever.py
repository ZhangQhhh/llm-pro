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


class HiddenKBRetriever:
    """
    隐藏知识库检索器
    
    用途：
    - 题库内容检索
    - 提升回答准确率但不暴露来源
    - 对用户完全透明
    """
    def __init__(self, retriever, name):
        self.retriever = retriever
        self.name = name
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
        
        logger.info(f"[{self.name}] 开始检索 | 查询: {query[:50]}... | 返回数量: {top_k}")
        
        try:
            # 创建 QueryBundle
            query_bundle = QueryBundle(query_str=query)
            
            # 调用底层检索器
            nodes = self.retriever.retrieve(query_bundle)
            
            if not nodes:
                logger.info(f"[{self.name}] 未检索到相关内容")
                return []
            
            # 取前 top_k 个结果
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