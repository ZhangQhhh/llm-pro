# 子问题前端显示示例

## 数据格式

### SSE 消息格式

```
SUB_QUESTIONS:{"sub_questions": ["子问题1", "子问题2"], "count": 2, "sub_answers": [{"sub_question": "子问题1", "answer": "答案摘要1"}, {"sub_question": "子问题2", "answer": "答案摘要2"}]}
```

### JSON 数据结构

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
      "answer": "根据检索结果，中国护照可以免签进入以下国家：泰国、新加坡、马来西亚..."
    },
    {
      "sub_question": "各国免签停留时间是多久？",
      "answer": "各国免签停留时间如下：泰国30天、新加坡30天、马来西亚30天..."
    }
  ]
}
```

---

## 前端实现示例

### 1. JavaScript 原生实现

```javascript
// 监听 SSE 消息
eventSource.onmessage = function(event) {
    const message = event.data;
    
    if (message.startsWith('SUB_QUESTIONS:')) {
        // 提取 JSON 数据
        const jsonStr = message.substring('SUB_QUESTIONS:'.length);
        const data = JSON.parse(jsonStr);
        
        console.log('收到子问题数据:', data);
        
        // 显示子问题和答案
        displaySubQuestions(data);
    }
};

// 显示子问题的函数
function displaySubQuestions(data) {
    const container = document.getElementById('sub-questions-container');
    container.innerHTML = '';
    
    // 创建标题
    const title = document.createElement('div');
    title.className = 'sub-questions-title';
    title.innerHTML = `<h3>📋 问题分解（共 ${data.count} 个子问题）</h3>`;
    container.appendChild(title);
    
    // 遍历子问题
    data.sub_questions.forEach((question, index) => {
        const item = document.createElement('div');
        item.className = 'sub-question-item';
        
        // 子问题标题
        const questionDiv = document.createElement('div');
        questionDiv.className = 'sub-question';
        questionDiv.innerHTML = `<strong>${index + 1}. ${question}</strong>`;
        item.appendChild(questionDiv);
        
        // 如果有答案摘要，显示
        const answer = data.sub_answers.find(a => a.sub_question === question);
        if (answer) {
            const answerDiv = document.createElement('div');
            answerDiv.className = 'sub-answer';
            answerDiv.textContent = answer.answer;
            item.appendChild(answerDiv);
        }
        
        container.appendChild(item);
    });
}
```

### 2. CSS 样式

```css
/* 子问题容器 */
#sub-questions-container {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 16px;
    margin: 16px 0;
}

/* 标题 */
.sub-questions-title {
    color: #495057;
    margin-bottom: 12px;
    border-bottom: 2px solid #007bff;
    padding-bottom: 8px;
}

.sub-questions-title h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
}

/* 子问题项 */
.sub-question-item {
    background: white;
    border: 1px solid #e9ecef;
    border-radius: 6px;
    padding: 12px;
    margin-bottom: 12px;
}

.sub-question-item:last-child {
    margin-bottom: 0;
}

/* 子问题文本 */
.sub-question {
    color: #212529;
    font-size: 14px;
    margin-bottom: 8px;
}

.sub-question strong {
    color: #007bff;
}

/* 答案摘要 */
.sub-answer {
    color: #6c757d;
    font-size: 13px;
    line-height: 1.6;
    padding: 8px;
    background: #f8f9fa;
    border-left: 3px solid #28a745;
    border-radius: 4px;
}
```

### 3. HTML 结构

```html
<!DOCTYPE html>
<html>
<head>
    <title>知识问答</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div class="container">
        <h1>知识问答系统</h1>
        
        <!-- 输入区域 -->
        <div class="input-area">
            <textarea id="question-input" placeholder="请输入您的问题..."></textarea>
            <button onclick="askQuestion()">提问</button>
        </div>
        
        <!-- 子问题显示区域 -->
        <div id="sub-questions-container" style="display: none;"></div>
        
        <!-- 答案显示区域 -->
        <div id="answer-container"></div>
    </div>
    
    <script src="script.js"></script>
</body>
</html>
```

### 4. 完整 JavaScript 示例

```javascript
let eventSource = null;

function askQuestion() {
    const question = document.getElementById('question-input').value;
    if (!question.trim()) {
        alert('请输入问题');
        return;
    }
    
    // 清空之前的内容
    document.getElementById('sub-questions-container').style.display = 'none';
    document.getElementById('sub-questions-container').innerHTML = '';
    document.getElementById('answer-container').innerHTML = '';
    
    // 关闭之前的连接
    if (eventSource) {
        eventSource.close();
    }
    
    // 创建新的 SSE 连接
    const url = `/api/knowledge?question=${encodeURIComponent(question)}&enable_thinking=false&rerank_top_n=10`;
    eventSource = new EventSource(url);
    
    // 监听消息
    eventSource.onmessage = function(event) {
        const message = event.data;
        
        if (message.startsWith('SUB_QUESTIONS:')) {
            // 显示子问题
            const jsonStr = message.substring('SUB_QUESTIONS:'.length);
            const data = JSON.parse(jsonStr);
            
            displaySubQuestions(data);
            document.getElementById('sub-questions-container').style.display = 'block';
            
        } else if (message.startsWith('CONTENT:')) {
            // 显示答案内容
            const content = message.substring('CONTENT:'.length);
            appendAnswer(content);
            
        } else if (message.startsWith('THINK:')) {
            // 显示思考过程
            const thinkContent = message.substring('THINK:'.length);
            appendThinking(thinkContent);
            
        } else if (message.startsWith('DONE:')) {
            // 完成
            eventSource.close();
            eventSource = null;
        }
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE 错误:', error);
        eventSource.close();
        eventSource = null;
    };
}

function displaySubQuestions(data) {
    const container = document.getElementById('sub-questions-container');
    container.innerHTML = '';
    
    // 创建标题
    const title = document.createElement('div');
    title.className = 'sub-questions-title';
    title.innerHTML = `<h3>📋 问题分解（共 ${data.count} 个子问题）</h3>`;
    container.appendChild(title);
    
    // 遍历子问题
    data.sub_questions.forEach((question, index) => {
        const item = document.createElement('div');
        item.className = 'sub-question-item';
        
        // 子问题标题
        const questionDiv = document.createElement('div');
        questionDiv.className = 'sub-question';
        questionDiv.innerHTML = `<strong>${index + 1}. ${question}</strong>`;
        item.appendChild(questionDiv);
        
        // 如果有答案摘要，显示
        const answer = data.sub_answers.find(a => a.sub_question === question);
        if (answer) {
            const answerDiv = document.createElement('div');
            answerDiv.className = 'sub-answer';
            answerDiv.innerHTML = `<em>答案摘要：</em>${answer.answer}`;
            item.appendChild(answerDiv);
        }
        
        container.appendChild(item);
    });
}

function appendAnswer(content) {
    const container = document.getElementById('answer-container');
    container.innerHTML += content;
}

function appendThinking(content) {
    // 可选：显示思考过程
    const container = document.getElementById('answer-container');
    const thinkDiv = document.createElement('div');
    thinkDiv.className = 'thinking-content';
    thinkDiv.textContent = content;
    container.appendChild(thinkDiv);
}
```

---

## 数据说明

### sub_questions（子问题列表）

- **类型**：`Array<string>`
- **说明**：分解后的子问题列表
- **示例**：
  ```json
  [
    "中国护照去哪些国家免签？",
    "各国免签停留时间是多久？"
  ]
  ```

### count（子问题数量）

- **类型**：`number`
- **说明**：子问题的数量
- **示例**：`2`

### sub_answers（子问题答案摘要）

- **类型**：`Array<{sub_question: string, answer: string}>`
- **说明**：每个子问题的答案摘要（取检索结果的前200字符）
- **示例**：
  ```json
  [
    {
      "sub_question": "中国护照去哪些国家免签？",
      "answer": "根据检索结果，中国护照可以免签进入以下国家：泰国、新加坡、马来西亚..."
    }
  ]
  ```

---

## 使用场景

### 场景1：只显示子问题

```javascript
function displaySubQuestions(data) {
    const html = data.sub_questions.map((q, i) => 
        `<div>${i + 1}. ${q}</div>`
    ).join('');
    
    document.getElementById('sub-questions-container').innerHTML = html;
}
```

### 场景2：显示子问题 + 答案摘要

```javascript
function displaySubQuestions(data) {
    const html = data.sub_questions.map((q, i) => {
        const answer = data.sub_answers.find(a => a.sub_question === q);
        return `
            <div class="sub-question-item">
                <div class="question">${i + 1}. ${q}</div>
                ${answer ? `<div class="answer">${answer.answer}</div>` : ''}
            </div>
        `;
    }).join('');
    
    document.getElementById('sub-questions-container').innerHTML = html;
}
```

### 场景3：折叠/展开子问题

```javascript
function displaySubQuestions(data) {
    const container = document.getElementById('sub-questions-container');
    
    // 创建可折叠的标题
    const header = document.createElement('div');
    header.className = 'sub-questions-header';
    header.innerHTML = `
        <span>📋 问题分解（${data.count} 个子问题）</span>
        <button onclick="toggleSubQuestions()">展开/折叠</button>
    `;
    container.appendChild(header);
    
    // 创建内容区域
    const content = document.createElement('div');
    content.id = 'sub-questions-content';
    content.className = 'sub-questions-content';
    
    data.sub_questions.forEach((q, i) => {
        const answer = data.sub_answers.find(a => a.sub_question === q);
        content.innerHTML += `
            <div class="sub-question-item">
                <div class="question">${i + 1}. ${q}</div>
                ${answer ? `<div class="answer">${answer.answer}</div>` : ''}
            </div>
        `;
    });
    
    container.appendChild(content);
}

function toggleSubQuestions() {
    const content = document.getElementById('sub-questions-content');
    content.style.display = content.style.display === 'none' ? 'block' : 'none';
}
```

---

## 调试技巧

### 1. 查看原始 SSE 消息

```javascript
eventSource.onmessage = function(event) {
    console.log('收到消息:', event.data);
    
    // 处理消息...
};
```

### 2. 验证 JSON 格式

```javascript
if (message.startsWith('SUB_QUESTIONS:')) {
    const jsonStr = message.substring('SUB_QUESTIONS:'.length);
    
    try {
        const data = JSON.parse(jsonStr);
        console.log('解析成功:', data);
    } catch (e) {
        console.error('JSON 解析失败:', e);
        console.log('原始数据:', jsonStr);
    }
}
```

### 3. 检查数据完整性

```javascript
function displaySubQuestions(data) {
    // 验证数据
    if (!data.sub_questions || !Array.isArray(data.sub_questions)) {
        console.error('无效的子问题数据:', data);
        return;
    }
    
    if (data.count !== data.sub_questions.length) {
        console.warn('子问题数量不匹配:', data.count, data.sub_questions.length);
    }
    
    // 显示数据...
}
```

---

## 常见问题

### Q1: 为什么没有收到 SUB_QUESTIONS 消息？

**可能原因**：
1. 子问题分解功能未启用：`ENABLE_SUBQUESTION_DECOMPOSITION=false`
2. 查询未触发分解：长度不足或 LLM 判断不需要分解
3. 使用了 LlamaIndex 引擎：不支持元数据传递

**解决方案**：
```bash
# 启用子问题分解
ENABLE_SUBQUESTION_DECOMPOSITION=true

# 使用自定义引擎
SUBQUESTION_ENGINE_TYPE=custom

# 降低长度阈值
SUBQUESTION_COMPLEXITY_THRESHOLD=20

# 关闭 LLM 判断（强制分解）
SUBQUESTION_USE_LLM_JUDGE=false
```

### Q2: sub_answers 为空怎么办？

**原因**：子问题检索失败或没有找到相关文档。

**处理**：
```javascript
const answer = data.sub_answers.find(a => a.sub_question === q);
if (answer && answer.answer) {
    // 显示答案
} else {
    // 显示占位符
    answerDiv.textContent = '暂无答案摘要';
}
```

### Q3: 答案摘要太短怎么办？

**原因**：默认只取前 200 字符。

**修改**：编辑 `core/sub_question_decomposer.py`：
```python
# 第 366 行
top_node_content = result['nodes'][0].node.get_content()[:500]  # 改为 500 字符
```

---

## 相关文档

- [子问题分解使用指南](./SUBQUESTION_DECOMPOSITION_GUIDE.md)
- [LLM 判断开关指南](./SUBQUESTION_LLM_JUDGE_GUIDE.md)
- [环境变量配置指南](./ENV_CONFIGURATION_GUIDE.md)
