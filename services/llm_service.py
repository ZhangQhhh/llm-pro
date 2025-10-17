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

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=Settings.LLM_CONTEXT_WINDOW,
            num_output=Settings.LLM_MAX_TOKENS,
            is_chat_model=True,
            model_name=self.model,
        )

    def _get_completion_kwargs(self, **kwargs: Any) -> Dict[str, Any]:
        """重写以强制设置 max_tokens、top_p 并移除 stop 参数"""
        completion_kwargs = super()._get_completion_kwargs(**kwargs)
        completion_kwargs["max_tokens"] = Settings.LLM_MAX_TOKENS
        completion_kwargs["top_p"] = Settings.TOP_P
        completion_kwargs.pop("stop", None)
        return completion_kwargs

    def _get_chat_kwargs(self, **kwargs: Any) -> Dict[str, Any]:
        """重写以强制设置 max_tokens、top_p 并移除 stop 参数"""
        chat_kwargs = super()._get_chat_kwargs(**kwargs)
        chat_kwargs["max_tokens"] = Settings.LLM_MAX_TOKENS
        chat_kwargs["top_p"] = Settings.TOP_P
        chat_kwargs.pop("stop", None)
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
