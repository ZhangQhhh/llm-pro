# -*- coding: utf-8 -*-
"""
调试脚本：检查 Qdrant 中节点的实际内容
"""
from qdrant_client import QdrantClient
from config import Settings
import json
import sys

def debug_nodes():
    """检查节点内容"""
    # 输出到文件
    output_file = "debug_nodes_output.txt"
    
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            # 重定向标准输出到文件
            original_stdout = sys.stdout
            sys.stdout = f
            
            print("=" * 80)
            print("开始检查 Qdrant 节点内容")
            print("=" * 80)
            
            # 连接 Qdrant
            client = QdrantClient(
                host=Settings.QDRANT_HOST,
                port=Settings.QDRANT_PORT
            )
            
            # 获取前5个节点
            collection_name = Settings.QDRANT_COLLECTION
            print(f"\n检查集合: {collection_name}")
            
            try:
                result = client.scroll(
                    collection_name=collection_name,
                    limit=5,
                    with_payload=True,
                    with_vectors=False
                )
                
                points = result[0]
                print(f"\n成功获取 {len(points)} 个节点\n")
                
                for i, point in enumerate(points, 1):
                    print("=" * 80)
                    print(f"节点 #{i}")
                    print("=" * 80)
                    print(f"ID: {point.id}")
                    print(f"\nPayload 所有字段: {list(point.payload.keys())}")
                    
                    # 检查 _node_content
                    node_content = point.payload.get("_node_content", None)
                    print(f"\n_node_content 存在: {node_content is not None}")
                    if node_content:
                        print(f"_node_content 类型: {type(node_content)}")
                        print(f"_node_content 长度: {len(str(node_content))}")
                        print(f"_node_content 前200字符:\n{str(node_content)[:200]}")
                    
                    # 检查 text
                    text = point.payload.get("text", None)
                    print(f"\ntext 存在: {text is not None}")
                    if text:
                        print(f"text 类型: {type(text)}")
                        print(f"text 长度: {len(str(text))}")
                        print(f"text 前200字符:\n{str(text)[:200]}")
                    
                    # 检查其他字段
                    print(f"\nfile_name: {point.payload.get('file_name', 'NOT FOUND')}")
                    print(f"file_path: {point.payload.get('file_path', 'NOT FOUND')}")
                    
                    # 检查是否有以 _ 开头的其他字段
                    internal_fields = [k for k in point.payload.keys() if k.startswith("_")]
                    print(f"\n所有内部字段 (_开头): {internal_fields}")
                    
                    print("\n")
            
            except Exception as e:
                print(f"错误: {e}")
                import traceback
                traceback.print_exc()
            
            # 恢复标准输出
            sys.stdout = original_stdout
        
        print(f"✓ 调试信息已写入: {output_file}")
        
    except Exception as e:
        print(f"写入文件失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_nodes()
