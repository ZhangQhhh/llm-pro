# -*- coding: utf-8 -*-
"""
服务层模块包初始化
"""
from .llm_service import LLMService, CustomOpenAILike
from .embedding_service import EmbeddingService
from .knowledge_service import KnowledgeService
# IntentClassifier 已迁移到 core.intent_classifier（新版本，支持 LLM 意图分类）

__all__ = [
    'LLMService',
    'CustomOpenAILike',
    'EmbeddingService',
    'KnowledgeService',
]

