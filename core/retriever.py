# -*- coding: utf-8 -*-
"""
检索器模块
实现混合检索（BM25 + 向量检索 + RRF 融合）
"""
import jieba
from typing import List
from llama_index.core import Document, QueryBundle
from llama_index.core.retrievers import AutoMergingRetriever, BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core import VectorStoreIndex
from llama_index.retrievers.bm25 import BM25Retriever as OfficialBM25
from utils.logger import logger


class CleanBM25Retriever(BaseRetriever):
    """清理后的 BM25 检索器（使用 jieba 分词）"""

    def __init__(self, nodes: List[TextNode], similarity_top_k: int = 2):
        self._id_to_original_node = {node.node_id: node for node in nodes}

        # 使用 jieba 分词
        tokenized_corpus = [
            " ".join(jieba.lcut(node.get_content()))
            for node in nodes
        ]
        tokenized_docs = [
            Document(text=text, id_=node.id_)
            for text, node in zip(tokenized_corpus, nodes)
        ]

        self._bm25_retriever = OfficialBM25(
            nodes=tokenized_docs,
            similarity_top_k=similarity_top_k
        )
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """执行检索"""
        # 对查询进行分词
        tokenized_query = " ".join(jieba.lcut(query_bundle.query_str))
        tokenized_bundle = QueryBundle(query_str=tokenized_query)

        # 检索
        retrieved_nodes = self._bm25_retriever.retrieve(tokenized_bundle)

        # 替换回原始节点
        clean_nodes = []
        for node_with_score in retrieved_nodes:
            original_node = self._id_to_original_node.get(
                node_with_score.node.node_id
            )
            if original_node:
                clean_nodes.append(
                    NodeWithScore(node=original_node, score=node_with_score.score)
                )

        return clean_nodes


class HybridRetriever(BaseRetriever):
    """混合检索器（向量 + BM25 + RRF 融合）"""

    def __init__(
        self,
        automerging_retriever: AutoMergingRetriever,
        bm25_retriever: CleanBM25Retriever,
        rrf_k: float = 60.0
    ):
        self._automerging = automerging_retriever
        self._bm25 = bm25_retriever
        self._rrf_k = rrf_k
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """
        使用 Reciprocal Rank Fusion (RRF) 算法融合检索结果

        Args:
            query_bundle: 查询内容

        Returns:
            融合后的检索结果
        """
        # 1. 分别执行两种检索
        automerging_nodes = self._automerging.retrieve(query_bundle)
        bm25_nodes = self._bm25.retrieve(query_bundle)

        # 2. 收集所有唯一节点
        all_nodes = {n.node.node_id: n.node for n in automerging_nodes}
        all_nodes.update({n.node.node_id: n.node for n in bm25_nodes})

        # 3. 计算排名和原始分数
        vector_ranks = {
            node.node.node_id: rank
            for rank, node in enumerate(automerging_nodes, 1)
        }
        bm25_ranks = {
            node.node.node_id: rank
            for rank, node in enumerate(bm25_nodes, 1)
        }
        vector_scores = {n.node.node_id: n.score for n in automerging_nodes}
        bm25_scores = {n.node.node_id: n.score for n in bm25_nodes}

        # 4. 计算 RRF 分数
        fused_scores = {}
        for node_id in all_nodes:
            score = 0.0
            if node_id in vector_ranks:
                score += 1.0 / (self._rrf_k + vector_ranks[node_id])
            if node_id in bm25_ranks:
                score += 1.0 / (self._rrf_k + bm25_ranks[node_id])
            fused_scores[node_id] = score

        # 5. 构建结果并附加元数据
        fused_results = []
        for node_id, score in fused_scores.items():
            node_obj = all_nodes[node_id]
            node_obj.metadata['vector_score'] = vector_scores.get(node_id, 0.0)
            node_obj.metadata['bm25_score'] = bm25_scores.get(node_id, 0.0)
            node_obj.metadata['initial_score'] = score

            fused_results.append(NodeWithScore(node=node_obj, score=score))

        # 6. 按 RRF 分数降序排序
        sorted_results = sorted(
            fused_results,
            key=lambda x: x.score,
            reverse=True
        )

        return sorted_results


class RetrieverFactory:
    """检索器工厂"""

    @staticmethod
    def create_hybrid_retriever(
        index: VectorStoreIndex,
        all_nodes: List[TextNode],
        similarity_top_k: int
    ) -> HybridRetriever:
        """
        创建混合检索器

        Args:
            index: 向量索引
            all_nodes: 所有节点
            similarity_top_k: 检索数量

        Returns:
            混合检索器实例
        """
        logger.info("创建混合检索器（向量 + BM25 + RRF）...")

        # 向量检索器
        vector_retriever = index.as_retriever(similarity_top_k=similarity_top_k)

        # 自动合并检索器
        automerging_retriever = AutoMergingRetriever(
            vector_retriever,
            index.storage_context,
            verbose=False
        )

        # BM25 检索器
        bm25_retriever = CleanBM25Retriever(
            all_nodes,
            similarity_top_k=similarity_top_k
        )

        # 混合检索器
        return HybridRetriever(automerging_retriever, bm25_retriever)

