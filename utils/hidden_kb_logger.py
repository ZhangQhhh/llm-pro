# -*- coding: utf-8 -*-
"""
隐藏知识库专用日志记录器
用于详细记录隐藏知识库的检索和调用情况
"""
import os
import json
import datetime
from typing import List, Any, Optional
from llama_index.core.schema import NodeWithScore
from config import Settings


class HiddenKBLogger:
    """隐藏知识库专用日志记录器"""
    
    def __init__(self):
        # 创建日志目录
        self.log_dir = "logs/hidden_logs"
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 按日期创建日志文件
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        self.log_file = os.path.join(self.log_dir, f"hidden_kb_{today}.log")
        
        # JSON 详细记录文件
        self.json_file = os.path.join(self.log_dir, f"hidden_kb_{today}.json")
        
    def log_retrieval_start(self, query: str, kb_name: str = "hidden_kb"):
        """记录检索开始"""
        timestamp = datetime.datetime.now().isoformat()
        
        # 文本日志
        log_entry = f"[{timestamp}] [检索开始] {kb_name} | 查询: {query}\n"
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        # JSON 日志
        json_entry = {
            "timestamp": timestamp,
            "type": "retrieval_start",
            "kb_name": kb_name,
            "query": query,
            "query_length": len(query)
        }
        self._append_json(json_entry)
    
    def log_retrieval_result(self, query: str, nodes: List[NodeWithScore], kb_name: str = "hidden_kb"):
        """记录检索结果"""
        timestamp = datetime.datetime.now().isoformat()
        
        if not nodes:
            log_entry = f"[{timestamp}] [检索结果] {kb_name} | 查询: {query} | 结果: 无匹配\n"
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            
            json_entry = {
                "timestamp": timestamp,
                "type": "retrieval_result",
                "kb_name": kb_name,
                "query": query,
                "result_count": 0,
                "nodes": []
            }
            self._append_json(json_entry)
            return
        
        # 提取节点信息
        node_info = []
        for i, node in enumerate(nodes):
            content = node.node.get_content()
            metadata = node.node.metadata
            
            node_info.append({
                "rank": i + 1,
                "score": round(node.score, 4),
                "content_length": len(content),
                "content_preview": content[:100] + "..." if len(content) > 100 else content,
                "doc_id": metadata.get('doc_id', 'unknown'),
                "file_name": metadata.get('file_name', 'unknown'),
                "is_hidden": metadata.get('is_hidden', False)
            })
        
        # 文本日志
        scores = [f"{n.score:.4f}" for n in nodes[:3]]
        log_entry = (
            f"[{timestamp}] [检索结果] {kb_name} | "
            f"查询: {query[:50]}... | "
            f"返回: {len(nodes)}条 | "
            f"Top3分数: {', '.join(scores)}\n"
        )
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        # JSON 日志
        json_entry = {
            "timestamp": timestamp,
            "type": "retrieval_result",
            "kb_name": kb_name,
            "query": query,
            "result_count": len(nodes),
            "nodes": node_info
        }
        self._append_json(json_entry)
    
    def log_context_injection(self, query: str, injected_nodes: List[NodeWithScore], context_length: int):
        """记录上下文注入"""
        timestamp = datetime.datetime.now().isoformat()
        
        if not injected_nodes:
            log_entry = f"[{timestamp}] [上下文注入] 查询: {query} | 注入: 无（分数过低）\n"
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            return
        
        # 计算注入统计
        scores = [n.score for n in injected_nodes]
        avg_score = sum(scores) / len(scores)
        
        log_entry = (
            f"[{timestamp}] [上下文注入] 查询: {query[:50]}... | "
            f"注入: {len(injected_nodes)}条 | "
            f"上下文长度: {context_length}字符 | "
            f"平均分数: {avg_score:.4f}\n"
        )
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_entry)
        
        # JSON 日志
        json_entry = {
            "timestamp": timestamp,
            "type": "context_injection",
            "query": query,
            "injected_count": len(injected_nodes),
            "context_length": context_length,
            "average_score": round(avg_score, 4),
            "injected_nodes": [
                {
                    "rank": i + 1,
                    "score": round(node.score, 4),
                    "content_preview": node.node.get_content()[:100] + "..." if len(node.node.get_content()) > 100 else node.node.get_content()
                }
                for i, node in enumerate(injected_nodes)
            ]
        }
        self._append_json(json_entry)
    
    def log_daily_summary(self):
        """记录每日统计"""
        # 这里可以添加每日统计逻辑
        pass
    
    def _append_json(self, entry: dict):
        """追加 JSON 记录"""
        try:
            with open(self.json_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            # 如果 JSON 写入失败，至少记录到文本日志
            error_log = f"[{datetime.datetime.now().isoformat()}] [JSON写入错误] {str(e)}\n"
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(error_log)


# 全局实例
hidden_kb_logger = HiddenKBLogger()
