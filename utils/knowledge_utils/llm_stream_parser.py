# -*- coding: utf-8 -*-
"""
LLM 流式输出解析工具
处理 LLM 流式响应的解析，支持思考模式和普通模式
"""
from typing import Generator, Tuple, Any
from utils import logger, clean_for_sse_text


def parse_thinking_stream(response_stream: Any) -> Generator[Tuple[str, str], None, None]:
    """
    解析启用思考模式的 LLM 流式输出
    
    支持两种思考模式：
    1. 阿里云原生 reasoning_content 字段（推荐）
    2. 文本标记方式（兼容其他模型）
    
    Args:
        response_stream: LLM 流式响应对象
        
    Yields:
        (消息类型, 内容) 元组，类型为 'THINK' 或 'CONTENT'
    """
    buffer = ""
    in_thinking_section = False
    thinking_complete = False
    has_reasoning_content = False  # 标记是否检测到原生 reasoning_content
    think_output_count = 0
    content_output_count = 0
    
    # 用于累积原生格式的内容
    reasoning_buffer = ""
    content_buffer = ""

    for delta in response_stream:
        # 优先检查阿里云原生的 reasoning_content 字段
        if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
            has_reasoning_content = True
            reasoning_text = delta.reasoning_content
            if reasoning_text:
                reasoning_buffer += reasoning_text
                # 累积到一定长度后再发送
                if len(reasoning_buffer) >= 10:
                    think_output_count += 1
                    output = ('THINK', clean_for_sse_text(reasoning_buffer))
                    yield output
                    reasoning_buffer = ""

        # 检查正常回答内容（无论是否有 reasoning_content，都要处理）
        if hasattr(delta, 'content') and delta.content is not None:
            content_text = delta.content
            if content_text:
                content_buffer += content_text
                # 累积到一定长度后再发送
                if len(content_buffer) >= 10:
                    content_output_count += 1
                    output = ('CONTENT', clean_for_sse_text(content_buffer))
                    yield output
                    content_buffer = ""
            # 如果有 reasoning_content 且已处理了 content，则跳过后续的文本标记解析
            if has_reasoning_content:
                continue

        # 如果没有 reasoning_content 字段，使用文本标记方式（兼容模式）
        if not has_reasoning_content:
            # 获取文本内容
            token = _extract_delta_text(delta)
            if not token:
                continue

            buffer += token

            # 检测思考部分的开始和结束标记
            if not thinking_complete:
                # 检查是否进入思考区域
                if not in_thinking_section:
                    in_thinking_section = _detect_thinking_start(buffer)

                # 检测思考结束的标记
                if in_thinking_section:
                    thinking_complete, think_content, buffer = _detect_thinking_end(buffer)
                    if thinking_complete and think_content:
                        think_output_count += 1
                        output = ('THINK', clean_for_sse_text(think_content))
                        yield output

            # 在思考区域且buffer足够长时，流式输出思考内容
            if in_thinking_section and not thinking_complete and len(buffer) > 20:
                think_output_count += 1
                output = ('THINK', clean_for_sse_text(buffer))
                yield output
                buffer = ""
            # 思考完成后，流式输出正文内容
            elif thinking_complete and len(buffer) > 0:
                # 只清理开头的标记符号（冒号等），保留换行符
                cleaned_buffer = buffer.lstrip(':：')
                if cleaned_buffer:
                    content_output_count += 1
                    output = ('CONTENT', clean_for_sse_text(cleaned_buffer))
                    yield output
                buffer = ""

    # 输出剩余的buffer
    # 1. 原生格式的剩余内容
    if has_reasoning_content:
        if reasoning_buffer:
            think_output_count += 1
            output = ('THINK', clean_for_sse_text(reasoning_buffer))
            yield output
        if content_buffer:
            content_output_count += 1
            output = ('CONTENT', clean_for_sse_text(content_buffer))
            yield output
    # 2. 文本标记模式的剩余内容
    elif buffer:
        if in_thinking_section and not thinking_complete:
            # 如果思考区域未完成，剩余内容作为思考输出
            think_output_count += 1
            output = ('THINK', clean_for_sse_text(buffer))
            yield output
        else:
            # 否则作为正文输出，只清理开头的标记符号，保留换行符
            cleaned_buffer = buffer.lstrip(':：')
            if cleaned_buffer:
                content_output_count += 1
                output = ('CONTENT', clean_for_sse_text(cleaned_buffer))
                yield output


def parse_normal_stream(response_stream: Any) -> Generator[Tuple[str, str], None, None]:
    """
    解析普通模式的 LLM 流式输出（不分离思考内容）
    
    Args:
        response_stream: LLM 流式响应对象
        
    Yields:
        (消息类型, 内容) 元组，类型始终为 'CONTENT'
    """
    buffer = ""
    for delta in response_stream:
        # 获取文本内容
        text = _extract_delta_text(delta)

        if text:
            buffer += text
            # 智能发送策略：
            # 1. 遇到换行符立即发送（保持换行的及时性）
            # 2. 或者 buffer 达到 20 个字符发送（平衡性能）
            if '\n' in buffer or len(buffer) >= 20:
                yield ('CONTENT', clean_for_sse_text(buffer))
                buffer = ""
    
    # 发送剩余内容
    if buffer:
        yield ('CONTENT', clean_for_sse_text(buffer))


def _extract_delta_text(delta: Any) -> str:
    """
    从 delta 对象中提取文本内容
    
    Args:
        delta: LLM 流式响应的单个 delta 对象
        
    Returns:
        提取的文本内容
    """
    if hasattr(delta, 'delta'):
        return delta.delta
    elif hasattr(delta, 'text'):
        return delta.text
    elif hasattr(delta, 'content'):
        return delta.content
    else:
        return str(delta) if delta else ''


def _detect_thinking_start(buffer: str) -> bool:
    """
    检测思考开始标记
    
    Args:
        buffer: 当前缓冲区内容
        
    Returns:
        是否检测到思考开始标记
    """
    thinking_markers = [
        '【咨询解析】', '第一部分：咨询解析', '第一部分:咨询解析',
        '<think>', '## 思考过程', '## 分析过程',
        '关键实体', 'Key Entities', '1. 关键实体'
    ]

    for marker in thinking_markers:
        if marker in buffer:
            logger.info(f"检测到思考开始标记: {marker}")
            return True
    
    return False


def _detect_thinking_end(buffer: str) -> Tuple[bool, str, str]:
    """
    检测思考结束标记
    
    Args:
        buffer: 当前缓冲区内容
        
    Returns:
        (是否完成, 思考内容, 剩余buffer)
    """
    end_markers = [
        '【综合解答】', '第二部分：综合解答', '第二部分:综合解答',
        '</think>', '## 最终答案', '## 回答'
    ]

    for marker in end_markers:
        if marker in buffer:
            # 输出思考内容（不包含结束标记）
            idx = buffer.index(marker)
            think_content = buffer[:idx] if idx > 0 else ""
            # 跳过标记本身，只保留标记之后的内容
            remaining_buffer = buffer[idx + len(marker):]
            return True, think_content, remaining_buffer
    
    return False, "", buffer
