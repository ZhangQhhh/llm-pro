# -*- coding: utf-8 -*-
"""
LLM 封装层
提供统一的 LLM 调用接口，支持 Chat 和 Complete 模式
"""
from typing import Optional, List, Any
from utils.logger import logger


try:
    from llama_index.core.llms import ChatMessage, MessageRole
except ImportError:
    try:
        from llama_index.core.base.llms.types import ChatMessage, MessageRole
    except ImportError:
        ChatMessage = None
        MessageRole = None


class LLMStreamWrapper:
    """LLM 流式调用统一封装"""

    @staticmethod
    def stream(
        llm: Any,
        prompt: Optional[str] = None,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        assistant_context: Optional[str] = None,
        use_chat_mode: bool = True
    ):
        """
        统一的流式调用接口

        Args:
            llm: LLM 实例
            prompt: 完整 prompt（fallback 使用）
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            assistant_context: 助手上下文（RAG 内容）
            use_chat_mode: 是否使用 chat 模式

        Returns:
            流式响应生成器
        """
        use_chat = (
            use_chat_mode
            and ChatMessage is not None
            and hasattr(llm, 'stream_chat')
        )

        if use_chat:
            return LLMStreamWrapper._stream_chat(
                llm, system_prompt, user_prompt, assistant_context, prompt
            )
        else:
            return LLMStreamWrapper._stream_complete(
                llm, system_prompt, user_prompt, assistant_context, prompt
            )

    @staticmethod
    def _stream_chat(
        llm: Any,
        system_prompt: Optional[str],
        user_prompt: Optional[str],
        assistant_context: Optional[str],
        fallback_prompt: Optional[str]
    ):
        """Chat 模式流式调用"""
        if not user_prompt:
            user_prompt = fallback_prompt or ''
        if not system_prompt:
            system_prompt = "你是一个严谨且专业的大语言模型助手。"

        messages = [ChatMessage(role="system", content=system_prompt)]

        if assistant_context:
            messages.append(ChatMessage(role="assistant", content=assistant_context))

        messages.append(ChatMessage(role="user", content=user_prompt))

        try:
            return llm.stream_chat(messages)
        except Exception as e:
            logger.warning(f"stream_chat 失败，回退到 stream_complete: {e}")
            combined = system_prompt + "\n"
            if assistant_context:
                combined += assistant_context + "\n"
            combined += user_prompt
            return llm.stream_complete(fallback_prompt or combined)

    @staticmethod
    def _stream_complete(
        llm: Any,
        system_prompt: Optional[str],
        user_prompt: Optional[str],
        assistant_context: Optional[str],
        prompt: Optional[str]
    ):
        """Complete 模式流式调用"""
        combined = (system_prompt or '') + "\n"
        if assistant_context:
            combined += assistant_context + "\n"
        combined += (user_prompt or '')
        return llm.stream_complete(prompt or combined)

