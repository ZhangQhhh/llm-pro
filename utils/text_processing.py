# -*- coding: utf-8 -*-
"""
文本处理工具
"""
import unicodedata


def clean_for_sse_text(text: str) -> str:
    """清理文本用于 SSE 传输
    
    注意：SSE 使用 \n\n 作为消息分隔符，所以不能在消息中包含 \n\n
    我们将 \n\n 替换为 <NEWLINE><NEWLINE>，保留单个 \n
    前端需要将 <NEWLINE> 转换回 \n 进行 markdown 渲染
    """
    if not isinstance(text, str):
        text = str(text)

    # 先处理 \r\n 和 \r，统一为 \n
    cleaned = text.replace('\r\n', '\n').replace('\r', '')
    
    # 将连续的 \n\n 替换为特殊标记（避免与 SSE 消息分隔符冲突）
    cleaned = cleaned.replace('\n\n', '<NEWLINE><NEWLINE>')
    
    # 将单个 \n 也替换为特殊标记（保持一致性）
    cleaned = cleaned.replace('\n', '<NEWLINE>')

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

