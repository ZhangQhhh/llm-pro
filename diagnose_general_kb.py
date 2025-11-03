#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断脚本：对比 ENABLE_VISA_FREE_FEATURE 开启前后通用知识库的状态
关键发现：true 时重排序得分 0.05，false 时得分 0.98
"""
import os
import sys
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Settings
from utils.logger import logger
from services import LLMService, EmbeddingService, KnowledgeService
from llama_index.core import QueryBundle


def compute_content_hash(text: str) -> str:
    """计算文本内容的哈希值"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def diagnose_general_kb():
    """
    诊断通用知识库的状态
    """
    logger.info("=" * 80)
    logger.info("诊断通用知识库状态")
    logger.info("=" * 80)
    logger.info(f"\n免签功能状态: {Settings.ENABLE_VISA_FREE_FEATURE}")
    
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
    logger.info(f"Qdrant 客户端ID: {id(knowledge_service.qdrant_client)}")
    
    index, all_nodes = knowledge_service.build_or_load_index()
    
    if not (index and all_nodes):
        logger.error("通用知识库构建失败")
        return
    
    logger.info(f"✓ 通用知识库: {len(all_nodes)} 个节点")
    
    # 3. 分析通用知识库的内容
    logger.info("\n[步骤3] 分析通用知识库内容...")
    
    content_hashes = []
    file_names = set()
    total_chars = 0
    
    for node in all_nodes:
        content = node.get_content()
        content_hash = compute_content_hash(content)
        content_hashes.append(content_hash)
        
        file_name = node.metadata.get('file_name', '未知')
        file_names.add(file_name)
        
        total_chars += len(content)
    
    # 计算整体哈希（用于对比）
    overall_hash = hashlib.md5(''.join(sorted(content_hashes)).encode('utf-8')).hexdigest()
    
    logger.info(f"\n通用知识库统计:")
    logger.info(f"  - 节点数量: {len(all_nodes)}")
    logger.info(f"  - 文件数量: {len(file_names)}")
    logger.info(f"  - 总字符数: {total_chars}")
    logger.info(f"  - 内容哈希: {overall_hash}")
    
    logger.info(f"\n文件列表 (前20个):")
    for i, file_name in enumerate(sorted(file_names)[:20], 1):
        logger.info(f"  {i}. {file_name}")
    
    # 4. 创建通用检索器
    logger.info("\n[步骤4] 创建通用检索器...")
    retriever = knowledge_service.create_retriever()
    logger.info(f"✓ 检索器创建成功，对象ID: {id(retriever)}")
    
    # 5. 执行测试检索（构建免签库之前）
    test_question = "内地居民办理了两次有效赴港旅游签注和一次有效赴澳旅游签注。在内地边检机关扣减无误的前提下，下列会导致该旅客所持电子往来港澳通行证签注计数器JS0、JS1、JS2、JS3分别为2、0、1、0的情形是。C.该旅客持用该本证件从内地出境后过境香港,实际未进入香港.前往澳门，在澳门逗留6日后返回内地。"
    
    logger.info("\n[步骤5] 测试检索（构建免签库之前）...")
    retrieved_nodes_before = retriever.retrieve(test_question)
    logger.info(f"✓ 检索到 {len(retrieved_nodes_before)} 个节点")
    
    if retrieved_nodes_before:
        logger.info(f"\n检索结果Top5:")
        for i, node in enumerate(retrieved_nodes_before[:5], 1):
            logger.info(f"\n  {i}. 得分: {node.score:.4f}")
            logger.info(f"     文件: {node.node.metadata.get('file_name', '未知')}")
            logger.info(f"     内容: {node.node.get_content()[:100]}...")
    
    # 6. 执行重排序（构建免签库之前）
    logger.info("\n[步骤6] 执行重排序（构建免签库之前）...")
    reranker_input = retrieved_nodes_before[:Settings.RERANKER_INPUT_TOP_N]
    query_bundle = QueryBundle(test_question)
    
    reranked_nodes_before = reranker.postprocess_nodes(
        reranker_input,
        query_bundle=query_bundle
    )
    
    logger.info(f"✓ 重排序完成，得到 {len(reranked_nodes_before)} 个节点")
    
    if reranked_nodes_before:
        rerank_scores_before = [node.score for node in reranked_nodes_before[:5]]
        logger.info(f"\n重排序Top5得分: {', '.join([f'{s:.4f}' for s in rerank_scores_before])}")
        logger.info(f"最高分: {max(rerank_scores_before):.4f}")
    
    # 7. 如果启用免签功能，构建免签库并再次测试
    if Settings.ENABLE_VISA_FREE_FEATURE:
        logger.info("\n" + "=" * 80)
        logger.info("[关键] 现在构建免签知识库...")
        logger.info("=" * 80)
        
        logger.info(f"\nQdrant 客户端ID (构建前): {id(knowledge_service.qdrant_client)}")
        
        visa_free_index, visa_free_nodes = knowledge_service.build_or_load_visa_free_index()
        
        if visa_free_index and visa_free_nodes:
            logger.info(f"✓ 免签知识库: {len(visa_free_nodes)} 个节点")
            logger.info(f"\nQdrant 客户端ID (构建后): {id(knowledge_service.qdrant_client)}")
            
            # 8. 再次检查通用知识库
            logger.info("\n[步骤8] 再次检查通用知识库...")
            logger.info(f"通用索引对象ID: {id(index)}")
            logger.info(f"通用节点数量: {len(all_nodes)}")
            
            # 9. 再次执行测试检索
            logger.info("\n[步骤9] 测试检索（构建免签库之后）...")
            retrieved_nodes_after = retriever.retrieve(test_question)
            logger.info(f"✓ 检索到 {len(retrieved_nodes_after)} 个节点")
            
            if retrieved_nodes_after:
                logger.info(f"\n检索结果Top5:")
                for i, node in enumerate(retrieved_nodes_after[:5], 1):
                    logger.info(f"\n  {i}. 得分: {node.score:.4f}")
                    logger.info(f"     文件: {node.node.metadata.get('file_name', '未知')}")
                    logger.info(f"     内容: {node.node.get_content()[:100]}...")
            
            # 10. 再次执行重排序
            logger.info("\n[步骤10] 执行重排序（构建免签库之后）...")
            reranker_input = retrieved_nodes_after[:Settings.RERANKER_INPUT_TOP_N]
            
            reranked_nodes_after = reranker.postprocess_nodes(
                reranker_input,
                query_bundle=query_bundle
            )
            
            logger.info(f"✓ 重排序完成，得到 {len(reranked_nodes_after)} 个节点")
            
            if reranked_nodes_after:
                rerank_scores_after = [node.score for node in reranked_nodes_after[:5]]
                logger.info(f"\n重排序Top5得分: {', '.join([f'{s:.4f}' for s in rerank_scores_after])}")
                logger.info(f"最高分: {max(rerank_scores_after):.4f}")
            
            # 11. 对比分析
            logger.info("\n" + "=" * 80)
            logger.info("对比分析")
            logger.info("=" * 80)
            
            logger.info(f"\n【检索节点数量】")
            logger.info(f"  构建前: {len(retrieved_nodes_before)}")
            logger.info(f"  构建后: {len(retrieved_nodes_after)}")
            logger.info(f"  差异: {len(retrieved_nodes_after) - len(retrieved_nodes_before)}")
            
            if reranked_nodes_before and reranked_nodes_after:
                logger.info(f"\n【重排序最高分】")
                logger.info(f"  构建前: {max(rerank_scores_before):.4f}")
                logger.info(f"  构建后: {max(rerank_scores_after):.4f}")
                logger.info(f"  差异: {max(rerank_scores_after) - max(rerank_scores_before):.4f}")
                
                if max(rerank_scores_after) < max(rerank_scores_before) * 0.5:
                    logger.error("\n❌ 关键发现：构建免签库后，重排序得分大幅下降！")
                    logger.error("   这证实了问题的存在！")
                else:
                    logger.info("\n✓ 重排序得分正常")
            
            # 12. 检查节点内容是否变化
            logger.info(f"\n【第一个检索节点对比】")
            if retrieved_nodes_before and retrieved_nodes_after:
                content_before = retrieved_nodes_before[0].node.get_content()[:200]
                content_after = retrieved_nodes_after[0].node.get_content()[:200]
                
                logger.info(f"  构建前: {content_before}...")
                logger.info(f"  构建后: {content_after}...")
                
                if content_before != content_after:
                    logger.error("\n❌ 关键发现：检索到的节点内容发生了变化！")
                else:
                    logger.info("\n✓ 节点内容一致")
    
    logger.info("\n" + "=" * 80)
    logger.info("诊断完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    logger.info("\n" + "🔍" * 40)
    logger.info(f"免签功能状态: {'✅ 开启' if Settings.ENABLE_VISA_FREE_FEATURE else '❌ 关闭'}")
    logger.info("🔍" * 40 + "\n")
    
    diagnose_general_kb()
    
    logger.info("\n\n" + "📋" * 40)
    logger.info("说明")
    logger.info("📋" * 40)
    logger.info("\n此脚本会：")
    logger.info("1. 构建通用知识库并执行检索和重排序")
    logger.info("2. 如果启用免签功能，再构建免签库")
    logger.info("3. 再次执行检索和重排序")
    logger.info("4. 对比两次结果，找出差异")
    logger.info("\n如果构建免签库后得分大幅下降，说明问题得到确认！")
