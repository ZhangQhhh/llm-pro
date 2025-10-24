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
        use_chat_mode: bool = True,
        enable_thinking: bool = False
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
            enable_thinking: 是否启用思考模式（通过提示词控制，而非 API 原生参数）

        Returns:
            流式响应生成器

        Note:
            enable_thinking 参数会传递到底层但会在 llm_service.py 中被过滤掉，
            实际的思考模式通过提示词内容来控制。
        """
        use_chat = (
            use_chat_mode
            and ChatMessage is not None
            and hasattr(llm, 'stream_chat')
        )

        if use_chat:
            return LLMStreamWrapper._stream_chat(
                llm, system_prompt, user_prompt, assistant_context, prompt, enable_thinking
            )
        else:
            return LLMStreamWrapper._stream_complete(
                llm, system_prompt, user_prompt, assistant_context, prompt, enable_thinking
            )

    @staticmethod
    def stream_chat(llm: Any, messages: List[Any]):
        """
        多轮对话模式的流式调用接口

        Args:
            llm: LLM 实例
            messages: ChatMessage 列表或字典列表

        Returns:
            流式响应生成器
        """
        try:
            # 如果 LLM 支持 stream_chat，将字典转换为 ChatMessage 对象
            if hasattr(llm, 'stream_chat'):
                # 检查 messages 是否需要转换
                if messages and isinstance(messages[0], dict):
                    # 字典格式，需要转换为 ChatMessage
                    if ChatMessage is not None:
                        chat_messages = []
                        for msg in messages:
                            role = msg.get('role', 'user')
                            content = msg.get('content', '')
                            chat_messages.append(ChatMessage(role=role, content=content))
                        return llm.stream_chat(chat_messages)
                    else:
                        # ChatMessage 未导入，回退到 stream_complete
                        logger.warning("ChatMessage 未导入，回退到 stream_complete")
                        prompt_parts = []
                        for msg in messages:
                            role = msg.get('role', 'user')
                            content = msg.get('content', '')
                            if role == 'system':
                                prompt_parts.append(f"系统: {content}")
                            elif role == 'user':
                                prompt_parts.append(f"用户: {content}")
                            elif role == 'assistant':
                                prompt_parts.append(f"助手: {content}")
                        combined_prompt = "\n".join(prompt_parts)
                        return llm.stream_complete(combined_prompt)
                else:
                    # 已经是 ChatMessage 对象，直接使用
                    return llm.stream_chat(messages)
            else:
                # 如果不支持 stream_chat，回退到 stream_complete
                logger.warning(f"LLM 不支持 stream_chat，尝试使用 stream_complete")

                # 将 messages 转换为单个 prompt
                prompt_parts = []
                for msg in messages:
                    # 兼容字典和对象两种格式
                    if isinstance(msg, dict):
                        role = msg.get('role', 'user')
                        content = msg.get('content', '')
                    else:
                        role = getattr(msg, 'role', 'user')
                        content = getattr(msg, 'content', '')

                    if role == 'system':
                        prompt_parts.append(f"系统: {content}")
                    elif role == 'user':
                        prompt_parts.append(f"用户: {content}")
                    elif role == 'assistant':
                        prompt_parts.append(f"助手: {content}")

                combined_prompt = "\n".join(prompt_parts)
                return llm.stream_complete(combined_prompt)

        except Exception as e:
            logger.error(f"stream_chat 调用失败: {e}", exc_info=True)
            raise

    @staticmethod
    def _stream_chat(
        llm: Any,
        system_prompt: Optional[str],
        user_prompt: Optional[str],
        assistant_context: Optional[str],
        fallback_prompt: Optional[str],
        enable_thinking: bool = False
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
            # 不传递 enable_thinking 参数，该参数仅用于上层逻辑控制
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
        prompt: Optional[str],
        enable_thinking: bool = False
    ):
        """Complete 模式流式调用"""
        combined = (system_prompt or '') + "\n"
        if assistant_context:
            combined += assistant_context + "\n"
        combined += (user_prompt or '')
        return llm.stream_complete(prompt or combined)
