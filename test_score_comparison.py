#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
对比测试：开启/关闭免签功能时的检索得分
用于定位得分降低的真正原因
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Settings
from utils.logger import logger
from services import LLMService, EmbeddingService, KnowledgeService
from llama_index.core import QueryBundle


def test_retrieval_with_reranker(question: str):
    """
    完整测试检索和重排序流程
    模拟 KnowledgeHandler._retrieve_and_rerank 的逻辑
    """
    logger.info("=" * 80)
    logger.info(f"测试问题: {question}")
    logger.info("=" * 80)
    
    # 1. 初始化服务
    logger.info("\n[步骤1] 初始化服务...")
    embedding_service = EmbeddingService()
    embed_model, reranker = embedding_service.initialize()
    
    llm_service = LLMService()
    llm_clients = llm_service.initialize()
    default_llm = llm_service.get_client(Settings.DEFAULT_LLM_ID)
    
    knowledge_service = KnowledgeService(default_llm)
    
    # 2. 构建通用知识库
    logger.info("\n[步骤2] 构建通用知识库...")
    index, all_nodes = knowledge_service.build_or_load_index()
    
    if not (index and all_nodes):
        logger.error("通用知识库构建失败")
        return
    
    logger.info(f"✓ 通用知识库: {len(all_nodes)} 个节点")
    
    # 3. 创建通用检索器
    logger.info("\n[步骤3] 创建通用检索器...")
    retriever = knowledge_service.create_retriever()
    logger.info(f"✓ 通用检索器创建成功")
    
    # 4. 如果启用免签功能，构建免签知识库
    if Settings.ENABLE_VISA_FREE_FEATURE:
        logger.info("\n[步骤4] 构建免签知识库...")
        visa_free_index, visa_free_nodes = knowledge_service.build_or_load_visa_free_index()
        
        if visa_free_index and visa_free_nodes:
            knowledge_service.visa_free_index = visa_free_index
            knowledge_service.visa_free_nodes = visa_free_nodes
            logger.info(f"✓ 免签知识库: {len(visa_free_nodes)} 个节点")
            
            visa_free_retriever = knowledge_service.create_visa_free_retriever()
            logger.info(f"✓ 免签检索器创建成功")
        else:
            logger.warning("免签知识库构建失败")
    
    # 5. 执行检索和重排序（模拟单知识库流程）
    logger.info("\n" + "=" * 80)
    logger.info("开始测试单知识库检索流程")
    logger.info("=" * 80)
    
    # 5.1 初始检索
    logger.info(f"\n[5.1] 初始检索...")
    retrieved_nodes = retriever.retrieve(question)
    logger.info(f"✓ 检索到 {len(retrieved_nodes)} 个节点")
    
    if retrieved_nodes:
        logger.info(f"\n📊 初始检索Top5得分:")
        for i, node in enumerate(retrieved_nodes[:5], 1):
            logger.info(f"  {i}. 得分: {node.score:.4f} | 内容: {node.node.get_content()[:50]}...")
    
    # 5.2 准备重排序输入
    reranker_input_top_n = Settings.RERANKER_INPUT_TOP_N
    reranker_input = retrieved_nodes[:reranker_input_top_n]
    logger.info(f"\n[5.2] 选取前 {len(reranker_input)} 个节点送入重排序")
    
    # 5.3 重排序
    logger.info(f"\n[5.3] 执行重排序...")
    query_bundle = QueryBundle(question)
    
    if reranker_input:
        reranked_nodes = reranker.postprocess_nodes(
            reranker_input,
            query_bundle=query_bundle
        )
        logger.info(f"✓ 重排序完成，得到 {len(reranked_nodes)} 个节点")
        
        if reranked_nodes:
            logger.info(f"\n📊 重排序后Top5得分:")
            for i, node in enumerate(reranked_nodes[:5], 1):
                logger.info(f"  {i}. 得分: {node.score:.4f} | 内容: {node.node.get_content()[:50]}...")
        
        # 5.4 阈值过滤
        threshold = Settings.RERANK_SCORE_THRESHOLD
        final_nodes = [node for node in reranked_nodes if node.score >= threshold]
        
        logger.info(f"\n[5.4] 阈值过滤 (threshold={threshold})")
        logger.info(f"✓ 过滤后剩余 {len(final_nodes)} 个节点")
        
        if final_nodes:
            logger.info(f"\n📊 最终结果Top5得分:")
            for i, node in enumerate(final_nodes[:5], 1):
                logger.info(f"  {i}. 得分: {node.score:.4f} | 内容: {node.node.get_content()[:50]}...")
        
        # 6. 统计分析
        logger.info("\n" + "=" * 80)
        logger.info("统计分析")
        logger.info("=" * 80)
        
        if retrieved_nodes and reranked_nodes:
            initial_max = max(n.score for n in retrieved_nodes)
            rerank_max = max(n.score for n in reranked_nodes)
            
            logger.info(f"初始检索最高分: {initial_max:.4f}")
            logger.info(f"重排序后最高分: {rerank_max:.4f}")
            logger.info(f"得分提升: {(rerank_max - initial_max):.4f} ({(rerank_max/initial_max - 1)*100:.1f}%)")
            
            logger.info(f"\n初始检索平均分: {sum(n.score for n in retrieved_nodes[:10])/10:.4f}")
            logger.info(f"重排序后平均分: {sum(n.score for n in reranked_nodes[:10])/10:.4f}")
    else:
        logger.error("❌ reranker_input 为空，无法重排序")
    
    logger.info("\n" + "=" * 80)
    logger.info("测试完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    # 测试问题（非免签问题）
    test_question = "内地居民办理了两次有效赴港旅游签注和一次有效赴澳旅游签注。在内地边检机关扣减无误的前提下，下列会导致该旅客所持电子往来港澳通行证签注计数器JS0、JS1、JS2、JS3分别为2、0、1、0的情形是。C.该旅客持用该本证件从内地出境后过境香港,实际未进入香港.前往澳门，在澳门逗留6日后返回内地。"
    
    logger.info("\n" + "🔍" * 40)
    logger.info(f"免签功能状态: {'✅ 开启' if Settings.ENABLE_VISA_FREE_FEATURE else '❌ 关闭'}")
    logger.info("🔍" * 40 + "\n")
    
    test_retrieval_with_reranker(test_question)
    
    logger.info("\n\n" + "📋" * 40)
    logger.info("测试建议")
    logger.info("📋" * 40)
    logger.info("\n1. 先运行此脚本，记录 ENABLE_VISA_FREE_FEATURE=false 的结果")
    logger.info("2. 修改 .env 文件，设置 ENABLE_VISA_FREE_FEATURE=true")
    logger.info("3. 再次运行此脚本，记录结果")
    logger.info("4. 对比两次的 '重排序后Top5得分'")
    logger.info("\n如果得分确实降低，说明问题存在；如果得分一致，说明问题在其他地方。")
