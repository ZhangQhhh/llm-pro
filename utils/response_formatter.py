# -*- coding: utf-8 -*-
"""
LLM 响应格式化和校验工具
确保输出符合预期的格式规范
"""
import re
from utils.logger import logger


class ResponseFormatter:
    """响应格式化器"""
    
    # 必需的标题
    REQUIRED_SECTIONS = [
        "## 咨询解析",
        "## 综合解答"
    ]
    
    # 咨询解析必需的小标题
    REQUIRED_SUBSECTIONS = [
        "**关键实体**",
        "**核心动作**"
    ]
    
    def validate_format(self, response: str) -> dict:
        """
        验证响应格式
        
        Args:
            response: LLM 响应文本
            
        Returns:
            验证结果字典 {
                "valid": bool,
                "missing_sections": list,
                "missing_subsections": list,
                "has_code_blocks": bool
            }
        """
        result = {
            "valid": True,
            "missing_sections": [],
            "missing_subsections": [],
            "has_code_blocks": False
        }
        
        # 检查必需的主标题
        for section in self.REQUIRED_SECTIONS:
            if section not in response:
                result["valid"] = False
                result["missing_sections"].append(section)
        
        # 检查咨询解析中的小标题
        if "## 咨询解析" in response:
            analysis_section = response.split("## 综合解答")[0]
            for subsection in self.REQUIRED_SUBSECTIONS:
                if subsection not in analysis_section:
                    result["valid"] = False
                    result["missing_subsections"].append(subsection)
        
        # 检查是否有代码块
        if "```" in response:
            result["has_code_blocks"] = True
            result["valid"] = False
        
        return result
    
    def fix_format(self, response: str) -> str:
        """
        修复响应格式
        
        Args:
            response: 原始响应文本
            
        Returns:
            修复后的响应文本
        """
        fixed = response
        
        # 1. 移除代码块符号
        fixed = fixed.replace("```", "")
        
        # 2. 检查并添加缺失的主标题
        if "## 咨询解析" not in fixed:
            logger.warning(" 缺少 '## 咨询解析' 标题，自动添加")
            # 在开头添加
            fixed = "## 咨询解析\n\n" + fixed
        
        if "## 综合解答" not in fixed:
            logger.warning(" 缺少 '## 综合解答' 标题，自动添加")
            # 在中间添加（假设前半部分是解析，后半部分是解答）
            lines = fixed.split('\n')
            mid_point = len(lines) // 2
            lines.insert(mid_point, "\n## 综合解答\n")
            fixed = '\n'.join(lines)
        
        # 3. 检查并添加缺失的小标题
        if "## 咨询解析" in fixed and "**关键实体**" not in fixed:
            logger.warning(" 缺少 '**关键实体**' 小标题，自动添加")
            # 在咨询解析后添加
            fixed = fixed.replace(
                "## 咨询解析\n",
                "## 咨询解析\n\n**关键实体**\n- 待补充\n\n"
            )
        
        if "## 咨询解析" in fixed and "**核心动作**" not in fixed:
            logger.warning(" 缺少 '**核心动作**' 小标题，自动添加")
            # 在关键实体后添加
            if "**关键实体**" in fixed:
                # 找到关键实体后的第一个空行
                parts = fixed.split("**关键实体**")
                if len(parts) > 1:
                    entity_part = parts[1].split('\n\n', 1)
                    if len(entity_part) > 1:
                        fixed = parts[0] + "**关键实体**" + entity_part[0] + "\n\n**核心动作**\n- 待补充\n\n" + entity_part[1]
        
        return fixed
    
    def format_with_template(self, question: str, raw_response: str) -> str:
        """
        使用模板格式化响应
        
        Args:
            question: 用户问题
            raw_response: 原始响应
            
        Returns:
            格式化后的响应
        """
        template = f"""## 咨询解析

**关键实体**
- 待分析

**核心动作**
- 待分析

## 综合解答

{raw_response}

注：以上内容基于业务规定生成，如有疑问请参考具体条款。
"""
        return template
    
    def clean_response(self, response: str) -> str:
        """
        清理响应内容
        
        Args:
            response: 原始响应
            
        Returns:
            清理后的响应
        """
        cleaned = response
        
        # 移除多余的空行（超过2个连续换行）
        while '\n\n\n' in cleaned:
            cleaned = cleaned.replace('\n\n\n', '\n\n')
        
        # 移除代码块符号
        cleaned = cleaned.replace('```', '')
        
        # 移除行首的多余空格
        lines = cleaned.split('\n')
        cleaned_lines = [line.rstrip() for line in lines]
        cleaned = '\n'.join(cleaned_lines)
        
        return cleaned
    
    def process_response(self, response: str, question: str = None) -> str:
        """
        处理响应：验证、修复、清理
        
        Args:
            response: 原始响应
            question: 用户问题（可选）
            
        Returns:
            处理后的响应
        """
        # 1. 清理
        cleaned = self.clean_response(response)
        
        # 2. 验证
        validation = self.validate_format(cleaned)
        
        if not validation["valid"]:
            logger.warning(f" 响应格式不规范: {validation}")
            
            # 3. 修复
            fixed = self.fix_format(cleaned)
            
            logger.info(" 已自动修复响应格式")
            return fixed
        
        return cleaned


# 全局实例
response_formatter = ResponseFormatter()
