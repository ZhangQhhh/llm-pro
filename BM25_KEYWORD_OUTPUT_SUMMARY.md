# BM25 关键词输出功能实现总结

## 🎯 功能概述

实现了将 BM25 关键词检索的详细信息输出到前端，包括：
1. 检索来源（向量/关键词/混合）
2. 各检索方式的分数和排名
3. 匹配的关键词列表

## 📝 实现时间

2025-11-12

## 🔧 核心修改

### 1. BM25 关键词追踪（`core/retriever.py`）

**位置**: `CleanBM25Retriever._retrieve()` 方法（第 74-95 行）

**功能**: 在 BM25 检索时记录匹配的关键词

```python
def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
    # 对查询进行分词
    query_keywords = jieba.lcut(query_bundle.query_str)
    
    # 检索
    retrieved_nodes = self._bm25_retriever.retrieve(tokenized_bundle)
    
    # 替换回原始节点，并添加匹配关键词信息
    for node_with_score in retrieved_nodes:
        original_node = self._id_to_original_node.get(node_with_score.node.node_id)
        if original_node:
            # 找出文档中匹配的关键词（过滤单字符）
            doc_content = original_node.get_content()
            matched_keywords = [kw for kw in query_keywords if kw in doc_content and len(kw) > 1]
            
            # 将匹配的关键词添加到节点元数据
            original_node.metadata['bm25_matched_keywords'] = matched_keywords
            original_node.metadata['bm25_query_keywords'] = query_keywords
```

**元数据字段**:
- `bm25_matched_keywords`: 匹配的关键词列表
- `bm25_query_keywords`: 查询的所有关键词

---

### 2. 混合检索元数据设置（`core/retriever.py`）

**位置**: `HybridRetriever._retrieve()` 方法（第 161-180 行）

**功能**: 在 RRF 融合时记录检索来源和分数

```python
def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
    # 执行向量检索和 BM25 检索
    automerging_nodes = self._automerging.retrieve(query_bundle)
    bm25_nodes = self._bm25.retrieve(query_bundle)
    
    # 计算排名和分数
    vector_ranks = {node.node.node_id: rank for rank, node in enumerate(automerging_nodes, 1)}
    bm25_ranks = {node.node.node_id: rank for rank, node in enumerate(bm25_nodes, 1)}
    vector_scores = {n.node.node_id: n.score for n in automerging_nodes}
    bm25_scores = {n.node.node_id: n.score for n in bm25_nodes}
    
    # 为每个节点添加元数据
    for node_id, score in fused_scores.items():
        node_obj = all_nodes[node_id]
        sources = []
        if node_id in vector_ranks:
            sources.append("vector")
        if node_id in bm25_ranks:
            sources.append("keyword")
        
        node_obj.metadata['vector_score'] = vector_scores.get(node_id, 0.0)
        node_obj.metadata['bm25_score'] = bm25_scores.get(node_id, 0.0)
        node_obj.metadata['vector_rank'] = vector_ranks.get(node_id)
        node_obj.metadata['bm25_rank'] = bm25_ranks.get(node_id)
        node_obj.metadata['retrieval_sources'] = sources
        node_obj.metadata['initial_score'] = score
```

**元数据字段**:
- `retrieval_sources`: 检索来源列表 `["vector"]` / `["keyword"]` / `["vector", "keyword"]`
- `vector_score`: 向量检索分数
- `bm25_score`: BM25 检索分数
- `vector_rank`: 向量检索排名（1-based）
- `bm25_rank`: BM25 检索排名（1-based）
- `initial_score`: RRF 融合分数

---

### 3. 重排序元数据保留（`api/knowledge_handler.py`）

**位置**: `_retrieve_and_rerank_with_retriever()` 方法（第 1317-1347 行）

**问题**: 重排序器（reranker）会创建新的节点对象，导致原始元数据丢失

**解决方案**: 在重排序前保存元数据，重排序后恢复

```python
def _retrieve_and_rerank_with_retriever(self, question, rerank_top_n, retriever):
    # 检索
    retrieved_nodes = retriever.retrieve(query_bundle)
    
    # ⭐ 保存原始节点的检索元数据
    original_metadata = {}
    for node in retrieved_nodes:
        node_id = node.node.node_id
        original_metadata[node_id] = {
            'retrieval_sources': node.node.metadata.get('retrieval_sources', []),
            'vector_score': node.node.metadata.get('vector_score', 0.0),
            'bm25_score': node.node.metadata.get('bm25_score', 0.0),
            'bm25_matched_keywords': node.node.metadata.get('bm25_matched_keywords', []),
            'bm25_query_keywords': node.node.metadata.get('bm25_query_keywords', []),
            'vector_rank': node.node.metadata.get('vector_rank'),
            'bm25_rank': node.node.metadata.get('bm25_rank'),
            'initial_score': node.node.metadata.get('initial_score', node.score)
        }
    
    # 重排序
    reranked_nodes = self.reranker.postprocess_nodes(retrieved_nodes, query_bundle)
    
    # ⭐ 恢复原始节点的检索元数据
    for node in reranked_nodes:
        node_id = node.node.node_id
        if node_id in original_metadata:
            node.node.metadata.update(original_metadata[node_id])
```

---

### 4. 前端数据格式化（`api/knowledge_handler.py`）

**位置**: `_format_sources()` 方法（第 673-706 行）

**功能**: 将节点元数据格式化为前端 JSON 数据

```python
def _format_sources(self, final_nodes):
    """格式化参考来源"""
    for i, node in enumerate(final_nodes):
        # 提取元数据
        initial_score = node.node.metadata.get('initial_score', 0.0)
        retrieval_sources = node.node.metadata.get('retrieval_sources', [])
        vector_score = node.node.metadata.get('vector_score', 0.0)
        bm25_score = node.node.metadata.get('bm25_score', 0.0)
        vector_rank = node.node.metadata.get('vector_rank')
        bm25_rank = node.node.metadata.get('bm25_rank')
        
        # 构建基础数据
        source_data = {
            "id": i + 1,
            "fileName": node.node.metadata.get('file_name', '未知'),
            "initialScore": f"{initial_score:.4f}",
            "rerankedScore": f"{node.score:.4f}",
            "content": node.node.text.strip(),
            "retrievalSources": retrieval_sources,
            "vectorScore": f"{vector_score:.4f}",
            "bm25Score": f"{bm25_score:.4f}"
        }
        
        # 添加排名信息（如果存在）
        if vector_rank is not None:
            source_data['vectorRank'] = vector_rank
        if bm25_rank is not None:
            source_data['bm25Rank'] = bm25_rank
        
        # 添加匹配的关键词（如果是关键词检索）
        if 'keyword' in retrieval_sources:
            matched_keywords = node.node.metadata.get('bm25_matched_keywords', [])
            if matched_keywords:
                source_data['matchedKeywords'] = matched_keywords
        
        yield ('SOURCE', json.dumps(source_data, ensure_ascii=False))
```

---

## 📊 前端数据结构

### 完整示例

```json
{
  "id": 1,
  "fileName": "免签政策.md",
  "initialScore": "0.0234",
  "rerankedScore": "0.8567",
  "content": "文档内容...",
  "retrievalSources": ["vector", "keyword"],
  "vectorScore": "0.7234",
  "bm25Score": "0.6543",
  "vectorRank": 3,
  "bm25Rank": 5,
  "matchedKeywords": ["泰国", "免签", "30天"]
}
```

### 字段说明

| 字段 | 类型 | 说明 | 是否必选 |
|------|------|------|---------|
| `id` | `number` | 序号 | ✅ 必选 |
| `fileName` | `string` | 文件名 | ✅ 必选 |
| `initialScore` | `string` | RRF 融合分数 | ✅ 必选 |
| `rerankedScore` | `string` | 重排序分数 | ✅ 必选 |
| `content` | `string` | 文档内容 | ✅ 必选 |
| `retrievalSources` | `string[]` | 检索来源 | ✅ 必选 |
| `vectorScore` | `string` | 向量检索分数 | ✅ 必选 |
| `bm25Score` | `string` | BM25 检索分数 | ✅ 必选 |
| `vectorRank` | `number` | 向量检索排名 | ⭕ 可选 |
| `bm25Rank` | `number` | BM25 检索排名 | ⭕ 可选 |
| `matchedKeywords` | `string[]` | 匹配的关键词 | ⭕ 可选 |

---

## 🎨 前端展示示例

### 方案 1：标签 + 排名

```html
<div class="source-item">
  <div class="source-header">
    <span class="file-name">免签政策.md</span>
    <div class="badges">
      <span class="badge badge-vector">🧠 语义检索 #3</span>
      <span class="badge badge-keyword">🔑 关键词检索 #5</span>
    </div>
  </div>
  
  <div class="matched-keywords">
    <span class="label">匹配关键词：</span>
    <span class="keyword">泰国</span>
    <span class="keyword">免签</span>
    <span class="keyword">30天</span>
  </div>
  
  <div class="scores">
    <span>语义相似度: 0.7234 (排名 #3)</span>
    <span>关键词得分: 0.6543 (排名 #5)</span>
  </div>
</div>
```

### 方案 2：图标 + 徽章

```html
<div class="retrieval-icons">
  <i class="icon-vector" title="通过语义检索找到 (排名 #3)">
    🧠 <span class="rank-badge">#3</span>
  </i>
  <i class="icon-keyword" title="匹配关键词: 泰国, 免签, 30天 (排名 #5)">
    🔑 <span class="rank-badge">#5</span>
  </i>
</div>
```

---

## 📁 相关文件

### 后端代码
- `core/retriever.py` - BM25 关键词提取和混合检索元数据设置
- `api/knowledge_handler.py` - 重排序元数据保留和前端数据格式化
- `config/settings.py` - RRF 权重配置

### 文档
- `FRONTEND_KEYWORD_DISPLAY.md` - 前端展示完整指南（包含 Vue/React 示例）
- `HYBRID_RETRIEVAL_TUNING.md` - RRF 权重调优指南
- `BM25_KEYWORD_OUTPUT_SUMMARY.md` - 本文档

---

## ✅ 测试验证

### 1. 重启服务

```bash
cd /opt/rag_final_project/code_here/llm_pro
pkill -f app.py
nohup python app.py > app.log 2>&1 &
```

### 2. 发送测试请求

```bash
curl -X POST http://localhost:8000/api/knowledge/qa \
  -H "Content-Type: application/json" \
  -d '{"question": "泰国免签政策是什么？", "top_k": 10}'
```

### 3. 检查 SOURCE 事件

前端应该能收到包含以下字段的 JSON 数据：
- ✅ `retrievalSources`
- ✅ `vectorScore`
- ✅ `bm25Score`
- ✅ `vectorRank`（如果是向量检索）
- ✅ `bm25Rank`（如果是关键词检索）
- ✅ `matchedKeywords`（如果是关键词检索且有匹配）

---

## 🐛 已解决的问题

### 问题 1: 重排序后元数据丢失

**现象**: 前端收到的数据中 `retrievalSources`、`vectorScore` 等字段为 `undefined`

**原因**: 重排序器（reranker）创建新的 `NodeWithScore` 对象，没有保留原始元数据

**解决**: 在重排序前保存元数据，重排序后恢复（第 1317-1347 行）

### 问题 2: 关键词未追踪

**现象**: 无法知道哪些关键词匹配了文档

**原因**: BM25 检索器只返回分数，没有记录匹配的关键词

**解决**: 在 `CleanBM25Retriever._retrieve()` 中手动提取匹配的关键词（第 74-95 行）

---

## 🔄 后续优化建议

1. **关键词权重排序**
   - 根据 TF-IDF 权重对关键词排序
   - 只显示最重要的 3-5 个关键词

2. **上下文片段提取**
   - 提取包含关键词的上下文片段
   - 类似搜索引擎的摘要高亮

3. **检索解释生成**
   - 自动生成检索原因说明
   - 例如："该文档在语义上与您的查询高度相关（相似度 0.72），并且包含关键词'泰国'、'免签'"

4. **性能优化**
   - 对于长文档，只高亮前 500 字符
   - 使用虚拟滚动优化大量结果的渲染

---

## 📞 技术支持

如有问题，请查看：
- 前端文档：`FRONTEND_KEYWORD_DISPLAY.md`
- 后端代码：`core/retriever.py`、`api/knowledge_handler.py`
- 配置文件：`config/settings.py`
