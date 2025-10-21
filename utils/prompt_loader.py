# -*- coding: utf-8 -*-
"""
Prompt 配置加载器
"""
import json
import logging
import os
from typing import Dict, Any, Optional


class PromptLoader:
    """Prompt 模板加载和管理器"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self.prompts: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        """加载 Prompt 配置文件（支持 .json 和 .py 格式）"""
        try:
            # 检查文件扩展名
            _, ext = os.path.splitext(self.config_path)

            if ext == '.py':
                # 加载 Python 配置文件
                import importlib.util
                spec = importlib.util.spec_from_file_location("prompts_config", self.config_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    self.prompts = getattr(module, 'PROMPTS', {})
                    logging.info(f"Prompts 配置文件已加载 (Python): {self.config_path}")
                else:
                    raise ValueError(f"无法加载 Python 配置文件: {self.config_path}")
            else:
                # 默认按 JSON 格式加载
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.prompts = json.load(f)
                logging.info(f"Prompts 配置文件已加载 (JSON): {self.config_path}")

        except FileNotFoundError:
            logging.warning(f"Prompts 配置文件不存在: {self.config_path}")
            self.prompts = {}
        except Exception as e:
            logging.error(f"加载 Prompts 配置文件失败: {e}", exc_info=True)
            self.prompts = {}

    def get(self, path: str, default: str = "") -> str:
        """
        通过路径获取 Prompt 模板

        Args:
            path: 点分隔的路径，如 "knowledge.system.rag_simple"
            default: 默认值

        Returns:
            str: Prompt 模板字符串
        """
        if not self.prompts:
            return default

        node = self.prompts
        for key in path.split('.'):
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default

        # 支持字符串和数组两种格式
        if isinstance(node, str):
            return node
        elif isinstance(node, list):
            return '\n'.join(node)
        else:
            return default

    def reload(self) -> None:
        """热重载配置"""
        self.load()


# 全局 Prompt 加载器（延迟初始化）
_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader(config_path: Optional[str] = None) -> PromptLoader:
    """获取全局 Prompt 加载器实例"""
    global _prompt_loader
    if _prompt_loader is None:
        if config_path is None:
            from config import CONFIG
            config_path = CONFIG["prompt_config_path"]
        _prompt_loader = PromptLoader(config_path)
    return _prompt_loader


def get_prompt(path: str, default: str = "") -> str:
    """便捷函数：获取 Prompt 模板"""
    return get_prompt_loader().get(path, default)
