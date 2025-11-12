# 如何查看规则注入日志

## 快速查看

### 方法1：实时查看规则注入日志

```bash
# 过滤规则注入相关日志
tail -f /opt/rag_final_project/qa_logs/app.log | grep "规则注入"
```

### 方法2：查看最近的规则注入记录

```bash
# 查看最近20条规则注入日志
grep "规则注入" /opt/rag_final_project/qa_logs/app.log | tail -20
```

### 方法3：按问题查看

```bash
# 查看特定时间段的日志
grep "规则注入" /opt/rag_final_project/qa_logs/app.log | grep "2025-01-07 12:"
```

## 日志格式说明

### 完整的规则注入流程日志

```
[规则注入] 开始检索规则知识库...
[规则注入] 检索到 3 条规则，Top3分数: 0.856, 0.782, 0.654
[规则注入] 发现 2 条高相关性规则（>=0.7），注入前 2 条
[规则注入] ✓ 已注入 2 条规则，总节点数: 22
[规则注入] 规则1 (分数: 1.000): 【特殊规定1】：JS0只有在国内赴港出境时候扣减次数、JS1只有在国内出境时候赴澳扣减次数，JS2只有港方入境时候扣减次数，JS3只有澳方入境时候扣减次数，为前提分析。...
[规则注入] 规则2 (分数: 0.990): 【特殊规定2】：出入境手续办理规则。办理出入境手续时，应当向边检机关交验本人的护照或者其他旅行证件等出境入境证件，填写出境入境登记卡，经边检机关查验准许，方可出境入境。...
```

### 日志字段解释

| 字段 | 说明 | 示例 |
|------|------|------|
| `检索到 X 条规则` | 从规则库检索到的总数 | `检索到 3 条规则` |
| `Top3分数` | 前3条规则的相关性分数 | `0.856, 0.782, 0.654` |
| `高相关性规则` | 分数 >= 0.7 的规则数量 | `发现 2 条高相关性规则` |
| `注入前 X 条` | 实际注入的规则数量 | `注入前 2 条` |
| `规则X (分数: Y)` | 具体注入的规则及其分数 | `规则1 (分数: 1.000)` |
| `规则内容预览` | 规则的前100个字符 | `【特殊规定1】：JS0只有在...` |

## 三种注入场景

### 场景1：高相关性（分数 >= 0.7）

**用户问题**：`"JS0 在什么时候扣减次数？"`

**日志输出**：
```
[规则注入] 开始检索规则知识库...
[规则注入] 检索到 3 条规则，Top3分数: 0.856, 0.782, 0.654
[规则注入] 发现 2 条高相关性规则（>=0.7），注入前 2 条
[规则注入] ✓ 已注入 2 条规则，总节点数: 22
[规则注入] 规则1 (分数: 1.000): 【特殊规定1】：JS0只有在国内赴港出境时候扣减次数...
[规则注入] 规则2 (分数: 0.990): 【特殊规定2】：出入境手续办理规则...
```

**解读**：
- ✅ 检索到2条高相关性规则（0.856, 0.782）
- ✅ 注入了2条规则
- ✅ 规则1和规则2都与JS计数器相关

---

### 场景2：中等相关性（0.5 <= 分数 < 0.7）

**用户问题**：`"护照有效期不足6个月可以出境吗？"`

**日志输出**：
```
[规则注入] 开始检索规则知识库...
[规则注入] 检索到 3 条规则，Top3分数: 0.623, 0.487, 0.356
[规则注入] 无高相关性规则，但最高分 0.623 >= 0.5，注入 1 条中等相关性规则
[规则注入] ✓ 已注入 1 条规则，总节点数: 21
[规则注入] 规则1 (分数: 1.000): 【特殊规定2】：出入境手续办理规则。办理出入境手续时，应当向边检机关交验本人的护照...
```

**解读**：
- ⚠️ 无高相关性规则
- ✅ 最高分0.623 >= 0.5，至少注入1条
- ✅ 注入了出入境手续相关规则

---

### 场景3：低相关性（分数 < 0.5）

**用户问题**：`"北京今天天气怎么样？"`

**日志输出**：
```
[规则注入] 开始检索规则知识库...
[规则注入] 检索到 3 条规则，Top3分数: 0.356, 0.289, 0.234
[规则注入] 最高分 0.356 < 0.5，相关性过低，跳过注入
```

**解读**：
- ❌ 所有规则相关性都很低
- ❌ 不注入任何规则
- ✅ 避免噪音干扰

## 统计分析

### 统计注入规则数量分布

```bash
# 统计注入了多少条规则的次数
grep "已注入" /opt/rag_final_project/qa_logs/app.log | \
  awk '{print $4}' | \
  sort | uniq -c

# 示例输出：
#  45 1条规则
#  23 2条规则
#  12 3条规则
#   5 4条规则
```

### 统计跳过注入的次数

```bash
# 统计相关性过低跳过注入的次数
grep "相关性过低，跳过注入" /opt/rag_final_project/qa_logs/app.log | wc -l
```

### 查看规则相关性分数分布

```bash
# 查看最近20次的规则检索分数
grep "Top3分数" /opt/rag_final_project/qa_logs/app.log | tail -20
```

## 调试技巧

### 1. 查看特定规则被注入的频率

```bash
# 查看"特殊规定1"被注入的次数
grep "规则注入.*特殊规定1" /opt/rag_final_project/qa_logs/app.log | wc -l
```

### 2. 查看某个问题的完整注入流程

```bash
# 假设问题ID是 req_12345
grep "req_12345" /opt/rag_final_project/qa_logs/app.log | grep "规则注入"
```

### 3. 监控规则注入失败

```bash
# 查看规则注入失败的情况
grep "规则检索失败" /opt/rag_final_project/qa_logs/app.log
```

## 在代码中查看

### 方法1：在 KnowledgeHandler 中添加调试日志

```python
# api/knowledge_handler.py

# 在 _retrieve_and_rerank 方法中
if self.rules_retriever:
    rules_nodes = self.rules_retriever.retrieve(question)
    
    # 添加调试日志
    print(f"\n{'='*60}")
    print(f"问题: {question}")
    print(f"检索到规则数: {len(rules_nodes)}")
    for i, node in enumerate(rules_nodes[:5], 1):
        print(f"规则{i} (分数: {node.score:.3f}): {node.node.get_content()[:80]}")
    print(f"{'='*60}\n")
```

### 方法2：使用 Python 脚本分析日志

```python
# scripts/analyze_rules_injection.py

import re
from collections import Counter

def analyze_rules_injection(log_file):
    """分析规则注入日志"""
    
    # 统计注入数量
    injection_counts = []
    
    # 统计规则类型
    rule_types = []
    
    with open(log_file, 'r', encoding='utf-8') as f:
        for line in f:
            # 提取注入数量
            if '已注入' in line:
                match = re.search(r'已注入 (\d+) 条规则', line)
                if match:
                    injection_counts.append(int(match.group(1)))
            
            # 提取规则类型
            if '特殊规定' in line:
                match = re.search(r'【特殊规定(\d+)】', line)
                if match:
                    rule_types.append(f"特殊规定{match.group(1)}")
    
    # 输出统计结果
    print("注入数量分布:")
    for count, freq in Counter(injection_counts).most_common():
        print(f"  {count}条规则: {freq}次")
    
    print("\n规则类型分布:")
    for rule, freq in Counter(rule_types).most_common():
        print(f"  {rule}: {freq}次")

# 使用
analyze_rules_injection('/opt/rag_final_project/qa_logs/app.log')
```

## 可视化（可选）

### 使用 Grafana 监控规则注入

如果你有 Grafana 和 Loki，可以创建仪表板：

```promql
# 规则注入成功率
sum(rate({job="llm_pro"} |= "规则注入" |= "已注入"[5m]))

# 规则注入数量分布
histogram_quantile(0.95, 
  sum(rate({job="llm_pro"} |= "已注入" | regexp "已注入 (?P<count>\\d+) 条规则"[5m])) by (count)
)

# 跳过注入的频率
sum(rate({job="llm_pro"} |= "相关性过低，跳过注入"[5m]))
```

## 总结

### 快速查看命令

```bash
# 实时监控
tail -f /opt/rag_final_project/qa_logs/app.log | grep "规则注入"

# 查看最近记录
grep "规则注入" /opt/rag_final_project/qa_logs/app.log | tail -20

# 统计注入情况
grep "已注入" /opt/rag_final_project/qa_logs/app.log | awk '{print $4}' | sort | uniq -c
```

### 日志位置

- **应用日志**：`/opt/rag_final_project/qa_logs/app.log`
- **规则注入标签**：`[规则注入]`
- **关键字段**：检索数量、Top3分数、注入数量、规则内容

### 日志级别

所有规则注入日志都是 `INFO` 级别，默认会输出到日志文件。
