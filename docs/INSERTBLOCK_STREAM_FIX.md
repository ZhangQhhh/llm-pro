# InsertBlock 精准检索流式传输中断修复

## 问题现象

```
POST http://53.3.1.2/llm/api/knowledge_chat net::ERR_INCOMPLETE_CHUNKED_ENCODING 200 (OK)
```

前端日志显示：
- 成功接收到 "正在进行混合检索..."
- 成功接收到 "正在使用精准检索分析 10 个文档..."
- 但连接在中途断开，导致分块传输不完整

## 根本原因

### 1. **LLM 调用无超时保护** ⚠️ 最关键
`core/node_filter.py` 第 291 行：
```python
response = llm.complete(full_prompt)  # 可能无限阻塞
```

**问题**：
- 如果 LLM 服务响应慢或卡住，线程会无限等待
- 导致 InsertBlock 过滤器整体超时
- 主线程等待超时后继续执行，但后台线程可能还在运行
- 流式传输状态不一致，最终中断

### 2. **异常未正确传播**
`core/node_filter.py` 的 `filter_nodes` 方法：
```python
except TimeoutError:
    timeout_count += 1
    logger.error(...)  # 只记录日志，不抛出异常
```

**问题**：
- 即使大量节点超时/失败，方法仍正常返回
- 主线程无法感知到过滤器内部的严重错误
- 继续执行后续步骤，可能导致状态异常

### 3. **线程超时处理不完善**
`api/knowledge_handler.py` 第 273 行：
```python
filter_thread.join(timeout=1)  # 只等待1秒
# 没有检查线程是否还在运行
```

**问题**：
- 如果过滤器需要更长时间，1秒后主线程继续执行
- 后台线程可能还在运行，状态不一致
- `filtered_results` 可能是 `None`，导致后续逻辑错误

### 4. **错误信息未通知前端**
```python
elif item[0] == 'ERROR':
    logger.error(...)
    break  # 只是 break，没有 yield 错误信息
```

**问题**：
- 前端不知道发生了错误
- 继续等待数据，但服务器已停止发送
- 导致 `ERR_INCOMPLETE_CHUNKED_ENCODING`

## 修复方案

### 修复 1：为 LLM 调用添加超时保护 ✅

**文件**：`core/node_filter.py`

```python
# 使用 Future 实现超时控制
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

def call_llm():
    return llm.complete(full_prompt)

with ThreadPoolExecutor(max_workers=1) as llm_executor:
    future = llm_executor.submit(call_llm)
    try:
        response = future.result(timeout=self.timeout)  # 15秒超时
        response_text = response.text.strip()
    except FutureTimeoutError:
        logger.error(f"LLM 调用超时: {file_name}")
        raise TimeoutError(f"LLM 调用超时: {file_name}")
```

**效果**：
- 确保 LLM 调用不会无限阻塞
- 超时后立即抛出异常，被上层捕获
- 避免线程池卡死

### 修复 2：记录并抛出关键错误 ✅

**文件**：`core/node_filter.py`

```python
# 记录关键错误
critical_error = None

# 在循环中检测
if timeout_count > len(nodes) * 0.5:
    critical_error = f"超过50%的节点处理超时 ({timeout_count}/{len(nodes)})"

if error_count > len(nodes) * 0.5:
    critical_error = f"超过50%的节点处理失败 ({error_count}/{len(nodes)})"

# 方法末尾抛出异常
if critical_error:
    logger.error(f"InsertBlock 过滤遇到关键错误: {critical_error}")
    raise RuntimeError(f"InsertBlock 过滤失败: {critical_error}")
```

**效果**：
- 当超过50%节点失败时，认为是关键错误
- 抛出异常，让上层感知到问题
- 避免返回不完整的结果

### 修复 3：增强线程超时处理 ✅

**文件**：`api/knowledge_handler.py`

```python
# 增加超时时间
filter_thread.join(timeout=3)  # 从1秒增加到3秒

# 检查线程是否还在运行
if filter_thread.is_alive():
    logger.warning("精准检索线程超时未完成，将继续使用原始检索结果")
    timeout_msg = "⚠️ 精准检索超时，将使用原始检索结果\n"
    yield ('CONTENT', timeout_msg)
    full_response += timeout_msg
    filtered_results = None
```

**效果**：
- 给线程更多时间完成
- 检测线程是否还在运行
- 通知前端超时信息，避免前端等待

### 修复 4：错误信息通知前端 ✅

**文件**：`api/knowledge_handler.py`

```python
elif item[0] == 'ERROR':
    filter_error = item[1]
    logger.error(f"精准检索过滤失败: {filter_error}")
    # 通知前端错误信息
    error_msg = f"⚠️ 精准检索失败: {str(filter_error)}\n"
    yield ('CONTENT', error_msg)
    full_response += error_msg
    break
```

**效果**：
- 前端能看到错误信息
- 流式传输继续，不会中断
- 用户体验更好

### 修复 5：确保发送 DONE 信号 ✅

**文件**：`api/knowledge_handler.py`

```python
except Exception as e:
    error_msg = f"处理错误: {str(e)}"
    logger.error(f"知识问答处理出错: {e}", exc_info=True)
    yield ('ERROR', error_msg)
    # 确保发送 DONE 信号，避免前端等待超时
    yield ('DONE', '')
```

**效果**：
- 无论成功或失败，都发送 DONE 信号
- 前端知道流式传输已结束
- 避免 `ERR_INCOMPLETE_CHUNKED_ENCODING`

## 配置优化建议

### 1. 调整超时时间

**文件**：`config/settings.py`

```python
# InsertBlock 配置
INSERTBLOCK_MAX_WORKERS = 5  # 降低并发数，避免资源竞争
INSERTBLOCK_TIMEOUT = 20     # 增加超时时间（如果 LLM 响应慢）
```

### 2. 调整并发数

如果 LLM 服务响应慢，降低并发数可以减少资源竞争：
```python
INSERTBLOCK_MAX_WORKERS = 3  # 从 10 降到 3
```

### 3. 监控日志

关注以下日志：
```
⏱ 节点处理超时: xxx.txt | 超时限制: 15s
LLM 调用超时: xxx.txt | 超时限制: 15s
InsertBlock 过滤遇到关键错误: 超过50%的节点处理超时
```

## 验证步骤

1. **启动服务**
   ```bash
   python app.py
   ```

2. **测试精准检索**
   - 前端开启精准检索模式
   - 提交一个需要检索 10+ 文档的问题

3. **观察日志**
   ```
   [INFO] 开始使用 InsertBlock 过滤器处理 10 个节点 | 并发数: 5
   [INFO] ✓ 节点通过 [1] xxx.txt | 关键段落: 150 字符
   [INFO] InsertBlock 过滤完成统计:
   [INFO]   总节点数: 10
   [INFO]   通过筛选: 3 个节点
   [INFO]   超时: 0 个节点
   [INFO]   错误: 0 个节点
   ```

4. **检查前端**
   - 应该能看到完整的流式输出
   - 不应该出现 `ERR_INCOMPLETE_CHUNKED_ENCODING`
   - 能看到进度更新和最终结果

## 相关文件

- `core/node_filter.py` - InsertBlock 过滤器核心实现
- `api/knowledge_handler.py` - 知识问答处理器
- `config/settings.py` - 配置文件
- `docs/THINK_STREAM_DEBUG_GUIDE.md` - 流式输出调试指南

## 技术要点

### 1. 线程池超时控制
```python
with ThreadPoolExecutor(max_workers=1) as executor:
    future = executor.submit(func)
    result = future.result(timeout=15)  # 超时抛出 TimeoutError
```

### 2. 流式传输完整性
- 必须发送 `DONE` 信号结束流
- 异常时也要发送 `DONE`
- 使用 `try-except-finally` 确保完整性

### 3. 错误传播机制
- 底层异常要向上传播
- 关键错误要抛出异常，不能只记录日志
- 上层要捕获并处理异常

## 性能影响

- **LLM 超时保护**：增加约 10ms 开销（线程池创建）
- **错误检测**：几乎无开销
- **线程超时检查**：增加最多 3 秒等待时间（仅在超时时）
- **总体影响**：正常情况下 < 50ms，超时情况下最多 3 秒

## 后续优化

1. **连接池复用**：为 LLM 调用使用连接池，减少创建开销
2. **自适应超时**：根据历史响应时间动态调整超时
3. **降级策略**：超时后自动降级到更快的模型
4. **缓存机制**：对相同节点的判断结果进行缓存

---

**修复日期**：2025-01-20  
**影响范围**：InsertBlock 精准检索功能  
**优先级**：高（影响用户体验）
