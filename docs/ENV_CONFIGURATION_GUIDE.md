# 环境变量配置指南

## 概述

本项目使用 `.env` 文件管理所有环境变量配置。所有配置项都有合理的默认值，可以根据实际需求进行调整。

## 配置文件位置

```
llm_pro/
  ├── .env              # 环境变量配置文件
  └── config/
      └── settings.py   # 读取环境变量的配置类
```

## 配置分类

### 1. Spring Boot 认证服务

```bash
# Spring Boot 后端的基础 URL（用于 JWT Token 验证）
SPRING_BOOT_URL=http://localhost:3000
```

**说明**：如果使用JWT认证，需要配置Spring Boot后端地址。

---

### 2. 意图分类器

```bash
# 是否启用意图分类器
ENABLE_INTENT_CLASSIFIER=false

# 意图分类使用的LLM ID
INTENT_CLASSIFIER_LLM_ID=qwen3-32b

# 意图分类超时时间（秒）
INTENT_CLASSIFIER_TIMEOUT=5
```

**功能**：自动判断用户问题是否需要调用免签知识库、航司知识库或通用库。

**推荐配置**：
- 生产环境：`ENABLE_INTENT_CLASSIFIER=true`
- 开发环境：`ENABLE_INTENT_CLASSIFIER=false`（减少LLM调用）

---

### 3. 子问题分解

#### 基础开关

```bash
# 是否启用子问题分解功能
ENABLE_SUBQUESTION_DECOMPOSITION=false
```

#### 分解参数

```bash
# 最大子问题数量
SUBQUESTION_MAX_DEPTH=3

# 子问题检索最低分数阈值
SUBQUESTION_MIN_SCORE=0.3

# 触发分解的最小查询长度（字符）
SUBQUESTION_COMPLEXITY_THRESHOLD=50

# 用于分解的LLM
SUBQUESTION_DECOMP_LLM_ID=qwen3-32b

# 分解超时时间（秒）
SUBQUESTION_DECOMP_TIMEOUT=10
```

#### 实体检测

```bash
# 启用命名实体检测
SUBQUESTION_ENABLE_ENTITY_CHECK=true

# 触发分解的最小实体数
SUBQUESTION_MIN_ENTITIES=2
```

#### 对话历史压缩（多轮场景）

```bash
# 压缩最近N轮对话
SUBQUESTION_HISTORY_COMPRESS_TURNS=5

# 历史摘要最大token数
SUBQUESTION_HISTORY_MAX_TOKENS=500
```

#### 健康度指标

```bash
# 允许的最大空结果子问题数
SUBQUESTION_MAX_EMPTY_RESULTS=2

# 错误时回退到标准检索
SUBQUESTION_FALLBACK_ON_ERROR=true
```

**使用场景**：
- 复杂长问题：自动分解为多个子问题并行检索
- 多方面查询：如"去泰国免签需要什么条件，有哪些航班？"

**性能影响**：
- 增加延迟：~2-3秒（LLM分解 + 并行检索 + 答案合成）
- 提升召回：复杂问题的答案质量显著提升

**推荐配置**：
```bash
# 生产环境（启用）
ENABLE_SUBQUESTION_DECOMPOSITION=true
SUBQUESTION_COMPLEXITY_THRESHOLD=50
SUBQUESTION_MAX_DEPTH=3

# 开发环境（关闭以加快响应）
ENABLE_SUBQUESTION_DECOMPOSITION=false
```

---

### 4. RRF 融合权重

```bash
# RRF 平滑参数（降低以增加排名差异影响）
RRF_K=10.0

# 向量检索权重
RRF_VECTOR_WEIGHT=0.7

# BM25 检索权重
RRF_BM25_WEIGHT=0.3
```

**说明**：
- `RRF_K`：控制排名差异的影响程度，值越小排名差异影响越大
- 权重总和应为 1.0
- 向量检索适合语义相似，BM25适合关键词匹配

**调优建议**：
- 专业术语多：提高 `RRF_BM25_WEIGHT`
- 语义查询多：提高 `RRF_VECTOR_WEIGHT`
- 向量分数普遍较低：降低 `RRF_K` 到 5-10

---

### 5. RAG 核心参数

```bash
# 向量检索数量
RETRIEVAL_TOP_K=30

# BM25检索数量
RETRIEVAL_TOP_K_BM25=30

# 重排序后返回数量
RERANK_TOP_N=20

# 送入重排序的数量
RERANKER_INPUT_TOP_N=30

# 检索分数阈值
RETRIEVAL_SCORE_THRESHOLD=0.2

# 重排序分数阈值
RERANK_SCORE_THRESHOLD=0.2
```

**调优建议**：
- 召回不足：提高 `RETRIEVAL_TOP_K` 和 `RETRIEVAL_TOP_K_BM25`
- 噪音过多：提高 `RERANK_SCORE_THRESHOLD`
- 性能优化：降低 `RERANKER_INPUT_TOP_N`

---

### 6. 免签知识库配置

```bash
# 免签库检索数量
VISA_FREE_RETRIEVAL_COUNT=5

# 通用库检索数量
GENERAL_RETRIEVAL_COUNT=5
```

**说明**：双库检索时，分别从免签库和通用库检索的数量。

---

### 7. LLM 行为参数

```bash
# LLM请求超时（秒）
LLM_REQUEST_TIMEOUT=1800.0

# LLM上下文窗口
LLM_CONTEXT_WINDOW=32768

# LLM最大生成tokens
LLM_MAX_TOKENS=8192

# LLM最大重试次数
LLM_MAX_RETRIES=2

# 分解任务温度
TEMPERATURE_DISASSEMBLY=0.0

# 分析任务温度
TEMPERATURE_ANALYSIS_ON=0.5
```

**说明**：
- `TEMPERATURE_DISASSEMBLY=0.0`：确定性输出，用于分解、分类等任务
- `TEMPERATURE_ANALYSIS_ON=0.5`：适度创造性，用于分析、回答等任务

---

### 8. 设备配置

```bash
# 设备类型：npu, cpu（默认：自动检测）
# DEVICE=cpu
```

**说明**：
- 注释掉则自动检测NPU
- 强制使用CPU：`DEVICE=cpu`

---

### 9. Qdrant 配置

```bash
# Qdrant主机
QDRANT_HOST=localhost

# Qdrant端口
QDRANT_PORT=6333

# 通用库集合名
QDRANT_COLLECTION=travel_kb
```

**说明**：向量数据库连接配置。

---

### 10. 规则知识库配置

```bash
# 是否启用规则库
ENABLE_RULES_FEATURE=true

# 每次固定注入规则数
RULES_FIXED_INJECT_COUNT=3
```

**功能**：自动注入最相关的业务规则到提示词中。

---

## 快速配置方案

### 方案1：最小配置（开发环境）

```bash
# 只配置必要项，其他使用默认值
SPRING_BOOT_URL=http://localhost:3000
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 方案2：标准配置（测试环境）

```bash
# 启用意图分类
ENABLE_INTENT_CLASSIFIER=true

# 关闭子问题分解（减少延迟）
ENABLE_SUBQUESTION_DECOMPOSITION=false

# 标准RAG参数
RETRIEVAL_TOP_K=30
RERANK_TOP_N=20
```

### 方案3：完整配置（生产环境）

```bash
# 启用所有功能
ENABLE_INTENT_CLASSIFIER=true
ENABLE_SUBQUESTION_DECOMPOSITION=true

# 优化性能
SUBQUESTION_COMPLEXITY_THRESHOLD=60
SUBQUESTION_MAX_DEPTH=3
SUBQUESTION_DECOMP_TIMEOUT=10

# 提高质量
RERANK_SCORE_THRESHOLD=0.3
RRF_K=10.0
```

---

## 配置验证

### 1. 检查配置是否生效

```python
from config import Settings

print(f"意图分类器: {Settings.ENABLE_INTENT_CLASSIFIER}")
print(f"子问题分解: {Settings.ENABLE_SUBQUESTION_DECOMPOSITION}")
print(f"RRF_K: {Settings.RRF_K}")
```

### 2. 查看日志

启动应用后，查看日志中的配置信息：

```
子问题分解器初始化完成 | 状态: 启用 | 引擎: LlamaIndex原生
意图分类器初始化完成 | 状态: 启用
RRF融合参数: k=10.0, vector_weight=0.7, bm25_weight=0.3
```

---

## 常见问题

### Q1: 修改配置后不生效？

**A**: 需要重启应用：
```bash
# 停止应用
Ctrl+C

# 重新启动
python app.py
```

### Q2: 如何临时覆盖配置？

**A**: 使用命令行环境变量：
```bash
ENABLE_SUBQUESTION_DECOMPOSITION=true python app.py
```

### Q3: 配置文件在哪里？

**A**: 
- 环境变量：`.env`
- 配置类：`config/settings.py`
- 文档：`docs/ENV_CONFIGURATION_GUIDE.md`

---

## 性能调优建议

### 降低延迟

```bash
# 关闭子问题分解
ENABLE_SUBQUESTION_DECOMPOSITION=false

# 减少检索数量
RETRIEVAL_TOP_K=20
RERANKER_INPUT_TOP_N=20

# 降低超时时间
INTENT_CLASSIFIER_TIMEOUT=3
```

### 提高质量

```bash
# 启用所有功能
ENABLE_INTENT_CLASSIFIER=true
ENABLE_SUBQUESTION_DECOMPOSITION=true

# 增加检索数量
RETRIEVAL_TOP_K=50
RERANK_TOP_N=30

# 提高分数阈值
RERANK_SCORE_THRESHOLD=0.3
```

### 平衡配置

```bash
# 启用意图分类，关闭子问题分解
ENABLE_INTENT_CLASSIFIER=true
ENABLE_SUBQUESTION_DECOMPOSITION=false

# 标准检索参数
RETRIEVAL_TOP_K=30
RERANK_TOP_N=20
RERANK_SCORE_THRESHOLD=0.2
```

---

## 相关文档

- [子问题分解使用指南](./SUBQUESTION_DECOMPOSITION_GUIDE.md)
- [意图分类器文档](./INTENT_CLASSIFIER_README.md)
- [RRF融合修复说明](./RRF_FUSION_FIX.md)

---

## 更新日志

- 2025-01-XX: 初始版本，包含所有环境变量配置
