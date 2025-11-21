#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 auto_keyword_blacklist.json 和 auto_keyword_whitelist.json 转换为文本格式

输出格式：
- blacklist -> dict/auto_stopwords.txt (停用词格式，每行一个词)
- whitelist -> dict/auto_keywords.txt (自定义词典格式，词 频率 词性)
"""

import json
import logging
from pathlib import Path
from typing import List, Dict

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_json_file(filepath: Path) -> Dict:
    """加载 JSON 文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"加载文件失败: {filepath} | 错误: {e}")
        return {}


def convert_blacklist_to_stopwords(
    blacklist_file: Path,
    output_file: Path,
    min_doc_ratio: float = 0.5
) -> int:
    """
    将 blacklist JSON 转换为停用词文本格式
    
    Args:
        blacklist_file: blacklist JSON 文件路径
        output_file: 输出文本文件路径
        min_doc_ratio: 最小文档比例阈值（过滤掉出现频率过低的词）
        
    Returns:
        转换的词数
    """
    logger.info(f"开始转换 blacklist: {blacklist_file}")
    
    data = load_json_file(blacklist_file)
    if not data or 'tokens' not in data:
        logger.error("blacklist 文件格式错误或为空")
        return 0
    
    tokens = data['tokens']
    logger.info(f"读取到 {len(tokens)} 个 blacklist 词")
    
    # 过滤并排序
    filtered_tokens = [
        t for t in tokens 
        if t.get('doc_ratio', 0) >= min_doc_ratio
    ]
    
    # 按 doc_ratio 降序排序
    filtered_tokens.sort(key=lambda x: x.get('doc_ratio', 0), reverse=True)
    
    logger.info(f"过滤后保留 {len(filtered_tokens)} 个词 (doc_ratio >= {min_doc_ratio})")
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        # 写入文件头
        f.write("# 自动生成的停用词表\n")
        f.write(f"# 来源: {blacklist_file.name}\n")
        f.write(f"# 生成时间: {data.get('generated_at', 'unknown')}\n")
        f.write(f"# 过滤条件: doc_ratio >= {min_doc_ratio}\n")
        f.write(f"# 总词数: {len(filtered_tokens)}\n")
        f.write("\n")
        
        # 写入词汇（带注释）
        for token_data in filtered_tokens:
            token = token_data['token']
            doc_ratio = token_data.get('doc_ratio', 0)
            sources = ', '.join(token_data.get('sources', []))
            
            # 写入词汇和注释
            f.write(f"{token}  # doc_ratio={doc_ratio:.2f}, sources=[{sources}]\n")
    
    logger.info(f"✓ blacklist 转换完成: {output_file}")
    logger.info(f"  共 {len(filtered_tokens)} 个停用词")
    
    return len(filtered_tokens)


def convert_whitelist_to_custom_dict(
    whitelist_file: Path,
    output_file: Path,
    min_tfidf: float = 0.01,
    default_freq: int = 10000
) -> int:
    """
    将 whitelist JSON 转换为自定义词典格式
    
    Args:
        whitelist_file: whitelist JSON 文件路径
        output_file: 输出文本文件路径
        min_tfidf: 最小 TF-IDF 阈值
        default_freq: 默认词频
        
    Returns:
        转换的词数
    """
    logger.info(f"开始转换 whitelist: {whitelist_file}")
    
    data = load_json_file(whitelist_file)
    if not data or 'tokens' not in data:
        logger.error("whitelist 文件格式错误或为空")
        return 0
    
    tokens = data['tokens']
    logger.info(f"读取到 {len(tokens)} 个 whitelist 词")
    
    # 过滤并排序
    filtered_tokens = [
        t for t in tokens 
        if t.get('tfidf', 0) >= min_tfidf
    ]
    
    # 按 tfidf 降序排序
    filtered_tokens.sort(key=lambda x: x.get('tfidf', 0), reverse=True)
    
    logger.info(f"过滤后保留 {len(filtered_tokens)} 个词 (tfidf >= {min_tfidf})")
    
    # 写入文件
    with open(output_file, 'w', encoding='utf-8') as f:
        # 写入文件头
        f.write("# 自动生成的自定义词典\n")
        f.write(f"# 来源: {whitelist_file.name}\n")
        f.write(f"# 生成时间: {data.get('generated_at', 'unknown')}\n")
        f.write(f"# 过滤条件: tfidf >= {min_tfidf}\n")
        f.write(f"# 总词数: {len(filtered_tokens)}\n")
        f.write(f"# 格式: 词 频率 词性\n")
        f.write("\n")
        
        # 写入词汇
        for token_data in filtered_tokens:
            token = token_data['token']
            tfidf = token_data.get('tfidf', 0)
            sources = ', '.join(token_data.get('sources', []))
            
            # 根据 tfidf 计算词频（tfidf 越高，词频越高）
            freq = int(default_freq * (1 + tfidf * 10))
            
            # 写入词汇（jieba 格式：词 频率 词性）
            f.write(f"{token}  {freq} n  # tfidf={tfidf:.4f}, sources=[{sources}]\n")
    
    logger.info(f"✓ whitelist 转换完成: {output_file}")
    logger.info(f"  共 {len(filtered_tokens)} 个关键词")
    
    return len(filtered_tokens)


def main():
    """主函数"""
    # 定义路径
    base_dir = Path(__file__).parent.parent
    logs_dir = base_dir / "logs"
    dict_dir = base_dir / "dict"
    
    blacklist_file = logs_dir / "auto_keyword_blacklist.json"
    whitelist_file = logs_dir / "auto_keyword_whitelist.json"
    
    stopwords_output = dict_dir / "auto_stopwords.txt"
    keywords_output = dict_dir / "auto_keywords.txt"
    
    # 确保输出目录存在
    dict_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("=" * 60)
    logger.info("开始转换关键词 JSON 文件")
    logger.info("=" * 60)
    
    # 转换 blacklist
    if blacklist_file.exists():
        blacklist_count = convert_blacklist_to_stopwords(
            blacklist_file=blacklist_file,
            output_file=stopwords_output,
            min_doc_ratio=0.5  # 只保留在 50% 以上文档中出现的词
        )
    else:
        logger.warning(f"blacklist 文件不存在: {blacklist_file}")
        blacklist_count = 0
    
    logger.info("")
    
    # 转换 whitelist
    if whitelist_file.exists():
        whitelist_count = convert_whitelist_to_custom_dict(
            whitelist_file=whitelist_file,
            output_file=keywords_output,
            min_tfidf=0.01,  # 只保留 TF-IDF >= 0.01 的词
            default_freq=10000
        )
    else:
        logger.warning(f"whitelist 文件不存在: {whitelist_file}")
        whitelist_count = 0
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("转换完成")
    logger.info("=" * 60)
    logger.info(f"停用词: {stopwords_output} ({blacklist_count} 个)")
    logger.info(f"关键词: {keywords_output} ({whitelist_count} 个)")
    logger.info("")
    logger.info("使用方法:")
    logger.info("1. 停用词: 将 auto_stopwords.txt 中的词添加到 stopwords.txt")
    logger.info("2. 关键词: 将 auto_keywords.txt 中的词添加到 custom_dict.txt")
    logger.info("3. 或者直接使用这两个文件替换原有文件（需要备份）")


if __name__ == "__main__":
    main()
