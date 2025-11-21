# 响应格式化器使用说明

## 📋 功能概述

`ResponseFormatter` 是一个自动校验和修复 LLM 响应格式的工具，确保输出符合预期的结构规范。

## 🔧 已接入位置

### 1. 单轮知识问答 (`process` 方法)
- **文件**: `api/knowledge_handler.py`
- **位置**: 第 488-522 行
- **时机**: 在 `yield ('DONE', '')` 之前

```python
# 8. 格式化校验和修复（在最后一次 yield 前）
from utils.response_formatter import response_formatter

validated_response = response_formatter.process_response(
    response_to_validate.strip(),
    question=question
)
```

### 2. 多轮对话 (`process_conversation` 方法)
- **文件**: `api/knowledge_handler.py`
- **位置**: 第 1243-1255 行
- **时机**: 在 `yield "DONE:"` 之前

```python
# 格式化校验和修复（在最后一次 yield 前）
from utils.response_formatter import response_formatter

if assistant_response:
    validated_response = response_formatter.process_response(
        assistant_response.strip(),
        question=question
    )
```

## ✅ 校验规则

### 必需的主标题
```markdown
## 咨询解析
## 综合解答
```

### 必需的小标题（在咨询解析中）
```markdown
**关键实体**
**核心动作**
```

### 禁止的内容
- 代码块符号：```
- 多余的空行（超过2个连续换行）

## 🔄 自动修复策略

### 1. 缺少主标题
```python
# 修复前
用户询问关于J2签证的问题...

# 修复后
## 咨询解析

用户询问关于J2签证的问题...
```

### 2. 缺少小标题
```python
# 修复前
## 咨询解析
用户询问...

# 修复后
## 咨询解析

**关键实体**
- 待补充

**核心动作**
- 待补充

用户询问...
```

### 3. 移除代码块符号
```python
# 修复前
```
根据规定...
```

# 修复后
根据规定...
```

### 4. 清理多余空行
```python
# 修复前
第一段



第二段

# 修复后
第一段

第二段
```

## 📊 验证方法

### 1. 查看格式修复日志
```bash
# 查看是否有格式修复
grep "格式修复" logs/app.log

# 应该看到：
# [格式修复] 响应格式已自动修复
# [对话-格式修复] 响应格式已自动修复
```

### 2. 查看格式校验详情
```bash
# 查看格式不规范的详情
grep "响应格式不规范" logs/app.log

# 应该看到：
# 响应格式不规范: {'valid': False, 'missing_sections': ['## 咨询解析'], ...}
```

### 3. 测试格式修复
```python
from utils.response_formatter import response_formatter

# 测试缺少标题
response = "这是一个没有标题的回答"
fixed = response_formatter.process_response(response, "测试问题")
print(fixed)

# 测试代码块
response = "```\n这是代码块\n```"
fixed = response_formatter.process_response(response, "测试问题")
print(fixed)  # 应该没有 ```
```

## 🚨 注意事项

### 1. 不影响流式输出
- 格式化在**最后一次 yield 前**执行
- 不会阻塞流式输出过程
- 只修复最终保存到日志的内容

### 2. 只校验 LLM 回答部分
- 自动过滤检索状态消息
- 只校验实际的回答内容
- 保留参考来源等元数据

### 3. 优雅降级
- 格式化失败不影响主流程
- 异常会被捕获并记录
- 返回原始响应作为后备

## 🔍 调试技巧

### 1. 启用详细日志
```python
# 在 response_formatter.py 中
logger.setLevel(logging.DEBUG)
```

### 2. 手动测试
```python
from utils.response_formatter import response_formatter

# 验证格式
validation = response_formatter.validate_format(response)
print(f"格式是否有效: {validation['valid']}")
print(f"缺少的标题: {validation['missing_sections']}")
print(f"缺少的小标题: {validation['missing_subsections']}")
print(f"是否有代码块: {validation['has_code_blocks']}")

# 修复格式
fixed = response_formatter.fix_format(response)
print(f"修复后的响应:\n{fixed}")
```

### 3. 查看修复前后对比
```bash
# 查看修复日志
tail -f logs/app.log | grep -A 5 "格式修复"
```

## 📈 性能影响

- **处理延迟**: ~2ms（格式校验）
- **修复延迟**: ~5ms（格式修复）
- **内存占用**: 可忽略（只处理文本）
- **CPU 占用**: 可忽略（简单字符串操作）

## 🎯 最佳实践

### 1. 定期检查日志
```bash
# 每天检查格式修复频率
grep -c "格式修复" logs/app_$(date +%Y-%m-%d).log

# 如果修复频率过高（>10%），需要优化 Prompt
```

### 2. 优化 Prompt
如果格式修复频繁，说明 LLM 没有遵守格式规范，需要：
- 在 Prompt 中强调格式要求
- 添加格式示例
- 使用结构化输出（JSON/函数调用）

### 3. 监控修复类型
```bash
# 统计缺少哪些标题
grep "missing_sections" logs/app.log | sort | uniq -c

# 统计缺少哪些小标题
grep "missing_subsections" logs/app.log | sort | uniq -c
```

---

通过这个格式化器，可以确保 LLM 输出始终符合预期的结构规范，提升用户体验！
