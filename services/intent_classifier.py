# -*- coding: utf-8 -*-
"""
意图识别服务
用于快速判断用户问题是否与免签政策相关
"""
from typing import Optional
from config import Settings
from utils.logger import logger


class IntentClassifier:
    """意图分类器 - 判断问题是否与免签政策相关"""

    def __init__(self, llm_service=None):
        """
        初始化意图分类器
        
        Args:
            llm_service: LLM服务实例（可选，用于更精确的意图识别）
        """
        self.llm_service = llm_service
        self.visa_keywords = Settings.VISA_FREE_KEYWORDS
        logger.info(f"意图分类器初始化完成，关键词数量: {len(self.visa_keywords)}")

    def is_visa_related(self, question: str) -> bool:
        """
        判断问题是否与免签政策相关
        
        使用快速关键词匹配策略，确保低延迟
        
        Args:
            question: 用户问题
            
        Returns:
            True: 问题与免签相关
            False: 问题与免签无关
        """
        if not question or not question.strip():
            return False
        
        question_lower = question.lower()
        
        # 关键词匹配
        for keyword in self.visa_keywords:
            if keyword in question_lower:
                logger.info(f"检测到免签相关问题，匹配关键词: '{keyword}'")
                return True
        
        logger.debug(f"问题未匹配到免签关键词: '{question[:50]}...'")
        return False

    def is_visa_related_with_llm(self, question: str, llm_id: Optional[str] = None) -> bool:
        """
        使用LLM进行更精确的意图识别（可选，延迟较高）
        
        Args:
            question: 用户问题
            llm_id: 使用的LLM模型ID
            
        Returns:
            True: 问题与免签相关
            False: 问题与免签无关
        """
        if not self.llm_service:
            logger.warning("LLM服务未初始化，回退到关键词匹配")
            return self.is_visa_related(question)
        
        try:
            # 构建简单的分类提示词
            prompt = f"""请判断以下问题是否与签证、免签政策、入境政策相关。
只需回答"是"或"否"，不要解释。

问题：{question}

回答："""
            
            # 获取LLM客户端
            llm = self.llm_service.get_client(llm_id or Settings.DEFAULT_LLM_ID)
            
            # 调用LLM（非流式）
            response = llm.complete(prompt)
            answer = response.text.strip().lower()
            
            # 判断结果
            is_related = "是" in answer or "yes" in answer
            
            logger.info(f"LLM意图识别结果: {is_related} (原始回答: {answer})")
            return is_related
            
        except Exception as e:
            logger.error(f"LLM意图识别失败，回退到关键词匹配: {e}")
            return self.is_visa_related(question)

    def get_classification_info(self, question: str) -> dict:
        """
        获取分类详细信息（用于调试和日志）
        
        Args:
            question: 用户问题
            
        Returns:
            包含分类结果和匹配信息的字典
        """
        is_related = self.is_visa_related(question)
        matched_keywords = []
        
        if is_related:
            question_lower = question.lower()
            for keyword in self.visa_keywords:
                if keyword in question_lower:
                    matched_keywords.append(keyword)
        
        return {
            "is_visa_related": is_related,
            "matched_keywords": matched_keywords,
            "method": "keyword_matching"
        }
