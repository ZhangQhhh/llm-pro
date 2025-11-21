# -*- coding: utf-8 -*-
"""
LLM 流式输出解析工具
处理 LLM 流式响应的解析，支持思考模式和普通模式
"""
from typing import Generator, Tuple, Any
from utils import logger, clean_for_sse_text


def _remove_code_blocks(text: str) -> str:
    """
    移除文本中的所有代码块符号（包括各种变体）
    
    Args:
        text: 输入文本
        
    Returns:
        移除代码块符号后的文本
    """
    import re
    
    # 移除所有可能的代码块符号变体
    cleaned = text
    
    # 1. 先用正则处理连续反引号（3个或以上）
    cleaned = re.sub(r'`{3,}', '', cleaned)  # 半角连续反引号
    cleaned = re.sub(r'`{3,}', '', cleaned)  # 全角连续反引号
    
    # 2. 半角反引号（标准）
    cleaned = cleaned.replace('```', '')
    
    # 3. 全角反引号（中文输入法）
    cleaned = cleaned.replace('```', '')
    
    # 4. 混合反引号
    cleaned = cleaned.replace('``', '')
    cleaned = cleaned.replace('``', '')
    
    return cleaned


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
    delta_count = 0
    try:
        for delta in response_stream:
            delta_count += 1
            # 优先检查阿里云原生的 reasoning_content 字段
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
                has_reasoning_content = True
                reasoning_text = delta.reasoning_content
                if reasoning_text:
                    reasoning_buffer += reasoning_text
                    
                    # DeepSeek-R1 可能一次性返回大块内容，需要分段输出
                    # 按换行符分割并逐段输出
                    while '\n' in reasoning_buffer or len(reasoning_buffer) >= 100:
                        if '\n' in reasoning_buffer:
                            # 找到第一个换行符的位置
                            idx = reasoning_buffer.index('\n')
                            chunk = reasoning_buffer[:idx + 1]  # 包含换行符
                            reasoning_buffer = reasoning_buffer[idx + 1:]
                        else:
                            # 没有换行符但内容很长，按100字符分段
                            chunk = reasoning_buffer[:100]
                            reasoning_buffer = reasoning_buffer[100:]
                        
                        if chunk:
                            think_output_count += 1
                            output = ('THINK', clean_for_sse_text(chunk))
                            yield output

            # 检查正常回答内容（无论是否有 reasoning_content，都要处理）
            if hasattr(delta, 'content') and delta.content is not None:
                content_text = delta.content
                if content_text:
                    content_buffer += content_text
                    
                    # 同样处理大块内容，按换行符或100字符分段输出
                    while '\n' in content_buffer or len(content_buffer) >= 100:
                        if '\n' in content_buffer:
                            idx = content_buffer.index('\n')
                            chunk = content_buffer[:idx + 1]
                            content_buffer = content_buffer[idx + 1:]
                        else:
                            chunk = content_buffer[:100]
                            content_buffer = content_buffer[100:]
                        
                        if chunk:
                            # 过滤代码块符号（在发送前过滤）
                            cleaned_content = _remove_code_blocks(chunk)
                            content_output_count += 1
                            output = ('CONTENT', clean_for_sse_text(cleaned_content))
                            yield output
                
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

                # 在思考区域且buffer足够长时，流式输出思考内容（降低阈值）
                if in_thinking_section and not thinking_complete:
                    # 如果包含换行符，立即发送
                    if '\n' in buffer or len(buffer) > 10:
                        think_output_count += 1
                        output = ('THINK', clean_for_sse_text(buffer))
                        yield output
                        buffer = ""
                # 思考完成后，流式输出正文内容
                elif thinking_complete and len(buffer) > 0:
                    # 如果包含换行符，立即发送
                    if '\n' in buffer or len(buffer) > 5:
                        # 只清理开头的标记符号（冒号等），保留换行符
                        cleaned_buffer = buffer.lstrip(':：')
                        if cleaned_buffer:
                            content_output_count += 1
                            output = ('CONTENT', clean_for_sse_text(cleaned_buffer))
                            yield output
                        buffer = ""

    except Exception as e:
        logger.error(f"流式解析异常 (思考模式): {e} | 已处理 {delta_count} 个 delta", exc_info=True)
        # 输出剩余buffer（如果有），确保前端能收到已接收的内容
        if reasoning_buffer:
            yield ('THINK', clean_for_sse_text(reasoning_buffer))
        if content_buffer:
            cleaned = _remove_code_blocks(content_buffer)
            yield ('CONTENT', clean_for_sse_text(cleaned))
        if buffer:
            cleaned = _remove_code_blocks(buffer)
            yield ('CONTENT', clean_for_sse_text(cleaned))
    
    # 输出剩余的buffer（正常情况）
    # 1. 原生格式的剩余内容
    if has_reasoning_content:
        if reasoning_buffer:
            think_output_count += 1
            output = ('THINK', clean_for_sse_text(reasoning_buffer))
            yield output
        if content_buffer:
            content_output_count += 1
            cleaned = _remove_code_blocks(content_buffer)
            output = ('CONTENT', clean_for_sse_text(cleaned))
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
            cleaned_buffer = _remove_code_blocks(cleaned_buffer)
            if cleaned_buffer:
                content_output_count += 1
                output = ('CONTENT', clean_for_sse_text(cleaned_buffer))
                yield output
    
    # 输出处理统计（仅在DEBUG模式下）
    if logger.isEnabledFor(10):  # DEBUG level
        logger.debug(
            f"思考模式处理完成，共处理 {delta_count} 个 delta 块 | "
            f"THINK输出: {think_output_count} 次 | CONTENT输出: {content_output_count} 次 | "
            f"模式: {'原生reasoning_content' if has_reasoning_content else '文本标记'}"
        )


def parse_normal_stream(response_stream: Any) -> Generator[Tuple[str, str], None, None]:
    """
    解析普通模式的 LLM 流式输出（不分离思考内容）
    
    Args:
        response_stream: LLM 流式响应对象
        
    Yields:
        (消息类型, 内容) 元组，类型始终为 'CONTENT'
    """
    buffer = ""
    delta_count = 0
    try:
        for delta in response_stream:
            delta_count += 1
            # 获取文本内容
            text = _extract_delta_text(delta)

            if text:
                buffer += text
                # 智能发送策略：
                # 1. 遇到换行符立即发送（保持换行的及时性）
                # 2. 或者 buffer 达到 5 个字符发送（更流畅）
                if '\n' in buffer or len(buffer) >= 5:
                    yield ('CONTENT', clean_for_sse_text(buffer))
                    buffer = ""
    
    except Exception as e:
        logger.error(f"流式解析异常 (普通模式): {e} | 已处理 {delta_count} 个 delta", exc_info=True)
        # 输出剩余buffer（如果有）
        if buffer:
            cleaned = _remove_code_blocks(buffer)
            yield ('CONTENT', clean_for_sse_text(cleaned))
    
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
