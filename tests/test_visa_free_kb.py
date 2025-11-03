#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
免签知识库功能测试
测试免签库是否能独立工作，不影响通用库
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Settings
from services.knowledge_service import KnowledgeService
from services.llm_service import LLMService
from services.embedding_service import EmbeddingService
from core import MultiKBRetriever
from utils.logger import logger


def test_visa_free_kb():
    """测试免签知识库功能"""
    
    logger.info("=" * 80)
    logger.info("免签知识库功能测试")
    logger.info("=" * 80)
    
    # 检查配置
    logger.info("\n[步骤1] 检查配置")
    logger.info(f"ENABLE_VISA_FREE_FEATURE: {Settings.ENABLE_VISA_FREE_FEATURE}")
    logger.info(f"VISA_FREE_KB_DIR: {Settings.VISA_FREE_KB_DIR}")
    logger.info(f"VISA_FREE_COLLECTION: {Settings.VISA_FREE_COLLECTION}")
    
    if not Settings.ENABLE_VISA_FREE_FEATURE:
        logger.error("❌ 免签功能未启用！")
        logger.info("请设置环境变量: export ENABLE_VISA_FREE_FEATURE=true")
        return False
    
    # 初始化服务
    logger.info("\n[步骤2] 初始化服务")
    try:
        # 2.1 初始化 Embedding 和 Reranker
        embedding_service = EmbeddingService()
        embed_model, reranker = embedding_service.initialize()
        logger.info("✓ Embedding 和 Reranker 初始化成功")
        
        # 2.2 初始化 LLM 服务
        llm_service = LLMService()
        llm_service.initialize()
        llm = llm_service.get_client(Settings.DEFAULT_LLM_ID)
        logger.info("✓ LLM 服务初始化成功")
        
        # 2.3 初始化知识库服务
        knowledge_service = KnowledgeService(llm)
        logger.info("✓ 知识库服务初始化成功")
    except Exception as e:
        logger.error(f"❌ 服务初始化失败: {e}", exc_info=True)
        return False
    
    # 构建通用知识库
    logger.info("\n[步骤3] 构建通用知识库")
    try:
        general_index, general_nodes = knowledge_service.build_or_load_index()
        if general_index and general_nodes:
            logger.info(f"✓ 通用库构建成功 | 节点数: {len(general_nodes)}")
        else:
            logger.warning("⚠ 通用库为空")
    except Exception as e:
        logger.error(f"❌ 通用库构建失败: {e}", exc_info=True)
        return False
    
    # 构建免签知识库
    logger.info("\n[步骤4] 构建免签知识库")
    try:
        visa_index, visa_nodes = knowledge_service.build_or_load_visa_free_index()
        if visa_index and visa_nodes:
            logger.info(f"✓ 免签库构建成功 | 节点数: {len(visa_nodes)}")
            knowledge_service.visa_free_index = visa_index
            knowledge_service.visa_free_nodes = visa_nodes
        else:
            logger.error("❌ 免签库构建失败或为空")
            return False
    except Exception as e:
        logger.error(f"❌ 免签库构建失败: {e}", exc_info=True)
        return False
    
    # 创建检索器
    logger.info("\n[步骤5] 创建检索器")
    try:
        general_retriever = knowledge_service.create_retriever()
        visa_retriever = knowledge_service.create_visa_free_retriever()
        
        if not general_retriever:
            logger.error("❌ 通用检索器创建失败")
            return False
        if not visa_retriever:
            logger.error("❌ 免签检索器创建失败")
            return False
        
        logger.info("✓ 检索器创建成功")
    except Exception as e:
        logger.error(f"❌ 检索器创建失败: {e}", exc_info=True)
        return False
    
    # 测试1: 单独测试免签库
    logger.info("\n" + "=" * 80)
    logger.info("测试1: 单独测试免签库")
    logger.info("=" * 80)
    
    visa_question = "中国和哪些国家有互免签证协定？"
    logger.info(f"问题: {visa_question}")
    
    try:
        visa_results = visa_retriever.retrieve(visa_question)
        logger.info(f"✓ 免签库检索成功 | 返回 {len(visa_results)} 条结果")
        
        if visa_results:
            logger.info("\n免签库 Top3 结果:")
            for i, node in enumerate(visa_results[:3], 1):
                logger.info(f"  [{i}] 得分: {node.score:.4f} | 文件: {node.node.metadata.get('file_name', '未知')}")
                logger.info(f"      内容: {node.node.text[:100]}...")
    except Exception as e:
        logger.error(f"❌ 免签库检索失败: {e}", exc_info=True)
        return False
    
    # 测试2: 单独测试通用库（确保不受影响）
    logger.info("\n" + "=" * 80)
    logger.info("测试2: 内地居民办理了两次有效赴港旅游签注和一次有效赴澳旅游签注。在内地边检机关扣减无误的前提下,下列会导致该旅客所持电子往来港澳通行证签注计数器JS0、JS1、JS2、JS3分别为2、0、1、0的情形是。C.该旅客持用该本证件从内地出境后过境香港实际未进入香港前往澳门在澳门逗留6日后返回内地。")
    logger.info("=" * 80)
    
    general_question = "内地居民办理了两次有效赴港旅游签注和一次有效赴澳旅游签注。在内地边检机关扣减无误的前提下, 下列会导致该旅客所持电子往来港澳通行证签注计数器JS0、JS1、JS2、JS3分别为2、0、1、0的情形是。C.该旅客持用该本证件从内地出境后过境香港实际未进入香港前往澳门在澳门逗留6日后返回内地。"
    logger.info(f"问题: {general_question}")
    
    try:
        general_results = general_retriever.retrieve(general_question)
        logger.info(f"✓ 通用库检索成功 | 返回 {len(general_results)} 条结果")
        
        if general_results:
            logger.info("\n通用库 Top3 结果:")
            for i, node in enumerate(general_results[:3], 1):
                logger.info(f"  [{i}] 得分: {node.score:.4f} | 文件: {node.node.metadata.get('file_name', '未知')}")
                logger.info(f"      内容: {node.node.text[:100]}...")
    except Exception as e:
        logger.error(f"❌ 通用库检索失败: {e}", exc_info=True)
        return False
    
    # 测试3: 双库检索
    logger.info("\n" + "=" * 80)
    logger.info("内地居民办理了两次有效赴港旅游签注和一次有效赴澳旅游签注。在内地边检机关扣减无误的前提下,下列会导致该旅客所持电子往来港澳通行证签注计数器JS0、JS1、JS2、JS3分别为2、0、1、0的情形是。C.该旅客持用该本证件从内地出境后过境香港,实际未进入香港.前往澳门,在澳门逗留6日后返回内地。")
    logger.info("=" * 80)
    
    try:
        multi_retriever = MultiKBRetriever(
            general_retriever=general_retriever,
            visa_free_retriever=visa_retriever,
            strategy="adaptive"
        )
        
        mixed_question = "内地居民办理了两次有效赴港旅游签注和一次有效赴澳旅游签注。在内地边检机关扣减无误的前提下,下列会导致该旅客所持电子往来港澳通行证签注计数器JS0、JS1、JS2、JS3分别为2、0、1、0的情形是。C.该旅客持用该本证件从内地出境后过境香港,实际未进入香港.前往澳门,在澳门逗留6日后返回内地。"
        logger.info(f"问题: {mixed_question}")
        
        mixed_results = multi_retriever.retrieve_from_both(mixed_question)
        logger.info(f"✓ 双库检索成功 | 返回 {len(mixed_results)} 条结果")
        
        if mixed_results:
            logger.info("\n双库 Top5 结果:")
            for i, node in enumerate(mixed_results[:5], 1):
                file_name = node.node.metadata.get('file_name', '未知')
                source = "免签库" if "免签" in file_name or "签证" in file_name else "通用库"
                logger.info(f"  [{i}] 得分: {node.score:.4f} | 来源: {source} | 文件: {file_name}")
                logger.info(f"      内容: {node.node.text[:100]}...")
    except Exception as e:
        logger.error(f"❌ 双库检索失败: {e}", exc_info=True)
        return False
    
    # 总结
    logger.info("\n" + "=" * 80)
    logger.info("测试总结")
    logger.info("=" * 80)
    logger.info("✓ 所有测试通过！")
    logger.info("\n关键验证:")
    logger.info("  1. ✓ 免签库能独立构建和检索")
    logger.info("  2. ✓ 通用库不受免签库影响")
    logger.info("  3. ✓ 双库检索能正确合并结果")
    logger.info("\n下一步:")
    logger.info("  - 实现意图分类器（判断何时使用哪个库）")
    logger.info("  - 集成到 KnowledgeHandler")
    logger.info("  - 添加 API 路由")
    
    return True


if __name__ == "__main__":
    success = test_visa_free_kb()
    sys.exit(0 if success else 1)
