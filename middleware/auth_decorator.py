# -*- coding: utf-8 -*-
"""
Flask 鉴权装饰器 - 通过 Spring Boot 后端验证 JWT Token
"""
import requests
import logging
import os
from functools import wraps
from flask import request, jsonify, g
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class AuthManager:
    """JWT 鉴权管理器"""

    def __init__(self, spring_boot_url: str):
        """
        Args:
            spring_boot_url: Spring Boot 认证服务的基础 URL
                            例如: "http://localhost:8080"
        """
        self.spring_boot_url = spring_boot_url.rstrip('/')
        self.validate_url = f"{self.spring_boot_url}/api/auth/validate-token"

        # Token 验证结果缓存(避免频繁调用 Spring Boot)
        # 格式: {token: {"username": str, "userid": int, "expire_time": datetime}}
        self._token_cache: Dict[str, Dict] = {}
        self._cache_ttl = timedelta(minutes=5)  # 缓存 5 分钟

        logger.info(f"AuthManager 初始化完成，Spring Boot URL: {self.spring_boot_url}")

    def _extract_token(self) -> Optional[str]:
        """从请求中提取 JWT token"""
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return None

        # 支持 "Bearer <token>" 格式
        if auth_header.startswith("Bearer "):
            return auth_header[7:]

        return auth_header

    def _validate_token(self, token: str) -> Optional[Dict]:
        """
        验证 token 有效性
        Returns:
            dict: {"username": str, "userid": int} (验证成功)
            None: 验证失败
        """
        # 1. 检查缓存
        cached = self._get_from_cache(token)
        if cached:
            logger.debug(f"Token 验证命中缓存: {cached['username']}")
            return cached

        # 2. 调用 Spring Boot 验证接口
        try:
            response = requests.post(
                self.validate_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("valid"):
                    user_info = {
                        "username": data.get("username"),
                        "userid": data.get("userid")
                    }
                    # 存入缓存
                    self._put_to_cache(token, user_info)
                    logger.info(f"Token 验证成功: 用户 {user_info['username']} (ID: {user_info['userid']})")
                    return user_info
                else:
                    error_msg = data.get("error", "未知错误")
                    logger.warning(f"Token 验证失败: {error_msg}")
                    return None
            else:
                logger.warning(f"Token 验证请求失败: {response.status_code}")
                return None

        except requests.Timeout:
            logger.error(f"Token 验证超时: Spring Boot 服务 {self.validate_url} 无响应")
            return None
        except Exception as e:
            logger.error(f"Token 验证异常: {e}")
            return None

    def _get_from_cache(self, token: str) -> Optional[Dict]:
        """从缓存获取 token 验证结果"""
        if token in self._token_cache:
            cached_data = self._token_cache[token]
            if datetime.now() < cached_data["expire_time"]:
                return {
                    "username": cached_data["username"],
                    "userid": cached_data["userid"]
                }
            else:
                # 缓存过期，删除
                del self._token_cache[token]
        return None

    def _put_to_cache(self, token: str, user_info: Dict):
        """将 token 验证结果存入缓存"""
        expire_time = datetime.now() + self._cache_ttl
        self._token_cache[token] = {
            "username": user_info["username"],
            "userid": user_info["userid"],
            "expire_time": expire_time
        }

        # 定期清理过期缓存(简单实现)
        if len(self._token_cache) > 1000:
            self._clean_expired_cache()

    def _clean_expired_cache(self):
        """清理过期的缓存条目"""
        now = datetime.now()
        expired_tokens = [
            token for token, data in self._token_cache.items()
            if now >= data["expire_time"]
        ]
        for token in expired_tokens:
            del self._token_cache[token]
        logger.info(f"清理了 {len(expired_tokens)} 个过期 token 缓存")

    def require_auth(self, f):
        """
        装饰器: 要求请求必须携带有效的 JWT token

        使用方法:
            @app.route('/api/protected')
            @auth_manager.require_auth
            def protected_route():
                username = g.username  # 获取当前用户名
                userid = g.userid      # 获取当前用户ID
                return {"message": f"Hello, {username}"}
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. 提取 token
            token = self._extract_token()
            if not token:
                logger.warning(f"请求 {request.path} 缺少 Authorization header | IP: {request.remote_addr}")
                return jsonify({"detail": "未提供认证令牌"}), 401

            # 2. 验证 token
            user_info = self._validate_token(token)
            if not user_info:
                logger.warning(f"Token 验证失败: {token[:20]}... | IP: {request.remote_addr}")
                return jsonify({"detail": "认证令牌无效或已过期"}), 401

            # 3. 将用户信息注入到 Flask g 对象
            g.username = user_info["username"]
            g.userid = user_info["userid"]
            g.token = token

            logger.debug(f"用户 {g.username} (ID: {g.userid}) 已通过认证，访问 {request.path}")

            # 4. 继续执行原函数
            return f(*args, **kwargs)

        return decorated_function

    def optional_auth(self, f):
        """
        装饰器: 可选认证(如果有 token 则验证,没有也允许访问)

        使用方法:
            @app.route('/api/public')
            @auth_manager.optional_auth
            def public_route():
                username = getattr(g, 'username', None)
                if username:
                    return {"message": f"Hello, {username}"}
                else:
                    return {"message": "Hello, guest"}
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            token = self._extract_token()
            if token:
                user_info = self._validate_token(token)
                if user_info:
                    g.username = user_info["username"]
                    g.userid = user_info["userid"]
                    g.token = token
                    logger.debug(f"用户 {g.username} 已通过认证(可选)")
                else:
                    logger.debug("Token 验证失败,但允许访问(可选认证)")
            else:
                logger.debug("未提供 token,但允许访问(可选认证)")

            return f(*args, **kwargs)

        return decorated_function


# 工厂函数: 从环境变量创建认证管理器
def create_auth_manager() -> AuthManager:
    """
    创建 AuthManager 实例的工厂函数

    Returns:
        AuthManager: 鉴权管理器实例
    """
    spring_boot_url = os.getenv('SPRING_BOOT_URL', 'http://localhost:8080')
    return AuthManager(spring_boot_url)
