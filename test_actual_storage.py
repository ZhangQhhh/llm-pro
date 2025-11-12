# -*- coding: utf-8 -*-
"""
测试实际存储到 Qdrant 的数据格式
"""
from qdrant_client import QdrantClient
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core import VectorStoreIndex, StorageContext, ServiceContext, Settings as LlamaSettings
from llama_index.core.schema import TextNode, Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from config.settings import Settings
from utils.logger import logger
import json

def test_storage():
    """测试实际存储行为"""
    print("=" * 80)
    print("测试 TextNode 实际存储到 Qdrant 的格式")
    print("=" * 80)
    
    # 初始化
    test_collection = "test_storage_debug"
    
    client = QdrantClient(
        host=Settings.QDRANT_HOST,
        port=Settings.QDRANT_PORT
    )
    
    # 删除测试集合（如果存在）
    try:
        client.delete_collection(test_collection)
        print(f"✓ 已删除旧的测试集合")
    except:
        print(f"✓ 无旧集合需要删除")
    
    # 初始化 Embedding 模型
    print(f"\n加载 Embedding 模型: {Settings.EMBED_MODEL_PATH}")
    embed_model = HuggingFaceEmbedding(
        model_name=Settings.EMBED_MODEL_PATH,
        trust_remote_code=True
    )
    LlamaSettings.embed_model = embed_model
    
    # 创建测试节点
    print("\n" + "=" * 80)
    print("创建测试节点")
    print("=" * 80)
    
    # 方法1: 直接创建 TextNode
    test_nodes_method1 = [
        TextNode(
            text="这是第一个测试文本，用于验证 TextNode 的存储格式。",
            metadata={"method": "direct_textnode", "index": 1}
        ),
        TextNode(
            text="这是第二个测试文本，包含中文字符。",
            metadata={"method": "direct_textnode", "index": 2}
        )
    ]
    
    # 方法2: 从 Document 转换
    test_doc = Document(
        text="这是从 Document 转换的文本。",
        metadata={"method": "from_document", "index": 3}
    )
    
    test_nodes_method2 = [
        TextNode(
            text=test_doc.get_content(),
            metadata=test_doc.metadata.copy()
        )
    ]
    
    all_test_nodes = test_nodes_method1 + test_nodes_method2
    
    print(f"创建了 {len(all_test_nodes)} 个测试节点")
    for i, node in enumerate(all_test_nodes, 1):
        print(f"  节点{i}: {node.text[:30]}... | metadata: {node.metadata}")
    
    # 创建向量存储
    print("\n" + "=" * 80)
    print("创建向量存储并构建索引")
    print("=" * 80)
    
    vector_store = QdrantVectorStore(
        client=client,
        collection_name=test_collection
    )
    
    storage_context = StorageContext.from_defaults(
        vector_store=vector_store
    )
    
    service_context = ServiceContext.from_defaults(
        embed_model=embed_model
    )
    
    # 构建索引
    print("开始构建索引...")
    index = VectorStoreIndex(
        all_test_nodes,
        storage_context=storage_context,
        service_context=service_context,
        show_progress=True
    )
    print("✓ 索引构建完成")
    
    # 读取实际存储的数据
    print("\n" + "=" * 80)
    print("读取 Qdrant 中实际存储的数据")
    print("=" * 80)
    
    result = client.scroll(
        collection_name=test_collection,
        limit=10,
        with_payload=True,
        with_vectors=False
    )
    
    if not result[0]:
        print("❌ 集合为空！")
        return
    
    print(f"\n找到 {len(result[0])} 个节点\n")
    
    for i, point in enumerate(result[0], 1):
        print("=" * 80)
        print(f"节点 #{i}")
        print("=" * 80)
        
        print(f"\nID: {point.id}")
        print(f"\nPayload 字段: {list(point.payload.keys())}")
        
        # 检查 _node_content
        node_content = point.payload.get("_node_content", "")
        print(f"\n_node_content:")
        print(f"  存在: {bool(node_content)}")
        print(f"  类型: {type(node_content)}")
        print(f"  长度: {len(node_content)}")
        
        if node_content:
            # 检查是否是 JSON
            is_json = node_content.strip().startswith('{')
            print(f"  是否JSON: {is_json}")
            
            if is_json:
                print(f"  ❌ 格式错误：存储的是 JSON 字符串")
                print(f"  前200字符: {node_content[:200]}...")
                
                # 尝试解析
                try:
                    parsed = json.loads(node_content)
                    print(f"  JSON 内部字段: {list(parsed.keys())}")
                    if 'text' in parsed:
                        print(f"  JSON 内部的 text: {parsed['text']}")
                except Exception as e:
                    print(f"  解析失败: {e}")
            else:
                print(f"  ✅ 格式正确：存储的是纯文本")
                print(f"  内容: {node_content}")
        
        # 检查其他字段
        print(f"\n其他 payload 字段:")
        for key, value in point.payload.items():
            if key != "_node_content":
                print(f"  {key}: {value}")
        
        print()
    
    # 清理测试集合
    print("=" * 80)
    print("清理测试数据")
    print("=" * 80)
    
    try:
        client.delete_collection(test_collection)
        print(f"✓ 已删除测试集合 {test_collection}")
    except Exception as e:
        print(f"⚠ 删除失败: {e}")
    
    print("\n" + "=" * 80)
    print("测试完成")
    print("=" * 80)

if __name__ == "__main__":
    test_storage()
