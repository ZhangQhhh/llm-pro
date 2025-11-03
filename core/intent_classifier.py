# -*- coding: utf-8 -*-
"""
意图分类器
判断用户问题是否与免签政策相关，决定使用哪个知识库
"""
import re
from functools import lru_cache
from typing import Literal
from llama_index.core.llms import ChatMessage
from config import Settings
from prompts import get_intent_classifier_system, get_intent_classifier_user
from utils.logger import logger


class IntentClassifier:
    """
    意图分类器
    
    核心特性：
    1. 插件式设计：通过配置开关控制
    2. 防死循环：超时保护、重试限制
    3. 优雅降级：任何失败都返回默认策略
    4. 性能优化：LRU缓存、确定性输出
    """
    
    # 分类结果类型
    IntentType = Literal["visa_free", "general", "both"]
    
    def __init__(self, llm_client):
        """
        初始化意图分类器
        
        Args:
            llm_client: LLM 客户端（用于意图分类）
        """
        self.llm_client = llm_client
        self.timeout = Settings.INTENT_CLASSIFIER_TIMEOUT
        self.max_retries = 1  # 最多重试1次
        
        logger.info(f"意图分类器初始化完成 | 超时: {self.timeout}s | 最大重试: {self.max_retries}")
    
    @lru_cache(maxsize=100)
    def classify(self, question: str) -> IntentType:
        """
        分类用户问题的意图（带缓存）
        
        Args:
            question: 用户问题
            
        Returns:
            "visa_free": 只查免签库
            "general": 只查通用库
            "both": 查两个库
        """
        if not Settings.ENABLE_INTENT_CLASSIFIER:
            logger.info("[意图分类] 分类器未启用，使用默认策略: general")
            return "general"
        
        logger.info(f"[意图分类] 开始分类问题: {question[:50]}...")
        
        try:
            # 调用 LLM 进行分类（带超时）
            is_visa_related = self._classify_with_llm(question)
            
            if is_visa_related:
                logger.info("[意图分类] ✓ 判定为免签相关 -> 策略: both（双库检索）")
                return "both"
            else:
                logger.info("[意图分类] ✓ 判定为非免签相关 -> 策略: general（通用库）")
                return "general"
                
        except Exception as e:
            logger.warning(f"[意图分类] ✗ 分类失败: {e}，降级为默认策略: general")
            return "general"
    
    def _classify_with_llm(self, question: str) -> bool:
        """
        使用 LLM 进行意图分类（带超时和重试）
        
        Args:
            question: 用户问题
            
        Returns:
            True: 免签相关
            False: 非免签相关
        """
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(f"[意图分类] 重试 {attempt}/{self.max_retries}")
                
                # 构建消息
                messages = [
                    ChatMessage(role="system", content=get_intent_classifier_system()),
                    ChatMessage(role="user", content=get_intent_classifier_user(question))
                ]
                
                # 同步调用 LLM（简化版，不使用异步）
                response = self.llm_client.chat(
                    messages,
                    temperature=0.0,
                    max_tokens=10  # 只需要很少的 token
                )
                
                result = response.message.content
                
                # 解析结果
                is_visa_related = self._parse_response(result)
                logger.info(f"[意图分类] LLM 响应: {result.strip()[:100]} -> {is_visa_related}")
                
                return is_visa_related
                
            except Exception as e:
                logger.warning(f"[意图分类] LLM 调用失败: {e}")
                if attempt < self.max_retries:
                    continue
                raise
        
        # 所有重试都失败
        raise RuntimeError("意图分类失败：超过最大重试次数")
    
    def _parse_response(self, response: str) -> bool:
        """
        解析 LLM 响应
        
        Args:
            response: LLM 的响应文本
            
        Returns:
            True: 免签相关
            False: 非免签相关
        """
        response = response.strip().lower()
        
        # 方法1: 查找"判断: 是/否"格式
        match = re.search(r'判断[:：]\s*([是否])', response)
        if match:
            return match.group(1) == '是'
        
        # 方法2: 直接查找关键词
        if '判断: 是' in response or '判断：是' in response:
            return True
        if '判断: 否' in response or '判断：否' in response:
            return False
        
        # 方法3: 查找"是"或"否"（宽松匹配）
        if '是' in response and '否' not in response:
            return True
        if '否' in response and '是' not in response:
            return False
        
        # 默认：无法判断时返回 False（使用通用库更安全）
        logger.warning(f"[意图分类] 无法解析响应，默认为非免签: {response[:100]}")
        return False
    
    def clear_cache(self):
        """清空缓存"""
        self.classify.cache_clear()
        logger.info("[意图分类] 缓存已清空")
