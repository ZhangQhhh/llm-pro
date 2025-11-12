# -*- coding: utf-8 -*-
"""
LLM 服务层
负责 LLM 客户端的初始化和管理
"""
import httpx
from typing import Dict, Any
from llama_index.llms.openai import OpenAI
from llama_index.core.llms import LLMMetadata
from config import Settings
from utils.logger import logger


class CustomOpenAILike(OpenAI):
    """自定义 OpenAI 兼容 LLM 客户端"""

    # 使用类变量存储所有实例的思考模式设置（避免 Pydantic 验证错误）
    _thinking_modes: Dict[int, bool] = {}
    
    def __init__(self, *args, **kwargs):
        """初始化时设置 default_headers 来传递 enable_thinking"""
        super().__init__(*args, **kwargs)
        # 🔥 关键修复：为每个实例设置默认的思考模式为 False
        self._thinking_modes[id(self)] = False
        # 尝试在初始化时就设置 extra_body（如果 OpenAI SDK 支持）
        logger.info(f"CustomOpenAILike 初始化完成，模型: {kwargs.get('model')}, 默认 enable_thinking=False")

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=Settings.LLM_CONTEXT_WINDOW,
            num_output=Settings.LLM_MAX_TOKENS,
            is_chat_model=True,
            model_name=self.model,
        )

    def _get_enable_thinking(self) -> bool:
        """获取当前实例的思考模式设置"""
        return self._thinking_modes.get(id(self), False)

    def _set_enable_thinking(self, value: bool):
        """设置当前实例的思考模式"""
        self._thinking_modes[id(self)] = value

    def _get_model_kwargs(self, **kwargs: Any) -> Dict[str, Any]:
        """
        拦截并处理 enable_thinking 参数
        这个方法在 OpenAI 基类中被调用，用于准备模型参数
        """
        # 提取 enable_thinking 参数
        enable_thinking = kwargs.pop("enable_thinking", None)
        if enable_thinking is not None:
            self._set_enable_thinking(enable_thinking)
            logger.info(f"✓ 思考模式已设置: enable_thinking={enable_thinking}")

        # 调用父类方法
        if hasattr(super(), '_get_model_kwargs'):
            return super()._get_model_kwargs(**kwargs)
        return {}

    def _get_completion_kwargs(self, **kwargs: Any) -> Dict[str, Any]:
        """重写以强制设置 max_tokens、top_p 并移除 stop 参数，支持 enable_thinking"""
        # 先提取 enable_thinking，避免传递给父类
        enable_thinking = kwargs.pop("enable_thinking", None)
        if enable_thinking is not None:
            self._set_enable_thinking(enable_thinking)

        completion_kwargs = super()._get_completion_kwargs(**kwargs)
        completion_kwargs["max_tokens"] = Settings.LLM_MAX_TOKENS
        completion_kwargs["top_p"] = Settings.TOP_P
        completion_kwargs["top_k"] = Settings.TOP_K
        completion_kwargs.pop("stop", None)

        # 获取当前实例的思考模式设置
        current_enable_thinking = self._get_enable_thinking()

        # 通过 additional_kwargs 或 extra_body 传递 enable_thinking
        # 注意：始终传递该参数（True 或 False），以明确告诉大模型是否开启思考
        # 尝试使用 additional_kwargs（llama-index 的方式）
        if "additional_kwargs" not in completion_kwargs:
            completion_kwargs["additional_kwargs"] = {}
        completion_kwargs["additional_kwargs"]["enable_thinking"] = current_enable_thinking

        # 同时尝试 extra_body（OpenAI SDK 1.0+ 的方式）
        if "extra_body" not in completion_kwargs:
            completion_kwargs["extra_body"] = {}
        completion_kwargs["extra_body"]["enable_thinking"] = current_enable_thinking

        logger.info(f"✓ 已将 enable_thinking={current_enable_thinking} 添加到请求参数")

        return completion_kwargs

    def _get_chat_kwargs(self, **kwargs: Any) -> Dict[str, Any]:
        """重写以强制设置 max_tokens、top_p 并移除 stop 参数，支持 enable_thinking"""
        # 先提取 enable_thinking，避免传递给父类
        enable_thinking = kwargs.pop("enable_thinking", None)
        if enable_thinking is not None:
            self._set_enable_thinking(enable_thinking)

        chat_kwargs = super()._get_chat_kwargs(**kwargs)
        chat_kwargs["max_tokens"] = Settings.LLM_MAX_TOKENS
        chat_kwargs["top_p"] = Settings.TOP_P
        chat_kwargs["top_k"] = Settings.TOP_K
        chat_kwargs.pop("stop", None)

        # 获取当前实例的思考模式设置
        current_enable_thinking = self._get_enable_thinking()

        # 通过 additional_kwargs 或 extra_body 传递 enable_thinking
        # 注意：始终传递该参数（True 或 False），以明确告诉大模型是否开启思考
        # 尝试使用 additional_kwargs（llama-index 的方式）
        if "additional_kwargs" not in chat_kwargs:
            chat_kwargs["additional_kwargs"] = {}
        chat_kwargs["additional_kwargs"]["enable_thinking"] = current_enable_thinking

        # 同时尝试 extra_body（OpenAI SDK 1.0+ 的方式）
        if "extra_body" not in chat_kwargs:
            chat_kwargs["extra_body"] = {}
        chat_kwargs["extra_body"]["enable_thinking"] = current_enable_thinking

        logger.info(f"✓ 已将 enable_thinking={current_enable_thinking} 添加到请求参数")

        return chat_kwargs


class LLMService:
    """LLM 服务管理器"""

    def __init__(self):
        self.clients: Dict[str, CustomOpenAILike] = {}
        self.http_client = None

    def initialize(self) -> Dict[str, CustomOpenAILike]:
        """
        初始化所有 LLM 客户端

        Returns:
            模型 ID 到 LLM 客户端的映射
        """
        logger.info("初始化 LLM 客户端...")

        self.http_client = httpx.Client(
            verify=False,
            timeout=Settings.LLM_REQUEST_TIMEOUT
        )

        for model_id, config in Settings.LLM_ENDPOINTS.items():
            logger.info(
                f"创建模型客户端: '{model_id}' "
                f"(API: {config['api_base_url']})"
            )

            api_key = config.get("access_token") or "not-needed"

            llm_client = CustomOpenAILike(
                model=config["llm_model_name"],
                api_key=api_key,
                api_base=config["api_base_url"],
                http_client=self.http_client,
                is_chat_model=True,
                context_window=Settings.LLM_CONTEXT_WINDOW
            )

            self.clients[model_id] = llm_client
            logger.info(
                f"模型 '{model_id}' 上下文窗口: "
                f"{Settings.LLM_CONTEXT_WINDOW}"
            )

        logger.info(f"成功初始化 {len(self.clients)} 个 LLM 客户端")
        return self.clients

    def get_client(self, model_id: str) -> CustomOpenAILike:
        """
        获取指定的 LLM 客户端

        Args:
            model_id: 模型 ID

        Returns:
            LLM 客户端实例

        Raises:
            KeyError: 如果模型 ID 不存在
        """
        if model_id not in self.clients:
            logger.warning(
                f"请求的模型 '{model_id}' 不存在，"
                f"使用默认模型 '{Settings.DEFAULT_LLM_ID}'"
            )
            model_id = Settings.DEFAULT_LLM_ID

        return self.clients[model_id]
