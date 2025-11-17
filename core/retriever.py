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

        # 使用 jieba 分词，并过滤异常节点
        tokenized_corpus = []
        valid_nodes = []
        
        for node in nodes:
            # 获取节点内容
            content = node.get_content() if hasattr(node, 'get_content') else (node.text or "")
            
            # 验证内容是否有效（不是JSON格式的元数据）
            # 检查是否是 JSON 序列化的节点对象
            content_stripped = content.strip()
            is_json_node = (
                content_stripped.startswith('{"id_"') or 
                content_stripped.startswith('{"class_name"') or
                (content_stripped.startswith('{') and '"text":' in content_stripped and '"metadata":' in content_stripped)
            )
            
            if not content or is_json_node:
                logger.warning(f"跳过异常节点 {node.node_id[:8]}...: 内容为空或为元数据格式")
                logger.debug(f"  内容预览: {content[:100]}...")
                continue
            
            # 分词
            tokenized_text = " ".join(jieba.lcut(content))
            tokenized_corpus.append(tokenized_text)
            valid_nodes.append(node)
        
        # 更新映射，只包含有效节点
        self._id_to_original_node = {node.node_id: node for node in valid_nodes}
        
        logger.info(f"BM25检索器初始化: 总节点{len(nodes)}个, 有效节点{len(valid_nodes)}个, 跳过{len(nodes)-len(valid_nodes)}个异常节点")
        
        # 检查是否有有效节点
        if len(valid_nodes) == 0:
            logger.error("❌ 所有节点都无效！BM25检索器无法初始化")
            logger.error("请检查 Qdrant 中的数据是否正确，可能需要重建索引")
            raise ValueError(f"BM25检索器初始化失败: {len(nodes)}个节点全部无效，请重建知识库索引")
        
        tokenized_docs = [
            Document(text=text, id_=node.id_)
            for text, node in zip(tokenized_corpus, valid_nodes)
        ]

        self._bm25_retriever = OfficialBM25(
            nodes=tokenized_docs,
            similarity_top_k=similarity_top_k
        )
        super().__init__()

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """执行检索"""
        # 对查询进行分词
        query_keywords = jieba.lcut(query_bundle.query_str)
        tokenized_query = " ".join(query_keywords)
        tokenized_bundle = QueryBundle(query_str=tokenized_query)

        # 检索
        retrieved_nodes = self._bm25_retriever.retrieve(tokenized_bundle)

        # 替换回原始节点，并添加匹配关键词信息
        clean_nodes = []
        for node_with_score in retrieved_nodes:
            original_node = self._id_to_original_node.get(
                node_with_score.node.node_id
            )
            if original_node:
                # 找出文档中匹配的关键词
                doc_content = original_node.get_content() if hasattr(original_node, 'get_content') else (original_node.text or "")
                matched_keywords = [kw for kw in query_keywords if kw in doc_content and len(kw) > 1]
                
                # 将匹配的关键词添加到节点元数据
                original_node.metadata['bm25_matched_keywords'] = matched_keywords
                original_node.metadata['bm25_query_keywords'] = query_keywords
                
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
        rrf_k: float = 60.0,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3
    ):
        self._automerging = automerging_retriever
        self._bm25 = bm25_retriever
        self._rrf_k = rrf_k
        self._vector_weight = vector_weight
        self._bm25_weight = bm25_weight
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

        # 4. 计算加权 RRF 分数
        fused_scores = {}
        vector_score_threshold = 0.01  # 向量分数阈值，低于此值视为无效
        bm25_only_count = 0  # 统计纯BM25结果数量
        
        for node_id in all_nodes:
            score = 0.0
            vector_score = vector_scores.get(node_id, 0.0)
            bm25_score = bm25_scores.get(node_id, 0.0)
            
            # 判断向量检索是否有效（分数 > 阈值）
            vector_valid = node_id in vector_ranks and vector_score > vector_score_threshold
            bm25_valid = node_id in bm25_ranks
            
            # 如果只有BM25有效（向量检索失败或分数过低），使用BM25原始分数
            if not vector_valid and bm25_valid:
                # 纯BM25结果：直接使用BM25分数
                score = bm25_score * self._bm25_weight
                bm25_only_count += 1
            else:
                # 标准RRF融合
                if vector_valid:
                    score += self._vector_weight * (1.0 / (self._rrf_k + vector_ranks[node_id]))
                if bm25_valid:
                    score += self._bm25_weight * (1.0 / (self._rrf_k + bm25_ranks[node_id]))
            
            fused_scores[node_id] = score
        
        # 记录纯BM25结果统计
        if bm25_only_count > 0:
            from utils import logger
            logger.debug(
                f"[RRF融合] 检测到 {bm25_only_count} 个纯BM25结果（向量分数 < {vector_score_threshold}），"
                f"使用BM25原始分数排序"
            )

        # 5. 构建结果并附加元数据
        fused_results = []
        for node_id, score in fused_scores.items():
            node_obj = all_nodes[node_id]
            vector_rank = vector_ranks.get(node_id)
            bm25_rank = bm25_ranks.get(node_id)
            sources = []
            if vector_rank is not None:
                sources.append("vector")
            if bm25_rank is not None:
                sources.append("keyword")

            node_obj.metadata['vector_score'] = vector_scores.get(node_id, 0.0)
            node_obj.metadata['bm25_score'] = bm25_scores.get(node_id, 0.0)
            node_obj.metadata['vector_rank'] = vector_rank
            node_obj.metadata['bm25_rank'] = bm25_rank
            node_obj.metadata['retrieval_sources'] = sources
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
        similarity_top_k: int,
        similarity_top_k_bm25: int
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
            similarity_top_k=similarity_top_k_bm25
        )

        # 混合检索器（使用配置的权重）
        from config.settings import Settings as AppSettings
        return HybridRetriever(
            automerging_retriever, 
            bm25_retriever,
            rrf_k=AppSettings.RRF_K,
            vector_weight=AppSettings.RRF_VECTOR_WEIGHT,
            bm25_weight=AppSettings.RRF_BM25_WEIGHT
        )

