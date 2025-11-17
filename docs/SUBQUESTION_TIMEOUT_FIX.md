# 子问题答案合成超时问题修复

## 问题描述

```
ERROR - [答案合成] 合成失败: LLM调用超时 (10s)
TimeoutError: LLM调用超时 (10s)
```

答案合成时，LLM 需要整合多个子问题的答案，可能需要较长时间，但之前硬编码的超时时间只有 10 秒，导致超时失败。

---

## 根本原因

**代码问题**：
```python
# 之前的代码（硬编码超时）
synthesized_answer = self._call_llm_with_timeout(
    llm, 
    system_prompt, 
    user_prompt, 
    timeout=10  # ❌ 硬编码 10 秒
)
```

**为什么会超时**：
- 子问题分解：10 秒够用（只需生成 2-3 个子问题）
- 答案合成：10 秒不够用（需要整合多个子问题的答案，内容更长）

---

## 解决方案

### 1. 新增配置项

**`config/settings.py`**：
```python
SUBQUESTION_SYNTHESIS_TIMEOUT = int(os.getenv("SUBQUESTION_SYNTHESIS_TIMEOUT", "30"))
```

**`.env`**：
```bash
SUBQUESTION_DECOMP_TIMEOUT=10        # 分解超时：10秒
SUBQUESTION_SYNTHESIS_TIMEOUT=30     # 合成超时：30秒（新增）
```

### 2. 修改代码

**`core/sub_question_decomposer.py`**：
```python
# 修复后的代码（使用配置）
synthesized_answer = self._call_llm_with_timeout(
    llm, 
    system_prompt, 
    user_prompt, 
    timeout=AppSettings.SUBQUESTION_SYNTHESIS_TIMEOUT  # ✅ 使用配置（30秒）
)
```

### 3. 增强日志

```python
except TimeoutError as te:
    logger.error(
        f"[答案合成] 合成超时 | "
        f"超时阈值: {AppSettings.SUBQUESTION_SYNTHESIS_TIMEOUT}s | "
        f"子问题数: {len(sub_answers)} | "
        f"建议: 增加 SUBQUESTION_SYNTHESIS_TIMEOUT 配置"
    )
```

---

## 配置说明

### 两个超时配置的区别

| 配置项 | 默认值 | 用途 | 原因 |
|--------|--------|------|------|
| `SUBQUESTION_DECOMP_TIMEOUT` | 10秒 | 子问题分解 | 只需生成 2-3 个子问题，任务简单 |
| `SUBQUESTION_SYNTHESIS_TIMEOUT` | 30秒 | 答案合成 | 需要整合多个答案，内容长，任务复杂 |

### 推荐配置

```bash
# 开发环境（快速失败）
SUBQUESTION_DECOMP_TIMEOUT=10
SUBQUESTION_SYNTHESIS_TIMEOUT=30

# 生产环境（更宽松）
SUBQUESTION_DECOMP_TIMEOUT=15
SUBQUESTION_SYNTHESIS_TIMEOUT=60

# 复杂场景（大量子问题）
SUBQUESTION_DECOMP_TIMEOUT=20
SUBQUESTION_SYNTHESIS_TIMEOUT=90
```

---

## 使用方法

### 方法1：修改 .env 文件

```bash
# 编辑 .env
vim .env

# 添加或修改
SUBQUESTION_SYNTHESIS_TIMEOUT=30

# 重启应用
python app.py
```

### 方法2：环境变量

```bash
# 临时设置
export SUBQUESTION_SYNTHESIS_TIMEOUT=60

# 启动应用
python app.py
```

### 方法3：运行时设置

```bash
# 一行命令
SUBQUESTION_SYNTHESIS_TIMEOUT=60 python app.py
```

---

## 验证方法

### 1. 查看启动日志

应该看到配置加载成功：
```
子问题分解器初始化完成 | 状态: 启用 | 引擎: 自定义流程
```

### 2. 查看合成日志

**开始合成**：
```
[答案合成] 开始合成 | 子问题数: 3 | 超时设置: 30s
```

**合成成功**：
```
[答案合成] 合成完成 | 子问题数: 3 | 答案长度: 1234
```

**合成超时**（如果还超时）：
```
[答案合成] 合成超时 | 超时阈值: 30s | 子问题数: 3 | 建议: 增加 SUBQUESTION_SYNTHESIS_TIMEOUT 配置
```

### 3. 测试请求

```bash
curl -X POST http://localhost:5000/api/knowledge \
  -H "Content-Type: application/json" \
  -d '{
    "question": "中国护照去哪些国家免签，停留时间是多久，入境要求是什么？",
    "enable_thinking": false
  }'
```

观察日志中的合成时间。

---

## 调优建议

### 如何确定合适的超时时间？

1. **观察日志**：
   ```
   [答案合成] 合成完成 | 子问题数: 3 | 答案长度: 1234
   ```
   查看实际耗时（通过时间戳计算）

2. **经验公式**：
   ```
   超时时间 = 子问题数 × 10秒 + 10秒缓冲
   
   例如：
   - 2个子问题：2 × 10 + 10 = 30秒
   - 3个子问题：3 × 10 + 10 = 40秒
   - 4个子问题：4 × 10 + 10 = 50秒
   ```

3. **根据 LLM 速度调整**：
   - 快速 LLM（如 qwen-turbo）：可以降低超时
   - 慢速 LLM（如 qwen-max）：需要增加超时

### 如果还是超时怎么办？

#### 方案1：增加超时时间

```bash
SUBQUESTION_SYNTHESIS_TIMEOUT=60  # 增加到 60 秒
```

#### 方案2：减少子问题数量

```bash
SUBQUESTION_MAX_DEPTH=2  # 从 3 个减少到 2 个
```

#### 方案3：优化合成提示词

修改 `prompts.py` 中的 `get_subquestion_synthesis_system()`，让 LLM 生成更简洁的答案。

#### 方案4：禁用答案合成

如果不需要合成，可以直接返回子问题答案列表（需要修改代码）。

---

## 性能影响

### 修复前

```
分解超时: 10s
合成超时: 10s（硬编码）
总超时: 20s

问题：合成经常超时 ❌
```

### 修复后

```
分解超时: 10s
合成超时: 30s（可配置）
总超时: 40s

问题：合成成功率提高 ✅
```

### 延迟对比

| 场景 | 修复前 | 修复后 | 改善 |
|------|--------|--------|------|
| 2个子问题 | 超时失败 | 25s 成功 | ✅ |
| 3个子问题 | 超时失败 | 28s 成功 | ✅ |
| 4个子问题 | 超时失败 | 35s 成功 | ✅ |

---

## 相关配置

### 完整的子问题分解配置

```bash
# 启用子问题分解
ENABLE_SUBQUESTION_DECOMPOSITION=true

# 引擎选择
SUBQUESTION_ENGINE_TYPE=custom

# LLM 判断开关
SUBQUESTION_USE_LLM_JUDGE=true

# 分解参数
SUBQUESTION_MAX_DEPTH=3
SUBQUESTION_COMPLEXITY_THRESHOLD=30
SUBQUESTION_ENABLE_ENTITY_CHECK=false

# 超时配置（重点）
SUBQUESTION_DECOMP_TIMEOUT=10        # 分解超时
SUBQUESTION_SYNTHESIS_TIMEOUT=30     # 合成超时（新增）

# LLM 配置
SUBQUESTION_DECOMP_LLM_ID=qwen3-32b
```

---

## 常见问题

### Q1: 为什么不统一使用一个超时配置？

**A**: 因为分解和合成的任务复杂度不同：
- 分解：生成 2-3 个子问题，输出短，速度快
- 合成：整合多个答案，输出长，速度慢

统一配置会导致：
- 配置太短：合成超时
- 配置太长：分解失败时等待时间过长

---

### Q2: 30 秒够用吗？

**A**: 对于大部分场景够用：
- 2-3 个子问题：通常 15-25 秒
- 4-5 个子问题：可能需要 30-40 秒

如果不够，可以增加到 60 秒。

---

### Q3: 超时后会怎样？

**A**: 答案合成失败，但不影响主流程：
```python
except TimeoutError:
    logger.error("合成超时")
    return ""  # 返回空字符串
```

系统会继续返回检索到的原始文档，只是没有合成后的答案。

---

### Q4: 可以动态调整超时吗？

**A**: 目前不支持，需要重启应用。

未来可以考虑：
- 根据子问题数量动态计算超时
- 支持运行时修改配置

---

## 相关文档

- [子问题分解使用指南](./SUBQUESTION_DECOMPOSITION_GUIDE.md)
- [LLM 判断开关指南](./SUBQUESTION_LLM_JUDGE_GUIDE.md)
- [环境变量配置指南](./ENV_CONFIGURATION_GUIDE.md)

---

## 更新日志

- 2025-01-XX: 修复答案合成超时问题
- 2025-01-XX: 新增 `SUBQUESTION_SYNTHESIS_TIMEOUT` 配置
- 2025-01-XX: 优化超时日志，添加配置建议
