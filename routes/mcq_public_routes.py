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
    bank_delete_questions,
    bank_list_deleted,
    bank_restore_questions,
    bank_clear_deleted,
    bank_get_deletion_logs,
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
from middleware.role_required import require_admin_or_super, get_current_user

# === 新增：考试服务 ===
from services.exam_service import (
    papers_list_open,
    papers_view,
    exam_start,
    exam_submit,
    exam_review,
    student_export_report_docx,
    export_paper_reports_zip,
    export_paper_summary_docx,
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

@mcq_public_bp.route("/bank/delete", methods=["POST"])
@require_admin_or_super
def bank_delete_api():
    """删除题目（软删除，移到回收站）- 需要管理员权限"""
    data = request.get_json() or {}
    user_info = get_current_user()
    data["user"] = user_info["username"]
    return jsonify(bank_delete_questions(data))

@mcq_public_bp.route("/bank/deleted", methods=["GET"])
@require_admin_or_super
def bank_list_deleted_api():
    """列出回收站中的题目 - 需要管理员权限"""
    return jsonify(bank_list_deleted())

@mcq_public_bp.route("/bank/restore", methods=["POST"])
@require_admin_or_super
def bank_restore_api():
    """从回收站恢复题目 - 需要管理员权限"""
    data = request.get_json() or {}
    user_info = get_current_user()
    data["user"] = user_info["username"]
    return jsonify(bank_restore_questions(data))

@mcq_public_bp.route("/bank/clear_deleted", methods=["POST"])
@require_admin_or_super
def bank_clear_deleted_api():
    """清空回收站 - 需要管理员权限"""
    data = request.get_json() or {}
    user_info = get_current_user()
    data["user"] = user_info["username"]
    return jsonify(bank_clear_deleted(data))

@mcq_public_bp.route("/bank/deletion_logs", methods=["GET"])
@require_admin_or_super
def bank_deletion_logs_api():
    """获取删除日志 - 需要管理员权限"""
    limit = request.args.get("limit", 100, type=int)
    return jsonify(bank_get_deletion_logs(limit))

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


# ===================== 考试相关路由 =====================

@mcq_public_bp.route("/papers/list_open", methods=["GET"])
def papers_list_open_api():
    """列出可用的试卷（学生端）"""
    try:
        papers = papers_list_open()
        response = jsonify(papers)
        response.headers['Content-Type'] = 'application/json; charset=utf-8'
        return response
    except Exception as e:
        logger.error(f"[Exam] 列出试卷失败: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@mcq_public_bp.route("/papers/view", methods=["GET"])
def papers_view_api():
    """查看试卷详情（题目列表，不含答案）"""
    paper_id = (request.args.get("paper_id") or "").strip()
    if not paper_id:
        return jsonify({"ok": False, "detail": "缺少参数 paper_id"}), 400
    
    try:
        result = papers_view(paper_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"[Exam] 查看试卷失败: {e}", exc_info=True)
        return jsonify({"ok": False, "detail": str(e)}), 500


@mcq_public_bp.route("/exam/start", methods=["POST"])
def exam_start_api():
    """开始考试，创建考试会话"""
    data = request.get_json() or {}
    paper_id = data.get("paper_id")
    duration_sec = data.get("duration_sec", 1800)  # 默认30分钟
    student_id = data.get("student_id", "anonymous")
    
    if not paper_id:
        return jsonify({"ok": False, "detail": "缺少参数 paper_id"}), 400
    
    try:
        result = exam_start(paper_id, duration_sec, student_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"[Exam] 开始考试失败: {e}", exc_info=True)
        return jsonify({"ok": False, "detail": str(e)}), 500


@mcq_public_bp.route("/exam/submit", methods=["POST"])
def exam_submit_api():
    """提交答案并评分"""
    data = request.get_json() or {}
    attempt_id = data.get("attempt_id")
    answers = data.get("answers", [])
    
    if not attempt_id:
        return jsonify({"ok": False, "detail": "缺少参数 attempt_id"}), 400
    
    try:
        result = exam_submit(attempt_id, answers)
        return jsonify(result)
    except Exception as e:
        logger.error(f"[Exam] 提交答案失败: {e}", exc_info=True)
        return jsonify({"ok": False, "detail": str(e)}), 500


@mcq_public_bp.route("/exam/review", methods=["GET"])
def exam_review_api():
    """查看答案解析"""
    attempt_id = (request.args.get("attempt_id") or "").strip()
    if not attempt_id:
        return jsonify({"ok": False, "detail": "缺少参数 attempt_id"}), 400
    
    try:
        result = exam_review(attempt_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"[Exam] 查看解析失败: {e}", exc_info=True)
        return jsonify({"ok": False, "detail": str(e)}), 500


@mcq_public_bp.route("/student/export_my_report_docx", methods=["POST"])
def student_export_report_api():
    """导出学生成绩报告（DOCX）"""
    # 支持 JSON 和 FormData 两种方式
    if request.is_json:
        data = request.get_json() or {}
        attempt_id = data.get("attempt_id")
    else:
        attempt_id = request.form.get("attempt_id")
    
    if not attempt_id:
        return jsonify({"ok": False, "detail": "缺少参数 attempt_id"}), 400
    
    try:
        result = student_export_report_docx(attempt_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"[Exam] 导出报告失败: {e}", exc_info=True)
        return jsonify({"ok": False, "detail": str(e)}), 500


@mcq_public_bp.route("/student/download_report", methods=["GET"])
def student_download_report():
    """下载成绩报告文件"""
    filename = (request.args.get("filename") or "").strip()
    if not filename:
        return jsonify({"ok": False, "msg": "缺少参数 filename"}), 400
    
    filepath = os.path.join("./data/reports", filename)
    if not os.path.exists(filepath):
        return jsonify({"ok": False, "msg": "文件不存在"}), 404
    
    try:
        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        logger.error(f"[Exam] 下载报告失败: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


# ===================== 成绩导出相关路由 =====================

@mcq_public_bp.route("/grades/export_zip", methods=["GET"])
def export_grades_zip():
    """
    导出指定试卷所有考生的成绩报告（ZIP压缩包）
    每个考生一个DOCX文件
    """
    paper_id = (request.args.get("paper_id") or "").strip()
    if not paper_id:
        return jsonify({"ok": False, "msg": "缺少参数 paper_id"}), 400
    
    try:
        zip_path, zip_filename = export_paper_reports_zip(paper_id)
        
        if not zip_path:
            return jsonify({"ok": False, "msg": "该试卷暂无已完成的考试记录"}), 404
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name=zip_filename,
            mimetype="application/zip",
        )
    except Exception as e:
        logger.error(f"[Exam] 导出成绩ZIP失败: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500


@mcq_public_bp.route("/grades/export_summary_docx", methods=["GET"])
def export_grades_summary():
    """
    导出指定试卷所有考生的成绩汇总表（DOCX）
    包含每名考生的答题情况和总得分
    """
    paper_id = (request.args.get("paper_id") or "").strip()
    if not paper_id:
        return jsonify({"ok": False, "msg": "缺少参数 paper_id"}), 400
    
    try:
        docx_path, docx_filename = export_paper_summary_docx(paper_id)
        
        if not docx_path:
            return jsonify({"ok": False, "msg": "该试卷暂无已完成的考试记录"}), 404
        
        return send_file(
            docx_path,
            as_attachment=True,
            download_name=docx_filename,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    except Exception as e:
        logger.error(f"[Exam] 导出成绩汇总失败: {e}", exc_info=True)
        return jsonify({"ok": False, "msg": str(e)}), 500
