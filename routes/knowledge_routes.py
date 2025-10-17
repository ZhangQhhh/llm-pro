# -*- coding: utf-8 -*-
"""
知识问答路由
"""
from flask import Blueprint, request, jsonify, Response
from config import Settings
from utils import format_sse_text, logger


knowledge_bp = Blueprint('knowledge', __name__)


@knowledge_bp.route('/api/knowledge_chat_conversation', methods=['POST'])
def knowledge_chat_conversation():
    """
    支持多轮对话的知识问答接口

    Request JSON:
    {
        "question": "用户问题",
        "session_id": "会话ID(可选,不提供则创建新会话)",
        "thinking": true/false,
        "model_id": "模型ID",
        "rerank_top_n": 10,
        "use_insert_block": false
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"type": "error", "content": "请求体必须是JSON格式"}), 400

    # 参数解析
    user_question = data.get('question', '').strip()
    session_id = data.get('session_id')  # 可选
    enable_thinking_str = data.get('thinking', 'true')
    enable_thinking = str(enable_thinking_str).lower() == 'true'
    requested_model_id = data.get('model_id', Settings.DEFAULT_LLM_ID)

    # InsertBlock 模式参数
    use_insert_block_str = data.get('use_insert_block', 'false')
    use_insert_block = str(use_insert_block_str).lower() == 'true'
    insert_block_llm_id = data.get('insert_block_llm_id', None)

    # 验证 rerank_top_n
    default_top_n = Settings.RERANK_TOP_N
    MIN_RERANK_N = 1
    MAX_RERANK_N = 15

    custom_top_n = data.get('rerank_top_n', default_top_n)
    try:
        rerank_top_n = int(custom_top_n)
        if not (MIN_RERANK_N <= rerank_top_n <= MAX_RERANK_N):
            logger.warning(
                f"rerank_top_n 值({rerank_top_n})超出范围"
                f"[{MIN_RERANK_N}-{MAX_RERANK_N}]，重置为{default_top_n}"
            )
            rerank_top_n = default_top_n
    except (ValueError, TypeError):
        logger.warning(
            f"rerank_top_n 值('{custom_top_n}')格式错误，"
            f"重置为{default_top_n}"
        )
        rerank_top_n = default_top_n

    # 验证问题非空
    if not user_question:
        return jsonify({"type": "error", "content": "问题内容不能为空"}), 400

    # 获取依赖
    from flask import current_app
    import uuid

    llm_service = current_app.llm_service
    knowledge_handler = current_app.knowledge_handler

    # 生成会话ID
    if not session_id:
        session_id = str(uuid.uuid4())
        logger.info(f"创建新会话: {session_id}")

    # 获取 LLM 客户端
    try:
        selected_llm = llm_service.get_client(requested_model_id)
        logger.info(
            f"会话 {session_id[:8]}... | 模型: '{requested_model_id}' | "
            f"InsertBlock: {use_insert_block}"
        )
    except Exception as e:
        logger.error(f"获取 LLM 客户端失败: {e}")
        return jsonify({"type": "error", "content": "模型服务异常"}), 500

    # 获取客户端 IP
    try:
        client_ip = request.environ.get(
            'HTTP_X_FORWARDED_FOR',
            request.environ.get('REMOTE_ADDR', 'unknown')
        )
    except RuntimeError:
        client_ip = 'unknown'

    # 处理多轮对话请求
    def generate():
        for item in knowledge_handler.process_conversation(
            user_question,
            session_id,
            enable_thinking,
            rerank_top_n,
            selected_llm,
            client_ip,
            use_insert_block=use_insert_block,
            insert_block_llm_id=insert_block_llm_id
        ):
            yield format_sse_text(item)

    return Response(generate(), mimetype='text/event-stream')


@knowledge_bp.route('/api/conversation/clear', methods=['POST'])
def clear_conversation():
    """
    清空指定会话的对话历史

    Request JSON:
    {
        "session_id": "会话ID"
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"type": "error", "content": "请求体必须是JSON格式"}), 400

    session_id = data.get('session_id')
    if not session_id:
        return jsonify({"type": "error", "content": "缺少 session_id 参数"}), 400

    try:
        from flask import current_app
        knowledge_service = current_app.knowledge_service

        if knowledge_service.conversation_manager:
            knowledge_service.conversation_manager.clear_session(session_id)
            return jsonify({
                "type": "success",
                "message": f"会话 {session_id} 已清空"
            })
        else:
            return jsonify({
                "type": "error",
                "content": "对话管理器未初始化"
            }), 500
    except Exception as e:
        logger.error(f"清空会话失败: {e}")
        return jsonify({"type": "error", "content": str(e)}), 500


@knowledge_bp.route('/api/knowledge_chat', methods=['POST'])
def knowledge_chat():
    """知识问答接口"""
    data = request.get_json()
    if not data:
        return jsonify({"type": "error", "content": "请求体必须是JSON格式"}), 400

    # 参数解析
    user_question = data.get('question', '').strip()
    enable_thinking_str = data.get('thinking', 'true')
    enable_thinking = str(enable_thinking_str).lower() == 'true'
    requested_model_id = data.get('model_id', Settings.DEFAULT_LLM_ID)

    # InsertBlock 模式参数
    use_insert_block_str = data.get('use_insert_block', 'false')
    use_insert_block = str(use_insert_block_str).lower() == 'true'
    insert_block_llm_id = data.get('insert_block_llm_id', None)  # 默认使用 default LLM

    # 验证 rerank_top_n
    default_top_n = Settings.RERANK_TOP_N
    MIN_RERANK_N = 1
    MAX_RERANK_N = 15

    custom_top_n = data.get('rerank_top_n', default_top_n)
    try:
        rerank_top_n = int(custom_top_n)
        if not (MIN_RERANK_N <= rerank_top_n <= MAX_RERANK_N):
            logger.warning(
                f"rerank_top_n 值({rerank_top_n})超出范围"
                f"[{MIN_RERANK_N}-{MAX_RERANK_N}]，重置为{default_top_n}"
            )
            rerank_top_n = default_top_n
    except (ValueError, TypeError):
        logger.warning(
            f"rerank_top_n 值('{custom_top_n}')格式错误，"
            f"重置为{default_top_n}"
        )
        rerank_top_n = default_top_n

    # 验证问题非空
    if not user_question:
        def empty_stream():
            yield "ERROR:问题内容不能为空！"
        return Response(
            (format_sse_text(item) for item in empty_stream()),
            mimetype='text/event-stream'
        )

    # 获取依赖（从应用上下文）
    from flask import current_app
    llm_service = current_app.llm_service
    knowledge_handler = current_app.knowledge_handler

    # 获取 LLM 客户端
    try:
        selected_llm = llm_service.get_client(requested_model_id)
        logger.info(
            f"本次请求使用模型: '{requested_model_id}' | "
            f"InsertBlock 模式: {use_insert_block}"
        )
    except Exception as e:
        logger.error(f"获取 LLM 客户端失败: {e}")
        def error_stream():
            yield "ERROR:模型服务异常"
        return Response(
            (format_sse_text(item) for item in error_stream()),
            mimetype='text/event-stream'
        )

    # 获取客户端 IP
    try:
        client_ip = request.environ.get(
            'HTTP_X_FORWARDED_FOR',
            request.environ.get('REMOTE_ADDR', 'unknown')
        )
    except RuntimeError:
        client_ip = 'unknown'

    # 处理请求
    def generate():
        for item in knowledge_handler.process(
            user_question,
            enable_thinking,
            rerank_top_n,
            selected_llm,
            client_ip,
            use_insert_block=use_insert_block,
            insert_block_llm_id=insert_block_llm_id
        ):
            yield item

    return Response(
        (format_sse_text(item) for item in generate()),
        mimetype='text/event-stream'
    )
