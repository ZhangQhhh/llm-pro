# RAG 系统 - 企业级架构版本

## 📁 项目结构

```
10.9/
├── app.py                      # 主应用入口（应用工厂模式）
├── prompts.json                # Prompt 模板配置文件
│
├── config/                     # 配置模块
│   ├── __init__.py
│   └── settings.py             # 集中式配置管理
│
├── utils/                      # 工具模块
│   ├── __init__.py
│   ├── logger.py               # 日志管理
│   ├── text_processing.py      # 文本处理工具
│   └── prompt_loader.py        # Prompt 加载器
│
├── core/                       # 核心业务模块
│   ├── __init__.py
│   ├── llm_wrapper.py          # LLM 统一封装
│   ├── document_processor.py   # 文档处理器
│   └── retriever.py            # 检索器（BM25 + 向量 + RRF）
│
├── services/                   # 服务层
│   ├── __init__.py
│   ├── llm_service.py          # LLM 服务管理
│   ├── embedding_service.py    # Embedding 和 Reranker 服务
│   └── knowledge_service.py    # 知识库服务
│
├── api/                        # API 业务逻辑层
│   ├── __init__.py
│   ├── judge_handler.py        # 判断题处理器 (尚未暴露 HTTP 路由)
│   └── knowledge_handler.py    # 知识问答处理器
│
└── routes/                     # 路由层
    ├── __init__.py
    └── knowledge_routes.py     # 知识问答路由 (/api/knowledge_chat)
```

> 提示: Judge 功能虽然有 `JudgeHandler`，但当前没有对应的 Blueprint 路由文件（例如 `judge_routes.py`），因此外部暂时不能直接通过 HTTP 访问判断题接口。如需开放，请参考“🔌 添加 Judge 路由”章节。

## ✅ 当前 README 完整性评估概览

已覆盖: 架构分层、设计原则、核心模块说明、扩展方式、代码规范、最佳实践、调试、迁移。

缺失/不完整（本次已补充）:
- 运行环境与依赖安装方式
- 知识库与模型文件准备说明
- API 详细文档（请求/响应/SSE 协议）
- Judge 功能开放指引
- 日志与目录说明 / 权限
- 典型调用示例 (curl / Python)
- 常见问题 (FAQ) & 性能调优建议
- Roadmap / 后续扩展建议

下面章节已补齐，便于首次部署与二次开发。

## 🧩 系统简述
本项目实现一个混合检索增强生成 (RAG) 系统：通过向量检索 + BM25 + RRF 融合获取候选片段，并进行重排序后将上下文注入到 LLM，支持知识问答与（预留的）判断题推理模式，并可选择“思考(推理)”输出格式。

## 🖥️ 运行环境要求
- Python 3.10+ (建议 3.10 / 3.11)
- 操作系统: Linux / macOS / Windows (生产建议 Linux)
- 可选: NPU 或 GPU (配置中 `DEVICE` 自动判定；当前代码仅简单检测 NPU)
- 内存: 8GB+（视向量数量增多而增长）
- 模型存储位置需可读权限；日志与索引目录需可写权限。

## 📦 依赖安装
在 `10.9/` 目录下建议创建独立虚拟环境:
```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1 / CMD: .venv\Scripts\activate.bat
# Linux/macOS: source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```
如果暂未生成 `requirements.txt`，可根据实际使用添加（示例）:
```
flask
flask-cors
httpx
jieba
llama-index>=0.10.0
sentence-transformers
transformers
torch            # 或对应加速版 (CPU/GPU/NPU)
tqdm
```
> 注: `torch` 版本需与硬件/驱动匹配；`llama-index` 版本与 API 兼容性请根据实际环境固定。

## 📁 目录 & 数据准备
### 1. 知识库目录 (`Settings.KNOWLEDGE_BASE_DIR`)
默认: `/opt/rag_final_project/knowledge_base`
放置 txt / md / pdf (由 `SimpleDirectoryReader` 支持的格式) 文件；空目录会导致索引跳过。

### 2. 模型目录
```
/opt/rag_final_project/models/
  ├── text2vec-base-chinese        # Embedding 模型 (HuggingFace 结构)
  └── bge-reranker-v2-m3           # Reranker 模型
```
对应 `Settings.EMBED_MODEL_PATH` 与 `Settings.RERANKER_MODEL_PATH`。

### 3. 持久化与日志
```
/opt/rag_final_project/storage     # 向量索引与中间缓存
/opt/rag_final_project/qa_logs     # 问答 JSONL 日志
```
确保进程对以上路径拥有读写权限；首次运行会自动创建并生成索引。

### 4. Prompt 配置
`prompts.json` 放在：
1. `10.9/prompts.json` (优先)
2. 或 `/opt/rag_final_project/prompts.json`
程序启动时会自动解析找到可用文件。

## 🔑 关键配置 (`config/settings.py`)
无需实例化，类属性集中配置：
- 检索类: `RETRIEVAL_TOP_K`, `RERANKER_INPUT_TOP_N`, `RERANK_TOP_N`
- 模型: `LLM_ENDPOINTS`, `DEFAULT_LLM_ID`
- 超参: `LLM_MAX_TOKENS`, `LLM_REQUEST_TIMEOUT`
- 阈值: `RETRIEVAL_SCORE_THRESHOLD`, `RERANK_SCORE_THRESHOLD`
- 路径: `KNOWLEDGE_BASE_DIR`, `STORAGE_PATH`, `LOG_DIR`
- 行为: `USE_CHAT_MODE`

> 建议: 生产环境可增加“环境变量覆盖”机制（尚未实现），以便容器化部署。示例：检测 `os.getenv("KNOWLEDGE_BASE_DIR")`。

## 🚀 启动应用
```bash
cd 10.9
python app.py
```
访问（默认端口 5000）：
- 页面: `http://localhost:5000/` (导航)
- QA 接口: `POST /api/knowledge_chat` (SSE)

> 如果返回为空或立即结束，优先检查知识库目录是否包含有效文档。

## 🌐 API 文档
### 1. 知识问答 (Streaming SSE)
`POST /api/knowledge_chat`

请求 JSON:
```json
{
  "question": "边检证件过期后流程是什么？",
  "thinking": true,              // 是否启用推理 (影响 prompt 模板)
  "model_id": "qwen3-32b",      // 可选，默认 Settings.DEFAULT_LLM_ID
  "rerank_top_n": 5              // 可选，最终参考文档数 (1-15)
}
```

响应: `text/event-stream`，每行一个事件内容（未使用标准 Event: 字段，直接文本流）。前缀解释:
- `CONTENT:` 模型增量正文
- `SOURCE:` JSON，包含来源文档元数据
- `DONE:` 结束标记
- `ERROR:` 错误信息（此后通常终止）

示例 curl:
```bash
curl -N -H "Content-Type: application/json" \
  -X POST http://localhost:5000/api/knowledge_chat \
  -d '{"question":"示例问题","thinking":true}'
```
增量解析伪代码:
```python
import requests
r = requests.post(url, json=payload, stream=True)
for line in r.iter_lines(decode_unicode=True):
    if not line: continue
    if line.startswith("CONTENT:"):
        print(line[8:], end="")
    elif line.startswith("SOURCE:"):
        # 解析 JSON
        ...
    elif line.startswith("DONE:"):
        break
    elif line.startswith("ERROR:"):
        print("发生错误", line)
        break
```

### 2. 判断题 (尚未开放 HTTP)
已有: 业务逻辑类 `api/judge_handler.py`
缺失: 对应路由 (Blueprint)。参考实现：
```python
# routes/judge_routes.py (示例)
from flask import Blueprint, request, jsonify
from flask import current_app
judge_bp = Blueprint('judge', __name__)

@judge_bp.route('/api/judge', methods=['POST'])
def judge():
    data = request.get_json() or {}
    question = data.get('question','').strip()
    thinking = str(data.get('thinking','true')).lower() == 'true'
    if not question:
        return jsonify({"type":"error","content":"问题不能为空"}), 400
    llm = current_app.llm_service.get_client(data.get('model_id'))
    handler = current_app.judge_handler
    results = []
    for item in handler.process(question, thinking, llm):
        results.append(item)
    return jsonify(results)
```
并在 `app.py` 中 `from routes import judge_bp` 后 `app.register_blueprint(judge_bp)`。

## 🔄 检索与生成流程概述
1. 文档加载 & 切分 (`KnowledgeService` + `DocumentProcessor`)
2. 索引构建 (`VectorStoreIndex` + 持久化)
3. 检索 (`HybridRetriever` = 向量 + BM25 + RRF)
4. 初筛 Top-K 送入 Reranker (`SentenceTransformerRerank`)
5. 阈值过滤 + 截断到 `rerank_top_n`
6. 组装上下文 Prompt，调用 LLM (`LLMStreamWrapper.stream`)
7. SSE 流式输出内容与来源 JSON
8. 记录日志 (`utils.QALogger`)

## 🧪 测试建议 (尚未集成)
可增加：
- 单元测试：检索结果数量、Rerank 过滤逻辑
- 集成测试：模拟 /api/knowledge_chat 请求，断言 DONE 标记出现
- 回归测试：知识库变更后哈希差异触发重建

## 🔧 扩展指南
### 添加新的 LLM 端点
```python
LLM_ENDPOINTS = {
  "new_model": {
    "api_base_url": "http://.../v1",
    "access_token": "",
    "llm_model_name": "model_name"
  }
}
```
### 添加新的 API 路由
1. 创建 Blueprint 文件
2. 注入依赖 (`current_app.<service_or_handler>`) 
3. 在 `app.py` 注册

### 添加新的业务处理器
1. 在 `api/` 新建 Handler 类
2. 提供 `process()` 生成器或直接返回结构
3. 路由中调用并组织返回格式

## 📝 代码规范
- 类名: PascalCase (`LLMService`)
- 函数: snake_case (`create_app`)
- 常量: UPPER_CASE (`SERVER_PORT`)
- 私有: `_internal_method`
- 使用类型提示 & 文档字符串

## 🧾 日志规范
- 运行日志: 标准输出 (可用进程管理工具重定向)
- 业务问答日志: `qa_logs/qa_log_YYYY-MM-DD.jsonl`
- 每条包含: timestamp / type / question / answer / metadata
- 建议: 增加定期归档与清理（未实现）

## 🔒 最佳实践
1. 配置集中管理；建议后续引入环境变量覆盖
2. 依赖注入而非全局单例（除 Settings 常量）
3. 索引重建基于文件哈希比对
4. LLM 调用设置重试 (`LLM_MAX_RETRIES`)
5. 流式输出便于前端渐进渲染

## ⚙️ 性能与调优建议
| 目标 | 手段 |
|------|------|
| 减少首 Token 延迟 | 预热 Embedding 模型与 LLM，启动后做一次空调用 |
| 提升检索相关性 | 调整 `RETRIEVAL_TOP_K` / `RERANKER_INPUT_TOP_N` / 阈值 |
| 降低内存 | 减少向量维度（更换 Embedding 模型）|
| 快速热更新文档 | 添加接口触发 `KnowledgeService.build_or_load_index()` |
| 横向扩展 | 将检索与生成拆分为独立服务（后续 Roadmap）|

## 🧩 Prompt 模板说明 (节选)
`prompts.json` 中组织为业务域 -> 模式 -> 子键；缺失键会使用代码中的默认回退值。可新增领域，如 `"policy": {...}`，并在 Handler 中调用 `get_prompt("policy.xxx")`。

## ❓ 常见问题 (FAQ)
Q1: 首次启动很慢 / 无输出？
- 需完成 Embedding 生成与索引构建；观察日志。

Q2: 日志出现“知识库为空”？
- 检查 `KNOWLEDGE_BASE_DIR` 目录是否有可读文件。

Q3: SSE 响应被浏览器缓存？
- 前端需使用 `EventSource` 或禁用缓存的 fetch；设置 `Cache-Control: no-cache`。

Q4: 想切换模型？
- 请求体传 `model_id`；若未配置将回退默认模型。

Q5: 如何新增判断题 HTTP API？
- 参考上文“判断题 (尚未开放 HTTP)”示例添加路由。

## 🛣️ Roadmap (建议)
- [ ] 提供 `/api/judge` SSE/JSON 版接口
- [ ] 增加环境变量覆盖配置
- [ ] 增加向量存储 (Faiss / Milvus) 抽象层
- [ ] 引入缓存层 (检索结果 / Prompt 模板)
- [ ] 增加文档增量更新接口（只重建变更部分）
- [ ] 前端 UI 优化（显示来源权重、思考折叠）
- [ ] 完整测试套件 (pytest + 假数据)
- [ ] Docker 化部署示例

## 🔐 安全注意事项
- 当前未做认证/鉴权；生产需增加 Token / IP 白名单
- 未限制并发与速率；建议接入反向代理 (Nginx + 限流)
- LLM 输出未做敏感信息过滤；如涉政/涉隐需接入审查模块

## ♻️ 迁移 & 回滚
- 旧版 `appV-inuse.py`、`rag_core.py` 已模块化解构
- 如需回滚，可直接运行旧脚本（但不兼容新索引结构）

## 🧾 许可证
- 本目录未声明 license；若要开源建议补充 `LICENSE` 文件（MIT / Apache-2.0 等）。

## ✅ 快速自检清单
- [ ] 已放置知识库文件
- [ ] 已安装依赖并能导入 `llama_index`
- [ ] 启动日志显示“混合检索器创建成功”
- [ ] `/api/knowledge_chat` 返回流包含 `DONE:`
- [ ] 日志目录产生日志文件

---
如发现文档仍有缺失或需补充的特定章节（部署/Docker/监控/CI 等），可在此基础上继续扩展。
