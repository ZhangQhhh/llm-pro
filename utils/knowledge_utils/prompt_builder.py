# -*- coding: utf-8 -*-
"""
提示词构建工具
处理知识库问答的提示词生成逻辑
"""
from typing import Dict, Any, List, Optional, Tuple
from prompts import (
    get_knowledge_assistant_context_prefix,
    get_knowledge_system_rag_simple,
    get_knowledge_system_rag_advanced,
    get_knowledge_system_no_rag_think,
    get_knowledge_system_no_rag_simple,
    get_knowledge_user_rag_simple,
    get_knowledge_user_rag_advanced,
    get_knowledge_user_no_rag_think,
    get_knowledge_user_no_rag_simple
)
from utils import logger
from .context_builder import (
    build_rag_context as _build_rag_context,
    build_subquestion_context,
    merge_contexts
)


def format_question_with_mode(question: str, enable_thinking: bool) -> str:
    """
    根据思考模式格式化问题
    
    Args:
        question: 原始问题
        enable_thinking: 是否启用思考模式
        
    Returns:
        格式化后的问题
    """
    if not enable_thinking:
        actual_question = f"{question}/no_think"
        logger.info(f"✓ 已在问题后追加 /no_think 指令: '{actual_question}'")
        return actual_question
    return question


def build_full_context(
    final_nodes: List[Any] = None,
    filtered_results: List[Dict[str, Any]] = None,
    sub_answers: List[Dict[str, str]] = None,
    synthesized_answer: str = None,
    hidden_nodes: List[Any] = None
) -> Tuple[str, bool]:
    """
    构建完整上下文内容（RAG + 子问题 + 隐藏知识库）
    
    Args:
        final_nodes: 检索到的节点列表
        filtered_results: InsertBlock 过滤结果
        sub_answers: 子问题答案列表
        synthesized_answer: 子问题答案合成
        hidden_nodes: 隐藏知识库节点（不显示来源）
        
    Returns:
        (上下文字符串, 是否有RAG内容)
    """
    # 构建 RAG 上下文（包含隐藏知识库）
    rag_context = _build_rag_context(final_nodes, filtered_results, hidden_nodes)
    has_rag = bool(rag_context)
    
    # 构建子问题上下文
    subquestion_context = build_subquestion_context(sub_answers, synthesized_answer)
    
    # 合并上下文
    prefix = get_knowledge_assistant_context_prefix() if has_rag or subquestion_context else None
    full_context = merge_contexts(rag_context, subquestion_context, prefix)
    
    return full_context, has_rag or bool(subquestion_context)


def merge_context_with_prompt(
    system_prompt: str,
    user_template: str,
    context: str,
    question: str
) -> Tuple[str, str]:
    """
    将上下文合并到用户提示词中（二段式）
    
    Args:
        system_prompt: 系统提示词
        user_template: 用户提示词模板
        context: 上下文内容
        question: 用户问题
        
    Returns:
        (合并后的用户提示词, None) # assistant_context 设为 None
    """
    user_prompt_str = "\n".join(user_template) if isinstance(user_template, list) else user_template
    user_prompt = user_prompt_str.format(context=context, question=question)
    
    logger.info("[提示词构建] 已将参考资料合并到用户问题中（二段式）")
    return user_prompt, None


def build_knowledge_prompt(
    question: str,
    enable_thinking: bool,
    final_nodes: List[Any] = None,
    filtered_results: List[Dict[str, Any]] = None,
    sub_answers: List[Dict[str, str]] = None,
    synthesized_answer: str = None,
    hidden_nodes: List[Any] = None
) -> Dict[str, Any]:
    """
    构建知识库问答提示词
    
    Args:
        question: 用户问题
        enable_thinking: 是否启用思考模式
        final_nodes: 检索到的节点列表
        filtered_results: InsertBlock 过滤结果
        sub_answers: 子问题答案列表
        synthesized_answer: 子问题答案合成
        hidden_nodes: 隐藏知识库节点（不显示来源）
        
    Returns:
        提示词字典
    """
    # 构建上下文
    assistant_context, has_context = build_full_context(
        final_nodes=final_nodes,
        filtered_results=filtered_results,
        sub_answers=sub_answers,
        synthesized_answer=synthesized_answer,
        hidden_nodes=hidden_nodes
    )
    
    # 格式化问题
    actual_question = format_question_with_mode(question, enable_thinking)
    
    if has_context:
        # 有检索文档或子问题答案
        if enable_thinking:
            system_prompt = get_knowledge_system_rag_advanced()
            user_template = get_knowledge_user_rag_advanced()
        else:
            system_prompt = get_knowledge_system_rag_simple()
            user_template = get_knowledge_user_rag_simple()
        
        # 合并上下文到用户提示词
        user_prompt, llm_assistant_context = merge_context_with_prompt(
            system_prompt, user_template, assistant_context, actual_question
        )
    else:
        # 没有检索到相关内容
        assistant_context = None
        llm_assistant_context = None
        
        if enable_thinking:
            system_prompt = get_knowledge_system_no_rag_think()
            user_template = get_knowledge_user_no_rag_think()
        else:
            system_prompt = get_knowledge_system_no_rag_simple()
            user_template = get_knowledge_user_no_rag_simple()
        
        user_prompt_str = "\n".join(user_template) if isinstance(user_template, list) else user_template
        user_prompt = user_prompt_str.format(question=actual_question)
    
    # system_prompt 可能是列表，需要转换为字符串
    if isinstance(system_prompt, list):
        system_prompt = "\n".join(system_prompt)
    
    # 构建 fallback_prompt
    fallback_parts = [system_prompt]
    if llm_assistant_context:
        fallback_parts.append(llm_assistant_context)
    fallback_parts.append(user_prompt)
    
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "assistant_context": llm_assistant_context,  # 实际传给 LLM 的
        "assistant_context_log": assistant_context,  # 用于日志记录
        "fallback_prompt": "\n\n".join(fallback_parts)
    }


def build_conversation_prompt(
    question: str,
    enable_thinking: bool,
    final_nodes: List[Any] = None,
    filtered_results: List[Dict[str, Any]] = None,
    sub_answers: List[Dict[str, str]] = None,
    synthesized_answer: str = None,
    recent_history: List[Dict] = None,
    relevant_history: List[Dict] = None,
    history_summary: str = None
) -> Dict[str, Any]:
    """
    构建多轮对话知识库问答提示词
    
    Args:
        question: 用户问题
        enable_thinking: 是否启用思考模式
        final_nodes: 检索到的节点列表
        filtered_results: InsertBlock 过滤结果
        sub_answers: 子问题答案列表
        synthesized_answer: 子问题答案合成
        recent_history: 最近对话历史
        relevant_history: 相关对话历史
        history_summary: 历史对话摘要
        
    Returns:
        提示词字典
    """
    # TODO: 实现多轮对话提示词构建
    # 这里可以复用 build_knowledge_prompt 的逻辑，并添加历史对话处理
    return build_knowledge_prompt(
        question=question,
        enable_thinking=enable_thinking,
        final_nodes=final_nodes,
        filtered_results=filtered_results,
        sub_answers=sub_answers,
        synthesized_answer=synthesized_answer
    )
