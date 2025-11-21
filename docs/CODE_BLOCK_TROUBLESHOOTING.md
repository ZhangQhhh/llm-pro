# 代码块符号问题排查指南

## 🐛 问题现象

前端显示黑色代码框，正常文本被渲染成代码样式。

![问题截图](示例：黑色背景的代码框包裹正常文本)

---

## ✅ 排查步骤

### 1. 确认代码已修改

检查 `utils/knowledge_utils/llm_stream_parser.py` 是否包含 `_remove_code_blocks` 函数：

```bash
grep -n "_remove_code_blocks" utils/knowledge_utils/llm_stream_parser.py
```

**期望输出**:
```
10:def _remove_code_blocks(text: str) -> str:
88:    cleaned_content = _remove_code_blocks(content_buffer)
...
```

---

### 2. **重启应用（最重要！）**

**Python 代码修改后必须重启才能生效！**

```bash
# 1. 停止应用
Ctrl+C  # 或 kill <PID>

# 2. 重新启动
cd /opt/rag_final_project/code_here/llmV27
python app.py
```

**验证启动成功**:
```
✅ 应用启动成功
✅ 监听端口: 8000
```

---

### 3. 清除前端缓存

**浏览器缓存可能导致旧代码仍在运行！**

#### Chrome/Edge:
1. 按 `F12` 打开开发者工具
2. 右键点击刷新按钮
3. 选择 **"清空缓存并硬性重新加载"**

#### 或者:
1. `Ctrl + Shift + Delete`
2. 选择 **"缓存的图片和文件"**
3. 点击 **"清除数据"**

---

### 4. 检查日志输出

启用 DEBUG 日志，查看是否有代码块过滤记录：

```bash
# 修改 .env 或环境变量
export LOG_LEVEL=DEBUG

# 重启应用
python app.py
```

**期望日志**:
```
[代码块过滤] 原文: '```核验1. Q2签证...'
[代码块过滤] 过滤后: '核验1. Q2签证...'
```

如果**没有看到这个日志**，说明：
- 应用没有重启
- 代码没有被调用
- 代码块符号在其他地方生成

---

### 5. 测试过滤函数

运行测试脚本验证过滤功能：

```bash
cd /opt/rag_final_project/code_here/llmV27
python tests/test_code_block_filter.py
```

**期望输出**:
```
================================================================================
测试结果: 8 通过, 0 失败
================================================================================
```

---

### 6. 检查前端代码

如果后端已经过滤，但前端仍显示代码框，可能是**前端 Markdown 渲染问题**。

检查前端是否有额外的代码块符号添加逻辑：

```javascript
// 前端可能的问题代码
content = "```\n" + content + "\n```";  // ❌ 不要这样做
```

---

## 🔧 完整修复流程

### Step 1: 确认后端修改
```bash
# 检查文件是否已修改
ls -lh utils/knowledge_utils/llm_stream_parser.py
```

### Step 2: 重启应用
```bash
# 停止
ps aux | grep app.py
kill <PID>

# 启动
python app.py
```

### Step 3: 清除前端缓存
- 浏览器: `Ctrl + Shift + Delete`
- 或硬性刷新: `Ctrl + F5`

### Step 4: 测试
1. 提问: "J2签证申请流程"
2. 观察回答是否有黑色代码框
3. 检查日志是否有过滤记录

---

## 🎯 常见原因

| 原因 | 解决方法 |
|------|---------|
| **应用未重启** | `Ctrl+C` 停止，重新 `python app.py` |
| **前端缓存** | 清空缓存并硬性重新加载 |
| **代码未同步** | 确认服务器文件已更新 |
| **LLM 输出新符号** | 检查日志，添加新的过滤规则 |
| **前端添加符号** | 检查前端 JavaScript 代码 |

---

## 📊 调试技巧

### 1. 实时查看日志
```bash
tail -f logs/app.log | grep "代码块过滤"
```

### 2. 抓取 SSE 消息
```bash
# 使用 curl 测试 SSE 接口
curl -N http://localhost:8000/api/knowledge/query \
  -H "Content-Type: application/json" \
  -d '{"question":"J2签证申请"}'
```

### 3. 检查原始输出
在 `llm_stream_parser.py` 中添加日志：
```python
logger.info(f"[原始输出] {repr(text[:200])}")
```

---

## ✅ 验证成功标志

1. **日志中看到**:
   ```
   [代码块过滤] 原文: '```...'
   [代码块过滤] 过滤后: '...'
   ```

2. **前端显示**:
   - ✅ 正常文本（白色背景）
   - ❌ 黑色代码框

3. **测试通过**:
   ```
   测试结果: 8 通过, 0 失败
   ```

---

## 🆘 如果仍然失败

### 1. 检查 LLM 输出原文
添加日志查看 LLM 原始输出：
```python
logger.info(f"[LLM原始输出] {repr(delta.content)}")
```

### 2. 检查是否有其他符号
可能是其他 Markdown 符号导致代码框：
- ` ~~~ ` (波浪线代码块)
- 4个空格缩进
- Tab 缩进

### 3. 联系支持
提供以下信息：
- 完整日志
- 前端截图
- LLM 原始输出
- 浏览器版本

---

## 📝 相关文档

- `docs/CODE_BLOCK_FILTER_FIX.md` - 修复说明
- `tests/test_code_block_filter.py` - 测试脚本
- `utils/knowledge_utils/llm_stream_parser.py` - 过滤实现
