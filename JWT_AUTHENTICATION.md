# JWT 鉴权功能说明文档

## 📋 功能概述

本系统已实现基于 Spring Boot 后端的 JWT Token 鉴权功能，支持：
- ✅ Token 验证（调用 Java 后端接口）
- ✅ Token 缓存（5分钟缓存，减少后端压力）
- ✅ 用户信息注入（username, userid）
- ✅ 路由级别的认证钩子
- ✅ 装饰器模式的认证（可选）

---

## 🔧 配置说明

### 1. 环境变量配置

在项目根目录的 `.env` 文件中配置 Spring Boot 后端地址：

```bash
# Spring Boot 认证服务的基础 URL
SPRING_BOOT_URL=http://localhost:3000
```

**注意**：如果你的 Java 后端部署在其他地址，请修改此配置。

### 2. 依赖安装

确保已安装 `requests` 库：

```bash
pip install requests
```

或使用 requirements.txt 安装：

```bash
pip install -r requirements.txt
```

---

## 🔐 鉴权实现方式

### 方式一：蓝图级别的认证钩子（当前使用）

`routes/knowledge_routes.py` 中使用了 `@knowledge_bp.before_request` 钩子：

- **所有路由默认需要认证**
- **白名单机制**：部分路由可免认证

```python
# 白名单路径配置
whitelist_paths = [
    '/api/health',
    '/api/test',
]
```

**当前受保护的接口**：
- ✅ `/api/knowledge_chat_conversation` - 多轮对话接口
- ✅ `/api/knowledge_chat` - 单轮问答接口
- ✅ `/api/conversation/clear` - 清空会话
- ✅ `/api/conversation/statistics` - 获取会话统计
- ✅ `/api/conversation/cache/clear` - 清空缓存

---

## 📡 Java 后端接口要求

### 接口信息

```
POST /auth/api/validate-token
Header: Authorization: Bearer <token>
```

### 预期响应格式

**成功响应（200 OK）**：
```json
{
  "valid": true,
  "username": "张三",
  "userid": 12345
}
```

**失败响应（200 OK）**：
```json
{
  "valid": false,
  "error": "Token 已过期"
}
```

**其他状态码**：
- `401` - 未授权
- `403` - 禁止访问
- `500` - 服务器错误

---

## 🧪 测试方法

### 1. 测试无 Token 访问（应该被拒绝）

```bash
curl -X POST http://localhost:5000/api/knowledge_chat_conversation \
  -H "Content-Type: application/json" \
  -d '{"question": "测试问题"}'
```

**预期响应**：
```json
{
  "detail": "未提供认证令牌"
}
```
**状态码**：401

### 2. 测试有效 Token 访问

```bash
curl -X POST http://localhost:5000/api/knowledge_chat_conversation \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_VALID_TOKEN" \
  -d '{
    "question": "什么是人工智能?",
    "session_id": "test-session-123"
  }'
```

**预期响应**：正常返回 SSE 流式数据

### 3. 测试无效 Token 访问

```bash
curl -X POST http://localhost:5000/api/knowledge_chat_conversation \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer INVALID_TOKEN_12345" \
  -d '{"question": "测试问题"}'
```

**预期响应**：
```json
{
  "detail": "认证令牌无效或已过期"
}
```
**状态码**：401

---

## 📊 用户信息获取

在受保护的路由中，可通过 Flask 的 `g` 对象获取当前用户信息：

```python
from flask import g

@knowledge_bp.route('/my-route', methods=['POST'])
def my_route():
    # 获取当前用户信息（由认证钩子自动注入）
    username = g.username  # 用户名
    userid = g.userid      # 用户ID
    token = g.token        # 原始 Token
    
    logger.info(f"用户 {username} (ID: {userid}) 访问了此接口")
    # ...业务逻辑
```

**示例**（已在 `knowledge_chat_conversation` 中使用）：
```python
username = g.get('username', 'unknown')
userid = g.get('userid', 0)

logger.info(f"用户 {username} (ID: {userid}) | 会话 {session_id[:8]}...")
```

---

## 🔄 Token 缓存机制

为了减少对 Spring Boot 后端的频繁请求，系统实现了 Token 缓存：

- **缓存时间**：5 分钟
- **缓存容量**：1000 个 Token（超过会自动清理过期缓存）
- **缓存内容**：`{username, userid, expire_time}`

**缓存逻辑**：
1. 首次验证：调用 Spring Boot 接口 → 存入缓存
2. 5分钟内再次请求：直接从缓存获取（不调用后端）
3. 超过5分钟：重新调用 Spring Boot 接口验证

---

## 🛡️ 白名单配置

如果需要某些接口**不需要认证**，请在 `knowledge_routes.py` 中添加到白名单：

```python
whitelist_paths = [
    '/api/health',        # 健康检查
    '/api/test',          # 测试接口
    '/api/public_api',    # 新增的公开接口
]
```

---

## 🎯 方式二：装饰器模式（可选使用）

如果希望在单个路由上使用装饰器，可以这样做：

```python
from flask import current_app, g

@knowledge_bp.route('/protected-route', methods=['POST'])
def protected_route():
    # 手动获取 auth_manager
    auth_manager = current_app.extensions.get('auth_manager')
    
    # 使用装饰器函数
    @auth_manager.require_auth
    def inner_handler():
        username = g.username
        return {"message": f"Hello, {username}"}
    
    return inner_handler()
```

**或者直接使用装饰器**：
```python
@app.route('/api/admin/stats')
@auth_manager.require_auth  # 需要认证
def admin_stats():
    return {"stats": "..."}

@app.route('/api/public/info')
@auth_manager.optional_auth  # 可选认证
def public_info():
    username = getattr(g, 'username', None)
    if username:
        return {"message": f"Hello, {username}"}
    else:
        return {"message": "Hello, guest"}
```

---

## 📝 日志说明

### 成功认证日志
```
INFO - Token 验证成功: 用户 张三 (ID: 12345)
DEBUG - 用户 张三 (ID: 12345) 已通过认证，访问 /api/knowledge_chat_conversation
```

### 认证失败日志
```
WARNING - 请求 /api/knowledge_chat 缺少 Authorization header | IP: 192.168.1.100
WARNING - Token 验证失败: eyJhbGciOiJIUzI1Ni... | IP: 192.168.1.100
```

### 缓存命中日志
```
DEBUG - Token 验证命中缓存: 张三
```

---

## ⚠️ 注意事项

1. **确保 Spring Boot 服务可访问**：
   - Flask 服务需要能访问到 `SPRING_BOOT_URL` 配置的地址
   - 网络防火墙/安全组需要开放相应端口

2. **超时设置**：
   - Token 验证请求超时时间为 5 秒
   - 如果后端响应慢，可在 `auth_decorator.py` 中调整 `timeout=5.0`

3. **错误处理**：
   - 如果 Spring Boot 服务不可用，Token 验证会失败（返回 401）
   - 生产环境建议添加降级策略或熔断机制

4. **HTTPS 建议**：
   - 生产环境建议使用 HTTPS 传输 Token
   - 避免 Token 在网络中明文传输

---

## 🚀 快速检查清单

- [x] `middleware/auth_decorator.py` - 认证管理器已实现
- [x] `routes/knowledge_routes.py` - 认证钩子已添加
- [x] `app.py` - 认证管理器已注册
- [x] `.env` - Spring Boot URL 已配置
- [x] `requirements.txt` - requests 库已添加

**部署前检查**：
```bash
# 1. 检查环境变量
cat .env | grep SPRING_BOOT_URL

# 2. 测试 Spring Boot 接口连通性
curl -X POST http://localhost:8080/auth/api/validate-token \
  -H "Authorization: Bearer test_token"

# 3. 安装依赖
pip install -r requirements.txt

# 4. 启动 Flask 服务
python app.py
```

---

## 📞 问题排查

### 问题 1：认证管理器未初始化
**错误**：`认证管理器未初始化`
**解决**：检查 `app.py` 中是否正确注册了 `auth_manager`

### 问题 2：Token 验证超时
**错误**：`Token 验证超时: Spring Boot 服务 xxx 无响应`
**解决**：
1. 检查 Spring Boot 服务是否启动
2. 检查网络连通性
3. 检查防火墙配置

### 问题 3：所有请求都返回 401
**原因**：可能是测试接口也被拦截了
**解决**：将测试接口添加到白名单

---

## 📌 总结

✅ **鉴权功能已完整实现**，包括：
- Token 验证逻辑
- 缓存优化机制
- 路由级别保护
- 用户信息注入
- 完善的日志记录

✅ **与 Java 后端对接规范清晰**：
- POST `/auth/api/validate-token`
- 返回格式：`{valid, username, userid}`

✅ **开箱即用**，只需配置 `SPRING_BOOT_URL` 环境变量即可。

