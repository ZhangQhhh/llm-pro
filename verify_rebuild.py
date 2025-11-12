# -*- coding: utf-8 -*-
"""
验证知识库重建是否成功
"""
from qdrant_client import QdrantClient
from config.settings import Settings
import json

def verify_all_collections():
    """验证所有知识库的数据格式"""
    print("=" * 80)
    print("验证知识库重建结果")
    print("=" * 80)
    
    client = QdrantClient(
        host=Settings.QDRANT_HOST,
        port=Settings.QDRANT_PORT
    )
    
    collections = [
        ("通用知识库", Settings.QDRANT_COLLECTION),
        ("免签知识库", Settings.VISA_FREE_COLLECTION),
        ("航司知识库", Settings.AIRLINE_COLLECTION),
    ]
    
    for name, collection_name in collections:
        print(f"\n{'=' * 80}")
        print(f"检查 {name} ({collection_name})")
        print("=" * 80)
        
        try:
            # 获取集合信息
            collection_info = client.get_collection(collection_name)
            total_points = collection_info.points_count
            print(f"总节点数: {total_points}")
            
            if total_points == 0:
                print(f"⚠️  集合为空！")
                continue
            
            # 随机获取 3 个节点检查
            result = client.scroll(
                collection_name=collection_name,
                limit=3,
                with_payload=True,
                with_vectors=False
            )
            
            if not result[0]:
                print(f"⚠️  无法获取节点数据")
                continue
            
            print(f"\n抽样检查 {len(result[0])} 个节点:")
            print("-" * 80)
            
            valid_count = 0
            invalid_count = 0
            
            for i, point in enumerate(result[0], 1):
                node_content = point.payload.get("_node_content", "")
                
                print(f"\n节点 #{i}")
                print(f"  ID: {point.id}")
                print(f"  _node_content 长度: {len(node_content)}")
                
                # 检查是否是 JSON
                is_json = node_content.strip().startswith('{')
                
                if is_json:
                    print(f"  ❌ 格式: JSON（异常）")
                    print(f"  预览: {node_content[:100]}...")
                    invalid_count += 1
                    
                    # 尝试解析
                    try:
                        parsed = json.loads(node_content)
                        if "text" in parsed:
                            print(f"  JSON内部text: {parsed['text'][:80]}...")
                    except:
                        pass
                else:
                    print(f"  ✅ 格式: 纯文本（正常）")
                    print(f"  预览: {node_content[:100]}...")
                    valid_count += 1
            
            print(f"\n" + "-" * 80)
            print(f"抽样结果: ✅ {valid_count} 个正常, ❌ {invalid_count} 个异常")
            
            if invalid_count > 0:
                print(f"\n⚠️  {name} 仍有异常数据，可能需要：")
                print(f"   1. 确认是否真的重建了索引")
                print(f"   2. 检查 Qdrant 是否有多个同名 collection")
                print(f"   3. 手动删除 collection 后重建")
            else:
                print(f"\n✅ {name} 数据格式正确！")
                
        except Exception as e:
            print(f"❌ 检查失败: {e}")
    
    print("\n" + "=" * 80)
    print("验证完成")
    print("=" * 80)

if __name__ == "__main__":
    verify_all_collections()
