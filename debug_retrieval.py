#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试检索流程的脚本
打印重排序之前的检索结果
"""
import sys
from llama_index.core import QueryBundle
from config import Settings
from services.knowledge_service import KnowledgeService
from services.embedding_service import EmbeddingService
from utils.logger import logger


def debug_retrieval(question: str):
    """
    调试检索流程
    
    Args:
        question: 用户问题
    """
    print("=" * 80)
    print("检索流程调试")
    print("=" * 80)
    print(f"\n用户问题: {question}")
    print("\n" + "=" * 80)
    
    # 1. 初始化服务
    print("\n[步骤1] 初始化 Embedding 和 Reranker...")
    embedding_service = EmbeddingService()
    embed_model, reranker = embedding_service.initialize()
    print(f"✓ Embedding 模型: {Settings.EMBED_MODEL_PATH}")
    print(f"✓ Reranker 模型: {Settings.RERANKER_MODEL_PATH}")
    
    # 2. 初始化知识库服务
    print("\n[步骤2] 初始化知识库服务...")
    knowledge_service = KnowledgeService(embed_model)
    
    # 3. 构建或加载索引
    print("\n[步骤3] 加载通用知识库索引...")
    index, all_nodes = knowledge_service.build_or_load_index()
    
    if index is None or all_nodes is None:
        print("✗ 索引加载失败！")
        return
    
    print(f"✓ 索引加载成功，共 {len(all_nodes)} 个节点")
    
    # 4. 创建检索器
    print("\n[步骤4] 创建混合检索器...")
    retriever = knowledge_service.create_retriever()
    
    if retriever is None:
        print("✗ 检索器创建失败！")
        return
    
    print(f"✓ 检索器创建成功")
    print(f"  - 向量检索数量: {Settings.RETRIEVAL_TOP_K}")
    print(f"  - BM25检索数量: {Settings.RETRIEVAL_TOP_K_BM25}")
    
    # 5. 执行初始检索
    print("\n[步骤5] 执行初始检索...")
    print(f"问题: {question}")
    print("-" * 80)
    
    retrieved_nodes = retriever.retrieve(question)
    
    print(f"\n✓ 初始检索完成，找到 {len(retrieved_nodes)} 个节点")
    
    # 6. 打印检索结果详情
    print("\n" + "=" * 80)
    print("初始检索结果详情（重排序之前）")
    print("=" * 80)
    
    if len(retrieved_nodes) == 0:
        print("\n✗ 警告: 没有检索到任何节点！")
        print("\n可能的原因:")
        print("1. 知识库为空")
        print("2. 问题与知识库内容完全不相关")
        print("3. Embedding 模型问题")
        return
    
    for i, node in enumerate(retrieved_nodes[:10], 1):  # 只显示前10个
        print(f"\n节点 #{i}")
        print("-" * 80)
        print(f"文件名: {node.node.metadata.get('file_name', '未知')}")
        print(f"RRF融合分数: {node.score:.6f}")
        print(f"向量检索分数: {node.node.metadata.get('vector_score', 0.0):.6f}")
        print(f"BM25检索分数: {node.node.metadata.get('bm25_score', 0.0):.6f}")
        print(f"初始分数: {node.node.metadata.get('initial_score', 0.0):.6f}")
        
        # 打印文本内容（前200字符）
        content = node.node.get_content().strip()
        if len(content) > 200:
            content = content[:200] + "..."
        print(f"内容预览:\n{content}")
    
    if len(retrieved_nodes) > 10:
        print(f"\n... 还有 {len(retrieved_nodes) - 10} 个节点未显示")
    
    # 7. 执行重排序
    print("\n" + "=" * 80)
    print("重排序流程")
    print("=" * 80)
    
    reranker_input_top_n = Settings.RERANKER_INPUT_TOP_N
    reranker_input = retrieved_nodes[:reranker_input_top_n]
    
    print(f"\n选取前 {len(reranker_input)} 个节点送入重排序...")
    
    if reranker_input:
        reranked_nodes = reranker.postprocess_nodes(
            reranker_input,
            query_bundle=QueryBundle(question)
        )
    else:
        reranked_nodes = []
    
    print(f"✓ 重排序完成，得到 {len(reranked_nodes)} 个节点")
    
    # 8. 打印重排序结果
    print("\n" + "=" * 80)
    print("重排序结果详情")
    print("=" * 80)
    
    if len(reranked_nodes) == 0:
        print("\n✗ 警告: 重排序后没有节点！")
        return
    
    for i, node in enumerate(reranked_nodes[:10], 1):  # 只显示前10个
        print(f"\n节点 #{i}")
        print("-" * 80)
        print(f"文件名: {node.node.metadata.get('file_name', '未知')}")
        print(f"重排序分数: {node.score:.6f}")
        print(f"初始RRF分数: {node.node.metadata.get('initial_score', 0.0):.6f}")
        
        # 打印文本内容（前200字符）
        content = node.node.get_content().strip()
        if len(content) > 200:
            content = content[:200] + "..."
        print(f"内容预览:\n{content}")
    
    if len(reranked_nodes) > 10:
        print(f"\n... 还有 {len(reranked_nodes) - 10} 个节点未显示")
    
    # 9. 阈值过滤
    print("\n" + "=" * 80)
    print("阈值过滤")
    print("=" * 80)
    
    threshold = Settings.RERANK_SCORE_THRESHOLD
    final_nodes = [
        node for node in reranked_nodes
        if node.score >= threshold
    ]
    
    print(f"\n阈值: {threshold}")
    print(f"过滤前: {len(reranked_nodes)} 个节点")
    print(f"过滤后: {len(final_nodes)} 个节点")
    
    if len(final_nodes) == 0:
        print("\n✗ 警告: 阈值过滤后没有节点！")
        print(f"   所有节点的重排序分数都低于阈值 {threshold}")
        print("\n建议:")
        print(f"1. 降低阈值 RERANK_SCORE_THRESHOLD (当前: {threshold})")
        print("2. 检查问题是否与知识库内容相关")
        print("3. 检查 Reranker 模型是否正常工作")
    else:
        print("\n✓ 阈值过滤成功")
        print("\n最终节点列表:")
        for i, node in enumerate(final_nodes[:5], 1):
            print(f"  {i}. {node.node.metadata.get('file_name', '未知')} (分数: {node.score:.6f})")
    
    # 10. 总结
    print("\n" + "=" * 80)
    print("检索流程总结")
    print("=" * 80)
    print(f"用户问题: {question}")
    print(f"初始检索: {len(retrieved_nodes)} 个节点")
    print(f"送入重排序: {len(reranker_input)} 个节点")
    print(f"重排序后: {len(reranked_nodes)} 个节点")
    print(f"阈值过滤后: {len(final_nodes)} 个节点")
    print(f"最终返回: {min(len(final_nodes), Settings.RERANK_TOP_N)} 个节点")
    print("=" * 80)


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python debug_retrieval.py \"你的问题\"")
        print("\n示例:")
        print("  python debug_retrieval.py \"如何办理护照？\"")
        print("  python debug_retrieval.py \"中国公民去泰国需要签证吗？\"")
        return
    
    question = " ".join(sys.argv[1:])
    debug_retrieval(question)


if __name__ == "__main__":
    main()
