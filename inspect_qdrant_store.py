# -*- coding: utf-8 -*-
"""
检查 QdrantVectorStore 如何存储节点
"""
import inspect
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.schema import TextNode

def inspect_qdrant_store():
    """检查 QdrantVectorStore 的实现"""
    print("=" * 80)
    print("QdrantVectorStore 实现检查")
    print("=" * 80)
    
    # 1. 查看 QdrantVectorStore 的方法
    print("\n1. QdrantVectorStore 可用方法:")
    methods = [m for m in dir(QdrantVectorStore) if not m.startswith('_')]
    for method in methods:
        print(f"  - {method}")
    
    # 2. 查看 add 方法的签名
    print("\n" + "=" * 80)
    print("2. add() 方法签名:")
    print("=" * 80)
    
    if hasattr(QdrantVectorStore, 'add'):
        try:
            sig = inspect.signature(QdrantVectorStore.add)
            print(f"签名: {sig}")
            
            # 获取源代码
            try:
                source = inspect.getsource(QdrantVectorStore.add)
                print(f"\n源代码（前50行）:")
                print("-" * 80)
                lines = source.split('\n')[:50]
                for i, line in enumerate(lines, 1):
                    print(f"{i:3d}: {line}")
            except:
                print("无法获取源代码")
        except Exception as e:
            print(f"无法获取签名: {e}")
    
    # 3. 查看 _build_points 或类似的方法
    print("\n" + "=" * 80)
    print("3. 查找节点转换相关方法:")
    print("=" * 80)
    
    conversion_methods = [m for m in dir(QdrantVectorStore) if 'point' in m.lower() or 'node' in m.lower() or 'payload' in m.lower()]
    for method in conversion_methods:
        print(f"  - {method}")
        if not method.startswith('_'):
            try:
                sig = inspect.signature(getattr(QdrantVectorStore, method))
                print(f"    签名: {sig}")
            except:
                pass
    
    # 4. 检查 TextNode 的序列化
    print("\n" + "=" * 80)
    print("4. TextNode 序列化检查:")
    print("=" * 80)
    
    test_node = TextNode(
        text="测试文本",
        metadata={"file_name": "test.txt"}
    )
    
    # 检查可能的序列化方法
    serialization_methods = ['dict', 'to_dict', 'json', 'to_json', '__dict__']
    for method_name in serialization_methods:
        if hasattr(test_node, method_name):
            print(f"\n{method_name} 存在:")
            try:
                if callable(getattr(test_node, method_name)):
                    result = getattr(test_node, method_name)()
                else:
                    result = getattr(test_node, method_name)
                
                if isinstance(result, dict):
                    print(f"  键: {list(result.keys())}")
                    if 'text' in result:
                        print(f"  text 字段: {result['text'][:50]}...")
                    if '_node_content' in result:
                        print(f"  _node_content 字段: {result['_node_content'][:50]}...")
                else:
                    print(f"  类型: {type(result)}")
                    print(f"  值: {str(result)[:100]}...")
            except Exception as e:
                print(f"  调用失败: {e}")
    
    # 5. 查看 LlamaIndex 如何生成 payload
    print("\n" + "=" * 80)
    print("5. 查找 payload 生成逻辑:")
    print("=" * 80)
    
    # 查找所有包含 "payload" 的私有方法
    private_methods = [m for m in dir(QdrantVectorStore) if m.startswith('_') and 'payload' in m.lower()]
    for method in private_methods:
        print(f"\n方法: {method}")
        try:
            source = inspect.getsource(getattr(QdrantVectorStore, method))
            print(f"源代码（前30行）:")
            print("-" * 80)
            lines = source.split('\n')[:30]
            for i, line in enumerate(lines, 1):
                print(f"{i:3d}: {line}")
        except Exception as e:
            print(f"  无法获取源代码: {e}")

if __name__ == "__main__":
    inspect_qdrant_store()
