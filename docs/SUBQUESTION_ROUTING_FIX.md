# 子问题分解与意图路由集成修复

## 修复的问题

### 问题1：子问题分解绕过意图分类和多库路由 ✅

**原问题：**
- `_smart_retrieve_and_rerank()` 在意图分类**之前**就尝试子问题分解
- 一旦分解成功，直接返回结果，意图分类和多库路由永远不会执行
- `SubQuestionDecomposer` 始终使用初始化时注入的通用 `HybridRetriever`
- 复杂长问越容易触发分解，越无法命中专库（免签库、航司库）
- 与既有"按意图路由"能力相冲突

**修复方案：**
1. **调整执行顺序**：意图分类 → 选择检索器 → 子问题分解
2. **动态retriever传递**：让 `SubQuestionDecomposer` 接受路由后的检索器

**修改文件：**
- `api/knowledge_handler.py` (lines 1354-1427)
- `core/sub_question_decomposer.py` (lines 202-546)

---

### 问题2：答案合成功能未被调用 ✅

**原问题：**
- `retrieve_with_decomposition()` 生成了 `sub_answers`
- `synthesize_answer()` 方法已实现
- 但全局没有任何调用，功能完全未生效
- 文档宣称的"合成子问题答案"无法实现

**修复方案：**
在检索完成后，检测 `metadata['sub_answers']`，自动调用 `synthesize_answer()` 生成合成答案。

**修改文件：**
- `api/knowledge_handler.py` (lines 329-341, 1429-1441)

---

## 详细修复

### 1. SubQuestionDecomposer支持动态retriever

#### 修改 `retrieve_with_decomposition()`

**位置**：`core/sub_question_decomposer.py` (lines 202-222)

```python
def retrieve_with_decomposition(
    self,
    query: str,
    rerank_top_n: int,
    conversation_history: Optional[List[Dict]] = None,
    retriever=None  # 新增：可选的检索器参数
) -> Tuple[List, Dict]:
    """
    使用子问题分解进行检索
    
    Args:
        query: 用户查询
        rerank_top_n: 重排序返回数量
        conversation_history: 对话历史
        retriever: 可选的检索器（用于意图路由后的专库检索）
    """
    # 使用传入的retriever或默认retriever
    active_retriever = retriever if retriever is not None else self.retriever
    
    # ... 后续使用 active_retriever 进行检索
```

#### 更新所有子方法

**修改的方法：**
- `_standard_retrieve(query, rerank_top_n, retriever=None)` - line 457
- `_parallel_retrieve_subquestions(sub_questions, rerank_top_n, retriever=None)` - line 488
- `_retrieve_single_subquestion(sub_question, rerank_top_n, retriever=None)` - line 534

**核心改动：**
```python
# 所有检索方法都接受可选的retriever参数
active_retriever = retriever if retriever is not None else self.retriever
retrieved_nodes = active_retriever.retrieve(query)
```

---

### 2. 调整KnowledgeHandler执行顺序

#### 修改 `_smart_retrieve_and_rerank()`

**位置**：`api/knowledge_handler.py` (lines 1354-1427)

**修改前流程：**
```
1. 尝试子问题分解（使用通用retriever）
   ↓ 如果成功，直接返回
2. ❌ 意图分类（永远不会执行）
3. ❌ 选择检索器（永远不会执行）
```

**修改后流程：**
```
1. 意图分类（如果启用）
   ↓
2. 根据策略选择检索器
   - both → multi_kb_retriever（双库）
   - visa_free → visa_free_retriever（免签库）
   - general → retriever（通用库）
   ↓
3. 尝试子问题分解（使用选中的检索器）
   ↓
4. 标准检索（如果分解失败或未触发）
```

**关键代码：**
```python
# 1. 意图分类
strategy = "general"
if self.intent_classifier:
    strategy = self.intent_classifier.classify(question)

# 2. 选择检索器
if strategy == "both" and self.multi_kb_retriever:
    selected_retriever = self.multi_kb_retriever
elif strategy == "visa_free" and self.visa_free_retriever:
    selected_retriever = self.visa_free_retriever
else:
    selected_retriever = self.retriever

# 3. 子问题分解（使用选中的检索器）
if self.sub_question_decomposer and self.sub_question_decomposer.enabled:
    nodes, metadata = self.sub_question_decomposer.retrieve_with_decomposition(
        query=question,
        rerank_top_n=rerank_top_n,
        conversation_history=conversation_history,
        retriever=selected_retriever  # 传入路由后的检索器
    )
    if metadata.get('decomposed'):
        logger.info(f"使用库: {strategy}")
        return nodes

# 4. 标准检索
return self._retrieve_and_rerank_with_retriever(question, rerank_top_n, selected_retriever)
```

---

### 3. 实现答案合成调用

#### 单轮路径

**位置**：`api/knowledge_handler.py` (lines 1429-1441)

```python
if metadata.get('decomposed'):
    logger.info(f"[子问题检索] 分解检索完成 | 使用库: {strategy}")
    
    # 可选：生成子问题答案合成
    if metadata.get('sub_answers') and len(metadata['sub_answers']) > 0:
        try:
            synthesized_answer = self.sub_question_decomposer.synthesize_answer(
                original_query=question,
                sub_answers=metadata['sub_answers']
            )
            if synthesized_answer:
                metadata['synthesized_answer'] = synthesized_answer
                logger.info(f"[答案合成] 已生成合成答案 | 长度: {len(synthesized_answer)}")
        except Exception as synth_e:
            logger.warning(f"[答案合成] 合成失败: {synth_e}")
    
    return nodes
```

#### 多轮路径

**位置**：`api/knowledge_handler.py` (lines 329-341)

相同的答案合成逻辑也添加到 `_retrieve_and_rerank()` 方法中。

---

## 工作流程对比

### 修复前

```
用户查询
  ↓
_smart_retrieve_and_rerank()
  ↓
子问题分解（通用库）
  ├─ 成功 → 直接返回 ✅
  └─ 失败 ↓
意图分类
  ↓
选择检索器（免签库/双库/通用库）
  ↓
标准检索
```

**问题**：复杂免签问题 → 触发分解 → 使用通用库 → 无法命中免签库

---

### 修复后

```
用户查询
  ↓
_smart_retrieve_and_rerank()
  ↓
意图分类
  ↓
选择检索器（免签库/双库/通用库）
  ↓
子问题分解（使用选中的检索器）
  ├─ 成功 → 生成答案合成 → 返回 ✅
  └─ 失败 ↓
标准检索（使用选中的检索器）
```

**效果**：复杂免签问题 → 意图分类=visa_free → 选择免签库 → 分解检索免签库 ✅

---

## 答案合成流程

```
retrieve_with_decomposition()
  ↓
分解为3个子问题
  ↓
并行检索（使用路由后的检索器）
  ├─ 子问题1 → Top节点内容（200字符）
  ├─ 子问题2 → Top节点内容（200字符）
  └─ 子问题3 → Top节点内容（200字符）
  ↓
合并节点 + 生成 sub_answers
  ↓
返回到 KnowledgeHandler
  ↓
检测到 sub_answers → 调用 synthesize_answer()
  ↓
LLM合成完整答案
  ↓
添加到 metadata['synthesized_answer']
  ↓
（可选）在最终回答中使用合成答案
```

---

## 使用场景

### 场景1：复杂免签问题

**查询**："中国护照去哪些国家免签，停留时间是多久，需要什么条件？"

**流程**：
1. 意图分类 → `visa_free`
2. 选择免签库 → `visa_free_retriever`
3. 子问题分解：
   - "哪些国家对中国免签？"
   - "免签停留时间是多久？"
   - "免签入境条件是什么？"
4. 并行检索**免签库**（而非通用库）
5. 合并结果 + 生成答案合成
6. 返回高质量答案

---

### 场景2：复杂双库问题

**查询**："去泰国免签需要什么条件，有哪些航班可以直飞？"

**流程**：
1. 意图分类 → `both`
2. 选择双库 → `multi_kb_retriever`
3. 子问题分解：
   - "去泰国免签需要什么条件？"
   - "有哪些航班可以直飞泰国？"
4. 并行检索**双库**（免签库+航司库）
5. 合并结果 + 生成答案合成
6. 返回综合答案

---

## 日志示例

### 修复前（问题）

```
[智能路由] 意图分类器未启用，使用默认策略: general
[检索策略] 尝试使用子问题分解检索（单轮）
[子问题分解] 分解成功 | 子问题数: 3
[子问题检索] 开始并行检索 3 个子问题
[子问题检索] 分解检索完成 | 返回节点数: 15
# ❌ 意图分类和路由永远不会执行
```

---

### 修复后（正确）

```
[智能路由] 意图分类结果: visa_free
[智能路由] 使用免签知识库
[检索策略] 尝试使用子问题分解检索（单轮） | 目标库: visa_free
[子问题分解] 分解成功 | 子问题数: 3
[子问题检索] 开始并行检索 3 个子问题
[子问题检索] 分解检索完成 | 返回节点数: 15 | 使用库: visa_free
[答案合成] 已生成合成答案 | 长度: 450
# ✅ 正确使用免签库 + 生成答案合成
```

---

## 配置说明

### 启用子问题分解

```bash
export ENABLE_SUBQUESTION_DECOMPOSITION=true
```

### 启用意图分类

```bash
export ENABLE_INTENT_CLASSIFIER=true
```

### 同时启用（推荐）

```bash
export ENABLE_SUBQUESTION_DECOMPOSITION=true
export ENABLE_INTENT_CLASSIFIER=true
```

**效果**：复杂问题 → 意图路由 → 专库分解检索 → 答案合成

---

## 性能影响

| 步骤 | 耗时 | 说明 |
|------|------|------|
| 意图分类 | ~200ms | LLM调用 |
| 子问题分解 | ~1-2s | LLM调用 |
| 并行检索（3个子问题） | ~800ms | 并行执行 |
| 答案合成 | ~1-2s | LLM调用 |
| **总计** | **~3-5s** | 相比标准检索增加 |

**优化建议**：
- 提高 `COMPLEXITY_THRESHOLD` 减少分解频率
- 降低 `MAX_DEPTH` 减少子问题数量
- 答案合成可选，根据需要启用

---

## 验证方法

### 1. 测试意图路由 + 子问题分解

```bash
# 复杂免签问题
curl -X POST http://localhost:5000/api/knowledge \
  -H "Content-Type: application/json" \
  -d '{"question": "中国护照去哪些国家免签，停留时间是多久？", "enable_thinking": false}'

# 查看日志
grep "\[智能路由\]" logs/app.log
grep "\[子问题检索\]" logs/app.log
grep "使用库:" logs/app.log
```

### 2. 验证答案合成

```bash
# 查看合成日志
grep "\[答案合成\]" logs/app.log

# 应该看到：
# [答案合成] 已生成合成答案 | 长度: XXX
```

### 3. 对比修复前后

**修复前**：
- 复杂免签问题使用通用库
- 无答案合成

**修复后**：
- 复杂免签问题使用免签库
- 自动生成答案合成

---

## 后续优化方向

1. **多轮场景支持意图路由**：当前多轮场景使用默认retriever，可以添加意图分类
2. **答案合成并入提示词**：将 `synthesized_answer` 作为额外上下文注入到最终prompt
3. **缓存分解结果**：相似查询复用分解结果
4. **自适应分解**：根据知识库类型调整分解策略

---

## 相关文档

- [子问题分解使用指南](./SUBQUESTION_DECOMPOSITION_GUIDE.md)
- [子问题分解修复总结](./SUBQUESTION_IMPLEMENTATION_FIXES.md)
- [意图分类器文档](./INTENT_CLASSIFIER_README.md)

---

## 修复时间

2025-01-XX

## 修复人员

开发团队
