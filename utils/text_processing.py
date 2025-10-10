# -*- coding: utf-8 -*-
"""
文本处理工具
"""
import unicodedata


def clean_for_sse_text(text: str) -> str:
    """清理文本用于 SSE 传输"""
    if not isinstance(text, str):
        text = str(text)

    # 替换换行符
    cleaned = text.replace('\n', '\u2029').replace('\r', '')

    # 过滤控制字符
    cleaned_chars = []
    for char in cleaned:
        if char == '\t' or unicodedata.category(char)[0] != "C":
            cleaned_chars.append(char)
        else:
            cleaned_chars.append(' ')

    cleaned = ''.join(cleaned_chars)

    # 确保 UTF-8 编码
    try:
        cleaned.encode('utf-8')
    except UnicodeEncodeError:
        cleaned = cleaned.encode('utf-8', errors='replace').decode('utf-8')

    return cleaned


def format_sse_message(data: dict) -> str:
    """格式化 SSE 消息（JSON 格式）"""
    import json
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def format_sse_text(text: str) -> str:
    """格式化 SSE 消息（文本格式）"""
    safe_text = text.replace('\n', '\\n').replace('\r', '\\r')
    return f"data: {safe_text}\n\n"

