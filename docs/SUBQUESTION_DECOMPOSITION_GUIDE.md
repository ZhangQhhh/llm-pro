# 子问题分解功能使用指南

## 功能概述

子问题分解是一个可选的检索前编排层，能够将复杂查询自动分解为多个简单子问题，并行检索后合并结果，提升复杂问题的召回率和答案质量。

### 核心特性

- **插件式设计**：通过环境变量一键启用/关闭，默认关闭
- **单轮/多轮统一**：单轮直接使用当前query，多轮自动压缩历史对话
- **智能触发**：基于查询长度、复杂度、实体数量等启发式规则判断是否分解
- **并行检索**：多个子问题并行检索，提升性能
- **优雅降级**：任何失败都会自动回退到标准检索，不影响业务
- **健康度监控**：内置指标追踪，支持调试和优化

## 配置说明

### 环境变量配置

```bash
# 启用子问题分解功能
export ENABLE_SUBQUESTION_DECOMPOSITION=true

# 子问题分解参数
export SUBQUESTION_MAX_DEPTH=3                    # 最大子问题数量（默认3）
export SUBQUESTION_MIN_SCORE=0.3                  # 子问题检索最低分数阈值（默认0.3）
export SUBQUESTION_COMPLEXITY_THRESHOLD=50        # 触发分解的最小查询长度（默认50字符）
export SUBQUESTION_DECOMP_LLM_ID=qwen3-32b       # 用于分解的LLM（默认qwen3-32b）
export SUBQUESTION_DECOMP_TIMEOUT=10             # 分解超时时间（默认10秒）
export SUBQUESTION_ENABLE_ENTITY_CHECK=true      # 启用命名实体检测（默认true）
export SUBQUESTION_MIN_ENTITIES=2                # 触发分解的最小实体数（默认2）

# 对话历史压缩配置（多轮场景）
export SUBQUESTION_HISTORY_COMPRESS_TURNS=5      # 压缩最近N轮对话（默认5）
export SUBQUESTION_HISTORY_MAX_TOKENS=500        # 历史摘要最大token数（默认500）

# 健康度指标配置
export SUBQUESTION_MAX_EMPTY_RESULTS=2           # 允许的最大空结果子问题数（默认2）
export SUBQUESTION_FALLBACK_ON_ERROR=true        # 错误时回退到标准检索（默认true）
```

### 配置文件位置

所有配置项在 `config/settings.py` 中定义，支持通过环境变量覆盖。

## 工作流程

### 1. 查询路由

```
用户查询 → 检查是否启用 → 判断是否应该分解 → 选择检索策略
                ↓                    ↓
            未启用/不满足条件      满足条件
                ↓                    ↓
            标准检索流程          子问题分解流程
```

### 2. 分解判断条件

系统会根据以下条件判断是否分解：

- **查询长度**：≥ `SUBQUESTION_COMPLEXITY_THRESHOLD`（默认50字符）
- **实体数量**（可选）：检测到的实体指标 ≥ `SUBQUESTION_MIN_ENTITIES`（默认2）
- **LLM判断**：调用LLM分析查询复杂度

### 3. 子问题分解流程

```
原始查询 → 压缩历史对话（多轮） → LLM分解 → 生成2-3个子问题
    ↓
并行检索各子问题 → 重排序 → 合并去重 → 按分数排序 → 返回Top-N
```

### 4. 多轮对话支持

对于多轮对话场景：

1. 自动获取最近N轮对话（`SUBQUESTION_HISTORY_COMPRESS_TURNS`）
2. 调用LLM压缩为简洁摘要（≤200字）
3. 将摘要作为上下文传递给分解器
4. 分解器结合上下文生成子问题

## 使用示例

### 启用功能

```bash
# 方式1：环境变量
export ENABLE_SUBQUESTION_DECOMPOSITION=true
python app.py

# 方式2：配置文件（修改 config/settings.py）
ENABLE_SUBQUESTION_DECOMPOSITION = True
```

### 调试检索

使用增强的调试脚本查看子问题分解链路：

```bash
# 显示子问题分解信息
python scripts/debug_retrieval_scores.py "复杂查询问题" --show-subquestions

# 示例输出：
# 🔗 子问题分解统计
# 检测到 3 个子问题：
#   子问题1: 什么是免签政策？
#     → 匹配节点数: 5
#   子问题2: 哪些国家对中国免签？
#     → 匹配节点数: 8
#   子问题3: 免签停留时间是多久？
#     → 匹配节点数: 4
```

### 查看健康度指标

在应用运行时，子问题分解器会自动记录健康度指标：

```python
# 在代码中获取指标
if knowledge_service.sub_question_decomposer:
    metrics = knowledge_service.sub_question_decomposer.get_metrics()
    print(metrics)

# 输出示例：
# {
#     'total_queries': 100,
#     'decomposed_queries': 35,
#     'fallback_count': 3,
#     'empty_results_count': 1,
#     'timeout_count': 0,
#     'error_count': 0,
#     'decompose_rate': '35.00%',
#     'fallback_rate': '3.00%'
# }
```

## 日志说明

### 关键日志标记

- `[子问题分解]`：分解过程日志
- `[子问题检索]`：检索执行日志
- `[历史压缩]`：对话历史压缩日志
- `[结果合并]`：结果合并日志

### 日志示例

```
[子问题分解] 开始分解查询: 中国护照去哪些国家免签，停留时间是多久...
[子问题分解] LLM响应完成 | 耗时: 1.23s
[子问题分解] 分解成功 | 子问题数: 3 | 子问题: ['哪些国家对中国免签？', '免签停留时间是多久？', '免签入境条件是什么？']
[子问题检索] 开始并行检索 3 个子问题
[子问题检索] 完成: 哪些国家对中国免签？ | 节点数: 8
[子问题检索] 完成: 免签停留时间是多久？ | 节点数: 6
[子问题检索] 完成: 免签入境条件是什么？ | 节点数: 5
[结果合并] 总节点: 19 | 过滤后: 15 | 返回: 15
[子问题检索] 检索完成 | 合并后节点数: 15 | 子问题数: 3
```

## 性能优化建议

### 1. 调整触发阈值

如果分解过于频繁或不够频繁，调整以下参数：

```bash
# 提高复杂度阈值，减少分解频率
export SUBQUESTION_COMPLEXITY_THRESHOLD=80

# 降低实体数阈值，增加分解频率
export SUBQUESTION_MIN_ENTITIES=1
```

### 2. 优化超时设置

根据LLM响应速度调整超时时间：

```bash
# 快速LLM（如本地模型）
export SUBQUESTION_DECOMP_TIMEOUT=5

# 慢速LLM（如远程API）
export SUBQUESTION_DECOMP_TIMEOUT=15
```

### 3. 控制子问题数量

```bash
# 减少子问题数量，提升速度
export SUBQUESTION_MAX_DEPTH=2

# 增加子问题数量，提升召回
export SUBQUESTION_MAX_DEPTH=4
```

### 4. 调整分数阈值

```bash
# 提高阈值，过滤低质量结果
export SUBQUESTION_MIN_SCORE=0.5

# 降低阈值，保留更多结果
export SUBQUESTION_MIN_SCORE=0.2
```

## 故障排查

### 问题1：分解功能未生效

**检查清单：**

1. 确认环境变量已设置：`echo $ENABLE_SUBQUESTION_DECOMPOSITION`
2. 查看启动日志是否有"子问题分解器初始化完成"
3. 确认查询满足触发条件（长度、实体数等）

### 问题2：分解超时频繁

**解决方案：**

1. 增加超时时间：`export SUBQUESTION_DECOMP_TIMEOUT=20`
2. 检查LLM服务是否正常
3. 考虑使用更快的LLM模型

### 问题3：回退率过高

**原因分析：**

- 子问题检索结果为空过多
- LLM分解质量不佳
- 知识库覆盖不足

**解决方案：**

1. 降低 `SUBQUESTION_MAX_EMPTY_RESULTS` 阈值
2. 调整分解提示词（`prompts.py`）
3. 丰富知识库内容

### 问题4：检索结果质量下降

**解决方案：**

1. 提高 `SUBQUESTION_MIN_SCORE` 阈值
2. 减少 `SUBQUESTION_MAX_DEPTH`，避免过度分解
3. 检查子问题是否合理（查看日志）

## 技术架构

### 核心组件

```
SubQuestionDecomposer (core/sub_question_decomposer.py)
    ├── decompose_query()           # 分解查询
    ├── retrieve_with_decomposition() # 分解检索
    ├── _compress_history()         # 压缩历史
    ├── _parallel_retrieve_subquestions() # 并行检索
    └── _merge_subquestion_results() # 合并结果
```

### 集成点

1. **KnowledgeService** (`services/knowledge_service.py`)
   - `create_sub_question_decomposer()` - 创建分解器

2. **KnowledgeHandler** (`api/knowledge_handler.py`)
   - `_retrieve_and_rerank()` - 检索入口，支持分解

3. **App** (`app.py`)
   - 启动时初始化分解器

4. **Prompts** (`prompts.py`)
   - 分解、合成、压缩提示词

## 最佳实践

### 1. 灰度发布

```bash
# 阶段1：小流量测试（关闭）
export ENABLE_SUBQUESTION_DECOMPOSITION=false

# 阶段2：开启并监控指标
export ENABLE_SUBQUESTION_DECOMPOSITION=true
# 观察 decompose_rate, fallback_rate

# 阶段3：根据指标调优参数
# 调整 COMPLEXITY_THRESHOLD, MIN_SCORE 等
```

### 2. 监控指标

定期检查以下指标：

- **分解率**：`decompose_rate` - 应在20%-40%之间
- **回退率**：`fallback_rate` - 应低于5%
- **超时率**：`timeout_count / total_queries` - 应低于1%
- **错误率**：`error_count / total_queries` - 应为0

### 3. 提示词优化

根据实际效果调整提示词（`prompts.py`）：

- 分解提示词：`get_subquestion_decomposition_system()`
- 合成提示词：`get_subquestion_synthesis_system()`
- 压缩提示词：`get_history_compression_system()`

### 4. 日志分析

使用日志分析工具追踪：

```bash
# 统计分解成功率
grep "\[子问题分解\] 分解成功" logs/app.log | wc -l

# 统计回退次数
grep "\[子问题检索\] 回退到标准检索" logs/app.log | wc -l

# 查看超时情况
grep "\[子问题分解\] 超时" logs/app.log
```

## 常见问题

**Q: 子问题分解会增加多少延迟？**

A: 通常增加1-3秒，取决于：
- LLM响应速度（分解+压缩）
- 子问题数量（并行检索）
- 网络延迟

**Q: 是否支持自定义分解逻辑？**

A: 支持。修改 `SubQuestionDecomposer.should_decompose()` 方法实现自定义触发条件。

**Q: 如何禁用实体检测？**

A: 设置 `export SUBQUESTION_ENABLE_ENTITY_CHECK=false`

**Q: 子问题分解是否支持流式输出？**

A: 当前版本不支持流式输出分解过程，但最终答案支持流式输出。

## 更新日志

### v1.0.0 (2025-01-XX)

- ✅ 初始版本发布
- ✅ 支持单轮/多轮查询分解
- ✅ 并行检索和结果合并
- ✅ 健康度监控和自动降级
- ✅ 调试工具集成

## 相关文档

- [DEBUG_RETRIEVAL_GUIDE.md](./DEBUG_RETRIEVAL_GUIDE.md) - 检索调试指南
- [INTENT_CLASSIFIER_README.md](./INTENT_CLASSIFIER_README.md) - 意图分类器文档
- [MULTI_KB_RETRIEVAL_STRATEGY.md](./MULTI_KB_RETRIEVAL_STRATEGY.md) - 多库检索策略

## 联系方式

如有问题或建议，请联系开发团队或提交Issue。
