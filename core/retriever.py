# -*- coding: utf-8 -*-
"""
检索器模块
实现混合检索（BM25 + 向量检索 + RRF 融合）
"""
import jieba
import os
from typing import List
from llama_index.core import Document, QueryBundle
from llama_index.core.retrievers import AutoMergingRetriever, BaseRetriever
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core import VectorStoreIndex
from llama_index.retrievers.bm25 import BM25Retriever as OfficialBM25
from utils.logger import logger
from utils.keyword_ranker import keyword_ranker

# 加载自定义词典（保留默认词典，只增强自定义词）
CUSTOM_DICT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dict", "custom_dict.txt")
CUSTOM_WORDS_SET = set()  # 全局变量，用于标记自定义词

if os.path.exists(CUSTOM_DICT_PATH):
    # 使用 jieba.load_userdict 加载自定义词典（保留默认词典）
    jieba.load_userdict(CUSTOM_DICT_PATH)
    
    # 提取自定义词典的词和权重
    custom_words = {}
    line_count = 0
    empty_lines = 0
    comment_lines = 0
    
    with open(CUSTOM_DICT_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line_count += 1
            line = line.strip()
            
            if not line:
                empty_lines += 1
                continue
                
            if line.startswith('#'):
                comment_lines += 1
                continue
            
            # 解析词和权重：格式为 "词 权重 词性" 或 "词\t权重\t词性"
            parts = line.split()
            if len(parts) >= 2:
                word = parts[0]
                try:
                    freq = int(parts[1])
                    custom_words[word] = freq
                    CUSTOM_WORDS_SET.add(word)
                except ValueError:
                    custom_words[word] = 100000
                    CUSTOM_WORDS_SET.add(word)
                    logger.warning(f"第 {line_count} 行权重解析失败，使用默认值: '{line}'")
            elif len(parts) == 1:
                custom_words[parts[0]] = 100000
                CUSTOM_WORDS_SET.add(parts[0])
            else:
                logger.warning(f"第 {line_count} 行解析失败: '{line}'")
    
    # 对自定义词赋予更高权重（不清空默认词典）
    for word, freq in custom_words.items():
        jieba.dt.FREQ[word] = freq
    
    # 重新计算总词频
    jieba.dt.total = sum(jieba.dt.FREQ.values())
    
    logger.info(f"✅ 已加载自定义词典（保留默认词典）: {CUSTOM_DICT_PATH}")
    logger.info(f"📊 词典统计: 总行数={line_count}, 空行={empty_lines}, 注释行={comment_lines}")
    logger.info(f"✅ 自定义词条数: {len(custom_words)}")
    logger.info(f"✅ jieba 总词条数: {len(jieba.dt.FREQ)}")
    logger.info(f"✅ 自定义词示例（前10个）: {list(custom_words.keys())[:10]}")
else:
    logger.warning(f"⚠️ 自定义词典不存在: {CUSTOM_DICT_PATH}")


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
            
            # 分词，过滤单字即可（保证索引完整性）
            all_tokens = jieba.lcut(content)
            filtered_tokens = [token for token in all_tokens if len(token) > 1]
            tokenized_text = " ".join(filtered_tokens)
            
            # 调试：记录第一个节点的分词情况
            if len(valid_nodes) == 0:
                logger.info(f"[BM25索引构建-示例] 原始tokens数: {len(all_tokens)}, 过滤后: {len(filtered_tokens)}")
                logger.info(f"[BM25索引构建-示例] 过滤后tokens示例: {filtered_tokens[:20]}")  # 只显示前20个
            
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
        all_keywords = jieba.lcut(query_bundle.query_str)
        
        # 检索阶段：使用停用词过滤
        query_keywords_for_retrieval = keyword_ranker.filter_keywords(all_keywords)
        
     
        
        # ⭐ 新增：检查是否过度过滤
        if len(query_keywords_for_retrieval) == 0:
            logger.warning(
                f"[BM25检索-警告] 停用词过滤后查询为空！\n"
                f"  原始查询: {query_bundle.query_str}\n"
                f"  原始分词: {all_keywords}\n"
                f"  建议: 检查停用词表或使用原始分词"
            )
            # 回退到原始分词（只过滤单字）
            query_keywords_for_retrieval = [kw for kw in all_keywords if len(kw) > 1]
          
        
        tokenized_query = " ".join(query_keywords_for_retrieval)
        tokenized_bundle = QueryBundle(query_str=tokenized_query)

        # 检索
        retrieved_nodes = self._bm25_retriever.retrieve(tokenized_bundle)
        
        # ⭐ 新增：记录检索结果分数
        if retrieved_nodes:
            bm25_scores = [f"{n.score:.4f}" for n in retrieved_nodes[:5]]
            logger.info(f"[BM25检索-结果] 返回 {len(retrieved_nodes)} 个节点 | Top5分数: {', '.join(bm25_scores)}")
        else:
            logger.warning(f"[BM25检索-结果] 未找到任何匹配节点")

        # 替换回原始节点，并添加匹配关键词信息
        clean_nodes = []
        for node_with_score in retrieved_nodes:
            original_node = self._id_to_original_node.get(
                node_with_score.node.node_id
            )
            if original_node:
                # 找出文档中匹配的关键词（使用所有检索关键词）
                doc_content = original_node.get_content() if hasattr(original_node, 'get_content') else (original_node.text or "")
                matched_keywords_raw = [kw for kw in query_keywords_for_retrieval if kw in doc_content]
                
                # 使用 keyword_ranker 过滤停用词（黑名单）
                matched_keywords = keyword_ranker.filter_keywords(matched_keywords_raw)
                
                
                # 将匹配的关键词添加到节点元数据
                original_node.metadata['bm25_matched_keywords'] = matched_keywords
                original_node.metadata['bm25_query_keywords'] = query_keywords_for_retrieval
                
                # Add a new metadata field 'bm25_relevance_score'
                original_node.metadata['bm25_relevance_score'] = node_with_score.score
                
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
        
        #  新增：记录向量检索结果
        if automerging_nodes:
            vector_scores_display = [f"{n.score:.4f}" for n in automerging_nodes[:5]]
        else:
            logger.warning(f"[向量检索-结果] 未找到任何匹配节点")

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
        #  修复1: 降低向量分数阈值，避免过度过滤（从 0.01 降到 0.001）
        vector_score_threshold = 0.001  # 向量分数阈值，低于此值视为无效
        bm25_only_count = 0  # 统计纯BM25结果数量
        
        for node_id in all_nodes:
            score = 0.0
            vector_score = vector_scores.get(node_id, 0.0)
            bm25_score = bm25_scores.get(node_id, 0.0)
            
            # 判断向量检索是否有效（分数 > 阈值）
            vector_valid = node_id in vector_ranks and vector_score > vector_score_threshold
            bm25_valid = node_id in bm25_ranks
            
            #  修复2: 改进纯BM25结果的分数计算，使用 RRF 而非原始分数
            if not vector_valid and bm25_valid:
                # 纯BM25结果：使用 RRF 公式计算，确保分数在合理范围
                # 使用 BM25 排名计算 RRF 分数，并乘以权重
                score = self._bm25_weight * (1.0 / (self._rrf_k + bm25_ranks[node_id]))
                # 添加一个基础分数，避免分数过低
                score = max(score, bm25_score * 0.1)  # 至少保留 BM25 分数的 10%
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
            logger.info(
                f"[RRF融合] 检测到 {bm25_only_count} 个纯BM25结果（向量分数 < {vector_score_threshold}），"
                f"使用改进的 RRF 分数计算"
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

