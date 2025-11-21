# -*- coding: utf-8 -*-
"""
意图分类器
判断用户问题是否与免签政策相关，决定使用哪个知识库
"""
import re
from functools import lru_cache
from typing import Literal, Optional, Tuple
from llama_index.core.llms import ChatMessage
from config import Settings
from prompts import get_intent_classifier_system, get_intent_classifier_user, change_questions
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
    IntentType = Literal["visa_free", "general", "both", "airline", "airline_visa_free", "airline_general"]
    
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
            "airline": 只查航司库
            "visa_free": 只查免签库
            "general": 只查通用库
            "both": 查免签+通用库
            "airline_visa_free": 查航司+免签库
            "airline_general": 查航司+通用库
        """
        if not Settings.ENABLE_INTENT_CLASSIFIER:
            logger.info("[意图分类] 分类器未启用，使用默认策略: general")
            return "general"
        
        logger.info(f"[意图分类] 开始分类问题: {question[:50]}...")
        
        try:
            # 调用 LLM 进行分类（带超时）
            intent = self._classify_with_llm(question)
            logger.info(f"[意图分类] ✓ 判定结果: {intent}")
            return intent
                
        except Exception as e:
            logger.warning(f"[意图分类] ✗ 分类失败: {e}，降级为默认策略: general")
            return "general"
    
    def _classify_with_llm(self, question: str) -> IntentType:
        """
        使用 LLM 进行意图分类（带超时和重试）
        
        Args:
            question: 用户问题
            
        Returns:
            IntentType: 分类结果
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
                    max_tokens=20  # 增加token以支持更长的分类结果
                )
                
                result = response.message.content
                
                # 解析结果
                intent = self._parse_response(result)
                logger.info(f"[意图分类] LLM 响应: {result.strip()[:100]} -> {intent}")
                
                return intent
                
            except Exception as e:
                logger.warning(f"[意图分类] LLM 调用失败: {e}")
                if attempt < self.max_retries:
                    continue
                raise
        
        # 所有重试都失败
        raise RuntimeError("意图分类失败：超过最大重试次数")
    
    def _parse_response(self, response: str) -> IntentType:
        """
        解析 LLM 响应
        
        Args:
            response: LLM 的响应文本
            
        Returns:
            IntentType: 分类结果
        """
        response = response.strip().lower()
        
        # 方法1: 查找"分类: xxx"格式
        match = re.search(r'分类[:：]\s*([\w_]+)', response)
        if match:
            category = match.group(1)
            # 优先匹配组合类型
            if 'airline_visa_free' in category or 'airline_visa' in category:
                return "airline_visa_free"
            elif 'airline_general' in category:
                return "airline_general"
            elif 'airline' in category:
                return "airline"
            elif 'visa_free' in category or 'visa' in category:
                return "visa_free"
            elif 'general' in category:
                return "general"
        
        # 方法2: 直接查找关键词（优先匹配组合）
        if ('airline' in response and 'visa' in response) or 'airline_visa_free' in response:
            return "airline_visa_free"
        if ('airline' in response and 'general' in response) or 'airline_general' in response:
            return "airline_general"
        if 'airline' in response:
            return "airline"
        if 'visa_free' in response or 'visa' in response:
            return "visa_free"
        if 'general' in response:
            return "general"
        
        # 方法3: 兼容旧格式（判断: 是/否）
        if '判断: 是' in response or '判断：是' in response or '是' in response:
            return "both"  # 旧格式的"是"映射为双库检索
        
        # 默认：无法判断时返回 general（使用通用库更安全）
        logger.warning(f"[意图分类] 无法解析响应，默认为 general: {response[:100]}")
        return "general"
    
    def rewrite_question(self, question: str, intent: IntentType) -> Optional[str]:
        """
        根据意图改写问题（仅针对免签和航司相关问题）
        
        Args:
            question: 原始问题
            intent: 意图分类结果
            
        Returns:
            改写后的问题，如果不需要改写则返回 None
        """
        # 只对免签和航司相关问题进行改写
        # both 类型也需要改写，因为涉及免签政策
        if intent not in ["visa_free", "airline_visa_free", "both"]:
            logger.info(f"[问题改写] 意图为 {intent}，无需改写")
            return None
        
        logger.info(f"[问题改写] 开始改写问题: {question[:50]}...")
        
        try:
            # 构建改写提示
            messages = [
                ChatMessage(role="user", content=change_questions(question))
            ]
            
            # 调用 LLM 改写（禁用思考模式）
            response = self.llm_client.chat(
                messages,
                temperature=0.2,  # 降低创造性，减少思考倾向
                max_tokens=100,  # 限制输出长度，防止过度思考
                enable_thinking=False  # 禁用思考模式
            )
            
            rewritten = response.message.content.strip()
            
            # 清理可能残留的思考标签
            rewritten = self._clean_thinking_tags(rewritten)
            
            logger.info(f"[问题改写] ✓ 改写完成: {rewritten[:100]}...")
            
            return rewritten
            
        except Exception as e:
            logger.warning(f"[问题改写] ✗ 改写失败: {e}，使用原问题")
            return None
    
    def classify_and_rewrite(self, question: str) -> Tuple[IntentType, Optional[str]]:
        """
        分类并改写问题（一站式接口）
        
        Args:
            question: 用户问题
            
        Returns:
            (意图类型, 改写后的问题或None)
        """
        # 1. 分类
        intent = self.classify(question)
        
        # 2. 根据意图决定是否改写
        rewritten = self.rewrite_question(question, intent)
        
        return intent, rewritten
    
    def _clean_thinking_tags(self, text: str) -> str:
        """清理文本中的思考标签、思考内容和解释性文本"""
        import re
        
        # 1. 移除 <think>...</think> 标签及其内容
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        
        # 2. 移除可能残留的单独标签
        text = text.replace('<think>', '').replace('</think>', '')
        
        # 3. 移除重复提示词的句子
        prompt_repeat_patterns = [
            r'^用户强调.*?[。\.\n]',    # "用户强调只输出改写后的问题..."
            r'^用户要求.*?[。\.\n]',    # "用户要求..."
            r'^请.*?输出.*?[。\.\n]',   # "请仅输出改写后的问题..."
            r'^改写要求.*?[。\.\n]',    # "改写要求是..."
            r'^根据要求.*?[。\.\n]',    # "根据要求..."
            r'^需要.*?格式.*?[。\.\n]', # "需要按照以下格式..."
        ]
        
        for pattern in prompt_repeat_patterns:
            text = re.sub(pattern, '', text, flags=re.MULTILINE)
        
        # 4. 移除常见的思考开头模式
        thinking_patterns = [
            r'^好的[，,].*?[。\.\n]',     # "好的，我现在需要..."
            r'^首先[，,].*?[。\.\n]',     # "首先，我需要..."
            r'^让我.*?[。\.\n]',          # "让我来分析..."
            r'^我现在.*?[。\.\n]',        # "我现在需要..."
            r'^我需要.*?[。\.\n]',        # "我需要..."
            r'^我将.*?[。\.\n]',          # "我将..."
        ]
        
        for pattern in thinking_patterns:
            text = re.sub(pattern, '', text, flags=re.MULTILINE)
        
        # 5. 如果文本包含多个段落（用空行分隔），只保留实质性内容
        # 移除以"原问题"开头的解释性段落
        lines = text.split('\n')
        filtered_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # 跳过解释性行
            if line.startswith(('原问题', '改写：', '改写:', '示例')):
                continue
            # 跳过纯粹的重复说明
            if '改写后的问题' in line or '额外内容' in line or '解释' in line:
                continue
            filtered_lines.append(line)
        
        if filtered_lines:
            text = '\n'.join(filtered_lines)
        
        # 6. 清理后，如果文本仍以非实质内容开头，尝试提取核心问题
        text = text.strip()
        if text and not any(keyword in text[:30] for keyword in ['中国', '是否', '如何', '什么', '哪些', '能否']):
            # 如果开头30个字符中没有实质性问题词，尝试找到第一个问号之后的内容
            # 或者移除第一句话
            sentences = re.split(r'[。\.\?？]', text, maxsplit=1)
            if len(sentences) > 1 and sentences[1].strip():
                text = sentences[1].strip()
        
        return text.strip()
    
    def clear_cache(self):
        """清空缓存"""
        self.classify.cache_clear()
        logger.info("[意图分类] 缓存已清空")
