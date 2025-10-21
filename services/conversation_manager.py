# -*- coding: utf-8 -*-
"""
对话管理器
负责多轮对话的存储、检索和上下文构建
"""
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, FilterSelector, Range
from llama_index.core.embeddings import BaseEmbedding
from config import Settings as AppSettings
from utils.logger import logger
import uuid
import time


class ConversationManager:
    """多轮对话管理器"""

    def __init__(self, embed_model: BaseEmbedding, qdrant_client: QdrantClient):
        self.embed_model = embed_model
        self.qdrant_client = qdrant_client
        self.collection_name = AppSettings.CONVERSATION_COLLECTION

        # 缓存最近对话（减少 Qdrant 查询）
        self._recent_cache = {}  # {session_id: {"conversations": [...], "timestamp": float}}
        self._cache_ttl = 300  # 缓存有效期 5 分钟

        # 确保对话集合存在
        self._ensure_collection()

    def _ensure_collection(self):
        """确保 Qdrant 对话集合存在"""
        try:
            collections = self.qdrant_client.get_collections().collections
            collection_exists = any(c.name == self.collection_name for c in collections)

            if not collection_exists:
                logger.warning(f"对话集合 {self.collection_name} 不存在，正在创建...")
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
                logger.info(f" 成功创建对话集合 {self.collection_name}（维度: {vector_size}）")

            return True
        except Exception as e:
            logger.error(f" 创建对话集合失败: {e}", exc_info=True)
            raise  # 抛出异常而不是静默失败

    def _check_and_create_collection(self):
        """检查集合是否存在，不存在则创建（用于运行时检查）"""
        try:
            # 尝试获取集合信息
            self.qdrant_client.get_collection(self.collection_name)
            return True
        except Exception:
            # 集合不存在，尝试创建
            logger.warning(f"检测到集合 {self.collection_name} 不存在，尝试重新创建...")
            return self._ensure_collection()

    def add_conversation_turn(
        self,
        session_id: str,
        user_query: str,
        assistant_response: str,
        context_docs: Optional[List[str]] = None,
        turn_id: Optional[str] = None,
        parent_turn_id: Optional[str] = None
    ):
        """
        存储一轮对话到向量库

        Args:
            session_id: 会话ID
            user_query: 用户问题
            assistant_response: 助手回答
            context_docs: 使用的上下文文档(可选)
            turn_id: 对话轮次ID(可选，用于对话分支)
            parent_turn_id: 父对话轮次ID(可选，用于对话分支)
        """
        start_time = time.time()

        try:
            # 确保集合存在
            self._check_and_create_collection()

            # 构建对话文本(用于向量化)
            conversation_text = f"用户: {user_query}\n助手: {assistant_response}"

            # 统计 token 数量（粗略估算：中文按字符数，英文按空格分词）
            token_count = len(user_query) + len(assistant_response)

            # 生成 embedding
            embedding_start = time.time()
            embedding = self.embed_model.get_text_embedding(conversation_text)
            embedding_time = time.time() - embedding_start

            # 构建 payload（包含监控字段和分支字段）
            payload = {
                "session_id": session_id,
                "user_query": user_query,
                "assistant_response": assistant_response,
                "timestamp": datetime.now().isoformat(),
                "context_docs": context_docs or [],
                "token_count": token_count,
                "turn_id": turn_id or str(uuid.uuid4()),  # 自动生成或使用提供的
                "parent_turn_id": parent_turn_id or None  # 用于对话分支
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

            # 清除该会话的缓存
            if session_id in self._recent_cache:
                del self._recent_cache[session_id]

            total_time = time.time() - start_time

            logger.info(
                f"会话 {session_id} 对话已存储 | "
                f"Token数: {token_count} | "
                f"Embedding耗时: {embedding_time:.2f}s | "
                f"总耗时: {total_time:.2f}s"
            )

            # 异常检测：如果 token 数过多，发出警告
            if token_count > 4000:
                logger.warning(
                    f"⚠️ 会话 {session_id} 单轮对话 token 数过多: {token_count}，"
                    f"可能导致上下文超限"
                )

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
        start_time = time.time()

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

            elapsed_time = time.time() - start_time
            logger.info(
                f"检索到 {len(relevant_history)} 条相关历史 | "
                f"耗时: {elapsed_time:.2f}s"
            )
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
        获取最近 N 轮对话（带缓存优化）

        Args:
            session_id: 会话ID
            limit: 获取数量

        Returns:
            最近对话列表(按时间升序)
        """
        # 检查缓存
        current_time = time.time()
        if session_id in self._recent_cache:
            cache_entry = self._recent_cache[session_id]
            if current_time - cache_entry["timestamp"] < self._cache_ttl:
                logger.debug(f"使用缓存的最近对话 (session: {session_id})")
                return cache_entry["conversations"][:limit]

        try:
            # 确保集合存在
            self._check_and_create_collection()

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
            total_tokens = 0
            for point in scroll_result[0]:
                all_turns.append({
                    "user_query": point.payload["user_query"],
                    "assistant_response": point.payload["assistant_response"],
                    "timestamp": point.payload["timestamp"],
                    "turn_id": point.payload.get("turn_id"),  # 添加 turn_id
                    "parent_turn_id": point.payload.get("parent_turn_id")  # 添加 parent_turn_id
                })
                total_tokens += point.payload.get("token_count", 0)

            # 按时间降序排序,取最近的 limit 条
            recent_turns = sorted(
                all_turns,
                key=lambda x: x["timestamp"],
                reverse=True
            )[:limit]

            # 反转为时间升序(旧→新)
            recent_turns.reverse()

            # 更新缓存
            self._recent_cache[session_id] = {
                "conversations": recent_turns,
                "timestamp": current_time
            }

            logger.info(
                f"获取到 {len(recent_turns)} 条最近对话 | "
                f"会话总轮次: {len(all_turns)} | "
                f"累计Token数: {total_tokens}"
            )

            # 如果累计 token 数过多，发出警告
            if total_tokens > 10000:
                logger.warning(
                    f"⚠️ 会话 {session_id} 累计 token 数过多: {total_tokens}，"
                    f"建议考虑清理历史或增加摘要机制"
                )

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

    def clear_session(self, session_id: str) -> bool:
        """
        清空指定会话的所有历史对话

        Args:
            session_id: 会话ID

        Returns:
            是否成功清空
        """
        try:
            logger.info(f"开始清空会话 {session_id} 的历史对话...")

            # 删除 Qdrant 中该会话的所有点
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="session_id",
                                match=MatchValue(value=session_id)
                            )
                        ]
                    )
                )
            )

            # 清除缓存
            if session_id in self._recent_cache:
                del self._recent_cache[session_id]

            logger.info(f"✅ 会话 {session_id} 历史对话已清空")
            return True

        except Exception as e:
            logger.error(f"清空会话失败: {e}", exc_info=True)
            return False

    def get_session_statistics(self, session_id: str) -> Dict:
        """
        获取会话统计信息

        Args:
            session_id: 会话ID

        Returns:
            统计信息字典
        """
        try:
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter={
                    "must": [
                        {"key": "session_id", "match": {"value": session_id}}
                    ]
                },
                limit=1000,
                with_payload=True
            )

            total_turns = len(scroll_result[0])
            total_tokens = sum(
                point.payload.get("token_count", 0)
                for point in scroll_result[0]
            )

            if total_turns > 0:
                first_turn = min(
                    scroll_result[0],
                    key=lambda p: p.payload["timestamp"]
                )
                last_turn = max(
                    scroll_result[0],
                    key=lambda p: p.payload["timestamp"]
                )

                return {
                    "session_id": session_id,
                    "total_turns": total_turns,
                    "total_tokens": total_tokens,
                    "avg_tokens_per_turn": total_tokens / total_turns,
                    "first_conversation": first_turn.payload["timestamp"],
                    "last_conversation": last_turn.payload["timestamp"]
                }
            else:
                return {
                    "session_id": session_id,
                    "total_turns": 0,
                    "total_tokens": 0,
                    "avg_tokens_per_turn": 0
                }

        except Exception as e:
            logger.error(f"获取会话统计失败: {e}", exc_info=True)
            return {"error": str(e)}

    def clear_cache(self):
        """清空所有缓存"""
        self._recent_cache.clear()
        logger.info("对话缓存已清空")

    def get_user_sessions(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        sort_by: str = "last_update"
    ) -> Dict:
        """
        获取用户的所有会话列表

        Args:
            user_id: 用户ID
            limit: 每页返回的会话数量
            offset: 分页偏移量
            sort_by: 排序方式 ("last_update" 或 "create_time")

        Returns:
            包含会话列表和总数的字典
        """
        try:
            logger.info(f"获取用户 {user_id} 的会话列表 (limit={limit}, offset={offset})")

            # 确保集合存在
            self._check_and_create_collection()

            # 获取所有该用户的对话点（通过 session_id 前缀匹配）
            # 注意：Qdrant 不支持前缀匹配，我们需要获取所有点然后在内存中过滤
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                limit=10000,  # 假设不会超过这个数量
                with_payload=True
            )

            # 按 session_id 分组
            sessions_data = {}
            for point in scroll_result[0]:
                session_id = point.payload.get("session_id")

                # 验证 session_id 是否属于该用户
                if session_id and session_id.startswith(f"{user_id}_"):
                    if session_id not in sessions_data:
                        sessions_data[session_id] = {
                            "turns": [],
                            "total_tokens": 0
                        }

                    sessions_data[session_id]["turns"].append({
                        "user_query": point.payload.get("user_query"),
                        "assistant_response": point.payload.get("assistant_response"),
                        "timestamp": point.payload.get("timestamp"),
                        "token_count": point.payload.get("token_count", 0)
                    })
                    sessions_data[session_id]["total_tokens"] += point.payload.get("token_count", 0)

            # 构建会话列表
            sessions = []
            for session_id, data in sessions_data.items():
                turns = data["turns"]
                if not turns:
                    continue

                # 按时间排序
                turns_sorted = sorted(turns, key=lambda x: x["timestamp"])
                first_turn = turns_sorted[0]
                last_turn = turns_sorted[-1]

                # 生成会话标题（从第一条用户消息提取）
                title = self._generate_session_title(first_turn["user_query"])

                sessions.append({
                    "session_id": session_id,
                    "user_id": user_id,
                    "title": title,
                    "first_message": first_turn["user_query"][:50] + "..." if len(first_turn["user_query"]) > 50 else first_turn["user_query"],
                    "last_message": last_turn["user_query"][:50] + "..." if len(last_turn["user_query"]) > 50 else last_turn["user_query"],
                    "message_count": len(turns),
                    "total_tokens": data["total_tokens"],
                    "create_time": first_turn["timestamp"],
                    "last_update_time": last_turn["timestamp"]
                })

            # 排序
            if sort_by == "last_update":
                sessions.sort(key=lambda x: x["last_update_time"], reverse=True)
            else:  # create_time
                sessions.sort(key=lambda x: x["create_time"], reverse=True)

            # 分页
            total = len(sessions)
            sessions_page = sessions[offset:offset + limit]

            logger.info(f"找到用户 {user_id} 的 {total} 个会话，返回第 {offset}-{offset+len(sessions_page)} 个")

            return {
                "total": total,
                "sessions": sessions_page,
                "limit": limit,
                "offset": offset
            }

        except Exception as e:
            logger.error(f"获取用户会话列表失败: {e}", exc_info=True)
            return {
                "total": 0,
                "sessions": [],
                "error": str(e)
            }

    def _generate_session_title(self, first_message: str, max_length: int = 30) -> str:
        """
        从第一条消息生成会话标题

        Args:
            first_message: 第一条用户消息
            max_length: 标题最大长度

        Returns:
            会话标题
        """
        # 清理消息
        title = first_message.strip()

        # 移除多余的空白字符
        title = " ".join(title.split())

        # 截断到合适长度
        if len(title) > max_length:
            title = title[:max_length] + "..."

        return title if title else "新对话"

    def get_session_full_history(
        self,
        session_id: str,
        limit: int = 100,
        offset: int = 0,
        order: str = "asc"
    ) -> Dict:
        """
        获取会话的完整历史记录（支持分页）

        Args:
            session_id: 会话ID
            limit: 每页返回的消息数量
            offset: 分页偏移量
            order: 排序顺序 ("asc"=从旧到新, "desc"=从新到旧)

        Returns:
            包含消息列表和总数的字典
        """
        try:
            logger.info(f"获取会话 {session_id} 的完整历史 (limit={limit}, offset={offset}, order={order})")

            # 确保集合存在
            self._check_and_create_collection()

            # 获取该会话的所有对话
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter={
                    "must": [
                        {"key": "session_id", "match": {"value": session_id}}
                    ]
                },
                limit=1000,  # 假设单会话不超过1000轮
                with_payload=True
            )

            # 提取所有消息
            messages = []
            for point in scroll_result[0]:
                messages.append({
                    "turn_id": point.payload.get("turn_id"),
                    "parent_turn_id": point.payload.get("parent_turn_id"),
                    "user_query": point.payload.get("user_query"),
                    "assistant_response": point.payload.get("assistant_response"),
                    "timestamp": point.payload.get("timestamp"),
                    "context_docs": point.payload.get("context_docs", []),
                    "token_count": point.payload.get("token_count", 0)
                })

            # 按时间排序
            messages.sort(
                key=lambda x: x["timestamp"],
                reverse=(order == "desc")
            )

            # 分页
            total = len(messages)
            messages_page = messages[offset:offset + limit]

            logger.info(f"会话 {session_id} 共有 {total} 条消息，返回第 {offset}-{offset+len(messages_page)} 条")

            return {
                "session_id": session_id,
                "total_messages": total,
                "messages": messages_page,
                "limit": limit,
                "offset": offset,
                "order": order
            }

        except Exception as e:
            logger.error(f"获取会话历史失败: {e}", exc_info=True)
            return {
                "session_id": session_id,
                "total_messages": 0,
                "messages": [],
                "error": str(e)
            }

    def delete_session(self, session_id: str) -> bool:
        """
        删除指定会话（物理删除）

        Args:
            session_id: 会话ID

        Returns:
            是否成功删除
        """
        try:
            logger.info(f"开始删除会话 {session_id}...")

            # 删除 Qdrant 中该会话的所有点
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="session_id",
                                match=MatchValue(value=session_id)
                            )
                        ]
                    )
                )
            )

            # 清除缓存
            if session_id in self._recent_cache:
                del self._recent_cache[session_id]

            logger.info(f"✅ 会话 {session_id} 已删除")
            return True

        except Exception as e:
            logger.error(f"删除会话失败: {e}", exc_info=True)
            return False

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        """
        获取单个会话的详细信息

        Args:
            session_id: 会话ID

        Returns:
            会话信息字典，如果不存在返回 None
        """
        try:
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter={
                    "must": [
                        {"key": "session_id", "match": {"value": session_id}}
                    ]
                },
                limit=1000,
                with_payload=True
            )

            if not scroll_result[0]:
                return None

            # 提取所有对话轮次
            turns = []
            total_tokens = 0
            for point in scroll_result[0]:
                turns.append({
                    "timestamp": point.payload.get("timestamp"),
                    "user_query": point.payload.get("user_query"),
                    "token_count": point.payload.get("token_count", 0)
                })
                total_tokens += point.payload.get("token_count", 0)

            # 排序
            turns.sort(key=lambda x: x["timestamp"])
            first_turn = turns[0]
            last_turn = turns[-1]

            # 提取 user_id
            user_id = None
            if "_" in session_id:
                try:
                    user_id = int(session_id.split("_", 1)[0])
                except ValueError:
                    pass

            return {
                "session_id": session_id,
                "user_id": user_id,
                "title": self._generate_session_title(first_turn["user_query"]),
                "message_count": len(turns),
                "total_tokens": total_tokens,
                "create_time": first_turn["timestamp"],
                "last_update_time": last_turn["timestamp"],
                "first_message": first_turn["user_query"]
            }

        except Exception as e:
            logger.error(f"获取会话信息失败: {e}", exc_info=True)
            return None

    def delete_old_conversations(self, days: int) -> Dict[str, any]:
        """
        删除指定天数之前的过期对话

        Args:
            days: 指定天数，删除该天数之前的对话

        Returns:
            删除结果字典，包含删除的会话数量和详细信息
        """
        try:
            # 计算阈值日期
            threshold_date = datetime.now() - timedelta(days=days)
            threshold_iso = threshold_date.isoformat()

            logger.info(f"开始删除 {days} 天前（{threshold_iso}）的过期对话...")

            # 先统计有多少条过期对话
            scroll_result = self.qdrant_client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="timestamp",
                            range=Range(lt=threshold_iso)  # 小于阈值日期的对话
                        )
                    ]
                ),
                limit=10000,  # 假设不会超过1万条过期对话
                with_payload=True
            )

            expired_points = scroll_result[0]
            expired_count = len(expired_points)

            if expired_count == 0:
                logger.info("没有找到需要删除的过期对话")
                return {
                    "success": True,
                    "deleted_count": 0,
                    "message": "没有过期对话需要删除"
                }

            # 统计受影响的会话
            affected_sessions = set()
            total_tokens = 0
            for point in expired_points:
                affected_sessions.add(point.payload.get("session_id"))
                total_tokens += point.payload.get("token_count", 0)

            # 删除过期对话
            self.qdrant_client.delete(
                collection_name=self.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[
                            FieldCondition(
                                key="timestamp",
                                range=Range(lt=threshold_iso)
                            )
                        ]
                    )
                )
            )

            # 清空所有缓存（因为可能涉及多个会话）
            self.clear_cache()

            result = {
                "success": True,
                "deleted_count": expired_count,
                "affected_sessions": len(affected_sessions),
                "total_tokens_removed": total_tokens,
                "threshold_date": threshold_iso
            }

            logger.info(
                f"✅ 成功删除 {expired_count} 条过期对话 | "
                f"涉及 {len(affected_sessions)} 个会话 | "
                f"释放 {total_tokens} tokens"
            )

            return result

        except Exception as e:
            logger.error(f"删除过期对话失败: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "deleted_count": 0
            }

    def cleanup_expired_conversations(self) -> Dict[str, any]:
        """
        自动清理过期对话（使用配置的过期天数）

        Returns:
            清理结果字典
        """
        expire_days = AppSettings.CONVERSATION_EXPIRE_DAYS
        logger.info(f"开始自动清理过期对话（过期天数: {expire_days}）...")
        result = self.delete_old_conversations(expire_days)
        logger.info(f"自动清理完成: {result}")
        return result
