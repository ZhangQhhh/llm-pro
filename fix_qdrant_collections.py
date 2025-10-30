# -*- coding: utf-8 -*-
"""
修复 Qdrant 集合维度问题
由于更换了嵌入模型（从 768 维 -> 1024 维），需要重建集合
"""
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from config import Settings as AppSettings
from services.embedding_service import EmbeddingService
from utils.logger import logger


def fix_collections():
    """重建 Qdrant 集合以匹配新的向量维度"""

    # 初始化客户端
    qdrant_client = QdrantClient(
        host=AppSettings.QDRANT_HOST,
        port=AppSettings.QDRANT_PORT
    )

    # 初始化嵌入模型获取正确的维度
    embedding_service = EmbeddingService()
    embed_model, _ = embedding_service.initialize()

    # 获取新模型的向量维度
    test_embedding = embed_model.get_text_embedding("测试文本")
    new_vector_size = len(test_embedding)
    logger.info(f"新嵌入模型向量维度: {new_vector_size}")

    # 需要重建的集合列表
    collections_to_fix = [
        AppSettings.CONVERSATION_COLLECTION,  # conversations 集合
        AppSettings.QDRANT_COLLECTION  # knowledge_base 集合（如果也需要）
    ]

    for collection_name in collections_to_fix:
        try:
            # 检查集合是否存在
            existing_collections = qdrant_client.get_collections().collections
            collection_exists = any(c.name == collection_name for c in existing_collections)

            if collection_exists:
                # 获取现有集合信息
                collection_info = qdrant_client.get_collection(collection_name)
                current_vector_size = collection_info.config.params.vectors.size

                logger.info(f"集合 '{collection_name}' 当前维度: {current_vector_size}")

                if current_vector_size != new_vector_size:
                    logger.warning(f"集合 '{collection_name}' 维度不匹配！")

                    # 询问是否删除并重建
                    response = input(f"\n是否删除并重建集合 '{collection_name}'？这将清空所有数据！(yes/no): ")

                    if response.lower() == 'yes':
                        # 删除旧集合
                        qdrant_client.delete_collection(collection_name)
                        logger.info(f"✓ 已删除集合 '{collection_name}'")

                        # 创建新集合
                        qdrant_client.create_collection(
                            collection_name=collection_name,
                            vectors_config=VectorParams(
                                size=new_vector_size,
                                distance=Distance.COSINE
                            )
                        )
                        logger.info(f"✓ 已重建集合 '{collection_name}'（新维度: {new_vector_size}）")
                    else:
                        logger.info(f"跳过集合 '{collection_name}'")
                else:
                    logger.info(f"✓ 集合 '{collection_name}' 维度正确，无需修复")
            else:
                # 集合不存在，直接创建
                logger.info(f"集合 '{collection_name}' 不存在，正在创建...")
                qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=new_vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"✓ 已创建集合 '{collection_name}'（维度: {new_vector_size}）")

        except Exception as e:
            logger.error(f"处理集合 '{collection_name}' 时出错: {e}", exc_info=True)

    logger.info("\n修复完成！")


if __name__ == "__main__":
    print("=" * 60)
    print("Qdrant 集合维度修复工具")
    print("=" * 60)
    print(f"\n当前配置:")
    print(f"  - 嵌入模型: {AppSettings.EMBED_MODEL_PATH}")
    print(f"  - Qdrant 地址: {AppSettings.QDRANT_HOST}:{AppSettings.QDRANT_PORT}")
    print(f"  - 设备: {AppSettings.DEVICE}")
    print("\n注意: 此操作将删除旧数据！请确保已备份重要数据。\n")

    input("按 Enter 键继续...")

    fix_collections()

