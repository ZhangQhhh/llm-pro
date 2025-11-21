# -*- coding: utf-8 -*-
"""
关键词权重计算和排序工具
"""
import os
import jieba
from collections import Counter
from typing import List, Dict, Tuple
from utils.logger import logger


class KeywordRanker:
    """关键词权重计算器"""
    
    def __init__(self):
        # 加载停用词
        self.stopwords = self._load_stopwords()
        logger.info(f" 加载停用词: {len(self.stopwords)} 个")
    
    def _load_stopwords(self) -> set:
        """加载停用词表"""
        stopwords = set()
        stopwords_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "dict", "auto_stopwords.txt"
        )
        
        if os.path.exists(stopwords_path):
            with open(stopwords_path, 'r', encoding='utf-8') as f:
                for line in f:
                    word = line.strip()
                    if word and not word.startswith('#'):
                        stopwords.add(word)
        else:
            logger.warning(f" 停用词表不存在: {stopwords_path}")
        
        return stopwords
    
    def filter_keywords(self, keywords: List[str]) -> List[str]:
        """
        过滤关键词：移除停用词和单字
        
        Args:
            keywords: 原始关键词列表
            
        Returns:
            过滤后的关键词列表
        """
        filtered = []
        for kw in keywords:
            # 过滤条件：
            # 1. 不在停用词表中
            # 2. 长度大于1（保留多字词）
            # 3. 不是纯数字或纯标点
            if (kw not in self.stopwords and 
                len(kw) > 1 and 
                not kw.isdigit() and
                not all(c in '，。、；：？！…—·《》（）【】""'',.;:?!-_/\\|[]{}()<>' for c in kw)):
                filtered.append(kw)
        
        return filtered
    
    def calculate_tf(self, text: str) -> Dict[str, float]:
        """
        计算词频（TF）
        
        Args:
            text: 输入文本
            
        Returns:
            词频字典 {词: TF值}
        """
        # 分词
        words = jieba.lcut(text)
        
        # 过滤
        words = self.filter_keywords(words)
        
        if not words:
            return {}
        
        # 计算词频
        word_counts = Counter(words)
        total_words = len(words)
        
        # 归一化为 TF 值
        tf_dict = {word: count / total_words for word, count in word_counts.items()}
        
        return tf_dict
    
    def rank_question_keywords(
        self,
        question: str,
        top_k: int = 30
    ) -> List[Tuple[str, float]]:
        """
        对问题关键词进行排序
        
        Args:
            question: 问题文本
            top_k: 返回前 K 个关键词
            
        Returns:
            排序后的关键词列表 [(词, TF值), ...]
        """
        tf_dict = self.calculate_tf(question)
        
        # 按 TF 值降序排序
        ranked = sorted(tf_dict.items(), key=lambda x: x[1], reverse=True)
        
        return ranked[:top_k]
    
    def rank_document_keywords(
        self,
        matched_keywords: List[str],
        node_score: float,
        top_k: int = 30
    ) -> List[Tuple[str, float]]:
        """
        对文档关键词进行排序
        
        Args:
            matched_keywords: 文档中匹配的关键词列表
            node_score: 节点的 BM25 分数
            top_k: 返回前 K 个关键词
            
        Returns:
            排序后的关键词列表 [(词, 权重), ...]
        """
        # 过滤关键词
        filtered = self.filter_keywords(matched_keywords)
        
        if not filtered:
            return []
        
        # 计算词频
        word_counts = Counter(filtered)
        
        # 权重 = 词频 * 节点分数
        weighted = []
        for word, count in word_counts.items():
            weight = count * node_score
            weighted.append((word, weight))
        
        # 按权重降序排序
        ranked = sorted(weighted, key=lambda x: x[1], reverse=True)
        
        return ranked[:top_k]
    
    def merge_and_rank_keywords(
        self,
        question_keywords: List[Tuple[str, float]],
        document_keywords: List[Tuple[str, float]],
        max_display: int = 60
    ) -> List[str]:
        """
        合并并排序问题关键词和文档关键词
        
        策略：按权重降序填充可展示的槽位
        
        Args:
            question_keywords: 问题关键词 [(词, TF值), ...]
            document_keywords: 文档关键词 [(词, 权重), ...]
            max_display: 最大显示数量
            
        Returns:
            排序后的关键词列表
        """
        # 合并所有关键词，去重并保留最高权重
        keyword_weights = {}
        
        # 添加问题关键词（权重 * 1.5，提高问题词的优先级）
        for word, weight in question_keywords:
            keyword_weights[word] = weight * 1.5
        
        # 添加文档关键词（如果已存在，取最大值）
        for word, weight in document_keywords:
            if word in keyword_weights:
                keyword_weights[word] = max(keyword_weights[word], weight)
            else:
                keyword_weights[word] = weight
        
        # 按权重降序排序
        ranked = sorted(keyword_weights.items(), key=lambda x: x[1], reverse=True)
        
        # 返回前 max_display 个关键词
        return [word for word, _ in ranked[:max_display]]


# 全局实例
keyword_ranker = KeywordRanker()
