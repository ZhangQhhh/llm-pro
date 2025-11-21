# -*- coding: utf-8 -*-
import os
import re
from typing import List, Iterable, Tuple, Any, Optional
from flask import Blueprint, request, jsonify, Response, stream_with_context, current_app

from utils import logger, format_sse_text, generate_session_id
from services.writer_service import writer_service
from api.writer_handler import WriterHandler
from config import Settings

writer_bp = Blueprint('writer', __name__)

# ================== 目录/常量 ==================
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
UPLOAD_ROOT = os.path.join(BASE_DIR, "data", "writer_uploads")
KB_UPLOAD_ROOT = os.path.join(BASE_DIR, "data", "writer_kb")
os.makedirs(UPLOAD_ROOT, exist_ok=True)
os.makedirs(KB_UPLOAD_ROOT, exist_ok=True)

ALLOWED_EXT = {".txt", ".md", ".pdf", ".docx", ".doc"}
MAX_FILES = 10  # 会话上传上限：10
MAX_SIZE_MB = 20

# ============ Settings/环境变量 ============
QDRANT_HOST = getattr(Settings, "QDRANT_HOST", "localhost")
QDRANT_PORT = int(getattr(Settings, "QDRANT_PORT", 6333))

# —— 会话知识库统一到单集合 —— #
WRITER_SESSION_COLLECTION = getattr(
    Settings, "WRITER_SESSION_COLLECTION",
    f"{getattr(Settings, 'QDRANT_COLLECTION', 'kb')}_writer_session"
)

# 额外知识库集合（持久化）
WRITER_KB_COLLECTION = getattr(
    Settings, "WRITER_KB_COLLECTION",
    f"{getattr(Settings, 'QDRANT_COLLECTION', 'kb')}_writer"
)

# 额外知识库上传口令
WRITER_KB_UPLOAD_PASSWORD = getattr(
    Settings, "WRITER_KB_UPLOAD_PASSWORD",
    os.environ.get("WRITER_KB_UPLOAD_PASSWORD", None)
)

# ---------- 文件名：保留中文 ----------
_CJK_SAFE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff\.\-_]")

def safe_cjk_filename(name: str) -> str:
    base = os.path.basename(name).strip()
    base = base.replace(" ", "_")
    base = _CJK_SAFE.sub("_", base)
    return base or "file"

def _save_files(target_dir: str, files, *, max_files: int = None, overwrite: bool = True) -> List[str]:
    """保存上传文件（同名覆盖、中文文件名、安全大小限制）"""
    saved, total = [], 0
    for f in files:
        orig_name = f.filename or ""
        ext = os.path.splitext(orig_name)[1].lower()
        if not orig_name or ext not in ALLOWED_EXT:
            continue
        f.seek(0, os.SEEK_END); size = f.tell(); f.seek(0)
        total += size
        if total > MAX_SIZE_MB * 1024 * 1024:
            break
        fname = safe_cjk_filename(orig_name)
        path = os.path.join(target_dir, fname)
        if overwrite and os.path.exists(path):
            try: os.remove(path)
            except Exception: pass
        with open(path, "wb") as out:
            out.write(f.read())
        saved.append(path)
        if max_files and len(saved) >= max_files:
            break
    return saved

# ================== 兼容调用包装（适配不同服务签名） ==================
def _try_call(func, patterns: List[Tuple[tuple, dict]]) -> Any:
    last_err = None
    for args, kwargs in patterns:
        try:
            return func(*args, **kwargs)
        except TypeError as e:
            last_err = e  # 签名不匹配则尝试下一个
        except Exception:
            raise  # 真实运行错误直接抛出
    if last_err:
        raise last_err
    raise RuntimeError("调用失败：无可用调用模式")

# ================== KB 工具（统一 basename） ==================
def _kb_disk_all_paths() -> List[str]:
    if not os.path.isdir(KB_UPLOAD_ROOT):
        return []
    return [
        os.path.join(KB_UPLOAD_ROOT, f)
        for f in os.listdir(KB_UPLOAD_ROOT)
        if os.path.isfile(os.path.join(KB_UPLOAD_ROOT, f))
    ]

def _to_basenames(items: List[Any]) -> List[str]:
    names = []
    for it in items or []:
        if isinstance(it, str):
            names.append(os.path.basename(it))
        elif isinstance(it, dict):
            for k in ("filename", "name", "file_name", "path", "file_path"):
                if k in it and it[k]:
                    names.append(os.path.basename(str(it[k])))
                    break
    seen, out = set(), []
    for n in sorted(names):
        if n not in seen:
            seen.add(n); out.append(n)
    return out

def _kb_list_basenames_via_service_or_disk() -> List[str]:
    try:
        files = writer_service.list_kb_files()
        return _to_basenames(files)
    except Exception:
        return _to_basenames(_kb_disk_all_paths())

def _kb_resolve_candidates(filename: str) -> List[str]:
    filename = os.path.basename(filename)
    cands = [os.path.join(KB_UPLOAD_ROOT, filename)]
    try:
        svc_list = writer_service.list_kb_files()
        for it in svc_list:
            if isinstance(it, str) and os.path.basename(it) == filename:
                cands.append(it)
        for it in svc_list:
            if isinstance(it, dict):
                for k in ("path", "file_path", "filename", "name", "file_name"):
                    if k in it and it[k] and os.path.basename(str(it[k])) == filename:
                        cands.append(str(it[k]))
                        break
    except Exception:
        pass
    uniq, seen = [], set()
    for p in cands:
        if p and p not in seen:
            seen.add(p); uniq.append(p)
    return uniq

# ================== 项目内“向量删除”封装优先 ==================
def _try_project_vector_delete(collection: str, filename_or_path: str, session_id: Optional[str] = None) -> Optional[bool]:
    """
    优先调用工程内封装：
    - writer_service.delete_vectors_by_session_and_filename(collection, session_id, name)
    - writer_service.delete_vectors_by_filename(collection, name)
    - current_app.vector_store.* / current_app.qdrant_client.*
    成功 True；完全不可用 None。
    """
    # 1) 带 session 的方法（单集合推荐）
    fn = getattr(writer_service, "delete_vectors_by_session_and_filename", None)
    if callable(fn):
        try:
            ret = fn(collection, session_id, filename_or_path)
            if isinstance(ret, bool): return ret
            if isinstance(ret, int): return ret > 0
            return True
        except Exception as e:
            logger.warning(f"[Writer] writer_service.delete_vectors_by_session_and_filename 失败: {e}")

    # 2) 仅文件名的删除（老实现）
    for attr in ("delete_vectors_by_filename", "remove_kb_vectors", "remove_vectors_by_source", "delete_document_vectors"):
        fn = getattr(writer_service, attr, None)
        if callable(fn):
            try:
                ret = fn(collection, filename_or_path)
                if isinstance(ret, bool): return ret
                if isinstance(ret, int): return ret > 0
                return True
            except Exception as e:
                logger.warning(f"[Writer] writer_service.{attr} 调用失败: {e}")

    # 3) current_app.vector_store
    vs = getattr(current_app, "vector_store", None)
    if vs:
        for method in ("delete_by_filter", "delete_by_metadata", "delete"):
            fn = getattr(vs, method, None)
            if callable(fn):
                try:
                    cond = {}
                    if session_id:
                        cond = {"$and":[{"session_id": str(session_id)}]}
                    for key in ["file_name", "filename", "file", "source", "path", "doc_path", "doc_name"]:
                        where = dict(cond)
                        if "$and" in where:
                            where["$and"] = where["$and"] + [{key: filename_or_path}]
                        else:
                            where = {key: filename_or_path}
                        ret = fn(collection_name=collection, where=where)
                        if isinstance(ret, bool): return ret
                        if isinstance(ret, int): return ret > 0
                        return True
                except Exception as e:
                    logger.warning(f"[Writer] vector_store.{method} 调用失败: {e}")

    # 4) current_app.qdrant_client 兜底
    qc = getattr(current_app, "qdrant_client", None)
    if qc:
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            keys = ["file_name", "filename", "file", "source", "path", "doc_path", "doc_name"]
            values = [filename_or_path, os.path.basename(filename_or_path)]
            for key in keys:
                must = []
                if session_id:
                    must.append(FieldCondition(key="session_id", match=MatchValue(value=str(session_id))))
                for val in values:
                    flt = Filter(must=must + [FieldCondition(key=key, match=MatchValue(value=str(val)))])
                    cnt = qc.count(collection, flt, exact=True)
                    if getattr(cnt, "count", 0) > 0:
                        qc.delete(collection, points_selector=flt)
                        return True
        except Exception as e:
            logger.warning(f"[Writer] qdrant_client 删除失败: {e}")

    return None

# ================== 直连 Qdrant 兜底 ==================
def _qdrant_delete_by_filename(collection: str, filename_or_path: str, session_id: Optional[str] = None) -> Optional[bool]:
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        keys = ["file_name", "filename", "file", "source", "path", "doc_path", "doc_name"]
        values = [filename_or_path, os.path.basename(filename_or_path)]
        deleted_any = False
        for key in keys:
            must = []
            if session_id:
                must.append(FieldCondition(key="session_id", match=MatchValue(value=str(session_id))))
            for val in values:
                flt = Filter(must=must + [FieldCondition(key=key, match=MatchValue(value=str(val)))])
                try:
                    cnt = client.count(collection, flt, exact=True)
                    if getattr(cnt, "count", 0) > 0:
                        client.delete(collection, points_selector=flt)
                        deleted_any = True
                except Exception as e:
                    logger.debug(f"[Writer] Qdrant 尝试删除失败 key={key} val={val}: {e}")
        return deleted_any
    except Exception as e:
        logger.warning(f"[Writer] Qdrant 兜底删除异常: {e}")
        return None

def _delete_vectors_for_candidates(collection: str, candidates: List[str], session_id: Optional[str] = None) -> bool:
    for cand in candidates:
        ok = _try_project_vector_delete(collection, cand, session_id=session_id)
        if ok:
            return True
        if ok is None:
            ok2 = _qdrant_delete_by_filename(collection, cand, session_id=session_id)
            if ok2:
                return True
    return False

# ================== 会话 ==================
@writer_bp.route("/writer/session/new", methods=["POST"])
def create_session():
    session_id = generate_session_id(user_id="guest")
    return jsonify({"session_id": session_id})

@writer_bp.route("/writer/upload", methods=["POST"])
def upload_files():
    """会话临时知识库上传（≤10），一律写入单集合 WRITER_SESSION_COLLECTION"""
    try:
        session_id = request.form.get("session_id", "").strip()
        if not session_id:
            return jsonify({"ok": False, "error": "缺少 session_id"}), 400

        files = request.files.getlist("files")
        if not files:
            return jsonify({"ok": False, "error": "未选择文件"}), 400

        session_dir = os.path.join(UPLOAD_ROOT, session_id)
        os.makedirs(session_dir, exist_ok=True)
        saved_paths = _save_files(session_dir, files, max_files=MAX_FILES, overwrite=True)
        if not saved_paths:
            return jsonify({"ok": False, "error": "文件类型不支持或超出限制"}), 400

        added, names = _try_call(
            writer_service.attach_files,
            [
                ((session_id, saved_paths), {"target_collection": WRITER_SESSION_COLLECTION, "ingest_metadata": {"session_id": str(session_id)}}),
                ((saved_paths,), {"target_collection": WRITER_SESSION_COLLECTION, "ingest_metadata": {"session_id": str(session_id)}}),
                # 兼容老签名
                ((session_id, saved_paths), {}),
                ((saved_paths,), {}),
            ]
        )
        return jsonify({"ok": True, "added": added, "files": names, "allFiles": writer_service.list_files(session_id)})
    except Exception as e:
        logger.error(f"上传失败: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

@writer_bp.route("/writer/upload/delete", methods=["POST"])
def delete_file():
    """删除会话文档：本地删除 + 单集合向量删除（按 session_id + filename）"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        session_id = (data.get("session_id") or "").strip()
        filename = (data.get("filename") or "").strip()
        if not session_id or not filename:
            return jsonify({"ok": False, "error": "缺少 session_id 或 filename"}), 400

        # 1) 服务层解绑（本地与索引）
        removed = _try_call(
            writer_service.detach_file,
            [
                ((session_id, filename), {}),
                ((filename,), {}),
            ]
        )

        # 2) 向量库删除（单集合 + 会话过滤兜底）
        cand = [filename, os.path.join(UPLOAD_ROOT, session_id, os.path.basename(filename))]
        vec_removed = _delete_vectors_for_candidates(WRITER_SESSION_COLLECTION, cand, session_id=session_id)

        if not removed and not vec_removed:
            return jsonify({"ok": False, "error": "未找到指定文件"}), 404

        return jsonify({"ok": True, "allFiles": writer_service.list_files(session_id)})
    except Exception as e:
        logger.error(f"删除失败: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

# ================== 模板识别（只弹窗编辑，不写入输入框/不缓存后端） ==================
import re as _re
HEADING_RE = _re.compile(r"^(#{1,6}\s+.+|第[一二三四五六七八九十百千]+[章节部分篇]\s*.+|\d+[\.)、]\s+.+)$", _re.M)

@writer_bp.route("/writer/template/recognize", methods=["POST"])
def recognize_template():
    try:
        data = request.get_json(force=True, silent=True) or {}
        session_id = (data.get("session_id") or "").strip()
        filename = (data.get("filename") or "").strip()
        if not session_id:
            return jsonify({"ok": False, "error": "缺少 session_id"}), 400

        session_dir = os.path.join(UPLOAD_ROOT, session_id)
        if not filename:
            if not os.path.isdir(session_dir):
                return jsonify({"ok": False, "error": "该会话暂无上传文件"}), 400
            cands = [os.path.join(session_dir, f) for f in os.listdir(session_dir)
                     if os.path.splitext(f)[1].lower() in ALLOWED_EXT]
            if not cands:
                return jsonify({"ok": False, "error": "该会话暂无可识别的文件"}), 400
            cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            filename = os.path.basename(cands[0])

        text = writer_service.get_doc_text_by_filename(session_id, filename)
        if not text:
            return jsonify({"ok": False, "error": "模板文件未在会话中找到或内容为空"}), 404

        headings, placeholders = [], set()
        for line in text.splitlines():
            s = line.strip()
            if s and (HEADING_RE.match(s) or len(s) <= 24):
                headings.append(s)
        for pat in [r"\{\{(.+?)\}\}", r"【(.+?)】", r"\[(.+?)\]"]:
            for m in _re.findall(pat, text):
                placeholders.add(m.strip())

        outline = [h for h in headings[:10]]
        ph_list = list(placeholders)[:20]
        joined_outline = "\n".join(f"- {h}" for h in outline) if outline else "（未识别到明显大纲，按常见结构撰写）"
        joined_ph = ", ".join(ph_list) if ph_list else "（无明显占位符，按常见字段自行补充）"

        suggested_instruction = (
            f"【写作模板】\n{joined_outline}\n\n"
            f"【重点字段】{joined_ph}\n"
            f"请基于以上模板约束完成写作。"
        )
        return jsonify({"ok": True, "template": {
            "filename": filename,
            "outline": outline,
            "placeholders": ph_list,
            "suggested_instruction": suggested_instruction
        }})
    except Exception as e:
        logger.error(f"模板识别失败: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

# ================== 模型列表 ==================
def _normalize_models(ms: Iterable) -> List[str]:
    out = []
    if not ms: return out
    if isinstance(ms, dict): return [str(k) for k in ms.keys()]
    for x in ms: out.append(str(x))
    return out

@writer_bp.route("/writer/models", methods=["GET"])
def list_models():
    try:
        llm_service = current_app.llm_service
        models = []
        try:
            clients = getattr(llm_service, "clients", None)
            if clients: models = _normalize_models(clients)
        except Exception:
            models = []
        if not models:
            fallback = getattr(Settings, "LLM_ENDPOINTS", None)
            if isinstance(fallback, dict): models = _normalize_models(fallback)
            elif isinstance(fallback, (list, tuple, set)): models = [str(x) for x in fallback]
        seen=set(); uniq=[]
        for m in models:
            if m and m not in seen: seen.add(m); uniq.append(m)
        default_id = getattr(Settings, "DEFAULT_LLM_ID", None)
        if default_id and default_id not in seen: uniq.insert(0, default_id)
        return jsonify({"ok": True, "models": uniq, "default": default_id})
    except Exception as e:
        logger.error(f"列出模型失败: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

# ================== 生成流（新增：kb_selected 透传） ==================
@writer_bp.route("/writer/chat", methods=["POST"])
def writer_chat():
    data = request.get_json(force=True, silent=True) or {}
    session_id = (data.get("session_id") or "").strip()
    instruction = (data.get("instruction") or "").strip()
    template_content = (data.get("template_content") or "").strip()
    model_id = data.get("model_id", getattr(Settings, "DEFAULT_LLM_ID", None))
    enable_thinking = bool(data.get("enable_thinking", False))
    use_kb = bool(data.get("use_kb", False))
    kb_selected_raw = data.get("kb_selected") or data.get("selected_kb_files") or []

    # 规范化：仅保留 basename，过滤空项
    kb_selected = []
    if isinstance(kb_selected_raw, list):
        for x in kb_selected_raw:
            if not x:
                continue
            kb_selected.append(os.path.basename(str(x)))

    if not session_id or not instruction:
        return jsonify({"ok": False, "error": "缺少 session_id 或 instruction"}), 400

    composed_instruction = (
        f"【写作模板】\n{template_content}\n\n【写作需求】\n{instruction}"
        if template_content else instruction
    )

    llm_service = current_app.llm_service
    knowledge_service = current_app.knowledge_service
    reranker = current_app.reranker
    try:
        llm = llm_service.get_client(model_id)
    except Exception as e:
        logger.error(f"获取 LLM 失败: {e}", exc_info=True)
        return jsonify({"ok": False, "error": f"模型不可用：{e}"}), 500

    handler = WriterHandler(reranker)

    def generate():
        try:
            for chunk in handler.process_stream(
                llm=llm,
                session_id=session_id,
                instruction=composed_instruction,
                conversation_manager=knowledge_service.conversation_manager,
                enable_thinking=enable_thinking,
                use_kb=use_kb,
                kb_selected=kb_selected,   # ← 新增：仅使用被选中的 KB 文档
            ):
                yield chunk
        except Exception as e:
            yield f"ERROR:{str(e)}"

    return Response(
        stream_with_context((format_sse_text(item) for item in generate())),
        mimetype="text/event-stream"
    )

# ================== 额外知识库（持久化 + 口令校验） ==================
@writer_bp.route("/writer/kb/upload", methods=["POST"])
def kb_upload():
    try:
        # 口令校验（必须）
        kb_pwd = request.form.get("kb_password", "") or request.headers.get("X-KB-PASSWORD", "")
        if not WRITER_KB_UPLOAD_PASSWORD:
            return jsonify({"ok": False, "error": "系统未配置知识库上传口令（WRITER_KB_UPLOAD_PASSWORD）"}), 403
        if kb_pwd != str(WRITER_KB_UPLOAD_PASSWORD):
            return jsonify({"ok": False, "error": "知识库口令错误"}), 403

        files = request.files.getlist("files")
        if not files:
            return jsonify({"ok": False, "error": "未选择文件"}), 400
        saved = _save_files(KB_UPLOAD_ROOT, files, overwrite=True)
        if not saved:
            return jsonify({"ok": False, "error": "文件类型不支持或超出限制"}), 400

        added, names = _try_call(
            writer_service.attach_kb_files,
            [((saved,), {"target_collection": WRITER_KB_COLLECTION})]
        )
        return jsonify({"ok": True, "added": added, "files": _to_basenames(names), "allFiles": _kb_list_basenames_via_service_or_disk()})
    except AttributeError:
        # 服务层未实现 target_collection 也可退化成功
        return jsonify({"ok": True, "added": len(saved), "files": [os.path.basename(p) for p in saved], "allFiles": _to_basenames(_kb_disk_all_paths())})
    except Exception as e:
        logger.error(f"KB 上传失败: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

@writer_bp.route("/writer/kb/upload/delete", methods=["POST"])
def kb_delete():
    try:
        data = request.get_json(force=True, silent=True) or {}
        filename = (data.get("filename") or "").strip()
        if not filename:
            return jsonify({"ok": False, "error": "缺少 filename"}), 400

        candidates = _kb_resolve_candidates(filename)

        # 1) 服务层删除
        removed = False
        try:
            removed = _try_call(writer_service.detach_kb_file, [((filename,), {})])
        except AttributeError:
            removed = False

        # 2) 磁盘兜底
        if not removed:
            for cand in candidates:
                if os.path.exists(cand):
                    try:
                        os.remove(cand)
                        removed = True
                        break
                    except Exception as e:
                        logger.warning(f"磁盘删除失败: {cand} -> {e}")

        # 3) 向量删除（KB 集合）
        vec_removed = _delete_vectors_for_candidates(WRITER_KB_COLLECTION, candidates + [filename])

        # 前端已采用“墓碑”隐藏，不回滚
        if not removed and not vec_removed:
            return jsonify({"ok": False, "error": "未找到指定文件", "available": _kb_list_basenames_via_service_or_disk()}), 404

        return jsonify({"ok": True, "allFiles": _kb_list_basenames_via_service_or_disk()})
    except Exception as e:
        logger.error(f"KB 删除失败: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500

@writer_bp.route("/writer/kb/list", methods=["GET"])
def kb_list():
    try:
        return jsonify({"ok": True, "files": _kb_list_basenames_via_service_or_disk()})
    except Exception as e:
        logger.error(f"KB 列表失败: {e}", exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500
