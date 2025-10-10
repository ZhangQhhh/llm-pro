# -*- coding: utf-8 -*-
"""
文档处理模块
负责文档切分、哈希计算等功能
"""
import os
import re
import hashlib
from typing import List, Dict
from llama_index.core import Document
from utils.logger import logger


class DocumentProcessor:
    """文档处理器"""

    def __init__(self, chunk_pattern: str):
        """
        初始化文档处理器

        Args:
            chunk_pattern: 切分模式（正则表达式字符串）
        """
        self.chunk_pattern = re.compile(re.escape(chunk_pattern))

    def split_documents(self, docs: List[Document]) -> List[Document]:
        """
        按指定模式切分文档

        Args:
            docs: 原始文档列表

        Returns:
            切分后的文档列表
        """
        logger.info("开始按指定模式切分文档...")
        all_split_nodes = []

        for doc in docs:
            file_name = doc.metadata.get("file_name", "未知文件")
            original_text = doc.get_content()

            # 文本净化
            purified_text = self._purify_text(original_text, file_name)

            # 切分
            split_chunks = self._split_by_pattern(purified_text)

            # 创建新节点
            for chunk_text in split_chunks:
                new_node = Document(
                    text=chunk_text,
                    metadata=doc.metadata.copy()
                )
                all_split_nodes.append(new_node)

            logger.info(f"文件 '{file_name}' 被切割成 {len(split_chunks)} 个部分")

        return all_split_nodes

    def _purify_text(self, text: str, file_name: str) -> str:
        """净化文本中的转义字符"""
        try:
            return text.encode('raw_unicode_escape').decode('unicode_escape')
        except UnicodeDecodeError:
            logger.warning(f"文件 '{file_name}' 包含复杂转义字符，尝试替换处理")
            return re.sub(
                r'\\u([0-9a-fA-F]{4})',
                lambda m: chr(int(m.group(1), 16)),
                text
            )

    def _split_by_pattern(self, text: str) -> List[str]:
        """按模式切分文本"""
        matches = list(self.chunk_pattern.finditer(text))

        if not matches:
            return [text]

        chunks = []
        last_end = 0

        for match in matches:
            chunk = text[last_end:match.start()].strip()
            if chunk:
                chunks.append(chunk)
            last_end = match.start()

        # 添加最后一段
        last_chunk = text[last_end:].strip()
        if last_chunk:
            chunks.append(last_chunk)

        return chunks

    @staticmethod
    def compute_file_hashes(dir_path: str) -> Dict[str, str]:
        """
        计算目录下所有文件的哈希值

        Args:
            dir_path: 目录路径

        Returns:
            文件路径到哈希值的映射
        """
        hashes = {}

        for root, _, files in os.walk(dir_path):
            for file in files:
                # 跳过临时文件
                if file.lower().endswith((".doc", ".tmp")):
                    continue

                file_path = os.path.join(root, file)
                hasher = hashlib.sha256()

                try:
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(8192):
                            hasher.update(chunk)
                    hashes[file_path] = hasher.hexdigest()
                except IOError as e:
                    logger.warning(f"无法读取文件 {file_path}: {e}")

        return hashes

