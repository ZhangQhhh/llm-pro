# -*- coding: utf-8 -*-
"""
Embedding 和 Reranker 服务层
"""
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.postprocessor import SentenceTransformerRerank
from llama_index.core import Settings
from config import Settings as AppSettings
from utils.logger import logger


class EmbeddingService:
    """Embedding 和 Reranker 服务管理器"""

    def __init__(self):
        self.embed_model = None
        self.reranker = None

    def initialize(self):
        """初始化 Embedding 模型和 Reranker"""
        logger.info("加载 Embedding 和 Reranker 模型...")

        # 加载 Embedding 模型
        self.embed_model = HuggingFaceEmbedding(
            model_name=AppSettings.EMBED_MODEL_PATH,
            device=AppSettings.DEVICE
        )
        logger.info(f"Embedding 模型已加载，设备: {AppSettings.DEVICE}")

        # 加载 Reranker
        self.reranker = SentenceTransformerRerank(
            model=AppSettings.RERANKER_MODEL_PATH,
            top_n=AppSettings.RERANK_TOP_N,
            device=AppSettings.DEVICE
        )
        logger.info(f"Reranker 模型已加载，设备: {AppSettings.DEVICE}")

        # 设置全局 Embedding 模型
        Settings.embed_model = self.embed_model

        return self.embed_model, self.reranker

