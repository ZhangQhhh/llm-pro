# -*- coding: utf-8 -*-
"""
Keyword Table 检索器
基于 LlamaIndex 的 KeywordTableIndex 实现关键词检索
"""
import jieba
from typing import List
from llama_index.core import QueryBundle
from llama_index.core.schema import NodeWithScore
from llama_index.core.retrievers import BaseRetriever
from utils.logger import logger
from utils.keyword_ranker import keyword_ranker


class KeywordTableRetriever(BaseRetriever):
    """
    Keyword Table 检索器
    
    使用 LlamaIndex 的 KeywordTableIndex 进行关键词检索
    """
    
    def __init__(
        self,
        keyword_index,
        similarity_top_k: int = 10,
        min_score: float = 0.3
    ):
        """
        初始化 Keyword Table 检索器
        
        Args:
            keyword_index: LlamaIndex KeywordTableIndex 实例
            similarity_top_k: 返回的节点数量
            min_score: 最低分数阈值
        """
        self._keyword_index = keyword_index
        self._similarity_top_k = similarity_top_k
        self._min_score = min_score
        self._keyword_retriever = keyword_index.as_retriever(
            similarity_top_k=similarity_top_k
        )
        
        logger.info(
            f"KeywordTableRetriever 初始化完成 | "
            f"top_k={similarity_top_k} | min_score={min_score}"
        )
    
    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """
        执行 Keyword Table 检索
        
        Args:
            query_bundle: 查询对象
            
        Returns:
            检索到的节点列表
        """
        # 1. 对查询进行分词和停用词过滤
        all_keywords = jieba.lcut(query_bundle.query_str)
        filtered_keywords = keyword_ranker.filter_keywords(all_keywords)
        
        
        
        if not filtered_keywords:
            logger.warning("[KeywordTable检索] 过滤后无关键词，返回空结果")
            return []
        
        # 2. 调用 keyword table 检索
        try:
            retrieved_nodes = self._keyword_retriever.retrieve(query_bundle)
            
            
            
            # 3. 过滤低分节点
            filtered_nodes = []
            for node in retrieved_nodes:
                # 处理 score 为 None 的情况（Keyword Table 可能不返回分数）
                node_score = node.score if node.score is not None else 1.0
                
                if node_score >= self._min_score:
                    # 标记检索来源
                    if 'retrieval_sources' not in node.node.metadata:
                        node.node.metadata['retrieval_sources'] = []
                    
                    if 'keyword_table' not in node.node.metadata['retrieval_sources']:
                        node.node.metadata['retrieval_sources'].append('keyword_table')
                    
                    # 记录 keyword table 分数
                    node.node.metadata['keyword_table_score'] = node.score
                    
                    # 提取关键词（如果 keyword index 提供了）
                    if hasattr(node.node, 'keywords') and node.node.keywords:
                        node.node.metadata['keyword_table_keywords'] = node.node.keywords
                    else:
                        # 使用查询关键词作为匹配关键词
                        node.node.metadata['keyword_table_keywords'] = filtered_keywords
                    
                    filtered_nodes.append(node)
                else:
                    debug_score = node.score if node.score is not None else 0.0
                    logger.debug(
                        f"[KeywordTable检索] 过滤低分节点 | "
                        f"score={debug_score:.4f} < {self._min_score}"
                    )
            
            if filtered_nodes:
                first_score = filtered_nodes[0].score if filtered_nodes[0].score is not None else 1.0
                last_score = filtered_nodes[-1].score if filtered_nodes[-1].score is not None else 1.0
                logger.info(
                    f"[KeywordTable检索] 过滤后返回 {len(filtered_nodes)} 个节点 | "
                    f"分数范围: {first_score:.4f} - {last_score:.4f}"
                )
            else:
                logger.info("[KeywordTable检索] 过滤后无节点")
            
            return filtered_nodes
            
        except Exception as e:
            logger.error(f"[KeywordTable检索] 检索失败: {e}", exc_info=True)
            return []
    
    def get_stats(self) -> dict:
        """获取检索器统计信息"""
        return {
            "type": "keyword_table",
            "similarity_top_k": self._similarity_top_k,
            "min_score": self._min_score,
            "index_type": type(self._keyword_index).__name__
        }
