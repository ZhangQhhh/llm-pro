# -*- coding: utf-8 -*-
"""
多知识库检索器
支持从多个知识库并行检索并按权重融合结果
"""
from typing import List, Optional
from llama_index.core import QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.schema import NodeWithScore
from utils.logger import logger


class MultiKBRetriever(BaseRetriever):
    """
    多知识库检索器
    
    支持从多个知识库并行检索，并按照指定的权重分配检索数量
    """

    def __init__(
        self,
        general_retriever: BaseRetriever,
        visa_free_retriever: Optional[BaseRetriever] = None,
        general_count: int = 4,
        visa_free_count: int = 6
    ):
        """
        初始化多知识库检索器
        
        Args:
            general_retriever: 通用知识库检索器
            visa_free_retriever: 免签政策知识库检索器（可选）
            general_count: 从通用知识库检索的文档数量
            visa_free_count: 从免签知识库检索的文档数量
        """
        self.general_retriever = general_retriever
        self.visa_free_retriever = visa_free_retriever
        self.general_count = general_count
        self.visa_free_count = visa_free_count
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """
        执行单知识库检索（默认只使用通用知识库）
        
        Args:
            query_bundle: 查询内容
            
        Returns:
            检索结果列表
        """
        # 默认只从通用知识库检索
        return self.general_retriever.retrieve(query_bundle)

    def retrieve_from_both(
        self,
        query_bundle: QueryBundle
    ) -> List[NodeWithScore]:
        """
        从两个知识库并行检索并融合结果
        
        Args:
            query_bundle: 查询内容
            
        Returns:
            融合后的检索结果，免签知识库的结果在前
        """
        if not self.visa_free_retriever:
            logger.warning("免签知识库检索器未初始化，只从通用知识库检索")
            return self.general_retriever.retrieve(query_bundle)

        logger.info(
            f"并行检索两个知识库: "
            f"免签库({self.visa_free_count}个) + "
            f"通用库({self.general_count}个)"
        )

        # 并行检索两个知识库
        # 注意：这里使用同步方式，如果需要真正的并行可以使用 asyncio
        visa_free_nodes = self.visa_free_retriever.retrieve(query_bundle)
        general_nodes = self.general_retriever.retrieve(query_bundle)

        # 取指定数量的节点
        visa_free_results = visa_free_nodes[:self.visa_free_count]
        general_results = general_nodes[:self.general_count]

        # 标记节点来源
        for node in visa_free_results:
            node.node.metadata['kb_source'] = 'visa_free'
        
        for node in general_results:
            node.node.metadata['kb_source'] = 'general'

        # 合并结果：免签知识库的结果在前（权重更高）
        merged_results = visa_free_results + general_results

        logger.info(
            f"检索完成: 免签库{len(visa_free_results)}个 + "
            f"通用库{len(general_results)}个 = "
            f"总计{len(merged_results)}个节点"
        )

        return merged_results

    def retrieve_general_only(
        self,
        query_bundle: QueryBundle,
        top_k: Optional[int] = None
    ) -> List[NodeWithScore]:
        """
        只从通用知识库检索
        
        Args:
            query_bundle: 查询内容
            top_k: 检索数量（可选）
            
        Returns:
            检索结果列表
        """
        logger.info("只从通用知识库检索")
        results = self.general_retriever.retrieve(query_bundle)
        
        # 标记节点来源
        for node in results:
            node.node.metadata['kb_source'] = 'general'
        
        if top_k:
            results = results[:top_k]
        
        return results


class MultiKBRetrieverFactory:
    """多知识库检索器工厂"""

    @staticmethod
    def create_multi_kb_retriever(
        general_retriever: BaseRetriever,
        visa_free_retriever: Optional[BaseRetriever],
        general_count: int,
        visa_free_count: int
    ) -> MultiKBRetriever:
        """
        创建多知识库检索器
        
        Args:
            general_retriever: 通用知识库检索器
            visa_free_retriever: 免签政策知识库检索器
            general_count: 从通用知识库检索的文档数量
            visa_free_count: 从免签知识库检索的文档数量
            
        Returns:
            多知识库检索器实例
        """
        logger.info(
            f"创建多知识库检索器: "
            f"通用库({general_count}个) + "
            f"免签库({visa_free_count}个)"
        )
        
        return MultiKBRetriever(
            general_retriever=general_retriever,
            visa_free_retriever=visa_free_retriever,
            general_count=general_count,
            visa_free_count=visa_free_count
        )
