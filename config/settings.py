# -*- coding: utf-8 -*-
"""
配置管理模块
集中管理所有系统配置参数
"""
import os
import logging
from typing import Dict, Any

# 检测 NPU 可用性
try:
    import torch
    import torch_npu
    NPU_AVAILABLE = torch.npu.is_available()
except ImportError:
    NPU_AVAILABLE = False


class Settings:
    """系统配置类"""

    # ==================== 路径配置 ====================
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    KNOWLEDGE_BASE_DIR = "/opt/rag_final_project/knowledge_base"
    EMBED_MODEL_PATH = "/opt/rag_final_project/models/text2vec-base-chinese"
    RERANKER_MODEL_PATH = "/opt/rag_final_project/models/bge-reranker-v2-m3"
    STORAGE_PATH = "/opt/rag_final_project/storage"
    LOG_DIR = "/opt/rag_final_project/qa_logs"

    # Prompt 配置文件候选路径 (修复: 去掉 cls 未定义的引用)
    PROMPT_CONFIG_CANDIDATES = [
        os.path.join(BASE_DIR, 'prompts.py'),            # Python 配置（优先）
        os.path.join(BASE_DIR, 'prompts.json'),          # JSON 配置（兼容旧版）
        os.path.join(BASE_DIR, '..', 'prompts.py'),      # 上一级 Python
        os.path.join(BASE_DIR, '..', 'prompts.json'),    # 上一级 JSON（兼容旧结构）
        "/opt/rag_final_project/prompts.py",             # 部署环境 Python
        "/opt/rag_final_project/prompts.json"            # 部署环境 JSON
    ]
    PROMPT_CONFIG_PATH = None

    # ==================== LLM 端点配置 ====================
    LLM_ENDPOINTS = {
        "qwen2025": {
            "api_base_url": "http://53.2.102.1:2025/v1",
            "access_token": "",
            "llm_model_name": "qwen3"
        },
        "qwen3-32b": {
            "api_base_url": "http://127.0.0.1:1025/v1",
            "access_token": "",
            "llm_model_name": "qwen3-32b"
        },
        "deepseek": {
            "api_base_url": "http://53.3.1.4:34567/v1",
            "access_token": "",
            "llm_model_name": "deepseek-r1"
        },
        "qwen3-14b-lora": {
            "api_base_url": "http://127.0.0.1:1035/v1",
            "access_token": "",
            "llm_model_name": "qwen3-14b-lora"
        }
    }
    DEFAULT_LLM_ID = "qwen3-32b"

    # ==================== RAG 核心参数 ====================
    RETRIEVAL_TOP_K = 30
    RERANK_TOP_N = 10
    RERANKER_INPUT_TOP_N = 20
    RETRIEVAL_SCORE_THRESHOLD = 0.2
    RERANK_SCORE_THRESHOLD = 0.2
    DEVICE = "npu" if NPU_AVAILABLE else "cpu"

    # ==================== LLM 行为参数 ====================
    LLM_REQUEST_TIMEOUT = 1800.0
    LLM_CONTEXT_WINDOW = 32768
    LLM_MAX_TOKENS = 8192
    LLM_MAX_RETRIES = 2
    TEMPERATURE_DISASSEMBLY = 0.0
    TEMPERATURE_ANALYSIS_ON = 0.3
    TEMPERATURE_ANALYSIS_OFF = 0.0
    TEMPERATURE_REDUCTION = 0.0
    TOP_P = 0.95  # 添加top_p参数，默认值0.95

    # Qdrant 配置
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "knowledge_base")

    # 对话管理配置
    CONVERSATION_COLLECTION = os.getenv("CONVERSATION_COLLECTION", "conversations")
    MAX_RECENT_TURNS = int(os.getenv("MAX_RECENT_TURNS", 3))  # 最近对话轮数
    MAX_RELEVANT_TURNS = int(os.getenv("MAX_RELEVANT_TURNS", 2))  # 相关对话轮数
    CONVERSATION_EXPIRE_DAYS = int(os.getenv("CONVERSATION_EXPIRE_DAYS", 7))  # 对话过期天数，默认7天

    # 可选:内嵌模式路径(不使用 Docker 时启用) 现在用的是docker，用不到hhhhhhhhhhh
    # QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_data")

    # ==================== 服务器配置 ====================
    # SERVER_HOST = "0.0.0.0"
    SERVER_HOST = "127.0.0.1" # 只能监听本机，通过nginx代理访问
    SERVER_PORT = 5000
    SERVER_DEBUG_MODE = False

    # ==================== 特性开关 ====================
    USE_CHAT_MODE = True  # 是否使用 ChatMessage (system/user) 结构化上下文模式

    # ==================== 文档切分配置 ====================
    CHUNK_CHAR_A = "--- 切分点 ---"
    CHUNK_CHAR_B = "|||"

    @classmethod
    def resolve_prompt_config_path(cls):
        """解析 Prompt 配置文件路径"""
        for candidate in cls.PROMPT_CONFIG_CANDIDATES:
            abs_path = os.path.abspath(candidate)
            if os.path.exists(abs_path):
                cls.PROMPT_CONFIG_PATH = abs_path
                return abs_path
        # 若都不存在，使用第一个作为期望路径
        cls.PROMPT_CONFIG_PATH = os.path.abspath(cls.PROMPT_CONFIG_CANDIDATES[0])
        logging.warning(f"未找到 prompts 配置文件，期望路径: {cls.PROMPT_CONFIG_PATH}")
        return cls.PROMPT_CONFIG_PATH

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """转换为字典格式（兼容旧代码）"""
        return {
            "knowledge_base_dir": cls.KNOWLEDGE_BASE_DIR,
            "embed_model_path": cls.EMBED_MODEL_PATH,
            "reranker_model_path": cls.RERANKER_MODEL_PATH,
            "storage_path": cls.STORAGE_PATH,
            "prompt_config_path": cls.PROMPT_CONFIG_PATH or cls.resolve_prompt_config_path(),
            "log_dir": cls.LOG_DIR,
            "llm_endpoints": cls.LLM_ENDPOINTS,
            "default_llm_id": cls.DEFAULT_LLM_ID,
            "retrieval_top_k": cls.RETRIEVAL_TOP_K,
            "rerank_top_n": cls.RERANK_TOP_N,
            "reranker_input_top_n": cls.RERANKER_INPUT_TOP_N,
            "retrieval_score_threshold": cls.RETRIEVAL_SCORE_THRESHOLD,
            "rerank_score_threshold": cls.RERANK_SCORE_THRESHOLD,
            "device": cls.DEVICE,
            "llm_request_timeout": cls.LLM_REQUEST_TIMEOUT,
            "llm_context_window": cls.LLM_CONTEXT_WINDOW,
            "llm_max_tokens": cls.LLM_MAX_TOKENS,
            "llm_max_retries": cls.LLM_MAX_RETRIES,
            "temperature_disassembly": cls.TEMPERATURE_DISASSEMBLY,
            "temperature_analysis_on": cls.TEMPERATURE_ANALYSIS_ON,
            "temperature_analysis_off": cls.TEMPERATURE_ANALYSIS_OFF,
            "temperature_reduction": cls.TEMPERATURE_REDUCTION,
            "top_p": cls.TOP_P,
            "server_host": cls.SERVER_HOST,
            "server_port": cls.SERVER_PORT,
            "server_debug_mode": cls.SERVER_DEBUG_MODE,
            "use_chat_mode": cls.USE_CHAT_MODE,
            "chunk_char_A": cls.CHUNK_CHAR_A,
            "chunk_char_B": cls.CHUNK_CHAR_B,
        }


# 自动解析 Prompt 配置路径
Settings.resolve_prompt_config_path()

# 导出配置实例
CONFIG = Settings.to_dict()
