# 意图路由策略修复 - 确保通用库始终被检索

## 修复日期
2025-01-21

## 问题描述
原有的意图分类器在识别到免签或航司问题时，只检索对应的专业知识库，不检索通用知识库，导致信息不全面。

## 用户需求（4种情况）

1. **识别到免签问题** → 检索免签知识库 + 通用知识库
2. **识别到航司问题** → 检索航司知识库 + 通用知识库
3. **识别到免签+航司问题** → 三库检索（航司库 + 免签库 + 通用库）
4. **非免签非航司通用问题** → 只检索通用知识库

**核心原则：通用库在任何情况下都会被检索（除了纯通用问题）**

## 修复方案

### 1. 更新意图分类器提示词 (`prompts.py`)

#### 分类类别
- `airline_visa_free` → 航司库 + 免签库 + 通用库（三库）
- `visa_free` → 免签库 + 通用库
- `airline` → 航司库 + 通用库
- `general` → 仅通用库

#### 检索策略说明
在每个分类类别中明确标注检索策略，确保LLM理解每种分类对应的检索范围。

```python
### 1. 组合类型 (airline_visa_free)
- **[检索策略]**：返回 `airline_visa_free` 表示三库检索（航司库 + 免签库 + 通用库）。

### 2. 航司相关 (airline)
- **[检索策略]**：返回 `airline` 表示检索航司库 + 通用库（通用库保底）。

### 3. 免签相关 (visa_free)
- **[检索策略]**：返回 `visa_free` 表示检索免签库 + 通用库（通用库保底）。

### 4. 通用问题 (general)
- 仅检索通用库
```

### 2. 更新路由逻辑 (`knowledge_handler.py`)

#### 智能路由选择检索器
```python
# 根据策略选择检索器（确保通用库始终被检索）
if strategy == "airline_visa_free" and self.multi_kb_retriever:
    # 三库检索（航司库 + 免签库 + 通用库）
    selected_retriever = self.multi_kb_retriever
elif strategy == "visa_free" and self.multi_kb_retriever:
    # 双库检索（免签库 + 通用库）
    selected_retriever = self.multi_kb_retriever
elif strategy == "airline" and self.multi_kb_retriever:
    # 双库检索（航司库 + 通用库）
    selected_retriever = self.multi_kb_retriever
else:
    # 只用通用库（默认）
    selected_retriever = self.retriever
```

#### 根据策略调用不同的检索方法
```python
if isinstance(retriever, MultiKBRetriever):
    # 根据策略调用不同的检索方法
    if strategy == "airline_visa_free":
        # 三库检索
        retrieved_nodes = retriever.retrieve_from_all_three(question)
    elif strategy == "visa_free":
        # 免签库 + 通用库
        retrieved_nodes = retriever.retrieve_from_both(question)
    elif strategy == "airline":
        # 航司库 + 通用库
        retrieved_nodes = retriever.retrieve_airline_only(question)
    else:
        # 默认：根据可用检索器自动选择
        retrieved_nodes = retriever.retrieve(question)
```

### 3. MultiKBRetriever 方法映射

| 策略 | 调用方法 | 检索范围 | 固定返回数量 |
|------|---------|---------|------------|
| `airline_visa_free` | `retrieve_from_all_three()` | 航司库 + 免签库 + 通用库 | **20条**（固定） |
| `visa_free` | `retrieve_from_both()` | 免签库 + 通用库 | **15条**（固定） |
| `airline` | `retrieve_airline_only()` | 航司库 + 通用库 | **15条**（固定） |
| `general` | 直接使用 `self.retriever` | 仅通用库 | **前端参数**（默认15条） |

## 核心改动文件

1. **prompts.py**
   - 更新意图分类器系统提示词
   - 明确每种分类的检索策略
   - 添加检索策略总结说明

2. **knowledge_handler.py**
   - 修改 `_smart_retrieve_and_rerank()` 方法
   - 修改 `_retrieve_and_rerank_with_retriever()` 方法
   - 添加 `strategy` 参数传递
   - 根据策略调用不同的检索方法
   - **根据策略使用固定返回数量或前端参数**

3. **intent_classifier.py**
   - 保持原有解析逻辑（返回 visa_free, airline, airline_visa_free, general）
   - 确保 `rewrite_question()` 方法支持所有需要改写的策略

4. **settings.py**
   - 添加多库检索固定返回数量配置
   - 通用问题默认改为15条

## 验证方法

### 1. 测试免签问题
```python
question = "去泰国旅游需要签证吗？"
# 预期：意图分类 = visa_free
# 预期：检索免签库 + 通用库
```

### 2. 测试航司问题
```python
question = "什么是民航双边协议？"
# 预期：意图分类 = airline
# 预期：检索航司库 + 通用库
```

### 3. 测试组合问题
```python
question = "执行飞往泰国航班的机组人员需要签证吗？"
# 预期：意图分类 = airline_visa_free
# 预期：检索航司库 + 免签库 + 通用库
```

### 4. 测试通用问题
```python
question = "如何办理护照？"
# 预期：意图分类 = general
# 预期：仅检索通用库
```

## 日志验证

启用意图分类器后，查看日志中的以下关键信息：

```
[智能路由] 意图分类结果: visa_free
[智能路由] 策略: visa_free → 双库检索（免签库 + 通用库）
[融合策略] BM25 + 向量检索 | 策略: visa_free
[双库检索] 查询: ...
[双库检索] 免签库检索完成 | 返回 X 条
[双库检索] 通用库检索完成 | 返回 Y 条
[双库检索] 合并完成 | 最终返回 Z 条
```

## 配置要求

确保以下环境变量已设置：

```bash
# 启用意图分类器
export ENABLE_INTENT_CLASSIFIER=true

# 启用免签知识库
export ENABLE_VISA_FREE_FEATURE=true

# 启用航司知识库
export ENABLE_AIRLINE_FEATURE=true
```

## 返回数量控制策略（重要更新）

### 前端参数 `rerank_top_n` 的作用范围

| 策略 | 是否受前端参数控制 | 返回数量 | 说明 |
|------|------------------|---------|------|
| `general` | ✅ **是** | 前端参数（默认15条） | 通用问题使用前端传入的参数 |
| `visa_free` | ❌ **否** | **固定15条** | 免签问题固定返回15条 |
| `airline` | ❌ **否** | **固定15条** | 航司问题固定返回15条 |
| `airline_visa_free` | ❌ **否** | **固定20条** | 组合问题固定返回20条 |

### 配置参数（settings.py）

```python
# 通用问题默认返回数量（可被前端参数覆盖）
RERANK_TOP_N = 15

# 多库检索固定返回数量（不受前端参数控制）
VISA_FREE_STRATEGY_RETURN_COUNT = 15    # visa_free策略固定返回15条
AIRLINE_STRATEGY_RETURN_COUNT = 15      # airline策略固定返回15条
AIRLINE_VISA_FREE_RETURN_COUNT = 20     # airline_visa_free策略固定返回20条
```

## 注意事项

1. **通用库保底**：所有非通用策略都会包含通用库检索，确保信息全面
2. **策略传递**：strategy 参数需要从路由层传递到检索层
3. **去重机制**：MultiKBRetriever 的所有方法都包含去重逻辑（按 node_id）
4. **分数排序**：最终结果按相关性分数排序，确保高质量文档优先
5. **固定返回数量**：多库检索策略使用固定配置，不受前端参数影响，确保返回足够的参考文档

## 后续优化建议

1. 可以根据实际使用情况调整各库的检索数量配置
2. 可以添加更多的意图分类类型（如 airline_general）
3. 可以优化检索策略，根据得分动态调整各库的权重
