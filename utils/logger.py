# -*- coding: utf-8 -*-
"""
日志管理工具
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any


def setup_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """配置并返回日志记录器"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


class QALogger:
    """问答日志管理器"""

    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

    def save_log(
        self,
        question: str,
        answer: str,
        qa_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """保存问答日志到文件"""
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = os.path.join(self.log_dir, f"qa_log_{today}.jsonl")

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "type": qa_type,
            "question": question,
            "answer": answer,
            "metadata": metadata or {}
        }

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            logging.info(f"问答日志已保存: {log_file}")
        except Exception as e:
            logging.error(f"保存问答日志失败: {e}")


# 全局日志记录器
logger = setup_logger("RAGSystem")

# 禁用 urllib3 的详细日志
logging.getLogger("urllib3").setLevel(logging.WARNING)

