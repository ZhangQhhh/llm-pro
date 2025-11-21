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
        """按模式切分文本（切分后自动移除分隔符）"""
        matches = list(self.chunk_pattern.finditer(text))

        if not matches:
            return [text]

        chunks = []
        last_end = 0

        for match in matches:
            # 提取分隔符之前的内容
            chunk = text[last_end:match.start()].strip()
            if chunk:
                chunks.append(chunk)
            # 关键修复：跳过分隔符本身，从 match.end() 开始下一段
            last_end = match.end()

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

# =========================
# 新增：WriterAwareSplitter
# =========================
class WriterAwareSplitter:
    """
    面向“智能体写作”的高质量语义切分器（新增，不影响旧逻辑）：
    - 优先按“标题/小节/列表项/空行”切分；
    - 再按“句末标点”做软切分与聚合；
    - 控制 chunk 最大长度 + 重叠，适配写作引用与重排。
    """

    # 章节/标题（Markdown/中文序号）
    HEADING_RE = re.compile(
        r"^(?:\s{0,3}#{1,6}\s+.+|"                # Markdown 标题
        r"\s{0,2}第[一二三四五六七八九十百千]+[章节部分篇]\s*.+|"  # 中文序号标题
        r"\s{0,2}\d+[\.)、]\s+.+)$",              # 数字序号标题
        re.M
    )
    # 列表项/要点
    LIST_RE = re.compile(r"^\s*([-*•·]|[0-9]{1,2}[.)、])\s+.+$", re.M)

    # 句末标点（中英文）
    SENT_END_RE = re.compile(r"(?<=[。！？!?；;])\s+")
    # 过长行的软换行
    SOFT_WRAP_RE = re.compile(r"[，,、]\s+")

    def __init__(self,
                 max_chars: int = 1200,
                 overlap: int = 120,
                 prefer_headings: bool = True,
                 merge_short: bool = True):
        self.max_chars = max_chars
        self.overlap = overlap
        self.prefer_headings = prefer_headings
        self.merge_short = merge_short

    @staticmethod
    def _purify_text(text: str) -> str:
        """复用旧模块的净化思路，独立实现以免影响旧逻辑"""
        try:
            return text.encode('raw_unicode_escape').decode('unicode_escape')
        except UnicodeDecodeError:
            return re.sub(
                r'\\u([0-9a-fA-F]{4})',
                lambda m: chr(int(m.group(1), 16)),
                text
            )

    def _hard_segments(self, text: str) -> List[str]:
        """
        先做“硬分段”：标题/列表/空行 → 自然段
        """
        lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        segs: List[str] = []
        buf: List[str] = []

        def flush():
            if buf:
                segs.append("\n".join(buf).strip())
                buf.clear()

        for ln in lines:
            if not ln.strip():
                # 空行：分段
                flush()
                continue
            if self.HEADING_RE.match(ln) or self.LIST_RE.match(ln):
                flush()
                segs.append(ln.strip())
            else:
                buf.append(ln)
        flush()
        # 过滤空
        return [s for s in segs if s]

    def _soft_sentences(self, paragraph: str) -> List[str]:
        """
        对段落内部做“软切分”：句子/逗号群
        """
        paragraph = paragraph.strip()
        if len(paragraph) <= self.max_chars:
            return [paragraph]

        # 先按句末切
        sents = []
        start = 0
        for m in self.SENT_END_RE.finditer(paragraph):
            sents.append(paragraph[start:m.end()].strip())
            start = m.end()
        if start < len(paragraph):
            sents.append(paragraph[start:].strip())

        # 若句子仍然过长，再按逗号软切
        fine = []
        for s in sents:
            if len(s) <= self.max_chars:
                fine.append(s)
            else:
                parts = self.SOFT_WRAP_RE.split(s)
                cur = ""
                for p in parts:
                    add = (p + "，") if not p.endswith(("。", "！", "？", "；", ".", "!", "?", ";")) else p
                    if len(cur) + len(add) <= self.max_chars:
                        cur += add
                    else:
                        if cur:
                            fine.append(cur.strip("，"))
                        cur = add
                if cur:
                    fine.append(cur.strip("，"))
        return [x for x in fine if x]

    def split_text(self, text: str) -> List[str]:
        """
        综合切分：硬分段 + 软切分 + 聚合到 max_chars，段与段之间保留少量重叠
        """
        text = self._purify_text(text)
        hard = self._hard_segments(text)

        # 将短段合并，尽量在标题后开新块
        chunks: List[str] = []
        cur = ""
        last_was_heading = False

        def push(buf: str):
            if not buf:
                return
            if len(buf) <= self.max_chars:
                chunks.append(buf)
                return
            # 超长块再按句子软切
            for s in self._soft_sentences(buf):
                chunks.append(s)

        for seg in hard:
            is_heading = bool(self.HEADING_RE.match(seg))
            # 标题：强制断块
            if is_heading and self.prefer_headings:
                if cur:
                    push(cur.strip())
                    cur = ""
                push(seg.strip())
                last_was_heading = True
                continue

            candidate = (cur + "\n\n" + seg) if cur else seg
            if len(candidate) > self.max_chars:
                if cur:
                    push(cur.strip())
                cur = seg
            else:
                cur = candidate
            last_was_heading = is_heading

        if cur:
            push(cur.strip())

        # 可选：为检索重排提供小重叠（在文本末尾重复一小段）
        if self.overlap > 0 and len(chunks) > 1:
            overlapped: List[str] = []
            for i, c in enumerate(chunks):
                if i == 0:
                    overlapped.append(c)
                else:
                    tail = chunks[i - 1][-self.overlap :]
                    overlapped.append((tail + "\n\n" + c).strip())
            chunks = overlapped

        return chunks

    def split_documents_for_writer(self, docs: List[Document]) -> List[Document]:
        """对 Document 列表进行写作友好切分"""
        results: List[Document] = []
        for doc in docs:
            file_name = doc.metadata.get("file_name", "未知文件")
            text = doc.get_content() or ""
            logger.info(f"[WriterSplit] 处理文件：{file_name}（长度 {len(text)}）")
            for idx, chunk in enumerate(self.split_text(text)):
                meta = doc.metadata.copy()
                meta["chunk_id"] = idx
                meta["source_file"] = file_name
                results.append(Document(text=chunk, metadata=meta))
        logger.info(f"[WriterSplit] 共生成 {len(results)} 个切分块")
        return results


# ================
# 便捷函数（新增）
# ================
def split_documents_writer(
    docs: List[Document],
    max_chars: int = 1200,
    overlap: int = 120,
    prefer_headings: bool = True,
    merge_short: bool = True
) -> List[Document]:
    """
    供 writer_service / writer_handler 引用的“智能体写作专用”切分函数。
    不影响旧的 DocumentProcessor API。
    """
    splitter = WriterAwareSplitter(
        max_chars=max_chars,
        overlap=overlap,
        prefer_headings=prefer_headings,
        merge_short=merge_short
    )
    return splitter.split_documents_for_writer(docs)