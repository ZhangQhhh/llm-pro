# 路由逻辑验证报告

## 验证时间
2025-01-31

## 验证目的
确保多库检索路由逻辑正确，并且没有 QueryBundle 使用错误。

## 路由逻辑规则

### 用户需求明确
1. **通用问题（general）**: 只过通用知识库
2. **免签问题（visa_free）**: 过免签库 + 通用库
3. **航司问题（airline）**: 过航司库 + 通用库
4. **航司+免签问题（airline_visa_free）**: 三库都过（航司库 + 免签库 + 通用库）

## 验证结果

### ✅ 1. QueryBundle 使用检查

#### 检查位置
`core/multi_kb_retriever.py` 中所有 `.retrieve()` 调用

#### 检查结果
```python
# ✅ retrieve_from_both() - 第94行和第106行
query_bundle = QueryBundle(query_str=query)
visa_free_nodes = self.visa_free_retriever.retrieve(query_bundle)
general_nodes = self.general_retriever.retrieve(query_bundle)

# ✅ retrieve_airline_only() - 第243行和第249行
query_bundle = QueryBundle(query_str=query)
airline_nodes = self.airline_retriever.retrieve(query_bundle)
general_nodes = self.general_retriever.retrieve(query_bundle)

# ✅ retrieve_from_all_three() - 第316行、第321行、第326行
query_bundle = QueryBundle(query_str=query)
airline_nodes = self.airline_retriever.retrieve(query_bundle)
visa_nodes = self.visa_free_retriever.retrieve(query_bundle)
general_nodes = self.general_retriever.retrieve(query_bundle)
```

**结论**: ✅ 所有检索器调用都正确使用了 `QueryBundle`，不会出现之前的错误。

### ✅ 2. 路由逻辑检查

#### 检查位置
`api/knowledge_handler.py` 的 `_smart_retrieve_and_rerank()` 方法

#### 路由表

| 意图分类 | 检索策略 | 使用的库 | 方法调用 |
|---------|---------|---------|---------|
| `general` | 只通用库 | 通用库 | `retriever.retrieve(query_bundle)` |
| `visa_free` | 免签+通用 | 免签库 + 通用库 | `multi_kb_retriever.retrieve_from_both()` |
| `airline` | 航司+通用 | 航司库 + 通用库 | `multi_kb_retriever.retrieve_airline_only()` |
| `airline_visa_free` | 三库 | 航司库 + 免签库 + 通用库 | `multi_kb_retriever.retrieve_from_all_three()` |
| `both` (兼容旧版) | 免签+通用 | 免签库 + 通用库 | `multi_kb_retriever.retrieve_from_both()` |

#### 代码验证

```python
# ✅ 1. airline_visa_free -> 三库检索
if strategy == "airline_visa_free":
    use_multi_kb_method = "all_three"
    retriever = self.multi_kb_retriever
    # 调用: retriever.retrieve_from_all_three(question)

# ✅ 2. airline -> 航司+通用
elif strategy == "airline":
    use_multi_kb_method = "airline_only"
    retriever = self.multi_kb_retriever
    # 调用: retriever.retrieve_airline_only(question)

# ✅ 3. visa_free -> 免签+通用
elif strategy == "visa_free":
    use_multi_kb_method = "both"
    retriever = self.multi_kb_retriever
    # 调用: retriever.retrieve_from_both(question)

# ✅ 4. general -> 只通用
else:
    retriever = self.retriever
    # 调用: retriever.retrieve(query_bundle)
```

**结论**: ✅ 路由逻辑完全符合需求。

### ✅ 3. 去重逻辑检查

#### 检查位置
`core/multi_kb_retriever.py` 的所有合并方法

#### 去重实现
```python
# 所有合并方法都包含去重逻辑
seen_ids = set()
unique_merged = []
for node in merged:
    node_id = node.node.node_id
    if node_id not in seen_ids:
        seen_ids.add(node_id)
        unique_merged.append(node)
```

#### 应用位置
- ✅ `_fixed_merge()` - 第209-216行
- ✅ `retrieve_airline_only()` - 第263-270行
- ✅ `retrieve_from_all_three()` - 第349-356行

**结论**: ✅ 所有合并方法都正确实现了去重逻辑。

### ✅ 4. 通用库保底策略检查

#### 验证点：通用库是否在所有情况下都参与检索？

| 场景 | 通用库是否参与 | 验证 |
|------|--------------|------|
| 通用问题 | ✅ 是（唯一） | 只用通用库 |
| 免签问题 | ✅ 是（保底） | `retrieve_from_both()` 包含通用库 |
| 航司问题 | ✅ 是（保底） | `retrieve_airline_only()` 包含通用库 |
| 航司+免签问题 | ✅ 是（保底） | `retrieve_from_all_three()` 包含通用库 |

**结论**: ✅ 通用库在所有情况下都参与检索，符合"通用库始终参与"的原则。

## 工作流程示例

### 示例1：通用问题
```
用户问题: "护照办理需要什么材料？"
    ↓
意图分类: general
    ↓
路由决策: 使用通用知识库
    ↓
检索: retriever.retrieve(query_bundle)
    ↓
返回: 通用库的15条结果
```

### 示例2：免签问题
```
用户问题: "去泰国旅游需要签证吗？"
    ↓
意图分类: visa_free
    ↓
路由决策: 使用双库检索（免签库 + 通用库）
    ↓
检索: multi_kb_retriever.retrieve_from_both(question)
    ↓
合并策略:
  - 前5条：免签库最高分
  - 中5条：通用库最高分（保底）
  - 后5条：综合比较
    ↓
去重: 按node_id去重
    ↓
返回: 去重后的15条结果（免签内容 + 通用知识）
```

### 示例3：航司问题
```
用户问题: "执行中美航班的机组人员需要签证吗？"
    ↓
意图分类: airline
    ↓
路由决策: 使用航司知识库（含通用库保底）
    ↓
检索: multi_kb_retriever.retrieve_airline_only(question)
    ↓
合并策略:
  - 前5条：航司库最高分
  - 中5条：通用库最高分（保底）
  - 后5条：综合比较
    ↓
去重: 按node_id去重
    ↓
返回: 去重后的15条结果（航司内容 + 通用知识）
```

### 示例4：航司+免签问题 ⭐
```
用户问题: "执行飞往泰国航班的机组人员需要签证吗？"
    ↓
意图分类: airline_visa_free
    ↓
路由决策: 使用三库检索（航司库 + 免签库 + 通用库）
    ↓
检索: multi_kb_retriever.retrieve_from_all_three(question)
    ↓
合并策略:
  - 前5条：航司库最高分
  - 中5条：免签库最高分
  - 后5条：通用库最高分（保底）
  - 额外5条：综合比较
    ↓
去重: 按node_id去重 ⭐ 关键
    ↓
返回: 去重后的20条结果（航司内容 + 免签内容 + 通用知识）
```

## 关键改进点

### 1. QueryBundle 使用
- ✅ 所有 `.retrieve()` 调用都传入 `QueryBundle` 对象
- ✅ 避免了之前直接传字符串的错误

### 2. 路由逻辑优化
- ✅ `visa_free` 策略：从"只免签库"改为"免签库+通用库"
- ✅ 新增 `airline_visa_free` 策略：支持三库同时检索
- ✅ 保留 `both` 策略：兼容旧版代码

### 3. 去重机制
- ✅ 所有合并方法都实现了按 `node_id` 去重
- ✅ 避免了同一文档片段重复出现的问题

### 4. 通用库保底
- ✅ 所有非通用问题都强制包含通用库
- ✅ 确保用户获得更全面的信息

## 测试建议

### 1. 单元测试
```python
# 测试通用问题
assert strategy == "general"
assert only_general_kb_used()

# 测试免签问题
assert strategy == "visa_free"
assert visa_kb_and_general_kb_used()

# 测试航司问题
assert strategy == "airline"
assert airline_kb_and_general_kb_used()

# 测试航司+免签问题
assert strategy == "airline_visa_free"
assert all_three_kbs_used()
```

### 2. 集成测试
```bash
# 测试问题集
python tests/test_routing_logic.py

# 测试去重
python tests/test_deduplication.py

# 测试意图分类
python tests/test_airline_intent.py
```

### 3. 日志验证
检查日志中是否出现：
```
[智能路由] 使用通用知识库
[智能路由] 使用双库检索（免签库 + 通用库）
[智能路由] 使用航司知识库（含通用库保底）
[智能路由] 使用三库检索（航司库 + 免签库 + 通用库）
```

## 总结

### ✅ 验证通过项
1. QueryBundle 使用正确
2. 路由逻辑符合需求
3. 去重机制完善
4. 通用库保底策略有效

### 📝 注意事项
1. 意图分类器需要正确识别 `airline_visa_free` 组合意图
2. 提示词需要包含组合类型的示例
3. 三库检索时注意性能（三次检索调用）

### 🎯 核心优势
- **灵活性**: 支持单库、双库、三库检索
- **准确性**: 智能意图识别，精准路由
- **完整性**: 通用库保底，信息全面
- **可靠性**: 自动去重，避免重复
