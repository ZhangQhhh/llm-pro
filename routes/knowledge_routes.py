# -*- coding: utf-8 -*-
"""
知识问答路由
"""
from flask import Blueprint, request, jsonify, Response, stream_with_context, g, current_app
from config import Settings
from utils import format_sse_text, logger, generate_session_id, validate_session_ownership
from utils.IP_helper import get_client_ip
import time

knowledge_bp = Blueprint('knowledge', __name__)


#  添加认证钩子 - 在所有路由执行前验证 token
@knowledge_bp.before_request
def require_auth_for_knowledge():
    """知识库路由的认证钩子"""
    # 白名单路径(不需要认证的路由)
    whitelist_paths = [
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


@knowledge_bp.route('/conversation/new', methods=['POST'])
def create_new_session():
    """
    创建新会话接口

    用户主动创建新会话，不再自动生成

    Returns:
        JSON: {"session_id": "新会话ID", "message": "成功消息"}
    """
    # 获取当前用户信息
    username = g.get('username', 'unknown')
    userid = g.get('userid', 0)

    # 生成新会话ID
    new_session_id = generate_session_id(userid)

    logger.info(f"用户 {username} (ID: {userid}) 主动创建新会话: {new_session_id}")

    return jsonify({
        "session_id": new_session_id,
        "message": "新会话创建成功"
    }), 200


@knowledge_bp.route('/knowledge_chat_conversation', methods=['POST'])
def knowledge_chat_conversation():
    """
    支持多轮对话的知识问答接口（需要认证）

    Request JSON:
    {
        "question": "用户问题",
        "session_id": "会话ID(必须提供，使用/conversation/new创建)",
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
    session_id = data.get('session_id')  # 现在变为必须提供
    enable_thinking_str = data.get('thinking', 'true')
    enable_thinking = str(enable_thinking_str).lower() == 'true'
    requested_model_id = data.get('model_id', Settings.DEFAULT_LLM_ID)

    # InsertBlock 模式参数
    use_insert_block_str = data.get('use_insert_block', 'false')
    use_insert_block = str(use_insert_block_str).lower() == 'true'
    insert_block_llm_id = data.get('insert_block_llm_id', None)

    # 验证 rerank_top_n
    default_top_n = Settings.RERANK_TOP_N
    MIN_RERANK_N = 0  # 允许设置为 0，表示不检索
    MAX_RERANK_N = 30  # 放宽限制，允许前端传入更多参考文献

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

    # 🔥 验证会话ID必须提供
    if not session_id:
        return jsonify({
            "type": "error",
            "content": "缺少会话ID，请先创建会话或使用现有会话"
        }), 400

    # 获取依赖
    llm_service = current_app.llm_service
    knowledge_handler = current_app.knowledge_handler

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
            client_ip = get_client_ip()
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
            # item 是元组格式: ('THINK', content) 或 ('CONTENT', content) 或 ('SOURCE', json_data)
            if isinstance(item, tuple) and len(item) == 2:
                prefix_type, content = item
                # 格式化为 SSE 消息
                if prefix_type == 'THINK':
                    formatted_item = f"THINK:{content}"
                    logger.debug(f"[DEBUG] THINK 原始数据: \"{content[:100]}...\" | 长度: {len(content)}")
                    logger.debug(f"[DEBUG] THINK SSE格式化后: \"{formatted_item[:100]}...\"")
                elif prefix_type == 'CONTENT':
                    formatted_item = f"CONTENT:{content}"
                elif prefix_type == 'SOURCE':
                    formatted_item = f"SOURCE:{content}"
                elif prefix_type == 'DONE':
                    formatted_item = f"DONE:{content}"
                else:
                    # 兼容其他格式
                    formatted_item = f"{prefix_type}:{content}"
            else:
                # 兼容旧格式（直接是字符串）
                formatted_item = item
            
            yield format_sse_text(formatted_item)

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

    # ✅ 验证用户ID有效性 - 防止获取到无效用户或所有用户的数据
    if not userid or userid <= 0:
        logger.warning(f"无效的用户ID: {userid}，拒绝获取会话列表")
        return jsonify({
            "type": "error",
            "content": "无效的用户认证信息，请重新登录"
        }), 401

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
    enable_thinking_str = data.get('thinking', 'false')  # 默认关闭思考模式，避免无限思考
    enable_thinking = str(enable_thinking_str).lower() == 'true'
    requested_model_id = data.get('model_id', Settings.DEFAULT_LLM_ID)

    # InsertBlock 模式参数
    use_insert_block_str = data.get('use_insert_block', 'false')
    use_insert_block = str(use_insert_block_str).lower() == 'true'
    insert_block_llm_id = data.get('insert_block_llm_id', None)  # 默认使用 default LLM

    # 验证 rerank_top_n
    default_top_n = Settings.RERANK_TOP_N
    MIN_RERANK_N = 0  # 允许设置为 0，表示不检索
    MAX_RERANK_N = 30  # 放宽限制，允许前端传入更多参考文献

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
            # item 是元组格式: ('THINK', content) 或 ('CONTENT', content) 或 ('SOURCE', json_data) 或 ('SUB_QUESTIONS', data)
            if isinstance(item, tuple) and len(item) == 2:
                prefix_type, content = item
                # 格式化为 SSE 消息
                if prefix_type == 'THINK':
                    yield f"THINK:{content}"
                elif prefix_type == 'CONTENT':
                    yield f"CONTENT:{content}"
                elif prefix_type == 'SOURCE':
                    yield f"SOURCE:{content}"
                elif prefix_type == 'SUB_QUESTIONS':
                    # 子问题数据，转换为 JSON
                    import json
                    yield f"SUB_QUESTIONS:{json.dumps(content, ensure_ascii=False)}"
                elif prefix_type == 'DONE':
                    yield f"DONE:{content}"
                else:
                    # 兼容其他格式
                    yield f"{prefix_type}:{content}"
            else:
                # 兼容旧格式（直接是字符串）
                yield item

    return Response(
        stream_with_context((format_sse_text(item) for item in generate())),
        mimetype='text/event-stream'
    )


@knowledge_bp.route('/knowledge_chat_12367', methods=['POST'])
def knowledge_chat_12367():
    """
    12367专用知识问答接口
    使用通用知识库B，其他功能与原接口完全相同
    """
    # 检查通用知识库B是否启用
    if not current_app.knowledge_handler_b:
        return jsonify({
            "type": "error",
            "content": "通用知识库B未启用或初始化失败"
        }), 503
    
    data = request.get_json()
    if not data:
        return jsonify({"type": "error", "content": "请求体必须是JSON格式"}), 400

    # 参数解析（与原接口完全相同）
    user_question = data.get('question', '').strip()
    enable_thinking_str = data.get('thinking', 'false')
    enable_thinking = str(enable_thinking_str).lower() == 'true'
    requested_model_id = data.get('model_id', Settings.DEFAULT_LLM_ID)

    # InsertBlock 模式参数
    use_insert_block_str = data.get('use_insert_block', 'false')
    use_insert_block = str(use_insert_block_str).lower() == 'true'
    insert_block_llm_id = data.get('insert_block_llm_id', None)

    # 验证 rerank_top_n
    default_top_n = Settings.RERANK_TOP_N
    MIN_RERANK_N = 0
    MAX_RERANK_N = 30

    custom_top_n = data.get('rerank_top_n', default_top_n)
    try:
        rerank_top_n = int(custom_top_n)
        if not (MIN_RERANK_N <= rerank_top_n <= MAX_RERANK_N):
            logger.warning(
                f"[12367] rerank_top_n 值({rerank_top_n})超出范围"
                f"[{MIN_RERANK_N}-{MAX_RERANK_N}]，重置为{default_top_n}"
            )
            rerank_top_n = default_top_n
    except (ValueError, TypeError):
        logger.warning(
            f"[12367] rerank_top_n 值('{custom_top_n}')格式错误，"
            f"重置为{default_top_n}"
        )
        rerank_top_n = default_top_n

    # 验证问题非空
    if not user_question:
        def empty_stream():
            yield "CONTENT:问题不能为空\n"
            yield "DONE:问题不能为空\n"
        return Response(
            stream_with_context((format_sse_text(item) for item in empty_stream())),
            mimetype='text/event-stream'
        )

    # 获取 LLM 客户端
    llm_service = current_app.llm_service
    try:
        selected_llm = llm_service.get_client(requested_model_id)
        logger.info(
            f"[12367专用接口] 本次请求使用模型: '{requested_model_id}' | "
            f"InsertBlock 模式: {use_insert_block}"
        )
    except Exception as e:
        logger.error(f"[12367专用接口] 获取 LLM 客户端失败: {e}")
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

    # 使用12367专用的knowledge_handler_b处理请求
    def generate():
        try:
            logger.info(f"[12367专用接口] 收到问题: {user_question}")
            logger.info(f"[12367专用接口] 使用通用知识库B | 模型: {requested_model_id} | 思考模式: {enable_thinking}")
            logger.info(f"[12367专用接口] InsertBlock模式: {use_insert_block} | 重排序数量: {rerank_top_n}")
            
            # 调用12367专用handler的process方法
            for item in current_app.knowledge_handler_b.process(
                question=user_question,
                enable_thinking=enable_thinking,
                rerank_top_n=rerank_top_n,
                llm=selected_llm,
                client_ip=client_ip,
                use_insert_block=use_insert_block,
                insert_block_llm_id=insert_block_llm_id
            ):
                if isinstance(item, tuple):
                    prefix_type, content = item
                    if prefix_type == 'SOURCE':
                        yield f"SOURCE:{content}"
                    elif prefix_type == 'THINK':
                        yield f"THINK:{content}"
                    elif prefix_type == 'CONTENT':
                        yield f"CONTENT:{content}"
                    elif prefix_type == 'SUB_QUESTIONS':
                        yield f"SUB_QUESTIONS:{json.dumps(content, ensure_ascii=False)}"
                    elif prefix_type == 'DONE':
                        yield f"DONE:{content}"
                    else:
                        yield f"{prefix_type}:{content}"
                else:
                    yield item
                    
        except Exception as e:
            logger.error(f"[12367专用接口] 处理失败: {e}", exc_info=True)
            yield f"CONTENT:抱歉，处理您的问题时出现错误: {str(e)}\n"
            yield f"DONE:处理失败\n"

    return Response(
        stream_with_context((format_sse_text(item) for item in generate())),
        mimetype='text/event-stream'
    )


@knowledge_bp.route('/api/data/trend_summary', methods=['POST'])
def data_trend_summary():
    """
    数据趋势分析接口
    
    接收 Java 后端解析的统计数据，调用 LLM 生成趋势摘要
    
    请求体:
    {
        "code": 200,
        "message": "success",
        "data": {
            "totalCount": 1000,
            "entryCount": 600,
            "exitCount": 400,
            "maleCount": 550,
            "femaleCount": 450,
            "transportationToolStats": {...},
            "countryRegionStats": {...},
            "transportationModeStats": {...},
            "personCategoryStats": {...},
            "ethnicityStats": {...}
        },
        "model_id": "qwen2025",  // 可选，默认使用 Settings.DEFAULT_LLM_ID
        "thinking": false,        // 可选，是否启用思考模式
        "stream": true,           // 可选，是否使用 SSE 流式输出
        "max_length": 250         // 可选，摘要最大字数，默认250字
    }
    
    响应:
    - stream=true: SSE 流式输出
      * THINK: 思考内容（thinking=true 时）
      * CONTENT: 正文内容
      * META: 元数据 JSON {"model_id": "...", "elapsed_time": 2.5, "max_length": 250}
      * ERROR: 错误信息
      * DONE: 完成信号
    - stream=false: JSON 格式 {"summary": "...", "model_id": "...", "elapsed_time": 2.5, "code": 200}
    """
    try:
        # 1. 获取请求参数
        request_data = request.get_json()
        
        if not request_data:
            return jsonify({
                "code": 400,
                "message": "请求体不能为空",
                "data": None
            }), 400
        
        # 提取统计数据（支持两种格式）
        # 格式1: {"data": {...}}
        # 格式2: 直接传统计数据 {...}
        if "data" in request_data and isinstance(request_data["data"], dict):
            stats_data = request_data["data"]
        else:
            stats_data = request_data
        
        # 提取可选参数
        model_id = request_data.get("model_id", Settings.DEFAULT_LLM_ID)
        enable_thinking = request_data.get("thinking", False)
        use_stream = request_data.get("stream", True)
        max_length = request_data.get("max_length")  # 可选，默认使用配置
        
        logger.info(
            f"收到数据趋势分析请求 | "
            f"model_id: {model_id} | "
            f"thinking: {enable_thinking} | "
            f"stream: {use_stream} | "
            f"totalCount: {stats_data.get('totalCount', 'N/A')}"
        )
        
        # 记录开始时间
        start_time = time.time()
        
        # 2. 获取 LLM 服务
        llm_service = current_app.llm_service
        if not llm_service:
            logger.error("LLM 服务未初始化")
            return jsonify({
                "code": 500,
                "message": "LLM 服务未初始化",
                "data": None
            }), 500
        
        # 3. 创建数据分析处理器
        from api.data_analysis_handler import DataAnalysisHandler
        handler = DataAnalysisHandler(llm_service)
        
        # 4. 调用分析方法
        if use_stream:
            # SSE 流式输出
            def generate():
                """生成 SSE 流"""
                for msg_type, content in handler.analyze(
                    stats=stats_data,
                    llm_id=model_id,
                    enable_thinking=enable_thinking,
                    stream=True,
                    max_length=max_length
                ):
                    # 转换为 SSE 格式
                    if msg_type == 'THINK':
                        yield f"THINK:{content}"
                    elif msg_type == 'CONTENT':
                        yield f"CONTENT:{content}"
                    elif msg_type == 'ERROR':
                        yield f"ERROR:{content}"
                    elif msg_type == 'META':
                        yield f"META:{content}"
                    elif msg_type == 'DONE':
                        yield "DONE:"
            
            return Response(
                stream_with_context((format_sse_text(item) for item in generate())),
                mimetype='text/event-stream'
            )
        else:
            # JSON 同步输出
            think_parts = []
            content_parts = []
            error_msg = None
            
            for msg_type, content in handler.analyze(
                stats=stats_data,
                llm_id=model_id,
                enable_thinking=enable_thinking,
                stream=False,
                max_length=max_length
            ):
                if msg_type == 'THINK':
                    think_parts.append(content)
                elif msg_type == 'CONTENT':
                    content_parts.append(content)
                elif msg_type == 'ERROR':
                    error_msg = content
            
            # 如果有错误，返回错误响应
            if error_msg:
                return jsonify({
                    "code": 400,
                    "message": error_msg,
                    "data": None
                }), 400
            
            # 构建响应
            summary = ''.join(content_parts)
            response_data = {
                "summary": summary,
                "model_id": model_id
            }
            
            # 如果有思考内容，也包含进去
            if think_parts:
                response_data["thinking"] = ''.join(think_parts)
            
            # 添加耗时信息（在路由层计算）
            elapsed_time = time.time() - start_time
            response_data["elapsed_time"] = round(elapsed_time, 2)  # 秒，保留2位小数
            
            return jsonify({
                "code": 200,
                "message": "success",
                "data": response_data
            })
    
    except Exception as e:
        error_msg = f"数据趋势分析失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return jsonify({
            "code": 500,
            "message": error_msg,
            "data": None
        }), 500

