# -*- coding: utf-8 -*-
"""
子问题分解器
将复杂查询分解为多个子问题，并整合检索结果
使用LlamaIndex原生SubQuestionQueryEngine
"""
import json
import re
import time
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from llama_index.core.query_engine import SubQuestionQueryEngine
from llama_index.core.tools import QueryEngineTool, ToolMetadata
from llama_index.core import QueryBundle
from utils import logger
from config.settings import Settings as AppSettings
from prompts import (
    get_subquestion_decomposition_system,
    get_subquestion_decomposition_user,
    get_subquestion_synthesis_system,
    get_subquestion_synthesis_user,
    get_history_compression_system,
    get_history_compression_user
)


class SubQuestionDecomposer:
    """子问题分解器（基于LlamaIndex）"""
    
    def __init__(self, llm_service, retriever, reranker, index=None):
        """
        初始化子问题分解器
        
        Args:
            llm_service: LLM服务实例
            retriever: 检索器实例
            reranker: 重排序器实例
            index: VectorStoreIndex实例（用于创建QueryEngine）
        """
        self.llm_service = llm_service
        self.retriever = retriever
        self.reranker = reranker
        self.index = index
        self.enabled = AppSettings.ENABLE_SUBQUESTION_DECOMPOSITION
        self.engine_type = AppSettings.SUBQUESTION_ENGINE_TYPE  # custom 或 llamaindex
        
        # 创建LlamaIndex SubQuestionQueryEngine（如果启用且有index）
        self.sub_question_engine = None
        if self.enabled and self.engine_type == "llamaindex" and index:
            try:
                self._init_sub_question_engine()
            except Exception as e:
                logger.warning(f"初始化SubQuestionQueryEngine失败: {e}，将回退到自定义流程")
                self.engine_type = "custom"  # 回退到自定义模式
        
        # 健康度指标
        self.metrics = {
            'total_queries': 0,
            'decomposed_queries': 0,
            'fallback_count': 0,
            'empty_results_count': 0,
            'timeout_count': 0,
            'error_count': 0
        }
        
        engine_name = "LlamaIndex原生" if self.engine_type == "llamaindex" else "自定义流程"
        logger.info(
            f"子问题分解器初始化完成 | "
            f"状态: {'启用' if self.enabled else '禁用'} | "
            f"引擎: {engine_name}"
        )
    
    def _init_sub_question_engine(self):
        """初始化LlamaIndex SubQuestionQueryEngine"""
        try:
            # 创建查询引擎工具
            query_engine = self.index.as_query_engine(
                similarity_top_k=AppSettings.RETRIEVAL_TOP_K
            )
            
            query_engine_tool = QueryEngineTool(
                query_engine=query_engine,
                metadata=ToolMetadata(
                    name="knowledge_base",
                    description="知识库检索工具，用于回答各类问题"
                )
            )
            
            # 创建SubQuestionQueryEngine
            # 获取我们自己的LLM客户端，而不是使用LlamaIndex默认的OpenAI
            llm_client = self.llm_service.get_client(AppSettings.SUBQUESTION_DECOMP_LLM_ID)
            self.sub_question_engine = SubQuestionQueryEngine.from_defaults(
                query_engine_tools=[query_engine_tool],
                llm=llm_client,
                use_async=False
            )
            
            logger.info("LlamaIndex SubQuestionQueryEngine初始化成功")
            
        except Exception as e:
            logger.error(f"初始化SubQuestionQueryEngine失败: {e}", exc_info=True)
            self.sub_question_engine = None
    
    def should_decompose(self, query: str) -> bool:
        """
        判断查询是否应该分解
        
        Args:
            query: 用户查询
            
        Returns:
            是否应该分解
        """
        if not self.enabled:
            return False
        
        # 检查查询长度
        if len(query) < AppSettings.SUBQUESTION_COMPLEXITY_THRESHOLD:
            logger.debug(f"查询长度不足，跳过分解 | 长度: {len(query)}")
            return False
        
        # 检查命名实体数量（简单启发式：检测关键词数量）
        if AppSettings.SUBQUESTION_ENABLE_ENTITY_CHECK:
            # 简单的实体检测：统计逗号、顿号、"和"、"以及"等分隔符
            entity_indicators = len(re.findall(r'[，、和以及与及]', query))
            if entity_indicators < AppSettings.SUBQUESTION_MIN_ENTITIES:
                logger.debug(f"实体数量不足，跳过分解 | 实体指标: {entity_indicators}")
                return False
        
        return True
    
    def decompose_query(
        self, 
        query: str, 
        conversation_history: Optional[List[Dict]] = None
    ) -> Tuple[bool, List[str]]:
        """
        分解查询为子问题
        
        Args:
            query: 用户查询
            conversation_history: 对话历史（用于多轮场景）
            
        Returns:
            (是否需要分解, 子问题列表)
        """
        self.metrics['total_queries'] += 1
        
        # 检查是否应该分解
        if not self.should_decompose(query):
            return False, []
        
        try:
            # 压缩对话历史（如果有）
            conversation_summary = ""
            if conversation_history:
                conversation_summary = self._compress_history(conversation_history)
            
            # 检查是否使用LLM判断
            if not AppSettings.SUBQUESTION_USE_LLM_JUDGE:
                # 强制分解模式：跳过LLM判断，直接生成子问题
                logger.info(f"[子问题分解] 强制分解模式 | 查询: {query[:50]}...")
                sub_questions = self._force_decompose(query, conversation_summary)
                
                if sub_questions:
                    self.metrics['decomposed_queries'] += 1
                    logger.info(
                        f"[子问题分解] 强制分解成功 | 子问题数: {len(sub_questions)} | "
                        f"子问题: {sub_questions}"
                    )
                    return True, sub_questions
                else:
                    logger.info("[子问题分解] 强制分解失败，使用原查询")
                    return False, []
            
            # 智能模式：使用LLM判断是否需要分解
            logger.info(f"[子问题分解] 智能判断模式 | 查询: {query[:50]}...")
            
            # 构建提示词
            system_prompt = "\n".join(get_subquestion_decomposition_system())
            user_prompt = get_subquestion_decomposition_user(query, conversation_summary)
            
            # 调用LLM进行分解
            start_time = time.time()
            
            llm = self.llm_service.get_client(AppSettings.SUBQUESTION_DECOMP_LLM_ID)
            logger.debug(f"[子问题分解] 使用LLM: {AppSettings.SUBQUESTION_DECOMP_LLM_ID}")
            
            # 使用超时保护
            logger.debug(f"[子问题分解] 调用LLM | 超时设置: {AppSettings.SUBQUESTION_DECOMP_TIMEOUT}s")
            response = self._call_llm_with_timeout(
                llm,
                system_prompt,
                user_prompt,
                timeout=AppSettings.SUBQUESTION_DECOMP_TIMEOUT
            )
            
            elapsed = time.time() - start_time
            logger.info(f"[子问题分解] LLM响应完成 | 耗时: {elapsed:.2f}s")
            logger.debug(f"[子问题分解] LLM原始响应: {response[:200]}...")
            
            # 解析响应
            need_decompose, sub_questions = self._parse_decomposition_response(response)
            
            if need_decompose:
                self.metrics['decomposed_queries'] += 1
                logger.info(
                    f"[子问题分解] 分解成功 | 子问题数: {len(sub_questions)} | "
                    f"子问题: {sub_questions}"
                )
            else:
                logger.info("[子问题分解] 无需分解，使用原查询")
            
            return need_decompose, sub_questions
            
        except TimeoutError as te:
            self.metrics['timeout_count'] += 1
            logger.warning(
                f"[子问题分解] LLM调用超时，回退到标准检索 | "
                f"超时阈值: {AppSettings.SUBQUESTION_DECOMP_TIMEOUT}s | "
                f"错误: {te}"
            )
            return False, []
        except Exception as e:
            self.metrics['error_count'] += 1
            logger.error(
                f"[子问题分解] 分解失败 | "
                f"错误类型: {type(e).__name__} | "
                f"错误信息: {str(e)}", 
                exc_info=True
            )
            if AppSettings.SUBQUESTION_FALLBACK_ON_ERROR:
                logger.info("[子问题分解] 启用错误回退，使用标准检索")
                return False, []
            raise
    
    def retrieve_with_decomposition(
        self,
        query: str,
        rerank_top_n: int,
        conversation_history: Optional[List[Dict]] = None,
        retriever=None
    ) -> Tuple[List, Dict]:
        """
        使用子问题分解进行检索
        
        Args:
            query: 用户查询
            rerank_top_n: 重排序返回数量
            conversation_history: 对话历史
            retriever: 可选的检索器（用于意图路由后的专库检索）
            
        Returns:
            (检索节点列表, 元数据字典)
        """
        # 使用传入的retriever或默认retriever
        active_retriever = retriever if retriever is not None else self.retriever
        
        # 根据引擎类型选择不同的处理方式
        if self.engine_type == "llamaindex" and self.sub_question_engine:
            return self._retrieve_with_llamaindex(query, rerank_top_n)
        else:
            return self._retrieve_with_custom(query, rerank_top_n, conversation_history, active_retriever)
    
    def _retrieve_with_llamaindex(self, query: str, rerank_top_n: int) -> Tuple[List, Dict]:
        """
        使用LlamaIndex原生SubQuestionQueryEngine进行检索
        
        Args:
            query: 用户查询
            rerank_top_n: 重排序返回数量
            
        Returns:
            (检索节点列表, 元数据字典)
        """
        try:
            logger.info(f"[子问题检索-LlamaIndex] 使用LlamaIndex原生引擎: {query[:50]}...")
            
            # 使用LlamaIndex SubQuestionQueryEngine
            response = self.sub_question_engine.query(query)
            
            # 提取节点
            nodes = response.source_nodes[:rerank_top_n] if hasattr(response, 'source_nodes') else []
            
            # 构建元数据
            metadata = {
                'decomposed': True,
                'engine': 'llamaindex',
                'sub_questions': [],  # LlamaIndex不暴露子问题
                'sub_results': [],
                'response': str(response)
            }
            
            logger.info(f"[子问题检索-LlamaIndex] 检索完成 | 返回节点数: {len(nodes)}")
            return nodes, metadata
            
        except Exception as e:
            logger.error(f"[子问题检索-LlamaIndex] 检索失败: {e}", exc_info=True)
            # 回退到标准检索
            nodes = self._standard_retrieve(query, rerank_top_n, self.retriever)
            metadata = {
                'decomposed': False,
                'engine': 'llamaindex',
                'fallback_reason': 'llamaindex_error',
                'error': str(e)
            }
            return nodes, metadata
    
    def _retrieve_with_custom(self, query: str, rerank_top_n: int, conversation_history: Optional[List[Dict]], active_retriever) -> Tuple[List, Dict]:
        """
        使用自定义流程进行子问题分解和检索
        
        Args:
            query: 用户查询
            rerank_top_n: 重排序返回数量
            conversation_history: 对话历史
            active_retriever: 活动检索器
            
        Returns:
            (检索节点列表, 元数据字典)
        """
        # 尝试分解
        need_decompose, sub_questions = self.decompose_query(query, conversation_history)
        
        # 如果不需要分解，使用标准检索
        if not need_decompose or not sub_questions:
            logger.info("[子问题检索] 使用标准检索流程")
            nodes = self._standard_retrieve(query, rerank_top_n, active_retriever)
            metadata = {
                'decomposed': False,
                'sub_questions': [],
                'sub_results': []
            }
            return nodes, metadata
        
        # 执行子问题检索
        logger.info(f"[子问题检索] 开始并行检索 {len(sub_questions)} 个子问题")
        sub_results = self._parallel_retrieve_subquestions(sub_questions, rerank_top_n, active_retriever)
        
        # 检查健康度
        empty_count = sum(1 for r in sub_results if not r['nodes'])
        if empty_count > AppSettings.SUBQUESTION_MAX_EMPTY_RESULTS:
            self.metrics['empty_results_count'] += 1
            logger.warning(
                f"[子问题检索] 空结果过多，回退到标准检索 | "
                f"空结果数: {empty_count}/{len(sub_results)}"
            )
            self.metrics['fallback_count'] += 1
            nodes = self._standard_retrieve(query, rerank_top_n, active_retriever)
            metadata = {
                'decomposed': False,
                'sub_questions': sub_questions,
                'sub_results': [],
                'fallback_reason': 'too_many_empty_results'
            }
            return nodes, metadata
        
        # 合并子问题结果
        merged_nodes = self._merge_subquestion_results(sub_results, rerank_top_n)
        
        # 生成子问题答案（使用 LLM 基于检索上下文）
        sub_answers = []
        logger.info(f"[子问题答案生成] 开始为 {len(sub_results)} 个子问题生成答案")
        
        for result in sub_results:
            if result['nodes']:
                try:
                    # 调用 LLM 生成答案
                    sub_answer = self._generate_sub_answer(
                        sub_question=result['sub_question'],
                        nodes=result['nodes'][:3]  # 使用 top 3 节点作为上下文
                    )
                    
                    if sub_answer:
                        sub_answers.append({
                            'sub_question': result['sub_question'],
                            'answer': sub_answer
                        })
                        logger.info(f"[子问题答案] 生成成功: {result['sub_question'][:30]}... | 长度: {len(sub_answer)}")
                    else:
                        # LLM 返回空，使用检索片段
                        fallback_answer = result['nodes'][0].node.get_content()[:200]
                        sub_answers.append({
                            'sub_question': result['sub_question'],
                            'answer': fallback_answer
                        })
                        logger.warning(f"[子问题答案] LLM返回空，使用检索片段")
                        
                except Exception as e:
                    logger.error(f"[子问题答案] 生成失败: {result['sub_question'][:30]}... | 错误: {e}")
                    # 回退到检索片段
                    fallback_answer = result['nodes'][0].node.get_content()[:200]
                    sub_answers.append({
                        'sub_question': result['sub_question'],
                        'answer': fallback_answer
                    })
        
        # 构建元数据
        metadata = {
            'decomposed': True,
            'sub_questions': sub_questions,
            'sub_results': [
                {
                    'sub_question': r['sub_question'],
                    'node_count': len(r['nodes']),
                    'top_score': r['nodes'][0].score if r['nodes'] else 0.0
                }
                for r in sub_results
            ],
            'sub_answers': sub_answers  # 添加子答案用于后续合成
        }
        
        logger.info(
            f"[子问题检索] 检索完成 | 合并后节点数: {len(merged_nodes)} | "
            f"子问题数: {len(sub_questions)}"
        )
        
        return merged_nodes, metadata
    
    def _compress_history(self, conversation_history: List[Dict]) -> str:
        """
        压缩对话历史（带Token限制）
        
        Args:
            conversation_history: 对话历史列表
            
        Returns:
            压缩后的摘要
        """
        try:
            # 只取最近N轮
            recent_history = conversation_history[-AppSettings.SUBQUESTION_HISTORY_COMPRESS_TURNS:]
            
            if not recent_history:
                return ""
            
            # Token限制：截断历史以避免超窗
            max_tokens = AppSettings.SUBQUESTION_HISTORY_MAX_TOKENS
            truncated_history = self._truncate_history_by_tokens(recent_history, max_tokens)
            
            if not truncated_history:
                logger.warning("[历史压缩] 历史内容为空，跳过压缩")
                return ""
            
            # 构建提示词
            system_prompt = "\n".join(get_history_compression_system())
            user_prompt = get_history_compression_user(truncated_history)
            
            # 调用LLM
            llm = self.llm_service.get_client(AppSettings.SUBQUESTION_DECOMP_LLM_ID)
            summary = self._call_llm_with_timeout(llm, system_prompt, user_prompt, timeout=5)
            
            logger.debug(
                f"[历史压缩] 压缩完成 | "
                f"原始轮数: {len(recent_history)} | "
                f"截断后轮数: {len(truncated_history)} | "
                f"摘要长度: {len(summary)}"
            )
            return summary
            
        except Exception as e:
            logger.warning(f"[历史压缩] 压缩失败: {e}")
            return ""
    
    def _truncate_history_by_tokens(self, history: List[Dict], max_tokens: int) -> List[Dict]:
        """
        按Token数截断历史对话
        
        Args:
            history: 对话历史列表
            max_tokens: 最大Token数
            
        Returns:
            截断后的历史列表
        """
        # 简单估算：中文约1.5字符/token，英文约4字符/token
        # 保守估计：2字符/token
        chars_per_token = 2
        max_chars = max_tokens * chars_per_token
        
        truncated = []
        total_chars = 0
        
        # 从最新的对话开始累加
        for turn in reversed(history):
            content = turn.get('content', '')
            turn_chars = len(content)
            
            if total_chars + turn_chars > max_chars:
                # 如果加上这轮会超限，尝试部分截断
                remaining_chars = max_chars - total_chars
                if remaining_chars > 50:  # 至少保留50字符
                    truncated_turn = turn.copy()
                    truncated_turn['content'] = content[:remaining_chars] + "..."
                    truncated.insert(0, truncated_turn)
                break
            
            truncated.insert(0, turn)
            total_chars += turn_chars
        
        if len(truncated) < len(history):
            logger.debug(
                f"[历史截断] 原始轮数: {len(history)} | "
                f"截断后轮数: {len(truncated)} | "
                f"总字符数: {total_chars}/{max_chars}"
            )
        
        return truncated
    
    def _force_decompose(self, query: str, conversation_summary: str = "") -> List[str]:
        """
        强制分解模式：直接调用LLM生成子问题，不判断是否需要分解
        
        Args:
            query: 用户查询
            conversation_summary: 对话历史摘要
            
        Returns:
            子问题列表
        """
        try:
            # 使用强制分解提示词
            from prompts import get_subquestion_force_decomposition_system, get_subquestion_force_decomposition_user
            
            system_prompt = "\n".join(get_subquestion_force_decomposition_system())
            user_prompt = get_subquestion_force_decomposition_user(query, conversation_summary)
            
            # 调用LLM
            llm = self.llm_service.get_client(AppSettings.SUBQUESTION_DECOMP_LLM_ID)
            response = self._call_llm_with_timeout(
                llm,
                system_prompt,
                user_prompt,
                timeout=AppSettings.SUBQUESTION_DECOMP_TIMEOUT
            )
            
            # 解析子问题
            sub_questions = self._parse_force_decomposition_response(response)
            return sub_questions
            
        except Exception as e:
            logger.error(f"[子问题分解] 强制分解失败: {e}", exc_info=True)
            return []
    
    def _parse_force_decomposition_response(self, response: str) -> List[str]:
        """
        解析强制分解响应（只返回子问题列表）
        
        Args:
            response: LLM响应
            
        Returns:
            子问题列表
        """
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{[^{}]*"sub_questions"[^{}]*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                sub_questions = data.get('sub_questions', [])
                
                # 过滤和验证
                sub_questions = [q.strip() for q in sub_questions if q and len(q.strip()) > 5]
                sub_questions = sub_questions[:AppSettings.SUBQUESTION_MAX_DEPTH]
                
                return sub_questions
            
            # 如果没有JSON，尝试按行解析
            lines = [line.strip() for line in response.split('\n') if line.strip()]
            sub_questions = []
            for line in lines:
                # 移除序号和标记
                line = re.sub(r'^\d+[\.\)、]\s*', '', line)
                line = re.sub(r'^[-*]\s*', '', line)
                if len(line) > 5 and '?' in line or '？' in line:
                    sub_questions.append(line)
                    if len(sub_questions) >= AppSettings.SUBQUESTION_MAX_DEPTH:
                        break
            
            return sub_questions
            
        except Exception as e:
            logger.error(f"[子问题分解] 解析强制分解响应失败: {e}")
            return []
    
    def _call_llm_with_timeout(
        self, 
        llm, 
        system_prompt: str, 
        user_prompt: str, 
        timeout: int
    ) -> str:
        """
        带超时保护的LLM调用
        
        Args:
            llm: LLM实例
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            timeout: 超时时间（秒）
            
        Returns:
            LLM响应文本
        """
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
        from llama_index.core.llms import ChatMessage, MessageRole
        
        def _call():
            messages = [
                ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
                ChatMessage(role=MessageRole.USER, content=user_prompt)
            ]
            response = llm.chat(messages)
            return response.message.content
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_call)
            try:
                return future.result(timeout=timeout)
            except FutureTimeoutError:
                raise TimeoutError(f"LLM调用超时 ({timeout}s)")
    
    def _parse_decomposition_response(self, response: str) -> Tuple[bool, List[str]]:
        """
        解析分解响应
        
        Args:
            response: LLM响应
            
        Returns:
            (是否需要分解, 子问题列表)
        """
        try:
            # 尝试提取JSON
            json_match = re.search(r'\{[^{}]*"need_decompose"[^{}]*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
            else:
                data = json.loads(response)
            
            need_decompose = data.get('need_decompose', False)
            sub_questions = data.get('sub_questions', [])
            
            # 限制子问题数量
            if len(sub_questions) > AppSettings.SUBQUESTION_MAX_DEPTH:
                logger.warning(
                    f"[子问题分解] 子问题数量超限，截断 | "
                    f"原数量: {len(sub_questions)} | 限制: {AppSettings.SUBQUESTION_MAX_DEPTH}"
                )
                sub_questions = sub_questions[:AppSettings.SUBQUESTION_MAX_DEPTH]
            
            return need_decompose, sub_questions
            
        except Exception as e:
            logger.error(f"[子问题分解] 解析响应失败: {e} | 响应: {response[:200]}")
            return False, []
    
    def _standard_retrieve(self, query: str, rerank_top_n: int, retriever=None) -> List:
        """
        标准检索流程
        
        Args:
            query: 查询
            rerank_top_n: 重排序返回数量
            retriever: 可选的检索器
            
        Returns:
            检索节点列表
        """
        from llama_index.core import QueryBundle
        
        # 使用传入的retriever或默认retriever
        active_retriever = retriever if retriever is not None else self.retriever
        
        # 初始检索
        retrieved_nodes = active_retriever.retrieve(query)
        
        # 重排序
        reranker_input = retrieved_nodes[:AppSettings.RERANKER_INPUT_TOP_N]
        if reranker_input:
            reranked_nodes = self.reranker.postprocess_nodes(
                reranker_input,
                query_bundle=QueryBundle(query)
            )
            return reranked_nodes[:rerank_top_n]
        
        return []
    
    def _parallel_retrieve_subquestions(
        self, 
        sub_questions: List[str], 
        rerank_top_n: int,
        retriever=None
    ) -> List[Dict]:
        """
        并行检索多个子问题
        
        Args:
            sub_questions: 子问题列表
            rerank_top_n: 每个子问题的重排序返回数量
            retriever: 可选的检索器
            
        Returns:
            子问题检索结果列表
        """
        results = []
        
        # 使用线程池并行检索
        with ThreadPoolExecutor(max_workers=min(len(sub_questions), 3)) as executor:
            futures = {
                executor.submit(self._retrieve_single_subquestion, sq, rerank_top_n, retriever): sq
                for sq in sub_questions
            }
            
            for future in as_completed(futures):
                sub_q = futures[future]
                try:
                    nodes = future.result()
                    results.append({
                        'sub_question': sub_q,
                        'nodes': nodes
                    })
                    logger.debug(f"[子问题检索] 完成: {sub_q} | 节点数: {len(nodes)}")
                except Exception as e:
                    logger.error(f"[子问题检索] 失败: {sub_q} | 错误: {e}")
                    results.append({
                        'sub_question': sub_q,
                        'nodes': []
                    })
        
        # 按原始顺序排序
        results.sort(key=lambda x: sub_questions.index(x['sub_question']))
        return results
    
    def _retrieve_single_subquestion(self, sub_question: str, rerank_top_n: int, retriever=None) -> List:
        """
        检索单个子问题
        
        Args:
            sub_question: 子问题
            rerank_top_n: 重排序返回数量
            retriever: 可选的检索器
            
        Returns:
            检索节点列表
        """
        return self._standard_retrieve(sub_question, rerank_top_n, retriever)
    
    def _merge_subquestion_results(
        self, 
        sub_results: List[Dict], 
        final_top_n: int
    ) -> List:
        """
        合并子问题结果
        
        Args:
            sub_results: 子问题结果列表
            final_top_n: 最终返回数量
            
        Returns:
            合并后的节点列表
        """
        all_nodes = []
        seen_ids = set()
        
        # 收集所有节点，去重
        for result in sub_results:
            for node in result['nodes']:
                node_id = node.node.node_id
                if node_id not in seen_ids:
                    seen_ids.add(node_id)
                    # 添加子问题标记
                    node.node.metadata['sub_question'] = result['sub_question']
                    all_nodes.append(node)
        
        # 按分数排序
        all_nodes.sort(key=lambda x: x.score, reverse=True)
        
        # 过滤低分节点
        filtered_nodes = [
            n for n in all_nodes 
            if n.score >= AppSettings.SUBQUESTION_MIN_SCORE
        ]
        
        logger.info(
            f"[结果合并] 总节点: {len(all_nodes)} | "
            f"过滤后: {len(filtered_nodes)} | "
            f"返回: {min(len(filtered_nodes), final_top_n)}"
        )
        
        return filtered_nodes[:final_top_n]
    
    def _generate_sub_answer(self, sub_question: str, nodes: List) -> str:
        """
        为单个子问题生成答案（基于检索上下文）
        
        Args:
            sub_question: 子问题
            nodes: 检索到的节点列表
            
        Returns:
            LLM 生成的答案
        """
        if not nodes:
            return ""
        
        try:
            # 构建上下文
            context_parts = []
            for i, node in enumerate(nodes[:3], 1):
                content = node.node.get_content()
                context_parts.append(f"[参考资料{i}]\n{content}\n")
            
            context = "\n".join(context_parts)
            
            # 构建提示词
            from prompts import get_sub_answer_generation_system, get_sub_answer_generation_user
            
            system_prompt = "\n".join(get_sub_answer_generation_system())
            user_prompt = get_sub_answer_generation_user(sub_question, context)
            
            # 调用 LLM（使用较短超时）
            llm = self.llm_service.get_client(AppSettings.SUBQUESTION_DECOMP_LLM_ID)
            answer = self._call_llm_with_timeout(
                llm,
                system_prompt,
                user_prompt,
                timeout=15  # 15秒超时
            )
            
            return answer.strip()
            
        except TimeoutError:
            logger.warning(f"[子问题答案] 生成超时: {sub_question[:50]}...")
            return ""
        except Exception as e:
            logger.error(f"[子问题答案] 生成失败: {e}")
            return ""
    
    def synthesize_answer(self, original_query: str, sub_answers: List[Dict]) -> str:
        """
        合成子问题答案为完整回答（可选功能）
        
        Args:
            original_query: 原始查询
            sub_answers: 子问题答案列表 [{'sub_question': ..., 'answer': ...}, ...]
            
        Returns:
            合成后的完整答案
        """
        if not sub_answers:
            return ""
        
        try:
            # 构建提示词
            system_prompt = "\n".join(get_subquestion_synthesis_system())
            user_prompt = get_subquestion_synthesis_user(original_query, sub_answers)
            
            # 调用LLM合成答案
            logger.info(
                f"[答案合成] 开始合成 | 子问题数: {len(sub_answers)} | "
                f"超时设置: {AppSettings.SUBQUESTION_SYNTHESIS_TIMEOUT}s"
            )
            llm = self.llm_service.get_client(AppSettings.SUBQUESTION_DECOMP_LLM_ID)
            synthesized_answer = self._call_llm_with_timeout(
                llm, 
                system_prompt, 
                user_prompt, 
                timeout=AppSettings.SUBQUESTION_SYNTHESIS_TIMEOUT
            )
            
            logger.info(f"[答案合成] 合成完成 | 子问题数: {len(sub_answers)} | 答案长度: {len(synthesized_answer)}")
            return synthesized_answer
            
        except TimeoutError as te:
            logger.error(
                f"[答案合成] 合成超时 | "
                f"超时阈值: {AppSettings.SUBQUESTION_SYNTHESIS_TIMEOUT}s | "
                f"子问题数: {len(sub_answers)} | "
                f"建议: 增加 SUBQUESTION_SYNTHESIS_TIMEOUT 配置"
            )
            return ""
        except Exception as e:
            logger.error(f"[答案合成] 合成失败: {e}", exc_info=True)
            return ""
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取健康度指标"""
        if self.metrics['total_queries'] > 0:
            decompose_rate = self.metrics['decomposed_queries'] / self.metrics['total_queries']
            fallback_rate = self.metrics['fallback_count'] / self.metrics['total_queries']
        else:
            decompose_rate = 0.0
            fallback_rate = 0.0
        
        return {
            **self.metrics,
            'decompose_rate': f"{decompose_rate:.2%}",
            'fallback_rate': f"{fallback_rate:.2%}"
        }
    
    def log_metrics(self):
        """记录健康度指标"""
        metrics = self.get_metrics()
        logger.info(
            f"[子问题分解器指标] "
            f"总查询: {metrics['total_queries']} | "
            f"分解率: {metrics['decompose_rate']} | "
            f"回退率: {metrics['fallback_rate']} | "
            f"超时: {metrics['timeout_count']} | "
            f"错误: {metrics['error_count']}"
        )
