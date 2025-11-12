#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
诊断航司知识库向量存储问题
检查 Qdrant 中实际存储的数据结构
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from qdrant_client import QdrantClient
from config import Settings
from utils.logger import logger
import json


def diagnose_airline_storage():
    """诊断航司知识库存储"""
    
    logger.info("=" * 80)
    logger.info("航司知识库存储诊断")
    logger.info("=" * 80)
    
    # 1. 连接 Qdrant
    logger.info(f"\n[步骤1] 连接 Qdrant: {Settings.QDRANT_HOST}:{Settings.QDRANT_PORT}")
    qdrant_client = QdrantClient(
        host=Settings.QDRANT_HOST,
        port=Settings.QDRANT_PORT
    )
    
    # 2. 检查集合是否存在
    collection_name = Settings.AIRLINE_COLLECTION
    logger.info(f"\n[步骤2] 检查集合: {collection_name}")
    
    try:
        collections = qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        logger.info(f"所有集合: {collection_names}")
        
        if collection_name not in collection_names:
            logger.error(f"❌ 集合 '{collection_name}' 不存在！")
            logger.info("\n请先运行: python scripts/build_airline_index.py")
            return False
        
        logger.info(f"✓ 集合 '{collection_name}' 存在")
        
    except Exception as e:
        logger.error(f"❌ 无法连接到 Qdrant: {e}")
        return False
    
    # 3. 获取集合信息
    logger.info(f"\n[步骤3] 获取集合信息")
    try:
        collection_info = qdrant_client.get_collection(collection_name)
        logger.info(f"向量数量: {collection_info.points_count}")
        logger.info(f"向量维度: {collection_info.config.params.vectors.size}")
        logger.info(f"距离度量: {collection_info.config.params.vectors.distance}")
    except Exception as e:
        logger.error(f"❌ 获取集合信息失败: {e}")
        return False
    
    # 4. 获取前3个点的详细信息
    logger.info(f"\n[步骤4] 获取前3个点的详细信息")
    try:
        scroll_result = qdrant_client.scroll(
            collection_name=collection_name,
            limit=3,
            with_payload=True,
            with_vectors=False
        )
        
        points = scroll_result[0]
        logger.info(f"获取到 {len(points)} 个点")
        
        for i, point in enumerate(points, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"点 #{i} - ID: {point.id}")
            logger.info(f"{'='*60}")
            
            # 检查 payload 结构
            if not point.payload:
                logger.warning("⚠️ payload 为空！")
                continue
            
            logger.info(f"\nPayload 字段列表:")
            for key in sorted(point.payload.keys()):
                value = point.payload[key]
                value_type = type(value).__name__
                
                # 显示值的预览
                if isinstance(value, str):
                    preview = value[:100] + "..." if len(value) > 100 else value
                    logger.info(f"  - {key} ({value_type}): {preview}")
                elif isinstance(value, (list, dict)):
                    logger.info(f"  - {key} ({value_type}): {json.dumps(value, ensure_ascii=False)[:100]}...")
                else:
                    logger.info(f"  - {key} ({value_type}): {value}")
            
            # 重点检查文本内容字段
            logger.info(f"\n🔍 文本内容字段检查:")
            text_fields = ['_node_content', 'text', 'content', 'doc_id']
            
            for field in text_fields:
                if field in point.payload:
                    value = point.payload[field]
                    if isinstance(value, str):
                        logger.info(f"  ✓ 找到字段 '{field}': {len(value)} 字符")
                        logger.info(f"    内容预览: {value[:200]}...")
                    else:
                        logger.info(f"  ⚠️ 字段 '{field}' 存在但不是字符串类型: {type(value)}")
                else:
                    logger.info(f"  ✗ 未找到字段 '{field}'")
            
            # 检查是否有向量数据被误存到 payload
            logger.info(f"\n🔍 检查是否有向量数据:")
            for key, value in point.payload.items():
                if isinstance(value, list) and len(value) > 100:
                    logger.warning(f"  ⚠️ 字段 '{key}' 包含 {len(value)} 个元素的列表，可能是向量！")
                    if all(isinstance(x, (int, float)) for x in value[:10]):
                        logger.error(f"  ❌ 字段 '{key}' 确实是向量数据！这不应该存储在 payload 中！")
    
    except Exception as e:
        logger.error(f"❌ 获取点信息失败: {e}", exc_info=True)
        return False
    
    # 5. 测试检索
    logger.info(f"\n[步骤5] 测试检索功能")
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        from llama_index.vector_stores.qdrant import QdrantVectorStore
        from llama_index.core import VectorStoreIndex, Settings as LlamaSettings
        
        # 初始化 Embedding 模型
        logger.info(f"加载 Embedding 模型: {Settings.EMBED_MODEL_PATH}")
        embed_model = HuggingFaceEmbedding(
            model_name=Settings.EMBED_MODEL_PATH,
            device=Settings.DEVICE
        )
        LlamaSettings.embed_model = embed_model
        
        # 创建向量存储
        vector_store = QdrantVectorStore(
            client=qdrant_client,
            collection_name=collection_name
        )
        
        # 加载索引
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
        
        # 测试检索
        test_query = "机组人员需要签证吗？"
        logger.info(f"\n测试查询: {test_query}")
        
        retriever = index.as_retriever(similarity_top_k=3)
        results = retriever.retrieve(test_query)
        
        logger.info(f"✓ 返回 {len(results)} 条结果")
        
        for i, result in enumerate(results, 1):
            logger.info(f"\n结果 #{i}:")
            logger.info(f"  得分: {result.score:.4f}")
            logger.info(f"  节点类型: {type(result.node).__name__}")
            
            # 尝试多种方式获取文本内容
            logger.info(f"\n  🔍 尝试获取文本内容:")
            
            # 方式1: .text 属性
            if hasattr(result.node, 'text'):
                text = result.node.text
                logger.info(f"    ✓ .text 属性: {type(text).__name__}, {len(text) if isinstance(text, str) else 'N/A'} 字符")
                if isinstance(text, str):
                    logger.info(f"      内容预览: {text[:200]}...")
                else:
                    logger.error(f"      ❌ .text 不是字符串！实际值: {text}")
            else:
                logger.warning(f"    ✗ 没有 .text 属性")
            
            # 方式2: .get_content() 方法
            if hasattr(result.node, 'get_content'):
                try:
                    content = result.node.get_content()
                    logger.info(f"    ✓ .get_content(): {type(content).__name__}, {len(content) if isinstance(content, str) else 'N/A'} 字符")
                    if isinstance(content, str):
                        logger.info(f"      内容预览: {content[:200]}...")
                    else:
                        logger.error(f"      ❌ .get_content() 不返回字符串！实际值: {content}")
                except Exception as e:
                    logger.error(f"    ✗ .get_content() 调用失败: {e}")
            else:
                logger.warning(f"    ✗ 没有 .get_content() 方法")
            
            # 方式3: metadata
            if hasattr(result.node, 'metadata'):
                logger.info(f"    ✓ metadata: {list(result.node.metadata.keys())}")
        
    except Exception as e:
        logger.error(f"❌ 测试检索失败: {e}", exc_info=True)
        return False
    
    logger.info("\n" + "=" * 80)
    logger.info("诊断完成")
    logger.info("=" * 80)
    
    return True


if __name__ == "__main__":
    try:
        success = diagnose_airline_storage()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"诊断失败: {e}", exc_info=True)
        sys.exit(1)
