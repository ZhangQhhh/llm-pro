# -*- coding: utf-8 -*-
"""
会话ID辅助函数
用于管理和验证与用户关联的会话ID
"""
import uuid
from typing import Optional, Tuple
from utils import logger


def generate_session_id(user_id: int) -> str:
    """
    生成与用户关联的会话ID

    格式: {user_id}_{uuid}

    Args:
        user_id: 用户ID

    Returns:
        str: 会话ID
    """
    session_uuid = str(uuid.uuid4())
    session_id = f"{user_id}_{session_uuid}"
    logger.debug(f"为用户 {user_id} 生成新会话ID: {session_id}")
    return session_id


def parse_session_id(session_id: str) -> Optional[Tuple[int, str]]:
    """
    解析会话ID，提取用户ID和UUID部分

    Args:
        session_id: 会话ID

    Returns:
        Optional[Tuple[int, str]]: (user_id, uuid) 或 None（如果格式无效）
    """
    if not session_id or '_' not in session_id:
        return None

    try:
        parts = session_id.split('_', 1)
        user_id = int(parts[0])
        session_uuid = parts[1]
        return (user_id, session_uuid)
    except (ValueError, IndexError):
        return None


def validate_session_ownership(session_id: str, user_id: int) -> bool:
    """
    验证会话ID是否属于指定用户

    Args:
        session_id: 会话ID
        user_id: 用户ID

    Returns:
        bool: 如果会话属于该用户返回True，否则返回False
    """
    parsed = parse_session_id(session_id)
    if parsed is None:
        # 旧格式（纯UUID）- 允许通过但记录警告
        logger.warning(f"检测到旧格式 session_id: {session_id}")
        return True

    session_user_id, _ = parsed
    return session_user_id == user_id


def get_user_id_from_session(session_id: str) -> Optional[int]:
    """
    从会话ID中提取用户ID

    Args:
        session_id: 会话ID

    Returns:
        Optional[int]: 用户ID，如果无法解析则返回None
    """
    parsed = parse_session_id(session_id)
    if parsed is None:
        return None
    return parsed[0]


def is_legacy_session_id(session_id: str) -> bool:
    """
    检查是否为旧格式的会话ID（纯UUID）

    Args:
        session_id: 会话ID

    Returns:
        bool: 如果是旧格式返回True
    """
    return '_' not in session_id

