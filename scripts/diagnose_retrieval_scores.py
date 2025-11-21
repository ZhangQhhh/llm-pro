# -*- coding: utf-8 -*-
"""
检索分数诊断脚本
用于测试和诊断检索分数过低的问题
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Settings as AppSettings
from services.knowledge_service import KnowledgeService
from services.embedding_service import EmbeddingService
from utils.logger import logger
from llama_index.core import QueryBundle



def diagnose_retrieval():
    """诊断检索分数问题"""
    
    logger.info("=" * 80)
    logger.info("检索分数诊断工具")
    logger.info("=" * 80)
    
    # 1. 初始化 Embedding 和 Reranker
    logger.info("\n[步骤1] 初始化 Embedding 和 Reranker...")
    embedding_service = EmbeddingService()
    embed_model, reranker = embedding_service.initialize()
    
    # 2. 初始化知识库服务（需要先创建一个简单的LLM对象）
    logger.info("\n[步骤2] 初始化知识库服务...")
    from llama_index.core.llms import MockLLM
    # 使用 MockLLM 作为占位符，因为我们只需要检索功能
    mock_llm = MockLLM()
    knowledge_service = KnowledgeService(mock_llm)
    
    # 3. 加载索引
    logger.info("\n[步骤3] 加载通用知识库索引...")
    index, all_nodes = knowledge_service.build_or_load_index()
    
    if not index or not all_nodes:
        logger.error("索引加载失败！")
        return
    
    logger.info(f"✓ 索引加载成功 | 节点数: {len(all_nodes)}")
    
    # 4. 创建检索器
    logger.info("\n[步骤4] 创建混合检索器...")
    retriever = knowledge_service.create_retriever()
    
    if not retriever:
        logger.error("检索器创建失败！")
        return
    
    logger.info(f"✓ 检索器创建成功")
    logger.info(f"  - RRF_K: {AppSettings.RRF_K}")
    logger.info(f"  - 向量权重: {AppSettings.RRF_VECTOR_WEIGHT}")
    logger.info(f"  - BM25权重: {AppSettings.RRF_BM25_WEIGHT}")
    logger.info(f"  - 检索数量: {AppSettings.RETRIEVAL_TOP_K}")
    logger.info(f"  - BM25检索数量: {AppSettings.RETRIEVAL_TOP_K_BM25}")
    
    # 5. 测试查询
    test_queries = [
        "中国与外国互免签证协议",
        "免签政策",
        "口岸签证",
        "24小时过境免签"
    ]
    
    logger.info("\n[步骤5] 测试检索...")
    logger.info("=" * 80)
    
    for i, query in enumerate(test_queries, 1):
        logger.info(f"\n测试 {i}/{len(test_queries)}: {query}")
        logger.info("-" * 80)
        
        # 执行检索
        query_bundle = QueryBundle(query_str=query)
        nodes = retriever.retrieve(query_bundle)
        
        if not nodes:
            logger.warning(f"⚠️ 未检索到任何结果")
            continue
        
        logger.info(f"✓ 检索到 {len(nodes)} 个结果")
        
        # 分析分数分布
        scores = [n.score for n in nodes]
        logger.info(f"\n分数统计:")
        logger.info(f"  - 最高分: {max(scores):.6f}")
        logger.info(f"  - 最低分: {min(scores):.6f}")
        logger.info(f"  - 平均分: {sum(scores)/len(scores):.6f}")
        logger.info(f"  - 中位数: {sorted(scores)[len(scores)//2]:.6f}")
        
        # 显示 Top 5 结果
        logger.info(f"\nTop 5 结果:")
        for j, node in enumerate(nodes[:5], 1):
            metadata = node.node.metadata
            logger.info(f"\n  [{j}] 分数: {node.score:.6f}")
            logger.info(f"      初始分数: {metadata.get('initial_score', 'N/A'):.6f}")
            logger.info(f"      向量分数: {metadata.get('vector_score', 0.0):.6f}")
            logger.info(f"      BM25分数: {metadata.get('bm25_score', 0.0):.6f}")
            logger.info(f"      向量排名: {metadata.get('vector_rank', 'N/A')}")
            logger.info(f"      BM25排名: {metadata.get('bm25_rank', 'N/A')}")
            logger.info(f"      检索来源: {metadata.get('retrieval_sources', [])}")
            logger.info(f"      文件名: {metadata.get('file_name', 'N/A')}")
            
            # 显示内容预览
            content = node.node.get_content()
            logger.info(f"      内容预览: {content[:100]}...")
        
        # 检查是否有纯 BM25 结果
        pure_bm25_count = sum(1 for n in nodes if 'keyword' in n.node.metadata.get('retrieval_sources', []) 
                              and 'vector' not in n.node.metadata.get('retrieval_sources', []))
        if pure_bm25_count > 0:
            logger.info(f"\n⚠️ 检测到 {pure_bm25_count} 个纯BM25结果（向量检索失败）")
        
        logger.info("\n" + "=" * 80)
    
    # 5. 重排序测试
    logger.info("\n[步骤6] 测试重排序...")
    logger.info("=" * 80)
    
    query = test_queries[0]
    logger.info(f"测试查询: {query}")
    
    # 先检索
    query_bundle = QueryBundle(query_str=query)
    retrieved_nodes = retriever.retrieve(query_bundle)
    
    if not retrieved_nodes:
        logger.warning("检索结果为空，无法测试重排序")
        return
    
    logger.info(f"检索到 {len(retrieved_nodes)} 个节点")
    
    # 取前 30 个送入重排序
    reranker_input = retrieved_nodes[:AppSettings.RERANKER_INPUT_TOP_N]
    logger.info(f"送入重排序: {len(reranker_input)} 个节点")
    
    # 重排序
    reranked_nodes = reranker.postprocess_nodes(
        reranker_input,
        query_bundle=query_bundle
    )
    
    logger.info(f"重排序后: {len(reranked_nodes)} 个节点")
    
    # 分析重排序分数
    if reranked_nodes:
        rerank_scores = [n.score for n in reranked_nodes]
        logger.info(f"\n重排序分数统计:")
        logger.info(f"  - 最高分: {max(rerank_scores):.6f}")
        logger.info(f"  - 最低分: {min(rerank_scores):.6f}")
        logger.info(f"  - 平均分: {sum(rerank_scores)/len(rerank_scores):.6f}")
        
        logger.info(f"\nTop 5 重排序结果:")
        for j, node in enumerate(reranked_nodes[:5], 1):
            logger.info(f"  [{j}] 重排序分数: {node.score:.6f}")
            logger.info(f"      文件名: {node.node.metadata.get('file_name', 'N/A')}")
            logger.info(f"      内容预览: {node.node.get_content()[:100]}...")
    
    logger.info("\n" + "=" * 80)
    logger.info("诊断完成！")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        diagnose_retrieval()
    except Exception as e:
        import logging
        logging.error(f"诊断失败: {e}", exc_info=True)
