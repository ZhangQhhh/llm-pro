# Keyword Table Fallback 方案使用指南

## 📋 方案概述

Keyword Table Fallback 是一个智能检索回退机制，优先使用关键词表检索，失败时自动回退到向量/BM25混合检索。

### 检索流程
```
用户查询
    ↓
Keyword Table 检索
    ↓
   成功? ──→ 是 ──→ 返回结果
    ↓
   否
    ↓
BM25/向量混合检索
    ↓
返回结果
```

## 🔧 配置说明

### 1. 环境变量配置 (`.env`)

```bash
# Keyword Table 索引配置
ENABLE_KEYWORD_TABLE=true                     # 是否启用（默认：false）
RETRIEVAL_TOP_K_KEYWORD=10                    # 返回节点数（默认：10）
KEYWORD_TABLE_MIN_SCORE=0.3                   # 最低分数阈值（默认：0.3）
KEYWORD_TABLE_FALLBACK_MODE=keyword_bm25_vector  # 回退模式
```

### 2. 回退模式说明

- **`keyword_vector`**: Keyword Table → Vector（跳过 BM25）
  - 当 Keyword Table 无结果时，直接使用向量检索
  - 适合语义理解要求高的场景
  
- **`keyword_bm25_vector`**: Keyword Table → BM25 → Vector（推荐，默认）
  - 当 Keyword Table 无结果时，使用完整的混合检索（BM25 + 向量）
  - 综合关键词匹配和语义理解
  - 召回率最高，推荐使用

## 📦 核心组件

### 1. KeywordTableRetriever (`core/keyword_table_retriever.py`)
- 封装 LlamaIndex 的 KeywordTableIndex
- 支持停用词过滤
- 自动标记检索来源

### 2. KnowledgeService 扩展
- `load_keyword_table_index()`: 加载索引
- `create_keyword_table_retriever()`: 创建检索器

### 3. KnowledgeHandler 集成
- 在 `_retrieve_and_rerank_with_retriever` 中实现 Fallback
- 自动记录检索模式和统计信息

## 🚀 使用步骤

### 步骤 1: 构建 Keyword Table 索引

```bash
# 使用默认配置
python scripts/build_keyword_index.py

# 自定义配置
python scripts/build_keyword_index.py \
    --data-dir /path/to/data \
    --persist-dir /path/to/storage \
    --chunk-size 512 \
    --chunk-overlap 50 \
    --force-rebuild
```

**输出示例**:
```
正在加载文档...
 加载了 150 个文档
正在分块 | chunk_size=512, overlap=50
 生成了 2500 个节点
正在构建 Keyword Table 索引...
 Keyword Table 索引构建完成
正在持久化索引到: /opt/rag_final_project/storage/vector_store/keyword_table
 索引持久化完成
============================================================
Keyword Table 索引构建完成
文档数: 150
节点数: 2500
存储位置: /opt/rag_final_project/storage/vector_store/keyword_table
============================================================
```

**注意**: Keyword Table 索引存储在 `storage/vector_store/keyword_table` 目录中，与向量索引同级，便于统一管理。

### 步骤 2: 启用 Keyword Table

编辑 `.env`:
```bash
ENABLE_KEYWORD_TABLE=true
```

### 步骤 3: 启动应用

```bash
python app.py
```

**启动日志**:
```
============================================================
开始初始化 Keyword Table 索引
============================================================
正在加载 Keyword Table 索引: /opt/rag_final_project/storage/vector_store/keyword_table
 Keyword Table 索引加载成功
创建 Keyword Table 检索器...
KeywordTableRetriever 初始化完成 | top_k=10 | min_score=0.3
 Keyword Table 检索器创建成功
============================================================
Keyword Table 功能初始化完成
============================================================
✓ 知识库功能已启用: Keyword Table, 隐藏知识库, 多库检索+意图分类
```

### 步骤 4: 测试检索

提问后查看日志：

```
[Keyword Table] 开始检索 | 回退模式: keyword_bm25_vector
[KeywordTable检索-原始分词] ['签证', '申请', '流程']
[KeywordTable检索-停用词过滤后] ['签证', '申请', '流程']
[KeywordTable检索] 原始检索返回 8 个节点
[KeywordTable检索] 过滤后返回 8 个节点 | 分数范围: 0.8567 - 0.3245
[Keyword Table] 检索成功 | 返回 8 个节点
检索完成 | 模式: keyword_table | 结果数: 8
```

## 📊 监控和调试

### 1. 查看检索模式统计

```bash
# 统计各检索模式使用次数
grep "检索完成 | 模式:" logs/app.log | cut -d'|' -f2 | sort | uniq -c

# 输出示例：
#  45 模式: keyword_table
#  12 模式: hybrid
#   3 模式: multi_kb
```

### 2. 查看 Keyword Table 命中率

```bash
# 计算命中率
total=$(grep -c "Keyword Table] 开始检索" logs/app.log)
success=$(grep -c "Keyword Table] 检索成功" logs/app.log)
echo "命中率: $(echo "scale=2; $success/$total*100" | bc)%"
```

### 3. 查看回退情况

```bash
# 查看回退到其他检索器的次数
grep "检索回退] 使用原有检索器" logs/app.log | wc -l
```

### 4. 分析低分过滤

```bash
# 查看被过滤的低分节点
grep "过滤低分节点" logs/app.log
```

## 🎯 性能优化

### 1. 调整分数阈值

如果命中率太低，降低阈值：
```bash
KEYWORD_TABLE_MIN_SCORE=0.2  # 从 0.3 降到 0.2
```

### 2. 调整返回数量

如果结果不够丰富，增加返回数量：
```bash
RETRIEVAL_TOP_K_KEYWORD=15  # 从 10 增加到 15
```

### 3. 优化关键词提取

编辑 `scripts/build_keyword_index.py`，自定义关键词提取模板：

```python
keyword_extract_template = """
从以下文本中提取最重要的关键词（3-10个），优先提取：
1. 专业术语（如"J2签证"、"APEC卡"）
2. 动作词（如"申请"、"办理"）
3. 实体名称（如"移民局"、"大使馆"）

文本：
{context_str}

关键词（用逗号分隔）：
"""

keyword_index = KeywordTableIndex(
    nodes=nodes,
    keyword_extract_template=keyword_extract_template
)
```

### 4. 重建索引

修改配置后重建索引：
```bash
python scripts/build_keyword_index.py --force-rebuild
```

## 🔍 故障排除

### 问题 1: 索引加载失败

**错误信息**:
```
Keyword Table 索引目录不存在: /opt/rag_final_project/storage/keyword_table
请先运行: python scripts/build_keyword_index.py
```

**解决方案**:
```bash
python scripts/build_keyword_index.py
```

### 问题 2: 检索无结果

**可能原因**:
1. 分数阈值过高
2. 关键词提取不准确
3. 停用词过滤过度

**解决方案**:
```bash
# 1. 降低阈值
KEYWORD_TABLE_MIN_SCORE=0.1

# 2. 查看实际提取的关键词
grep "KeywordTable检索-停用词过滤后" logs/app.log

# 3. 检查停用词表
cat dict/stopwords.txt
```

### 问题 3: 性能下降

**可能原因**:
- Keyword Table 索引过大
- 返回节点数过多

**解决方案**:
```bash
# 减少返回数量
RETRIEVAL_TOP_K_KEYWORD=5

# 提高分数阈值
KEYWORD_TABLE_MIN_SCORE=0.5
```

## 📈 效果评估

### 1. 召回率

```bash
# 对比 Keyword Table 和混合检索的召回率
# 在测试集上运行，统计相关文档被检索到的比例
```

### 2. 响应时间

```bash
# 统计平均检索时间
grep "检索完成" logs/app.log | grep -oP "耗时: \K[0-9.]+" | awk '{sum+=$1; n++} END {print "平均耗时:", sum/n, "ms"}'
```

### 3. 准确率

```bash
# 人工评估 Top5 结果的相关性
# 计算 Keyword Table 和混合检索的准确率对比
```

## 🚨 注意事项

1. **索引更新**: 文档更新后需要重建 Keyword Table 索引
2. **内存占用**: Keyword Table 索引会占用额外内存
3. **兼容性**: 确保 LlamaIndex 版本支持 KeywordTableIndex
4. **灰度上线**: 建议先在小范围测试，确认效果后再全量上线

## 📚 相关文档

- [关键词排序优化](./KEYWORD_AND_FORMAT_OPTIMIZATION.md)
- [响应格式化器](./RESPONSE_FORMATTER_USAGE.md)
- [隐藏知识库指南](./HIDDEN_KB_FLOW_GUIDE.md)

---

通过 Keyword Table Fallback，可以显著提升关键词匹配场景的检索准确率！
