# 子问题分解与答案生成完整指南

## 功能概述

子问题分解后，系统会：
1. **为每个子问题调用 LLM 生成答案**（基于检索到的上下文）
2. **将子问题和答案注入到最终答案的上下文中**
3. **将子问题和答案返回给前端显示**

---

## 完整流程

```
用户提问
  ↓
意图分类（选择知识库）
  ↓
子问题分解（LLM 判断是否需要分解）
  ↓
并行检索每个子问题
  ↓
【为每个子问题生成答案】← 新增：调用 LLM
  ↓
【保存子问题答案】← 用于注入上下文
  ↓
【发送子问题和答案到前端】← SSE 流式传输
  ↓
【注入子问题答案到上下文】← 生成最终答案时使用
  ↓
LLM 生成完整答案（基于检索文档 + 子问题答案）
  ↓
流式返回给前端
```

---

## 核心实现

### 1. 子问题答案生成

**位置**：`core/sub_question_decomposer.py` - `_generate_sub_answer()` 方法

**功能**：为每个子问题调用 LLM 生成答案

```python
def _generate_sub_answer(self, sub_question: str, nodes: List) -> str:
    """
    为单个子问题生成答案（基于检索上下文）
    
    Args:
        sub_question: 子问题
        nodes: 检索到的节点列表（top 3）
        
    Returns:
        LLM 生成的答案
    """
    # 1. 构建上下文（使用 top 3 检索节点）
    context_parts = []
    for i, node in enumerate(nodes[:3], 1):
        content = node.node.get_content()
        context_parts.append(f"[参考资料{i}]\n{content}\n")
    
    context = "\n".join(context_parts)
    
    # 2. 调用 LLM 生成答案
    system_prompt = get_sub_answer_generation_system()
    user_prompt = get_sub_answer_generation_user(sub_question, context)
    
    answer = self._call_llm_with_timeout(
        llm,
        system_prompt,
        user_prompt,
        timeout=15  # 15秒超时
    )
    
    return answer.strip()
```

**提示词**（`prompts.py`）：
```python
def get_sub_answer_generation_system():
    return [
        "你是一名专业的问答助手。",
        "你的任务是根据提供的参考资料，简洁准确地回答问题。",
        "回答要求：",
        "1. 仅基于提供的参考资料回答，不要编造信息",
        "2. 回答要简洁明了，直接回答问题核心",
        "3. 如果参考资料中没有相关信息，明确说明",
        "4. 回答长度控制在 100-200 字以内",
        "/no_think"
    ]
```

---

### 2. 子问题答案注入上下文

**位置**：`api/knowledge_handler.py` - `_build_prompt()` 方法

**功能**：将子问题答案注入到最终答案生成的上下文中

```python
# 如果有子问题答案，添加到上下文中
if hasattr(self, '_last_sub_answers') and self._last_sub_answers:
    sub_answers_block = "\n\n### 📋 子问题分解与回答:\n"
    for i, sub_answer in enumerate(self._last_sub_answers, 1):
        sub_q = sub_answer.get('sub_question', '')
        answer = sub_answer.get('answer', '')
        sub_answers_block += f"\n**子问题{i}**: {sub_q}\n**回答{i}**: {answer}\n"
    
    sub_answers_block += "\n**注意**: 以上是各子问题的独立回答，请结合这些信息和业务规定给出完整答案。"
    assistant_context += sub_answers_block
    logger.info(f"[提示词构建] 已将 {len(self._last_sub_answers)} 个子问题答案注入上下文")
```

**注入后的上下文示例**：
```
### 业务规定 1 - 文件名:
> 检索到的文档内容...

### 业务规定 2 - 文件名:
> 检索到的文档内容...

### 📋 子问题分解与回答:

**子问题1**: 中国护照去哪些国家免签？
**回答1**: 根据参考资料，中国护照可以免签进入泰国、新加坡、马来西亚等国家...

**子问题2**: 各国免签停留时间是多久？
**回答2**: 根据参考资料，泰国免签停留30天，新加坡免签停留30天...

**注意**: 以上是各子问题的独立回答，请结合这些信息和业务规定给出完整答案。
```

---

### 3. 返回给前端

**SSE 消息格式**：
```
SUB_QUESTIONS:{"sub_questions": ["子问题1", "子问题2"], "count": 2, "sub_answers": [{"sub_question": "子问题1", "answer": "LLM生成的答案1"}, {"sub_question": "子问题2", "answer": "LLM生成的答案2"}]}
```

**JSON 数据结构**：
```json
{
  "sub_questions": [
    "中国护照去哪些国家免签？",
    "各国免签停留时间是多久？"
  ],
  "count": 2,
  "sub_answers": [
    {
      "sub_question": "中国护照去哪些国家免签？",
      "answer": "根据参考资料，中国护照可以免签进入泰国、新加坡、马来西亚等国家。这些国家对中国公民实行免签政策，无需提前申请签证即可入境。"
    },
    {
      "sub_question": "各国免签停留时间是多久？",
      "answer": "根据参考资料，各国免签停留时间如下：泰国30天、新加坡30天、马来西亚30天。不同国家的免签停留期限有所不同，建议出行前确认具体要求。"
    }
  ]
}
```

---

## 日志示例

### 完整日志流程

```
[子问题分解] 智能判断模式 | 查询: 中国护照去哪些国家免签，停留时间是多久？
[子问题分解] 分解成功 | 子问题数: 2 | 子问题: ['中国护照去哪些国家免签？', '各国免签停留时间是多久？']

[子问题检索] 开始并行检索 2 个子问题

[子问题答案生成] 开始为 2 个子问题生成答案
[子问题答案] 生成成功: 中国护照去哪些国家免签？... | 长度: 156
[子问题答案] 生成成功: 各国免签停留时间是多久？... | 长度: 142

[子问题检索] 分解检索完成 | 子问题数: 2 | 返回节点数: 10 | 使用库: both
[子问题答案] 已保存 2 个子问题答案，将注入上下文

[前端输出] 已发送子问题到前端 | 子问题数: 2 | 答案数: 2

[提示词构建] 已将 2 个子问题答案注入上下文

[LLM生成] 开始生成最终答案...
```

---

## 前端接收示例

```javascript
eventSource.onmessage = function(event) {
    const message = event.data;
    
    if (message.startsWith('SUB_QUESTIONS:')) {
        const jsonStr = message.substring('SUB_QUESTIONS:'.length);
        const data = JSON.parse(jsonStr);
        
        console.log('子问题:', data.sub_questions);
        console.log('答案:', data.sub_answers);
        
        // 显示子问题和答案
        displaySubQuestionsWithAnswers(data);
    }
};

function displaySubQuestionsWithAnswers(data) {
    const container = document.getElementById('sub-questions-container');
    container.innerHTML = '';
    
    // 标题
    const title = document.createElement('div');
    title.className = 'sub-questions-title';
    title.innerHTML = `<h3>📋 问题分解（共 ${data.count} 个子问题）</h3>`;
    container.appendChild(title);
    
    // 遍历子问题和答案
    data.sub_questions.forEach((question, index) => {
        const item = document.createElement('div');
        item.className = 'sub-question-item';
        
        // 子问题
        const questionDiv = document.createElement('div');
        questionDiv.className = 'sub-question';
        questionDiv.innerHTML = `<strong>${index + 1}. ${question}</strong>`;
        item.appendChild(questionDiv);
        
        // 答案（LLM 生成的）
        const answer = data.sub_answers.find(a => a.sub_question === question);
        if (answer) {
            const answerDiv = document.createElement('div');
            answerDiv.className = 'sub-answer';
            answerDiv.innerHTML = `<div class="answer-label">💡 回答：</div>${answer.answer}`;
            item.appendChild(answerDiv);
        }
        
        container.appendChild(item);
    });
}
```

---

## 配置说明

### 必需配置

```bash
# 启用子问题分解
ENABLE_SUBQUESTION_DECOMPOSITION=true

# 使用自定义引擎（必须）
SUBQUESTION_ENGINE_TYPE=custom

# 子问题答案生成超时（15秒）
# 注意：这是每个子问题的超时时间
```

### 推荐配置

```bash
# 开发环境
ENABLE_SUBQUESTION_DECOMPOSITION=true
SUBQUESTION_ENGINE_TYPE=custom
SUBQUESTION_USE_LLM_JUDGE=false  # 强制分解，方便测试
SUBQUESTION_COMPLEXITY_THRESHOLD=20
SUBQUESTION_ENABLE_ENTITY_CHECK=false
SUBQUESTION_DECOMP_LLM_ID=qwen3-32b

# 生产环境
ENABLE_SUBQUESTION_DECOMPOSITION=true
SUBQUESTION_ENGINE_TYPE=custom
SUBQUESTION_USE_LLM_JUDGE=true  # 智能判断
SUBQUESTION_COMPLEXITY_THRESHOLD=30
SUBQUESTION_ENABLE_ENTITY_CHECK=false
SUBQUESTION_DECOMP_LLM_ID=qwen3-32b
```

---

## 性能影响

### 延迟分析

| 步骤 | 时间 | 说明 |
|------|------|------|
| 子问题分解 | ~1s | LLM 判断 + 生成子问题 |
| 并行检索 | ~0.5s | 同时检索所有子问题 |
| **生成子问题答案** | **~15s × N** | **每个子问题调用 LLM（新增）** |
| 答案合成 | ~30s | 可选，整合所有子问题答案 |
| 最终答案生成 | ~5-10s | 基于上下文生成完整答案 |

**总延迟**：
- 2个子问题：~1 + 0.5 + 30 + 10 = **41.5秒**
- 3个子问题：~1 + 0.5 + 45 + 10 = **56.5秒**

### 优化建议

1. **并行生成子问题答案**（未来优化）
   - 当前：串行生成（15s × N）
   - 优化后：并行生成（15s）
   - 节省时间：(N-1) × 15s

2. **调整超时时间**
   ```bash
   # 如果答案生成经常超时
   # 修改 _generate_sub_answer 中的 timeout 参数
   timeout=20  # 从 15秒 增加到 20秒
   ```

3. **禁用答案合成**
   - 如果不需要合成答案，可以跳过这一步
   - 节省 ~30秒

---

## 常见问题

### Q1: 子问题答案是检索片段还是 LLM 生成的？

**A**: 现在是 **LLM 生成的答案**！

- **之前**：只是检索片段的前 200 字符
- **现在**：基于检索到的 top 3 节点，调用 LLM 生成简洁答案（100-200字）

### Q2: 子问题答案会注入到最终答案的上下文中吗？

**A**: 是的！会注入到 `_build_prompt` 的上下文中。

最终答案生成时，LLM 可以看到：
1. 检索到的业务规定文档
2. 各个子问题的答案
3. 子问题答案的综合分析（如果启用）

### Q3: 前端能拿到子问题的答案吗？

**A**: 能！通过 SSE 消息 `SUB_QUESTIONS` 传输。

数据包含：
- `sub_questions`: 子问题列表
- `sub_answers`: 每个子问题的 LLM 生成答案

### Q4: 如果子问题答案生成失败怎么办？

**A**: 会自动回退到检索片段。

```python
try:
    # 调用 LLM 生成答案
    sub_answer = self._generate_sub_answer(...)
    if sub_answer:
        # 使用 LLM 答案
    else:
        # 回退到检索片段
        fallback_answer = nodes[0].get_content()[:200]
except Exception as e:
    # 回退到检索片段
    fallback_answer = nodes[0].get_content()[:200]
```

### Q5: 为什么延迟这么长？

**A**: 因为需要为每个子问题调用 LLM。

**优化方案**：
1. 减少子问题数量（`SUBQUESTION_MAX_DEPTH=2`）
2. 使用更快的 LLM（如 qwen-turbo）
3. 未来实现并行生成

---

## 验证方法

### 1. 查看日志

```bash
# 启动应用
python app.py

# 发送测试请求
curl -N "http://localhost:5000/api/knowledge?question=中国护照去哪些国家免签，停留时间是多久&enable_thinking=false"
```

应该看到：
```
[子问题答案生成] 开始为 2 个子问题生成答案
[子问题答案] 生成成功: 中国护照去哪些国家免签？... | 长度: 156
[子问题答案] 生成成功: 各国免签停留时间是多久？... | 长度: 142
[子问题答案] 已保存 2 个子问题答案，将注入上下文
[提示词构建] 已将 2 个子问题答案注入上下文
```

### 2. 查看 SSE 输出

```
SUB_QUESTIONS:{"sub_questions": [...], "count": 2, "sub_answers": [{"sub_question": "...", "answer": "LLM生成的答案..."}, ...]}
```

### 3. 检查最终答案质量

最终答案应该：
- 包含各个子问题的信息
- 更加完整和连贯
- 基于子问题答案进行综合

---

## 相关文档

- [子问题分解使用指南](./SUBQUESTION_DECOMPOSITION_GUIDE.md)
- [LLM 判断开关指南](./SUBQUESTION_LLM_JUDGE_GUIDE.md)
- [前端显示示例](./SUB_QUESTIONS_FRONTEND_EXAMPLE.md)
- [超时问题修复](./SUBQUESTION_TIMEOUT_FIX.md)

---

## 更新日志

- 2025-01-XX: 实现子问题答案生成功能
- 2025-01-XX: 添加子问题答案注入上下文
- 2025-01-XX: 优化前端数据传输格式
