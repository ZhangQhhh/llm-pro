# -*- coding: utf-8 -*-
import os
from flask import Blueprint, request, jsonify, send_file, current_app
from utils import logger
from services.mcq_service import bank_get_sources as _svc_get_sources
from services.mcq_service import (
    mcq_upload_parse,
    mcq_explain_sync,
    bank_list,
    bank_bulk_upsert,
    bank_bulk_update,
    bank_bulk_reject,
    bank_export_docx,
    bank_import_docx,
    bank_generate_paper,
    bank_list_papers,
    bank_get_paper_docx,
    bank_get_paper_zip,
    # === 新增：异步最小接口 ===
    create_async_explain_task,
    get_task_status,
)


mcq_public_bp = Blueprint("mcq_public", __name__)

@mcq_public_bp.route("/upload", methods=["POST"])
def mcq_upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "msg": "缺少文件参数 file"}), 400
    try:
        return jsonify(mcq_upload_parse(f))
    except Exception as e:
        logger.error(f"[MCQ] 批量上传解析失败: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500

@mcq_public_bp.route("/explain", methods=["POST"])
def mcq_explain():
    data = request.get_json() or {}
    return jsonify(mcq_explain_sync(data))

# === 新增：创建异步任务（最小版） ===
@mcq_public_bp.route("/explain_batch_async", methods=["POST"])
def mcq_explain_batch_async():
    data = request.get_json() or {}
    try:
        return jsonify(create_async_explain_task(data))
    except Exception as e:
        logger.error(f"[MCQ] 创建异步任务失败: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500

# === 新增：查询任务状态（仅状态/进度） ===
@mcq_public_bp.route("/tasks/status", methods=["GET"])
def mcq_task_status():
    task_id = (request.args.get("task_id") or "").strip()
    if not task_id:
        return jsonify({"ok": False, "msg": "缺少参数 task_id"}), 400
    return jsonify(get_task_status(task_id))

@mcq_public_bp.route("/bank/list", methods=["GET"])
def bank_list_api():
    return jsonify(bank_list())

@mcq_public_bp.route("/bank/bulk_upsert", methods=["POST"])
def bank_bulk_upsert_api():
    data = request.get_json() or {}
    return jsonify(bank_bulk_upsert(data))

@mcq_public_bp.route("/bank/bulk_update", methods=["POST"])
def bank_bulk_update_api():
    data = request.get_json() or {}
    return jsonify(bank_bulk_update(data))

@mcq_public_bp.route("/bank/bulk_reject", methods=["POST"])
def bank_bulk_reject_api():
    data = request.get_json() or {}
    return jsonify(bank_bulk_reject(data))

@mcq_public_bp.route("/bank/export_docx", methods=["GET"])
def bank_export_docx_api():
    try:
        path, filename = bank_export_docx()
        return send_file(
            path,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

@mcq_public_bp.route("/bank/import_docx", methods=["POST"])
def bank_import_docx_api():
    f = request.files.get("file")
    if not f:
        return jsonify({"ok": False, "msg": "缺少文件参数 file"}), 400
    try:
        return jsonify(bank_import_docx(f))
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

@mcq_public_bp.route("/bank/generate_paper", methods=["POST"])
def bank_generate_paper_api():
    data = request.get_json() or {}
    try:
        path, filename = bank_generate_paper(data.get("name") or "试卷")
        if path is None:
            return jsonify({"ok": True, "msg": "无可用题目（仅包含已通过）"})
        return send_file(
            path,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

@mcq_public_bp.route("/bank/papers", methods=["GET"])
def bank_list_papers_api():
    """列出已通过题库生成的试卷文件（./data/papers 下的 DOCX）。"""
    try:
        return jsonify(bank_list_papers())
    except Exception as e:
        logger.error(f"[MCQ] 列出试卷失败: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@mcq_public_bp.route("/bank/paper_docx", methods=["GET"])
def bank_paper_docx_api():
    """下载单个试卷的 DOCX 文件。"""
    paper_id = (request.args.get("paper_id") or "").strip()
    if not paper_id:
        return jsonify({"ok": False, "msg": "缺少参数 paper_id"}), 400
    path, filename = bank_get_paper_docx(paper_id)
    if not path:
        return jsonify({"ok": False, "msg": "试卷不存在"}), 404
    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@mcq_public_bp.route("/bank/paper_zip", methods=["GET"])
def bank_paper_zip_api():
    """将单个试卷打包为 ZIP 并下载。"""
    paper_id = (request.args.get("paper_id") or "").strip()
    if not paper_id:
        return jsonify({"ok": False, "msg": "缺少参数 paper_id"}), 400
    path, filename = bank_get_paper_zip(paper_id)
    if not path:
        return jsonify({"ok": False, "msg": "试卷不存在或打包失败"}), 404
    return send_file(
        path,
        as_attachment=True,
        download_name=filename,
        mimetype="application/zip",
    )



# 完整参考资料按需获取（全量不截断）
@mcq_public_bp.route("/bank/sources")
def bank_get_sources():
    from flask import request, jsonify
    qid = (request.args.get("qid") or "").strip()
    return jsonify(_svc_get_sources(qid))

@mcq_public_bp.route("/import_template", methods=["GET"])
def download_import_template():
    """
    题库导入模板下载：后端强制指定文件名为“题库导入模板.docx”
    """
    try:
        # Flask app 里 static_folder 已经在 app.py 里配置好了
        static_dir = current_app.static_folder
        path = os.path.join(static_dir, "import_template.docx")

        if not os.path.exists(path):
            return jsonify({"ok": False, "msg": "模板文件不存在"}), 404

        return send_file(
            path,
            as_attachment=True,
            download_name="题库导入模板.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        logger.error(f"[MCQ] 下载模板失败: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500
