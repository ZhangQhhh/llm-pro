# -*- coding: utf-8 -*-
"""
知识问答处理器
处理知识库问答的业务逻辑
"""
import json
from typing import Generator, Dict, Any, Optional
from llama_index.core import QueryBundle
from config import Settings
from utils import get_prompt, logger, clean_for_sse_text


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
            assistant_prefix = get_prompt(
                "knowledge.assistant_context_prefix",
                "业务规定如下：\n"
            )

            # 组合 assistant_context
            assistant_context = assistant_prefix + formatted_context

            # 根据思考模式选择不同的 system 和 user prompt
            if enable_thinking:
                system_key = "knowledge.system.rag_advanced"
                user_key = "knowledge.user.rag_advanced"
            else:
                system_key = "knowledge.system.rag_simple"
                user_key = "knowledge.user.rag_simple"

            system_prompt = get_prompt(system_key, "你是一名资深边检业务专家。")
            user_template = get_prompt(user_key, "业务咨询\n{question}\n\n请给出你的回答。")
            user_prompt = user_template.format(question=question)

        else:
            # 没有检索到相关内容
            assistant_context = None

            if enable_thinking:
                system_key = "knowledge.system.no_rag_think"
                user_key = "knowledge.user.no_rag_think"
            else:
                system_key = "knowledge.system.no_rag_simple"
                user_key = "knowledge.user.no_rag_simple"

            system_prompt = get_prompt(system_key, "你是一名资深边检业务专家。")
            user_template = get_prompt(user_key, "请回答以下问题。\n\n问题: {question}")
            user_prompt = user_template.format(question=question)

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

    def _call_llm(self, llm, prompt_parts):
        """调用 LLM"""
        logger.info(f"使用外部 Prompt:\n{prompt_parts['fallback_prompt'][:200]}...")

        response_stream = self.llm_wrapper.stream(
            llm,
            prompt=prompt_parts['fallback_prompt'],
            system_prompt=prompt_parts['system_prompt'],
            user_prompt=prompt_parts['user_prompt'],
            assistant_context=prompt_parts['assistant_context'],
            use_chat_mode=Settings.USE_CHAT_MODE
        )

        for delta in response_stream:
            token = getattr(delta, 'delta', None) or getattr(delta, 'text', None) or ''
            if token:
                yield clean_for_sse_text(token)

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

            # 3. 构建知识库上下文
            knowledge_context = self._build_knowledge_context(
                nodes_for_prompt,
                filtered_results
            )

            # 4. 从 prompts.py 获取对话提示词
            has_rag = bool(knowledge_context)

            if has_rag:
                system_prompt_list = get_prompt(
                    "conversation.system.rag_with_history",
                    ["你是一名资深边检业务专家。请根据业务规定和对话历史，回答用户的业务咨询。"]
                )
            else:
                system_prompt_list = get_prompt(
                    "conversation.system.general_with_history",
                    ["你是一名资深边检业务专家。请结合对话历史，回答用户的业务咨询。"]
                )

            system_prompt = "\n".join(system_prompt_list) if isinstance(system_prompt_list, list) else system_prompt_list

            # 获取上下文前缀
            context_prefixes = {
                "relevant_history": get_prompt(
                    "conversation.context_prefix.relevant_history",
                    "以下是相关的历史对话，可作为背景参考：\n"
                ),
                "recent_history": get_prompt(
                    "conversation.context_prefix.recent_history",
                    "以下是最近的对话历史：\n"
                ),
                "regulations": get_prompt(
                    "conversation.context_prefix.regulations",
                    "业务规定如下：\n"
                )
            }

            # 5. 构建完整的 messages 数组（包含历史对话）
            messages = conversation_manager.build_context_messages(
                session_id=session_id,
                current_query=question,
                system_prompt=system_prompt,
                knowledge_context=knowledge_context,
                context_prefixes=context_prefixes,
                recent_turns=Settings.MAX_RECENT_TURNS,  # 最近对话轮数
                relevant_turns=Settings.MAX_RELEVANT_TURNS  # 相关对话轮数
            )

            # 6. 输出状态
            status_msg = (
                "已找到相关资料，正在生成回答..."
                if final_nodes
                else "未找到高相关性资料，基于通用知识和对话历史回答..."
            )
            yield f"CONTENT:{status_msg}"
            full_response += status_msg + "\n"

            # 7. 调用 LLM（使用 messages 数组）
            assistant_response = ""
            for chunk in self._call_llm_with_messages(llm, messages):
                # _call_llm_with_messages 返回的chunk可能是:
                # 1. "THINK:xxx" - 思考内容，直接输出
                # 2. 普通文本 - 正文内容，需要加CONTENT:前缀
                if chunk.startswith('THINK:'):
                    yield chunk  # 直接输出思考内容
                    # 思考内容不计入assistant_response和full_response
                else:
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
                recent_history = conversation_manager.get_recent_history(
                    session_id=session_id,
                    limit=1
                )
                if recent_history:
                    parent_turn_id = recent_history[0].get('turn_id')
            except Exception as e:
                logger.warning(f"获取父对话ID失败: {e}")

            # 生成当前轮次的 turn_id
            current_turn_id = str(__import__('uuid').uuid4())

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

    def _build_knowledge_context(self, final_nodes, filtered_results=None):
        """构建知识库上下文字符串"""
        if filtered_results:
            # 使用 InsertBlock 过滤结果
            context_blocks = []
            for i, result in enumerate(filtered_results):
                file_name = result['file_name']
                key_passage = result.get('key_passage', '')
                full_content = result['node'].node.text.strip()

                if key_passage:
                    block = (
                        f"### 来源 {i + 1} - {file_name}:\n"
                        # f"**【关键段落】**\n> {key_passage}\n\n"      
                        f"**【完整内容】**\n> {full_content}"
                    )
                else:
                    block = f"### 来源 {i + 1} - {file_name}:\n> {full_content}"

                context_blocks.append(block)

            return "\n\n".join(context_blocks) if context_blocks else None

        elif final_nodes:
            # 使用普通检索结果
            context_blocks = []
            for i, node in enumerate(final_nodes):
                file_name = node.node.metadata.get('file_name', '未知文件')
                content = node.node.get_content().strip()
                block = f"### 来源 {i + 1} - {file_name}:\n> {content}"
                context_blocks.append(block)

            return "\n\n".join(context_blocks)

        return None

    def _call_llm_with_messages(self, llm, messages):
        """使用 messages 数组调用 LLM"""
        logger.info(f"使用多轮对话模式调用 LLM, 消息数: {len(messages)}")

        # 使用 llm_wrapper 的 chat 方法
        response_stream = self.llm_wrapper.stream_chat(
            llm,
            messages=messages
        )

        # 用于跟踪当前是否在思考标签内
        in_think_tag = False
        buffer = ""

        for delta in response_stream:
            token = getattr(delta, 'delta', None) or getattr(delta, 'text', None) or ''
            if not token:
                continue

            buffer += token

            # 处理思考标签的逻辑
            while True:
                if not in_think_tag:
                    # 查找 <think> 开始标签
                    think_start = buffer.find('<think>')
                    if think_start != -1:
                        # 发送思考标签之前的内容作为正文
                        if think_start > 0:
                            content_before = buffer[:think_start]
                            cleaned = clean_for_sse_text(content_before)
                            if cleaned:
                                yield cleaned
                        # 移除已处理的内容和 <think> 标签
                        buffer = buffer[think_start + 7:]
                        in_think_tag = True
                    else:
                        # 没有找到开始标签，检查buffer是否可能包含部分标签
                        # 保留可能的部分标签（最多7个字符 "<think>"）
                        if len(buffer) > 10:
                            safe_length = len(buffer) - 7
                            cleaned = clean_for_sse_text(buffer[:safe_length])
                            if cleaned:
                                yield cleaned
                            buffer = buffer[safe_length:]
                        break
                else:
                    # 在思考标签内，查找 </think> 结束标签
                    think_end = buffer.find('</think>')
                    if think_end != -1:
                        # 发送思考内容（带 THINK: 前缀）
                        think_content = buffer[:think_end]
                        if think_content:
                            cleaned = clean_for_sse_text(think_content)
                            if cleaned:
                                yield f'THINK:{cleaned}'
                        # 移除已处理的内容和 </think> 标签
                        buffer = buffer[think_end + 8:]
                        in_think_tag = False
                    else:
                        # 没有找到结束标签，保留可能的部分标签
                        if len(buffer) > 10:
                            safe_length = len(buffer) - 8
                            think_content = buffer[:safe_length]
                            if think_content:
                                cleaned = clean_for_sse_text(think_content)
                                if cleaned:
                                    yield f'THINK:{cleaned}'
                            buffer = buffer[safe_length:]
                        break

        # 处理剩余的buffer内容
        if buffer:
            cleaned = clean_for_sse_text(buffer)
            if cleaned:
                if in_think_tag:
                    yield f'THINK:{cleaned}'
                else:
                    yield cleaned
