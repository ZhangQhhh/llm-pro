#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
调试脚本：查看指定问题在检索/重排阶段的节点得分。

使用场景：
    当预期片段未进入前端展示的 TopN 时，快速定位它在各阶段的排名与得分。
"""
import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import create_app  # noqa: E402
from utils import logger  # noqa: E402


def _render_stage(stage_name: str, entries, lines: list[str]):
    if not entries:
        lines.append(f"[{stage_name}] 无结果")
        return

    lines.append(f"\n[{stage_name}] 共 {len(entries)} 条（已按得分排序）")
    for entry in entries:
        vector_score = entry.get("vector_score", 0.0)
        bm25_score = entry.get("bm25_score", 0.0)
        file_name = entry.get("file_name") or "-"
        source_label = entry.get("source_label", "unknown")
        vec_rank = entry.get("vector_rank")
        bm_rank = entry.get("bm25_rank")
        rank_labels = []
        if vec_rank is not None:
            rank_labels.append(f"vec#{vec_rank}")
        if bm_rank is not None:
            rank_labels.append(f"bm25#{bm_rank}")
        rank_info = ",".join(rank_labels) if rank_labels else "-"

        lines.append(
            f"  #{entry['rank']:02d} score={entry['score']:.4f} "
            f"vector={vector_score:.4f} bm25={bm25_score:.4f} "
            f"src={source_label} ranks={rank_info} "
            f"id={entry['node_id']} file={file_name}"
        )
        lines.append(f"     preview: {entry.get('text_preview', '')}")


def main():
    parser = argparse.ArgumentParser(
        description="调试检索/重排节点得分，定位遗漏的片段"
    )
    parser.add_argument("--question", required=True, help="需要诊断的问题文本")
    parser.add_argument("--substring", help="匹配正文/文件名中的子串")
    parser.add_argument("--node-id", help="按 node_id 过滤")
    parser.add_argument("--limit", type=int, default=50, help="每个阶段最多展示多少条")
    parser.add_argument(
        "--include-text",
        action="store_true",
        help="打印完整文本（默认只显示预览）"
    )
    parser.add_argument(
        "--skip-rerank",
        action="store_true",
        help="仅查看检索阶段结果，不执行重排"
    )

    args = parser.parse_args()

    logger.info("初始化应用以加载 KnowledgeHandler ...")
    app = create_app()
    if app is None or not hasattr(app, "knowledge_handler"):
        raise RuntimeError("无法初始化应用或未找到 KnowledgeHandler")

    handler = app.knowledge_handler
    debug_result = handler.debug_inspect_scores(
        question=args.question,
        match_substring=args.substring,
        match_node_id=args.node_id,
        max_candidates=args.limit,
        include_full_text=args.include_text,
        run_reranker=not args.skip_rerank
    )

    output_lines: list[str] = []
    output_lines.append("=" * 80)
    output_lines.append(f"Question: {debug_result['question']}")
    output_lines.append(f"Retriever: {debug_result['retriever_type']}")
    output_lines.append("=" * 80)

    _render_stage("Retrieval", debug_result["retrieval"], output_lines)
    _render_stage("Rerank", debug_result["rerank"], output_lines)

    matches = debug_result.get("matches") or []
    conditions = debug_result.get("match_conditions", {})
    if conditions.get("substring") or conditions.get("node_id"):
        output_lines.append("\n[MATCHES] 命中结果：")
        if not matches:
            output_lines.append("  未找到匹配节点，请尝试放宽匹配条件。")
        else:
            for entry in matches:
                stage = entry.get("stage", "?")
                source_label = entry.get("source_label", "unknown")
                vec_rank = entry.get("vector_rank")
                bm_rank = entry.get("bm25_rank")
                rank_labels = []
                if vec_rank is not None:
                    rank_labels.append(f"vec#{vec_rank}")
                if bm_rank is not None:
                    rank_labels.append(f"bm25#{bm_rank}")
                rank_info = ",".join(rank_labels) if rank_labels else "-"
                output_lines.append(
                    f"  [{stage}] #{entry['rank']:02d} score={entry['score']:.4f} "
                    f"src={source_label} ranks={rank_info} "
                    f"id={entry['node_id']} file={entry.get('file_name')}"
                )
                if args.include_text and entry.get("text"):
                    output_lines.append(f"     text: {entry['text']}")
                else:
                    output_lines.append(f"     preview: {entry.get('text_preview', '')}")

    log_path = os.path.join(os.path.dirname(__file__), "log.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"结果已写入 {log_path}")


if __name__ == "__main__":
    main()
