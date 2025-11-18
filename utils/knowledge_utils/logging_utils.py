# -*- coding: utf-8 -*-
"""
日志记录工具
处理知识库问答的日志输出和文件记录
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from utils import logger


def log_prompt_to_file(question: str, prompt_parts: Dict[str, Any]):
    """
    将提示词上下文输出到日志文件（每次问答单独保存）
    
    Args:
        question: 用户问题
        prompt_parts: 提示词字典
    """
    try:
        # 确保 logs 目录存在
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # 生成唯一的日志文件名（基于时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = logs_dir / f"prompt_{timestamp}.txt"
        
        # 构建日志内容（完整的单次问答上下文）
        log_content = []
        log_content.append("=" * 100)
        log_content.append(f"问答时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log_content.append("=" * 100)
        log_content.append("")
        
        # 用户问题
        log_content.append("【用户问题】")
        log_content.append(question)
        log_content.append("")
        log_content.append("-" * 100)
        log_content.append("")
        
        # System Prompt
        log_content.append("【System Prompt】")
        log_content.append(prompt_parts.get('system_prompt', 'N/A'))
        log_content.append("")
        log_content.append("-" * 100)
        log_content.append("")
        
        # Assistant Context (检索文档 + 子问题答案)
        context_for_log = prompt_parts.get('assistant_context_log') or prompt_parts.get('assistant_context')
        if context_for_log:
            log_content.append("【参考资料】（以下内容已注入到用户问题中）")
            log_content.append(context_for_log)
            log_content.append("")
            log_content.append("-" * 100)
            log_content.append("")
        else:
            log_content.append("【参考资料】")
            log_content.append("无检索文档或子问题答案")
            log_content.append("")
            log_content.append("-" * 100)
            log_content.append("")
        
        # User Prompt
        log_content.append("【User Prompt】")
        log_content.append(prompt_parts.get('user_prompt', 'N/A'))
        log_content.append("")
        log_content.append("=" * 100)
        
        # 写入文件（每次问答独立文件）
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_content))
        
        logger.info(f"[提示词日志] 已保存到 {log_file}")
        
        # 同时追加到总日志文件（可选，便于查看所有记录）
        all_logs_file = logs_dir / "prompts_logs_all.txt"
        with open(all_logs_file, 'a', encoding='utf-8') as f:
            f.write('\n'.join(log_content))
            f.write('\n\n')
        
    except Exception as e:
        logger.error(f"[提示词日志] 保存失败: {e}")


def log_reference_details(
    question: str,
    references: List[Dict],
    mode: str,
    session_id: Optional[str] = None,
    log_dir: str = None
):
    """
    记录参考文献详情到日志文件
    
    Args:
        question: 用户问题
        references: 参考文献列表
        mode: 模式标识
        session_id: 会话ID（可选）
        log_dir: 日志目录路径
    """
    try:
        from config import Settings
        log_dir = log_dir or Settings.LOG_DIR
        
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "reference_logs.jsonl")
        
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "mode": mode,
            "session_id": session_id,
            "question": question,
            "references": references
        }
        
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
            
    except Exception as e:
        logger.warning(f"记录参考文献日志失败: {e}")


def save_qa_log(
    question: str,
    response: str,
    client_ip: str,
    has_rag: bool,
    use_insert_block: bool = False,
    log_dir: str = None
):
    """
    保存问答日志
    
    Args:
        question: 用户问题
        response: 完整响应
        client_ip: 客户端IP
        has_rag: 是否有RAG内容
        use_insert_block: 是否使用了InsertBlock
        log_dir: 日志目录路径
    """
    try:
        from utils import QALogger
        from config import Settings
        
        log_dir = log_dir or Settings.LOG_DIR
        qa_logger = QALogger(log_dir)
        
        qa_logger.save_log(
            question,
            response,
            'knowledge_qa_stream',
            metadata={
                "ip": client_ip,
                "answer_type": "rag" if has_rag else "general",
                "chat_mode": Settings.USE_CHAT_MODE,
                "insert_block_mode": use_insert_block
            }
        )
        
    except Exception as e:
        logger.warning(f"保存问答日志失败: {e}")


def format_debug_info(
    question: str,
    node_count: int,
    processing_time: float,
    mode: str = "knowledge"
) -> str:
    """
    格式化调试信息
    
    Args:
        question: 用户问题
        node_count: 处理的节点数
        processing_time: 处理时间（秒）
        mode: 处理模式
        
    Returns:
        格式化的调试信息字符串
    """
    return (
        f"[{mode.upper()}] 问题: {question[:50]}{'...' if len(question) > 50 else ''} | "
        f"节点数: {node_count} | "
        f"耗时: {processing_time:.2f}s"
    )
