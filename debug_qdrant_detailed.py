# -*- coding: utf-8 -*-
"""
详细调试脚本：检查 Qdrant 节点的所有字段
"""
from qdrant_client import QdrantClient
from config.settings import Settings
import json

def debug_qdrant_detailed():
    """详细检查 Qdrant 节点"""
    print("=" * 80)
    print("Qdrant 节点详细检查")
    print("=" * 80)
    
    client = QdrantClient(
        host=Settings.QDRANT_HOST,
        port=Settings.QDRANT_PORT
    )
    
    # 获取1个节点
    result = client.scroll(
        collection_name=Settings.QDRANT_COLLECTION,
        limit=1,
        with_payload=True,
        with_vectors=False
    )
    
    if not result[0]:
        print("集合为空！")
        return
    
    point = result[0][0]
    
    print(f"\n节点 ID: {point.id}")
    print(f"\nPayload 所有字段: {list(point.payload.keys())}")
    print("\n" + "=" * 80)
    
    # 逐个检查每个字段
    for key, value in point.payload.items():
        print(f"\n字段: {key}")
        print(f"类型: {type(value)}")
        
        if isinstance(value, str):
            print(f"长度: {len(value)}")
            if len(value) > 200:
                print(f"前200字符: {value[:200]}...")
            else:
                print(f"完整内容: {value}")
        elif isinstance(value, (list, dict)):
            print(f"内容: {json.dumps(value, ensure_ascii=False, indent=2)[:500]}...")
        else:
            print(f"值: {value}")
        
        print("-" * 80)
    
    # 特别检查 _node_content 和 text
    print("\n" + "=" * 80)
    print("关键字段对比")
    print("=" * 80)
    
    node_content = point.payload.get("_node_content", "")
    text_field = point.payload.get("text", "")
    
    print(f"\n1. _node_content 字段:")
    print(f"   存在: {bool(node_content)}")
    if node_content:
        print(f"   长度: {len(node_content)}")
        print(f"   是否JSON: {node_content.strip().startswith('{')}")
        if node_content.strip().startswith('{'):
            try:
                parsed = json.loads(node_content)
                print(f"   JSON 内部字段: {list(parsed.keys())}")
                if "text" in parsed:
                    print(f"   JSON 内部的 text: {parsed['text'][:100]}...")
            except:
                print(f"   无法解析为 JSON")
    
    print(f"\n2. text 字段:")
    print(f"   存在: {bool(text_field)}")
    if text_field:
        print(f"   长度: {len(text_field)}")
        print(f"   内容: {text_field[:200]}...")
    
    print(f"\n3. 内容是否相同:")
    if node_content and text_field:
        print(f"   _node_content == text: {node_content == text_field}")
        
        # 如果 _node_content 是 JSON，尝试提取内部的 text
        if node_content.strip().startswith('{'):
            try:
                parsed = json.loads(node_content)
                json_text = parsed.get("text", "")
                print(f"   JSON内部text == text字段: {json_text == text_field}")
            except:
                pass

if __name__ == "__main__":
    debug_qdrant_detailed()
