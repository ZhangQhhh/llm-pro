# 学生ID与用户名关联说明

## 概述

成绩报告中的"学生ID"现在已经与登录用户名关联，不再显示为匿名的"anonymous"。

## 修改内容

### 前端修改 (ExamView.vue)

在学生开始考试时，将登录用户名作为 `student_id` 传递给后端：

```javascript
// 开始考试
const startData = await mcqFetch(API_ENDPOINTS.EXAM.START, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    paper_id: selectedPaperId.value,
    duration_sec: durationMin.value * 60,
    student_id: store.state.user.username || 'anonymous'  // ✅ 传递用户名
  })
})
```

### 后端接收 (routes/mcq_public_routes.py)

后端已经正确接收并处理 `student_id` 参数：

```python
@mcq_public_bp.route("/exam/start", methods=["POST"])
def exam_start_api():
    """开始考试，创建考试会话"""
    data = request.get_json() or {}
    paper_id = data.get("paper_id")
    duration_sec = data.get("duration_sec", 1800)  # 默认30分钟
    student_id = data.get("student_id", "anonymous")  # ✅ 接收用户名
    
    if not paper_id:
        return jsonify({"ok": False, "detail": "缺少参数 paper_id"}), 400
    
    try:
        result = exam_start(paper_id, duration_sec, student_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"[Exam] 开始考试失败: {e}", exc_info=True)
        return jsonify({"ok": False, "detail": str(e)}), 500
```

### 后端存储 (services/exam_service.py)

考试会话中保存用户名：

```python
def exam_start(paper_id: str, duration_sec: int, student_id: str = "anonymous") -> Dict[str, Any]:
    """
    开始考试，创建考试会话
    """
    # ... 省略其他代码 ...
    
    attempt = {
        "attempt_id": attempt_id,
        "paper_id": paper_id,
        "student_id": student_id,  # ✅ 保存用户名
        "duration_sec": duration_sec,
        "start_time": now,
        "end_time": None,
        "status": "in_progress",
        "questions": questions,
        "answers": [],
        "total_score": 0
    }
    
    # ... 保存到 exam_attempts.json ...
```

## 数据流转

```
1. 学生登录
   ↓ (用户名存储在 store.state.user.username)
2. 选择试卷并开始考试
   ↓ (前端发送 student_id: username)
3. 后端创建考试会话
   ↓ (保存 student_id 到 exam_attempts.json)
4. 学生答题并提交
   ↓ (会话中已有 student_id)
5. 生成成绩报告
   ↓ (使用 student_id 作为学生姓名)
6. 报告中显示真实用户名
   ✅ (不再是 "anonymous")
```

## 成绩报告中的显示

### 单个学生报告 (DOCX)

```
考试成绩报告

学生ID: zhangsan          ← ✅ 显示真实用户名
试卷: 期末考试
开始时间: 2025-11-21 23:00:00
结束时间: 2025-11-21 23:30:00
总分: 85.00

答题详情
...
```

### 批量报告 (ZIP)

ZIP文件中每个学生的报告文件名：
```
成绩报告_zhangsan_abc12345.docx    ← ✅ 文件名包含用户名
成绩报告_lisi_def67890.docx
成绩报告_wangwu_ghi11121.docx
```

### 成绩汇总表 (DOCX)

```
考试成绩汇总表

试卷名称: 期末考试
考试人数: 3

学生ID    | Q1  | Q2  | Q3  | ... | 总分
---------|-----|-----|-----|-----|------
zhangsan | A ✓ | B ✓ | C ✗ | ... | 85.00   ← ✅ 显示用户名
lisi     | B ✓ | A ✗ | C ✓ | ... | 75.00
wangwu   | A ✓ | B ✓ | C ✓ | ... | 95.00
```

## 用户信息来源

### 前端 Vuex Store

```javascript
// store/index.ts
state: {
  user: {
    id: '...',
    username: 'zhangsan',  // ✅ 用户名
    email: 'zhangsan@example.com',
    role: 'user'
  }
}
```

### 获取用户名

```javascript
// ExamView.vue
const store = useStore()
const username = computed(() => store.state.user.username || '学生')

// 使用
store.state.user.username  // 'zhangsan'
```

## 兼容性处理

### 未登录用户

如果用户未登录或用户名为空，系统会使用默认值 `"anonymous"`：

```javascript
student_id: store.state.user.username || 'anonymous'
```

### 旧数据

对于之前创建的考试会话（`student_id` 为 `"anonymous"`），报告中仍会显示 `"anonymous"`。这是正常的，因为当时没有记录用户名。

## 测试建议

### 功能测试

1. **登录并开始考试**
   - 使用不同的用户账号登录
   - 开始考试
   - 检查 `exam_attempts.json` 中的 `student_id` 是否为用户名

2. **生成成绩报告**
   - 完成考试并提交
   - 导出个人成绩报告
   - 检查报告中的"学生ID"是否显示为用户名

3. **批量导出**
   - 多个学生完成同一试卷
   - 管理员导出ZIP
   - 检查文件名和报告内容是否包含正确的用户名

4. **成绩汇总表**
   - 管理员导出成绩汇总DOCX
   - 检查表格中的"学生ID"列是否显示用户名

### 数据验证

检查 `exam_attempts.json` 文件：

```json
{
  "attempts": [
    {
      "attempt_id": "abc123...",
      "paper_id": "期末考试_1234567890.docx",
      "student_id": "zhangsan",  // ✅ 应该是用户名，不是 "anonymous"
      "duration_sec": 1800,
      "start_time": "2025-11-21 23:00:00",
      "status": "completed",
      "total_score": 85.0,
      ...
    }
  ]
}
```

## 常见问题

### Q1: 为什么有些报告显示 "anonymous"？
**A**: 这些是在修改前创建的考试会话，当时没有记录用户名。新的考试会话会正确显示用户名。

### Q2: 如果用户修改了用户名怎么办？
**A**: 考试会话中保存的是开始考试时的用户名，即使用户后来修改了用户名，报告中仍会显示原来的用户名。这是合理的，因为报告应该反映考试时的真实情况。

### Q3: 能否显示学生的真实姓名而不是用户名？
**A**: 可以。如果用户表中有真实姓名字段（如 `real_name`），可以修改前端传递 `real_name` 而不是 `username`。或者在后端根据 `username` 查询真实姓名。

### Q4: 多个学生使用同一个账号怎么办？
**A**: 不建议这样做。每个学生应该有独立的账号。如果确实需要，可以在开始考试时让学生输入姓名，而不是使用登录用户名。

## 扩展功能建议

### 1. 显示更多学生信息

可以在报告中显示更多信息：

```python
# 在 exam_start 时传递更多信息
{
  "student_id": username,
  "student_name": real_name,      # 真实姓名
  "student_email": email,         # 邮箱
  "student_class": class_name     # 班级
}

# 报告中显示
学生姓名: 张三
学生账号: zhangsan
邮箱: zhangsan@example.com
班级: 计算机2023-1班
```

### 2. 防止作弊

记录更多信息以防止作弊：

```python
{
  "student_id": username,
  "ip_address": request.remote_addr,  # IP地址
  "user_agent": request.user_agent,   # 浏览器信息
  "session_id": session_id            # 会话ID
}
```

### 3. 学号支持

如果学生有学号，可以使用学号作为主要标识：

```python
{
  "student_id": student_number,       # 学号
  "student_name": real_name,          # 姓名
  "username": username                # 登录账号
}
```

## 总结

✅ 学生ID现在已经与登录用户名关联  
✅ 成绩报告中显示真实用户名而不是 "anonymous"  
✅ 文件名也包含用户名，便于识别  
✅ 兼容旧数据（显示为 "anonymous"）  
✅ 支持未登录用户（使用默认值）  

现在成绩报告更加规范和实用了！
