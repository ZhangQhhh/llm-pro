# -*- coding: utf-8 -*-
"""
测试修复后的存储格式
"""
from qdrant_client import QdrantClient
from core.custom_qdrant_store import FixedQdrantVectorStore
from llama_index.core import VectorStoreIndex, StorageContext, ServiceContext, Settings as LlamaSettings
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from config.settings import Settings
import json

def test_fixed_storage():
    """测试修复后的存储"""
    print("=" * 80)
    print("测试修复后的 FixedQdrantVectorStore")
    print("=" * 80)
    
    test_collection = "test_fixed_storage"
    
    client = QdrantClient(
        host=Settings.QDRANT_HOST,
        port=Settings.QDRANT_PORT
    )
    
    # 删除旧集合
    try:
        client.delete_collection(test_collection)
        print("✓ 已删除旧集合")
    except:
        print("✓ 无旧集合")
    
    # 初始化 Embedding
    print(f"\n加载 Embedding 模型...")
    embed_model = HuggingFaceEmbedding(
        model_name=Settings.EMBED_MODEL_PATH,
        trust_remote_code=True
    )
    LlamaSettings.embed_model = embed_model
    print("✓ Embedding 模型加载完成")
    
    # 创建测试节点
    print("\n" + "=" * 80)
    print("创建测试节点")
    print("=" * 80)
    
    test_nodes = [
        TextNode(
            text="这是第一个测试文本，用于验证修复后的存储格式。",
            metadata={"test_id": 1, "file_name": "test1.txt"}
        ),
        TextNode(
            text="这是第二个测试文本，包含中文字符和标点符号！",
            metadata={"test_id": 2, "file_name": "test2.txt"}
        ),
        TextNode(
            text="第三个测试：验证 _node_content 字段是否只存储纯文本。",
            metadata={"test_id": 3, "file_name": "test3.txt"}
        )
    ]
    
    print(f"创建了 {len(test_nodes)} 个测试节点")
    
    # 使用修复版的 QdrantVectorStore
    print("\n" + "=" * 80)
    print("使用 FixedQdrantVectorStore 构建索引")
    print("=" * 80)
    
    vector_store = FixedQdrantVectorStore(
        client=client,
        collection_name=test_collection
    )
    
    storage_context = StorageContext.from_defaults(
        vector_store=vector_store
    )
    
    # 不需要 ServiceContext，直接使用全局 Settings
    # 禁用 LLM（我们只测试存储，不需要 LLM）
    from llama_index.core.llms import MockLLM
    LlamaSettings.llm = MockLLM()
    
    print("开始构建索引...")
    index = VectorStoreIndex(
        test_nodes,
        storage_context=storage_context,
        show_progress=True
    )
    print("✓ 索引构建完成")
    
    # 验证存储格式
    print("\n" + "=" * 80)
    print("验证 Qdrant 中的存储格式")
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
    
    success_count = 0
    fail_count = 0
    
    for i, point in enumerate(result[0], 1):
        print("=" * 80)
        print(f"节点 #{i}")
        print("=" * 80)
        
        node_content = point.payload.get("_node_content", "")
        
        print(f"\n_node_content:")
        print(f"  类型: {type(node_content)}")
        print(f"  长度: {len(node_content)}")
        
        # 检查是否是 JSON
        is_json = node_content.strip().startswith('{') if node_content else False
        
        if is_json:
            print(f"  ❌ 格式: JSON（修复失败）")
            print(f"  内容: {node_content[:200]}...")
            fail_count += 1
        else:
            print(f"  ✅ 格式: 纯文本（修复成功）")
            print(f"  内容: {node_content}")
            success_count += 1
        
        # 显示其他字段
        print(f"\n其他字段:")
        for key, value in point.payload.items():
            if key != "_node_content":
                print(f"  {key}: {value}")
        
        print()
    
    # 总结
    print("=" * 80)
    print("测试总结")
    print("=" * 80)
    print(f"\n✅ 成功: {success_count} 个节点")
    print(f"❌ 失败: {fail_count} 个节点")
    
    if fail_count == 0:
        print(f"\n🎉 修复成功！所有节点的 _node_content 都是纯文本格式")
    else:
        print(f"\n⚠️  修复未完全生效，仍有 {fail_count} 个节点存储了 JSON")
    
    # 清理
    print("\n" + "=" * 80)
    print("清理测试数据")
    print("=" * 80)
    
    try:
        client.delete_collection(test_collection)
        print(f"✓ 已删除测试集合")
    except Exception as e:
        print(f"⚠ 删除失败: {e}")

if __name__ == "__main__":
    test_fixed_storage()
