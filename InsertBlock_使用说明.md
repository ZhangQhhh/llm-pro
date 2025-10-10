# InsertBlock 智能过滤功能使用说明

## 功能概述

InsertBlock 是一个插件式的智能过滤功能，用于在知识问答过程中对重排后的节点进行二次筛选和提取。

### 工作原理

1. **混合检索 + 重排**：首先进行常规的检索和重排序操作
2. **并发智能过滤**：对每个重排后的节点，使用 InsertBlock 提示词判断：
   - 该节点内容是否与问题相关（`is_relevant`）
   - 该节点是否能直接回答问题（`can_answer`）
   - 从节点中提取最关键的段落（`key_passage`）
3. **精准上下文注入**：只将能回答问题的节点及其关键段落注入到最终的 LLM 上下文中

### 优势

- **减少噪音**：过滤掉不能直接回答问题的节点
- **提取关键**：只注入最相关的文本段落，节省 token
- **并发处理**：使用线程池并发处理多个节点，提升速度
- **可插拔**：通过参数控制是否启用，不影响原有功能

## API 使用方式

### 请求示例

```bash
curl -X POST http://localhost:5000/api/knowledge_chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "俄罗斯公民能否免签入境海南？",
    "thinking": "false",
    "rerank_top_n": 5,
    "model_id": "qwen",
    "use_insert_block": true,
    "insert_block_llm_id": "qwen"
  }'
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `question` | string | 必填 | 用户问题 |
| `thinking` | string/bool | "true" | 是否启用思考模式 |
| `rerank_top_n` | int | 5 | 重排后返回的节点数量 |
| `model_id` | string | "qwen" | 用于最终回答的 LLM ID |
| `use_insert_block` | string/bool | "false" | **是否启用 InsertBlock 过滤** |
| `insert_block_llm_id` | string | null | **InsertBlock 过滤使用的 LLM ID**（默认使用系统默认 LLM） |

### 响应示例

#### 启用 InsertBlock 模式

```
data: CONTENT:正在进行混合检索...

data: CONTENT:正在使用 InsertBlock 智能过滤...

data: CONTENT:找到 2 个可回答的节点

data: CONTENT:已找到相关资料，正在生成回答...

data: CONTENT:根据相关规定，俄罗斯公民可以免签入境海南...

data: CONTENT:

**参考来源（经 InsertBlock 过滤）:**

data: SOURCE:{"id":1,"fileName":"海南免签政策.pdf","initialScore":"0.8523","rerankedScore":"0.9234","canAnswer":true,"reasoning":"该法规明确列出了59个免签国家名单","keyPassage":"允许俄罗斯、英国...等59国人员免签入境海南","content":"...完整内容..."}

data: DONE:
```

## 代码层面使用

### 在 Python 代码中调用

```python
from flask import current_app

# 获取 handler
knowledge_handler = current_app.knowledge_handler
llm = current_app.llm_service.get_client("qwen")

# 调用处理方法
for chunk in knowledge_handler.process(
    question="俄罗斯公民能否免签入境海南？",
    enable_thinking=False,
    rerank_top_n=5,
    llm=llm,
    client_ip="127.0.0.1",
    use_insert_block=True,           # 启用 InsertBlock
    insert_block_llm_id="qwen"       # 指定过滤用的模型
):
    print(chunk)
```

### 自定义过滤器参数

```python
from core.node_filter import InsertBlockFilter
from services import LLMService

llm_service = LLMService()
llm_service.initialize()

# 创建过滤器（可自定义并发数）
filter = InsertBlockFilter(
    llm_service=llm_service,
    max_workers=10  # 最大并发线程数，默认 5
)

# 过滤节点
filtered_results = filter.filter_nodes(
    question="你的问题",
    nodes=reranked_nodes,
    llm_id="qwen"
)

# 查看结果
for result in filtered_results:
    print(f"文件: {result['file_name']}")
    print(f"可回答: {result['can_answer']}")
    print(f"关键段落: {result['key_passage']}")
    print(f"推理: {result['reasoning']}")
```

## 配置说明

### prompts.json 配置

InsertBlock 使用 `prompts.json` 中的 `insertBlock` 配置：

```json
{
  "insertBlock": {
    "system": {
      "all": [
        "# 角色\n你是一位精通中国出入境边防检查各项业务的专家...",
        "# 输入\n- **问题**: {question}\n- **法规**: {regulations}"
      ]
    },
    "user": {
      "all": [
        "# 任务\n你的任务是接收一个业务场景下的"问题"和一条"法规"...",
        "# 输出要求\n请严格按照以下JSON格式返回..."
      ]
    }
  }
}
```

提示词中的占位符：
- `{question}`: 用户问题
- `{regulations}`: 节点内容（法规原文）

### 并发配置

在 `core/node_filter.py` 中修改默认并发数：

```python
class InsertBlockFilter:
    def __init__(self, llm_service, max_workers: int = 5):  # 修改这里
        self.llm_service = llm_service
        self.max_workers = max_workers
```

## 日志输出

启用 InsertBlock 后，日志会包含以下信息：

```
[INFO] 开始使用 InsertBlock 过滤器处理 5 个节点
[INFO] 节点可回答: 海南免签政策.pdf | 关键段落长度: 156
[INFO] 节点可回答: 免签入境规定.docx | 关键段落长度: 203
[DEBUG] 节点不可回答: 其他无关文件.pdf
[INFO] InsertBlock 过滤完成: 5 个节点 -> 2 个可回答节点
```

## 性能考虑

1. **Token 消耗**：每个节点都会调用一次 LLM 进行判断，会增加 token 消耗
2. **响应时间**：虽然使用了并发，但仍会增加总体响应时间（约 2-5 秒，取决于节点数量和模型速度）
3. **适用场景**：
   - ✅ 适合：需要高精度答案、知识库较大、检索噪音较多的场景
   - ❌ 不适合：对响应速度要求极高、知识库质量已很高的场景

## 对比：启用 vs 不启用

| 模式 | 优点 | 缺点 |
|------|------|------|
| **不启用** | 响应快、token 消耗少 | 可能包含不相关的上下文 |
| **启用 InsertBlock** | 上下文更精准、答案质量更高 | 响应慢、token 消耗多 |

## 故障排除

### 问题：InsertBlock 过滤器未初始化

**原因**：创建 `KnowledgeHandler` 时未传入 `llm_service`

**解决**：检查 `app.py` 中的初始化代码：
```python
knowledge_handler = KnowledgeHandler(retriever, reranker, llm_wrapper, llm_service)
```

### 问题：JSON 解析失败

**原因**：LLM 返回的格式不符合预期

**解决**：
1. 检查 `prompts.json` 中 `insertBlock` 的提示词是否明确要求 JSON 格式
2. 查看日志中的 LLM 原始响应
3. 尝试更换更稳定的 LLM 模型

### 问题：所有节点都被过滤掉

**原因**：InsertBlock 判断标准过严或提示词不当

**解决**：
1. 检查并优化 `insertBlock` 提示词
2. 降低判断标准（修改提示词中的判断逻辑）
3. 查看日志中每个节点的 `reasoning` 字段，了解被过滤原因

## 扩展开发

### 添加自定义过滤策略

在 `core/node_filter.py` 中扩展：

```python
class InsertBlockFilter:
    def filter_nodes_with_score_threshold(
        self,
        question: str,
        nodes: List[Any],
        llm_id: Optional[str] = None,
        min_relevance_score: float = 0.7  # 自定义相关性阈值
    ):
        """带相关性分数阈值的过滤"""
        # 实现自定义逻辑
        pass
```

### 自定义返回字段

修改 `_process_single_node` 方法的返回结构，添加更多信息。

---

## 总结

InsertBlock 是一个强大的插件式功能，通过智能过滤和关键段落提取，显著提升知识问答的精准度。根据你的实际需求，灵活选择是否启用此功能。

