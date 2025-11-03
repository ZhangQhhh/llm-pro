#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断 Reranker 状态
检查 Reranker 是否在构建免签知识库后被修改
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Settings
from utils.logger import logger
from services import EmbeddingService, LLMService, KnowledgeService
from llama_index.core import QueryBundle


def diagnose_reranker():
    """诊断 Reranker 状态"""
    logger.info("=" * 80)
    logger.info("Reranker 状态诊断")
    logger.info("=" * 80)
    
    # 1. 初始化 Reranker
    logger.info("\n[步骤1] 初始化 Reranker...")
    embedding_service = EmbeddingService()
    embed_model, reranker = embedding_service.initialize()
    
    logger.info(f"✓ Reranker 类型: {type(reranker).__name__}")
    logger.info(f"✓ Reranker 对象ID: {id(reranker)}")
    logger.info(f"✓ Reranker top_n: {reranker.top_n}")
    logger.info(f"✓ Reranker 模型路径: {Settings.RERANKER_MODEL_PATH}")
    logger.info(f"✓ Reranker 设备: {Settings.DEVICE}")
    
    # 2. 初始化 LLM 和知识库服务
    logger.info("\n[步骤2] 初始化知识库服务...")
    llm_service = LLMService()
    llm_clients = llm_service.initialize()
    default_llm = llm_service.get_client(Settings.DEFAULT_LLM_ID)
    knowledge_service = KnowledgeService(default_llm)
    
    # 3. 构建通用知识库
    logger.info("\n[步骤3] 构建通用知识库...")
    index, all_nodes = knowledge_service.build_or_load_index()
    
    if not (index and all_nodes):
        logger.error("通用知识库构建失败")
        return
    
    logger.info(f"✓ 通用知识库节点数: {len(all_nodes)}")
    
    # 4. 创建通用检索器
    logger.info("\n[步骤4] 创建通用检索器...")
    retriever = knowledge_service.create_retriever()
    logger.info(f"✓ 通用检索器创建成功")
    
    # 5. 检查 Reranker 状态（构建通用知识库后）
    logger.info("\n[步骤5] 检查 Reranker 状态（构建通用知识库后）...")
    logger.info(f"Reranker 对象ID: {id(reranker)} (是否变化: {id(reranker) != id(embedding_service.reranker)})")
    logger.info(f"Reranker top_n: {reranker.top_n}")
    
    # 6. 执行一次测试检索和重排序
    test_question = "内地居民办理了两次有效赴港旅游签注和一次有效赴澳旅游签注。在内地边检机关扣减无误的前提下，下列会导致该旅客所持电子往来港澳通行证签注计数器JS0、JS1、JS2、JS3分别为2、0、1、0的情形是。C.该旅客持用该本证件从内地出境后过境香港,实际未进入香港.前往澳门，在澳门逗留6日后返回内地。"
    logger.info(f"\n[步骤6] 执行测试检索: '{test_question}'")
    
    retrieved_nodes = retriever.retrieve(test_question)
    logger.info(f"✓ 检索到 {len(retrieved_nodes)} 个节点")
    
    if retrieved_nodes:
        logger.info(f"初始检索Top3得分: {[f'{n.score:.4f}' for n in retrieved_nodes[:3]]}")
    
    # 重排序
    reranker_input = retrieved_nodes[:Settings.RERANKER_INPUT_TOP_N]
    logger.info(f"送入重排序: {len(reranker_input)} 个节点")
    
    reranked_nodes = reranker.postprocess_nodes(
        reranker_input,
        query_bundle=QueryBundle(test_question)
    )
    
    logger.info(f"✓ 重排序返回 {len(reranked_nodes)} 个节点")
    
    if reranked_nodes:
        logger.info(f"重排序后Top3得分: {[f'{n.score:.4f}' for n in reranked_nodes[:3]]}")
    
    # 7. 如果启用免签功能，构建免签知识库
    if Settings.ENABLE_VISA_FREE_FEATURE:
        logger.info("\n" + "=" * 80)
        logger.info("开始构建免签知识库")
        logger.info("=" * 80)
        
        logger.info("\n[步骤7] 构建免签知识库...")
        visa_free_index, visa_free_nodes = knowledge_service.build_or_load_visa_free_index()
        
        if visa_free_index and visa_free_nodes:
            knowledge_service.visa_free_index = visa_free_index
            knowledge_service.visa_free_nodes = visa_free_nodes
            logger.info(f"✓ 免签知识库节点数: {len(visa_free_nodes)}")
            
            # 8. 创建免签检索器
            logger.info("\n[步骤8] 创建免签检索器...")
            visa_free_retriever = knowledge_service.create_visa_free_retriever()
            logger.info(f"✓ 免签检索器创建成功")
            
            # 9. 再次检查 Reranker 状态（构建免签知识库后）
            logger.info("\n[步骤9] 检查 Reranker 状态（构建免签知识库后）...")
            logger.info(f"Reranker 对象ID: {id(reranker)} (是否变化: {id(reranker) != id(embedding_service.reranker)})")
            logger.info(f"Reranker top_n: {reranker.top_n}")
            
            # 10. 再次执行相同的测试检索和重排序
            logger.info(f"\n[步骤10] 再次执行测试检索: '{test_question}'")
            
            retrieved_nodes_2 = retriever.retrieve(test_question)
            logger.info(f"✓ 检索到 {len(retrieved_nodes_2)} 个节点")
            
            if retrieved_nodes_2:
                logger.info(f"初始检索Top3得分: {[f'{n.score:.4f}' for n in retrieved_nodes_2[:3]]}")
            
            # 重排序
            reranker_input_2 = retrieved_nodes_2[:Settings.RERANKER_INPUT_TOP_N]
            logger.info(f"送入重排序: {len(reranker_input_2)} 个节点")
            
            reranked_nodes_2 = reranker.postprocess_nodes(
                reranker_input_2,
                query_bundle=QueryBundle(test_question)
            )
            
            logger.info(f"✓ 重排序返回 {len(reranked_nodes_2)} 个节点")
            
            if reranked_nodes_2:
                logger.info(f"重排序后Top3得分: {[f'{n.score:.4f}' for n in reranked_nodes_2[:3]]}")
            
            # 11. 对比两次结果
            logger.info("\n" + "=" * 80)
            logger.info("对比分析")
            logger.info("=" * 80)
            
            logger.info(f"\n构建免签知识库前:")
            logger.info(f"  - 检索节点数: {len(retrieved_nodes)}")
            logger.info(f"  - 重排序返回数: {len(reranked_nodes)}")
            if reranked_nodes:
                logger.info(f"  - 最高分: {max(n.score for n in reranked_nodes):.4f}")
            
            logger.info(f"\n构建免签知识库后:")
            logger.info(f"  - 检索节点数: {len(retrieved_nodes_2)}")
            logger.info(f"  - 重排序返回数: {len(reranked_nodes_2)}")
            if reranked_nodes_2:
                logger.info(f"  - 最高分: {max(n.score for n in reranked_nodes_2):.4f}")
            
            if reranked_nodes and reranked_nodes_2:
                score_diff = max(n.score for n in reranked_nodes_2) - max(n.score for n in reranked_nodes)
                logger.info(f"\n得分差异: {score_diff:.4f}")
                
                if abs(score_diff) < 0.0001:
                    logger.info("✅ 得分一致，Reranker 未受影响")
                else:
                    logger.warning(f"⚠️ 得分变化: {score_diff:.4f}")
        else:
            logger.warning("免签知识库构建失败")
    else:
        logger.info("\n免签功能未启用，跳过免签知识库构建")
    
    logger.info("\n" + "=" * 80)
    logger.info("诊断完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    diagnose_reranker()
