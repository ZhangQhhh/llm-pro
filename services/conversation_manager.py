# -*- coding: utf-8 -*-
"""
对话管理器
负责多轮对话的存储、检索和上下文构建
"""
from typing import List, Dict, Optional
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from llama_index.core.embeddings import BaseEmbedding
from config import Settings as AppSettings
from utils.logger import logger
import uuid


class ConversationManager:
    """多轮对话管理器"""

    def __init__(self, embed_model: BaseEmbedding, qdrant_client: QdrantClient):
        self.embed_model = embed_model
        self.qdrant_client = qdrant_client
        self.collection_name = AppSettings.CONVERSATION_COLLECTION

        # 确保对话集合存在
        self._ensure_collection()

    def _ensure_collection(self):
        """确保 Qdrant 对话集合存在"""
        try:
            collections = self.qdrant_client.get_collections().collections
            if not any(c.name == self.collection_name for c in collections):
                # 获取 embedding 维度
                test_embedding = self.embed_model.get_text_embedding("test")
                vector_size = len(test_embedding)

                self.qdrant_client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"创建对话集合 {self.collection_name}")
        except Exception as e:
            logger.error(f"创建对话集合失败: {e}")

    def add_conversation_turn(
        self,
        session_id: str,
        user_query: str,
        assistant_response: str,
        context_docs: Optional[List[str]] = None
    ):
        """
        存储一轮对话到向量库

        Args:
            session_id: 会话ID
            user_query: 用户问题
            assistant_response: 助手回答
            context_docs: 使用的上下文文档(可选)
        """
        try:
            # 构建对话文本(用于向量化)
            conversation_text = f"用户: {user_query}\n助手: {assistant_response}"

            # 生成 embedding
            embedding = self.embed_model.get_text_embedding(conversation_text)

            # 构建 payload
            payload = {
                "session_id": session_id,
                "user_query": user_query,
                "assistant_response": assistant_response,
                "timestamp": datetime.now().isoformat(),
                "context_docs": context_docs or []
            }

            # 存储到 Qdrant
            point_id = str(uuid.uuid4())
            self.qdrant_client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=point_id,
                        vector=embedding,
                        payload=payload
                    )
                ]
            )

            logger.info(f"会话 {session_id} 对话已存储")

        except Exception as e:
            logger.error(f"存储对话失败: {e}", exc_info=True)

    def retrieve_relevant_history(
        self,
        session_id: str,
        current_query: str,
        top_k: int = 3
    ) -> List[Dict]:
        """
        检索相关历史对话

        Args:
            session_id: 会话ID
            current_query: 当前问题
            top_k: 检索数量

        Returns:
            相关对话列表
        """
        try:
            # 生成查询 embedding
            query_embedding = self.embed_model.get_text_embedding(current_query)

            # 向量检索(仅限当前会话)
            search_result = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter={
                    "must": [
                        {"key": "session_id", "match": {"value": session_id}}
                    ]
                },
                limit=top_k,
                with_payload=True
            )

            # 提取相关对话
            relevant_history = []
            for hit in search_result:
                relevant_history.append({
                    "user_query": hit.payload["user_query"],
                    "assistant_response": hit.payload["assistant_response"],
                    "timestamp": hit.payload["timestamp"],
                    "score": hit.score
                })

            logger.info(f"检索到 {len(relevant_history)} 条相关历史")
            return relevant_history

        except Exception as e:
            logger.error(f"检索历史对话失败: {e}", exc_info=True)
            return []

    def get_recent_history(
        self,
        session_id: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        获取最近 N 轮对话

        Args:
            session_id: 会话ID
            limit: 获取数量

        Returns:
            最近对话列表(按时间升序)
        """
        try:
            # 使用 scroll 获取所有对话,然后按时间排序
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter={
                    "must": [
                        {"key": "session_id", "match": {"value": session_id}}
                    ]
                },
                limit=100,  # 假设单会话不超过100轮
                with_payload=True
            )

            # 提取并排序
            all_turns = []
            for point in scroll_result[0]:
                all_turns.append({
                    "user_query": point.payload["user_query"],
                    "assistant_response": point.payload["assistant_response"],
                    "timestamp": point.payload["timestamp"]
                })

            # 按时间降序排序,取最近的 limit 条
            recent_turns = sorted(
                all_turns,
                key=lambda x: x["timestamp"],
                reverse=True
            )[:limit]

            # 反转为时间升序(旧→新)
            recent_turns.reverse()

            logger.info(f"获取到 {len(recent_turns)} 条最近对话")
            return recent_turns

        except Exception as e:
            logger.error(f"获取最近对话失败: {e}", exc_info=True)
            return []

    def build_context_messages(
        self,
        session_id: str,
        current_query: str,
        system_prompt: str,
        knowledge_context: Optional[str] = None,
        context_prefixes: Optional[Dict[str, str]] = None,
        recent_turns: int = 3,
        relevant_turns: int = 2
    ) -> List[Dict[str, str]]:
        """
        构建完整的上下文 messages 数组

        Args:
            session_id: 会话ID
            current_query: 当前用户问题
            system_prompt: 系统提示词
            knowledge_context: 知识库检索的上下文(可选)
            context_prefixes: 上下文前缀字典(可选)
            recent_turns: 保留的最近对话轮数
            relevant_turns: 检索的相关对话轮数

        Returns:
            messages 数组
        """
        messages = [{"role": "system", "content": system_prompt}]

        # 默认前缀
        if context_prefixes is None:
            context_prefixes = {
                "relevant_history": "以下是相关的历史对话，可作为背景参考：\n",
                "recent_history": "以下是最近的对话历史：\n",
                "regulations": "业务规定如下：\n"
            }

        # 1. 获取向量检索的相关历史
        relevant_history = self.retrieve_relevant_history(
            session_id,
            current_query,
            top_k=relevant_turns
        )

        # 2. 获取最近对话历史
        recent_history = self.get_recent_history(
            session_id,
            limit=recent_turns
        )

        # 3. 合并去重(优先保留最近对话)
        recent_queries = {h["user_query"] for h in recent_history}
        unique_relevant = [
            h for h in relevant_history
            if h["user_query"] not in recent_queries
        ]

        # 4. 构建 messages
        # 先加入相关历史(如果有)
        if unique_relevant:
            messages.append({
                "role": "system",
                "content": context_prefixes["relevant_history"]
            })
            for turn in unique_relevant:
                messages.append({
                    "role": "user",
                    "content": turn["user_query"]
                })
                messages.append({
                    "role": "assistant",
                    "content": turn["assistant_response"]
                })

        # 再加入最近对话
        if recent_history:
            messages.append({
                "role": "system",
                "content": context_prefixes["recent_history"]
            })
            for turn in recent_history:
                messages.append({
                    "role": "user",
                    "content": turn["user_query"]
                })
                messages.append({
                    "role": "assistant",
                    "content": turn["assistant_response"]
                })

        # 加入知识库上下文(如果有)
        if knowledge_context:
            messages.append({
                "role": "system",
                "content": context_prefixes["regulations"] + knowledge_context
            })

        # 最后加入当前问题
        messages.append({
            "role": "user",
            "content": current_query
        })

        return messages

    def clear_session(self, session_id: str):
        """清空指定会话的对话历史"""
        try:
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector={
                    "filter": {
                        "must": [
                            {"key": "session_id", "match": {"value": session_id}}
                        ]
                    }
                }
            )
            logger.info(f"已清空会话 {session_id}")
        except Exception as e:
            logger.error(f"清空会话失败: {e}")

