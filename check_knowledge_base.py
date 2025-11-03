#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
检查知识库状态的诊断脚本
"""
from qdrant_client import QdrantClient
from config import Settings

def check_knowledge_base():
    """检查知识库状态"""
    print("=" * 60)
    print("知识库状态检查")
    print("=" * 60)
    
    # 1. 连接 Qdrant
    try:
        client = QdrantClient(
            host=Settings.QDRANT_HOST,
            port=Settings.QDRANT_PORT
        )
        print(f"✓ 成功连接到 Qdrant ({Settings.QDRANT_HOST}:{Settings.QDRANT_PORT})")
    except Exception as e:
        print(f"✗ 无法连接到 Qdrant: {e}")
        return
    
    # 2. 获取所有集合
    try:
        collections = client.get_collections()
        print(f"\n找到 {len(collections.collections)} 个集合:")
        
        for collection in collections.collections:
            print(f"\n集合名称: {collection.name}")
            
            # 获取集合信息
            try:
                collection_info = client.get_collection(collection.name)
                print(f"  - 向量维度: {collection_info.config.params.vectors.size}")
                print(f"  - 距离度量: {collection_info.config.params.vectors.distance}")
                
                # 获取文档数量
                count = client.count(collection_name=collection.name)
                print(f"  - 文档数量: {count.count}")
                
                # 检查是否是我们的集合
                if collection.name == Settings.QDRANT_COLLECTION:
                    print(f"  ✓ 这是通用知识库集合")
                    if count.count == 0:
                        print(f"  ✗ 警告: 通用知识库为空！")
                elif collection.name == Settings.VISA_FREE_COLLECTION:
                    print(f"  ✓ 这是免签知识库集合")
                    if count.count == 0:
                        print(f"  ✗ 警告: 免签知识库为空！")
                
            except Exception as e:
                print(f"  ✗ 无法获取集合信息: {e}")
        
    except Exception as e:
        print(f"✗ 无法获取集合列表: {e}")
        return
    
    # 3. 检查配置
    print("\n" + "=" * 60)
    print("配置检查")
    print("=" * 60)
    print(f"通用知识库集合名: {Settings.QDRANT_COLLECTION}")
    print(f"免签知识库集合名: {Settings.VISA_FREE_COLLECTION}")
    print(f"通用知识库目录: {Settings.KNOWLEDGE_BASE_DIR}")
    print(f"免签知识库目录: {Settings.VISA_FREE_KB_DIR}")
    print(f"免签功能启用: {Settings.ENABLE_VISA_FREE_FEATURE}")
    print(f"意图分类器启用: {Settings.ENABLE_INTENT_CLASSIFIER}")
    
    # 4. 检查知识库目录
    import os
    print("\n" + "=" * 60)
    print("知识库目录检查")
    print("=" * 60)
    
    # 检查通用知识库
    if os.path.exists(Settings.KNOWLEDGE_BASE_DIR):
        files = list(os.listdir(Settings.KNOWLEDGE_BASE_DIR))
        print(f"✓ 通用知识库目录存在")
        print(f"  - 文件数量: {len(files)}")
        if len(files) > 0:
            print(f"  - 示例文件: {files[:5]}")
        else:
            print(f"  ✗ 警告: 通用知识库目录为空！")
    else:
        print(f"✗ 通用知识库目录不存在: {Settings.KNOWLEDGE_BASE_DIR}")
    
    # 检查免签知识库
    if Settings.ENABLE_VISA_FREE_FEATURE:
        if os.path.exists(Settings.VISA_FREE_KB_DIR):
            files = list(os.listdir(Settings.VISA_FREE_KB_DIR))
            print(f"\n✓ 免签知识库目录存在")
            print(f"  - 文件数量: {len(files)}")
            if len(files) > 0:
                print(f"  - 示例文件: {files[:5]}")
            else:
                print(f"  ✗ 警告: 免签知识库目录为空！")
        else:
            print(f"\n✗ 免签知识库目录不存在: {Settings.VISA_FREE_KB_DIR}")
    
    print("\n" + "=" * 60)
    print("检查完成")
    print("=" * 60)

if __name__ == "__main__":
    check_knowledge_base()
