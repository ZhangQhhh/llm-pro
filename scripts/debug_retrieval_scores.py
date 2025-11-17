#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检索分数调试工具
用于查看所有检索到的文档及其分数，帮助调试为什么某些文档没有被检索到
"""
import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from config import Settings
from llama_index.core import QueryBundle, load_index_from_storage, StorageContext
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from core.retriever import HybridRetriever
from utils import logger
import logging

# 设置日志级别为 INFO
logging.basicConfig(level=logging.INFO)


def _init_retriever():
    """初始化检索器和重排序器"""
    # 初始化 Qdrant 客户端
    qdrant_client = QdrantClient(
        host=Settings.QDRANT_HOST,
        port=Settings.QDRANT_PORT
    )
    
    # 加载向量存储
    vector_store = QdrantVectorStore(
        client=qdrant_client,
        collection_name=Settings.QDRANT_COLLECTION
    )
    
    # 加载索引
    storage_context = StorageContext.from_defaults(
        vector_store=vector_store,
        persist_dir=Settings.STORAGE_PATH
    )
    index = load_index_from_storage(storage_context)
    
    # 创建混合检索器
    retriever = HybridRetriever(
        index=index,
        vector_top_k=Settings.RETRIEVAL_TOP_K,
        bm25_top_k=Settings.RETRIEVAL_TOP_K_BM25,
        rrf_k=Settings.RRF_K,
        vector_weight=Settings.RRF_VECTOR_WEIGHT,
        bm25_weight=Settings.RRF_BM25_WEIGHT
    )
    
    # 创建重排序器
    reranker = SentenceTransformerRerank(
        model=Settings.RERANKER_MODEL_PATH,
        top_n=Settings.RERANK_TOP_N,
        device=Settings.DEVICE
    )
    
    return retriever, reranker


def debug_retrieval(question: str, top_k: int = 50, show_subquestions: bool = False):
    """
    调试检索过程，显示所有检索到的文档及其分数
    
    Args:
        question: 用户问题
        top_k: 显示前 N 个结果（默认50）
        show_subquestions: 是否显示子问题分解信息
    """
    print("=" * 80)
    print(f"🔍 检索调试工具")
    print(f"问题: {question}")
    print(f"显示前 {top_k} 个结果")
    if show_subquestions:
        print(f"子问题分解: 启用")
    print("=" * 80)
    
    # 初始化检索器
    retriever, reranker = _init_retriever()
    
    print("\n📊 第一步：向量检索 + BM25 检索（混合检索）")
    print("-" * 80)
    
    # 执行检索
    retrieved_nodes = retriever.retrieve(question)
    
    print(f"✓ 初始检索到 {len(retrieved_nodes)} 个节点")
    print("\n前 {} 个节点的详细信息：\n".format(min(top_k, len(retrieved_nodes))))
    
    # 显示初始检索结果
    for i, node in enumerate(retrieved_nodes[:top_k], 1):
        file_name = node.node.metadata.get('file_name', '未知')
        score = node.score
        
        # 提取检索元数据
        retrieval_sources = node.node.metadata.get('retrieval_sources', [])
        vector_score = node.node.metadata.get('vector_score', 0.0)
        bm25_score = node.node.metadata.get('bm25_score', 0.0)
        vector_rank = node.node.metadata.get('vector_rank', '-')
        bm25_rank = node.node.metadata.get('bm25_rank', '-')
        matched_keywords = node.node.metadata.get('bm25_matched_keywords', [])
        
        # 子问题分解元数据（如果有）
        sub_question = node.node.metadata.get('sub_question', None)
        
        # 获取内容预览
        content = node.node.get_content()
        content_preview = content[:100].replace('\n', ' ') + '...' if len(content) > 100 else content
        
        # 格式化输出
        sources_str = '+'.join(retrieval_sources) if retrieval_sources else '未知'
        
        print(f"[{i:2d}] {file_name}")
        print(f"     RRF融合分数: {score:.6f}")
        print(f"     检索来源: {sources_str}")
        
        if 'vector' in retrieval_sources:
            print(f"       - 向量分数: {vector_score:.6f} (排名 #{vector_rank})")
        if 'keyword' in retrieval_sources:
            print(f"       - BM25分数: {bm25_score:.6f} (排名 #{bm25_rank})")
            if matched_keywords:
                print(f"       - 匹配关键词: {', '.join(matched_keywords)}")
        
        # 显示子问题信息
        if show_subquestions and sub_question:
            print(f"     🔗 子问题: {sub_question}")
        
        print(f"     内容预览: {content_preview}")
        print()
    
    # 重排序
    print("\n📊 第二步：重排序（Reranker）")
    print("-" * 80)
    
    # 取前 N 个送入重排
    reranker_input_top_n = Settings.RERANKER_INPUT_TOP_N
    reranker_input = retrieved_nodes[:reranker_input_top_n]
    
    print(f"✓ 取前 {len(reranker_input)} 个节点送入重排序")
    
    if reranker_input:
        reranked_nodes = reranker.postprocess_nodes(
            reranker_input,
            query_bundle=QueryBundle(question)
        )
        
        print(f"✓ 重排序完成，得到 {len(reranked_nodes)} 个节点")
        print(f"\n前 {min(20, len(reranked_nodes))} 个重排序后的节点：\n")
        
        for i, node in enumerate(reranked_nodes[:20], 1):
            file_name = node.node.metadata.get('file_name', '未知')
            initial_score = node.node.metadata.get('initial_score', 0.0)
            rerank_score = node.score
            
            content = node.node.get_content()
            content_preview = content[:100].replace('\n', ' ') + '...' if len(content) > 100 else content
            
            print(f"[{i:2d}] {file_name}")
            print(f"     初始分数: {initial_score:.6f} → 重排分数: {rerank_score:.6f}")
            print(f"     内容预览: {content_preview}")
            print()
    
    # 阈值过滤
    print("\n📊 第三步：阈值过滤")
    print("-" * 80)
    
    threshold = Settings.RERANK_SCORE_THRESHOLD
    print(f"阈值设置: {threshold}")
    
    final_nodes = [
        node for node in reranked_nodes
        if node.score >= threshold
    ]
    
    print(f"✓ 经过阈值过滤后剩余 {len(final_nodes)} 个节点")
    
    if len(final_nodes) == 0 and len(reranked_nodes) > 0:
        max_score = max(node.score for node in reranked_nodes)
        print(f"\n⚠️ 警告：所有节点都被阈值过滤掉了！")
        print(f"   最高分数: {max_score:.6f}")
        print(f"   当前阈值: {threshold}")
        print(f"   建议：降低 RERANK_SCORE_THRESHOLD 配置")
    
    print("\n" + "=" * 80)
    print("🎯 调试总结")
    print("=" * 80)
    print(f"初始检索: {len(retrieved_nodes)} 个节点")
    print(f"重排序输入: {len(reranker_input)} 个节点")
    print(f"重排序输出: {len(reranked_nodes)} 个节点")
    print(f"阈值过滤后: {len(final_nodes)} 个节点")
    print("=" * 80)
    
    # 统计文件分布
    print("\n📁 文件分布统计")
    print("-" * 80)
    
    file_stats = {}
    for node in retrieved_nodes[:top_k]:
        file_name = node.node.metadata.get('file_name', '未知')
        file_stats[file_name] = file_stats.get(file_name, 0) + 1
    
    for file_name, count in sorted(file_stats.items(), key=lambda x: x[1], reverse=True):
        print(f"  {file_name}: {count} 个节点")
    
    # 子问题分解统计
    if show_subquestions:
        print("\n🔗 子问题分解统计")
        print("-" * 80)
        
        subq_stats = {}
        for node in retrieved_nodes[:top_k]:
            sub_question = node.node.metadata.get('sub_question', None)
            if sub_question:
                subq_stats[sub_question] = subq_stats.get(sub_question, 0) + 1
        
        if subq_stats:
            print(f"检测到 {len(subq_stats)} 个子问题：")
            for i, (sub_q, count) in enumerate(subq_stats.items(), 1):
                print(f"  子问题{i}: {sub_q}")
                print(f"    → 匹配节点数: {count}")
        else:
            print("  未检测到子问题分解（可能未启用或未触发）")
    
    print("\n" + "=" * 80)


def search_specific_file(question: str, target_file: str, top_k: int = 100):
    """
    搜索特定文件在检索结果中的位置和分数
    
    Args:
        question: 用户问题
        target_file: 目标文件名（如 "林允知识库.docx"）
        top_k: 搜索前 N 个结果
    """
    print("=" * 80)
    print(f"🎯 搜索特定文件")
    print(f"问题: {question}")
    print(f"目标文件: {target_file}")
    print("=" * 80)
    
    # 初始化检索器
    retriever, _ = _init_retriever()
    
    # 执行检索
    retrieved_nodes = retriever.retrieve(question)
    
    print(f"\n✓ 初始检索到 {len(retrieved_nodes)} 个节点")
    print(f"搜索前 {min(top_k, len(retrieved_nodes))} 个结果...\n")
    
    found_nodes = []
    
    for i, node in enumerate(retrieved_nodes[:top_k], 1):
        file_name = node.node.metadata.get('file_name', '未知')
        
        if target_file in file_name or file_name in target_file:
            score = node.score
            retrieval_sources = node.node.metadata.get('retrieval_sources', [])
            vector_score = node.node.metadata.get('vector_score', 0.0)
            bm25_score = node.node.metadata.get('bm25_score', 0.0)
            
            content = node.node.get_content()
            content_preview = content[:150].replace('\n', ' ') + '...' if len(content) > 150 else content
            
            found_nodes.append({
                'rank': i,
                'file_name': file_name,
                'score': score,
                'sources': retrieval_sources,
                'vector_score': vector_score,
                'bm25_score': bm25_score,
                'content_preview': content_preview
            })
    
    if found_nodes:
        print(f"✅ 找到 {len(found_nodes)} 个来自 '{target_file}' 的节点：\n")
        
        for node_info in found_nodes:
            print(f"排名 #{node_info['rank']}")
            print(f"  文件: {node_info['file_name']}")
            print(f"  RRF分数: {node_info['score']:.6f}")
            print(f"  检索来源: {'+'.join(node_info['sources'])}")
            print(f"  向量分数: {node_info['vector_score']:.6f}")
            print(f"  BM25分数: {node_info['bm25_score']:.6f}")
            print(f"  内容: {node_info['content_preview']}")
            print()
    else:
        print(f"❌ 在前 {min(top_k, len(retrieved_nodes))} 个结果中未找到 '{target_file}'")
        print(f"\n可能原因：")
        print(f"  1. 该文件与问题相关性太低")
        print(f"  2. 该文件不在知识库中")
        print(f"  3. 该文件在 {top_k} 名之后")
        print(f"\n建议：")
        print(f"  - 增加 top_k 参数（如 top_k=200）")
        print(f"  - 检查文件是否已加载到知识库")
        print(f"  - 调整问题描述，使用文件中的关键词")
    
    print("\n" + "=" * 80)


def search_text_fragment(question: str, text_fragment: str, top_k: int = 100):
    """
    搜索包含特定文本片段的节点
    
    Args:
        question: 用户问题
        text_fragment: 要搜索的文本片段
        top_k: 搜索前 N 个结果
    """
    print("=" * 80)
    print(f"🔍 搜索文本片段")
    print(f"问题: {question}")
    print(f"文本片段: {text_fragment[:50]}..." if len(text_fragment) > 50 else f"文本片段: {text_fragment}")
    print("=" * 80)
    
    # 初始化检索器
    retriever, _ = _init_retriever()
    
    # 执行检索
    retrieved_nodes = retriever.retrieve(question)
    
    print(f"\n✓ 初始检索到 {len(retrieved_nodes)} 个节点")
    print(f"搜索前 {min(top_k, len(retrieved_nodes))} 个结果中包含该文本的节点...\n")
    
    found_nodes = []
    
    for i, node in enumerate(retrieved_nodes[:top_k], 1):
        content = node.node.get_content()
        
        # 检查是否包含该文本片段
        if text_fragment in content:
            file_name = node.node.metadata.get('file_name', '未知')
            score = node.score
            retrieval_sources = node.node.metadata.get('retrieval_sources', [])
            vector_score = node.node.metadata.get('vector_score', 0.0)
            bm25_score = node.node.metadata.get('bm25_score', 0.0)
            vector_rank = node.node.metadata.get('vector_rank', '-')
            bm25_rank = node.node.metadata.get('bm25_rank', '-')
            matched_keywords = node.node.metadata.get('bm25_matched_keywords', [])
            
            # 找到文本片段的位置，显示上下文
            start_pos = content.find(text_fragment)
            context_start = max(0, start_pos - 50)
            context_end = min(len(content), start_pos + len(text_fragment) + 50)
            context = content[context_start:context_end]
            
            found_nodes.append({
                'rank': i,
                'file_name': file_name,
                'score': score,
                'sources': retrieval_sources,
                'vector_score': vector_score,
                'bm25_score': bm25_score,
                'vector_rank': vector_rank,
                'bm25_rank': bm25_rank,
                'matched_keywords': matched_keywords,
                'context': context,
                'full_content': content
            })
    
    if found_nodes:
        print(f"✅ 找到 {len(found_nodes)} 个包含该文本的节点：\n")
        
        for node_info in found_nodes:
            print(f"{'='*80}")
            print(f"排名 #{node_info['rank']}")
            print(f"文件: {node_info['file_name']}")
            print(f"RRF融合分数: {node_info['score']:.6f}")
            print(f"检索来源: {'+'.join(node_info['sources']) if node_info['sources'] else '未知'}")
            
            if 'vector' in node_info['sources']:
                print(f"  - 向量分数: {node_info['vector_score']:.6f} (排名 #{node_info['vector_rank']})")
            if 'keyword' in node_info['sources']:
                print(f"  - BM25分数: {node_info['bm25_score']:.6f} (排名 #{node_info['bm25_rank']})")
                if node_info['matched_keywords']:
                    print(f"  - 匹配关键词: {', '.join(node_info['matched_keywords'])}")
            
            print(f"\n上下文预览:")
            print(f"  ...{node_info['context']}...")
            
            print(f"\n完整内容 ({len(node_info['full_content'])} 字符):")
            print(f"  {node_info['full_content'][:300]}...")
            print()
    else:
        print(f"❌ 在前 {min(top_k, len(retrieved_nodes))} 个结果中未找到包含该文本的节点")
        print(f"\n可能原因：")
        print(f"  1. 该文本不在知识库中")
        print(f"  2. 该文本在 {top_k} 名之后")
        print(f"  3. 文本内容有细微差异（如空格、换行、标点）")
        print(f"\n建议：")
        print(f"  - 增加 --top-k 参数（如 --top-k 200）")
        print(f"  - 尝试搜索更短的关键文本片段")
        print(f"  - 使用 --file 参数指定文件名")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='检索分数调试工具')
    parser.add_argument('question', type=str, help='用户问题')
    parser.add_argument('--top-k', type=int, default=50, help='显示前 N 个结果（默认50）')
    parser.add_argument('--file', type=str, help='搜索特定文件名')
    parser.add_argument('--text', type=str, help='搜索包含特定文本片段的节点')
    parser.add_argument('--show-subquestions', action='store_true', help='显示子问题分解信息')
    
    args = parser.parse_args()
    
    if args.text:
        # 搜索文本片段
        search_text_fragment(args.question, args.text, args.top_k)
    elif args.file:
        # 搜索特定文件
        search_specific_file(args.question, args.file, args.top_k)
    else:
        # 显示所有检索结果
        debug_retrieval(args.question, args.top_k, args.show_subquestions)
