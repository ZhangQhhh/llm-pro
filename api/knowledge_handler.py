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
from llama_index.core.schema import NodeWithScore
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
# 导入新的工具函数
from utils.knowledge_utils import (
    build_knowledge_prompt,
    format_sources,
    format_filtered_sources,
    build_reference_entries,
    log_prompt_to_file,
    log_reference_details,
    save_qa_log,
    parse_thinking_stream,
    parse_normal_stream
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
        sub_question_decomposer=None,
        # 隐藏知识库检索器（可选）
        hidden_kb_retriever=None
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
        # 隐藏知识库检索器
        self.hidden_kb_retriever = hidden_kb_retriever
        
        # 子问题答案合成（用于传递到提示词）
        self._last_synthesized_answer = None

        # 如果提供了 llm_service，初始化 InsertBlock 过滤器
        if llm_service:
            from core.node_filter import InsertBlockFilter
            self.insert_block_filter = InsertBlockFilter(llm_service)
        
        # 知识库功能状态（仅在调试时启用）
        # enabled_features = []
        # if self.multi_kb_retriever and self.intent_classifier:
        #     enabled_features.append("多库检索+意图分类")
        # if enabled_features:
        #     logger.info(f"✓ 知识库功能已启用: {', '.join(enabled_features)}")

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
            # 处理知识问答
            pass

            # 1. 智能路由检索（根据意图选择知识库）
            # 如果前端设置参考数量为 0，跳过检索
            if rerank_top_n == 0:
                # 跳过检索
                pass
                final_nodes = []
                result = None
                hidden_nodes = []
            else:
                yield ('CONTENT', "正在进行混合检索...\n")
                full_response += "正在进行混合检索...\n"
                
                # 调用检索，获取节点和元数据
                result = self._smart_retrieve_and_rerank(question, rerank_top_n)
                
                # 1.5 隐藏知识库检索（并行进行，不影响主流程）
                hidden_nodes = []
                if self.hidden_kb_retriever and self.hidden_kb_retriever.enabled:
                    try:
                        logger.info("[hidden knowledge库] 开始并行检索...")
                        hidden_nodes = self.hidden_kb_retriever.retrieve(question)
                        if hidden_nodes:
                            logger.info(f"[hidden knowledge库] 检索成功 | 返回 {len(hidden_nodes)} 条")
                            
                            # 根据配置决定是否将隐藏节点合并到显示列表
                            if Settings.HIDDEN_KB_INJECT_MODE == "visible":
                                logger.info("[hidden knowledge库] visible 模式：将隐藏节点合并到参考来源")
                                # 注意：不修改 final_nodes，在显示时处理
                            else:
                                logger.info("[hidden knowledge库] silent 模式：隐藏节点不显示来源")
                        else:
                            logger.info("[hidden knowledge库] 未检索到相关内容")
                    except Exception as e:
                        logger.warning(f"[hidden knowledge库] 检索失败，继续主流程: {e}")
                        hidden_nodes = []
            
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
                # 发送开始消息
                start_msg = f"正在使用精准检索分析 {len(final_nodes)} 个文档...\n提示：系统正在逐个判断每个文档是否能回答您的问题，请稍候\n"
                yield ('CONTENT', start_msg)
                full_response += start_msg
                
                # 使用队列收集进度
                import queue
                import threading
                progress_queue = queue.Queue()
                filter_done = threading.Event()
                
                # 定义进度回调函数（将进度放入队列）
                def progress_callback(processed, total):
                    progress_queue.put((processed, total))
                
                # 在后台线程执行过滤
                def run_filter():
                    try:
                        result = self.insert_block_filter.filter_nodes(
                            question=question,
                            nodes=final_nodes,
                            llm_id=insert_block_llm_id,
                            progress_callback=progress_callback
                        )
                        progress_queue.put(('DONE', result))
                    except Exception as e:
                        progress_queue.put(('ERROR', e))
                    finally:
                        filter_done.set()
                
                filter_thread = threading.Thread(target=run_filter, daemon=True)
                filter_thread.start()
                
                # 主线程定期检查进度并发送
                last_progress = 0
                filtered_results = None
                
                filter_error = None
                while not filter_done.is_set():
                    try:
                        # 等待0.5秒或直到有新进度
                        item = progress_queue.get(timeout=0.5)
                        
                        if isinstance(item, tuple):
                            if item[0] == 'DONE':
                                filtered_results = item[1]
                                break
                            elif item[0] == 'ERROR':
                                filter_error = item[1]
                                logger.error(f"精准检索过滤失败: {filter_error}")
                                # 通知前端错误信息
                                error_msg = f" 精准检索失败: {str(filter_error)}\n"
                                yield ('CONTENT', error_msg)
                                full_response += error_msg
                                break
                            else:
                                # 进度更新
                                processed, total = item
                                # 每处理5个文档发送一次进度（避免刷屏）
                                if processed - last_progress >= 5 or processed == total:
                                    progress_msg = f"📊 进度: {processed}/{total} ({int(processed/total*100)}%)\n"
                                    yield ('CONTENT', progress_msg)
                                    full_response += progress_msg
                                    last_progress = processed
                    except queue.Empty:
                        # 超时，继续等待
                        continue
                
                # 等待线程结束（超时时间应足够长，覆盖所有节点处理）
                # 假设并发处理，最多需要 (节点数/并发数) * 单节点超时时间
                # 给予充足的时间：300秒（5分钟）
                filter_thread.join(timeout=300)
                
                # 检查线程是否还在运行
                if filter_thread.is_alive():
                    logger.warning("精准检索线程超时未完成（300秒），将继续使用原始检索结果")
                    timeout_msg = " 精准检索处理超时（5分钟），将使用原始检索结果\n"
                    yield ('CONTENT', timeout_msg)
                    full_response += timeout_msg
                    filtered_results = None

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

            # 3. 构造提示词（使用新工具函数，注入隐藏知识库内容）
            prompt_parts = build_knowledge_prompt(
                question=question,
                enable_thinking=enable_thinking,
                final_nodes=nodes_for_prompt,  # 根据 InsertBlock 结果决定传入哪些节点
                filtered_results=filtered_results,
                sub_answers=getattr(self, '_last_sub_answers', None),
                synthesized_answer=getattr(self, '_last_synthesized_answer', None),
                hidden_nodes=hidden_nodes  # 隐藏知识库节点（不显示来源）
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
                    logger.debug(f"[Handler] 收到 THINK 消息: {len(chunk)} 字符 | 内容预览: {chunk[:50]}")
                    yield ('THINK', chunk)
                    logger.debug(f"[Handler] 已 yield THINK 消息")
                    # 思考内容不计入 full_response
                elif prefix_type == 'CONTENT':
                    yield ('CONTENT', chunk)
                    full_response += chunk

            # 6. 收集并输出全局关键字（去重后限制数量）
            # 6.1 使用权重排序提取问题关键词
            from utils.keyword_ranker import keyword_ranker
            
            # 计算问题关键词的 TF 权重并排序
            question_keywords_ranked = keyword_ranker.rank_question_keywords(question, top_k=100)
            
            # 6.2 收集文档匹配的关键字并计算权重
            document_keywords_ranked = []
            if final_nodes:
                for i, node in enumerate(final_nodes):
                    retrieval_sources = node.node.metadata.get('retrieval_sources', [])
                    if 'keyword' in retrieval_sources:
                        matched_keywords = node.node.metadata.get('bm25_matched_keywords', [])
                        node_score = node.score
                        
                        # 计算文档关键词权重
                        doc_kw_ranked = keyword_ranker.rank_document_keywords(
                            matched_keywords, 
                            node_score,
                            top_k=50
                        )
                        document_keywords_ranked.extend(doc_kw_ranked)
            
            # 6.3 合并并按权重排序关键词
            final_keywords = keyword_ranker.merge_and_rank_keywords(
                question_keywords_ranked,
                document_keywords_ranked,
                max_display=Settings.MAX_DISPLAY_KEYWORDS
            )
            
            # 为了兼容旧代码，分离问题关键词和文档关键词
            # 问题关键词：在问题中出现的
            question_kw_set = set([kw for kw, _ in question_keywords_ranked])
            unique_question_keywords = [kw for kw in final_keywords if kw in question_kw_set]
            
            # 文档关键词：不在问题中的
            unique_doc_keywords = [kw for kw in final_keywords if kw not in question_kw_set]
            
            # 保持原有的固定分配逻辑（但已经按权重排序）
            seen_doc = set(unique_question_keywords)
            for kw in unique_doc_keywords:
                if kw not in seen_doc:
                    seen_doc.add(kw)
                    unique_doc_keywords.append(kw)
            
            # 限制数量（使用 MAX_DISPLAY_KEYWORDS）
            max_global_keywords = getattr(Settings, 'MAX_DISPLAY_KEYWORDS', 10)
            
            # 固定分配策略：问题关键词和文档关键词各占一半
            max_question_keywords = max_global_keywords // 2  # 一半给问题关键词
            max_doc_keywords = max_global_keywords - max_question_keywords  # 另一半给文档关键词
            
            final_question_keywords = unique_question_keywords[:max_question_keywords]
            final_doc_keywords = unique_doc_keywords[:max_doc_keywords]
            
            # 输出结构化关键字（区分来源）
            keywords_data = {
                "question": final_question_keywords,
                "document": final_doc_keywords
            }
            if final_question_keywords or final_doc_keywords:
                yield ('KEYWORDS', json.dumps(keywords_data, ensure_ascii=False))

            # 7. 输出参考来源（使用新工具函数）
            reference_entries = build_reference_entries(final_nodes, filtered_map)

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
                    
                    # 添加匹配的关键词（BM25 检索）
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
                # 普通模式：显示所有检索结果（使用新工具函数）
                yield ('CONTENT', "\n\n**参考来源:**")
                full_response += "\n\n参考来源:"

                # 合并隐藏节点（如果是 visible 模式）
                nodes_to_display = final_nodes
                if hidden_nodes and Settings.HIDDEN_KB_INJECT_MODE == "visible":
                    logger.info(
                        f"[隐藏知识库] 合并 {len(hidden_nodes)} 个隐藏节点到参考来源 | "
                        f"主知识库: {len(final_nodes)} 条 | "
                        f"隐藏节点: {len(hidden_nodes)} 条 (额外显示，不占用 rerank_top_n) | "
                        f"总计: {len(final_nodes) + len(hidden_nodes)} 条"
                    )
                    nodes_to_display = final_nodes + hidden_nodes
                
                # 根据配置决定是否包含隐藏节点
                include_hidden = (Settings.HIDDEN_KB_INJECT_MODE == "visible")
                
                for source_msg in format_sources(nodes_to_display, include_hidden=include_hidden):
                    yield source_msg
                    if isinstance(source_msg, tuple) and source_msg[0] == "SOURCE":
                        data = json.loads(source_msg[1])
                        full_response += (
                            f"\n[{data['id']}] 文件: {data['fileName']}, "
                            f"初始分: {data['initialScore']}, "
                            f"重排分: {data['rerankedScore']}"
                        )

            # 使用新工具函数记录参考文献
            log_reference_details(
                question=question,
                references=reference_entries,
                mode="single"
            )

            # 8. 格式化校验和修复（在最后一次 yield 前）
            from utils.response_formatter import response_formatter
            
            # 提取纯文本响应（去除状态消息）
            # full_response 包含了所有 CONTENT 内容，需要提取 LLM 实际回答部分
            # 简单处理：去除检索状态消息
            response_to_validate = full_response
            for status_prefix in [
                "正在进行混合检索...",
                "已找到相关资料，正在生成回答...",
                "未找到高相关性资料，基于通用知识回答...",
                "正在使用精准检索分析",
                "进度:",
                "找到",
                "未找到可直接回答的节点",
                "参考来源"
            ]:
                if status_prefix in response_to_validate:
                    # 移除状态消息行
                    lines = response_to_validate.split('\n')
                    filtered_lines = [line for line in lines if not line.strip().startswith(status_prefix)]
                    response_to_validate = '\n'.join(filtered_lines)
            
            # 格式化校验
            validated_response = response_formatter.process_response(
                response_to_validate.strip(),
                question=question
            )
            
            # 如果格式被修复，更新响应
            if validated_response != response_to_validate.strip():
                full_response = validated_response

            yield ('DONE', '')

            # 9. 保存日志（使用新工具函数）
            save_qa_log(
                question=question,
                response=full_response,
                client_ip=client_ip,
                has_rag=bool(final_nodes),
                use_insert_block=use_insert_block
            )

        except Exception as e:
            error_msg = f"处理错误: {str(e)}"
            logger.error(f"知识问答处理出错: {e}", exc_info=True)
            yield ('ERROR', error_msg)
            # 确保发送 DONE 信号，避免前端等待超时
            yield ('DONE', '')

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
                f"[单知识库检索] 初始检索结果为空！\n"
                f"  问题: {question}\n"
                f"  检索器状态: {self.retriever is not None}\n"
                f"  可能原因: 知识库为空、索引损坏、或问题与知识库完全不相关"
            )

        # 重排序
        logger.info(f"[单知识库检索] 准备重排序 - reranker_input 长度: {len(reranker_input)}")
        
        if reranker_input:
            logger.info(f"[单知识库检索] ✓ 进入重排序分支，开始调用 Reranker 模型")
            
            # 使用实例的 Reranker（已修复状态污染问题）
            reranked_nodes = self.reranker.postprocess_nodes(
                reranker_input,
                query_bundle=QueryBundle(question)
            )
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
        
        #  DEBUG: 记录过滤后得分
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
                f"[单知识库检索] 阈值过滤后结果为空！\n"
                f"  重排序节点数: {len(reranked_nodes)}\n"
                f"  最高分数: {max_score:.4f}\n"
                f"  阈值: {threshold}\n"
                f"  建议: 降低 RERANK_SCORE_THRESHOLD 或检查 Reranker 模型"
            )

        # 应用最终数量限制
        result = final_nodes[:rerank_top_n]
        logger.info(f"[单知识库检索] 最终返回 {len(result)} 个节点")
        return result

    def _call_llm(self, llm, prompt_parts, enable_thinking: bool = False):
        """
        调用 LLM，支持思考内容和正文内容的分离（使用新工具函数）

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

        # 使用新工具函数解析流式输出
        if enable_thinking:
            yield from parse_thinking_stream(response_stream)
        else:
            yield from parse_normal_stream(response_stream)

   

    def _save_log(self, question: str, response: str, client_ip: str, has_rag: bool, use_insert_block: bool = False):
        """
        【已废弃】保存问答日志 - 已被 save_qa_log 工具函数替代
        保留此方法作为备份，待测试通过后可删除
        """
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
                hidden_nodes = []
            else:
                yield "CONTENT:正在进行混合检索..."
                full_response += "正在进行混合检索...\n"

                final_nodes = self._retrieve_and_rerank(
                    question, 
                    rerank_top_n,
                    conversation_history=conversation_history_for_decomp
                )
                
                # 2.5 隐藏知识库检索（并行进行）
                hidden_nodes = []
                if self.hidden_kb_retriever and self.hidden_kb_retriever.enabled:
                    try:
                        logger.info("[对话-隐藏知识库] 开始并行检索...")
                        hidden_nodes = self.hidden_kb_retriever.retrieve(question)
                        if hidden_nodes:
                            logger.info(f"[对话-隐藏知识库] 检索成功 | 返回 {len(hidden_nodes)} 条")
                            
                            # 根据配置决定是否将隐藏节点合并到显示列表
                            if Settings.HIDDEN_KB_INJECT_MODE == "visible":
                                logger.info("[对话-隐藏知识库] visible 模式：将隐藏节点合并到参考来源")
                            else:
                                logger.info("[对话-隐藏知识库] silent 模式：隐藏节点不显示来源")
                    except Exception as e:
                        logger.warning(f"[对话-隐藏知识库] 检索失败: {e}")
                        hidden_nodes = []

            # 2. 如果启用 InsertBlock 模式，进行智能过滤
            filtered_results = None
            filtered_map = None
            nodes_for_prompt = final_nodes

            if use_insert_block and final_nodes and self.insert_block_filter:
                start_msg = f"正在使用精准检索分析 {len(final_nodes)} 个文档...\n提示：系统正在逐个判断每个文档是否能回答您的问题，请稍候"
                yield f"CONTENT:{start_msg}"
                full_response += start_msg + "\n"
                
                # 使用队列收集进度
                import queue
                import threading
                progress_queue = queue.Queue()
                filter_done = threading.Event()
                
                # 定义进度回调函数（将进度放入队列）
                def progress_callback(processed, total):
                    logger.info(f"[对话-精准检索进度] {processed}/{total} 个文档已分析")
                    progress_queue.put((processed, total))
                
                # 在后台线程执行过滤
                def run_filter():
                    try:
                        result = self.insert_block_filter.filter_nodes(
                            question=question,
                            nodes=final_nodes,
                            llm_id=insert_block_llm_id,
                            progress_callback=progress_callback
                        )
                        progress_queue.put(('DONE', result))
                    except Exception as e:
                        progress_queue.put(('ERROR', e))
                    finally:
                        filter_done.set()
                
                filter_thread = threading.Thread(target=run_filter, daemon=True)
                filter_thread.start()
                
                # 主线程定期检查进度并发送
                last_progress = 0
                filtered_results = None
                
                while not filter_done.is_set():
                    try:
                        # 等待0.5秒或直到有新进度
                        item = progress_queue.get(timeout=0.5)
                        
                        if isinstance(item, tuple):
                            if item[0] == 'DONE':
                                filtered_results = item[1]
                                break
                            elif item[0] == 'ERROR':
                                logger.error(f"对话-精准检索过滤失败: {item[1]}")
                                break
                            else:
                                # 进度更新
                                processed, total = item
                                # 每处理5个文档发送一次进度（避免刷屏）
                                if processed - last_progress >= 5 or processed == total:
                                    progress_msg = f"📊 进度: {processed}/{total} ({int(processed/total*100)}%)"
                                    yield f"CONTENT:{progress_msg}"
                                    full_response += progress_msg + "\n"
                                    last_progress = processed
                    except queue.Empty:
                        # 超时，继续等待
                        continue
                
                # 等待线程结束（多轮对话模式，同样给予充足时间）
                filter_thread.join(timeout=600)

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

            # 5. 使用优化的提示词构建方式（注入历史对话和隐藏知识库）
            prompt_parts = self._build_prompt_with_history(
                question,
                enable_thinking,
                nodes_for_prompt,
                filtered_results=filtered_results,
                recent_history=recent_history,
                relevant_history=relevant_history,
                history_summary=history_summary,
                hidden_nodes=hidden_nodes
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
                turn_id=current_turn_id,
                parent_turn_id=parent_turn_id
            )
            
            # 7. 收集并输出全局关键字（去重后限制数量）
            # 6.1 提取问题中的关键词
            import jieba
            all_keywords = list(jieba.lcut(question))
            # 过滤单字即可，保留所有多字词
            question_keywords = [kw for kw in all_keywords if len(kw) > 1]
            
            
            # 7.2 收集文档匹配的关键字
            global_keywords = []
            if final_nodes:
                for i, node in enumerate(final_nodes):
                    retrieval_sources = node.node.metadata.get('retrieval_sources', [])
                    if 'keyword' in retrieval_sources:
                        matched_keywords = node.node.metadata.get('bm25_matched_keywords', [])
                        global_keywords.extend(matched_keywords)
                    
            
            # 7.3 去重问题关键词和文档关键词
            # 问题关键词去重并优先排序（专业术语优先）
            seen_question = set()
            unique_question_keywords = []
            
            # 专业术语优先列表（这些词优先显示）
            priority_terms = {'J2', 'J1', 'X1', 'X2', 'SLTD', 'APEC卡', 
                            'J2签证', 'J1签证', 'X1签证', 'X2签证',
                            'J2字签证', 'J1字签证', 'X1字签证', 'X2字签证'}
            
            # 先添加优先术语
            for kw in question_keywords:
                if kw in priority_terms and kw not in seen_question:
                    seen_question.add(kw)
                    unique_question_keywords.append(kw)
            
            # 再添加其他关键词
            for kw in question_keywords:
                if kw not in seen_question:
                    seen_question.add(kw)
                    unique_question_keywords.append(kw)
            
            # 文档关键词去重（排除已在问题中的）
            seen_doc = set(unique_question_keywords)
            unique_doc_keywords = []
            for kw in global_keywords:
                if kw not in seen_doc:
                    seen_doc.add(kw)
                    unique_doc_keywords.append(kw)
            
            # 限制数量（使用 MAX_DISPLAY_KEYWORDS）
            from config import Settings as AppSettings
            max_global_keywords = getattr(AppSettings, 'MAX_DISPLAY_KEYWORDS', 5)
            
            # 分别限制问题关键词和文档关键词
            final_question_keywords = unique_question_keywords[:max_global_keywords]
            remaining_slots = max_global_keywords - len(final_question_keywords)
            final_doc_keywords = unique_doc_keywords[:remaining_slots] if remaining_slots > 0 else []
            
            # 输出结构化关键字（区分来源）
            keywords_data = {
                "question": final_question_keywords,
                "document": final_doc_keywords
            }
            if final_question_keywords or final_doc_keywords:
                yield f"KEYWORDS:{json.dumps(keywords_data, ensure_ascii=False)}"

            # 8. 输出参考来源
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
                    
                    # 添加匹配的关键词（BM25 检索）
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

                # 合并隐藏节点（如果是 visible 模式）
                nodes_to_display = final_nodes
                if hidden_nodes and Settings.HIDDEN_KB_INJECT_MODE == "visible":
                    logger.info(
                        f"[对话-隐藏知识库] 合并 {len(hidden_nodes)} 个隐藏节点到参考来源 | "
                        f"主知识库: {len(final_nodes)} 条 | "
                        f"隐藏节点: {len(hidden_nodes)} 条 (额外显示，不占用 rerank_top_n) | "
                        f"总计: {len(final_nodes) + len(hidden_nodes)} 条"
                    )
                    nodes_to_display = final_nodes + hidden_nodes

                for i, node in enumerate(nodes_to_display):
                    # 检查是否为隐藏节点
                    is_hidden = node.node.metadata.get('is_hidden', False)
                    
                    # 构建 source_data
                    source_data = {
                        "id": i + 1,
                        "fileName": node.node.metadata.get('file_name', '未知'),
                        "rerankedScore": f"{node.score:.4f}",
                        "content": node.node.text.strip()
                    }
                    
                    # 如果是隐藏节点，添加特殊标记
                    if is_hidden:
                        source_data['isHidden'] = True
                        source_data['hiddenKbName'] = node.node.metadata.get('hidden_kb_name', '隐藏知识库')
                    
                    yield f"SOURCE:{json.dumps(source_data, ensure_ascii=False)}"
                    full_response += (
                        f"\n[{i + 1}] 文件: {source_data['fileName']}, "
                        f"重排分: {node.score}"
                    )

            # 格式化校验和修复（在最后一次 yield 前）
            from utils.response_formatter import response_formatter
            
            # 提取 assistant_response 进行格式化（这是实际的 LLM 回答）
            if assistant_response:
                validated_response = response_formatter.process_response(
                    assistant_response.strip(),
                    question=question
                )
                
                # 如果格式被修复，记录日志
                if validated_response != assistant_response.strip():
                    logger.info("[对话-格式修复] 响应格式已自动修复")

            yield "DONE:"

        except Exception as e:
            error_msg = f"处理错误: {str(e)}"
            logger.error(f"多轮对话处理出错: {e}", exc_info=True)
            yield f"ERROR:{error_msg}"
            # 确保发送 DONE 信号，避免前端等待超时
            yield "DONE:"

    def _build_prompt_with_history(
        self,
        question: str,
        enable_thinking: bool,
        final_nodes,
        filtered_results=None,
        recent_history=None,
        relevant_history=None,
        history_summary=None,
        hidden_nodes=None
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
            hidden_nodes: 隐藏知识库节点（不显示来源）
        """
        # 1. 构建隐藏知识库上下文（优先级最高）
        hidden_context = None
        if hidden_nodes:
            from utils.knowledge_utils.context_builder import build_hidden_kb_context
            hidden_context = build_hidden_kb_context(hidden_nodes)
        
        # 2. 构建知识库上下文（与知识问答相同的逻辑）
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
                
                block = f"【业务规定 {block_index}】来源: {file_name}\n{full_content}"
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
                block = f"【业务规定 {i + 1}】来源: {file_name}\n{content}"
                context_blocks.append(block)
            knowledge_context = "\n\n".join(context_blocks)

        has_rag = bool(knowledge_context)
        
        # 如果有子问题答案合成，添加到知识库上下文中（使用简洁格式）
        if has_rag and self._last_synthesized_answer:
            synthesis_block = (
                f"\n\n【子问题综合分析】\n"
                f"{self._last_synthesized_answer}\n\n"
                f"注意: 以上是对多个子问题答案的综合整理，请结合具体业务规定给出最终回答。"
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
        if has_rag or hidden_context:
            # 获取前缀
            assistant_prefix = get_knowledge_assistant_context_prefix()

            # 组合上下文：隐藏知识库 + 历史对话 + 业务规定
            context_parts = []
            
            # 1. 隐藏知识库（最优先）
            if hidden_context:
                context_parts.append(hidden_context)
            
            # 2. 历史对话
            if history_context:
                context_parts.append(history_context)
            
            # 3. 业务规定
            if knowledge_context:
                context_parts.append(assistant_prefix + knowledge_context)
            elif hidden_context and not knowledge_context:
                # 只有隐藏知识库，没有普通知识库
                context_parts.append(assistant_prefix + "（已注入内部参考资料）")

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
            user_prompt = user_prompt_str.format(context=assistant_context, question=actual_question)

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
        
        # 2. 根据策略选择检索器（确保通用库始终被检索）
        selected_retriever = None
        if strategy == "airline_visa_free" and self.multi_kb_retriever:
            # 三库检索（航司库 + 免签库 + 通用库）
            logger.info("[智能路由] 策略: airline_visa_free → 三库检索（航司库 + 免签库 + 通用库）")
            selected_retriever = self.multi_kb_retriever
        elif strategy == "visa_free" and self.multi_kb_retriever:
            # 双库检索（免签库 + 通用库）
            logger.info("[智能路由] 策略: visa_free → 双库检索（免签库 + 通用库）")
            selected_retriever = self.multi_kb_retriever
        elif strategy == "airline" and self.multi_kb_retriever:
            # 双库检索（航司库 + 通用库）
            logger.info("[智能路由] 策略: airline → 双库检索（航司库 + 通用库）")
            selected_retriever = self.multi_kb_retriever
        else:
            # 只用通用库（默认）
            logger.info("[智能路由] 策略: general → 仅通用库")
            selected_retriever = self.retriever
            strategy = "general"  # 确保 strategy 为 general
        
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
        
        # 4. 标准检索和重排序（传入 strategy）
        return self._retrieve_and_rerank_with_retriever(
            question, 
            rerank_top_n, 
            selected_retriever,
            strategy=strategy  # 传入策略
        )
    
    def _retrieve_and_rerank_with_retriever(
        self, 
        question: str, 
        rerank_top_n: int,
        retriever,
        strategy: str = "general"
    ):
        """
        使用指定检索器进行检索和重排序（支持 Keyword Table Fallback）
        
        Args:
            question: 用户问题
            rerank_top_n: 重排序后返回的文档数量（仅对general策略生效）
            retriever: 检索器实例
            strategy: 检索策略（airline_visa_free/visa_free/airline/general）
            
        Returns:
            重排序后的节点列表
            
        Note:
            - general策略：使用前端传入的rerank_top_n参数
            - 其他策略：使用固定配置的返回数量，忽略rerank_top_n参数
        """
        # 创建 QueryBundle（重排序需要）
        query_bundle = QueryBundle(query_str=question)
        
        # BM25 + 向量检索融合策略
        retrieved_nodes = []
        retrieval_mode = "bm25_vector_fusion"
        
        from core.multi_kb_retriever import MultiKBRetriever
        
        # 执行 BM25 + 向量混合检索（根据策略选择方法）
        logger.info(f"[融合策略] BM25 + 向量检索 | 策略: {strategy}")
        if isinstance(retriever, MultiKBRetriever):
            # 根据策略调用不同的检索方法
            if strategy == "airline_visa_free":
                # 三库检索
                retrieved_nodes = retriever.retrieve_from_all_three(question)
            elif strategy == "visa_free":
                # 免签库 + 通用库
                retrieved_nodes = retriever.retrieve_from_both(question)
            elif strategy == "airline":
                # 航司库 + 通用库
                retrieved_nodes = retriever.retrieve_airline_only(question)
            else:
                # 默认：根据可用检索器自动选择
                retrieved_nodes = retriever.retrieve(question)
        else:
            retrieved_nodes = retriever.retrieve(query_bundle)
        
        logger.info(f"[BM25+向量检索] 返回 {len(retrieved_nodes)} 个节点")
        
        logger.info(f"检索完成 | 模式: {retrieval_mode} | 结果数: {len(retrieved_nodes)}")
        
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
        
        # 方案1+3组合：按得分排序后严格截断
        # 确保按分数从高到低排序
        reranked_nodes.sort(key=lambda x: x.score, reverse=True)
        
        # 根据策略决定返回数量
        if strategy == "airline_visa_free":
            # 三库检索：固定返回20条
            final_count = Settings.AIRLINE_VISA_FREE_RETURN_COUNT
            logger.info(f"[三库检索] 使用固定返回数量: {final_count}条（不受前端参数控制）")
        elif strategy == "visa_free":
            # 免签库+通用库：固定返回15条
            final_count = Settings.VISA_FREE_STRATEGY_RETURN_COUNT
            logger.info(f"[免签检索] 使用固定返回数量: {final_count}条（不受前端参数控制）")
        elif strategy == "airline":
            # 航司库+通用库：固定返回15条
            final_count = Settings.AIRLINE_STRATEGY_RETURN_COUNT
            logger.info(f"[航司检索] 使用固定返回数量: {final_count}条（不受前端参数控制）")
        else:
            # 通用问题：使用前端参数
            final_count = rerank_top_n
            logger.info(f"[通用检索] 使用前端参数: {final_count}条")
        
        # 截断到目标数量
        final_nodes = reranked_nodes[:final_count]
        
        if final_nodes:
            logger.info(
                f"最终返回 {len(final_nodes)} 个文档（策略: {strategy}, 目标数量: {final_count}） | "
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
