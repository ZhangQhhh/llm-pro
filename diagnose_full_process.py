#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断脚本：完整模拟实际应用的调用流程
关键发现：测试脚本正常(0.98)，实际应用异常(0.05)
目标：找出两者的差异
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Settings
from utils.logger import logger
from services import LLMService, EmbeddingService, KnowledgeService
from core.intent_classifier import IntentClassifier
from llama_index.core import QueryBundle


def test_with_intent_classifier():
    """
    完整模拟实际应用流程，包括意图分类
    """
    logger.info("=" * 80)
    logger.info("完整模拟实际应用流程")
    logger.info("=" * 80)
    
    test_question = "内地居民办理了两次有效赴港旅游签注和一次有效赴澳旅游签注。在内地边检机关扣减无误的前提下，下列会导致该旅客所持电子往来港澳通行证签注计数器JS0、JS1、JS2、JS3分别为2、0、1、0的情形是。C.该旅客持用该本证件从内地出境后过境香港,实际未进入香港.前往澳门，在澳门逗留6日后返回内地。"
    
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
    logger.info(f"✓ 检索器创建成功")
    
    # 4. 构建免签知识库（如果启用）
    if Settings.ENABLE_VISA_FREE_FEATURE:
        logger.info("\n[步骤4] 构建免签知识库...")
        visa_free_index, visa_free_nodes = knowledge_service.build_or_load_visa_free_index()
        
        if visa_free_index and visa_free_nodes:
            logger.info(f"✓ 免签知识库: {len(visa_free_nodes)} 个节点")
            
            visa_free_retriever = knowledge_service.create_visa_free_retriever()
            logger.info(f"✓ 免签检索器创建成功")
        else:
            logger.warning("免签知识库构建失败")
    
    # 5. 初始化意图分类器（如果启用）
    intent_classifier = None
    if Settings.ENABLE_VISA_FREE_FEATURE and Settings.ENABLE_INTENT_CLASSIFIER:
        logger.info("\n[步骤5] 初始化意图分类器...")
        intent_classifier = IntentClassifier(
            llm_service=llm_service,
            enabled=True
        )
        logger.info(f"✓ 意图分类器初始化成功")
    
    # ========== 关键测试：对比有无意图分类的影响 ==========
    
    # 测试 A：不调用意图分类器（模拟测试脚本）
    logger.info("\n" + "=" * 80)
    logger.info("【测试 A】不调用意图分类器")
    logger.info("=" * 80)
    
    logger.info("\n[A1] 执行检索...")
    retrieved_nodes_a = retriever.retrieve(test_question)
    logger.info(f"✓ 检索到 {len(retrieved_nodes_a)} 个节点")
    
    logger.info("\n[A2] 执行重排序...")
    reranker_input_a = retrieved_nodes_a[:Settings.RERANKER_INPUT_TOP_N]
    query_bundle_a = QueryBundle(test_question)
    
    logger.info(f"🔍 [DEBUG] Reranker 对象ID: {id(reranker)}")
    logger.info(f"🔍 [DEBUG] QueryBundle: {query_bundle_a.query_str[:100]}...")
    
    reranked_nodes_a = reranker.postprocess_nodes(
        reranker_input_a,
        query_bundle=query_bundle_a
    )
    
    logger.info(f"✓ 重排序完成，得到 {len(reranked_nodes_a)} 个节点")
    
    if reranked_nodes_a:
        scores_a = [node.score for node in reranked_nodes_a[:5]]
        logger.info(f"\n重排序Top5得分: {', '.join([f'{s:.4f}' for s in scores_a])}")
        logger.info(f"最高分: {max(scores_a):.4f}")
    
    # 测试 B：调用意图分类器后再检索（模拟实际应用）
    if intent_classifier:
        logger.info("\n" + "=" * 80)
        logger.info("【测试 B】调用意图分类器后再检索")
        logger.info("=" * 80)
        
        logger.info("\n[B1] 调用意图分类器...")
        logger.info(f"🔍 [DEBUG] 意图分类器对象ID: {id(intent_classifier)}")
        logger.info(f"🔍 [DEBUG] LLM 服务对象ID: {id(llm_service)}")
        
        is_visa_related = intent_classifier.is_visa_related(test_question)
        logger.info(f"✓ 意图分类结果: {'免签相关' if is_visa_related else '非免签'}")
        
        logger.info("\n[B2] 执行检索...")
        retrieved_nodes_b = retriever.retrieve(test_question)
        logger.info(f"✓ 检索到 {len(retrieved_nodes_b)} 个节点")
        
        # 检查检索结果是否变化
        if retrieved_nodes_a and retrieved_nodes_b:
            content_a = retrieved_nodes_a[0].node.get_content()[:100]
            content_b = retrieved_nodes_b[0].node.get_content()[:100]
            
            logger.info(f"\n🔍 [检查] 第一个检索节点内容:")
            logger.info(f"  测试A: {content_a}...")
            logger.info(f"  测试B: {content_b}...")
            
            if content_a != content_b:
                logger.error("❌ 检索结果发生了变化！")
            else:
                logger.info("✓ 检索结果一致")
        
        logger.info("\n[B3] 执行重排序...")
        reranker_input_b = retrieved_nodes_b[:Settings.RERANKER_INPUT_TOP_N]
        query_bundle_b = QueryBundle(test_question)
        
        logger.info(f"🔍 [DEBUG] Reranker 对象ID: {id(reranker)}")
        logger.info(f"🔍 [DEBUG] QueryBundle: {query_bundle_b.query_str[:100]}...")
        logger.info(f"🔍 [DEBUG] 输入节点数: {len(reranker_input_b)}")
        
        # 对比 query_bundle
        if query_bundle_a.query_str != query_bundle_b.query_str:
            logger.error(f"❌ QueryBundle 不一致！")
            logger.error(f"  长度A: {len(query_bundle_a.query_str)}")
            logger.error(f"  长度B: {len(query_bundle_b.query_str)}")
        
        reranked_nodes_b = reranker.postprocess_nodes(
            reranker_input_b,
            query_bundle=query_bundle_b
        )
        
        logger.info(f"✓ 重排序完成，得到 {len(reranked_nodes_b)} 个节点")
        
        if reranked_nodes_b:
            scores_b = [node.score for node in reranked_nodes_b[:5]]
            logger.info(f"\n重排序Top5得分: {', '.join([f'{s:.4f}' for s in scores_b])}")
            logger.info(f"最高分: {max(scores_b):.4f}")
        
        # 对比分析
        logger.info("\n" + "=" * 80)
        logger.info("对比分析")
        logger.info("=" * 80)
        
        if reranked_nodes_a and reranked_nodes_b:
            max_score_a = max(scores_a)
            max_score_b = max(scores_b)
            
            logger.info(f"\n【重排序最高分】")
            logger.info(f"  测试A（无意图分类）: {max_score_a:.4f}")
            logger.info(f"  测试B（有意图分类）: {max_score_b:.4f}")
            logger.info(f"  差异: {max_score_b - max_score_a:.4f}")
            
            if max_score_b < max_score_a * 0.5:
                logger.error("\n❌ 关键发现：调用意图分类器后，重排序得分大幅下降！")
                logger.error("   这说明意图分类器的调用影响了后续的重排序！")
            else:
                logger.info("\n✓ 重排序得分正常，意图分类器没有影响")
    
    # 测试 C：重新创建 Reranker 后再试（排除 Reranker 状态污染）
    if intent_classifier:
        logger.info("\n" + "=" * 80)
        logger.info("【测试 C】重新创建 Reranker 后再试")
        logger.info("=" * 80)
        
        logger.info("\n[C1] 调用意图分类器...")
        is_visa_related = intent_classifier.is_visa_related(test_question)
        logger.info(f"✓ 意图分类结果: {'免签相关' if is_visa_related else '非免签'}")
        
        logger.info("\n[C2] 重新创建 Reranker...")
        from llama_index.core.postprocessor import SentenceTransformerRerank
        new_reranker = SentenceTransformerRerank(
            model=Settings.RERANKER_MODEL_PATH,
            top_n=Settings.RERANK_TOP_N,
            device=Settings.DEVICE
        )
        logger.info(f"✓ 新 Reranker 对象ID: {id(new_reranker)}")
        
        logger.info("\n[C3] 执行检索...")
        retrieved_nodes_c = retriever.retrieve(test_question)
        logger.info(f"✓ 检索到 {len(retrieved_nodes_c)} 个节点")
        
        logger.info("\n[C4] 执行重排序（使用新 Reranker）...")
        reranker_input_c = retrieved_nodes_c[:Settings.RERANKER_INPUT_TOP_N]
        query_bundle_c = QueryBundle(test_question)
        
        reranked_nodes_c = new_reranker.postprocess_nodes(
            reranker_input_c,
            query_bundle=query_bundle_c
        )
        
        logger.info(f"✓ 重排序完成，得到 {len(reranked_nodes_c)} 个节点")
        
        if reranked_nodes_c:
            scores_c = [node.score for node in reranked_nodes_c[:5]]
            logger.info(f"\n重排序Top5得分: {', '.join([f'{s:.4f}' for s in scores_c])}")
            logger.info(f"最高分: {max(scores_c):.4f}")
            
            logger.info(f"\n【对比】")
            logger.info(f"  旧 Reranker: {max(scores_b):.4f}")
            logger.info(f"  新 Reranker: {max(scores_c):.4f}")
    
    logger.info("\n" + "=" * 80)
    logger.info("诊断完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    logger.info("\n" + "🔍" * 40)
    logger.info(f"免签功能状态: {'✅ 开启' if Settings.ENABLE_VISA_FREE_FEATURE else '❌ 关闭'}")
    logger.info(f"意图分类器状态: {'✅ 开启' if Settings.ENABLE_INTENT_CLASSIFIER else '❌ 关闭'}")
    logger.info("🔍" * 40 + "\n")
    
    test_with_intent_classifier()
    
    logger.info("\n\n" + "📋" * 40)
    logger.info("说明")
    logger.info("📋" * 40)
    logger.info("\n此脚本会：")
    logger.info("1. 测试A：不调用意图分类器，直接检索和重排序")
    logger.info("2. 测试B：调用意图分类器后，再检索和重排序")
    logger.info("3. 测试C：调用意图分类器后，使用新 Reranker 重排序")
    logger.info("4. 对比三次结果，找出差异")
    logger.info("\n如果测试B得分大幅下降，说明意图分类器影响了后续操作！")
