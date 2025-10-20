# 多轮对话上下文管理（Conversation / Context Management）技术文档

面向对象：本项目的后端/全栈开发者与维护者。
目的：帮助快速理解并接手“多轮对话上下文管理”的整体实现、调用链路、数据结构、清理策略与常见问题排查。

---

## 目录
- [总体概览](#总体概览)
- [关键模块与文件](#关键模块与文件)
- [端到端调用流程](#端到端调用流程)
- [数据结构与协议](#数据结构与协议)
  - [Qdrant 点的 Payload](#qdrant-点的-payload)
  - [LLM messages 结构](#llm-messages-结构)
  - [SSE 流前缀与约定](#sse-流前缀与约定)
- [父子链（parent_turn_id）机制](#父子链parent_turn_id机制)
- [历史缓存、检索与消息构建](#历史缓存检索与消息构建)
- [过期清理与配置](#过期清理与配置)
- [前端配合与展示](#前端配合与展示)
- [LLM 适配与流式解析](#llm-适配与流式解析)
- [边界条件与异常处理](#边界条件与异常处理)
- [测试清单与排查指南](#测试清单与排查指南)
- [附录：回填脚本与示例](#附录回填脚本与示例)

---

## 总体概览
上下文管理的目标：
- 将每一轮“用户问 + 助手答”存入向量数据库（Qdrant），为后续相似问题提供可检索的历史上下文；
- 在生成新回答时，组合“系统提示 + 相关历史 + 最近历史 + 知识库上下文 + 用户当前问题”形成 messages 输入给 LLM；
- 可维护多轮对话的“父子链关系”（parent_turn_id），支持线性链或扩展为分支结构；
- 支持定期删除超过 N 天的历史对话，释放存储；
- 以 SSE 流返回生成进度、思考过程与最终答案。

---

## 关键模块与文件
- 路由层（HTTP 入口）
  - `routes/knowledge_routes.py`
    - `/knowledge_chat_conversation`: 接收问题、会话与配置，发起多轮对话处理并以 SSE 流输出。
- 业务处理器（RAG + 对话）
  - `api/knowledge_handler.py`
    - `process_conversation(...)`: 多轮对话主流程，包含检索/重排、知识上下文构建、messages 构造、LLM 流式调用、结果入库与参考来源输出。
    - `_build_knowledge_context(...)`: 将检索结果格式化为可读上下文文本。
    - `_call_llm_with_messages(...)`: 基于 messages 进行 LLM 流式调用，并解析输出中的 `<think>...</think>`（如有）。
- 对话管理器（上下文存取）
  - `services/conversation_manager.py`
    - `add_conversation_turn(...)`: 将一轮对话生成 embedding 并写入 Qdrant；
    - `get_recent_history(...)`: 获取最近 N 轮（带 5 分钟缓存）；
    - `retrieve_relevant_history(...)`: 在当前会话内做相似度检索；
    - `build_context_messages(...)`: 依据系统提示、相关/最近历史与知识上下文，构建 messages；
    - `delete_old_conversations(days)` / `cleanup_expired_conversations()`: 删除过期对话。
- LLM 封装层
  - `core/llm_wrapper.py`
    - `LLMStreamWrapper.stream(...) / stream_chat(...)`: 统一流式接口，兼容 chat/complete；
- LLM 客户端管理
  - `services/llm_service.py`
    - `LLMService` + `CustomOpenAILike`: 管理不同模型实例，统一参数与 http client。
- 配置
  - `config/settings.py`（或 `config/__init__.py` 中的 `Settings`）
    - 重要字段：`CONVERSATION_COLLECTION`, `CONVERSATION_EXPIRE_DAYS`, `MAX_RECENT_TURNS`, `MAX_RELEVANT_TURNS`, `USE_CHAT_MODE`, `RERANK_SCORE_THRESHOLD`, `RERANKER_INPUT_TOP_N` 等。

---

## 端到端调用流程
以下描述一次完整的“多轮对话”请求从进入到存储的全过程：

1) 前端 POST `/knowledge_chat_conversation`
- Body 字段（示例）：
  - `question`: 用户问题
  - `session_id`（可选）：会话 ID（未提供则后端生成）
  - `thinking`: 是否启用“思考模式”（与 prompts 选择相关）
  - `model_id`：模型标识
  - `rerank_top_n`, `use_insert_block`, `insert_block_llm_id`：检索与过滤策略

2) 路由层解析参数，获取 LLM 客户端，调用 `KnowledgeHandler.process_conversation(...)`
- 首先返回 `SESSION:<session_id>`；
- 输出第一条进度：`CONTENT:正在进行混合检索...`。

3) 检索与重排（`_retrieve_and_rerank`）
- `retriever.retrieve(question)` 得到初检索节点；
- 取前 `Settings.RERANKER_INPUT_TOP_N` 个进入重排 `reranker.postprocess_nodes(...)`；
- 用 `Settings.RERANK_SCORE_THRESHOLD` 做阈值过滤，保留高质量节点（再切到 `rerank_top_n`）。

4) InsertBlock 智能过滤（可选）
- 若启用：在原始候选上做二次筛选，保留可直接回答的节点（并可携带关键段与推理原因）。

5) 构建知识上下文（`_build_knowledge_context`）
- 将（过滤后的）节点格式化为带来源编号的上下文文本，作为 `knowledge_context`。

6) 构建 messages（`ConversationManager.build_context_messages`）
- 依据 `has_rag` 选择不同的 system prompt；
- 获取上下文前缀（相关历史/最近历史/规定）；
- 组合：
  - `system`（角色扮演/规则）；
  - `relevant_history`（相似检索）去重后加入；
  - `recent_history`（最近 N 轮）；
  - `knowledge_context`（如有）；
  - 当前用户 `user` 提问。

7) 调用 LLM，流式输出（`_call_llm_with_messages`）
- 通过 `llm_wrapper.stream_chat(llm, messages)` 发起；
- 对流式 delta：
  - 若检测到 `<think>...</think>` 包裹内容 → 以 `THINK:` 前缀输出；
  - 其它内容 → 作为正文，最终在外层包装为 `CONTENT:` 输出。

8) 入库当前轮（`ConversationManager.add_conversation_turn`）
- 生成 `conversation_text = "用户: ...\n助手: ..."`；
- 用 `embed_model.get_text_embedding(...)` 得到向量，构建 payload（见下文）；
- 计算 `parent_turn_id`：取最近一轮的 `turn_id` 作为当前轮的父（线性链）；
- 生成新的 `turn_id`，连同 `parent_turn_id` 一起 upsert 到 Qdrant；
- 失效/清理该 session 的 recent 缓存。

9) 输出参考来源（SOURCE）与结束（DONE）
- 按模式输出参考来源的 JSON（包含文件名、分数、关键段等）；
- 输出 `DONE:`；
- 记录 QA 日志（`QALogger`）。

---

## 数据结构与协议

### Qdrant 点的 Payload
入库到 `Settings.CONVERSATION_COLLECTION` 的 payload 字段：
```json
{
  "session_id": "43dbf258-...",
  "user_query": "你好",
  "assistant_response": "您好……",
  "timestamp": "2025-10-20T16:28:31.386637",
  "context_docs": ["条例A.pdf", "指南B.md"],
  "token_count": 56,
  "turn_id": "cc98c594-...",
  "parent_turn_id": "上一次的turn_id或null"
}
```
说明：
- `turn_id`：当前轮的唯一标识（UUID）；
- `parent_turn_id`：父轮的 `turn_id`（线性链为上一轮）。

### LLM messages 结构
传给 LLM 的 `messages` 为数组：
```json
[
  {"role": "system", "content": "你是一名资深边检业务专家……"},
  {"role": "system", "content": "以下是相关的历史对话：\n..."},
  {"role": "user", "content": "历史用户问1"},
  {"role": "assistant", "content": "历史助手答1"},
  {"role": "system", "content": "以下是最近的对话历史：\n..."},
  ...,
  {"role": "system", "content": "业务规定如下：\n<知识上下文>"},
  {"role": "user", "content": "<当前用户问题>"}
]
```

### SSE 流前缀与约定
- `SESSION:<uuid>` — 服务端确认/生成的会话 ID；
- `CONTENT:<chunk>` — 正文内容的增量片段；
- `THINK:<chunk>` — 思考过程的增量片段（从 LLM 输出内的 `<think>...</think>` 解析而来）；
- `SOURCE:<json>` — 参考来源（JSON 格式字符串）；
- `ERROR:<msg>` — 错误；
- `DONE:` — 会话流结束标记。

前端需按前缀将内容分别渲染（例如 `THINK:` -> 思考面板，`CONTENT:` -> 正文面板）。

---

## 父子链（parent_turn_id）机制
- 目的：记录对话的先后/分支关系，支持回溯、可视化与高级检索；
- 现状（已修复）：
  - `process_conversation` 在入库前，会调用 `get_recent_history(session_id, 1)` 获取“上一轮”的 `turn_id` 并作为本轮 `parent_turn_id`；
  - 同时为本轮生成新的 `turn_id` 一并写入；
  - `get_recent_history` 的返回中包含 `turn_id`、`parent_turn_id`（已补充）。
- 分支能力：若要支持真正分支（非线性），可在前端发起请求时显式传入希望作为父节点的 `parent_turn_id`，后端优先采用该值。
- 历史数据回填：见附录脚本，可按时间线为既有记录自动建立线性 parent 链。

---

## 历史缓存、检索与消息构建
- 缓存：`ConversationManager._recent_cache`，key 为 `session_id`，value 为最近对话列表与缓存时间戳；TTL 5 分钟；新增对话后会清理对应 session 的缓存。
- 最近历史：`get_recent_history(session_id, limit)`
  - 使用 Qdrant `scroll` 拉取该会话的所有点（默认上限 100 条），按 `timestamp` 降序取最近 `limit` 条，再反转为升序（旧->新）；
  - 返回字段包含：`user_query, assistant_response, timestamp, turn_id, parent_turn_id`。
- 相关历史：`retrieve_relevant_history(session_id, current_query, top_k)`
  - 以 `current_query` 生成 embedding，在当前会话内向量检索最相近的历史，返回 `user_query/assistant_response/score` 等。
- 构建 messages：`build_context_messages(...)`
  - 合并 `relevant_history` 与 `recent_history`，对重复 `user_query` 去重（优先保留最近）；
  - 按顺序写入 messages（system → relevant → recent → knowledge_context → 当前 user）。

---

## 过期清理与配置
- 清理实现：`ConversationManager.delete_old_conversations(days)`
  - 计算阈值时间 `now - days`（ISO 字符串），删除所有 `timestamp < 阈值` 的点；
  - 返回删除统计，并清空 recent 缓存；
- 自动清理：`cleanup_expired_conversations()` 从配置读取 `Settings.CONVERSATION_EXPIRE_DAYS`，并调用 `delete_old_conversations`；
- 配置位置：`config/settings.py`（或同等 settings 定义文件）
  - `CONVERSATION_EXPIRE_DAYS = N`（示例：30）
  - `CONVERSATION_COLLECTION = "conversations"`
  - `MAX_RECENT_TURNS`, `MAX_RELEVANT_TURNS` 等；
- 运维建议：
  - 结合计划任务定期调用自动清理（如每日凌晨）；
  - 对清理前后的 Qdrant 占用做监控，必要时导出备份。

---

## 前端配合与展示
- 前端 HTML（如 `conversation3.html`）中：
  - 遇到 `SESSION:` 前缀，更新本地会话 ID；
  - `THINK:` 片段累加到“思考过程”区域（`updateAssistantThinking`）；
  - `CONTENT:` 片段累加到“最终回答”区域（支持 markdown 渲染，`updateAssistantFinal`）；
  - `SOURCE:` 展示参考来源列表（文件名、分数、关键段等）。
- 注意：后端已处理 `<think>` 标签拆分与缓冲，避免前端收到大量碎片；若仍有体验问题，可在前端增加节流/合并逻辑。

---

## LLM 适配与流式解析
- 适配层：`core/llm_wrapper.py`
  - 若 LLM 支持 `stream_chat`：优先使用（messages 结构）；
  - 若不支持：回退 `stream_complete`，将 messages 拼接为 plain prompt；
  - `ChatMessage` 类型导入失败时也会回退。
- 流式解析：
  - 在 `KnowledgeHandler._call_llm_with_messages` 中，解析 `<think>...</think>`：
    - 标签内内容以 `THINK:` 前缀输出；
    - 其余内容作为正文，由上层加 `CONTENT:`。
  - 这样前端即可区分“思考”与“正文”。

---

## 边界条件与异常处理
- 无检索结果：
  - 走“基于通用知识和对话历史”的提示词与回答路径；
- LLM 不支持 chat：
  - 自动回退到 complete 模式；
- SSE 流中断：
  - 前端应具备重连或告警；后端日志定位 `_call_llm_with_messages` 处异常；
- Qdrant 连接/写入失败：
  - 查看 `add_conversation_turn` 报错与网络连通，确认 collection 是否存在（初始化时会创建）；
- token 过多：
  - 日志会有警告；可调小 `MAX_RECENT_TURNS`、做历史摘要或增加上下文窗口；
- 大会话清理：
  - 定时运行 `cleanup_expired_conversations`，并关注阈值时间格式与时区。

---

## 测试清单与排查指南
- 入库链路：
  - 连续发两轮问题，检查第二轮的 `parent_turn_id` 是否等于第一轮的 `turn_id`；
- 历史构建：
  - 观察 messages 是否包含 recent 与 relevant（且去重生效）；
- SSE 正确性：
  - 是否存在 `SESSION:`、`THINK:`、`CONTENT:`、`SOURCE:`、`DONE:`；
  - THINK/CONTENT 是否被错误混用（后端已修复外层不重复加前缀）；
- 清理：
  - 设置一个较小 `CONVERSATION_EXPIRE_DAYS`，调用 `cleanup_expired_conversations()` 验证删除数量；
- 断网/异常：
  - 模拟 Qdrant 不可达，确认错误日志与 API 兜底响应。

---

## 附录：回填脚本与示例

### 历史 parent_turn_id 回填脚本（线性链）
用于将既有记录按时间排序，依次设置 `parent_turn_id` 指向前一条的 `turn_id`。在生产执行前务必做好备份。

```python
# scripts/backfill_parent_turns.py
from qdrant_client import QdrantClient
import os

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
API_KEY = os.getenv("QDRANT_API_KEY", None)
COLLECTION = "conversations"

client = QdrantClient(url=QDRANT_URL, api_key=API_KEY)

def backfill_session(session_id: str):
    scroll = client.scroll(
        collection_name=COLLECTION,
        scroll_filter={"must": [{"key": "session_id", "match": {"value": session_id}}]},
        with_payload=True,
        limit=1000,
    )
    points = scroll[0]
    points_sorted = sorted(points, key=lambda p: p.payload.get("timestamp"))

    prev_turn_id = None
    for p in points_sorted:
        payload = p.payload
        this_turn_id = payload.get("turn_id")
        if not this_turn_id:
            import uuid
            this_turn_id = str(uuid.uuid4())
            payload["turn_id"] = this_turn_id
        if payload.get("parent_turn_id") != prev_turn_id:
            payload["parent_turn_id"] = prev_turn_id
            client.upsert(collection_name=COLLECTION, points=[{"id": p.id, "vector": p.vector, "payload": payload}])
        prev_turn_id = this_turn_id

if __name__ == "__main__":
    sessions = [
        # TODO: 填入需要回填的 session_id 列表，或实现遍历所有会话
        "43dbf258-db89-4816-a282-db4b5cf2ad9e"
    ]
    for s in sessions:
        backfill_session(s)
    print("done")
```

### API 请求示例（多轮对话）
```json
POST /knowledge_chat_conversation
{
  "question": "中国签证类型有哪些",
  "session_id": "<可选，未传则后端生成>",
  "thinking": true,
  "model_id": "default",
  "rerank_top_n": 10,
  "use_insert_block": false
}
```

### 相关配置（示意）
```python
# config/settings.py
CONVERSATION_COLLECTION = "conversations"
CONVERSATION_EXPIRE_DAYS = 30
MAX_RECENT_TURNS = 5
MAX_RELEVANT_TURNS = 2
USE_CHAT_MODE = True
RERANKER_INPUT_TOP_N = 20
RERANK_SCORE_THRESHOLD = 0.2
```

---

如需将本文档链接到 README，建议增加“架构/上下文管理”章节并指向本文件；也可将回填脚本落库于 `scripts/` 并在 README 中添加使用注意事项。
