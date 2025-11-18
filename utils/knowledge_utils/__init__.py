# -*- coding: utf-8 -*-
"""
知识处理工具模块
提供知识库问答相关的通用工具函数
"""

from .prompt_builder import (
    build_knowledge_prompt,
    build_conversation_prompt,
    format_question_with_mode
)
from .source_formatter import (
    format_sources,
    format_filtered_sources,
    build_reference_entries,
    extract_node_metadata
)
from .context_builder import (
    build_rag_context,
    build_subquestion_context,
    merge_contexts
)
from .logging_utils import (
    log_prompt_to_file,
    log_reference_details,
    save_qa_log
)
from .llm_stream_parser import (
    parse_thinking_stream,
    parse_normal_stream
)

__all__ = [
    'build_knowledge_prompt',
    'build_conversation_prompt', 
    'format_question_with_mode',
    'format_sources',
    'format_filtered_sources',
    'build_reference_entries',
    'extract_node_metadata',
    'build_rag_context',
    'build_subquestion_context',
    'merge_contexts',
    'log_prompt_to_file',
    'log_reference_details',
    'save_qa_log',
    'parse_thinking_stream',
    'parse_normal_stream'
]
