# -*- coding: utf-8 -*-
"""
角色权限控制中间件
"""
from functools import wraps
from flask import request, jsonify, g
from utils import logger
import requests
import os

def _get_user_role_from_spring(username: str) -> str:
    """从Spring Boot后端获取用户角色"""
    try:
        spring_boot_url = os.getenv('SPRING_BOOT_URL', 'http://localhost:8080')
        url = f"{spring_boot_url}/api/auth/user-info"
        
        # 使用当前请求的token
        token = request.headers.get("Authorization", "")
        
        response = requests.get(
            url,
            headers={"Authorization": token},
            params={"username": username},
            timeout=3.0
        )
        
        if response.status_code == 200:
            data = response.json()
            role = data.get("role", "").lower()
            logger.info(f"[Auth] 从Spring Boot获取用户角色: {username} -> {role}")
            return role
        else:
            logger.warning(f"[Auth] 获取用户角色失败: HTTP {response.status_code}")
            return ""
    except Exception as e:
        logger.error(f"[Auth] 获取用户角色异常: {e}")
        return ""

def require_admin_or_super(f):
    """
    要求管理员或超级管理员权限
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            user_role = ""
            username = ""
            
            # 方式1: 从Flask g对象获取（如果使用了auth_decorator）
            if hasattr(g, 'username'):
                username = g.username
                logger.info(f"[Auth] 从g对象获取用户名: {username}")
                
                # 尝试从g对象获取角色
                if hasattr(g, 'role'):
                    user_role = getattr(g, 'role', '').lower()
                    logger.info(f"[Auth] 从g对象获取角色: {user_role}")
                else:
                    # 从Spring Boot获取角色
                    user_role = _get_user_role_from_spring(username)
            
            # 方式2: 从请求头获取
            if not user_role:
                user_role = request.headers.get('X-User-Role', '').lower()
                username = request.headers.get('X-User-Name', username)
                if user_role:
                    logger.info(f"[Auth] 从请求头获取角色: {user_role}")
            
            # 方式3: 从请求体获取（如果是POST请求）
            if not user_role and request.method == 'POST':
                data = request.get_json() or {}
                user_role = data.get('role', '').lower()
                username = data.get('user', data.get('username', username))
                if user_role:
                    logger.info(f"[Auth] 从请求体获取角色: {user_role}")
            
            # 检查权限
            logger.info(f"[Auth] 权限检查: 用户={username}, 角色={user_role}")
            
            if user_role not in ['admin', 'super_admin', 'superadmin', 'super admin']:
                logger.warning(f"[Auth] 权限不足: 用户={username}, 角色={user_role}, 需要admin或super_admin")
                return jsonify({
                    "ok": False,
                    "msg": f"权限不足，仅管理员和超级管理员可以执行此操作（当前角色: {user_role}）"
                }), 403
            
            logger.info(f"[Auth] 权限检查通过: 用户={username}, 角色={user_role}")
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"[Auth] 权限检查失败: {e}", exc_info=True)
            return jsonify({
                "ok": False,
                "msg": f"权限验证失败: {str(e)}"
            }), 500
    
    return decorated_function

def get_current_user():
    """
    获取当前用户信息
    """
    try:
        username = ""
        user_role = ""
        
        # 方式1: 从Flask g对象获取
        if hasattr(g, 'username'):
            username = g.username
            if hasattr(g, 'role'):
                user_role = getattr(g, 'role', '').lower()
            else:
                # 从Spring Boot获取角色
                user_role = _get_user_role_from_spring(username)
        
        # 方式2: 从请求头获取
        if not username:
            username = request.headers.get('X-User-Name', '')
            user_role = request.headers.get('X-User-Role', '').lower()
        
        # 方式3: 从请求体获取
        if not username and request.method == 'POST':
            data = request.get_json() or {}
            username = data.get('user', data.get('username', ''))
            user_role = data.get('role', '').lower()
        
        return {
            "username": username or "unknown",
            "role": user_role or "user"
        }
    except Exception as e:
        logger.error(f"[Auth] 获取用户信息失败: {e}")
        return {
            "username": "unknown",
            "role": "user"
        }
