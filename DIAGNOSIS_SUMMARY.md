# 免签功能得分降低问题 - 诊断总结

## 📊 当前发现

### 1. 测试脚本结果
- ✅ 初始检索得分一致（0.0306）
- ✅ 检索节点数一致（48个）
- ✅ Top1内容一致
- ❓ **但你在实际使用中看到重排序后得分降低**

### 2. 可能的原因

#### 原因 A：Reranker 的 top_n 限制
```python
# services/embedding_service.py
self.reranker = SentenceTransformerRerank(
    model=AppSettings.RERANKER_MODEL_PATH,
    top_n=AppSettings.RERANK_TOP_N,  # 固定为 15
    device=AppSettings.DEVICE
)
```

**问题**：Reranker 初始化时 `top_n=15`，这意味着无论输入多少节点，**最多只返回15个**。

但这不应该影响得分本身，只影响返回数量。

#### 原因 B：全局状态污染（尚未证实）
- 两个知识库共享同一个 Qdrant 客户端
- 两个知识库共享同一个 `Settings.embed_model`
- 可能存在某种缓存或状态污染

#### 原因 C：你看到的是多知识库检索的得分
- 如果意图分类器判定为免签问题，会走多知识库检索
- 多知识库检索的得分计算逻辑不同
- **这是正常的，不是bug**

## 🔬 诊断步骤

### 步骤 1：运行 Reranker 诊断脚本

```bash
# 开启免签功能
export ENABLE_VISA_FREE_FEATURE=true
python diagnose_reranker.py
```

**关键观察点**：
1. 构建免签知识库前后，Reranker 对象ID是否变化
2. 构建免签知识库前后，相同问题的重排序得分是否变化
3. 如果得分变化，说明存在状态污染

### 步骤 2：运行完整对比测试

```bash
# 测试 1：关闭免签功能
export ENABLE_VISA_FREE_FEATURE=false
python test_score_comparison.py > result_false.log 2>&1

# 测试 2：开启免签功能
export ENABLE_VISA_FREE_FEATURE=true
python test_score_comparison.py > result_true.log 2>&1

# 对比结果
diff result_false.log result_true.log
```

**关键对比点**：
- 初始检索得分是否一致
- **重排序后得分是否一致** ← 最重要！
- 最终返回节点数是否一致

### 步骤 3：检查实际应用日志

在实际应用中，用**同一个非免签问题**测试：

```bash
# 关闭免签功能，重启服务
export ENABLE_VISA_FREE_FEATURE=false
python app.py

# 提问，记录日志中的：
# [DEBUG] 单知识库初始检索Top5得分: ...
# [DEBUG] 单知识库重排序后Top5得分: ...

# 开启免签功能，重启服务
export ENABLE_VISA_FREE_FEATURE=true
python app.py

# 提问相同问题，记录日志
# 对比两次的重排序后得分
```

## 🎯 判断标准

### 情况 1：得分确实降低
如果 `diagnose_reranker.py` 显示：
```
构建免签知识库前:
  - 最高分: 0.9843

构建免签知识库后:
  - 最高分: 0.6123  ← 显著降低

得分差异: -0.3720
⚠️ 得分变化: -0.3720
```

**说明**：存在状态污染，需要修复。

**修复方案**：
1. 为每个知识库创建独立的 Qdrant 客户端
2. 或者延迟初始化免签检索器

### 情况 2：得分一致
如果 `diagnose_reranker.py` 显示：
```
构建免签知识库前:
  - 最高分: 0.9843

构建免签知识库后:
  - 最高分: 0.9843  ← 一致

得分差异: 0.0000
✅ 得分一致，Reranker 未受影响
```

**说明**：系统工作正常，你看到的得分降低可能是：
1. 触发了多知识库检索（这是正常的）
2. 或者是不同问题的对比（不是同一个问题）

## 📋 下一步行动

1. **立即执行**：
   ```bash
   python diagnose_reranker.py
   ```

2. **查看输出**，特别是 "对比分析" 部分

3. **根据结果**：
   - 如果得分降低 → 实施修复方案
   - 如果得分一致 → 检查是否误判问题

## 🔧 修复方案（如果需要）

### 方案 1：独立 Qdrant 客户端

```python
# services/knowledge_service.py
class KnowledgeService:
    def __init__(self, llm):
        # 通用知识库客户端
        self.qdrant_client = QdrantClient(
            host=AppSettings.QDRANT_HOST,
            port=AppSettings.QDRANT_PORT
        )
        
        # 免签知识库客户端（独立）
        self.visa_free_qdrant_client = QdrantClient(
            host=AppSettings.QDRANT_HOST,
            port=AppSettings.QDRANT_PORT
        )
```

### 方案 2：延迟初始化

```python
# app.py
# 不在启动时创建免签检索器
if Settings.ENABLE_VISA_FREE_FEATURE and visa_free_index and visa_free_nodes:
    # 只保存索引和节点
    knowledge_service.visa_free_index = visa_free_index
    knowledge_service.visa_free_nodes = visa_free_nodes
    logger.info("免签知识库索引已加载，检索器将按需创建")
    # 不调用 create_visa_free_retriever()
```

## 📞 需要帮助？

如果诊断脚本显示得分降低，请提供：
1. `diagnose_reranker.py` 的完整输出
2. 得分差异的具体数值
3. 是否所有问题都受影响，还是只有特定问题

我会根据具体情况提供针对性的修复方案。
