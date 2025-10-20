# -*- coding: utf-8 -*-
"""
对话清理脚本
用于定期清理过期的对话记录
"""
from services.conversation_manager import ConversationManager
from services.embedding_service import EmbeddingService
from qdrant_client import QdrantClient
from config import Settings
from utils.logger import logger


def main():
    """执行对话清理任务"""
    try:
        logger.info("=" * 60)
        logger.info("开始执行对话清理任务")
        logger.info("=" * 60)

        # 初始化服务
        logger.info("正在初始化 Embedding 服务...")
        embedding_service = EmbeddingService()
        embed_model, _ = embedding_service.initialize()

        logger.info("正在连接 Qdrant 数据库...")
        qdrant_client = QdrantClient(
            host=Settings.QDRANT_HOST,
            port=Settings.QDRANT_PORT
        )

        logger.info("正在初始化对话管理器...")
        conversation_manager = ConversationManager(embed_model, qdrant_client)

        # 执行自动清理（使用配置文件中的过期天数）
        logger.info(f"清理策略: 删除超过 {Settings.CONVERSATION_EXPIRE_DAYS} 天的对话")
        result = conversation_manager.cleanup_expired_conversations()

        # 输出结果
        logger.info("=" * 60)
        logger.info("清理任务执行完成")
        logger.info("=" * 60)

        if result.get("success"):
            logger.info(f"✅ 删除了 {result['deleted_count']} 条过期对话")
            if result['deleted_count'] > 0:
                logger.info(f"   - 涉及会话数: {result['affected_sessions']}")
                logger.info(f"   - 释放 Token 数: {result['total_tokens_removed']}")
                logger.info(f"   - 阈值日期: {result['threshold_date']}")
        else:
            logger.error(f"❌ 清理失败: {result.get('error', '未知错误')}")

    except Exception as e:
        logger.error(f"清理任务执行出错: {e}", exc_info=True)


if __name__ == "__main__":
    main()

