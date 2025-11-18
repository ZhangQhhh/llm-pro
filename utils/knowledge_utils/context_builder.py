# -*- coding: utf-8 -*-
"""
上下文构建工具
处理 RAG 上下文、子问题答案的组装和管理
"""
from typing import List, Dict, Any, Optional
from utils import logger


def build_hidden_kb_context(
    hidden_nodes: List[Any] = None
) -> str:
    """
    构建隐藏知识库上下文（不显示来源）
    
    Args:
        hidden_nodes: 隐藏知识库检索节点
        
    Returns:
        格式化的隐藏上下文字符串
    """
    if not hidden_nodes:
        return None
    
    from config import Settings
    
    # 过滤低分节点
    min_score = getattr(Settings, 'HIDDEN_KB_MIN_SCORE', 0.3)
    valid_nodes = [n for n in hidden_nodes if n.score >= min_score]
    
    if not valid_nodes:
        logger.info(f"[隐藏知识库] 所有节点得分低于阈值 {min_score}，跳过注入")
        return None
    
    # 构建隐藏上下文（不显示文件名，使用简洁格式）
    context_blocks = []
    for i, node in enumerate(valid_nodes, 1):
        content = node.node.get_content().strip()
        # 使用简洁格式，不使用 Markdown 符号（避免 LLM 学习并在回答中使用）
        block = f"【参考资料 {i}】\n{content}"
        context_blocks.append(block)
    
    logger.info(
        f"[隐藏知识库] 已构建隐藏上下文 | "
        f"节点数: {len(valid_nodes)} | "
        f"最高分: {valid_nodes[0].score:.4f}"
    )
    
    return "\n\n".join(context_blocks)


def build_rag_context(
    final_nodes: List[Any] = None,
    filtered_results: List[Dict[str, Any]] = None,
    hidden_nodes: List[Any] = None
) -> str:
    """
    构建 RAG 检索上下文（支持隐藏知识库）
    
    Args:
        final_nodes: 检索到的节点列表
        filtered_results: InsertBlock 过滤结果
        hidden_nodes: 隐藏知识库节点（可选）
        
    Returns:
        格式化的上下文字符串
    """
    context_blocks = []
    
    # 1. 构建隐藏知识库上下文（优先级最高，但不显示来源）
    if hidden_nodes:
        hidden_context = build_hidden_kb_context(hidden_nodes)
        if hidden_context:
            context_blocks.append(hidden_context)
    
    # 2. 优先使用 InsertBlock 过滤结果
    if filtered_results:
        block_index = 1
        
        for result in filtered_results:
            file_name = result['file_name']
            key_passage = result.get('key_passage', '')
            full_content = result['node'].node.text.strip()
            can_answer = result.get('can_answer', False)

            # 严格过滤：只有 can_answer=True 且 key_passage 不为空才注入上下文
            if not can_answer:
                logger.warning(f"[精准检索过滤] 跳过不可回答的节点: {file_name}")
                continue
            
            if not key_passage or key_passage.strip() == "":
                logger.warning(f"[精准检索过滤] 跳过无关键段落的节点: {file_name} | can_answer={can_answer}")
                continue

            # 构建包含关键段落和完整内容的块（使用简洁格式）
            block = (
                f"【业务规定 {block_index}】来源: {file_name}\n"
                f"{full_content}"
            )
            context_blocks.append(block)
            block_index += 1
            logger.info(f"[精准检索通过] 节点已注入上下文: {file_name} | 关键段落长度: {len(key_passage)}")

        logger.info(
            f"使用 InsertBlock 结果构建上下文: {len(context_blocks)} 个段落 "
            f"(包含关键段落+完整内容)"
        )
    elif final_nodes:
        # 格式化普通检索结果（使用简洁格式）
        for i, node in enumerate(final_nodes):
            file_name = node.node.metadata.get('file_name', '未知文件')
            content = node.node.get_content().strip()
            block = f"【业务规定 {i + 1}】来源: {file_name}\n{content}"
            context_blocks.append(block)
    
    return "\n\n".join(context_blocks) if context_blocks else None


def build_subquestion_context(
    sub_answers: List[Dict[str, str]] = None,
    synthesized_answer: str = None
) -> str:
    """
    构建子问题答案上下文
    
    Args:
        sub_answers: 子问题答案列表
        synthesized_answer: 子问题答案合成
        
    Returns:
        格式化的子问题上下文字符串
    """
    context_parts = []
    
    # 添加子问题答案（使用简洁格式）
    if sub_answers:
        sub_answers_block = "\n\n【子问题分解与回答】\n"
        for i, sub_answer in enumerate(sub_answers, 1):
            sub_q = sub_answer.get('sub_question', '')
            answer = sub_answer.get('answer', '')
            sub_answers_block += f"\n子问题{i}: {sub_q}\n回答{i}: {answer}\n"
        
        sub_answers_block += "\n注意: 以上是各子问题的独立回答，请结合这些信息和业务规定给出完整答案。"
        context_parts.append(sub_answers_block)
        logger.info(f"[提示词构建] 已将 {len(sub_answers)} 个子问题答案注入上下文")
    
    # 添加合成答案（使用简洁格式）
    if synthesized_answer:
        synthesis_block = (
            f"\n\n【子问题综合分析】\n"
            f"{synthesized_answer}\n\n"
            f"注意: 以上是对多个子问题答案的综合整理，请结合具体业务规定给出最终回答。"
        )
        context_parts.append(synthesis_block)
        logger.info(f"[提示词构建] 已将合成答案注入上下文 | 长度: {len(synthesized_answer)}")
    
    return "\n".join(context_parts) if context_parts else None


def merge_contexts(
    rag_context: str = None,
    subquestion_context: str = None,
    prefix: str = None
) -> str:
    """
    合并多个上下文部分
    
    Args:
        rag_context: RAG 检索上下文
        subquestion_context: 子问题上下文
        prefix: 上下文前缀
        
    Returns:
        合并后的完整上下文
    """
    context_parts = []
    
    # 添加前缀
    if prefix:
        context_parts.append(prefix)
    
    # 添加 RAG 上下文
    if rag_context:
        context_parts.append(rag_context)
    elif subquestion_context:
        # 如果没有 RAG 但有子问题，添加提示信息
        context_parts.append("**注意**: 未检索到相关业务规定文档，请基于以下子问题分析回答。\n")
        logger.info("[提示词构建] 无检索文档，但有子问题答案，创建上下文用于注入")
    
    # 添加子问题上下文
    if subquestion_context:
        context_parts.append(subquestion_context)
    
    return "\n".join(context_parts) if context_parts else None


def build_conversation_history_context(
    recent_history: List[Dict] = None,
    relevant_history: List[Dict] = None,
    history_summary: str = None
) -> str:
    """
    构建对话历史上下文
    
    Args:
        recent_history: 最近对话历史
        relevant_history: 相关对话历史
        history_summary: 历史对话摘要
        
    Returns:
        格式化的历史上下文字符串
    """
    # TODO: 实现对话历史上下文构建
    # 这里可以根据需要实现历史对话的格式化逻辑
    return None
