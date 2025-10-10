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
                else:
                    yield "CONTENT:未找到可直接回答的节点，将使用原始检索结果"
                    full_response += "未找到可直接回答的节点，将使用原始检索结果\n"

            # 3. 构造提示词
            prompt_parts = self._build_prompt(
                question,
                enable_thinking,
                final_nodes,
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
                # InsertBlock 模式：显示过滤后的结果
                yield "CONTENT:\n\n**参考来源（经 InsertBlock 过滤）:**"
                full_response += "\n\n参考来源（经 InsertBlock 过滤）:"

                for source_msg in self._format_filtered_sources(filtered_results):
                    yield source_msg
                    if source_msg.startswith("SOURCE:"):
                        data = json.loads(source_msg[7:])
                        full_response += (
                            f"\n[{data['id']}] 文件: {data['fileName']}, "
                            f"重排分: {data['rerankedScore']}, "
                            f"可回答: {data['canAnswer']}"
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
            # 使用关键段落和答案构建上下文
            context_blocks = []
            for i, result in enumerate(filtered_results):
                file_name = result['file_name']
                key_passage = result.get('key_passage', '')
                answer = result.get('answer', '')

                # 优先使用 key_passage，如果没有则使用原始内容
                content = key_passage if key_passage else result['node'].node.get_content().strip()

                block = f"### 来源 {i + 1} - {file_name}:\n> {content}"
                if answer:
                    block += f"\n\n**分析**: {answer}"
                context_blocks.append(block)

            formatted_context = "\n\n".join(context_blocks)
            has_rag = True
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
