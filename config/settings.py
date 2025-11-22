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
    RETRIEVAL_TOP_K_BM25 = 5  # BM25检索数量
    RERANK_TOP_N = 15  # 通用问题默认返回数量（可被前端参数覆盖）
    RERANKER_INPUT_TOP_N = 30  # 送入重排序的数量（三库检索最大30条）
    RETRIEVAL_SCORE_THRESHOLD = 0.2
    RERANK_SCORE_THRESHOLD = 0.2
    DEVICE = "npu" if NPU_AVAILABLE else "cpu"
    
    # RRF 融合权重配置
    #  修复：降低 RRF_K 使分数更合理（从 10.0 降到 5.0）
    # RRF 分数公式：1/(k+rank)，k 越小，排名差异影响越大，分数范围越大
    RRF_K = 5.0  # RRF 平滑参数（降低以增加排名差异影响，提高分数范围）
    RRF_VECTOR_WEIGHT = 0.7  # 向量检索权重（0-1）
    RRF_BM25_WEIGHT = 0.3    # BM25 检索权重（0-1）
    
    # 关键词显示配置
    MAX_DISPLAY_KEYWORDS = int(os.getenv("MAX_DISPLAY_KEYWORDS", "10"))  # 前端显示的最大关键词数量

    # 数据目录（用于构建索引）
    DATA_DIR = os.getenv("DATA_DIR", KNOWLEDGE_BASE_DIR)  # 默认使用知识库目录

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

    # —— Writer 用 Qdrant 集合命名 —— #
    WRITER_KB_COLLECTION = os.getenv("WRITER_KB_COLLECTION", "writer_kb_persist")
    # WRITER_SESSION_COLLECTION_PREFIX = os.getenv("WRITER_SESSION_COLLECTION_PREFIX", "writer_kb_session_")
    WRITER_SESSION_COLLECTION = os.getenv("WRITER_SESSION_COLLECTION", "writer_session_kb")
    # —— 会话集合持久化与过期策略 —— #
    WRITER_SESSION_PERSIST = bool(int(os.getenv("WRITER_SESSION_PERSIST", "1")))  # 1=持久化，0=仅内存
    WRITER_SESSION_TTL_HOURS = int(os.getenv("WRITER_SESSION_TTL_HOURS", "24"))  # 过期小时，0=不设置 TTL
    WRITER_KB_UPLOAD_PASSWORD = "147369"

    # ==================== 免签知识库配置 ====================
    # 免签功能开关（默认关闭，不影响现有系统）
    ENABLE_VISA_FREE_FEATURE = os.getenv("ENABLE_VISA_FREE_FEATURE", "false").lower() == "true"
    
    # 免签知识库路径（完全独立的目录）
    VISA_FREE_KB_DIR = "/opt/rag_final_project/visa_free_knowledge_base"
    VISA_FREE_STORAGE_PATH = "/opt/rag_final_project/visa_free_storage"
    VISA_FREE_COLLECTION = "visa_free_kb"  # 独立的 Qdrant collection
    
    # 免签检索参数（独立配置，不影响通用库）
    VISA_FREE_RETRIEVAL_TOP_K = 30
    VISA_FREE_RETRIEVAL_TOP_K_BM25 = 5
    VISA_FREE_RERANK_TOP_N = 15
    
    # 意图分类器配置
    ENABLE_INTENT_CLASSIFIER = os.getenv("ENABLE_INTENT_CLASSIFIER", "false").lower() == "true"
    INTENT_CLASSIFIER_TIMEOUT = 5  # 意图分类超时时间（秒）
    INTENT_CLASSIFIER_LLM_ID = "qwen3-32b"  # 用于意图分类的LLM
    
    # InsertBlock 精准检索配置
    INSERTBLOCK_MAX_WORKERS = 10  # 并发处理的最大线程数（默认5，提高到10可加快处理速度）
    
    # 数据趋势分析配置
    DATA_ANALYSIS_MAX_LENGTH = 250  # 分析摘要最大字数（默认250字）
    
    # 问题改写和独立重排序功能开关（需要先启用意图分类器）
    ENABLE_QUESTION_REWRITE = os.getenv("ENABLE_QUESTION_REWRITE", "false").lower() == "true"  # 默认关闭
    
    # 双库检索策略（当判断为混合问题时）
    DUAL_KB_STRATEGY = "adaptive"  # adaptive(自适应) 或 fixed(固定比例)
    
    # ==================== 多库检索数量配置 ====================
    # 各知识库单独检索数量（可通过环境变量配置）
    # 说明：这些参数控制从每个知识库中取多少条文档进行合并
    VISA_FREE_RETRIEVAL_COUNT = int(os.getenv("VISA_FREE_RETRIEVAL_COUNT", "10"))  # 免签库取10条
    GENERAL_RETRIEVAL_COUNT = int(os.getenv("GENERAL_RETRIEVAL_COUNT", "5"))       # 通用库取5条（保底）
    AIRLINE_RETRIEVAL_COUNT = int(os.getenv("AIRLINE_RETRIEVAL_COUNT", "10"))      # 航司库取10条
    
    # 多库检索最终返回数量（自动计算，不受前端参数控制）
    # 说明：这些数量是各库检索数量之和，表示合并去重后最终返回的文档总数
    # 
    # 1. visa_free 策略（免签库 + 通用库）
    #    最终返回 = 免签库10条 + 通用库5条 = 15条（包含两个库的文档总和）
    VISA_FREE_STRATEGY_RETURN_COUNT = VISA_FREE_RETRIEVAL_COUNT + GENERAL_RETRIEVAL_COUNT
    
    # 2. airline 策略（航司库 + 通用库）
    #    最终返回 = 航司库10条 + 通用库5条 = 15条（包含两个库的文档总和）
    AIRLINE_STRATEGY_RETURN_COUNT = AIRLINE_RETRIEVAL_COUNT + GENERAL_RETRIEVAL_COUNT
    
    # 3. airline_visa_free 策略（航司库 + 免签库 + 通用库）
    #    最终返回 = 航司库10条 + 免签库10条 + 通用库5条 = 25条（包含三个库的文档总和）
    AIRLINE_VISA_FREE_RETURN_COUNT = AIRLINE_RETRIEVAL_COUNT + VISA_FREE_RETRIEVAL_COUNT + GENERAL_RETRIEVAL_COUNT
    
    # ==================== 通用知识库B配置（12367专用）====================
    # 通用知识库B开关（默认关闭）
    ENABLE_GENERAL_KB_B = os.getenv("ENABLE_GENERAL_KB_B", "false").lower() == "true"
    
    # 通用知识库B路径（独立目录）
    GENERAL_KB_B_DIR = "/opt/rag_final_project/general_knowledge_base_b"
    GENERAL_KB_B_STORAGE_PATH = "/opt/rag_final_project/general_kb_b_storage"
    GENERAL_KB_B_COLLECTION = "general_kb_b"  # 独立的 Qdrant collection
    
    # 通用知识库B检索参数（与通用库A相同）
    GENERAL_KB_B_RETRIEVAL_TOP_K = RETRIEVAL_TOP_K
    GENERAL_KB_B_RETRIEVAL_TOP_K_BM25 = RETRIEVAL_TOP_K_BM25
    GENERAL_KB_B_RERANK_TOP_N = RERANK_TOP_N
    
    # ==================== 航司知识库配置 ====================
    # 航司功能开关（默认关闭）
    ENABLE_AIRLINE_FEATURE = os.getenv("ENABLE_AIRLINE_FEATURE", "false").lower() == "true"
    
    # 航司知识库路径（独立目录）
    AIRLINE_KB_DIR = "/opt/rag_final_project/airline_knowledge_base"
    AIRLINE_STORAGE_PATH = "/opt/rag_final_project/airline_storage"
    AIRLINE_COLLECTION = "airline_kb"  # 独立的 Qdrant collection
    
    # 航司检索参数
    AIRLINE_RETRIEVAL_TOP_K = 30
    AIRLINE_RETRIEVAL_TOP_K_BM25 = 5
    AIRLINE_RERANK_TOP_N = 20  # 适配三库检索30条策略

    # ==================== 隐藏知识库配置 ====================
    # 隐藏知识库功能开关（默认关闭）
    # 用途：题库等需要提升准确率但不暴露来源的内容
    ENABLE_HIDDEN_KB_FEATURE = os.getenv("ENABLE_HIDDEN_KB_FEATURE", "false").lower() == "true"
    
    # 隐藏知识库路径（独立目录）
    HIDDEN_KB_DIR = "/opt/rag_final_project/hidden_knowledge_base"
    HIDDEN_KB_STORAGE_PATH = "/opt/rag_final_project/hidden_storage"
    HIDDEN_KB_COLLECTION = "hidden_kb"  # 独立的 Qdrant collection
    
    # 隐藏知识库检索参数
    HIDDEN_KB_RETRIEVAL_TOP_K = 30  # 初始检索数量（向量检索）
    HIDDEN_KB_RETRIEVAL_TOP_K_BM25 = 5  # BM25检索数量
    HIDDEN_KB_RERANK_TOP_N = 10  # 送入重排序的数量（从混合检索结果中取前N条）
    HIDDEN_KB_RETRIEVAL_COUNT = 5  # 最终注入上下文的数量（从重排序结果中取前N条）
    
    # 隐藏知识库行为配置
    HIDDEN_KB_INJECT_MODE = os.getenv("HIDDEN_KB_INJECT_MODE", "silent")  # silent: 完全隐藏 | visible: 显示来源（调试用）
    HIDDEN_KB_MIN_SCORE = float(os.getenv("HIDDEN_KB_MIN_SCORE", "0.3"))  # 最低分数阈值（Reranker分数，通常0.3-0.9）

    # ==================== 特殊规定配置 ====================
    # 特殊规定文件夹路径（直接从文件读取，不使用向量数据库）
    SPECIAL_RULES_DIR = "/opt/rag_final_project/special_rules"

    # ==================== 子问题分解配置 ====================
    # 子问题分解功能开关（默认关闭，插件式设计）
    ENABLE_SUBQUESTION_DECOMPOSITION = os.getenv("ENABLE_SUBQUESTION_DECOMPOSITION", "false").lower() == "true"
    
    # 子问题分解引擎选择：custom（自定义）或 llamaindex（LlamaIndex原生）
    SUBQUESTION_ENGINE_TYPE = os.getenv("SUBQUESTION_ENGINE_TYPE", "custom")  # custom 或 llamaindex
    
    # 是否使用LLM判断是否需要分解（仅对custom引擎有效）
    # True: LLM判断是否分解（智能模式）
    # False: 跳过判断，直接分解所有问题（强制分解模式）
    SUBQUESTION_USE_LLM_JUDGE = os.getenv("SUBQUESTION_USE_LLM_JUDGE", "true").lower() == "true"
    
    # 子问题分解参数
    SUBQUESTION_MAX_DEPTH = int(os.getenv("SUBQUESTION_MAX_DEPTH", "3"))  # 最大子问题数量
    SUBQUESTION_MIN_SCORE = float(os.getenv("SUBQUESTION_MIN_SCORE", "0.3"))  # 子问题检索最低分数阈值
    SUBQUESTION_COMPLEXITY_THRESHOLD = int(os.getenv("SUBQUESTION_COMPLEXITY_THRESHOLD", "50"))  # 触发分解的最小查询长度
    SUBQUESTION_DECOMP_LLM_ID = os.getenv("SUBQUESTION_DECOMP_LLM_ID", "qwen3-32b")  # 用于子问题分解的LLM
    SUBQUESTION_DECOMP_TIMEOUT = int(os.getenv("SUBQUESTION_DECOMP_TIMEOUT", "10"))  # 分解超时时间（秒）
    SUBQUESTION_SYNTHESIS_TIMEOUT = int(os.getenv("SUBQUESTION_SYNTHESIS_TIMEOUT", "30"))  # 答案合成超时时间（秒）
    SUBQUESTION_ENABLE_ENTITY_CHECK = os.getenv("SUBQUESTION_ENABLE_ENTITY_CHECK", "true").lower() == "true"  # 启用命名实体检测
    SUBQUESTION_MIN_ENTITIES = int(os.getenv("SUBQUESTION_MIN_ENTITIES", "2"))  # 触发分解的最小实体数
    
    # 对话历史压缩配置（用于多轮场景）
    SUBQUESTION_HISTORY_COMPRESS_TURNS = int(os.getenv("SUBQUESTION_HISTORY_COMPRESS_TURNS", "5"))  # 压缩最近N轮对话
    SUBQUESTION_HISTORY_MAX_TOKENS = int(os.getenv("SUBQUESTION_HISTORY_MAX_TOKENS", "500"))  # 历史摘要最大token数
    
    # 健康度指标配置
    SUBQUESTION_MAX_EMPTY_RESULTS = int(os.getenv("SUBQUESTION_MAX_EMPTY_RESULTS", "2"))  # 允许的最大空结果子问题数
    SUBQUESTION_FALLBACK_ON_ERROR = os.getenv("SUBQUESTION_FALLBACK_ON_ERROR", "true").lower() == "true"  # 错误时回退到标准检索

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

    # ——  各源独立检索 top_k —— #
    WRITER_SESSION_SIM_TOP_K = 20  # 会话：向量检索 top_k
    WRITER_SESSION_BM25_TOP_K = 20  # 会话：BM25 top_k
    WRITER_KB_SIM_TOP_K = 20  # KB：向量检索 top_k
    WRITER_KB_BM25_TOP_K = 20  # KB：BM25 top_k

    # —— 来源配额 & 合并后的最终返回 —— #
    WRITER_SESSION_RETURN_K = 20
    WRITER_KB_RETURN_K = 20
    WRITER_MERGED_RETURN_K = 30
    WRITER_RERANK_TOP_N = 15

    # —— RRF 平滑参数 —— #
    WRITER_COMBINE_RRF_K = 60.0

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
            "data_dir": cls.DATA_DIR,
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
