# -*- coding: utf-8 -*-
"""
知识问答处理器
处理知识库问答的业务逻辑
"""
import json
from typing import Generator, Dict, Any, Optional
from llama_index.core import QueryBundle
from config import Settings
from utils import logger, clean_for_sse_text
from prompts import (
    get_knowledge_assistant_context_prefix,
    get_knowledge_system_rag_simple,
    get_knowledge_system_rag_advanced,
    get_knowledge_system_no_rag_think,
    get_knowledge_system_no_rag_simple,
    get_knowledge_user_rag_simple,
    get_knowledge_user_rag_advanced,
    get_knowledge_user_no_rag_think,
    get_knowledge_user_no_rag_simple,
    get_conversation_system_rag_with_history,
    get_conversation_system_general_with_history,
    get_conversation_context_prefix_relevant_history,
    get_conversation_context_prefix_recent_history,
    get_conversation_context_prefix_regulations,
    get_conversation_user_rag_query,
    get_conversation_user_general_query,
    get_conversation_summary_system,
    get_conversation_summary_user,
    get_conversation_summary_context_prefix
)


class KnowledgeHandler:
    """知识问答处理器"""

    def __init__(self, retriever, reranker, llm_wrapper, llm_service=None):
        self.retriever = retriever
        self.reranker = reranker
        self.llm_wrapper = llm_wrapper
        self.llm_service = llm_service
        self.insert_block_filter = None

        # 如果提供了 llm_service，初始化 InsertBlock 过滤器
        if llm_service:
            from core.node_filter import InsertBlockFilter
            self.insert_block_filter = InsertBlockFilter(llm_service)
            logger.info("InsertBlock 过滤器已初始化")

    def process(
        self,
        question: str,
        enable_thinking: bool,
        rerank_top_n: int,
        llm,
        client_ip: str = "unknown",
        use_insert_block: bool = False,
        insert_block_llm_id: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        处理知识问答

        Args:
            question: 问题内容
            enable_thinking: 是否启用思考模式
            rerank_top_n: 重排序后返回的文档数量
            llm: LLM 实例
            client_ip: 客户端 IP
            use_insert_block: 是否使用 InsertBlock 过滤模式
            insert_block_llm_id: InsertBlock 使用的 LLM ID

        Yields:
            SSE 格式的响应流
        """
        full_response = ""

        try:
            logger.info(
                f"处理知识问答: '{question}' | "
                f"思考模式: {enable_thinking} | "
                f"参考文件数: {rerank_top_n} | "
                f"InsertBlock: {use_insert_block}"
            )

            # 1. 检索
            yield "CONTENT:正在进行混合检索..."
            full_response += "正在进行混合检索...\n"

            final_nodes = self._retrieve_and_rerank(question, rerank_top_n)

            # 2. 如果启用 InsertBlock 模式，进行智能过滤
            filtered_results = None
            nodes_for_prompt = final_nodes  # 默认使用原始检索结果

            if use_insert_block and final_nodes and self.insert_block_filter:
                yield "CONTENT:正在使用 InsertBlock 智能过滤..."
                full_response += "正在使用 InsertBlock 智能过滤...\n"

                filtered_results = self.insert_block_filter.filter_nodes(
                    question=question,
                    nodes=final_nodes,
                    llm_id=insert_block_llm_id
                )

                if filtered_results:
                    yield f"CONTENT:找到 {len(filtered_results)} 个可回答的节点"
                    full_response += f"找到 {len(filtered_results)} 个可回答的节点\n"
                    # InsertBlock 成功：只使用过滤后的节点
                    nodes_for_prompt = None  # 不再传入原始节点
                else:
                    yield "CONTENT:未找到可直接回答的节点，将使用原始检索结果"
                    full_response += "未找到可直接回答的节点，将使用原始检索结果\n"
                    # InsertBlock 失败：继续使用原始节点，清空过滤结果
                    filtered_results = None

            # 3. 构造提示词
            prompt_parts = self._build_prompt(
                question,
                enable_thinking,
                nodes_for_prompt,  # 根据 InsertBlock 结果决定传入哪些节点
                filtered_results=filtered_results
            )

            # 4. 输出状态
            status_msg = (
                "已找到相关资料，正在生成回答..."
                if final_nodes
                else "未找到高相关性资料，基于通用知识回答..."
            )
            yield f"CONTENT:{status_msg}"
            full_response += status_msg + "\n"

            # 5. 调用 LLM
            for chunk in self._call_llm(llm, prompt_parts):
                yield f"CONTENT:{chunk}"
                full_response += chunk

            # 6. 输出参考来源
            if use_insert_block and filtered_results:
                # InsertBlock 模式：返回所有原始节点，但标注哪些被选中
                yield "CONTENT:\n\n**参考来源（全部检索结果）:**"
                full_response += "\n\n参考来源（全部检索结果）:"

                # 构建过滤结果的映射（用于快速查找）
                filtered_map = {}
                for result in filtered_results:
                    # 通过文件名和内容匹配原始节点
                    key = f"{result['file_name']}_{result['reranked_score']}"
                    filtered_map[key] = result

                # 遍历所有原始节点，标注哪些被选中
                for i, node in enumerate(final_nodes):
                    file_name = node.node.metadata.get('file_name', '未知')
                    initial_score = node.node.metadata.get('initial_score', 0.0)
                    key = f"{file_name}_{node.score}"

                    # 检查该节点是否在过滤结果中
                    filtered_info = filtered_map.get(key)

                    source_data = {
                        "id": i + 1,
                        "fileName": file_name,
                        "initialScore": f"{initial_score:.4f}",
                        "rerankedScore": f"{node.score:.4f}",
                        "content": node.node.text.strip(),
                        # 新增字段
                        "canAnswer": filtered_info is not None,
                        "reasoning": filtered_info.get('reasoning', '') if filtered_info else '',
                        "keyPassage": filtered_info.get('key_passage', '') if filtered_info else ''
                    }

                    yield f"SOURCE:{json.dumps(source_data, ensure_ascii=False)}"

                    full_response += (
                        f"\n[{source_data['id']}] 文件: {source_data['fileName']}, "
                        f"重排分: {source_data['rerankedScore']}, "
                        f"可回答: {source_data['canAnswer']}"
                    )

            elif final_nodes:
                # 普通模式：显示所有检索结果
                yield "CONTENT:\n\n**参考来源:**"
                full_response += "\n\n参考来源:"

                for source_msg in self._format_sources(final_nodes):
                    yield source_msg
                    if source_msg.startswith("SOURCE:"):
                        data = json.loads(source_msg[7:])
                        full_response += (
                            f"\n[{data['id']}] 文件: {data['fileName']}, "
                            f"初始分: {data['initialScore']}, "
                            f"重排分: {data['rerankedScore']}"
                        )

            yield "DONE:"

            # 7. 保存日志
            self._save_log(
                question,
                full_response,
                client_ip,
                bool(final_nodes),
                use_insert_block=use_insert_block
            )

        except Exception as e:
            error_msg = f"处理错误: {str(e)}"
            logger.error(f"知识问答处理出错: {e}", exc_info=True)
            yield f"ERROR:{error_msg}"

    def _retrieve_and_rerank(self, question: str, rerank_top_n: int):
        """检索和重排序"""
        # 初始检索
        retrieved_nodes = self.retriever.retrieve(question)

        # 取前 N 个送入重排
        reranker_input_top_n = Settings.RERANKER_INPUT_TOP_N
        reranker_input = retrieved_nodes[:reranker_input_top_n]

        logger.info(
            f"初检索找到 {len(retrieved_nodes)} 个节点, "
            f"选取前 {len(reranker_input)} 个送入重排"
        )

        # 重排序
        if reranker_input:
            reranked_nodes = self.reranker.postprocess_nodes(
                reranker_input,
                query_bundle=QueryBundle(question)
            )
        else:
            reranked_nodes = []

        # 阈值过滤
        threshold = Settings.RERANK_SCORE_THRESHOLD
        final_nodes = [
            node for node in reranked_nodes
            if node.score >= threshold
        ]

        logger.info(
            f"重排序后有 {len(reranked_nodes)} 个节点, "
            f"经过阈值 {threshold} 过滤后剩下 {len(final_nodes)} 个"
        )

        # 应用最终数量限制
        return final_nodes[:rerank_top_n]

    def _build_prompt(
        self,
        question: str,
        enable_thinking: bool,
        final_nodes,
        filtered_results=None
    ):
        """构造提示词"""
        # 如果有 InsertBlock 过滤结果，优先使用
        if filtered_results:
            # 同时使用关键段落和完整内容构建上下文
            context_blocks = []
            for i, result in enumerate(filtered_results):
                file_name = result['file_name']
                key_passage = result.get('key_passage', '')
                full_content = result['node'].node.text.strip()

                # 构建包含关键段落和完整内容的块
                if key_passage:
                    # 如果有关键段落，先展示关键段落，再展示完整内容
                    block = (
                        f"### 来源 {i + 1} - {file_name}:\n"
                        # f"**【关键段落】**\n> {key_passage}\n\n"
                        f"**【完整内容】**\n> {full_content}"
                    )
                else:
                    # 如果没有关键段落，只展示完整内容
                    block = f"### 来源 {i + 1} - {file_name}:\n> {full_content}"
                    logger.warning(f"节点通过筛选但没有关键段落: {file_name}")

                context_blocks.append(block)

            formatted_context = "\n\n".join(context_blocks) if context_blocks else None
            has_rag = bool(context_blocks)

            logger.info(
                f"使用 InsertBlock 结果构建上下文: {len(context_blocks)} 个段落 "
                f"(包含关键段落+完整内容)"
            )
        elif final_nodes:
            # 格式化上下文 - 直接显示文件名，并为每个来源编号
            context_blocks = []
            for i, node in enumerate(final_nodes):
                file_name = node.node.metadata.get('file_name', '未知文件')
                content = node.node.get_content().strip()
                block = f"### 来源 {i + 1} - {file_name}:\n> {content}"
                context_blocks.append(block)

            formatted_context = "\n\n".join(context_blocks)
            has_rag = True
        else:
            formatted_context = None
            has_rag = False

        if has_rag:
            # 获取前缀
            assistant_prefix = get_knowledge_assistant_context_prefix()

            # 组合 assistant_context
            assistant_context = assistant_prefix + formatted_context

            # 根据思考模式选择不同的 system 和 user prompt
            if enable_thinking:
                system_prompt = get_knowledge_system_rag_advanced()
                user_template = get_knowledge_user_rag_advanced()
            else:
                system_prompt = get_knowledge_system_rag_simple()
                user_template = get_knowledge_user_rag_simple()

            # user_template 是列表，需要 join 后再 format
            user_prompt_str = "\n".join(user_template) if isinstance(user_template, list) else user_template
            user_prompt = user_prompt_str.format(question=question)

        else:
            # 没有检索到相关内容
            assistant_context = None

            if enable_thinking:
                system_prompt = get_knowledge_system_no_rag_think()
                user_template = get_knowledge_user_no_rag_think()
            else:
                system_prompt = get_knowledge_system_no_rag_simple()
                user_template = get_knowledge_user_no_rag_simple()

            # user_template 可能是列表或字符串
            user_prompt_str = "\n".join(user_template) if isinstance(user_template, list) else user_template
            user_prompt = user_prompt_str.format(question=question)

        # system_prompt 可能是列表，需要转换为字符串
        if isinstance(system_prompt, list):
            system_prompt = "\n".join(system_prompt)

        # 构建 fallback_prompt（用于不支持 chat 模式的情况）
        fallback_parts = [system_prompt]
        if assistant_context:
            fallback_parts.append(assistant_context)
        fallback_parts.append(user_prompt)

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "assistant_context": assistant_context,
            "fallback_prompt": "\n\n".join(fallback_parts)
        }

    def _call_llm(self, llm, prompt_parts, enable_thinking=False):
        """
        调用 LLM，支持思考内容和正文内容的分离

        Args:
            llm: LLM 实例
            prompt_parts: 提示词字典
            enable_thinking: 是否启用思考模式（用于解析输出）
        """
        logger.info(f"使用外部 Prompt:\n{prompt_parts['fallback_prompt'][:200]}...")

        response_stream = self.llm_wrapper.stream(
            llm,
            prompt=prompt_parts['fallback_prompt'],
            system_prompt=prompt_parts['system_prompt'],
            user_prompt=prompt_parts['user_prompt'],
            assistant_context=prompt_parts['assistant_context'],
            use_chat_mode=Settings.USE_CHAT_MODE
        )

        # 如果启用思考模式，需要解析并分离思考内容和正文内容
        if enable_thinking:
            buffer = ""
            in_thinking_section = False
            thinking_complete = False

            for delta in response_stream:
                token = getattr(delta, 'delta', None) or getattr(delta, 'text', None) or ''
                if not token:
                    continue

                buffer += token

                # 检测思考部分的开始和结束标记
                if not thinking_complete:
                    # 检查是否进入思考区域
                    if not in_thinking_section:
                        # 检测思考开始的多种标记
                        thinking_markers = [
                            '【咨询解析】', '第一部分：咨询解析', '第一部分:咨询解析',
                            '<think>', '## 思考过程', '## 分析过程',
                            '关键实体', 'Key Entities', '1. 关键实体'
                        ]

                        for marker in thinking_markers:
                            if marker in buffer:
                                in_thinking_section = True
                                logger.info(f"检测到思考开始标记: {marker}")
                                break

                    # 检测思考结束的标记
                    if in_thinking_section:
                        end_markers = [
                            '【综合解答】', '第二部分：综合解答', '第二部分:综合解答',
                            '</think>', '## 最终答案', '## 回答'
                        ]

                        for marker in end_markers:
                            if marker in buffer:
                                thinking_complete = True
                                logger.info(f"检测到思考结束标记: {marker}")
                                # 🔥 修复点：输出思考内容（不包含结束标记）
                                idx = buffer.index(marker)
                                if idx > 0:
                                    yield ('THINK', clean_for_sse_text(buffer[:idx]))

                                # 🔥 关键修复：跳过标记本身，只保留标记之后的内容
                                # 而不是保留"标记+之后的内容"
                                buffer = buffer[idx + len(marker):]
                                logger.info(f"跳过结束标记 '{marker}'，剩余buffer长度: {len(buffer)}")
                                break

                    # 在思考区域且buffer足够长时，流式输出
                    if in_thinking_section and not thinking_complete and len(buffer) > 20:
                        yield ('THINK', clean_for_sse_text(buffer))
                        buffer = ""
                else:
                    # 思考完成后，所有内容都是正文
                    # 🔥 修复点：立即检查buffer中是否还有需要过滤的内容
                    # 移除可能残留的标题标记（如"第二部分"后面的冒号、换行等）
                    if buffer and len(buffer) > 20:
                        # 清理开头可能的空白字符和格式标记
                        cleaned_buffer = buffer.lstrip('\n\r :：')
                        if cleaned_buffer:
                            yield ('CONTENT', clean_for_sse_text(cleaned_buffer))
                        buffer = ""
                    elif buffer:
                        # buffer较短，继续累积
                        pass

            # 输出剩余的buffer
            if buffer:
                if in_thinking_section and not thinking_complete:
                    # 如果思考区域未完成，剩余内容作为思考输出
                    yield ('THINK', clean_for_sse_text(buffer))
                    logger.info(f"输出剩余思考内容: {len(buffer)} 字符")
                else:
                    # 否则作为正文输出，但要清理开头的空白和标记
                    cleaned_buffer = buffer.lstrip('\n\r :：')
                    if cleaned_buffer:
                        yield ('CONTENT', clean_for_sse_text(cleaned_buffer))
                        logger.info(f"输出剩余正文内容: {len(cleaned_buffer)} 字符")
        else:
            # 不启用思考模式，所有内容都是正文
            for delta in response_stream:
                token = getattr(delta, 'delta', None) or getattr(delta, 'text', None) or ''
                if token:
                    yield ('CONTENT', clean_for_sse_text(token))

    def _format_sources(self, final_nodes):
        """格式化参考来源"""
        for i, node in enumerate(final_nodes):
            initial_score = node.node.metadata.get('initial_score', 0.0)
            source_data = {
                "id": i + 1,
                "fileName": node.node.metadata.get('file_name', '未知'),
                "initialScore": f"{initial_score:.4f}",
                "rerankedScore": f"{node.score:.4f}",
                "content": node.node.text.strip()
            }
            yield f"SOURCE:{json.dumps(source_data, ensure_ascii=False)}"

    def _format_filtered_sources(self, filtered_results):
        """格式化 InsertBlock 过滤后的参考来源"""
        for i, result in enumerate(filtered_results):
            source_data = {
                "id": i + 1,
                "fileName": result['file_name'],
                "initialScore": f"{result['initial_score']:.4f}",
                "rerankedScore": f"{result['reranked_score']:.4f}",
                "canAnswer": result['can_answer'],
                "reasoning": result['reasoning'],
                "keyPassage": result.get('key_passage', ''),
                "content": result['node'].node.text.strip()
            }
            yield f"SOURCE:{json.dumps(source_data, ensure_ascii=False)}"

    def _save_log(self, question: str, response: str, client_ip: str, has_rag: bool, use_insert_block: bool = False):
        """保存问答日志"""
        from utils import QALogger
        qa_logger = QALogger(Settings.LOG_DIR)
        qa_logger.save_log(
            question,
            response,
            'knowledge_qa_stream',
            metadata={
                "ip": client_ip,
                "answer_type": "rag" if has_rag else "general",
                "chat_mode": Settings.USE_CHAT_MODE,
                "insert_block_mode": use_insert_block
            }
        )

    def process_conversation(
        self,
        question: str,
        session_id: str,
        enable_thinking: bool,
        rerank_top_n: int,
        llm,
        client_ip: str = "unknown",
        use_insert_block: bool = False,
        insert_block_llm_id: Optional[str] = None
    ) -> Generator[str, None, None]:
        """
        处理支持多轮对话的知识问答

        流程：
        1. 检索相关文档
        2. InsertBlock 过滤（可选）
        3. 获取历史对话
        4. 使用知识问答的提示词构建 prompt（将历史对话注入到上下文中）
        5. 调用 LLM
        6. 存储本轮对话
        7. 返回参考来源

        Args:
            question: 问题内容
            session_id: 会话ID
            enable_thinking: 是否启用思考模式
            rerank_top_n: 重排序后返回的文档数量
            llm: LLM 实例
            client_ip: 客户端 IP
            use_insert_block: 是否使用 InsertBlock 过滤模式
            insert_block_llm_id: InsertBlock 使用的 LLM ID

        Yields:
            SSE 格式的响应流
        """
        full_response = ""

        try:
            logger.info(
                f"处理多轮对话: 会话 {session_id[:8]}... | '{question}' | "
                f"思考模式: {enable_thinking} | InsertBlock: {use_insert_block}"
            )

            # 获取对话管理器
            from flask import current_app
            knowledge_service = current_app.knowledge_service
            conversation_manager = knowledge_service.conversation_manager

            if not conversation_manager:
                raise ValueError("对话管理器未初始化")

            # 返回会话ID
            yield f"SESSION:{session_id}"

            # 1. 检索
            yield "CONTENT:正在进行混合检索..."
            full_response += "正在进行混合检索...\n"

            final_nodes = self._retrieve_and_rerank(question, rerank_top_n)

            # 2. 如果启用 InsertBlock 模式，进行智能过滤
            filtered_results = None
            nodes_for_prompt = final_nodes

            if use_insert_block and final_nodes and self.insert_block_filter:
                yield "CONTENT:正在使用 InsertBlock 智能过滤..."
                full_response += "正在使用 InsertBlock 智能过滤...\n"

                filtered_results = self.insert_block_filter.filter_nodes(
                    question=question,
                    nodes=final_nodes,
                    llm_id=insert_block_llm_id
                )

                if filtered_results:
                    yield f"CONTENT:找到 {len(filtered_results)} 个可回答的节点"
                    full_response += f"找到 {len(filtered_results)} 个可回答的节点\n"
                    nodes_for_prompt = None
                else:
                    yield "CONTENT:未找到可直接回答的节点，将使用原始检索结果"
                    full_response += "未找到可直接回答的节点，将使用原始检索结果\n"
                    filtered_results = None

            # 3. 获取历史对话
            from config import Settings as AppSettings
            recent_turns = getattr(AppSettings, 'MAX_RECENT_TURNS', 6)
            relevant_turns = getattr(AppSettings, 'MAX_RELEVANT_TURNS', 3)
            max_summary_turns = getattr(AppSettings, 'MAX_SUMMARY_TURNS', 12)

            # 3.1 获取最近的对话历史
            recent_history = conversation_manager.get_recent_history(
                session_id=session_id,
                limit=recent_turns
            )

            # 3.2 检索与当前问题相关的历史对话
            relevant_history = []
            if relevant_turns > 0:
                try:
                    relevant_history = conversation_manager.retrieve_relevant_history(
                        session_id=session_id,
                        current_query=question,
                        top_k=relevant_turns
                    )
                    # 过滤掉已经在最近对话中的轮次（避免重复）
                    recent_turn_ids = {turn.get('turn_id') for turn in recent_history if turn.get('turn_id')}
                    relevant_history = [
                        turn for turn in relevant_history
                        if turn.get('turn_id') not in recent_turn_ids
                    ]
                    logger.info(f"检索到 {len(relevant_history)} 条相关历史对话（排除最近对话后）")
                except Exception as e:
                    logger.warning(f"检索相关历史对话失败: {e}")
                    relevant_history = []

            # 4. 构建历史对话摘要（优化版）
            # 获取会话总轮数
            try:
                all_history = conversation_manager.get_recent_history(
                    session_id=session_id,
                    limit=100  # 假设最多100轮
                )
                total_turns = len(all_history)
            except Exception as e:
                logger.warning(f"获取总对话轮数失败: {e}")
                total_turns = len(recent_history)
                all_history = recent_history

            history_summary = None

            # 只有当总轮数超过 MAX_SUMMARY_TURNS 时才生成摘要（避免频繁摘要）
            if total_turns > max_summary_turns:
                # 排除最近N轮，剩余的用于生成摘要
                old_history = all_history[:-recent_turns] if len(all_history) > recent_turns else []

                if old_history and len(old_history) >= 3:  # 至少3轮才值得摘要
                    # 检查摘要缓存
                    cache_key = f"{session_id}_summary"
                    current_time = time.time()

                    if hasattr(conversation_manager, '_summary_cache'):
                        cache_entry = conversation_manager._summary_cache.get(cache_key)
                        if cache_entry:
                            cache_age = current_time - cache_entry.get('timestamp', 0)
                            summarized_count = cache_entry.get('summarized_until', 0)

                            # 如果缓存有效且对话数量没变化太多（允许±2轮差异），使用缓存
                            if (cache_age < AppSettings.SUMMARY_CACHE_TTL and
                                abs(len(old_history) - summarized_count) <= 2):
                                history_summary = cache_entry.get('summary')
                                logger.info(f"使用缓存的历史摘要 (缓存时长: {cache_age:.0f}s)")

                    # 如果没有缓存或缓存失效，生成新摘要
                    if not history_summary:
                        try:
                            history_summary = conversation_manager.summarize_old_conversations(
                                session_id=session_id,
                                conversations=old_history
                            )

                            # 更新缓存
                            if history_summary and hasattr(conversation_manager, '_summary_cache'):
                                conversation_manager._summary_cache[cache_key] = {
                                    'summary': history_summary,
                                    'summarized_until': len(old_history),
                                    'timestamp': current_time
                                }
                                logger.info(f"已生成并缓存历史摘要 (覆盖 {len(old_history)} 轮)")
                        except Exception as e:
                            logger.warning(f"生成历史摘要失败: {e}")
                            history_summary = None
                else:
                    logger.debug(f"旧对话轮数({len(old_history)})不足，跳过摘要生成")
            else:
                logger.debug(f"总轮数({total_turns})未达摘要阈值({max_summary_turns})，跳过摘要")

            # 5. 使用优化的提示词构建方式（注入历史对话）
            prompt_parts = self._build_prompt_with_history(
                question,
                enable_thinking,
                nodes_for_prompt,
                filtered_results=filtered_results,
                recent_history=recent_history,
                relevant_history=relevant_history,
                history_summary=history_summary
            )

            # 6. 输出状态
            status_msg = (
                "已找到相关资料，正在生成回答..."
                if final_nodes
                else "未找到高相关性资料，基于通用知识和对话历史回答..."
            )
            yield f"CONTENT:{status_msg}"
            full_response += status_msg + "\n"

            # 7. 调用 LLM
            assistant_response = ""
            for result in self._call_llm(llm, prompt_parts, enable_thinking=enable_thinking):
                # result 是元组 (prefix_type, content)
                prefix_type, chunk = result
                if prefix_type == 'THINK':
                    yield f"THINK:{chunk}"
                    # 思考内容不计入 assistant_response
                elif prefix_type == 'CONTENT':
                    yield f"CONTENT:{chunk}"
                    full_response += chunk
                    assistant_response += chunk

            # 8. 存储本轮对话到向量库
            context_doc_names = []
            if final_nodes:
                context_doc_names = [
                    node.node.metadata.get('file_name', '未知')
                    for node in final_nodes
                ]

            # 获取上一轮对话的 turn_id 作为 parent_turn_id
            parent_turn_id = None
            try:
                if recent_history:
                    parent_turn_id = recent_history[-1].get('turn_id')
            except Exception as e:
                logger.warning(f"获取父对话ID失败: {e}")

            # 生成当前轮次的 turn_id
            import uuid
            current_turn_id = str(uuid.uuid4())

            # 存储对话（包含完整的助手回答，其中已经包含了实体和动作分析）
            conversation_manager.add_conversation_turn(
                session_id=session_id,
                user_query=question,
                assistant_response=assistant_response,
                context_docs=context_doc_names,
                turn_id=current_turn_id,
                parent_turn_id=parent_turn_id
            )

            # 9. 输出参考来源
            if use_insert_block and filtered_results:
                yield "CONTENT:\n\n**参考来源（全部检索结果）:**"
                full_response += "\n\n参考来源（全部检索结果）:"

                filtered_map = {}
                for result in filtered_results:
                    key = f"{result['file_name']}_{result['reranked_score']}"
                    filtered_map[key] = result

                for i, node in enumerate(final_nodes):
                    file_name = node.node.metadata.get('file_name', '未知')
                    initial_score = node.node.metadata.get('initial_score', 0.0)
                    key = f"{file_name}_{node.score}"

                    filtered_info = filtered_map.get(key)

                    source_data = {
                        "id": i + 1,
                        "fileName": file_name,
                        "initialScore": f"{initial_score:.4f}",
                        "rerankedScore": f"{node.score:.4f}",
                        "content": node.node.text.strip(),
                        "canAnswer": filtered_info is not None,
                        "reasoning": filtered_info.get('reasoning', '') if filtered_info else '',
                        "keyPassage": filtered_info.get('key_passage', '') if filtered_info else ''
                    }

                    yield f"SOURCE:{json.dumps(source_data, ensure_ascii=False)}"

                    full_response += (
                        f"\n[{source_data['id']}] 文件: {source_data['fileName']}, "
                        f"重排分: {source_data['rerankedScore']}, "
                        f"可回答: {source_data['canAnswer']}"
                    )

            elif final_nodes:
                yield "CONTENT:\n\n**参考来源:**"
                full_response += "\n\n参考来源:"

                for source_msg in self._format_sources(final_nodes):
                    yield source_msg
                    if source_msg.startswith("SOURCE:"):
                        data = json.loads(source_msg[7:])
                        full_response += (
                            f"\n[{data['id']}] 文件: {data['fileName']}, "
                            f"重排分: {data['rerankedScore']}"
                        )

            yield "DONE:"

            # 10. 保存日志
            self._save_log(
                question,
                full_response,
                client_ip,
                bool(final_nodes),
                use_insert_block=use_insert_block
            )

        except Exception as e:
            error_msg = f"处理错误: {str(e)}"
            logger.error(f"多轮对话处理出错: {e}", exc_info=True)
            yield f"ERROR:{error_msg}"

    def _build_prompt_with_history(
        self,
        question: str,
        enable_thinking: bool,
        final_nodes,
        filtered_results=None,
        recent_history=None,
        relevant_history=None,
        history_summary=None
    ):
        """
        构造带历史对话的提示词（使用知识问答的提示词格式）

        Args:
            question: 当前问题
            enable_thinking: 是否启用思考模式
            final_nodes: 检索到的节点
            filtered_results: InsertBlock 过滤结果
            recent_history: 最近的对话历史
            relevant_history: 相关的历史对话
            history_summary: 历史对话摘要
        """
        # 构建知识库上下文（与知识问答相同的逻辑）
        knowledge_context = None
        if filtered_results:
            # 使用 InsertBlock 过滤结果
            context_blocks = []
            for i, result in enumerate(filtered_results):
                file_name = result['file_name']
                full_content = result['node'].node.text.strip()
                block = f"### 来源 {i + 1} - {file_name}:\n> {full_content}"
                context_blocks.append(block)
            knowledge_context = "\n\n".join(context_blocks) if context_blocks else None

        elif final_nodes:
            # 使用普通检索结果
            context_blocks = []
            for i, node in enumerate(final_nodes):
                file_name = node.node.metadata.get('file_name', '未知文件')
                content = node.node.get_content().strip()
                block = f"### 来源 {i + 1} - {file_name}:\n> {content}"
                context_blocks.append(block)
            knowledge_context = "\n\n".join(context_blocks)

        has_rag = bool(knowledge_context)

        # 构建历史对话上下文
        history_context = None
        if history_summary or recent_history or relevant_history:
            history_parts = []

            # 添加摘要
            if history_summary:
                summary_prefix = get_conversation_summary_context_prefix()
                history_parts.append(f"{summary_prefix}{history_summary}")

            # 添加最近的对话
            if recent_history:
                recent_prefix = get_conversation_context_prefix_recent_history()
                recent_turns_text = "\n\n".join([
                    f"用户: {turn['user_query']}\n助手: {turn['assistant_response']}"
                    for turn in recent_history
                ])
                history_parts.append(f"{recent_prefix}{recent_turns_text}")

            # 添加相关历史对话
            if relevant_history:
                relevant_prefix = get_conversation_context_prefix_relevant_history()
                relevant_turns_text = "\n\n".join([
                    f"用户: {turn['user_query']}\n助手: {turn['assistant_response']}"
                    for turn in relevant_history
                ])
                history_parts.append(f"{relevant_prefix}{relevant_turns_text}")

            history_context = "\n\n".join(history_parts)

        # 使用知识问答的提示词逻辑
        if has_rag:
            # 获取前缀
            assistant_prefix = get_knowledge_assistant_context_prefix()

            # 组合上下文：历史对话 + 业务规定
            context_parts = []
            if history_context:
                context_parts.append(history_context)
            context_parts.append(assistant_prefix + knowledge_context)

            assistant_context = "\n\n---\n\n".join(context_parts)

            # 根据思考模式选择不同的 system 和 user prompt
            if enable_thinking:
                system_prompt = get_knowledge_system_rag_advanced()
                user_template = get_knowledge_user_rag_advanced()
            else:
                system_prompt = get_knowledge_system_rag_simple()
                user_template = get_knowledge_user_rag_simple()

            # user_template 是列表，需要 join 后再 format
            user_prompt_str = "\n".join(user_template) if isinstance(user_template, list) else user_template
            user_prompt = user_prompt_str.format(question=question)

        else:
            # 没有检索到相关内容，只有历史对话
            assistant_context = history_context

            if enable_thinking:
                system_prompt = get_knowledge_system_no_rag_think()
                user_template = get_knowledge_user_no_rag_think()
            else:
                system_prompt = get_knowledge_system_no_rag_simple()
                user_template = get_knowledge_user_no_rag_simple()

            # user_template 可能是列表或字符串
            user_prompt_str = "\n".join(user_template) if isinstance(user_template, list) else user_template
            user_prompt = user_prompt_str.format(question=question)

        # system_prompt 可能是列表，需要转换为字符串
        if isinstance(system_prompt, list):
            system_prompt = "\n".join(system_prompt)

        # 构建 fallback_prompt（用于不支持 chat 模式的情况）
        fallback_parts = [system_prompt]
        if assistant_context:
            fallback_parts.append(assistant_context)
        fallback_parts.append(user_prompt)

        return {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "assistant_context": assistant_context,
            "fallback_prompt": "\n\n".join(fallback_parts)
        }
