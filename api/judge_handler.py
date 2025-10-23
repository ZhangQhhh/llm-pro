# -*- coding: utf-8 -*-
"""
判断题处理器
处理选择题判断的业务逻辑
"""
import re
import time
from typing import Generator, Dict, Any
from llama_index.core import QueryBundle
from config import Settings
from utils import logger
from prompts import (
    get_judge_option_system_general,
    get_judge_option_system_rag,
    get_judge_option_general_think_on,
    get_judge_option_general_think_off,
    get_judge_option_user_think_on,
    get_judge_option_user_think_off,
    get_judge_option_assistant_context_prefix
)


class JudgeHandler:
    """判断题处理器"""

    def __init__(self, retriever, reranker, llm_wrapper):
        self.retriever = retriever
        self.reranker = reranker
        self.llm_wrapper = llm_wrapper

    def process(
        self,
        question: str,
        enable_thinking: bool,
        llm
    ) -> Generator[Dict[str, Any], None, None]:
        """
        处理判断题

        Args:
            question: 问题内容
            enable_thinking: 是否启用思考模式
            llm: LLM 实例

        Yields:
            处理结果字典
        """
        if not question or not question.strip():
            logger.warning("收到空问题")
            yield {"type": "error", "content": "问题内容为空"}
            return

        logger.info(f"处理判断题: '{question}' | 思考模式: {enable_thinking}")

        # 1. 检索
        try:
            retrieved_nodes = self.retriever.retrieve(question)
            reranked_nodes = self.reranker.postprocess_nodes(
                retrieved_nodes,
                query_bundle=QueryBundle(question)
            )
            reranked_nodes = reranked_nodes[:Settings.RERANK_TOP_N]
        except Exception as e:
            logger.error(f"检索错误: {e}", exc_info=True)
            yield {"type": "think_token", "content": f"(检索错误: {e})"}
            yield {
                "type": "judgment",
                "answer": "错误",
                "answer_type": "error",
                "full_analysis": str(e),
                "sources": ""
            }
            return

        # 2. 构造提示词
        prompt_parts = self._build_prompt(question, enable_thinking, reranked_nodes)

        # 3. 调用 LLM 并处理
        for result in self._call_llm_and_parse(
            llm,
            prompt_parts,
            enable_thinking
        ):
            yield result

    def _build_prompt(self, question: str, enable_thinking: bool, reranked_nodes):
        """构造提示词"""
        has_rag = bool(
            reranked_nodes
            and reranked_nodes[0].score >= Settings.RETRIEVAL_SCORE_THRESHOLD
        )

        if not has_rag:
            # 无 RAG 命中
            return {
                "answer_type": "general",
                "system_prompt": get_judge_option_system_general(),
                "user_prompt": get_judge_option_general_think_off().format(query=question),
                "assistant_context": None,
                "sources": "(来源: 通用知识)"
            }
        else:
            # RAG 命中
            context_str = "\n\n".join([
                n.node.get_content() for n in reranked_nodes
            ])

            sources_list = [
                f"[{i+1}] {n.node.metadata.get('file_name', '未知')} "
                f"(相似度: {n.score:.4f})"
                for i, n in enumerate(reranked_nodes)
            ]

            return {
                "answer_type": "rag",
                "system_prompt": get_judge_option_system_rag(),
                "user_prompt": get_judge_option_user_think_off().format(query=question),
                "assistant_context": get_judge_option_assistant_context_prefix() + context_str,
                "sources": "\n".join(sources_list)
            }

    def _call_llm_and_parse(self, llm, prompt_parts, enable_thinking):
        """调用 LLM 并解析结果"""
        fallback_prompt = (
            f"{prompt_parts['system_prompt']}\n"
            f"{prompt_parts.get('assistant_context') or ''}\n"
            f"{prompt_parts['user_prompt']}"
        )

        for attempt in range(Settings.LLM_MAX_RETRIES):
            try:
                response_stream = self.llm_wrapper.stream(
                    llm,
                    prompt=fallback_prompt,
                    system_prompt=prompt_parts['system_prompt'],
                    user_prompt=prompt_parts['user_prompt'],
                    assistant_context=prompt_parts.get('assistant_context'),
                    use_chat_mode=Settings.USE_CHAT_MODE
                )

                full_text = ""
                for delta in response_stream:
                    token = getattr(delta, 'delta', None) or getattr(delta, 'text', None) or ''
                    full_text += token

                    # 流式输出思考过程
                    if not enable_thinking or self._should_yield_token(full_text, token):
                        yield {"type": "think_token", "content": token}

                # 解析最终结果
                result = self._parse_response(full_text, enable_thinking)
                result.update({
                    "answer_type": prompt_parts['answer_type'],
                    "sources": prompt_parts['sources']
                })
                yield result
                return

            except Exception as e:
                logger.warning(f"LLM 调用失败 (尝试 {attempt+1}/{Settings.LLM_MAX_RETRIES}): {e}")
                if attempt == Settings.LLM_MAX_RETRIES - 1:
                    yield {"type": "think_token", "content": f"(API错误: {e})"}
                    yield {
                        "type": "judgment",
                        "answer": "错误",
                        "answer_type": "error",
                        "full_analysis": "",
                        "sources": ""
                    }
                    return
                time.sleep(1)

    def _should_yield_token(self, full_text: str, token: str) -> bool:
        """判断是否应该输出当前 token"""
        in_think = "<think>" in full_text and "</think>" not in full_text
        if in_think and "<think>" not in token:
            return True
        if "<think>" in token and "</think>" in token:
            return False
        return False

    def _parse_response(self, text: str, enable_thinking: bool) -> Dict[str, Any]:
        """解析 LLM 响应"""
        judgment = "错误"
        analysis = ""

        if enable_thinking:
            # 提取思考过程
            think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
            if think_match:
                analysis = think_match.group(1).strip()
            elif "【判断结果】" in text:
                analysis = text.split("【判断结果】")[0].strip()
            else:
                analysis = text

            # 提取判断结果
            judgment_match = re.search(r"【判断结果】\s*([正确错误])", text)
            if judgment_match:
                judgment = judgment_match.group(1).strip()
            elif text.strip().endswith("正确"):
                judgment = "正确"
        else:
            # 提取分析
            analysis_match = re.search(r"1\.\s*分析:\s*(.*)", text, re.DOTALL)
            if analysis_match:
                temp = analysis_match.group(1)
                idx = temp.find("2. 判断:")
                analysis = temp[:idx].strip() if idx != -1 else temp.strip()
            elif "2. 判断:" in text:
                analysis = text.split("2. 判断:")[0].strip()
            else:
                analysis = text

            # 提取判断
            judgment_match = re.search(r"2\.\s*判断:\s*([正确错误])", text)
            if judgment_match:
                judgment = judgment_match.group(1).strip()
            elif text.strip().endswith("正确"):
                judgment = "正确"

        return {
            "type": "judgment",
            "answer": judgment,
            "full_analysis": analysis
        }
