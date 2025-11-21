# 隐藏知识库完整流程指南

## 📋 概述

隐藏知识库是一个特殊的检索系统，用于题库等需要提升回答准确率但不暴露来源的场景。它的内容会被注入到 LLM 上下文中，但对用户完全不可见。

## 🔄 完整流程

### 1. 初始化阶段
```
app.py 启动
    ↓
knowledge_service.build_or_load_hidden_kb_index()
    ↓
创建独立的 Qdrant collection: "hidden_kb"
    ↓
knowledge_service.create_hidden_kb_retriever()
    ↓
包装为 HiddenKBRetriever
    ↓
传递给 KnowledgeHandler
```

### 2. 检索阶段
```
用户提问
    ↓
KnowledgeHandler._retrieve_and_rerank()
    ↓
hidden_kb_retriever.retrieve(question)
    ↓
记录检索开始日志 (logs/hidden_logs/)
    ↓
调用底层 HybridRetriever 检索
    ↓
标记节点为隐藏 (is_hidden=True)
    ↓
记录检索结果日志
    ↓
返回隐藏节点列表
```

### 3. 上下文注入阶段
```
build_hidden_kb_context(hidden_nodes)
    ↓
过滤低分节点 (HIDDEN_KB_MIN_SCORE=0.3)
    ↓
构建隐藏上下文格式: 【参考资料 i】内容
    ↓
记录上下文注入日志
    ↓
注入到 LLM Prompt 中
```

### 4. LLM 处理阶段
```
LLM 接收包含隐藏知识库的上下文
    ↓
基于隐藏内容回答问题
    ↓
不提及隐藏知识库来源
    ↓
前端只显示普通知识库来源
```

## 📊 日志系统

### 日志文件位置
```
logs/hidden_logs/
├── hidden_kb_2025-11-18.log    # 文本格式日志
└── hidden_kb_2025-11-18.json   # JSON 格式详细日志
```

### 日志类型

#### 1. 检索开始日志
```json
{
  "timestamp": "2025-11-18T15:30:00",
  "type": "retrieval_start",
  "kb_name": "hidden_kb",
  "query": "J2签证持有人可以入境吗？",
  "query_length": 12
}
```

#### 2. 检索结果日志
```json
{
  "timestamp": "2025-11-18T15:30:01",
  "type": "retrieval_result",
  "kb_name": "hidden_kb",
  "query": "J2签证持有人可以入境吗？",
  "result_count": 3,
  "nodes": [
    {
      "rank": 1,
      "score": 0.8567,
      "content_length": 245,
      "content_preview": "根据签证管理条例，J2签证持有人...",
      "doc_id": "doc_123",
      "file_name": "签证管理规定.txt",
      "is_hidden": true
    }
  ]
}
```

#### 3. 上下文注入日志
```json
{
  "timestamp": "2025-11-18T15:30:02",
  "type": "context_injection",
  "query": "隐藏知识库上下文构建",
  "injected_count": 3,
  "context_length": 1256,
  "average_score": 0.7434,
  "injected_nodes": [...]
}
```

## 🛠️ 查看和分析工具

### 1. 快速查看日志
```bash
# 查看今天的日志
python scripts/view_hidden_kb_logs.py --today

# 搜索特定关键词
python scripts/view_hidden_kb_logs.py --search "J2签证"

# 列出所有日志文件
python scripts/view_hidden_kb_logs.py --list
```

### 2. 详细分析报告
```bash
# 生成每日统计报告
python scripts/analyze_hidden_kb_logs.py

# 显示详细查询信息
python scripts/analyze_hidden_kb_logs.py --detail

# 输出 JSON 格式
python scripts/analyze_hidden_kb_logs.py --json

# 分析指定日期
python scripts/analyze_hidden_kb_logs.py --date 2025-11-18
```

## ⚙️ 配置参数

### 核心配置 (.env)
```bash
# 是否启用隐藏知识库
ENABLE_HIDDEN_KB_FEATURE=true

# 隐藏知识库目录
HIDDEN_KB_DIR="/opt/rag_final_project/hidden_knowledge_base"

# 检索参数
HIDDEN_KB_RETRIEVAL_COUNT=5      # 最终注入数量
HIDDEN_KB_MIN_SCORE=0.3          # 最低分数阈值
HIDDEN_KB_INJECT_MODE="silent"   # silent=完全隐藏
```

## 🔍 调试技巧

### 1. 检查是否启用
```bash
# 查看环境变量
echo $ENABLE_HIDDEN_KB_FEATURE

# 查看日志文件是否存在
ls -la logs/hidden_logs/
```

### 2. 验证检索效果
```bash
# 查看检索日志
python scripts/view_hidden_kb_logs.py --search "检索结果"

# 分析检索成功率
python scripts/analyze_hidden_kb_logs.py --detail
```

### 3. 调试注入问题
```bash
# 查看注入日志
python scripts/view_hidden_kb_logs.py --search "上下文注入"

# 检查分数阈值
grep "分数低于阈值" logs/hidden_logs/hidden_kb_*.log
```

## 📈 性能监控

### 关键指标
- **检索成功率**: 成功检索次数 / 总检索次数
- **平均检索分数**: 所有检索结果的平均相关性分数
- **注入率**: 注入次数 / 检索次数
- **热门查询**: 最常被查询的问题

### 监控命令
```bash
# 每日统计
python scripts/analyze_hidden_kb_logs.py

# 实时监控
tail -f logs/hidden_logs/hidden_kb_$(date +%Y-%m-%d).log
```

## 🚨 常见问题

### Q1: 隐藏知识库没有被调用
**检查步骤**:
1. 确认 `ENABLE_HIDDEN_KB_FEATURE=true`
2. 查看日志目录是否有文件生成
3. 检查隐藏知识库文件是否存在

### Q2: 检索结果为空
**可能原因**:
1. 隐藏知识库文件为空
2. 查询与隐藏知识库内容不匹配
3. 分数阈值设置过高

**解决方法**:
```bash
# 降低分数阈值
HIDDEN_KB_MIN_SCORE=0.1

# 查看检索详情
python scripts/view_hidden_kb_logs.py --search "未检索到相关内容"
```

### Q3: 上下文没有被注入
**检查步骤**:
1. 查看是否有 "上下文注入" 日志
2. 检查分数是否低于阈值
3. 确认检索到了有效结果

## 📝 使用示例

### 场景1: 验证题库检索
```bash
# 1. 提问关于题库内容的问题
# 2. 查看检索日志
python scripts/view_hidden_kb_logs.py --today

# 3. 分析检索效果
python scripts/analyze_hidden_kb_logs.py --detail
```

### 场景2: 监控日常使用
```bash
# 1. 设置每日分析脚本
crontab -e
# 添加: 0 9 * * * cd /path/to/project && python scripts/analyze_hidden_kb_logs.py

# 2. 查看一周趋势
python scripts/analyze_hidden_kb_logs.py --date $(date -d '7 days ago' +%Y-%m-%d)
```

---

通过这个完整的日志和分析系统，你可以清楚地了解隐藏知识库的每一次调用和效果！
