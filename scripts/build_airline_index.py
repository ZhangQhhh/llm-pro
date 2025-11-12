#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
航司知识库索引构建脚本
用于构建民航办事处常驻人员和机组人员签证协议的向量索引
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from llama_index.core import (
    VectorStoreIndex,
    SimpleDirectoryReader,
    StorageContext,
    Settings as LlamaSettings
)
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from config import Settings
from utils.logger import logger


def build_airline_index():
    """构建航司知识库索引"""
    
    logger.info("=" * 60)
    logger.info("开始构建航司知识库索引")
    logger.info("=" * 60)
    
    # 1. 检查配置
    kb_dir = Settings.AIRLINE_KB_DIR
    storage_path = Settings.AIRLINE_STORAGE_PATH
    collection_name = Settings.AIRLINE_COLLECTION
    
    logger.info(f"知识库目录: {kb_dir}")
    logger.info(f"存储路径: {storage_path}")
    logger.info(f"Collection名称: {collection_name}")
    
    if not os.path.exists(kb_dir):
        logger.error(f"知识库目录不存在: {kb_dir}")
        logger.error("请先运行: scripts/setup_airline_kb.sh")
        return False
    
    # 2. 检查文件
    files = list(Path(kb_dir).glob("*.txt"))
    if not files:
        logger.error(f"知识库目录为空: {kb_dir}")
        logger.error("请将航司协议文件复制到该目录")
        return False
    
    logger.info(f"找到 {len(files)} 个文件:")
    for f in files:
        logger.info(f"  - {f.name}")
    
    # 3. 初始化 Embedding 模型
    logger.info(f"加载 Embedding 模型: {Settings.EMBED_MODEL_PATH}")
    embed_model = HuggingFaceEmbedding(
        model_name=Settings.EMBED_MODEL_PATH,
        device=Settings.DEVICE
    )
    LlamaSettings.embed_model = embed_model
    
    # 4. 初始化 Qdrant 客户端
    logger.info(f"连接 Qdrant: {Settings.QDRANT_HOST}:{Settings.QDRANT_PORT}")
    qdrant_client = QdrantClient(
        host=Settings.QDRANT_HOST,
        port=Settings.QDRANT_PORT
    )
    
    # 5. 检查并删除旧的 collection
    collections = qdrant_client.get_collections().collections
    collection_names = [c.name for c in collections]
    
    if collection_name in collection_names:
        logger.warning(f"Collection '{collection_name}' 已存在，将被删除")
        qdrant_client.delete_collection(collection_name)
        logger.info("✓ 旧 Collection 已删除")
    
    # 6. 创建向量存储
    logger.info(f"创建向量存储: {collection_name}")
    vector_store = QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name
    )
    
    # 7. 加载文档
    logger.info("加载文档...")
    reader = SimpleDirectoryReader(
        input_dir=kb_dir,
        filename_as_id=True,
        recursive=False
    )
    documents = reader.load_data()
    logger.info(f"✓ 加载了 {len(documents)} 个文档")
    
    # 8. 构建索引
    logger.info("开始构建向量索引（这可能需要几分钟）...")
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    index = VectorStoreIndex.from_documents(
        documents,
        storage_context=storage_context,
        show_progress=True
    )
    
    logger.info("✓ 向量索引构建完成")
    
    # 9. 保存索引（可选）
    os.makedirs(storage_path, exist_ok=True)
    logger.info(f"保存索引到: {storage_path}")
    index.storage_context.persist(persist_dir=storage_path)
    logger.info("✓ 索引保存完成")
    
    # 10. 验证索引
    logger.info("验证索引...")
    collection_info = qdrant_client.get_collection(collection_name)
    logger.info(f"✓ Collection '{collection_name}' 包含 {collection_info.points_count} 个向量")
    
    # 11. 测试检索
    logger.info("测试检索功能...")
    test_query = "执行中美航班的机组人员需要签证吗？"
    retriever = index.as_retriever(similarity_top_k=5)
    results = retriever.retrieve(test_query)
    
    logger.info(f"✓ 测试查询: {test_query}")
    logger.info(f"✓ 返回 {len(results)} 条结果")
    if results:
        logger.info(f"  Top1 得分: {results[0].score:.4f}")
        logger.info(f"  Top1 内容预览: {results[0].node.get_content()[:100]}...")
    
    logger.info("=" * 60)
    logger.info("航司知识库索引构建成功！")
    logger.info("=" * 60)
    logger.info("")
    logger.info("后续步骤:")
    logger.info("1. 启用航司功能: export ENABLE_AIRLINE_FEATURE=true")
    logger.info("2. 启用意图分类: export ENABLE_INTENT_CLASSIFIER=true")
    logger.info("3. 重启服务: systemctl restart llm_pro")
    logger.info("4. 查看文档: docs/AIRLINE_KB_README.md")
    
    return True


if __name__ == "__main__":
    try:
        success = build_airline_index()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"构建索引失败: {e}", exc_info=True)
        sys.exit(1)
