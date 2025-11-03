# 意图分类器使用说明

## 概述

意图分类器是一个**插件式**功能模块，通过大模型判断用户问题是否与免签政策相关，从而决定是否调用免签知识库。

## 核心特性

### 1. 插件式设计
- ✅ 可通过配置一键启用/关闭
- ✅ 完全不影响现有业务逻辑
- ✅ 即使分类器失败，业务也能正常运行

### 2. 防死循环机制
- ⏱️ 超时保护（默认 5 秒）
- 🔄 重试机制（默认最多 1 次）
- 💾 结果缓存（避免重复调用）

### 3. 性能优化
- 🚀 LRU 缓存（最多 1000 条）
- 📊 详细的日志记录
- 🎯 确定性输出（temperature=0.0）

## 配置说明

### 环境变量配置

在 `.env` 文件或环境变量中设置：

```bash
# 是否启用意图分类器（默认：false）
ENABLE_INTENT_CLASSIFIER=true

# 超时时间（秒，默认：5.0）
INTENT_CLASSIFIER_TIMEOUT=5.0

# 最大重试次数（默认：1）
INTENT_CLASSIFIER_MAX_RETRIES=1

# 使用的 LLM ID（默认：使用系统默认 LLM）
INTENT_CLASSIFIER_LLM_ID=qwen3-32b
```

### Settings.py 配置

```python
# 在 config/settings.py 中
ENABLE_INTENT_CLASSIFIER = True  # 启用意图分类器
INTENT_CLASSIFIER_TIMEOUT = 5.0  # 超时时间
INTENT_CLASSIFIER_MAX_RETRIES = 1  # 最大重试次数
INTENT_CLASSIFIER_LLM_ID = "qwen3-32b"  # 使用的 LLM
```

## 使用方式

### 1. 启用意图分类器

```bash
# 方式1：通过环境变量
export ENABLE_INTENT_CLASSIFIER=true

# 方式2：在 .env 文件中
ENABLE_INTENT_CLASSIFIER=true

# 方式3：在 settings.py 中直接修改
ENABLE_INTENT_CLASSIFIER = True
```

### 2. 关闭意图分类器

```bash
# 方式1：通过环境变量
export ENABLE_INTENT_CLASSIFIER=false

# 方式2：在 .env 文件中
ENABLE_INTENT_CLASSIFIER=false

# 方式3：在 settings.py 中直接修改
ENABLE_INTENT_CLASSIFIER = False
```

### 3. 验证是否启用

启动应用后，查看日志：

```
# 启用时
意图分类器初始化成功（插件式）

# 关闭时
意图分类器未启用（通过配置关闭）
```

## 工作流程

```
用户提问
    ↓
意图分类器启用？
    ↓ 是
调用 LLM 判断（带超时保护）
    ↓
是否免签相关？
    ↓ 是                    ↓ 否
使用双知识库检索      使用通用知识库检索
    ↓                        ↓
返回结果 ←──────────────────┘
```

## 提示词说明

### 系统提示词
```
你是一个专业的出入境政策意图分类助手。
你的任务是快速准确地判断用户问题是否与免签政策相关。
```

### 用户提示词
包含以下内容：
- 问题描述
- 判断标准（是/否）
- 示例问题
- 输出格式要求

详见 `prompts.py` 中的 `get_visa_intent_classification_user_prompt()`

## 日志说明

### 初始化日志
```
意图分类器初始化 - 启用状态: True | 超时时间: 5.0s | 最大重试: 1 | LLM ID: qwen3-32b
```

### 分类日志
```
# 成功分类
意图分类完成 - 问题: 去泰国需要签证吗？ | 结果: 免签相关

# 使用缓存
使用缓存结果 - 问题: 去泰国需要签证吗？ | 结果: True

# 超时
意图分类超时 (5.0s) - 问题: ...

# 失败
意图分类失败 - 问题: ... | 错误: ...
```

## 故障处理

### 1. 意图分类器初始化失败
```
意图分类器初始化失败: [错误信息]
意图分类器功能不可用，将使用默认策略
```
**影响**：系统回退到默认策略（不使用免签知识库），业务正常运行

### 2. 意图分类超时
```
意图分类超时 (5.0s) - 问题: ...
```
**影响**：返回 False（不使用免签知识库），业务正常运行

### 3. 意图分类失败
```
意图分类器调用失败，回退到默认策略: [错误信息]
```
**影响**：返回 False（不使用免签知识库），业务正常运行

## 性能优化建议

### 1. 调整超时时间
```bash
# 如果网络较慢，可以增加超时时间
INTENT_CLASSIFIER_TIMEOUT=10.0
```

### 2. 调整缓存大小
在 `intent_classifier.py` 中修改：
```python
if len(self._cache) > 1000:  # 调整缓存大小
    ...
```

### 3. 使用更快的 LLM
```bash
# 使用响应更快的模型
INTENT_CLASSIFIER_LLM_ID=qwen3-14b
```

## 监控与统计

### 获取统计信息
```python
# 在代码中
stats = intent_classifier.get_stats()
print(stats)
# 输出：
# {
#     "enabled": True,
#     "cache_size": 42,
#     "timeout": 5.0,
#     "max_retries": 1,
#     "llm_id": "qwen3-32b"
# }
```

### 清空缓存
```python
intent_classifier.clear_cache()
```

## 常见问题

### Q1: 意图分类器会影响现有业务吗？
**A**: 不会。意图分类器采用插件式设计，即使失败也会回退到默认策略，保证业务正常运行。

### Q2: 如何验证意图分类器是否正常工作？
**A**: 查看日志中的 "意图分类完成" 消息，确认分类结果是否符合预期。

### Q3: 意图分类器会增加多少延迟？
**A**: 通常在 0.5-2 秒之间，具体取决于 LLM 的响应速度。可以通过缓存减少重复调用。

### Q4: 如何调整判断标准？
**A**: 修改 `prompts.py` 中的 `get_visa_intent_classification_user_prompt()` 函数。

### Q5: 意图分类器会死循环吗？
**A**: 不会。有超时保护、重试限制和异常处理机制。

## 测试建议

### 1. 功能测试
```python
# 测试免签相关问题
问题: "去泰国需要签证吗？"
预期: is_visa_related = True

# 测试非免签问题
问题: "如何办理护照？"
预期: is_visa_related = False
```

### 2. 性能测试
```python
# 测试缓存
第一次调用: 耗时 1.5s
第二次调用: 耗时 0.001s（使用缓存）
```

### 3. 故障测试
```python
# 测试超时
设置超时为 0.1s，观察是否正常回退

# 测试 LLM 失败
断开 LLM 连接，观察是否正常回退
```

## 版本历史

- **v1.0** (2025-01-31): 初始版本，支持基本的意图分类功能
  - 插件式设计
  - 超时保护
  - 缓存机制
  - 详细日志

## 联系方式

如有问题，请联系开发团队或查看项目文档。
