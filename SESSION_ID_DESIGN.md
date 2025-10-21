# Session ID 与 User ID 关联方案说明

## 方案概述

本方案通过将 `user_id` 编码到 `session_id` 中，实现了会话与用户的关联，格式为：`{user_id}_{uuid}`

## 实现细节

### 1. Session ID 格式

- **新格式**：`{user_id}_{uuid}` (例如: `123_a1b2c3d4-e5f6-7890-abcd-ef1234567890`)
- **旧格式**：纯 UUID (例如: `a1b2c3d4-e5f6-7890-abcd-ef1234567890`) - 向后兼容

### 2. 核心功能模块

#### `utils/session_helper.py` - 会话辅助函数

提供了以下核心函数：

1. **`generate_session_id(user_id: int) -> str`**
   - 生成与用户关联的会话ID
   - 自动附加用户ID前缀

2. **`parse_session_id(session_id: str) -> Optional[Tuple[int, str]]`**
   - 解析会话ID，提取用户ID和UUID部分
   - 返回 `(user_id, uuid)` 元组

3. **`validate_session_ownership(session_id: str, user_id: int) -> bool`**
   - 验证会话是否属于指定用户
   - 自动兼容旧格式（返回 True 但记录警告）

4. **`get_user_id_from_session(session_id: str) -> Optional[int]`**
   - 从会话ID中提取用户ID
   - 便于快速查询会话所属用户

5. **`is_legacy_session_id(session_id: str) -> bool`**
   - 检查是否为旧格式会话ID

### 3. 路由层实现

在 `routes/knowledge_routes.py` 中：

```python
# 创建新会话
if not session_id:
    session_id = generate_session_id(userid)
    logger.info(f"用户 {username} (ID: {userid}) 创建新会话: {session_id}")
else:
    # 验证会话所有权
    if not validate_session_ownership(session_id, userid):
        return jsonify({
            "type": "error",
            "content": "无权访问该会话"
        }), 403
```

## 优势

1. **无需额外存储**：直接从 session_id 解析出 user_id，不需要维护映射表
2. **安全性提升**：防止用户访问其他用户的会话
3. **向后兼容**：旧格式的 session_id 仍然可以使用
4. **便于追踪**：可以快速定位会话所属用户
5. **便于清理**：可以按用户批量清理会话

## 使用示例

### 前端调用示例

```javascript
// 首次请求（不提供 session_id）
const response1 = await fetch('/api/knowledge_chat_conversation', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer your_token_here',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    question: "你好",
    thinking: true,
    model_id: "qwen3-32b"
  })
});

// 后续请求（使用返回的 session_id）
const response2 = await fetch('/api/knowledge_chat_conversation', {
  method: 'POST',
  headers: {
    'Authorization': 'Bearer your_token_here',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    question: "继续上一个问题",
    session_id: "123_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    thinking: true,
    model_id: "qwen3-32b"
  })
});
```

### 后端查询示例

```python
from utils import get_user_id_from_session

# 从会话ID获取用户ID
session_id = "123_a1b2c3d4-e5f6-7890-abcd-ef1234567890"
user_id = get_user_id_from_session(session_id)  # 返回 123

# 验证会话所有权
if validate_session_ownership(session_id, 123):
    print("会话属于用户 123")
```

## 安全考虑

1. **认证检查**：所有需要 session_id 的接口都必须先通过 JWT 认证
2. **所有权验证**：每次使用 session_id 时都会验证是否属于当前用户
3. **日志记录**：记录所有会话访问和权限拒绝事件
4. **旧格式处理**：旧格式会话ID会被标记警告，建议逐步迁移

## 迁移建议

1. **新用户**：自动使用新格式
2. **老用户**：
   - 旧会话ID继续可用（向后兼容）
   - 创建新会话时使用新格式
   - 可以设置定期清理策略，逐步淘汰旧格式

## 扩展功能

基于这个方案，可以轻松实现：

1. **用户会话列表**：查询特定用户的所有会话
2. **批量清理**：清理特定用户的所有会话
3. **会话统计**：按用户统计会话使用情况
4. **权限控制**：更精细的会话访问控制

## 日志示例

```
[INFO] 用户 zhangsan (ID: 123) 创建新会话: 123_a1b2c3d4-e5f6-7890-abcd-ef1234567890
[INFO] 用户 zhangsan (ID: 123) | 会话 123_a1b2... | 模型: 'qwen3-32b' | InsertBlock: False
[WARNING] 用户 lisi (ID: 456) 尝试访问其他用户的会话: 123_a1b2c3d4-e5f6-7890-abcd-ef1234567890
[WARNING] 检测到旧格式 session_id: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

