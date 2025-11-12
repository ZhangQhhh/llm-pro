# 前端关键词显示功能说明

## 🎯 功能概述

现在后端会在参考来源（SOURCE）数据中返回 BM25 关键词匹配信息，前端可以展示：
1. 该文档是通过**向量检索**还是**关键词检索**找到的
2. 如果是关键词检索，具体匹配了哪些关键词

## 📊 返回的数据结构

### 原始格式（修改前）
```json
{
  "id": 1,
  "fileName": "免签政策.md",
  "initialScore": "0.0234",
  "rerankedScore": "0.8567",
  "content": "文档内容..."
}
```

### 新格式（修改后）
```json
{
  "id": 1,
  "fileName": "免签政策.md",
  "initialScore": "0.0234",
  "rerankedScore": "0.8567",
  "content": "文档内容...",
  
  // 新增字段
  "retrievalSources": ["vector", "keyword"],  // 检索来源
  "vectorScore": "0.7234",                    // 向量检索分数
  "bm25Score": "0.6543",                      // BM25 检索分数
  "vectorRank": 3,                            // 向量检索排名（可选，仅当 retrievalSources 包含 "vector" 时）
  "bm25Rank": 5,                              // BM25 检索排名（可选，仅当 retrievalSources 包含 "keyword" 时）
  "matchedKeywords": ["泰国", "免签", "30天"]  // 匹配的关键词（可选，仅当 retrievalSources 包含 "keyword" 时）
}
```

## 🔍 字段说明

### retrievalSources
- **类型**: `string[]`
- **可能值**: 
  - `["vector"]` - 仅通过向量检索找到
  - `["keyword"]` - 仅通过 BM25 关键词检索找到
  - `["vector", "keyword"]` - 同时被两种检索方式找到（混合检索）
- **用途**: 显示该文档的检索来源

### vectorScore
- **类型**: `string`
- **格式**: `"0.xxxx"` (4位小数)
- **说明**: 向量检索的原始分数（语义相似度）
- **范围**: 0.0 - 1.0（越高越相似）

### bm25Score
- **类型**: `string`
- **格式**: `"0.xxxx"` (4位小数)
- **说明**: BM25 关键词检索的原始分数
- **范围**: 0.0 - ∞（越高越相关）

### vectorRank
- **类型**: `number`
- **说明**: 该文档在向量检索结果中的排名（1 = 第一名）
- **仅在**: `retrievalSources` 包含 `"vector"` 时存在
- **用途**: 显示该文档在语义检索中的排名位置

### bm25Rank
- **类型**: `number`
- **说明**: 该文档在 BM25 关键词检索结果中的排名（1 = 第一名）
- **仅在**: `retrievalSources` 包含 `"keyword"` 时存在
- **用途**: 显示该文档在关键词检索中的排名位置

### matchedKeywords
- **类型**: `string[]`
- **说明**: 用户查询中被文档匹配到的关键词
- **仅在**: `retrievalSources` 包含 `"keyword"` 时存在
- **示例**: `["泰国", "免签", "30天"]`

## 📋 TypeScript 接口定义

```typescript
interface SourceData {
  id: number;                      // 序号
  fileName: string;                // 文件名
  initialScore: string;            // 初始融合分数（RRF）
  rerankedScore: string;           // 重排序后的分数
  content: string;                 // 文档内容
  retrievalSources: string[];      // 检索来源：["vector"] | ["keyword"] | ["vector", "keyword"]
  vectorScore: string;             // 向量检索分数
  bm25Score: string;               // BM25 检索分数
  vectorRank?: number;             // 向量检索排名（可选）
  bm25Rank?: number;               // BM25 检索排名（可选）
  matchedKeywords?: string[];      // 匹配的关键词（可选）
}
```

## 💡 前端展示建议

### 方案 1：标签展示（推荐）

```html
<div class="source-item">
  <div class="source-header">
    <span class="file-name">免签政策.md</span>
    <div class="badges">
      <!-- 检索来源标签 -->
      <span class="badge badge-vector" v-if="source.retrievalSources.includes('vector')">
        🔍 语义检索
      </span>
      <span class="badge badge-keyword" v-if="source.retrievalSources.includes('keyword')">
        🔑 关键词检索
      </span>
    </div>
  </div>
  
  <!-- 如果有匹配的关键词，显示 -->
  <div class="matched-keywords" v-if="source.matchedKeywords">
    <span class="label">匹配关键词：</span>
    <span class="keyword" v-for="kw in source.matchedKeywords" :key="kw">
      {{ kw }}
    </span>
  </div>
  
  <!-- 分数和排名信息（可选） -->
  <div class="scores">
    <span v-if="source.retrievalSources.includes('vector')">
      语义相似度: {{ source.vectorScore }}
      <span v-if="source.vectorRank" class="rank">(排名 #{{ source.vectorRank }})</span>
    </span>
    <span v-if="source.retrievalSources.includes('keyword')">
      关键词得分: {{ source.bm25Score }}
      <span v-if="source.bm25Rank" class="rank">(排名 #{{ source.bm25Rank }})</span>
    </span>
  </div>
  
  <div class="content">{{ source.content }}</div>
</div>
```

### 方案 2：图标展示

```html
<div class="source-item">
  <div class="source-header">
    <span class="file-name">免签政策.md</span>
    
    <!-- 检索方式图标 -->
    <div class="retrieval-icons">
      <i class="icon-vector" 
         v-if="source.retrievalSources.includes('vector')"
         :title="`通过语义检索找到 (排名 #${source.vectorRank || '?'})`">
        🧠 <span v-if="source.vectorRank" class="rank-badge">#{{ source.vectorRank }}</span>
      </i>
      <i class="icon-keyword" 
         v-if="source.retrievalSources.includes('keyword')"
         :title="`匹配关键词: ${source.matchedKeywords?.join(', ')} (排名 #${source.bm25Rank || '?'})`">
        🔑 <span v-if="source.bm25Rank" class="rank-badge">#{{ source.bm25Rank }}</span>
      </i>
    </div>
  </div>
  
  <div class="content">{{ source.content }}</div>
</div>
```

### 方案 3：高亮关键词

```javascript
// 在文档内容中高亮匹配的关键词
function highlightKeywords(content, keywords) {
  if (!keywords || keywords.length === 0) return content;
  
  let highlighted = content;
  keywords.forEach(keyword => {
    const regex = new RegExp(keyword, 'gi');
    highlighted = highlighted.replace(
      regex, 
      `<mark class="keyword-highlight">${keyword}</mark>`
    );
  });
  
  return highlighted;
}
```

```html
<div class="content" v-html="highlightKeywords(source.content, source.matchedKeywords)">
</div>
```

## 🎨 CSS 样式建议

```css
/* 检索来源标签 */
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 12px;
  margin-left: 8px;
}

.badge-vector {
  background-color: #e3f2fd;
  color: #1976d2;
  border: 1px solid #1976d2;
}

.badge-keyword {
  background-color: #fff3e0;
  color: #f57c00;
  border: 1px solid #f57c00;
}

/* 匹配关键词 */
.matched-keywords {
  margin: 8px 0;
  padding: 8px;
  background-color: #fffbf0;
  border-left: 3px solid #ffa726;
}

.matched-keywords .keyword {
  display: inline-block;
  padding: 2px 6px;
  margin: 0 4px;
  background-color: #fff;
  border: 1px solid #ffa726;
  border-radius: 4px;
  font-weight: 500;
  color: #f57c00;
}

/* 关键词高亮 */
.keyword-highlight {
  background-color: #ffeb3b;
  padding: 2px 4px;
  border-radius: 2px;
  font-weight: 500;
}

/* 分数信息 */
.scores {
  font-size: 12px;
  color: #666;
  margin: 4px 0;
}

.scores span {
  margin-right: 12px;
}

.scores .rank {
  color: #999;
  font-size: 11px;
  margin-left: 4px;
}

/* 排名徽章 */
.rank-badge {
  display: inline-block;
  background-color: #f0f0f0;
  color: #666;
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
  margin-left: 4px;
  font-weight: 600;
}
```

## 📝 使用示例

### Vue 3 示例

```vue
<template>
  <div class="sources-list">
    <div 
      v-for="source in sources" 
      :key="source.id"
      class="source-card"
    >
      <!-- 文件名和检索标签 -->
      <div class="source-header">
        <h4>{{ source.fileName }}</h4>
        <div class="badges">
          <span 
            v-if="source.retrievalSources?.includes('vector')"
            class="badge badge-vector"
            :title="`语义相似度: ${source.vectorScore}`"
          >
            🧠 语义检索
          </span>
          <span 
            v-if="source.retrievalSources?.includes('keyword')"
            class="badge badge-keyword"
            :title="`BM25 得分: ${source.bm25Score}`"
          >
            🔑 关键词检索
          </span>
        </div>
      </div>

      <!-- 匹配的关键词 -->
      <div 
        v-if="source.matchedKeywords && source.matchedKeywords.length > 0"
        class="matched-keywords"
      >
        <span class="label">匹配关键词：</span>
        <span 
          v-for="kw in source.matchedKeywords" 
          :key="kw"
          class="keyword"
        >
          {{ kw }}
        </span>
      </div>

      <!-- 分数信息 -->
      <div class="scores">
        <span>融合分数: {{ source.initialScore }}</span>
        <span>重排序分数: {{ source.rerankedScore }}</span>
      </div>

      <!-- 文档内容（高亮关键词） -->
      <div 
        class="content"
        v-html="highlightKeywords(source.content, source.matchedKeywords)"
      >
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue';

const sources = ref([]);

// 高亮关键词
function highlightKeywords(content, keywords) {
  if (!keywords || keywords.length === 0) return content;
  
  let highlighted = content;
  keywords.forEach(keyword => {
    const regex = new RegExp(keyword, 'gi');
    highlighted = highlighted.replace(
      regex, 
      `<mark class="keyword-highlight">${keyword}</mark>`
    );
  });
  
  return highlighted;
}

// 解析 SSE 流
function parseSourceEvent(data) {
  try {
    const source = JSON.parse(data);
    sources.value.push(source);
  } catch (e) {
    console.error('解析 SOURCE 数据失败:', e);
  }
}
</script>
```

### React 示例

```jsx
import React from 'react';

function SourceCard({ source }) {
  // 高亮关键词
  const highlightKeywords = (content, keywords) => {
    if (!keywords || keywords.length === 0) return content;
    
    let highlighted = content;
    keywords.forEach(keyword => {
      const regex = new RegExp(keyword, 'gi');
      highlighted = highlighted.replace(
        regex, 
        `<mark class="keyword-highlight">${keyword}</mark>`
      );
    });
    
    return { __html: highlighted };
  };

  return (
    <div className="source-card">
      {/* 文件名和检索标签 */}
      <div className="source-header">
        <h4>{source.fileName}</h4>
        <div className="badges">
          {source.retrievalSources?.includes('vector') && (
            <span 
              className="badge badge-vector"
              title={`语义相似度: ${source.vectorScore}`}
            >
              🧠 语义检索
            </span>
          )}
          {source.retrievalSources?.includes('keyword') && (
            <span 
              className="badge badge-keyword"
              title={`BM25 得分: ${source.bm25Score}`}
            >
              🔑 关键词检索
            </span>
          )}
        </div>
      </div>

      {/* 匹配的关键词 */}
      {source.matchedKeywords && source.matchedKeywords.length > 0 && (
        <div className="matched-keywords">
          <span className="label">匹配关键词：</span>
          {source.matchedKeywords.map(kw => (
            <span key={kw} className="keyword">{kw}</span>
          ))}
        </div>
      )}

      {/* 文档内容 */}
      <div 
        className="content"
        dangerouslySetInnerHTML={highlightKeywords(source.content, source.matchedKeywords)}
      />
    </div>
  );
}

export default SourceCard;
```

## ⚠️ 注意事项

1. **matchedKeywords 可能为空**
   - 即使 `retrievalSources` 包含 `"keyword"`，`matchedKeywords` 也可能不存在
   - 原因：查询关键词可能都是单字符（被过滤掉了）

2. **关键词高亮的性能**
   - 如果文档很长，正则替换可能较慢
   - 建议只高亮前 500 字符，或使用虚拟滚动

3. **XSS 安全**
   - 使用 `v-html` 或 `dangerouslySetInnerHTML` 时要注意安全
   - 确保 `content` 已经过后端清理

4. **中文分词**
   - 关键词是通过 jieba 分词得到的
   - 可能包含一些意外的分词结果（如"的"、"了"等，但已过滤单字符）

## 🔄 后续优化建议

1. **关键词权重**
   - 可以根据 TF-IDF 权重给关键词排序
   - 只显示最重要的 3-5 个关键词

2. **上下文片段**
   - 提取包含关键词的上下文片段
   - 类似搜索引擎的摘要

3. **检索解释**
   - 解释为什么这个文档被检索到
   - 例如："该文档与您的查询在语义上高度相关，并且包含关键词'泰国'、'免签'"

## 📞 技术支持

如有问题，请查看：
- 后端代码：`core/retriever.py` - BM25 关键词提取
- 后端代码：`api/knowledge_handler.py` - 数据格式化
- 配置文件：`config/settings.py` - RRF 权重配置
