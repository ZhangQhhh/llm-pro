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
    #EMBED_MODEL_PATH = "/opt/rag_final_project/models/text2vec-base-chinese"
    #RERANKER_MODEL_PATH = "/opt/rag_final_project/models/bge-reranker-v2-m3"
    EMBED_MODEL_PATH = "/yuanjing/bge-large-zh-v1.5"
    RERANKER_MODEL_PATH = "/yuanjing/bge-reranker-large"
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
        },
        "deepseek-32b": {
            "api_base_url": "https://53.3.1.3:5001/openapi/v1",
            "access_token": "sk-dd997ba3a3804d468e4e7e493184c9af",
            "llm_model_name": "deepseek-r1-distill-qwen-32b"
        }
    }
    DEFAULT_LLM_ID = "qwen3-32b"

    # ==================== RAG 核心参数 ====================
    RETRIEVAL_TOP_K = 30
    RETRIEVAL_TOP_K_BM25 = 30  # BM25检索数量
    RERANK_TOP_N = 20  # 重排序后返回数量（适配三库检索30条策略）
    RERANKER_INPUT_TOP_N = 30  # 送入重排序的数量（三库检索最大30条）
    RETRIEVAL_SCORE_THRESHOLD = 0.2
    RERANK_SCORE_THRESHOLD = 0.2
    DEVICE = "npu" if NPU_AVAILABLE else "cpu"
    
    # RRF 融合权重配置
    RRF_K = 60.0  # RRF 平滑参数
    RRF_VECTOR_WEIGHT = 0.7  # 向量检索权重（0-1）
    RRF_BM25_WEIGHT = 0.3    # BM25 检索权重（0-1）

    # ==================== LLM 行为参数 ====================
    LLM_REQUEST_TIMEOUT = 1800.0
    LLM_CONTEXT_WINDOW = 32768
    LLM_MAX_TOKENS = 8192
    LLM_MAX_RETRIES = 2
    TEMPERATURE_DISASSEMBLY = 0.0
    TEMPERATURE_ANALYSIS_ON = 0.5
    TEMPERATURE_ANALYSIS_OFF = 0.0
    TEMPERATURE_REDUCTION = 0.0
    TOP_P = 0.95  # 采样 top_p（默认0.95）
    TOP_K = 20    # 采样 top_k（默认20）

    # Qdrant 配置
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "knowledge_base")

    # 对话管理配置
    CONVERSATION_COLLECTION = os.getenv("CONVERSATION_COLLECTION", "conversations")
    MAX_RECENT_TURNS = int(os.getenv("MAX_RECENT_TURNS", 6))  # 从3提升到6 - 保留最近6轮完整对话
    MAX_RELEVANT_TURNS = int(os.getenv("MAX_RELEVANT_TURNS", 3))  # 从2提升到3 - 检索3轮相关历史
    CONVERSATION_EXPIRE_DAYS = int(os.getenv("CONVERSATION_EXPIRE_DAYS", 7))  # 对话过期天数，默认7天

    # 新增：对话记忆优化配置
    MAX_HISTORY_TOKEN_BUDGET = int(os.getenv("MAX_HISTORY_TOKEN_BUDGET", 4000))  # 历史对话Token预算上限
    MAX_SUMMARY_TURNS = int(os.getenv("MAX_SUMMARY_TURNS", 12))  # 超过12轮才生成摘要
    SUMMARY_CACHE_TTL = int(os.getenv("SUMMARY_CACHE_TTL", 1800))  # 摘要缓存30分钟(秒)
    ENABLE_SMART_HISTORY_FILTER = os.getenv("ENABLE_SMART_HISTORY_FILTER", "true").lower() == "true"  # 启用智能历史筛选

    # 可选:内嵌模式路径(不使用 Docker 时启用) 现在用的是docker，用不到hhhhhhhhhhh
    # QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_data")

    # ==================== 免签知识库配置 ====================
    # 免签功能开关（默认关闭，不影响现有系统）
    ENABLE_VISA_FREE_FEATURE = os.getenv("ENABLE_VISA_FREE_FEATURE", "false").lower() == "true"
    
    # 免签知识库路径（完全独立的目录）
    VISA_FREE_KB_DIR = "/opt/rag_final_project/visa_free_knowledge_base"
    VISA_FREE_STORAGE_PATH = "/opt/rag_final_project/visa_free_storage"
    VISA_FREE_COLLECTION = "visa_free_kb"  # 独立的 Qdrant collection
    
    # 免签检索参数（独立配置，不影响通用库）
    VISA_FREE_RETRIEVAL_TOP_K = 30
    VISA_FREE_RETRIEVAL_TOP_K_BM25 = 30
    VISA_FREE_RERANK_TOP_N = 15
    
    # 意图分类器配置
    ENABLE_INTENT_CLASSIFIER = os.getenv("ENABLE_INTENT_CLASSIFIER", "false").lower() == "true"
    INTENT_CLASSIFIER_TIMEOUT = 5  # 意图分类超时时间（秒）
    INTENT_CLASSIFIER_LLM_ID = "qwen3-32b"  # 用于意图分类的LLM
    
    # InsertBlock 精准检索配置
    INSERTBLOCK_MAX_WORKERS = 10  # 并发处理的最大线程数（默认5，提高到10可加快处理速度）
    
    # 问题改写和独立重排序功能开关（需要先启用意图分类器）
    ENABLE_QUESTION_REWRITE = os.getenv("ENABLE_QUESTION_REWRITE", "false").lower() == "true"  # 默认关闭
    
    # 双库检索策略（当判断为混合问题时）
    DUAL_KB_STRATEGY = "adaptive"  # adaptive(自适应) 或 fixed(固定比例)
    VISA_FREE_RETRIEVAL_COUNT = 10  # 免签库取10条（三库检索时）
    GENERAL_RETRIEVAL_COUNT = 5     # 通用库取5条（保底）
    
    # ==================== 航司知识库配置 ====================
    # 航司功能开关（默认关闭）
    ENABLE_AIRLINE_FEATURE = os.getenv("ENABLE_AIRLINE_FEATURE", "false").lower() == "true"
    
    # 航司知识库路径（独立目录）
    AIRLINE_KB_DIR = "/opt/rag_final_project/airline_knowledge_base"
    AIRLINE_STORAGE_PATH = "/opt/rag_final_project/airline_storage"
    AIRLINE_COLLECTION = "airline_kb"  # 独立的 Qdrant collection
    
    # 航司检索参数
    AIRLINE_RETRIEVAL_TOP_K = 30
    AIRLINE_RETRIEVAL_TOP_K_BM25 = 30
    AIRLINE_RERANK_TOP_N = 20  # 适配三库检索30条策略
    AIRLINE_RETRIEVAL_COUNT = 10  # 航司库取10条（三库检索时）

    # ==================== 特殊规定配置 ====================
    # 特殊规定文件夹路径（直接从文件读取，不使用向量数据库）
    SPECIAL_RULES_DIR = "/opt/rag_final_project/special_rules"

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
