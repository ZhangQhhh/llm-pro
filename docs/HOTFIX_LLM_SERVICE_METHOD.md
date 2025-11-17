# Hotfix: LLMService 方法名修复

## 问题描述

**错误信息**：
```
AttributeError: 'LLMService' object has no attribute 'get_llm'
```

**根本原因**：
- `SubQuestionDecomposer` 和测试文件中使用了错误的方法名 `get_llm()`
- `LLMService` 的正确方法名是 `get_client()`

---

## 修复内容

### 1. 核心文件修复

**文件**：`core/sub_question_decomposer.py`

修复了3处调用：

#### 位置1：查询分解（line 163）
```python
# 修复前
llm = self.llm_service.get_llm(AppSettings.SUBQUESTION_DECOMP_LLM_ID)

# 修复后
llm = self.llm_service.get_client(AppSettings.SUBQUESTION_DECOMP_LLM_ID)
```

#### 位置2：历史压缩（line 325）
```python
# 修复前
llm = self.llm_service.get_llm(AppSettings.SUBQUESTION_DECOMP_LLM_ID)

# 修复后
llm = self.llm_service.get_client(AppSettings.SUBQUESTION_DECOMP_LLM_ID)
```

#### 位置3：答案合成（line 613）
```python
# 修复前
llm = self.llm_service.get_llm(AppSettings.SUBQUESTION_DECOMP_LLM_ID)

# 修复后
llm = self.llm_service.get_client(AppSettings.SUBQUESTION_DECOMP_LLM_ID)
```

---

### 2. 测试文件修复

**文件**：`tests/test_airline_intent.py`

修复了2处调用：

#### 位置1：test_airline_intent（line 30）
```python
# 修复前
llm_client = llm_service.get_llm(Settings.INTENT_CLASSIFIER_LLM_ID)

# 修复后
llm_client = llm_service.get_client(Settings.INTENT_CLASSIFIER_LLM_ID)
```

#### 位置2：test_edge_cases（line 108）
```python
# 修复前
llm_client = llm_service.get_llm(Settings.INTENT_CLASSIFIER_LLM_ID)

# 修复后
llm_client = llm_service.get_client(Settings.INTENT_CLASSIFIER_LLM_ID)
```

---

## LLMService 正确用法

### 方法签名

```python
class LLMService:
    def get_client(self, model_id: str) -> CustomOpenAILike:
        """
        获取指定的 LLM 客户端
        
        Args:
            model_id: 模型ID（如 'qwen3-32b'）
            
        Returns:
            CustomOpenAILike: LLM客户端实例
        """
```

### 使用示例

```python
from services.llm_service import LLMService
from config import Settings

# 初始化服务
llm_service = LLMService()
llm_service.initialize()

# 获取LLM客户端（正确方法）
llm_client = llm_service.get_client(Settings.INTENT_CLASSIFIER_LLM_ID)

# ❌ 错误用法
# llm_client = llm_service.get_llm(Settings.INTENT_CLASSIFIER_LLM_ID)
```

---

## 验证修复

### 1. 启动应用

```bash
python app.py
```

### 2. 测试子问题分解

```bash
curl -X POST http://localhost:5000/api/knowledge \
  -H "Content-Type: application/json" \
  -d '{
    "question": "中国护照去哪些国家免签，停留时间是多久？",
    "enable_thinking": false
  }'
```

### 3. 查看日志

应该看到：
```
[子问题分解] 开始分解查询: 中国护照去哪些国家免签...
[子问题分解] 分解成功 | 子问题数: 3
```

不应该再看到：
```
AttributeError: 'LLMService' object has no attribute 'get_llm'
```

---

## 影响范围

### 修复的功能

✅ **子问题分解**
- 查询分解
- 历史压缩
- 答案合成

✅ **测试用例**
- 航司意图分类测试
- 边界情况测试

### 不受影响的功能

- 标准检索
- 意图分类（使用正确的方法名）
- 多库检索
- 重排序

---

## 预防措施

### 1. 代码审查清单

在添加新的 LLM 调用时，确认：
- [ ] 使用 `llm_service.get_client(model_id)`
- [ ] 不使用 `llm_service.get_llm(model_id)`
- [ ] 传入正确的 model_id

### 2. 单元测试

添加测试确保方法名正确：

```python
def test_llm_service_method():
    """测试LLMService方法名"""
    llm_service = LLMService()
    llm_service.initialize()
    
    # 应该有 get_client 方法
    assert hasattr(llm_service, 'get_client')
    
    # 不应该有 get_llm 方法
    assert not hasattr(llm_service, 'get_llm')
```

### 3. IDE 提示

使用 IDE 的自动补全功能，避免手动输入方法名。

---

## 相关文档

- [子问题分解使用指南](./SUBQUESTION_DECOMPOSITION_GUIDE.md)
- [LLM服务文档](./LLM_SERVICE.md)

---

## 修复时间

2025-01-XX

## 修复人员

开发团队

## 优先级

🔴 **高优先级** - 阻塞子问题分解功能
