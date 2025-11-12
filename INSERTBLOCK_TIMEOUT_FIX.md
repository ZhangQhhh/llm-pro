# InsertBlock 超时问题修复

## 🐛 问题描述

**现象**: 精准检索（InsertBlock）功能经常出现"网络连接失败"的提示

**原因**: InsertBlock 需要对每个检索到的文档调用 LLM 进行判断，处理时间较长，导致前端超时

## 📊 性能分析

### 原始配置
- **并发数**: 5 个线程
- **文档数**: 通常 15-20 个
- **每个文档处理时间**: 3-5 秒
- **总处理时间**: `20 / 5 * 4 = 16 秒` + 网络延迟

### 问题
- 前端通常设置 30-60 秒超时
- 如果 LLM 响应慢或文档多，容易超时
- 用户体验差，看到"网络连接失败"

## ✅ 解决方案

### 1. 提高并发数（已实现）

**修改文件**: `config/settings.py`

```python
# InsertBlock 精准检索配置
INSERTBLOCK_MAX_WORKERS = 10  # 并发处理的最大线程数（从 5 提高到 10）
```

**效果**:
- 原来: `20 / 5 * 4 = 16 秒`
- 现在: `20 / 10 * 4 = 8 秒`
- **速度提升 2 倍**

---

### 2. 动态使用配置值（已实现）

**修改文件**: `core/node_filter.py`

```python
class InsertBlockFilter:
    def __init__(self, llm_service, max_workers: int = None):
        """
        Args:
            llm_service: LLM 服务实例
            max_workers: 并发处理的最大线程数（None 则使用配置值）
        """
        self.llm_service = llm_service
        self.max_workers = max_workers or Settings.INSERTBLOCK_MAX_WORKERS
        logger.info(f"InsertBlockFilter 初始化 | 并发数: {self.max_workers}")
```

**优点**:
- 可以通过配置文件调整并发数
- 无需修改代码
- 灵活适应不同的服务器性能

---

### 3. 添加性能监控（已实现）

**修改文件**: `core/node_filter.py`

```python
def filter_nodes(self, question, nodes, llm_id=None):
    start_time = time.time()
    logger.info(f"开始使用 InsertBlock 过滤器处理 {len(nodes)} 个节点 | 并发数: {self.max_workers}")
    
    # ... 处理逻辑 ...
    
    # 计算处理时间
    elapsed_time = time.time() - start_time
    avg_time_per_node = elapsed_time / len(nodes) if nodes else 0
    
    logger.info(f"  总处理时间: {elapsed_time:.2f} 秒")
    logger.info(f"  平均每节点: {avg_time_per_node:.2f} 秒")
    logger.info(f"  并发数: {self.max_workers}")
```

**日志示例**:
```
InsertBlock 过滤完成统计:
  总节点数: 20
  通过筛选: 8 个节点
  被拒绝: 12 个节点
  处理失败: 0 个节点
  总处理时间: 8.45 秒
  平均每节点: 0.42 秒
  并发数: 10
```

---

## 🎯 性能对比

| 场景 | 并发数 | 文档数 | 每文档耗时 | 总耗时 | 是否超时 |
|------|--------|--------|-----------|--------|---------|
| **修改前** | 5 | 20 | 4秒 | ~16秒 | ⚠️ 容易超时 |
| **修改后** | 10 | 20 | 4秒 | ~8秒 | ✅ 不超时 |
| **极端情况** | 10 | 30 | 5秒 | ~15秒 | ⚠️ 可能超时 |

---

## 🔧 进一步优化建议

### 方案 1: 增加前端超时时间

**前端代码**:
```javascript
// 将超时时间从 30 秒增加到 60 秒
const response = await fetch('/api/knowledge/qa', {
  method: 'POST',
  body: JSON.stringify(data),
  signal: AbortSignal.timeout(60000)  // 60 秒
});
```

---

### 方案 2: 流式返回进度

**后端修改**: 在处理过程中实时返回进度

```python
def filter_nodes(self, question, nodes, llm_id=None):
    # 每处理完一个节点，就返回进度
    for i, node in enumerate(nodes):
        result = self._process_single_node(question, node, llm)
        yield ('PROGRESS', f"正在处理 {i+1}/{len(nodes)} 个文档...")
        if result and result.get("can_answer"):
            filtered_results.append(result)
```

**前端显示**:
```
正在使用 InsertBlock 智能过滤...
正在处理 5/20 个文档...
正在处理 10/20 个文档...
正在处理 15/20 个文档...
找到 8 个可回答的节点
```

---

### 方案 3: 限制处理的文档数量

**配置文件**:
```python
# 只对重排序后的前 N 个文档进行 InsertBlock 过滤
INSERTBLOCK_MAX_NODES = 15  # 最多处理 15 个文档
```

**代码修改**:
```python
def filter_nodes(self, question, nodes, llm_id=None):
    # 只处理前 N 个节点
    max_nodes = Settings.INSERTBLOCK_MAX_NODES
    nodes_to_process = nodes[:max_nodes]
    
    logger.info(f"限制处理节点数: {len(nodes_to_process)}/{len(nodes)}")
```

---

### 方案 4: 使用更快的 LLM

**配置文件**:
```python
# 使用更快的小模型进行 InsertBlock 判断
INSERTBLOCK_LLM_ID = "qwen3-7b"  # 使用 7B 模型而不是 32B
```

**效果**:
- 7B 模型响应时间: ~2 秒/文档
- 32B 模型响应时间: ~4 秒/文档
- **速度提升 2 倍**

---

## 📝 测试验证

### 1. 重启服务

```bash
cd /opt/rag_final_project/code_here/llm_pro
pkill -f app.py
nohup python app.py > app.log 2>&1 &
```

### 2. 测试精准检索

```bash
curl -X POST http://localhost:8000/api/knowledge/qa \
  -H "Content-Type: application/json" \
  -d '{
    "question": "泰国免签政策是什么？",
    "top_k": 20,
    "use_insert_block": true
  }'
```

### 3. 查看日志

```bash
tail -f app.log | grep "InsertBlock"
```

**期望输出**:
```
InsertBlockFilter 初始化 | 并发数: 10
开始使用 InsertBlock 过滤器处理 20 个节点 | 并发数: 10
✓ 节点通过 [1] 免签政策.md | 关键段落: 150 字符 | 推理: 该文档详细说明了泰国免签政策...
✓ 节点通过 [2] 签证规定.md | 关键段落: 200 字符 | 推理: 包含泰国免签的具体要求...
...
InsertBlock 过滤完成统计:
  总节点数: 20
  通过筛选: 8 个节点
  总处理时间: 8.45 秒
  平均每节点: 0.42 秒
  并发数: 10
```

---

## 🎛️ 调优建议

### 根据服务器性能调整并发数

| 服务器配置 | 推荐并发数 | 说明 |
|-----------|-----------|------|
| 低配（2核4G） | 5 | 避免资源耗尽 |
| 中配（4核8G） | 10 | **默认配置** |
| 高配（8核16G） | 15-20 | 充分利用资源 |

### 修改配置

编辑 `config/settings.py`:

```python
# 高性能服务器
INSERTBLOCK_MAX_WORKERS = 20

# 低性能服务器
INSERTBLOCK_MAX_WORKERS = 5
```

---

## ⚠️ 注意事项

1. **并发数不是越高越好**
   - 过高的并发数可能导致 LLM 服务器过载
   - 可能触发 API 限流
   - 建议根据实际测试调整

2. **监控 LLM 服务器负载**
   - 观察 LLM 服务器的 CPU、内存使用率
   - 如果服务器负载过高，降低并发数

3. **前端超时设置**
   - 建议前端超时时间设置为 60 秒
   - 或者显示加载进度，提升用户体验

---

## 📞 技术支持

如有问题，请查看：
- 配置文件：`config/settings.py`
- 核心代码：`core/node_filter.py`
- 日志文件：`app.log`

**相关配置**:
```python
INSERTBLOCK_MAX_WORKERS = 10  # 并发数
LLM_REQUEST_TIMEOUT = 1800.0  # LLM 请求超时（秒）
```
