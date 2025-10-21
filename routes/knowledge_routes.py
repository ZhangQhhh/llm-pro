# -*- coding: utf-8 -*-
"""
知识问答路由
"""
from flask import Blueprint, request, jsonify, Response, stream_with_context, g, current_app
from config import Settings
from utils import format_sse_text, logger, generate_session_id, validate_session_ownership
from utils.IP_helper import get_client_ip

knowledge_bp = Blueprint('knowledge', __name__)


# 🔥 添加认证钩子 - 在所有路由执行前验证 token
@knowledge_bp.before_request
def require_auth_for_knowledge():
    """知识库路由的认证钩子"""
    # 白名单路径(不需要认证的路由)
    whitelist_paths = [
        '/api/knowledge_chat',
        '/api/test',
    ]

    # 检查当前路径是否在白名单中
    if request.path in whitelist_paths:
        return None

    # 获取认证管理器
    auth_manager = current_app.extensions.get('auth_manager')
    if not auth_manager:
        logger.error("认证管理器未初始化")
        return jsonify({"detail": "服务配置错误"}), 500

    # 提取并验证 token
    token = request.headers.get("Authorization")
    if not token:
        logger.warning(f"请求 {request.path} 缺少 Authorization header | IP: {request.remote_addr}")
        client_ip = get_client_ip()
        logger.warning(f"----------- | IP: {client_ip} ")
        return jsonify({"detail": "未提供认证令牌"}), 401

    if token.startswith("Bearer "):
        token = token[7:]

    # 验证 token
    user_info = auth_manager._validate_token(token)
    if not user_info:
        logger.warning(f"Token 验证失败: {token[:20]}... | IP: {request.remote_addr}")
        return jsonify({"detail": "认证令牌无效或已过期"}), 401

    # 将用户信息注入到 g 对象  g对象是临时存储请求级别数据的地方
    g.username = user_info["username"]
    g.userid = user_info["userid"]
    g.token = token

    logger.debug(f"用户 {g.username} (ID: {g.userid}) 已通过认证，访问 {request.path}")


@knowledge_bp.route('/knowledge_chat_conversation', methods=['POST'])
def knowledge_chat_conversation():
    """
    支持多轮对话的知识问答接口（需要认证）

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
    # ✅ 获取当前用户信息（由 before_request 钩子注入）
    username = g.get('username', 'unknown')
    userid = g.get('userid', 0)

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
    llm_service = current_app.llm_service
    knowledge_handler = current_app.knowledge_handler

    # 处理会话ID（格式：{userid}_{uuid}）
    if not session_id:
        session_id = generate_session_id(userid)
        logger.info(f"用户 {username} (ID: {userid}) 创建新会话: {session_id}")
    else:
        # 验证会话ID是否属于当前用户
        if not validate_session_ownership(session_id, userid):
            logger.warning(
                f"用户 {username} (ID: {userid}) 尝试访问其他用户的会话: {session_id}"
            )
            return jsonify({
                "type": "error",
                "content": "无权访问该会话"
            }), 403

    # 获取 LLM 客户端
    try:
        selected_llm = llm_service.get_client(requested_model_id)
        logger.info(
            f"用户 {username} (ID: {userid}) | 会话 {session_id[:8]}... | "
            f"模型: '{requested_model_id}' | InsertBlock: {use_insert_block}"
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
        if client_ip == 'unknown':
            client_ip = get_client_ip()   # 这里如果获取不到，就用新的IP获取方法，原来的代码不是我写的hhh，所以不知道什么情况，先保留。
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

    # 使用 stream_with_context 确保在流式响应期间保留应用/请求上下文
    return Response(stream_with_context(generate()), mimetype='text/event-stream')


@knowledge_bp.route('/conversation/clear', methods=['POST'])
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
            success = knowledge_service.conversation_manager.clear_session(session_id)
            if success:
                return jsonify({
                    "type": "success",
                    "message": f"会话 {session_id} 已清空"
                })
            else:
                return jsonify({
                    "type": "error",
                    "content": "清空会话失败"
                }), 500
        else:
            return jsonify({
                "type": "error",
                "content": "对话管理器未初始化"
            }), 500
    except Exception as e:
        logger.error(f"清空会话失败: {e}", exc_info=True)
        return jsonify({"type": "error", "content": str(e)}), 500


@knowledge_bp.route('/conversation/statistics', methods=['POST'])
def get_conversation_statistics():
    """
    获取会话统计信息

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
            stats = knowledge_service.conversation_manager.get_session_statistics(session_id)
            if "error" in stats:
                return jsonify({
                    "type": "error",
                    "content": stats["error"]
                }), 500
            else:
                return jsonify({
                    "type": "success",
                    "data": stats
                })
        else:
            return jsonify({
                "type": "error",
                "content": "对话管理器未初始化"
            }), 500
    except Exception as e:
        logger.error(f"获取会话统计失败: {e}", exc_info=True)
        return jsonify({"type": "error", "content": str(e)}), 500


@knowledge_bp.route('/conversation/cache/clear', methods=['POST'])
def clear_conversation_cache():
    """
    清空对话缓存（管理员功能）

    Request JSON:
    {
        "admin_token": "管理员令牌(可选)"
    }
    """
    try:
        from flask import current_app
        knowledge_service = current_app.knowledge_service

        if knowledge_service.conversation_manager:
            knowledge_service.conversation_manager.clear_cache()
            return jsonify({
                "type": "success",
                "message": "对话缓存已清空"
            })
        else:
            return jsonify({
                "type": "error",
                "content": "对话管理器未初始化"
            }), 500
    except Exception as e:
        logger.error(f"清空缓存失败: {e}", exc_info=True)
        return jsonify({"type": "error", "content": str(e)}), 500


@knowledge_bp.route('/conversation/sessions/list', methods=['POST'])
def get_user_sessions_list():
    """
    获取当前用户的会话列表（需要认证）

    Request JSON:
    {
        "page": 1,
        "page_size": 20,
        "sort_by": "last_update"  # 或 "create_time"
    }

    Response:
    {
        "type": "success",
        "data": {
            "total": 50,
            "sessions": [
                {
                    "session_id": "123_uuid",
                    "user_id": 123,
                    "title": "关于护照办理的咨询",
                    "first_message": "我想问一下护照办理...",
                    "last_message": "好的，谢谢",
                    "message_count": 5,
                    "total_tokens": 1234,
                    "create_time": "2025-01-20T10:30:00",
                    "last_update_time": "2025-01-20T11:00:00"
                },
                ...
            ],
            "page": 1,
            "page_size": 20
        }
    }
    """
    # 获取当前用户信息
    username = g.get('username', 'unknown')
    userid = g.get('userid', 0)

    data = request.get_json() or {}

    # 参数解析
    page = data.get('page', 1)
    page_size = data.get('page_size', 20)
    sort_by = data.get('sort_by', 'last_update')

    # 参数验证
    try:
        page = max(1, int(page))
        page_size = max(1, min(100, int(page_size)))  # 限制最大100条
    except (ValueError, TypeError):
        return jsonify({
            "type": "error",
            "content": "页码和页大小必须是有效的数字"
        }), 400

    if sort_by not in ['last_update', 'create_time']:
        sort_by = 'last_update'

    # 计算偏移量
    offset = (page - 1) * page_size

    try:
        knowledge_service = current_app.knowledge_service

        if not knowledge_service.conversation_manager:
            return jsonify({
                "type": "error",
                "content": "对话管理器未初始化"
            }), 500

        # 获取会话列表
        result = knowledge_service.conversation_manager.get_user_sessions(
            user_id=userid,
            limit=page_size,
            offset=offset,
            sort_by=sort_by
        )

        if "error" in result:
            return jsonify({
                "type": "error",
                "content": result["error"]
            }), 500

        logger.info(
            f"用户 {username} (ID: {userid}) 查询会话列表 | "
            f"第 {page} 页，共 {result['total']} 个会话"
        )

        return jsonify({
            "type": "success",
            "data": {
                "total": result["total"],
                "sessions": result["sessions"],
                "page": page,
                "page_size": page_size
            }
        })

    except Exception as e:
        logger.error(f"获取会话列表失败: {e}", exc_info=True)
        return jsonify({
            "type": "error",
            "content": str(e)
        }), 500


@knowledge_bp.route('/conversation/sessions/<session_id>/history', methods=['POST'])
def get_session_history(session_id):
    """
    获取指定会话的历史消息（需要认证）

    URL Parameter:
        session_id: 会话ID

    Request JSON:
    {
        "limit": 50,
        "offset": 0,
        "order": "asc"  # asc=从旧到新, desc=从新到旧
    }

    Response:
    {
        "type": "success",
        "data": {
            "session_id": "123_uuid",
            "total_messages": 10,
            "messages": [
                {
                    "turn_id": "turn_uuid",
                    "user_query": "护照办理需要什么材料？",
                    "assistant_response": "护照办理需要以下材料...",
                    "timestamp": "2025-01-20T10:30:15",
                    "context_docs": ["护照办理规定.pdf"],
                    "token_count": 245
                },
                ...
            ]
        }
    }
    """
    # 获取当前用户信息
    username = g.get('username', 'unknown')
    userid = g.get('userid', 0)

    # 验证会话所有权
    if not validate_session_ownership(session_id, userid):
        logger.warning(
            f"用户 {username} (ID: {userid}) 尝试访问其他用户的会话历史: {session_id}"
        )
        return jsonify({
            "type": "error",
            "content": "无权访问该会话"
        }), 403

    data = request.get_json() or {}

    # 参数解析
    limit = data.get('limit', 50)
    offset = data.get('offset', 0)
    order = data.get('order', 'asc')

    # 参数验证
    try:
        limit = max(1, min(200, int(limit)))  # 限制最大200条
        offset = max(0, int(offset))
    except (ValueError, TypeError):
        return jsonify({
            "type": "error",
            "content": "limit和offset必须是有效的数字"
        }), 400

    if order not in ['asc', 'desc']:
        order = 'asc'

    try:
        knowledge_service = current_app.knowledge_service

        if not knowledge_service.conversation_manager:
            return jsonify({
                "type": "error",
                "content": "对话管理器未初始化"
            }), 500

        # 获取会话历史
        result = knowledge_service.conversation_manager.get_session_full_history(
            session_id=session_id,
            limit=limit,
            offset=offset,
            order=order
        )

        if "error" in result:
            return jsonify({
                "type": "error",
                "content": result["error"]
            }), 500

        logger.info(
            f"用户 {username} (ID: {userid}) 查询会话 {session_id[:8]}... 的历史 | "
            f"共 {result['total_messages']} 条消息"
        )

        return jsonify({
            "type": "success",
            "data": result
        })

    except Exception as e:
        logger.error(f"获取会话历史失败: {e}", exc_info=True)
        return jsonify({
            "type": "error",
            "content": str(e)
        }), 500


@knowledge_bp.route('/conversation/sessions/<session_id>/delete', methods=['DELETE', 'POST'])
def delete_session(session_id):
    """
    删除指定会话（需要认证）

    URL Parameter:
        session_id: 会话ID

    Response:
    {
        "type": "success",
        "message": "会话已删除"
    }
    """
    # 获取当前用户信息
    username = g.get('username', 'unknown')
    userid = g.get('userid', 0)

    # 验证会话所有权
    if not validate_session_ownership(session_id, userid):
        logger.warning(
            f"用户 {username} (ID: {userid}) 尝试删除其他用户的会话: {session_id}"
        )
        return jsonify({
            "type": "error",
            "content": "无权删除该会话"
        }), 403

    try:
        knowledge_service = current_app.knowledge_service

        if not knowledge_service.conversation_manager:
            return jsonify({
                "type": "error",
                "content": "对话管理器未初始化"
            }), 500

        # 删除会话
        success = knowledge_service.conversation_manager.delete_session(session_id)

        if success:
            logger.info(f"用户 {username} (ID: {userid}) 删除会话: {session_id}")
            return jsonify({
                "type": "success",
                "message": f"会话 {session_id} 已删除"
            })
        else:
            return jsonify({
                "type": "error",
                "content": "删除会话失败"
            }), 500

    except Exception as e:
        logger.error(f"删除会话失败: {e}", exc_info=True)
        return jsonify({
            "type": "error",
            "content": str(e)
        }), 500


@knowledge_bp.route('/conversation/sessions/<session_id>/info', methods=['GET', 'POST'])
def get_session_info(session_id):
    """
    获取会话的详细信息（需要认证）

    URL Parameter:
        session_id: 会话ID

    Response:
    {
        "type": "success",
        "data": {
            "session_id": "123_uuid",
            "user_id": 123,
            "title": "关于护照办理的咨询",
            "message_count": 10,
            "total_tokens": 2456,
            "create_time": "2025-01-20T10:30:00",
            "last_update_time": "2025-01-20T11:00:00",
            "first_message": "我想问一下护照办理需要什么材料？"
        }
    }
    """
    # 获取当前用户信息
    username = g.get('username', 'unknown')
    userid = g.get('userid', 0)

    # 验证会话所有权
    if not validate_session_ownership(session_id, userid):
        logger.warning(
            f"用户 {username} (ID: {userid}) 尝试访问其他用户的会话信息: {session_id}"
        )
        return jsonify({
            "type": "error",
            "content": "无权访问该会话"
        }), 403

    try:
        knowledge_service = current_app.knowledge_service

        if not knowledge_service.conversation_manager:
            return jsonify({
                "type": "error",
                "content": "对话管理器未初始化"
            }), 500

        # 获取会话信息
        session_info = knowledge_service.conversation_manager.get_session_info(session_id)

        if session_info is None:
            return jsonify({
                "type": "error",
                "content": "会话不存在"
            }), 404

        logger.info(f"用户 {username} (ID: {userid}) 查询会话信息: {session_id[:8]}...")

        return jsonify({
            "type": "success",
            "data": session_info
        })

    except Exception as e:
        logger.error(f"获取会话信息失败: {e}", exc_info=True)
        return jsonify({
            "type": "error",
            "content": str(e)
        }), 500


@knowledge_bp.route('/knowledge_chat', methods=['POST'])
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
            stream_with_context((format_sse_text(item) for item in empty_stream())),
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
            stream_with_context((format_sse_text(item) for item in error_stream())),
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
        stream_with_context((format_sse_text(item) for item in generate())),
        mimetype='text/event-stream'
    )
