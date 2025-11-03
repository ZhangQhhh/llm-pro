#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试免签功能对检索得分的影响
用于定位 ENABLE_VISA_FREE_FEATURE=true 时得分降低的问题
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Settings
from utils.logger import logger


def check_config():
    """检查配置是否正常"""
    logger.info("=" * 60)
    logger.info("配置检查")
    logger.info("=" * 60)
    
    logger.info(f"ENABLE_VISA_FREE_FEATURE: {Settings.ENABLE_VISA_FREE_FEATURE}")
    logger.info(f"ENABLE_INTENT_CLASSIFIER: {Settings.ENABLE_INTENT_CLASSIFIER}")
    logger.info(f"RETRIEVAL_TOP_K: {Settings.RETRIEVAL_TOP_K}")
    logger.info(f"RETRIEVAL_TOP_K_BM25: {Settings.RETRIEVAL_TOP_K_BM25}")
    logger.info(f"RERANKER_INPUT_TOP_N: {Settings.RERANKER_INPUT_TOP_N}")
    logger.info(f"RERANK_TOP_N: {Settings.RERANK_TOP_N}")
    logger.info(f"RERANK_SCORE_THRESHOLD: {Settings.RERANK_SCORE_THRESHOLD}")
    logger.info(f"VISA_FREE_RETRIEVAL_COUNT: {Settings.VISA_FREE_RETRIEVAL_COUNT}")
    logger.info(f"GENERAL_RETRIEVAL_COUNT: {Settings.GENERAL_RETRIEVAL_COUNT}")
    
    logger.info("=" * 60)


def check_retriever_initialization():
    """检查检索器初始化过程"""
    from services import KnowledgeService, LLMService, EmbeddingService
    
    logger.info("=" * 60)
    logger.info("初始化检查")
    logger.info("=" * 60)
    
    # 1. 初始化 Embedding
    logger.info("\n[步骤1] 初始化 Embedding 服务...")
    embedding_service = EmbeddingService()
    embed_model, reranker = embedding_service.initialize()
    logger.info(f"✓ Embedding 模型: {type(embed_model).__name__}")
    logger.info(f"✓ Reranker 模型: {type(reranker).__name__}")
    
    # 2. 初始化 LLM
    logger.info("\n[步骤2] 初始化 LLM 服务...")
    llm_service = LLMService()
    llm_clients = llm_service.initialize()
    default_llm = llm_service.get_client(Settings.DEFAULT_LLM_ID)
    logger.info(f"✓ 默认 LLM: {Settings.DEFAULT_LLM_ID}")
    
    # 3. 初始化知识库服务
    logger.info("\n[步骤3] 初始化知识库服务...")
    knowledge_service = KnowledgeService(default_llm)
    
    # 4. 构建通用知识库
    logger.info("\n[步骤4] 构建通用知识库...")
    logger.info(f"知识库目录: {Settings.KNOWLEDGE_BASE_DIR}")
    index, all_nodes = knowledge_service.build_or_load_index()
    
    if index and all_nodes:
        logger.info(f"✓ 通用知识库索引创建成功")
        logger.info(f"  - 节点数量: {len(all_nodes)}")
        logger.info(f"  - 索引类型: {type(index).__name__}")
    else:
        logger.error("✗ 通用知识库索引创建失败")
        return False
    
    # 5. 创建通用检索器
    logger.info("\n[步骤5] 创建通用检索器...")
    retriever = knowledge_service.create_retriever()
    if retriever:
        logger.info(f"✓ 通用检索器创建成功: {type(retriever).__name__}")
    else:
        logger.error("✗ 通用检索器创建失败")
        return False
    
    # 6. 如果启用免签功能，构建免签知识库
    if Settings.ENABLE_VISA_FREE_FEATURE:
        logger.info("\n[步骤6] 构建免签知识库...")
        logger.info(f"免签知识库目录: {Settings.VISA_FREE_KB_DIR}")
        
        visa_free_index, visa_free_nodes = knowledge_service.build_or_load_visa_free_index()
        
        if visa_free_index and visa_free_nodes:
            logger.info(f"✓ 免签知识库索引创建成功")
            logger.info(f"  - 节点数量: {len(visa_free_nodes)}")
            logger.info(f"  - 索引类型: {type(visa_free_index).__name__}")
            
            # 🔥 关键修复：设置 knowledge_service 的属性
            knowledge_service.visa_free_index = visa_free_index
            knowledge_service.visa_free_nodes = visa_free_nodes
            logger.info("✓ 已将免签索引和节点设置到 knowledge_service")
            
            # 创建免签检索器
            logger.info("\n[步骤7] 创建免签检索器...")
            visa_free_retriever = knowledge_service.create_visa_free_retriever()
            if visa_free_retriever:
                logger.info(f"✓ 免签检索器创建成功: {type(visa_free_retriever).__name__}")
            else:
                logger.error("✗ 免签检索器创建失败")
        else:
            logger.warning("⚠ 免签知识库索引创建失败或为空")
    
    # 7. 检查通用检索器是否仍然正常
    logger.info("\n[步骤8] 验证通用检索器状态...")
    logger.info(f"通用检索器对象: {retriever}")
    logger.info(f"通用检索器类型: {type(retriever).__name__}")
    
    # 尝试执行一次检索
    from llama_index.core import QueryBundle
    test_query = "测试查询"
    logger.info(f"\n[步骤9] 执行测试检索: '{test_query}'")
    
    try:
        test_results = retriever.retrieve(QueryBundle(test_query))
        logger.info(f"✓ 检索成功，返回 {len(test_results)} 个结果")
        
        if test_results:
            logger.info(f"  - Top1 得分: {test_results[0].score:.4f}")
            logger.info(f"  - Top1 内容预览: {test_results[0].node.get_content()[:50]}...")
    except Exception as e:
        logger.error(f"✗ 检索失败: {e}", exc_info=True)
        return False
    
    logger.info("\n" + "=" * 60)
    logger.info("初始化检查完成")
    logger.info("=" * 60)
    
    return True


if __name__ == "__main__":
    logger.info("开始测试免签功能对检索的影响...")
    
    # 1. 检查配置
    check_config()
    
    # 2. 检查初始化过程
    success = check_retriever_initialization()
    
    if success:
        logger.info("\n✓ 所有检查通过，未发现明显问题")
        logger.info("\n建议：")
        logger.info("1. 用相同问题分别测试 ENABLE_VISA_FREE_FEATURE=true/false")
        logger.info("2. 对比两种情况下的检索得分")
        logger.info("3. 检查是否是 Qdrant 向量数据库的问题")
    else:
        logger.error("\n✗ 检查过程中发现问题，请查看上面的日志")
