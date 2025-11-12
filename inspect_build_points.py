# -*- coding: utf-8 -*-
"""
检查 _build_points 方法的实现
"""
import inspect
from llama_index.vector_stores.qdrant import QdrantVectorStore

def inspect_build_points():
    """检查 _build_points 方法"""
    print("=" * 80)
    print("检查 QdrantVectorStore._build_points 方法")
    print("=" * 80)
    
    if hasattr(QdrantVectorStore, '_build_points'):
        print("\n✓ _build_points 方法存在")
        
        # 获取方法签名
        try:
            sig = inspect.signature(QdrantVectorStore._build_points)
            print(f"\n方法签名: {sig}")
        except Exception as e:
            print(f"无法获取签名: {e}")
        
        # 获取源代码
        try:
            source = inspect.getsource(QdrantVectorStore._build_points)
            print(f"\n完整源代码:")
            print("=" * 80)
            lines = source.split('\n')
            for i, line in enumerate(lines, 1):
                print(f"{i:4d}: {line}")
            print("=" * 80)
        except Exception as e:
            print(f"无法获取源代码: {e}")
    else:
        print("\n✗ _build_points 方法不存在")
    
    # 查找所有包含 "node_to" 或 "to_dict" 的方法
    print("\n" + "=" * 80)
    print("查找节点转换相关的方法:")
    print("=" * 80)
    
    all_methods = dir(QdrantVectorStore)
    conversion_methods = [m for m in all_methods if 'node' in m.lower() or 'dict' in m.lower() or 'payload' in m.lower()]
    
    for method_name in conversion_methods:
        if method_name.startswith('_'):
            print(f"\n方法: {method_name}")
            try:
                method = getattr(QdrantVectorStore, method_name)
                if callable(method):
                    sig = inspect.signature(method)
                    print(f"  签名: {sig}")
            except:
                pass

if __name__ == "__main__":
    inspect_build_points()
