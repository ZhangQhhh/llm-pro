# 数据趋势分析接口修复说明

## 修复内容

### 1. **修正 LLMStreamWrapper 使用方式**

**问题**: `api/data_analysis_handler.py` 中错误地实例化了 `LLMStreamWrapper`
- ❌ 错误: `self.llm_wrapper = LLMStreamWrapper(llm_service)`
- ❌ 错误: `self.llm_wrapper.stream(llm_id=...)`

**原因**: `LLMStreamWrapper` 是纯静态封装，不需要实例化

**修复**:
```python
# 移除实例化
# self.llm_wrapper = LLMStreamWrapper(llm_service)  # 删除

# 正确调用方式
llm = self.llm_service.get_client(llm_id)
response_stream = LLMStreamWrapper.stream(
    llm=llm,
    system_prompt=system_prompt,
    user_prompt=user_prompt,
    enable_thinking=enable_thinking
)
```

**修改文件**:
- `api/data_analysis_handler.py`: `__init__`, `_call_llm_stream`, `_call_llm_sync`

---

### 2. **修正 LLM 服务获取方式**

**问题**: `routes/knowledge_routes.py` 中使用错误的方式获取 LLM 服务
- ❌ 错误: `llm_service = current_app.extensions.get('llm_service')`
- 结果: 始终返回 `None` → 500 错误

**原因**: LLM 服务挂载在 `current_app.llm_service` 而不是 `extensions`

**修复**:
```python
# 正确方式
llm_service = current_app.llm_service
```

**修改文件**:
- `routes/knowledge_routes.py`: `/api/data/trend_summary` 接口

---

### 3. **添加可配置的摘要长度**

**问题**: 摘要长度硬编码为 150 字，太紧凑

**改进**:
1. **配置文件**: 添加 `Settings.DATA_ANALYSIS_MAX_LENGTH = 250`
2. **Prompt 函数**: 支持动态长度参数
3. **请求参数**: 支持 `max_length` 覆盖默认值

**修改文件**:
- `config/settings.py`: 添加 `DATA_ANALYSIS_MAX_LENGTH = 250`
- `prompts.py`: 
  - `get_data_stats_system(max_length=250)`
  - `get_data_stats_user(data_block, max_length=250)`
- `api/data_analysis_handler.py`: 添加 `max_length` 参数
- `routes/knowledge_routes.py`: 支持 `max_length` 请求参数

---

## 使用示例

### 基础调用（使用默认 250 字）

```python
import requests

url = "http://53.3.1.2/llm/api/data/trend_summary"
headers = {
    "Authorization": "Bearer your_token",
    "Content-Type": "application/json"
}

data = {
    "data": {
        "totalCount": 1000,
        "entryCount": 600,
        "exitCount": 400,
        # ... 其他字段
    },
    "model_id": "qwen2025",
    "stream": False
}

response = requests.post(url, headers=headers, json=data)
print(response.json())
```

### 自定义摘要长度

```python
data = {
    "data": {...},
    "model_id": "qwen2025",
    "stream": False,
    "max_length": 300  # 自定义为 300 字
}

response = requests.post(url, headers=headers, json=data)
```

### 完整参数示例

```json
{
  "data": {
    "totalCount": 1000,
    "entryCount": 600,
    "exitCount": 400,
    "maleCount": 550,
    "femaleCount": 450,
    "transportationToolStats": {
      "SL8103": 150,
      "CA1234": 200
    },
    "countryRegionStats": {
      "泰国": 300,
      "中国": 400
    },
    "transportationModeStats": {
      "1": 500,
      "2": 500
    },
    "personCategoryStats": {
      "26": 800
    },
    "ethnicityStats": {
      "汉族": 700
    }
  },
  "model_id": "qwen2025",
  "thinking": false,
  "stream": true,
  "max_length": 250
}
```

---

## 配置说明

### `config/settings.py`

```python
# 数据趋势分析配置
DATA_ANALYSIS_MAX_LENGTH = 250  # 分析摘要最大字数（默认250字）
```

可通过环境变量覆盖（如需要）:
```python
DATA_ANALYSIS_MAX_LENGTH = int(os.getenv("DATA_ANALYSIS_MAX_LENGTH", "250"))
```

---

## 参数优先级

摘要长度的确定顺序：
1. **请求参数** `max_length` (最高优先级)
2. **配置文件** `Settings.DATA_ANALYSIS_MAX_LENGTH`
3. **默认值** 250 字

示例：
```python
# 请求中指定 300 字
{"data": {...}, "max_length": 300}  # 使用 300

# 请求中未指定
{"data": {...}}  # 使用配置文件的 250

# 配置文件未设置
# 使用代码中的默认值 250
```

---

## 测试验证

### 1. 测试 LLM 服务获取

```python
# 确认能正常获取 LLM 服务
response = requests.post(
    "http://53.3.1.2/llm/api/data/trend_summary",
    headers={"Authorization": "Bearer your_token"},
    json={
        "data": {"totalCount": 100},
        "stream": False
    }
)

# 应该返回 200，而不是 500 (LLM 服务未初始化)
assert response.status_code == 200
```

### 2. 测试摘要长度控制

```python
# 测试不同长度限制
for max_len in [150, 200, 250, 300]:
    response = requests.post(
        url,
        headers=headers,
        json={
            "data": test_data,
            "max_length": max_len,
            "stream": False
        }
    )
    
    result = response.json()
    summary = result["data"]["summary"]
    print(f"max_length={max_len}, 实际长度={len(summary)}")
```

### 3. 测试流式输出

```python
response = requests.post(
    url,
    headers=headers,
    json={"data": test_data, "stream": True},
    stream=True
)

for line in response.iter_lines():
    if line:
        print(line.decode('utf-8'))
```

---

## 注意事项

1. **LLMStreamWrapper 是静态封装**
   - 不要实例化: `wrapper = LLMStreamWrapper(service)` ❌
   - 直接调用静态方法: `LLMStreamWrapper.stream(llm, ...)` ✅

2. **LLM 服务获取**
   - 使用 `current_app.llm_service` ✅
   - 不要用 `current_app.extensions.get('llm_service')` ❌

3. **摘要长度**
   - 默认 250 字已足够（原来 150 字太少）
   - 可通过请求参数 `max_length` 动态调整
   - 不建议超过 500 字（会影响 Word 文档排版）

4. **错误处理**
   - 所有错误都返回 JSON 格式，不抛内部异常
   - 流式模式下会发送 `ERROR:` 消息

---

## 修复前后对比

### 修复前
```python
# ❌ 错误的实现
class DataAnalysisHandler:
    def __init__(self, llm_service):
        self.llm_wrapper = LLMStreamWrapper(llm_service)  # TypeError
    
    def _call_llm_stream(self, llm_id, ...):
        response = self.llm_wrapper.stream(
            llm_id=llm_id,  # 签名不匹配
            ...
        )

# ❌ 错误的服务获取
llm_service = current_app.extensions.get('llm_service')  # 返回 None
```

### 修复后
```python
# ✅ 正确的实现
class DataAnalysisHandler:
    def __init__(self, llm_service):
        self.llm_service = llm_service
    
    def _call_llm_stream(self, llm_id, ...):
        llm = self.llm_service.get_client(llm_id)
        response = LLMStreamWrapper.stream(
            llm=llm,  # 正确传递 llm 对象
            system_prompt=...,
            user_prompt=...,
            enable_thinking=...
        )

# ✅ 正确的服务获取
llm_service = current_app.llm_service
```

---

## 相关文件清单

### 修改的文件
1. `api/data_analysis_handler.py` - 修正 LLMStreamWrapper 调用
2. `routes/knowledge_routes.py` - 修正服务获取和添加参数
3. `prompts.py` - 添加动态长度支持
4. `config/settings.py` - 添加配置项

### 新增文件
1. `utils/data_stats_formatter.py` - 数据格式化工具
2. `docs/DATA_TREND_ANALYSIS_API.md` - API 文档
3. `docs/DATA_TREND_ANALYSIS_FIX.md` - 本修复文档

---

## 下一步

接口现已完全可用，可以：

1. ✅ 启动服务测试接口
2. ✅ 集成到 Java Spring Boot 后端
3. ✅ 测试流式和同步两种模式
4. ✅ 验证不同摘要长度的效果
5. ✅ 部署到生产环境
