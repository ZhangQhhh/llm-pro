# -*- coding: utf-8 -*-
"""
数据分析 Handler
处理统计数据的趋势分析请求
"""
from typing import Dict, Any, Generator, Tuple, Optional
import time
import json
from utils import logger, clean_for_sse_text
from utils.data_stats_formatter import format_data_stats, validate_data_stats
from prompts import get_data_stats_system, get_data_stats_user
from utils.knowledge_utils.llm_stream_parser import parse_thinking_stream, parse_normal_stream
from core.llm_wrapper import LLMStreamWrapper


class DataAnalysisHandler:
    """数据分析处理器"""
    
    def __init__(self, llm_service):
        """
        初始化数据分析处理器
        
        Args:
            llm_service: LLM 服务实例
        """
        self.llm_service = llm_service
    
    def analyze(
        self,
        stats: Dict[str, Any],
        llm_id: str,
        enable_thinking: bool = False,
        stream: bool = True,
        max_length: int = None
    ) -> Generator[Tuple[str, str], None, None]:
        """
        分析统计数据并生成趋势摘要
        
        Args:
            stats: 统计数据字典
            llm_id: LLM ID
            enable_thinking: 是否启用思考模式
            stream: 是否流式输出
            max_length: 摘要最大字数，None 时使用配置值
            
        Yields:
            (消息类型, 内容) 元组
            - 'ERROR': 错误信息
            - 'THINK': 思考内容（仅在 enable_thinking=True 时）
            - 'CONTENT': 正文内容
            - 'DONE': 完成信号
        """
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 1. 参数校验
            if not stats:
                yield ('ERROR', '缺少必需参数：data')
                yield ('DONE', '')
                return
            
            # 验证数据有效性
            is_valid, error_msg = validate_data_stats(stats)
            if not is_valid:
                yield ('ERROR', f'数据验证失败：{error_msg}')
                yield ('DONE', '')
                return
            
            # 2. 格式化数据
            try:
                data_block = format_data_stats(stats)
                logger.info(f"数据格式化完成，长度: {len(data_block)} 字符")
            except Exception as e:
                logger.error(f"数据格式化失败: {e}", exc_info=True)
                yield ('ERROR', f'数据格式化失败：{str(e)}')
                yield ('DONE', '')
                return
            
            # 3. 构造 Prompt
            # 使用配置或请求参数中的长度限制
            from config import Settings
            summary_max_length = max_length or Settings.DATA_ANALYSIS_MAX_LENGTH
            
            system_prompt_parts = get_data_stats_system(max_length=summary_max_length)
            user_prompt_parts = get_data_stats_user(data_block, max_length=summary_max_length)
            
            system_prompt = "\n".join(system_prompt_parts)
            user_prompt = "\n".join(user_prompt_parts)
            
            logger.info(f"开始数据趋势分析 | LLM: {llm_id} | 思考模式: {enable_thinking} | 流式: {stream}")
            
            # 4. 调用 LLM
            if stream:
                # 流式输出
                yield from self._call_llm_stream(
                    llm_id=llm_id,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    enable_thinking=enable_thinking
                )
            else:
                # 同步模式
                yield from self._call_llm_sync(
                    llm_id=llm_id,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    enable_thinking=enable_thinking,
                    start_time=start_time
                )
            
            # 5. 发送完成信号
            # 在流式模式下，可以在 DONE 前发送聚合结果（可选）
            if stream:
                # 计算耗时
                elapsed_time = time.time() - start_time
                summary_json = {
                    "model_id": llm_id,
                    "elapsed_time": round(elapsed_time, 2),
                    "max_length": summary_max_length
                }
                yield ('META', json.dumps(summary_json, ensure_ascii=False))
            
            yield ('DONE', '')
            
        except Exception as e:
            error_msg = f"数据分析处理错误: {str(e)}"
            logger.error(error_msg, exc_info=True)
            yield ('ERROR', error_msg)
            yield ('DONE', '')
    
    def _call_llm_stream(
        self,
        llm_id: str,
        system_prompt: str,
        user_prompt: str,
        enable_thinking: bool
    ) -> Generator[Tuple[str, str], None, None]:
        """
        流式调用 LLM
        
        Args:
            llm_id: LLM ID
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            enable_thinking: 是否启用思考模式
            
        Yields:
            (消息类型, 内容) 元组
        """
        try:
            # 获取 LLM 实例
            llm = self.llm_service.get_client(llm_id)
            if not llm:
                raise ValueError(f"无法获取 LLM 实例: {llm_id}")
            
            # 调用 LLM 流式接口（LLMStreamWrapper 是静态封装）
            response_stream = LLMStreamWrapper.stream(
                llm=llm,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                enable_thinking=enable_thinking
            )
            
            # 根据思考模式选择解析器
            if enable_thinking:
                parser = parse_thinking_stream(response_stream)
            else:
                parser = parse_normal_stream(response_stream)
            
            # 流式输出
            for msg_type, content in parser:
                yield (msg_type, content)
                
        except Exception as e:
            error_msg = f"LLM 调用失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            yield ('ERROR', error_msg)
    
    def _call_llm_sync(
        self,
        llm_id: str,
        system_prompt: str,
        user_prompt: str,
        enable_thinking: bool,
        start_time: float
    ) -> Generator[Tuple[str, str], None, None]:
        """
        同步调用 LLM（聚合所有 token 后返回）
        
        Args:
            llm_id: LLM ID
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            enable_thinking: 是否启用思考模式
            start_time: 开始时间戳
            
        Yields:
            (消息类型, 内容) 元组
        """
        try:
            # 获取 LLM 实例
            llm = self.llm_service.get_client(llm_id)
            if not llm:
                raise ValueError(f"无法获取 LLM 实例: {llm_id}")
            
            # 调用流式接口并聚合结果
            response_stream = LLMStreamWrapper.stream(
                llm=llm,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                enable_thinking=enable_thinking
            )
            
            # 根据思考模式选择解析器
            if enable_thinking:
                parser = parse_thinking_stream(response_stream)
            else:
                parser = parse_normal_stream(response_stream)
            
            # 聚合所有内容
            think_content = []
            content_parts = []
            
            for msg_type, content in parser:
