# -*- coding: utf-8 -*-
"""
来源格式化工具
处理知识库检索结果的格式化和展示
"""
import json
from typing import Any, List, Dict, Generator, Tuple, Optional
from utils import logger


def extract_node_metadata(node: Any) -> Dict[str, Any]:
    """
    提取节点的元数据信息
    
    Args:
        node: 检索节点对象
        
    Returns:
        包含元数据的字典
    """
    return {
        "file_name": node.node.metadata.get('file_name', '未知'),
        "initial_score": node.node.metadata.get('initial_score', 0.0),
        "retrieval_sources": node.node.metadata.get('retrieval_sources', []),
        "vector_score": node.node.metadata.get('vector_score', 0.0),
        "bm25_score": node.node.metadata.get('bm25_score', 0.0),
        "vector_rank": node.node.metadata.get('vector_rank'),
        "bm25_rank": node.node.metadata.get('bm25_rank'),
        "content": node.node.text.strip()
    }


def build_source_data(
    node_index: int,
    node: Any,
    filtered_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    构建单个来源的数据字典
    
    Args:
        node_index: 节点索引
        node: 检索节点对象
        filtered_info: InsertBlock 过滤信息（可选）
        
    Returns:
        来源数据字典
    """
    metadata = extract_node_metadata(node)
    
    source_data = {
        "id": node_index + 1,
        "fileName": metadata["file_name"],
        "initialScore": f"{metadata['initial_score']:.4f}",
        "rerankedScore": f"{node.score:.4f}",
        "content": metadata["content"],
        "retrievalSources": metadata["retrieval_sources"],
        "vectorScore": f"{metadata['vector_score']:.4f}",
        "bm25Score": f"{metadata['bm25_score']:.4f}"
    }
    
    # 添加排名信息（如果存在）
    if metadata["vector_rank"] is not None:
        source_data['vectorRank'] = metadata["vector_rank"]
    if metadata["bm25_rank"] is not None:
        source_data['bm25Rank'] = metadata["bm25_rank"]
    
    # 添加匹配的关键词（如果是关键词检索）
    if 'keyword' in metadata["retrieval_sources"]:
        matched_keywords = node.node.metadata.get('bm25_matched_keywords', [])
        if matched_keywords:
            source_data['matchedKeywords'] = matched_keywords
    
    # 如果有 InsertBlock 过滤信息，添加相关字段
    if filtered_info:
        source_data.update({
            "canAnswer": True,
            "reasoning": filtered_info.get('reasoning', ''),
            "keyPassage": filtered_info.get('key_passage', '')
        })
    
    return source_data


def format_sources(final_nodes: List[Any]) -> Generator[Tuple[str, str], None, None]:
    """
    格式化普通检索结果的参考来源
    
    Args:
        final_nodes: 检索到的节点列表
        
    Yields:
        (消息类型, 内容) 元组
    """
    for i, node in enumerate(final_nodes):
        source_data = build_source_data(i, node)
        yield ('SOURCE', json.dumps(source_data, ensure_ascii=False))


def format_filtered_sources(final_nodes: List[Any], filtered_map: Dict[str, Any]) -> Generator[Tuple[str, str], None, None]:
    """
    格式化 InsertBlock 过滤后的参考来源
    
    Args:
        final_nodes: 原始检索节点列表
        filtered_map: 过滤结果映射
        
    Yields:
        (消息类型, 内容) 元组
    """
    for i, node in enumerate(final_nodes):
        file_name = node.node.metadata.get('file_name', '未知')
        key = f"{file_name}_{node.score}"
        filtered_info = filtered_map.get(key)
        
        source_data = build_source_data(i, node, filtered_info)
        
        # 确保包含 InsertBlock 特有字段
        if filtered_info:
            source_data.update({
                "canAnswer": True,
                "reasoning": filtered_info.get('reasoning', ''),
                "keyPassage": filtered_info.get('key_passage', '')
            })
        else:
            source_data.update({
                "canAnswer": False,
                "reasoning": '',
                "keyPassage": ''
            })
        
        yield ('SOURCE', json.dumps(source_data, ensure_ascii=False))


def build_reference_entries(
    final_nodes: List[Any],
    filtered_map: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    构建用于日志记录的参考文献条目
    
    Args:
        final_nodes: 检索到的节点列表
        filtered_map: 过滤结果映射（可选）
        
    Returns:
        参考文献条目列表
    """
    entries = []
    if not final_nodes:
        return entries

    for i, node in enumerate(final_nodes):
        metadata = extract_node_metadata(node)
        key = f"{metadata['file_name']}_{node.score}"
        filtered_info = filtered_map.get(key) if filtered_map else None

        entry = {
            "id": i + 1,
            "fileName": metadata["file_name"],
            "initialScore": round(float(metadata["initial_score"]), 6),
            "rerankedScore": round(float(node.score or 0.0), 6),
            "content": metadata["content"]
        }
        
        # 如果有过滤信息，添加相关字段
        if filtered_map:
            entry.update({
                "canAnswer": (filtered_info is not None),
                "reasoning": filtered_info.get('reasoning', '') if filtered_info else '',
                "keyPassage": filtered_info.get('key_passage', '') if filtered_info else ''
            })

        entries.append(entry)

    return entries


def format_reference_text(source_data: Dict[str, Any], include_insertblock: bool = False) -> str:
    """
    格式化单个参考来源的文本展示
    
    Args:
        source_data: 来源数据字典
        include_insertblock: 是否包含 InsertBlock 信息
        
    Returns:
        格式化的文本字符串
    """
    base_text = (
        f"\n[{source_data['id']}] 文件: {source_data['fileName']}, "
        f"初始分: {source_data['initialScore']}, "
        f"重排分: {source_data['rerankedScore']}"
    )
    
    if include_insertblock:
        base_text += f", 可回答: {source_data.get('canAnswer', False)}"
    
    return base_text
