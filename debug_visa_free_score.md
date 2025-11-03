# 免签功能得分降低问题 - Debug 指南

## 问题描述
当 `ENABLE_VISA_FREE_FEATURE=true` 时，同一个问题的知识库检索得分显著降低。

## 可能的根因

### 1. **双重重排序问题**（最可能）
- `multi_kb_retriever.retrieve_from_both()` 返回的是**初始检索得分**（embedding 相似度）
- 然后在 `_retrieve_and_rerank_multi_kb()` 中又进行了**第二次重排序**
- 两次排序可能导致得分计算混乱

### 2. **检索数量配置冲突**
- 单知识库：`RETRIEVAL_TOP_K = 30`
- 多知识库：免签5条 + 通用5条 + 综合5条 = 15条
- 送入 Reranker 的数量：`RERANKER_INPUT_TOP_N = 30`
- **问题**：多知识库只返回15条，但配置要求送入30条重排

### 3. **分数来源不一致**
- 单知识库：embedding 分数 → reranker 分数
- 多知识库：embedding 分数（两个库混合）→ reranker 分数
- 混合后的 embedding 分数可能不具有可比性

## Debug 步骤

### 步骤 1：对比日志输出

用**同一个问题**分别测试：

#### 测试 A：关闭免签功能
```bash
export ENABLE_VISA_FREE_FEATURE=false
# 重启服务，提问，观察日志
```

观察日志中的：
```
[DEBUG] 单知识库初始检索Top5得分: 0.8567, 0.8234, ...
[DEBUG] 单知识库重排序后Top5得分: 0.9123, 0.8987, ...
[DEBUG] 单知识库阈值过滤后Top5得分: 0.9123, 0.8987, ...
```

#### 测试 B：开启免签功能
```bash
export ENABLE_VISA_FREE_FEATURE=true
# 重启服务，提问相同问题，观察日志
```

观察日志中的：
```
检索策略执行完成:
  - 免签库Top5: 5条 | 分数: 0.8567, 0.8234, ...
  - 通用库Top5: 5条 | 分数: 0.8123, 0.7987, ...
  - 综合Top5: 5条 | 分数: 0.7234, 0.7123, ...

[DEBUG] 多知识库初始检索Top5得分: 0.8567, 0.8234, ...
[DEBUG] 重排序后Top5得分: 0.6123, 0.5987, ...  ← 注意这里！
[DEBUG] 阈值过滤后Top5得分: 0.6123, 0.5987, ...
```

### 步骤 2：检查得分变化

对比以下关键指标：

| 指标 | 单知识库 | 多知识库 | 差异 |
|------|---------|---------|------|
| 初始检索最高分 | ? | ? | ? |
| 重排序后最高分 | ? | ? | ? |
| 阈值过滤后数量 | ? | ? | ? |

### 步骤 3：验证假设

#### 假设 1：初始检索得分就不同
- **原因**：两个知识库的文档分布不同，导致 embedding 分数偏低
- **验证**：对比 `初始检索Top5得分`
- **解决**：调整检索策略，优先使用高分库

#### 假设 2：重排序导致得分降低
- **原因**：混合来源的文档送入 Reranker 后，得分计算方式不同
- **验证**：对比 `重排序后Top5得分`
- **解决**：分别重排序后再合并，或调整重排序逻辑

#### 假设 3：阈值过滤过于严格
- **原因**：`RERANK_SCORE_THRESHOLD = 0.2` 对多知识库不适用
- **验证**：对比 `阈值过滤后数量`
- **解决**：为多知识库设置独立的阈值

## 推荐的修复方案

### 方案 1：分别重排序后再合并（推荐）

```python
def _retrieve_and_rerank_multi_kb(self, question: str, rerank_top_n: int):
    # 1. 分别从两个知识库检索
    visa_nodes = self.multi_kb_retriever.visa_free_retriever.retrieve(query_bundle)
    general_nodes = self.multi_kb_retriever.general_retriever.retrieve(query_bundle)
    
    # 2. 分别重排序
    visa_reranked = self.reranker.postprocess_nodes(visa_nodes[:15], query_bundle)
    general_reranked = self.reranker.postprocess_nodes(general_nodes[:15], query_bundle)
    
    # 3. 合并并按重排序分数排序
    merged = visa_reranked + general_reranked
    merged.sort(key=lambda x: x.score, reverse=True)
    
    # 4. 阈值过滤
    final_nodes = [n for n in merged if n.score >= threshold]
    return final_nodes[:rerank_top_n]
```

### 方案 2：直接使用初始检索结果（不重排序）

```python
def _retrieve_and_rerank_multi_kb(self, question: str, rerank_top_n: int):
    # 直接使用 retrieve_from_both 的结果，不再重排序
    query_bundle = QueryBundle(question)
    retrieved_nodes = self.multi_kb_retriever.retrieve_from_both(query_bundle)
    
    # 只做阈值过滤（使用更低的阈值）
    threshold = 0.1  # 降低阈值
    final_nodes = [n for n in retrieved_nodes if n.score >= threshold]
    return final_nodes[:rerank_top_n]
```

### 方案 3：在 retrieve_from_both 内部完成重排序

修改 `multi_kb_retriever.py`，在合并后立即重排序：

```python
def retrieve_from_both(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
    # ... 现有的检索和合并逻辑 ...
    
    # 在合并后立即重排序
    if self.reranker:
        merged_results = self.reranker.postprocess_nodes(
            merged_results[:30],  # 取前30个送入重排
            query_bundle=query_bundle
        )
    
    return merged_results
```

## 测试清单

- [ ] 用相同问题测试单知识库和多知识库
- [ ] 记录并对比所有阶段的得分
- [ ] 确认得分降低发生在哪个阶段
- [ ] 根据发现选择合适的修复方案
- [ ] 验证修复后得分是否恢复正常
- [ ] 测试多个不同类型的问题

## 相关配置

```python
# settings.py
RETRIEVAL_TOP_K = 30                    # 初始检索数量
RERANKER_INPUT_TOP_N = 30               # 送入重排序的数量
RERANK_TOP_N = 15                       # 重排序后返回数量
RERANK_SCORE_THRESHOLD = 0.2            # 重排序分数阈值

VISA_FREE_RETRIEVAL_COUNT = 5           # 免签库检索数量
GENERAL_RETRIEVAL_COUNT = 5             # 通用库检索数量
```

## 预期结果

修复后，多知识库的得分应该：
- **初始检索得分**：与单知识库相当或更高（因为有两个库）
- **重排序后得分**：与单知识库相当
- **最终返回数量**：不应该因为阈值过滤而大幅减少
