# -*- coding: utf-8 -*-
"""
WriterHandler
- 写作端“独立重排参数”：WRITER_RERANK_TOP_N
- 在调用 reranker 前临时设置 top_n = clamp(1..len(results))，用后恢复
- 统一对空结果/异常返回前端可见的 ERROR:...
- 新增：process_stream 增参 use_kb（默认 True 以保持原行为）
- 新增：process_stream 增参 kb_selected（可选 list[str]，仅在 use_kb=True 时筛选 KB 文档）
"""

import json
from typing import Generator, Tuple, List, Dict, Any, Optional

from config import Settings
from utils import logger, clean_for_sse_text
from core.llm_wrapper import LLMStreamWrapper
from services.writer_service import writer_service
from llama_index.core.schema import NodeWithScore

# 统一从 prompts 读取
from prompts import get_prompt


class WriterHandler:
    def __init__(self, reranker):
        self.llm_wrapper = LLMStreamWrapper()
        self.reranker = reranker

    def _build_prompts(
        self,
        user_instruction: str,
        context_snippets: List[Tuple[int, str, Dict[str, Any]]],
        recent_history_text: Optional[str] = None
    ) -> Dict[str, str]:
        # 先把所有片段转成 [编号] 文本，随后再按“有效 top_n”截断
        all_refs = []
        for idx, snippet, meta in context_snippets:
            src = meta.get("filename") or meta.get("path") or "参考资料"
            all_refs.append(f"[{idx}]（{src}）{snippet}")

        req_top_n = int(getattr(Settings, "WRITER_RERANK_TOP_N",
                                getattr(Settings, "RERANK_TOP_N", 15)))
        n_ctx = max(0, len(context_snippets))
        effective_top_n = n_ctx if req_top_n <= 0 else min(req_top_n, n_ctx)
        context_block = "\n".join(all_refs[:effective_top_n]) if n_ctx > 0 else ""

        system_prompt = get_prompt(
            "writer.system",
            default=(
                "你是一个中文写作智能体。请根据【用户意图】并结合【参考资料】进行写作，要求：\n"
                "1) 先明确目标与受众；2) 结构清晰（含小标题）；3) 观点有据可循；\n"
                "4) 语言自然流畅、专业准确；5) 对来自参考资料的事实点，按出现位置以 [来源#编号] 注释；\n"
                "6) 最后给出“参考资料”清单（按 [编号] 文件名 排列）。"
            )
        )

        assistant_context = ""
        if recent_history_text:
            prefix = get_prompt(
                "writer.assistant_context_prefix",
                default="以下是与用户本次写作相关的最近对话（用于保持上下文与风格一致）：\n"
            )
            assistant_context = prefix + recent_history_text

        user_tmpl = get_prompt(
            "writer.user",
            default=(
                "【用户意图】\n{instruction}\n\n"
                "【参考资料】（已按相关性排序，编号从1开始）\n{context_block}\n\n"
                "请严格基于以上资料写作；如资料不足以支持某些断言，请明确假设并尽量保持客观。"
            )
        )
        user_prompt = user_tmpl.format(
            instruction=user_instruction,
            context_block=context_block
        )

        fallback_prompt = (
            f"{system_prompt}\n\n{assistant_context}\n\n"
            f"用户：{user_instruction}\n\n参考资料：\n{context_block}\n\n请开始写作。"
        )

        logger.info(f"[WriterDBG] build_prompts: ctx_total={n_ctx}, effective_top_n={effective_top_n}")
        return dict(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            assistant_context=assistant_context,
            fallback_prompt=fallback_prompt
        )

    def process_stream(
        self,
        llm,
        session_id: str,
        instruction: str,
        conversation_manager,
        enable_thinking: bool = False,
        use_kb: bool = True,                 # 是否合并额外知识库
        kb_selected: Optional[List[str]] = None  # 仅使用被选中的 KB 文件（basename 列表）
    ) -> Generator[str, None, None]:
        try:
            # 1) 检索
            results: List[NodeWithScore] = writer_service.retrieve(
                session_id=session_id,
                query=instruction,
                use_kb=use_kb,
                kb_selected=kb_selected,   # ← 新增开关：筛选 KB 文档
            )
            logger.info(f"[WriterDBG] retrieve: total_results={len(results)}")
            if not results:
                yield "ERROR:未检索到候选片段，请先上传资料或更换指令。"
                return

            # 2) Rerank（安全裁剪到 1..len(results)）
            reranked = results
            if self.reranker:
                req_top_n = int(getattr(Settings, "WRITER_RERANK_TOP_N",
                                        getattr(Settings, "RERANK_TOP_N", 15)))
                effective_top_n = max(1, min(req_top_n if req_top_n > 0 else len(results), len(results)))
                orig_top_n = getattr(self.reranker, "top_n", None)
                try:
                    setattr(self.reranker, "top_n", effective_top_n)
                except Exception:
                    pass
                try:
                    reranked = self.reranker.postprocess_nodes(results, query_str=instruction)
                finally:
                    try:
                        if orig_top_n is not None:
                            setattr(self.reranker, "top_n", orig_top_n)
                    except Exception:
                        pass
                logger.info(f"[WriterDBG] rerank: req_top_n={req_top_n}, effective_top_n={effective_top_n}, after_rerank={len(reranked)}")
            else:
                logger.info("[WriterDBG] rerank: disabled")

            if not reranked:
                yield "ERROR:重排后无有效结果，请尝试扩大检索范围或更换资料。"
                return

            # 3) 取片段
            def _clip(txt: str, n: int = 260) -> str:
                txt = (txt or "").replace("\n", " ").strip()
                return txt[:n] + ("…" if len(txt) > n else "")

            req_top_n = int(getattr(Settings, "WRITER_RERANK_TOP_N",
                                    getattr(Settings, "RERANK_TOP_N", 15)))
            take_n = min(req_top_n if req_top_n > 0 else len(reranked), len(reranked))
            context_snippets: List[Tuple[int, str, Dict[str, Any]]] = []
            for i, n in enumerate(reranked[:max(1, take_n)], start=1):
                meta = n.node.metadata or {}
                context_snippets.append((i, _clip(n.node.get_content()), meta))
            sample = []
            for i, _, m in context_snippets[:3]:
                fn = (m.get("filename") or (m.get("path") or "").split("/")[-1] or "")
                sample.append(f"{i}:{fn}#chunk{m.get('chunk_id','?')}")
            logger.info(f"[WriterDBG] ctx_snippets: count={len(context_snippets)}, peek=" + (", ".join(sample) if sample else "(empty)"))

            # 4) 最近对话（忽略失败）
            recent_history_text = ""
            try:
                recent = conversation_manager.get_recent_history(session_id=session_id, limit=4) or []
                for t in recent:
                    recent_history_text += f"用户：{t.get('user_query','')}\n助手：{t.get('assistant_response','')}\n---\n"
            except Exception:
                pass

            # 5) 组 Prompt 并流式生成
            prompts = self._build_prompts(instruction, context_snippets, recent_history_text)

            # 先发来源映射
            source_map = [{"id": idx,
                           "fileName": m.get("filename", "") or (m.get("path") or "").split("/")[-1],
                           "path": m.get("path", "")}
                          for idx, _, m in context_snippets]
            logger.info(f"[WriterDBG] SOURCE emit: count={len(source_map)}")
            yield "SOURCE:" + json.dumps(source_map, ensure_ascii=False)

            response_stream = self.llm_wrapper.stream(
                llm,
                prompt=prompts['fallback_prompt'],
                system_prompt=prompts['system_prompt'],
                user_prompt=prompts['user_prompt'],
                assistant_context=prompts['assistant_context'],
                use_chat_mode=getattr(Settings, "USE_CHAT_MODE", True),
                enable_thinking=enable_thinking
            )

            # 6) 正文流
            full_text = ""
            for delta in response_stream:
                if hasattr(delta, "delta"):
                    text = delta.delta
                elif hasattr(delta, "text"):
                    text = delta.text
                elif hasattr(delta, "content"):
                    text = delta.content
                else:
                    text = str(delta) if delta else ""
                text = text or ""
                if text:
                    full_text += text
                    yield "CONTENT:" + clean_for_sse_text(text)

            # 7) 记一份会话（忽略失败）
            try:
                import uuid
                conversation_manager.add_conversation_turn(
                    session_id=session_id,
                    user_query=instruction,
                    assistant_response=full_text,
                    context_docs=[it["fileName"] for it in source_map],
                    turn_id=str(uuid.uuid4()),
                    parent_turn_id=None
                )
            except Exception:
                pass

        except Exception as e:
            yield f"ERROR:{clean_for_sse_text(str(e))}"
