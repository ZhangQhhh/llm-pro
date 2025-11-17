# -*- coding: utf-8 -*-
"""
知识问答处理器
处理知识库问答的业务逻辑
"""
import json
import os
from datetime import datetime
from typing import Generator, Dict, Any, Optional, List
from llama_index.core import QueryBundle
from config import Settings
from utils import logger, clean_for_sse_text
from pathlib import Path
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

    def __init__(
        self, 
        retriever, 
        reranker, 
        llm_wrapper, 
        llm_service=None,
        # 免签知识库相关组件（可选）
        visa_free_retriever=None,
        # 航司知识库相关组件（可选）
        airline_retriever=None,
        # 多库检索器和意图分类器
        multi_kb_retriever=None,
        intent_classifier=None,
        # 子问题分解器（可选）
        sub_question_decomposer=None
    ):
        # 通用知识库组件
        self.retriever = retriever
        self.reranker = reranker
        self.llm_wrapper = llm_wrapper
        self.llm_service = llm_service
        self.insert_block_filter = None
        
        # 免签知识库组件
        self.visa_free_retriever = visa_free_retriever
        # 航司知识库组件
        self.airline_retriever = airline_retriever
        # 多库检索器和意图分类器
        self.multi_kb_retriever = multi_kb_retriever
        self.intent_classifier = intent_classifier
        # 子问题分解器
        self.sub_question_decomposer = sub_question_decomposer
        
        # 子问题答案合成（用于传递到提示词）
        self._last_synthesized_answer = None

        # 如果提供了 llm_service，初始化 InsertBlock 过滤器
        if llm_service:
            from core.node_filter import InsertBlockFilter
            self.insert_block_filter = InsertBlockFilter(llm_service)
            logger.info("InsertBlock 过滤器已初始化")
        
        # 日志：知识库功能状态
        enabled_features = []
        if self.multi_kb_retriever and self.intent_classifier:
            enabled_features.append("多库检索+意图分类")
        if self.visa_free_retriever:
            enabled_features.append("免签库")
        if self.airline_retriever:
            enabled_features.append("航司库")
        if self.sub_question_decomposer:
            enabled_features.append("子问题分解")
        
        if enabled_features:
            logger.info(f"✓ 知识库功能已启用: {', '.join(enabled_features)}")
        else:
            logger.info("⊘ 仅使用通用知识库")

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
        
        # 清空上一次的子问题答案和合成答案，防止串题
        self._last_sub_answers = None
        self._last_synthesized_answer = None

        try:
            logger.info(
                f"处理知识问答: '{question}' | "
                f"思考模式: {enable_thinking} | "
                f"参考文件数: {rerank_top_n} | "
                f"InsertBlock: {use_insert_block}"
            )

            # 1. 智能路由检索（根据意图选择知识库）
            # 如果前端设置参考数量为 0，跳过检索
            if rerank_top_n == 0:
                logger.info("[检索跳过] 前端设置参考数量为 0，跳过检索和子问题分解")
                final_nodes = []
                result = None
            else:
                yield ('CONTENT', "正在进行混合检索...\n")
                full_response += "正在进行混合检索...\n"
                
                # 调用检索，获取节点和元数据
                result = self._smart_retrieve_and_rerank(question, rerank_top_n)
            
            # 检查是否返回了元数据（子问题分解）
            if result and isinstance(result, tuple) and len(result) == 2:
                final_nodes, retrieval_metadata = result
                
                # 如果有子问题，输出到前端
                if retrieval_metadata.get('decomposed') and retrieval_metadata.get('sub_questions'):
                    sub_questions = retrieval_metadata['sub_questions']
                    sub_answers = retrieval_metadata.get('sub_answers', [])
                    
                    # 构建完整的子问题数据
                    sub_questions_data = {
                        'sub_questions': sub_questions,
                        'count': len(sub_questions),
                        'sub_answers': sub_answers  # 包含每个子问题的答案摘要
                    }
                    
                    yield ('SUB_QUESTIONS', sub_questions_data)
                    logger.info(
                        f"[前端输出] 已发送子问题到前端 | "
                        f"子问题数: {len(sub_questions)} | "
                        f"答案数: {len(sub_answers)}"
                    )
            else:
                # 兼容旧版本（只返回节点）
                final_nodes = result
                retrieval_metadata = None


            # 2. 如果启用 InsertBlock 模式，进行智能过滤
            filtered_results = None
            filtered_map = None
            nodes_for_prompt = final_nodes  # 默认使用原始检索结果

            if use_insert_block and final_nodes and self.insert_block_filter:
                yield ('CONTENT', f"正在使用 InsertBlock 智能过滤 {len(final_nodes)} 个节点...")
                full_response += f"正在使用 InsertBlock 智能过滤 {len(final_nodes)} 个节点...\n"

                # 定义进度回调函数
                def progress_callback(processed, total):
                    progress_msg = f"[精准检索进度] {processed}/{total} 个节点已处理"
                    logger.info(progress_msg)
                    # 不发送到前端，避免刷屏，只记录日志

                filtered_results = self.insert_block_filter.filter_nodes(
                    question=question,
                    nodes=final_nodes,
                    llm_id=insert_block_llm_id,
                    progress_callback=progress_callback
                )

                if filtered_results:
                    yield ('CONTENT', f"找到 {len(filtered_results)} 个可回答的节点")
                    full_response += f"找到 {len(filtered_results)} 个可回答的节点\n"
                    # InsertBlock 成功：只使用过滤后的节点
                    nodes_for_prompt = None  # 不再传入原始节点
                    filtered_map = {}
                    for result in filtered_results:
                        key = f"{result['file_name']}_{result['reranked_score']}"
                        filtered_map[key] = result
                else:
                    yield ('CONTENT', "未找到可直接回答的节点，将使用原始检索结果")
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
            yield ('CONTENT', status_msg)
            full_response += status_msg + "\n"

            # 5. 调用 LLM
            for result in self._call_llm(llm, prompt_parts, enable_thinking=enable_thinking):
                # result 是元组 (prefix_type, content)
                prefix_type, chunk = result
                if prefix_type == 'THINK':
                    yield ('THINK', chunk)
                    # 思考内容不计入 full_response
                elif prefix_type == 'CONTENT':
                    yield ('CONTENT', chunk)
                    full_response += chunk

            # 6. 输出参考来源
            reference_entries = self._build_reference_log_entries(final_nodes, filtered_map)

            if use_insert_block and filtered_results:
                # InsertBlock 模式：返回所有原始节点，但标注哪些被选中
                yield ('CONTENT', "\n\n**参考来源（全部检索结果）:**")
                full_response += "\n\n参考来源（全部检索结果）:"

                # 遍历所有原始节点，标注哪些被选中
                for i, node in enumerate(final_nodes):
                    file_name = node.node.metadata.get('file_name', '未知')
                    initial_score = node.node.metadata.get('initial_score', 0.0)
                    key = f"{file_name}_{node.score}"

                    # 检查该节点是否在过滤结果中
                    filtered_info = filtered_map.get(key)

                    # 提取检索元数据
                    retrieval_sources = node.node.metadata.get('retrieval_sources', [])
                    vector_score = node.node.metadata.get('vector_score', 0.0)
                    bm25_score = node.node.metadata.get('bm25_score', 0.0)
                    vector_rank = node.node.metadata.get('vector_rank')
                    bm25_rank = node.node.metadata.get('bm25_rank')
                    
                    source_data = {
                        "id": i + 1,
                        "fileName": file_name,
                        "initialScore": f"{initial_score:.4f}",
                        "rerankedScore": f"{node.score:.4f}",
                        "content": node.node.text.strip(),
                        # 检索元数据
                        "retrievalSources": retrieval_sources,
                        "vectorScore": f"{vector_score:.4f}",
                        "bm25Score": f"{bm25_score:.4f}",
                        # InsertBlock 特有字段
                        "canAnswer": filtered_info is not None,
                        "reasoning": filtered_info.get('reasoning', '') if filtered_info else '',
                        "keyPassage": filtered_info.get('key_passage', '') if filtered_info else ''
                    }
                    
                    # 添加排名信息（如果存在）
                    if vector_rank is not None:
                        source_data['vectorRank'] = vector_rank
                    if bm25_rank is not None:
                        source_data['bm25Rank'] = bm25_rank
                    
                    # 添加匹配的关键词（如果是关键词检索）
                    if 'keyword' in retrieval_sources:
                        matched_keywords = node.node.metadata.get('bm25_matched_keywords', [])
                        if matched_keywords:
                            source_data['matchedKeywords'] = matched_keywords

                    yield ('SOURCE', json.dumps(source_data, ensure_ascii=False))

                    full_response += (
                        f"\n[{source_data['id']}] 文件: {source_data['fileName']}, "
                        f"重排分: {source_data['rerankedScore']}, "
                        f"可回答: {source_data['canAnswer']}"
                    )

            elif final_nodes:
                # 普通模式：显示所有检索结果
                yield ('CONTENT', "\n\n**参考来源:**")
                full_response += "\n\n参考来源:"

                for source_msg in self._format_sources(final_nodes):
                    yield source_msg
                    if isinstance(source_msg, tuple) and source_msg[0] == "SOURCE":
                        data = json.loads(source_msg[1])
                        full_response += (
                            f"\n[{data['id']}] 文件: {data['fileName']}, "
                            f"初始分: {data['initialScore']}, "
                            f"重排分: {data['rerankedScore']}"
                        )

            self._log_reference_details(
                question=question,
                references=reference_entries,
                mode="single"
            )

            yield ('DONE', '')

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
            yield ('ERROR', error_msg)

    def _retrieve_and_rerank(self, question: str, rerank_top_n: int, conversation_history: Optional[List[Dict]] = None):
        """
        检索和重排序（支持子问题分解）
        
        Args:
            question: 用户查询
            rerank_top_n: 重排序返回数量
            conversation_history: 对话历史（用于多轮场景）
            
        Returns:
            检索节点列表
        """
        # 如果启用了子问题分解器，尝试使用分解检索
        if self.sub_question_decomposer and self.sub_question_decomposer.enabled:
            logger.info("[检索策略] 尝试使用子问题分解检索（多轮）")
            try:
                # 注意：多轮场景使用默认retriever，因为没有意图分类
                # 如果需要支持多轮+意图路由，需要在这里也添加意图分类逻辑
                nodes, metadata = self.sub_question_decomposer.retrieve_with_decomposition(
                    query=question,
                    rerank_top_n=rerank_top_n,
                    conversation_history=conversation_history
                )
                
                # 记录分解元数据
                if metadata.get('decomposed'):
                    logger.info(
                        f"[子问题检索] 分解检索完成 | "
                        f"子问题数: {len(metadata['sub_questions'])} | "
                        f"返回节点数: {len(nodes)}"
                    )
                    # 记录详细的子问题信息到日志
                    for i, sub_result in enumerate(metadata['sub_results'], 1):
                        logger.info(
                            f"  子问题{i}: {sub_result['sub_question']} | "
                            f"节点数: {sub_result['node_count']} | "
                            f"最高分: {sub_result['top_score']:.4f}"
                        )
                    
                    # 可选：生成子问题答案合成（如果有sub_answers）
                    if metadata.get('sub_answers') and len(metadata['sub_answers']) > 0:
                        try:
                            synthesized_answer = self.sub_question_decomposer.synthesize_answer(
                                original_query=question,
                                sub_answers=metadata['sub_answers']
                            )
                            if synthesized_answer:
                                # 将合成答案添加到metadata，供后续使用
                                metadata['synthesized_answer'] = synthesized_answer
                                # 存储为实例变量，供_build_prompt使用
                                self._last_synthesized_answer = synthesized_answer
                                logger.info(f"[答案合成] 已生成合成答案 | 长度: {len(synthesized_answer)}")
                        except Exception as synth_e:
                            logger.warning(f"[答案合成] 合成失败: {synth_e}")
                else:
                    logger.info("[子问题检索] 未分解，使用标准检索")
                
                return nodes
                
            except Exception as e:
                logger.error(f"[子问题检索] 分解检索失败: {e}", exc_info=True)
                logger.info("[子问题检索] 回退到标准检索流程")
                # 继续执行标准检索
        
        # 标准检索流程
        logger.info(f"[单知识库检索] 开始检索问题: {question}")
        logger.info(f"🔍 [DEBUG] 使用的检索器对象ID: {id(self.retriever)}")
        logger.info(f"🔍 [DEBUG] 检索器类型: {type(self.retriever).__name__}")
        retrieved_nodes = self.retriever.retrieve(question)
        
        # 🔍 DEBUG: 记录初始检索得分
        if retrieved_nodes:
            initial_scores = [f"{n.score:.4f}" for n in retrieved_nodes[:5]]
            logger.info(f"[DEBUG] 单知识库初始检索Top5得分: {', '.join(initial_scores)}")

        # 取前 N 个送入重排
        reranker_input_top_n = Settings.RERANKER_INPUT_TOP_N
        logger.info(f"[单知识库检索] 配置检查 - RERANKER_INPUT_TOP_N: {reranker_input_top_n}")
        
        # 详细检查 retrieved_nodes
        logger.info(f"[单知识库检索] retrieved_nodes 类型: {type(retrieved_nodes)}")
        logger.info(f"[单知识库检索] retrieved_nodes 长度: {len(retrieved_nodes) if retrieved_nodes else 'None'}")
        
        if retrieved_nodes and len(retrieved_nodes) > 0:
            logger.info(f"[单知识库检索] 第一个节点预览: {retrieved_nodes[0].node.get_content()[:100]}...")
        
        reranker_input = retrieved_nodes[:reranker_input_top_n]

        logger.info(
            f"[单知识库检索] 初检索找到 {len(retrieved_nodes)} 个节点, "
            f"选取前 {len(reranker_input)} 个送入重排"
        )
        
        # 如果初始检索为空，打印警告
        if len(retrieved_nodes) == 0:
            logger.warning(
                f"[单知识库检索] ⚠️ 初始检索结果为空！\n"
                f"  问题: {question}\n"
                f"  检索器状态: {self.retriever is not None}\n"
                f"  可能原因: 知识库为空、索引损坏、或问题与知识库完全不相关"
            )

        # 重排序
        logger.info(f"[单知识库检索] 准备重排序 - reranker_input 长度: {len(reranker_input)}")
        
        if reranker_input:
            logger.info(f"[单知识库检索] ✓ 进入重排序分支，开始调用 Reranker 模型")
            logger.info(f"🔍 [DEBUG] Reranker 对象ID: {id(self.reranker)}")
            logger.info(f"🔍 [DEBUG] Reranker 类型: {type(self.reranker).__name__}")
            logger.info(f"🔍 [DEBUG] Reranker top_n: {self.reranker.top_n}")
            logger.info(f"🔍 [DEBUG] 问题长度: {len(question)} 字符")
            logger.info(f"🔍 [DEBUG] 问题内容: {question[:100]}...")
            
            # 🧪 临时实验：重新创建 Reranker 来验证是否是状态污染问题
            logger.warning("🧪 [实验] 临时重新创建 Reranker 来测试...")
            from llama_index.core.postprocessor import SentenceTransformerRerank
            temp_reranker = SentenceTransformerRerank(
                model=Settings.RERANKER_MODEL_PATH,
                top_n=Settings.RERANK_TOP_N,
                device=Settings.DEVICE
            )
            logger.info(f"🧪 [实验] 临时 Reranker 对象ID: {id(temp_reranker)}")
            
            reranked_nodes = temp_reranker.postprocess_nodes(
                reranker_input,
                query_bundle=QueryBundle(question)
            )
            logger.info("🧪 [实验] 使用临时 Reranker 完成重排序")
            logger.info(f"[单知识库检索] ✓ Reranker 处理完成，得到 {len(reranked_nodes)} 个节点")
            # 🔍 DEBUG: 记录重排序后得分
            if reranked_nodes:
                rerank_scores = [f"{n.score:.4f}" for n in reranked_nodes[:5]]
                logger.info(f"[DEBUG] 单知识库重排序后Top5得分: {', '.join(rerank_scores)}")
        else:
            logger.warning(f"[单知识库检索] ⚠️ reranker_input 为空，跳过重排序！")
            reranked_nodes = []

        # 阈值过滤
        threshold = Settings.RERANK_SCORE_THRESHOLD
        final_nodes = [
            node for node in reranked_nodes
            if node.score >= threshold
        ]
        
        # 🔍 DEBUG: 记录过滤后得分
        if final_nodes:
            final_scores = [f"{n.score:.4f}" for n in final_nodes[:5]]
            logger.info(f"[DEBUG] 单知识库阈值过滤后Top5得分: {', '.join(final_scores)}")

        logger.info(
            f"[单知识库检索] 重排序后有 {len(reranked_nodes)} 个节点, "
            f"经过阈值 {threshold} 过滤后剩下 {len(final_nodes)} 个"
        )
        
        # 如果阈值过滤后为空，打印详细信息
        if len(reranked_nodes) > 0 and len(final_nodes) == 0:
            max_score = max(node.score for node in reranked_nodes) if reranked_nodes else 0.0
            logger.warning(
                f"[单知识库检索] ⚠️ 阈值过滤后结果为空！\n"
                f"  重排序节点数: {len(reranked_nodes)}\n"
                f"  最高分数: {max_score:.4f}\n"
                f"  阈值: {threshold}\n"
                f"  建议: 降低 RERANK_SCORE_THRESHOLD 或检查 Reranker 模型"
            )

        # 应用最终数量限制
        result = final_nodes[:rerank_top_n]
        logger.info(f"[单知识库检索] 最终返回 {len(result)} 个节点")
        return result


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
            block_index = 1  # 用于编号实际添加的块
            
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

                # 构建包含关键段落和完整内容的块
                block = (
                    f"### 业务规定 {block_index} - {file_name}:\n"
                    # f"**【关键段落】**\n> {key_passage}\n\n"
                    f"**【完整内容】**\n> {full_content}"
                )
                context_blocks.append(block)
                block_index += 1
                logger.info(f"[精准检索通过] 节点已注入上下文: {file_name} | 关键段落长度: {len(key_passage)}")

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
                block = f"### 业务规定 {i + 1} - {file_name}:\n> {content}"
                context_blocks.append(block)

            formatted_context = "\n\n".join(context_blocks)
            has_rag = True
        else:
            formatted_context = None
            has_rag = False

        # 检查是否有子问题答案或合成答案需要注入
        has_sub_answers = hasattr(self, '_last_sub_answers') and self._last_sub_answers
        has_synthesis = hasattr(self, '_last_synthesized_answer') and self._last_synthesized_answer
        
        # 如果有检索文档或有子问题答案，都需要构建上下文
        if has_rag or has_sub_answers or has_synthesis:
            # 获取前缀
            assistant_prefix = get_knowledge_assistant_context_prefix()
            
            # 构建基础上下文
            if has_rag:
                assistant_context = assistant_prefix + formatted_context
            else:
                # 即使没有检索文档，也创建上下文用于注入子问题答案
                assistant_context = assistant_prefix + "**注意**: 未检索到相关业务规定文档，请基于以下子问题分析回答。\n"
                logger.info("[提示词构建] 无检索文档，但有子问题答案，创建上下文用于注入")
            
            # 如果有子问题答案，添加到上下文中
            if has_sub_answers:
                sub_answers_block = "\n\n### 📋 子问题分解与回答:\n"
                for i, sub_answer in enumerate(self._last_sub_answers, 1):
                    sub_q = sub_answer.get('sub_question', '')
                    answer = sub_answer.get('answer', '')
                    sub_answers_block += f"\n**子问题{i}**: {sub_q}\n**回答{i}**: {answer}\n"
                
                sub_answers_block += "\n**注意**: 以上是各子问题的独立回答，请结合这些信息和业务规定给出完整答案。"
                assistant_context += sub_answers_block
                logger.info(f"[提示词构建] 已将 {len(self._last_sub_answers)} 个子问题答案注入上下文")
            
            # 如果有子问题答案合成，添加到上下文中
            if self._last_synthesized_answer:
                synthesis_block = (
                    f"\n\n###  子问题综合分析:\n"
                    f"> {self._last_synthesized_answer}\n\n"
                    f"**注意**: 以上是对多个子问题答案的综合整理，请结合具体业务规定给出最终回答。"
                )
                assistant_context += synthesis_block
                logger.info(f"[提示词构建] 已将合成答案注入上下文 | 长度: {len(self._last_synthesized_answer)}")

            # 根据思考模式选择不同的 system 和 user prompt
            if enable_thinking:
                system_prompt = get_knowledge_system_rag_advanced()
                user_template = get_knowledge_user_rag_advanced()
            else:
                system_prompt = get_knowledge_system_rag_simple()
                user_template = get_knowledge_user_rag_simple()

            # user_template 是列表，需要 join 后再 format
            user_prompt_str = "\n".join(user_template) if isinstance(user_template, list) else user_template
            # 如果关闭思考模式，自动在问题后追加 /no_think 指令（阿里云文档建议）
            actual_question = f"{question}/no_think" if not enable_thinking else question
            if not enable_thinking:
                logger.info(f"✓ 已在问题后追加 /no_think 指令: '{actual_question}'")
            
            # 将参考资料直接注入到 user_prompt 中，而不是作为单独的 assistant_context
            user_prompt = user_prompt_str.format(context=assistant_context, question=actual_question)
            # 清空 assistant_context，因为已经合并到 user_prompt 中
            assistant_context_for_llm = None
            logger.info("[提示词构建] 已将参考资料合并到用户问题中（二段式）")

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
            # 如果关闭思考模式，自动在问题后追加 /no_think 指令（阿里云文档建议）
            actual_question = f"{question}/no_think" if not enable_thinking else question
            if not enable_thinking:
                logger.info(f"✓ 已在问题后追加 /no_think 指令: '{actual_question}'")
            user_prompt = user_prompt_str.format(question=actual_question)

        # system_prompt 可能是列表，需要转换为字符串
        if isinstance(system_prompt, list):
            system_prompt = "\n".join(system_prompt)

        # 确定实际传给 LLM 的 assistant_context
        # 如果使用二段式（参考资料已合并到 user_prompt），则传 None
        llm_assistant_context = assistant_context_for_llm if 'assistant_context_for_llm' in locals() else assistant_context

        # 构建 fallback_prompt（用于不支持 chat 模式的情况）
        fallback_parts = [system_prompt]
        if llm_assistant_context:
            fallback_parts.append(llm_assistant_context)
        fallback_parts.append(user_prompt)

        prompt_result = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "assistant_context": llm_assistant_context,  # 实际传给 LLM 的
            "assistant_context_log": assistant_context,  # 用于日志记录
            "fallback_prompt": "\n\n".join(fallback_parts)
        }
        
        # 输出上下文到日志文件
        self._log_prompt_to_file(question, prompt_result)
        
        return prompt_result

    def _log_prompt_to_file(self, question: str, prompt_parts: Dict[str, Any]):
        """
        将提示词上下文输出到日志文件（每次问答单独保存）
        
        Args:
            question: 用户问题
            prompt_parts: 提示词字典
        """
        try:
            # 确保 logs 目录存在
            logs_dir = Path("logs")
            logs_dir.mkdir(exist_ok=True)
            
            # 生成唯一的日志文件名（基于时间戳）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = logs_dir / f"prompt_{timestamp}.txt"
            
            # 构建日志内容（完整的单次问答上下文）
            log_content = []
            log_content.append("=" * 100)
            log_content.append(f"问答时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            log_content.append("=" * 100)
            log_content.append("")
            
            # 用户问题
            log_content.append("【用户问题】")
            log_content.append(question)
            log_content.append("")
            log_content.append("-" * 100)
            log_content.append("")
            
            # System Prompt
            log_content.append("【System Prompt】")
            log_content.append(prompt_parts.get('system_prompt', 'N/A'))
            log_content.append("")
            log_content.append("-" * 100)
            log_content.append("")
            
            # Assistant Context (检索文档 + 子问题答案)
            # 使用 assistant_context_log 显示完整的参考资料（即使已合并到用户问题中）
            context_for_log = prompt_parts.get('assistant_context_log') or prompt_parts.get('assistant_context')
            if context_for_log:
                log_content.append("【参考资料】（以下内容已注入到用户问题中）")
                log_content.append(context_for_log)
                log_content.append("")
                log_content.append("-" * 100)
                log_content.append("")
            else:
                log_content.append("【参考资料】")
                log_content.append("无检索文档或子问题答案")
                log_content.append("")
                log_content.append("-" * 100)
                log_content.append("")
            
            # User Prompt
            log_content.append("【User Prompt】")
            log_content.append(prompt_parts.get('user_prompt', 'N/A'))
            log_content.append("")
            log_content.append("=" * 100)
            
            # 写入文件（每次问答独立文件）
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(log_content))
            
            logger.info(f"[提示词日志] 已保存到 {log_file}")
            
            # 同时追加到总日志文件（可选，便于查看所有记录）
            all_logs_file = logs_dir / "prompts_logs_all.txt"
            with open(all_logs_file, 'a', encoding='utf-8') as f:
                f.write('\n'.join(log_content))
                f.write('\n\n')
            
        except Exception as e:
            logger.error(f"[提示词日志] 保存失败: {e}")

    def _call_llm(self, llm, prompt_parts, enable_thinking: bool = False):
        """
        调用 LLM，支持思考内容和正文内容的分离

        Args:
            llm: LLM 实例
            prompt_parts: 提示词字典
            enable_thinking: 是否启用思考模式（用于解析输出）

        Note:
            支持两种思考模式：
            1. 阿里云原生 reasoning_content 字段（推荐）
            2. 文本标记方式（兼容其他模型）
        """
        logger.info(f"使用外部 Prompt:\n{prompt_parts['fallback_prompt'][:200]}...")

        response_stream = self.llm_wrapper.stream(
            llm,
            prompt=prompt_parts['fallback_prompt'],
            system_prompt=prompt_parts['system_prompt'],
            user_prompt=prompt_parts['user_prompt'],
            assistant_context=prompt_parts['assistant_context'],
            use_chat_mode=Settings.USE_CHAT_MODE,
            enable_thinking=enable_thinking
        )

        # 如果启用思考模式，需要解析并分离思考内容和正文内容
        if enable_thinking:
            buffer = ""
            in_thinking_section = False
            thinking_complete = False
            has_reasoning_content = False  # 标记是否检测到原生 reasoning_content
            think_output_count = 0
            content_output_count = 0
            
            # 用于累积原生格式的内容
            reasoning_buffer = ""
            content_buffer = ""

            for delta in response_stream:
                # 优先检查阿里云原生的 reasoning_content 字段
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
                    has_reasoning_content = True
                    reasoning_text = delta.reasoning_content
                    if reasoning_text:
                        reasoning_buffer += reasoning_text
                        # 累积到一定长度后再发送
                        if len(reasoning_buffer) >= 10:
                            think_output_count += 1
                            output = ('THINK', clean_for_sse_text(reasoning_buffer))
                            yield output
                            reasoning_buffer = ""

                # 检查正常回答内容（无论是否有 reasoning_content，都要处理）
                if hasattr(delta, 'content') and delta.content is not None:
                    content_text = delta.content
                    if content_text:
                        content_buffer += content_text
                        # 累积到一定长度后再发送
                        if len(content_buffer) >= 10:
                            content_output_count += 1
                            output = ('CONTENT', clean_for_sse_text(content_buffer))
                            yield output
                            content_buffer = ""
                    # 如果有 reasoning_content 且已处理了 content，则跳过后续的文本标记解析
                    if has_reasoning_content:
                        continue

                # 如果没有 reasoning_content 字段，使用文本标记方式（兼容模式）
                if not has_reasoning_content:
                    # 获取文本内容
                    if hasattr(delta, 'delta'):
                        token = delta.delta
                    elif hasattr(delta, 'text'):
                        token = delta.text
                    elif hasattr(delta, 'content'):
                        token = delta.content
                    else:
                        token = str(delta) if delta else ''

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
                                    # 输出思考内容（不包含结束标记）
                                    idx = buffer.index(marker)
                                    if idx > 0:
                                        think_content = buffer[:idx]
                                        think_output_count += 1
                                        output = ('THINK', clean_for_sse_text(think_content))
                                        yield output

                                    # 跳过标记本身，只保留标记之后的内容
                                    buffer = buffer[idx + len(marker):]
                                    break

                    # 在思考区域且buffer足够长时，流式输出思考内容
                    if in_thinking_section and not thinking_complete and len(buffer) > 20:
                        think_output_count += 1
                        output = ('THINK', clean_for_sse_text(buffer))
                        yield output
                        buffer = ""
                    # 思考完成后，流式输出正文内容
                    elif thinking_complete and len(buffer) > 0:
                        # 只清理开头的标记符号（冒号等），保留换行符
                        cleaned_buffer = buffer.lstrip(':：')
                        if cleaned_buffer:
                            content_output_count += 1
                            output = ('CONTENT', clean_for_sse_text(cleaned_buffer))
                            yield output
                        buffer = ""

            # 输出剩余的buffer
            # 1. 原生格式的剩余内容
            if has_reasoning_content:
                if reasoning_buffer:
                    think_output_count += 1
                    output = ('THINK', clean_for_sse_text(reasoning_buffer))
                    yield output
                if content_buffer:
                    content_output_count += 1
                    output = ('CONTENT', clean_for_sse_text(content_buffer))
                    yield output
            # 2. 文本标记模式的剩余内容
            elif buffer:
                if in_thinking_section and not thinking_complete:
                    # 如果思考区域未完成，剩余内容作为思考输出
                    think_output_count += 1
                    output = ('THINK', clean_for_sse_text(buffer))
                    yield output
                else:
                    # 否则作为正文输出，只清理开头的标记符号，保留换行符
                    cleaned_buffer = buffer.lstrip(':：')
                    if cleaned_buffer:
                        content_output_count += 1
                        output = ('CONTENT', clean_for_sse_text(cleaned_buffer))
                        yield output
        else:
            # 不启用思考模式，所有内容都是正文
            buffer = ""
            for delta in response_stream:
                # 获取文本内容
                if hasattr(delta, 'delta'):
                    text = delta.delta
                elif hasattr(delta, 'text'):
                    text = delta.text
                elif hasattr(delta, 'content'):
                    text = delta.content
                else:
                    text = str(delta) if delta else ''

                if text:
                    buffer += text
                    # 智能发送策略：
                    # 1. 遇到换行符立即发送（保持换行的及时性）
                    # 2. 或者 buffer 达到 20 个字符发送（平衡性能）
                    if '\n' in buffer or len(buffer) >= 20:
                        yield ('CONTENT', clean_for_sse_text(buffer))
                        buffer = ""
            
            # 发送剩余内容
            if buffer:
                yield ('CONTENT', clean_for_sse_text(buffer))

    def _format_sources(self, final_nodes):
        """格式化参考来源"""
        for i, node in enumerate(final_nodes):
            initial_score = node.node.metadata.get('initial_score', 0.0)
            retrieval_sources = node.node.metadata.get('retrieval_sources', [])
            vector_score = node.node.metadata.get('vector_score', 0.0)
            bm25_score = node.node.metadata.get('bm25_score', 0.0)
            vector_rank = node.node.metadata.get('vector_rank')
            bm25_rank = node.node.metadata.get('bm25_rank')
            
            source_data = {
                "id": i + 1,
                "fileName": node.node.metadata.get('file_name', '未知'),
                "initialScore": f"{initial_score:.4f}",
                "rerankedScore": f"{node.score:.4f}",
                "content": node.node.text.strip(),
                "retrievalSources": retrieval_sources,
                "vectorScore": f"{vector_score:.4f}",
                "bm25Score": f"{bm25_score:.4f}"
            }
            
            # 添加排名信息（如果存在）
            if vector_rank is not None:
                source_data['vectorRank'] = vector_rank
            if bm25_rank is not None:
                source_data['bm25Rank'] = bm25_rank
            
            # 添加匹配的关键词（如果是关键词检索）
            if 'keyword' in retrieval_sources:
                matched_keywords = node.node.metadata.get('bm25_matched_keywords', [])
                if matched_keywords:
                    source_data['matchedKeywords'] = matched_keywords
            
            yield ('SOURCE', json.dumps(source_data, ensure_ascii=False))

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

    def _build_reference_log_entries(self, final_nodes, filtered_map=None):
        """构建用于日志记录的参考文献条目"""
        entries = []
        if not final_nodes:
            return entries

        for i, node in enumerate(final_nodes):
            file_name = node.node.metadata.get('file_name', '未知')
            initial_score = node.node.metadata.get('initial_score', 0.0)
            key = f"{file_name}_{node.score}"
            filtered_info = filtered_map.get(key) if filtered_map else None

            entries.append({
                "id": i + 1,
                "fileName": file_name,
                "initialScore": round(float(initial_score), 6),
                "rerankedScore": round(float(node.score or 0.0), 6),
                "canAnswer": (filtered_info is not None) if filtered_map else None,
                "reasoning": filtered_info.get('reasoning', '') if filtered_info else '',
                "keyPassage": filtered_info.get('key_passage', '') if filtered_info else '',
                "content": node.node.text.strip()
            })

        return entries

    def _log_reference_details(
        self,
        question: str,
        references: list,
        mode: str,
        session_id: Optional[str] = None
    ):
        """记录参考文献详情到日志文件"""
        try:
            os.makedirs(Settings.LOG_DIR, exist_ok=True)
            log_path = os.path.join(Settings.LOG_DIR, "reference_logs.jsonl")
            payload = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "mode": mode,
                "session_id": session_id,
                "question": question,
                "references": references
            }
            with open(log_path, "a", encoding="utf-8") as log_file:
                log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"记录参考文献日志失败: {e}")

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
        
        # 清空上一次的合成答案（避免污染）
        self._last_synthesized_answer = None

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

            # 1. 获取最近的对话历史（用于子问题分解）
            from config import Settings as AppSettings
            recent_turns_for_decomp = getattr(AppSettings, 'SUBQUESTION_HISTORY_COMPRESS_TURNS', 5)
            
            try:
                conversation_history_for_decomp = conversation_manager.get_recent_history(
                    session_id=session_id,
                    limit=recent_turns_for_decomp
                )
            except Exception as e:
                logger.warning(f"获取对话历史用于子问题分解失败: {e}")
                conversation_history_for_decomp = None
            
            # 2. 检索
            # 如果前端设置参考数量为 0，跳过检索
            if rerank_top_n == 0:
                logger.info("[对话-检索跳过] 前端设置参考数量为 0，跳过检索和子问题分解")
                final_nodes = []
            else:
                yield "CONTENT:正在进行混合检索..."
                full_response += "正在进行混合检索...\n"

                final_nodes = self._retrieve_and_rerank(
                    question, 
                    rerank_top_n,
                    conversation_history=conversation_history_for_decomp
                )

            # 2. 如果启用 InsertBlock 模式，进行智能过滤
            filtered_results = None
            filtered_map = None
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
                    filtered_map = {}
                    for result in filtered_results:
                        key = f"{result['file_name']}_{result['reranked_score']}"
                        filtered_map[key] = result
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

            if use_insert_block and filtered_results:
                yield "CONTENT:\n\n**参考来源（全部检索结果）:**"
                full_response += "\n\n参考来源（全部检索结果）:"

                for i, node in enumerate(final_nodes):
                    file_name = node.node.metadata.get('file_name', '未知')
                    initial_score = node.node.metadata.get('initial_score', 0.0)
                    key = f"{file_name}_{node.score}"

                    filtered_info = filtered_map.get(key)

                    # 提取检索元数据
                    retrieval_sources = node.node.metadata.get('retrieval_sources', [])
                    vector_score = node.node.metadata.get('vector_score', 0.0)
                    bm25_score = node.node.metadata.get('bm25_score', 0.0)
                    vector_rank = node.node.metadata.get('vector_rank')
                    bm25_rank = node.node.metadata.get('bm25_rank')

                    source_data = {
                        "id": i + 1,
                        "fileName": file_name,
                        "initialScore": f"{initial_score:.4f}",
                        "rerankedScore": f"{node.score:.4f}",
                        "content": node.node.text.strip(),
                        # 检索元数据
                        "retrievalSources": retrieval_sources,
                        "vectorScore": f"{vector_score:.4f}",
                        "bm25Score": f"{bm25_score:.4f}",
                        # InsertBlock 特有字段
                        "canAnswer": filtered_info is not None,
                        "reasoning": filtered_info.get('reasoning', '') if filtered_info else '',
                        "keyPassage": filtered_info.get('key_passage', '') if filtered_info else ''
                    }
                    
                    # 添加排名信息（如果存在）
                    if vector_rank is not None:
                        source_data['vectorRank'] = vector_rank
                    if bm25_rank is not None:
                        source_data['bm25Rank'] = bm25_rank
                    
                    # 添加匹配的关键词（如果是关键词检索）
                    if 'keyword' in retrieval_sources:
                        matched_keywords = node.node.metadata.get('bm25_matched_keywords', [])
                        if matched_keywords:
                            source_data['matchedKeywords'] = matched_keywords

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
                    # _format_sources 返回元组 ('SOURCE', json_data)
                    prefix_type, json_data = source_msg
                    if prefix_type == 'SOURCE':
                        formatted_msg = f"SOURCE:{json_data}"
                        yield formatted_msg
                        data = json.loads(json_data)
                        full_response += (
                            f"\n[{data['id']}] 文件: {data['fileName']}, "
                            f"重排分: {data['rerankedScore']}"
                        )

            reference_entries = self._build_reference_log_entries(final_nodes, filtered_map)

            self._log_reference_details(
                question=question,
                references=reference_entries,
                mode="conversation",
                session_id=session_id
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
            block_index = 1
            
            for result in filtered_results:
                file_name = result['file_name']
                key_passage = result.get('key_passage', '')
                full_content = result['node'].node.text.strip()
                can_answer = result.get('can_answer', False)
                
                # 严格过滤：只有 can_answer=True 且 key_passage 不为空才注入上下文
                if not can_answer:
                    logger.warning(f"[对话-精准检索过滤] 跳过不可回答的节点: {file_name}")
                    continue
                
                if not key_passage or key_passage.strip() == "":
                    logger.warning(f"[对话-精准检索过滤] 跳过无关键段落的节点: {file_name} | can_answer={can_answer}")
                    continue
                
                block = f"### 业务规定 {block_index} - {file_name}:\n> {full_content}"
                context_blocks.append(block)
                block_index += 1
                logger.info(f"[对话-精准检索通过] 节点已注入上下文: {file_name} | 关键段落长度: {len(key_passage)}")
                
            knowledge_context = "\n\n".join(context_blocks) if context_blocks else None

        elif final_nodes:
            # 使用普通检索结果
            context_blocks = []
            for i, node in enumerate(final_nodes):
                file_name = node.node.metadata.get('file_name', '未知文件')
                content = node.node.get_content().strip()
                block = f"### 业务规定 {i + 1} - {file_name}:\n> {content}"
                context_blocks.append(block)
            knowledge_context = "\n\n".join(context_blocks)

        has_rag = bool(knowledge_context)
        
        # 如果有子问题答案合成，添加到知识库上下文中
        if has_rag and self._last_synthesized_answer:
            synthesis_block = (
                f"\n\n### 🎯 子问题综合分析:\n"
                f"> {self._last_synthesized_answer}\n\n"
                f"**注意**: 以上是对多个子问题答案的综合整理，请结合具体业务规定给出最终回答。"
            )
            knowledge_context += synthesis_block
            logger.info(f"[多轮提示词构建] 已将合成答案注入上下文 | 长度: {len(self._last_synthesized_answer)}")

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
            # 如果关闭思考模式，自动在问题后追加 /no_think 指令（阿里云文档建议）
            actual_question = f"{question}/no_think" if not enable_thinking else question
            user_prompt = user_prompt_str.format(question=actual_question)

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
            # 如果关闭思考模式，自动在问题后追加 /no_think 指令（阿里云文档建议）
            actual_question = f"{question}/no_think" if not enable_thinking else question
            user_prompt = user_prompt_str.format(question=actual_question)

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
    
    def _smart_retrieve_and_rerank(self, question: str, rerank_top_n: int, conversation_history: Optional[List[Dict]] = None):
        """
        智能路由检索：先意图分类选择知识库，再可选子问题分解
        
        Args:
            question: 用户问题
            rerank_top_n: 重排序后返回的文档数量
            conversation_history: 对话历史（用于子问题分解）
            
        Returns:
            重排序后的节点列表
        """
        # 1. 意图分类（如果启用）
        strategy = "general"  # 默认策略：只用通用库
        
        if self.intent_classifier:
            try:
                strategy = self.intent_classifier.classify(question)
                logger.info(f"[智能路由] 意图分类结果: {strategy}")
            except Exception as e:
                logger.warning(f"[智能路由] 意图分类失败: {e}，使用默认策略: general")
                strategy = "general"
        else:
            logger.info("[智能路由] 意图分类器未启用，使用默认策略: general")
        
        # 2. 根据策略选择检索器
        if strategy == "both" and self.multi_kb_retriever:
            # 双库检索
            logger.info("[智能路由] 使用双库检索（免签库 + 通用库）")
            selected_retriever = self.multi_kb_retriever
        elif strategy == "visa_free" and self.visa_free_retriever:
            # 只用免签库
            logger.info("[智能路由] 使用免签知识库")
            selected_retriever = self.visa_free_retriever
        else:
            # 只用通用库（默认）
            logger.info("[智能路由] 使用通用知识库")
            selected_retriever = self.retriever
        
        # 3. 尝试子问题分解（如果启用），使用路由后的检索器
        if self.sub_question_decomposer and self.sub_question_decomposer.enabled:
            logger.info(f"[检索策略] 尝试使用子问题分解检索（单轮） | 目标库: {strategy}")
            try:
                nodes, metadata = self.sub_question_decomposer.retrieve_with_decomposition(
                    query=question,
                    rerank_top_n=rerank_top_n,
                    conversation_history=conversation_history,
                    retriever=selected_retriever  # 传入路由后的检索器
                )
                
                # 记录分解元数据
                if metadata.get('decomposed'):
                    logger.info(
                        f"[子问题检索] 分解检索完成 | "
                        f"子问题数: {len(metadata['sub_questions'])} | "
                        f"返回节点数: {len(nodes)} | "
                        f"使用库: {strategy}"
                    )
                    
                    # 保存子问题答案（用于注入上下文和返回前端）
                    if metadata.get('sub_answers') and len(metadata['sub_answers']) > 0:
                        # 存储子问题答案，供 _build_prompt 使用
                        self._last_sub_answers = metadata['sub_answers']
                        logger.info(f"[子问题答案] 已保存 {len(metadata['sub_answers'])} 个子问题答案，将注入上下文")
                        
                        # 可选：生成子问题答案合成
                        try:
                            synthesized_answer = self.sub_question_decomposer.synthesize_answer(
                                original_query=question,
                                sub_answers=metadata['sub_answers']
                            )
                            if synthesized_answer:
                                # 将合成答案添加到metadata，供后续使用
                                metadata['synthesized_answer'] = synthesized_answer
                                # 存储为实例变量，供_build_prompt使用
                                self._last_synthesized_answer = synthesized_answer
                                logger.info(f"[答案合成] 已生成合成答案 | 长度: {len(synthesized_answer)}")
                        except Exception as synth_e:
                            logger.warning(f"[答案合成] 合成失败: {synth_e}")
                    
                    # 返回节点和元数据
                    return nodes, metadata
                else:
                    logger.info("[子问题检索] 未分解，继续标准检索流程")
                    # 清空子问题答案，避免使用旧数据
                    self._last_sub_answers = None
                    # 继续执行标准检索
                    
            except Exception as e:
                logger.error(f"[子问题检索] 分解检索失败: {e}", exc_info=True)
                logger.info("[子问题检索] 回退到标准检索流程")
                # 清空子问题答案，避免使用旧数据
                self._last_sub_answers = None
                # 继续执行标准检索
        
        # 4. 标准检索和重排序
        return self._retrieve_and_rerank_with_retriever(
            question, 
            rerank_top_n, 
            selected_retriever
        )
    
    def _retrieve_and_rerank_with_retriever(
        self, 
        question: str, 
        rerank_top_n: int,
        retriever
    ):
        """
        使用指定检索器进行检索和重排序
        
        Args:
            question: 用户问题
            rerank_top_n: 重排序后返回的文档数量
            retriever: 检索器实例
            
        Returns:
            重排序后的节点列表
        """
        # 创建 QueryBundle（重排序需要）
        query_bundle = QueryBundle(query_str=question)
        
        # 判断是否为 MultiKBRetriever
        from core.multi_kb_retriever import MultiKBRetriever
        if isinstance(retriever, MultiKBRetriever):
            # MultiKBRetriever 使用 retrieve_from_both 方法，直接传入 query 字符串
            retrieved_nodes = retriever.retrieve_from_both(question)
        else:
            # 其他检索器使用标准的 retrieve 方法，需要 QueryBundle
            retrieved_nodes = retriever.retrieve(query_bundle)
        
        logger.info(f"检索到 {len(retrieved_nodes)} 个初步结果")
        
        if not retrieved_nodes:
            logger.warning("未检索到任何相关文档")
            return []
        
        # 添加日志：检索后的分数
        if retrieved_nodes:
            retrieval_scores = [n.score for n in retrieved_nodes[:5]]
            logger.info(f"检索阶段Top5得分: {[f'{s:.4f}' for s in retrieval_scores]}")
        
        # 保存原始节点的检索元数据（重排序可能会丢失）
        original_metadata = {}
        for node in retrieved_nodes:
            node_id = node.node.node_id
            original_metadata[node_id] = {
                'retrieval_sources': node.node.metadata.get('retrieval_sources', []),
                'vector_score': node.node.metadata.get('vector_score', 0.0),
                'bm25_score': node.node.metadata.get('bm25_score', 0.0),
                'bm25_matched_keywords': node.node.metadata.get('bm25_matched_keywords', []),
                'bm25_query_keywords': node.node.metadata.get('bm25_query_keywords', []),
                'vector_rank': node.node.metadata.get('vector_rank'),
                'bm25_rank': node.node.metadata.get('bm25_rank'),
                'initial_score': node.node.metadata.get('initial_score', node.score)
            }
        
        # 重排序
        reranked_nodes = self.reranker.postprocess_nodes(
            retrieved_nodes,
            query_bundle=query_bundle
        )
        
        logger.info(f"重排序后保留 {len(reranked_nodes)} 个结果")
        
        # 恢复原始节点的检索元数据
        for node in reranked_nodes:
            node_id = node.node.node_id
            if node_id in original_metadata:
                metadata = original_metadata[node_id]
                node.node.metadata.update(metadata)
        
        logger.info(f"已恢复 {len([n for n in reranked_nodes if n.node.metadata.get('retrieval_sources')])} 个节点的检索元数据")
        
        # 添加日志：重排序后的分数
        if reranked_nodes:
            rerank_scores = [n.score for n in reranked_nodes[:5]]
            logger.info(f"重排序阶段Top5得分: {[f'{s:.4f}' for s in rerank_scores]}")
        
        # 方案1+3组合：按得分排序后严格截断到前端要求的数量
        # 确保按分数从高到低排序
        reranked_nodes.sort(key=lambda x: x.score, reverse=True)
        
        # 严格按照前端传入的 rerank_top_n 参数截断
        final_nodes = reranked_nodes[:rerank_top_n]
        
        if final_nodes:
            logger.info(
                f"最终返回 {len(final_nodes)} 个文档（严格按前端参数 top_k={rerank_top_n} 截断） | "
                f"最高分: {final_nodes[0].score:.4f} | "
                f"最低分: {final_nodes[-1].score:.4f}"
            )
        
        return final_nodes

    def debug_inspect_scores(
        self,
        question: str,
        *,
        retriever=None,
        match_substring: Optional[str] = None,
        match_node_id: Optional[str] = None,
        max_candidates: int = 50,
        include_full_text: bool = False,
        run_reranker: bool = True
    ) -> Dict[str, Any]:
        """
        调试辅助：查看检索/重排序阶段的节点得分。
        仅在显式调用时执行，不影响现有流程。
        """
        if not question:
            raise ValueError("question 不能为空")

        active_retriever = retriever or self.retriever
        if active_retriever is None:
            raise RuntimeError("未配置检索器，无法执行调试")

        if run_reranker and self.reranker is None:
            raise RuntimeError("未配置重排器，无法执行调试")

        query_bundle = QueryBundle(query_str=question)

        def _execute_retriever() -> List[Any]:
            """兼容多知识库检索器的调用方式"""
            try:
                from core.multi_kb_retriever import MultiKBRetriever
            except ImportError:
                MultiKBRetriever = None  # type: ignore

            if MultiKBRetriever and isinstance(active_retriever, MultiKBRetriever):
                return active_retriever.retrieve_from_all_three(question)

            return active_retriever.retrieve(query_bundle)

        def _serialize_nodes(nodes: List[Any], stage: str) -> List[Dict[str, Any]]:
            serialized = []
            for idx, node_score in enumerate(nodes[:max_candidates], start=1):
                node = node_score.node
                metadata = node.metadata or {}
                text = node.get_content()
                preview = text[:120].replace("\n", " ").strip()
                vector_rank = metadata.get("vector_rank")
                bm25_rank = metadata.get("bm25_rank")
                sources = metadata.get("retrieval_sources") or []
                source_label = "/".join(sources) if sources else "unknown"

                entry = {
                    "stage": stage,
                    "rank": idx,
                    "node_id": node.node_id,
                    "score": float(node_score.score or 0.0),
                    "vector_score": float(metadata.get("vector_score", 0.0)),
                    "bm25_score": float(metadata.get("bm25_score", 0.0)),
                    "vector_rank": vector_rank,
                    "bm25_rank": bm25_rank,
                    "sources": sources,
                    "source_label": source_label,
                    "file_name": metadata.get("file_name"),
                    "file_path": metadata.get("file_path"),
                    "text_preview": preview,
                    "metadata": metadata
                }

                if include_full_text:
                    entry["text"] = text

                serialized.append(entry)

            return serialized

        def _is_match(entry: Dict[str, Any]) -> bool:
            if not match_substring and not match_node_id:
                return False

            matched = True

            if match_substring:
                needle = match_substring.lower()
                haystack = [
                    (entry.get("text_preview") or "").lower(),
                    (entry.get("file_name") or "").lower(),
                ]
                if include_full_text:
                    haystack.append((entry.get("text") or "").lower())
                matched = any(needle in segment for segment in haystack)

            if matched and match_node_id:
                matched = match_node_id in (entry.get("node_id") or "")

            return matched

        retrieved_nodes = _execute_retriever() or []
        retrieval_serialized = _serialize_nodes(retrieved_nodes, stage="retrieval")

        rerank_serialized: List[Dict[str, Any]] = []
        if run_reranker and retrieved_nodes:
            reranked = self.reranker.postprocess_nodes(
                retrieved_nodes,
                query_bundle=query_bundle
            )
            reranked.sort(key=lambda x: x.score, reverse=True)
            rerank_serialized = _serialize_nodes(reranked, stage="rerank")

        matched_entries = []
        for entry in retrieval_serialized + rerank_serialized:
            if _is_match(entry):
                matched_entries.append(entry)

        return {
            "question": question,
            "retriever_type": type(active_retriever).__name__,
            "retrieval": retrieval_serialized,
            "rerank": rerank_serialized,
            "matches": matched_entries,
            "match_conditions": {
                "substring": match_substring,
                "node_id": match_node_id
            }
        }
