# -*- coding: utf-8 -*-
"""
调试 TextNode 序列化行为
"""
from llama_index.core.schema import TextNode, Document
import json

def test_serialization():
    """测试 TextNode 和 Document 的序列化"""
    print("=" * 80)
    print("测试 LlamaIndex 节点序列化")
    print("=" * 80)
    
    # 测试数据
    test_text = "这是一段测试文本，用于验证节点序列化。"
    test_metadata = {
        "file_name": "test.txt",
        "file_path": "/path/to/test.txt"
    }
    
    # 1. 测试 Document
    print("\n" + "=" * 80)
    print("1. Document 对象")
    print("=" * 80)
    
    doc = Document(
        text=test_text,
        metadata=test_metadata
    )
    
    print(f"\nDocument.text: {doc.text}")
    print(f"Document.get_content(): {doc.get_content()}")
    print(f"Document.metadata: {doc.metadata}")
    
    # 尝试序列化
    try:
        doc_dict = doc.dict()
        print(f"\nDocument.dict() 键: {list(doc_dict.keys())}")
        print(f"Document.dict() 完整内容:")
        print(json.dumps(doc_dict, ensure_ascii=False, indent=2)[:500])
    except Exception as e:
        print(f"Document.dict() 失败: {e}")
    
    # 2. 测试 TextNode
    print("\n" + "=" * 80)
    print("2. TextNode 对象")
    print("=" * 80)
    
    text_node = TextNode(
        text=test_text,
        metadata=test_metadata
    )
    
    print(f"\nTextNode.text: {text_node.text}")
    print(f"TextNode.get_content(): {text_node.get_content()}")
    print(f"TextNode.metadata: {text_node.metadata}")
    
    # 尝试序列化
    try:
        node_dict = text_node.dict()
        print(f"\nTextNode.dict() 键: {list(node_dict.keys())}")
        print(f"TextNode.dict() 完整内容:")
        print(json.dumps(node_dict, ensure_ascii=False, indent=2)[:500])
    except Exception as e:
        print(f"TextNode.dict() 失败: {e}")
    
    # 3. 测试从 Document 转换为 TextNode
    print("\n" + "=" * 80)
    print("3. Document -> TextNode 转换")
    print("=" * 80)
    
    converted_node = TextNode(
        text=doc.get_content(),
        metadata=doc.metadata.copy()
    )
    
    print(f"\n转换后的 TextNode.text: {converted_node.text}")
    print(f"转换后的 TextNode.get_content(): {converted_node.get_content()}")
    
    # 4. 检查 to_dict() 方法
    print("\n" + "=" * 80)
    print("4. 检查序列化方法")
    print("=" * 80)
    
    print(f"\nTextNode 可用方法:")
    methods = [m for m in dir(text_node) if not m.startswith('_')]
    for method in methods:
        if 'dict' in method.lower() or 'json' in method.lower() or 'serial' in method.lower():
            print(f"  - {method}")
    
    # 5. 测试 get_text() 方法
    print("\n" + "=" * 80)
    print("5. 测试内容获取方法")
    print("=" * 80)
    
    if hasattr(text_node, 'get_text'):
        print(f"TextNode.get_text(): {text_node.get_text()}")
    
    if hasattr(text_node, 'text'):
        print(f"TextNode.text 属性: {text_node.text}")
    
    # 6. 检查 LlamaIndex 版本
    print("\n" + "=" * 80)
    print("6. LlamaIndex 版本信息")
    print("=" * 80)
    
    try:
        import llama_index
        print(f"llama_index 版本: {llama_index.__version__}")
    except:
        print("无法获取 llama_index 版本")
    
    try:
        from llama_index.core import __version__
        print(f"llama_index.core 版本: {__version__}")
    except:
        print("无法获取 llama_index.core 版本")

if __name__ == "__main__":
    test_serialization()
