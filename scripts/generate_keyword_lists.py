#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量分析知识库文本，自动生成关键词白名单与黑名单候选列表。

使用方式（示例）:
    python scripts/generate_keyword_lists.py \
        --top-k 300 \
        --blacklist-doc-ratio 0.7

输出:
    dict/auto_keyword_whitelist.json
    dict/auto_keyword_blacklist.json
"""
import argparse
import json
import math
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import jieba

# 将项目根目录加入路径，便于导入现有模块
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config import Settings  # noqa: E402
from llama_index.core import SimpleDirectoryReader  # noqa: E402
from utils.logger import logger  # noqa: E402


DEFAULT_EXTS = [".txt", ".md", ".pdf", ".docx"]
PUNCTUATIONS = set("，。,.;；:?？！!、\"'`（）()[]{}<>《》/\\|+-=_~—…·  \t\r\n")


def load_stopwords(stopwords_path: Path) -> set:
    """读取停用词表."""
    stopwords = set()
    if stopwords_path.exists():
        with stopwords_path.open("r", encoding="utf-8") as f:
            for line in f:
                word = line.strip()
                if word and not word.startswith("#"):
                    stopwords.add(word)
    return stopwords


def tokenize(text: str, stopwords: set) -> List[str]:
    """分词并过滤无效 token."""
    tokens = []
    if not text:
        return tokens

    for token in jieba.lcut(text):
        token = token.strip()
        if not token:
            continue
        if token in stopwords:
            continue
        if all(ch in PUNCTUATIONS for ch in token):
            continue
        if token.isdigit():
            continue
        if len(token) == 1 and not token.isalpha():
            continue
        tokens.append(token)
    return tokens


def load_documents(directory: Path) -> List:
    """使用 SimpleDirectoryReader 读取目录下的文档."""
    # 检查目录是否存在且包含文件
    if not directory.exists():
        logger.warning(f"目录不存在: {directory}")
        return []
    
    # 检查目录是否为空
    has_files = False
    for ext in DEFAULT_EXTS:
        if list(directory.rglob(f"*{ext}")):
            has_files = True
            break
    
    if not has_files:
        logger.warning(f"目录为空或不包含支持的文件格式: {directory}")
        return []
    
    try:
        reader = SimpleDirectoryReader(
            str(directory),
            recursive=True,
            required_exts=DEFAULT_EXTS,
            filename_as_id=True,
        )
        return reader.load_data()
    except ValueError as e:
        logger.warning(f"读取目录失败: {directory} | 错误: {e}")
        return []


def compute_keyword_stats(
    kb_name: str,
    directory: Path,
    stopwords: set,
    top_k: int,
    blacklist_ratio: float,
) -> Optional[Dict]:
    """对单个知识库目录计算关键词统计."""
    if not directory.exists():
        logger.warning(f"[{kb_name}] 路径不存在: {directory}")
        return None

    logger.info(f"[{kb_name}] 开始加载文档... | 路径: {directory}")
    documents = load_documents(directory)
    if not documents:
        logger.warning(f"[{kb_name}] 未读取到任何文档，跳过")
        return None

    term_freq = Counter()
    doc_freq = Counter()
    total_docs = 0
    total_files = len(documents)
    log_interval = max(1, total_files // 20)  # roughly every 5%

    for idx, doc in enumerate(documents, start=1):
        text = doc.get_content() if hasattr(doc, "get_content") else getattr(doc, "text", "")
        tokens = tokenize(text, stopwords)
        if not tokens:
            continue

        total_docs += 1
        term_freq.update(tokens)
        doc_freq.update(set(tokens))

        if idx % log_interval == 0 or idx == total_files:
            logger.info(
                f"[{kb_name}] 进度: {idx}/{total_files} 文档（有效: {total_docs}）..."
            )

    if total_docs == 0:
        logger.warning(f"[{kb_name}] 没有可用于统计的文档")
        return None

    logger.info(f"[{kb_name}] 完成分词统计 | 文档数: {total_docs} | 词条数: {len(term_freq)}")

    keyword_candidates = []
    for token, freq in term_freq.items():
        df = doc_freq[token]
        tf = freq / sum(term_freq.values())
        idf = math.log((total_docs + 1) / (df + 1)) + 1
        tfidf = tf * idf
        doc_ratio = df / total_docs
        keyword_candidates.append(
            {
                "token": token,
                "tfidf": tfidf,
                "term_freq": freq,
                "doc_freq": df,
                "doc_ratio": doc_ratio,
            }
        )

    keyword_candidates.sort(key=lambda x: x["tfidf"], reverse=True)
    top_keywords = keyword_candidates[:top_k]
    blacklist_candidates = [
        item for item in keyword_candidates if item["doc_ratio"] >= blacklist_ratio
    ]

    return {
        "name": kb_name,
        "directory": str(directory),
        "document_count": total_docs,
        "distinct_terms": len(term_freq),
        "top_keywords": top_keywords,
        "blacklist_candidates": blacklist_candidates,
    }


def aggregate_tokens(
    per_kb_stats: List[Dict],
    top_k: int,
) -> Tuple[List[Dict], List[Dict]]:
    """汇总所有知识库的白名单和黑名单."""
    whitelist_map: Dict[str, Dict] = {}
    blacklist_map: Dict[str, Dict] = {}

    for stats in per_kb_stats:
        kb_name = stats["name"]
        for item in stats["top_keywords"]:
            token = item["token"]
            if token not in whitelist_map or item["tfidf"] > whitelist_map[token]["tfidf"]:
                whitelist_map[token] = {
                    "token": token,
                    "tfidf": item["tfidf"],
                    "sources": {kb_name},
                    "term_freq": item["term_freq"],
                    "doc_freq": item["doc_freq"],
                    "doc_ratio": item["doc_ratio"],
                }
            else:
                whitelist_map[token]["sources"].add(kb_name)

        for item in stats["blacklist_candidates"]:
            token = item["token"]
            if token not in blacklist_map or item["doc_ratio"] > blacklist_map[token]["doc_ratio"]:
                blacklist_map[token] = {
                    "token": token,
                    "doc_ratio": item["doc_ratio"],
                    "sources": {kb_name},
                    "term_freq": item["term_freq"],
                    "doc_freq": item["doc_freq"],
                }
            else:
                blacklist_map[token]["sources"].add(kb_name)

    whitelist = sorted(
        (
            {
                **value,
                "sources": sorted(value["sources"]),
            }
            for value in whitelist_map.values()
        ),
        key=lambda x: x["tfidf"],
        reverse=True,
    )[:top_k]

    blacklist = sorted(
        (
            {
                **value,
                "sources": sorted(value["sources"]),
            }
            for value in blacklist_map.values()
        ),
        key=lambda x: x["doc_ratio"],
        reverse=True,
    )

    return whitelist, blacklist


def write_output(path: Path, payload: Dict):
    """写出 JSON 文件."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info(f"已生成文件: {path}")


def write_stopwords_txt(
    output_path: Path,
    blacklist: List[Dict],
    metadata: Dict,
    min_doc_ratio: float = 0.5
):
    """将黑名单转换为停用词文本格式."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 过滤：只保留文档占比 >= min_doc_ratio 的词
    filtered = [t for t in blacklist if t.get('doc_ratio', 0) >= min_doc_ratio]
    
    with output_path.open('w', encoding='utf-8') as f:
        # 写入文件头
        f.write("# 自动生成的停用词表\n")
        f.write(f"# 生成时间: {metadata.get('generated_at', 'unknown')}\n")
        f.write(f"# 过滤条件: doc_ratio >= {min_doc_ratio}\n")
        f.write(f"# 知识库: {', '.join(metadata.get('knowledge_bases', []))}\n")
        f.write(f"# 总词数: {len(filtered)}\n")
        f.write("\n")
        
        # 写入词汇（带注释）
        for token_data in filtered:
            token = token_data['token']
            doc_ratio = token_data.get('doc_ratio', 0)
            sources = ', '.join(token_data.get('sources', []))
            f.write(f"{token}  # doc_ratio={doc_ratio:.2f}, sources=[{sources}]\n")
    
    logger.info(f"✓ 停用词文本文件已生成: {output_path} ({len(filtered)} 个词)")
    return len(filtered)


def write_keywords_txt(
    output_path: Path,
    whitelist: List[Dict],
    metadata: Dict,
    min_tfidf: float = 0.01,
    default_freq: int = 10000
):
    """将白名单转换为自定义词典格式."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 过滤：只保留 tfidf >= min_tfidf 的词
    filtered = [t for t in whitelist if t.get('tfidf', 0) >= min_tfidf]
    
    with output_path.open('w', encoding='utf-8') as f:
        # 写入文件头
        f.write("# 自动生成的自定义词典\n")
        f.write(f"# 生成时间: {metadata.get('generated_at', 'unknown')}\n")
        f.write(f"# 过滤条件: tfidf >= {min_tfidf}\n")
        f.write(f"# 知识库: {', '.join(metadata.get('knowledge_bases', []))}\n")
        f.write(f"# 总词数: {len(filtered)}\n")
        f.write(f"# 格式: 词 频率 词性\n")
        f.write("\n")
        
        # 写入词汇（jieba 格式）
        for token_data in filtered:
            token = token_data['token']
            tfidf = token_data.get('tfidf', 0)
            sources = ', '.join(token_data.get('sources', []))
            
            # 根据 tfidf 计算词频（tfidf 越高，词频越高）
            freq = int(default_freq * (1 + tfidf * 10))
            
            f.write(f"{token}  {freq} n  # tfidf={tfidf:.4f}, sources=[{sources}]\n")
    
    logger.info(f"✓ 关键词文本文件已生成: {output_path} ({len(filtered)} 个词)")
    return len(filtered)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="根据知识库生成关键词白名单与黑名单")
    parser.add_argument("--top-k", type=int, default=999999, help="每个知识库提取的关键词数量（默认提取所有）")
    parser.add_argument(
        "--global-top-k",
        type=int,
        default=999999,
        help="最终白名单的最大词条数（默认提取所有）",
    )
    parser.add_argument(
        "--blacklist-doc-ratio",
        type=float,
        default=0.5,
        help="若词条文档占比达到该阈值则纳入黑名单候选（默认0.5，即50%文档中出现）",
    )
    parser.add_argument(
        "--whitelist-output",
        type=str,
        default=str(PROJECT_ROOT / "dict" / "auto_keyword_whitelist.json"),
        help="白名单JSON输出路径",
    )
    parser.add_argument(
        "--blacklist-output",
        type=str,
        default=str(PROJECT_ROOT / "dict" / "auto_keyword_blacklist.json"),
        help="黑名单JSON输出路径",
    )
    parser.add_argument(
        "--output-txt",
        action="store_true",
        default=True,
        help="是否同时生成TXT格式文件（默认开启）",
    )
    parser.add_argument(
        "--min-tfidf",
        type=float,
        default=0.001,
        help="TXT格式白名单的最小TF-IDF阈值（默认0.001，设为0可保留所有）",
    )
    parser.add_argument(
        "--min-doc-ratio-txt",
        type=float,
        default=0.3,
        help="TXT格式黑名单的最小文档占比阈值（默认0.3，即30%文档中出现）",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # 加载自定义词典（如存在）
    custom_dict_path = PROJECT_ROOT / "dict" / "custom_dict.txt"
    if custom_dict_path.exists():
        jieba.load_userdict(str(custom_dict_path))
        logger.info(f"已加载自定义词典: {custom_dict_path}")

    stopwords = load_stopwords(PROJECT_ROOT / "dict" / "stopwords.txt")
    logger.info(f"停用词表加载完成，共 {len(stopwords)} 个词")

    kb_directories = [
        ("general", Path(Settings.KNOWLEDGE_BASE_DIR)),
        ("visa_free", Path(getattr(Settings, "VISA_FREE_KB_DIR", ""))),
        ("airline", Path(getattr(Settings, "AIRLINE_KB_DIR", ""))),
        ("hidden", Path(getattr(Settings, "HIDDEN_KB_DIR", ""))),
    ]

    per_kb_stats = []
    for kb_name, kb_path in kb_directories:
        if not kb_path or not str(kb_path).strip():
            continue
        stats = compute_keyword_stats(
            kb_name=kb_name,
            directory=kb_path,
            stopwords=stopwords,
            top_k=args.top_k,
            blacklist_ratio=args.blacklist_doc_ratio,
        )
        if stats:
            per_kb_stats.append(stats)

    if not per_kb_stats:
        logger.error("未能生成任何知识库的统计结果，脚本结束")
        sys.exit(1)

    whitelist, blacklist = aggregate_tokens(per_kb_stats, args.global_top_k)

    generated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    whitelist_payload = {
        "generated_at": generated_at,
        "top_k_per_kb": args.top_k,
        "global_top_k": args.global_top_k,
        "knowledge_bases": [stats["name"] for stats in per_kb_stats],
        "tokens": whitelist,
    }
    blacklist_payload = {
        "generated_at": generated_at,
        "blacklist_doc_ratio": args.blacklist_doc_ratio,
        "knowledge_bases": [stats["name"] for stats in per_kb_stats],
        "tokens": blacklist,
    }

    # 写入 JSON 文件
    write_output(Path(args.whitelist_output), whitelist_payload)
    write_output(Path(args.blacklist_output), blacklist_payload)

    # 同时生成 TXT 格式文件
    if args.output_txt:
        logger.info("")
        logger.info("=" * 60)
        logger.info("开始生成 TXT 格式文件")
        logger.info("=" * 60)
        
        # 生成停用词文本文件
        stopwords_txt_path = PROJECT_ROOT / "dict" / "auto_stopwords.txt"
        stopwords_count = write_stopwords_txt(
            output_path=stopwords_txt_path,
            blacklist=blacklist,
            metadata={
                'generated_at': generated_at,
                'knowledge_bases': [stats["name"] for stats in per_kb_stats]
            },
            min_doc_ratio=args.min_doc_ratio_txt
        )
        
        # 生成关键词文本文件
        keywords_txt_path = PROJECT_ROOT / "dict" / "auto_keywords.txt"
        keywords_count = write_keywords_txt(
            output_path=keywords_txt_path,
            whitelist=whitelist,
            metadata={
                'generated_at': generated_at,
                'knowledge_bases': [stats["name"] for stats in per_kb_stats]
            },
            min_tfidf=args.min_tfidf,
            default_freq=10000
        )
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("TXT 格式文件生成完成")
        logger.info("=" * 60)
        logger.info(f"停用词: {stopwords_txt_path} ({stopwords_count} 个)")
        logger.info(f"关键词: {keywords_txt_path} ({keywords_count} 个)")
        logger.info("")
        logger.info("使用方法:")
        logger.info("1. 查看生成的文件，确认词汇质量")
        logger.info("2. 将需要的词汇添加到 dict/stopwords.txt 和 dict/custom_dict.txt")
        logger.info("3. 或者直接使用生成的文件（需要备份原文件）")

    logger.info("")
    logger.info("关键词白名单/黑名单生成完成")


if __name__ == "__main__":
    main()
