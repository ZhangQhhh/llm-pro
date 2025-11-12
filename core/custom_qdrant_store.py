# -*- coding: utf-8 -*-
"""
自定义 QdrantVectorStore，修复 _node_content 存储问题
"""
from typing import List, Any, Optional, Tuple
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.schema import BaseNode
from qdrant_client.models import PointStruct
from utils.logger import logger


class FixedQdrantVectorStore(QdrantVectorStore):
    """
    修复版的 QdrantVectorStore
    
    问题：LlamaIndex 0.10.x 版本在存储节点时，会将整个 node.dict() 序列化为 JSON 字符串
    存储到 _node_content 字段，导致 BM25 检索失败。
    
    修复：覆盖 _build_points 方法，确保 _node_content 只存储纯文本内容。
    """
    
    def _build_points(
        self, 
        nodes: List[BaseNode],
        sparse_vector_name: Optional[str] = None
    ) -> Tuple[List[PointStruct], List[str]]:
        """
        构建 Qdrant Point 对象
        
        修复：确保 _node_content 字段只存储纯文本，而不是整个节点的 JSON 序列化
        """
        ids = []
        points = []
        
        for node in nodes:
            # 获取节点 ID
            node_id = node.node_id
            ids.append(node_id)
            
            # 获取 embedding
            embedding = node.get_embedding()
            
            # ⭐ 关键修复：构建 payload
            # 不使用 node.dict() 或 node.json()，而是手动构建 payload
            text_content = node.get_content()
            
            payload = {
                # 存储纯文本内容到 _node_content（用于 BM25 检索）
                "_node_content": text_content,
                
                # 同时存储到 text 字段（用于向量检索，兼容 LlamaIndex）
                "text": text_content,
                
                # 存储节点类型
                "_node_type": node.class_name(),
                
                # 存储元数据（只保留业务字段）
                **{k: v for k, v in node.metadata.items() if not k.startswith('_')},
                
                # 存储其他必要字段
                "doc_id": node.ref_doc_id if hasattr(node, 'ref_doc_id') else None,
                "document_id": node.ref_doc_id if hasattr(node, 'ref_doc_id') else None,
                "ref_doc_id": node.ref_doc_id if hasattr(node, 'ref_doc_id') else None,
            }
            
            # 创建 Point
            point = PointStruct(
                id=node_id,
                vector=embedding,
                payload=payload
            )
            
            points.append(point)
        
        logger.info(f"✓ 已构建 {len(points)} 个 Point，_node_content 为纯文本格式")
        
        return points, ids
    
    def add(self, nodes: List[BaseNode], **add_kwargs: Any) -> List[str]:
        """
        添加节点到索引
        
        覆盖父类方法以使用修复后的 _build_points
        """
        if len(nodes) > 0 and not self._collection_initialized:
            self._create_collection(
                collection_name=self.collection_name,
                vector_size=len(nodes[0].get_embedding()),
            )
        
        sparse_vector_name = self.sparse_vector_name()
        
        # 使用修复后的 _build_points
        points, ids = self._build_points(nodes, sparse_vector_name)
        
        self._client.upload_points(
            collection_name=self.collection_name,
            points=points,
            batch_size=self.batch_size,
            parallel=self.parallel,
            max_retries=self.max_retries,
            wait=True,
        )
        
        return ids
