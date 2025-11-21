# -*- coding: utf-8 -*-
"""
构建 Keyword Table 索引

从现有文档构建 KeywordTableIndex 并持久化
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from llama_index.core import (
    KeywordTableIndex,
    StorageContext,
    load_index_from_storage,
    SimpleDirectoryReader,
    Settings as LlamaSettings
)
from llama_index.core.node_parser import SentenceSplitter
from config import Settings
from utils.logger import logger


def build_keyword_index(
    data_dir: str,
    persist_dir: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    force_rebuild: bool = False
):
    """
    构建 Keyword Table 索引
    
    Args:
        data_dir: 数据目录
        persist_dir: 持久化目录
        chunk_size: 分块大小
        chunk_overlap: 分块重叠
        force_rebuild: 是否强制重建
    """
    # 将 Keyword Table 索引存储在向量知识库目录中
    keyword_storage_dir = os.path.join(persist_dir, "vector_store", "keyword_table")
    
    # 检查是否已存在索引
    if os.path.exists(keyword_storage_dir) and not force_rebuild:
        logger.info(f"检测到已存在的 Keyword Table 索引: {keyword_storage_dir}")
        try:
            storage_context = StorageContext.from_defaults(
                persist_dir=keyword_storage_dir
            )
            keyword_index = load_index_from_storage(storage_context)
            logger.info(" 成功加载现有 Keyword Table 索引")
            return keyword_index
        except Exception as e:
            logger.warning(f"加载现有索引失败，将重新构建: {e}")
    
    logger.info(f"开始构建 Keyword Table 索引...")
    logger.info(f"数据目录: {data_dir}")
    logger.info(f"持久化目录: {keyword_storage_dir}")
    
    # 1. 加载文档
    logger.info("正在加载文档...")
    documents = SimpleDirectoryReader(
        data_dir,
        recursive=True,
        required_exts=[".txt", ".md", ".pdf", ".docx"]
    ).load_data()
    
    logger.info(f" 加载了 {len(documents)} 个文档")
    
    # 2. 分块
    logger.info(f"正在分块 | chunk_size={chunk_size}, overlap={chunk_overlap}")
    text_splitter = SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    nodes = text_splitter.get_nodes_from_documents(documents)
    
    logger.info(f" 生成了 {len(nodes)} 个节点")
    
    # 3. 构建 Keyword Table 索引
    logger.info("正在构建 Keyword Table 索引...")
    
    # 禁用 LLM（Keyword Table 不需要 LLM，使用简单的关键词提取）
    LlamaSettings.llm = None
    
    # 禁用 NLTK stopwords（避免 NLTK 数据加载错误）
    from llama_index.core.utils import globals_helper
    globals_helper._stopwords = set()  # 使用空集合代替 NLTK stopwords
    
    # 可选：自定义关键词提取模板
    # keyword_extract_template = """
    # 从以下文本中提取最重要的关键词（3-10个）：
    # {context_str}
    # 
    # 关键词（用逗号分隔）：
    # """
    
    keyword_index = KeywordTableIndex(
        nodes=nodes,
        # keyword_extract_template=keyword_extract_template  # 可选
    )
    
    logger.info(" Keyword Table 索引构建完成")
    
    # 4. 持久化
    logger.info(f"正在持久化索引到: {keyword_storage_dir}")
    os.makedirs(keyword_storage_dir, exist_ok=True)
    keyword_index.storage_context.persist(persist_dir=keyword_storage_dir)
    
    logger.info(" 索引持久化完成")
    
    # 5. 统计信息
    logger.info("=" * 60)
    logger.info("Keyword Table 索引构建完成")
    logger.info(f"文档数: {len(documents)}")
    logger.info(f"节点数: {len(nodes)}")
    logger.info(f"存储位置: {keyword_storage_dir}")
    logger.info("=" * 60)
    
    return keyword_index


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="构建 Keyword Table 索引")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=Settings.DATA_DIR,
        help="数据目录路径"
    )
    parser.add_argument(
        "--persist-dir",
        type=str,
        default=Settings.STORAGE_PATH,
        help="索引持久化目录"
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=512,
        help="分块大小"
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="分块重叠"
    )
    parser.add_argument(
        "--force-rebuild",
        action="store_true",
        help="强制重建索引"
    )
    
    args = parser.parse_args()
    
    try:
        keyword_index = build_keyword_index(
            data_dir=args.data_dir,
            persist_dir=args.persist_dir,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            force_rebuild=args.force_rebuild
        )
        
        # 测试检索
        logger.info("\n" + "=" * 60)
        logger.info("测试检索功能")
        logger.info("=" * 60)
        
        test_query = "签证申请"
        logger.info(f"测试查询: {test_query}")
        
        retriever = keyword_index.as_retriever(similarity_top_k=5)
        from llama_index.core import QueryBundle
        results = retriever.retrieve(QueryBundle(query_str=test_query))
        
        logger.info(f"检索到 {len(results)} 个结果:")
        for i, node in enumerate(results, 1):
            score = node.score if node.score is not None else 0.0
            text_preview = node.node.text[:100] if hasattr(node.node, 'text') else str(node.node)[:100]
            logger.info(f"[{i}] 分数: {score:.4f} | 内容: {text_preview}...")
        
        logger.info("\n 构建完成！")
        
    except Exception as e:
        logger.error(f"构建失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
