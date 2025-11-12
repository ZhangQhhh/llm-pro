# 知识库缓存文件路径总结

## 📁 三个知识库的缓存文件位置

### 1. 通用知识库 (General Knowledge Base)
- **哈希文件**: `/opt/rag_final_project/storage/kb_hashes.json`
- **存储目录**: `/opt/rag_final_project/storage/`
- **知识库目录**: `/opt/rag_final_project/knowledge_base/`
- **Qdrant Collection**: `knowledge_base`

### 2. 免签知识库 (Visa-Free Knowledge Base)
- **哈希文件**: `/opt/rag_final_project/visa_free_storage/visa_free_kb_hashes.json`
- **存储目录**: `/opt/rag_final_project/visa_free_storage/`
- **知识库目录**: `/opt/rag_final_project/visa_free_knowledge_base/`
- **Qdrant Collection**: `visa_free_kb`

### 3. 航司知识库 (Airline Knowledge Base)
- **哈希文件**: `/opt/rag_final_project/airline_storage/airline_kb_hashes.json`
- **存储目录**: `/opt/rag_final_project/airline_storage/`
- **知识库目录**: `/opt/rag_final_project/airline_knowledge_base/`
- **Qdrant Collection**: `airline_kb`

---

## 🔧 快速清理命令

### 删除所有哈希文件（强制重建所有知识库）
```bash
rm -f /opt/rag_final_project/storage/kb_hashes.json
rm -f /opt/rag_final_project/visa_free_storage/visa_free_kb_hashes.json
rm -f /opt/rag_final_project/airline_storage/airline_kb_hashes.json
```

### 删除单个知识库的哈希文件
```bash
# 只重建通用知识库
rm -f /opt/rag_final_project/storage/kb_hashes.json

# 只重建免签知识库
rm -f /opt/rag_final_project/visa_free_storage/visa_free_kb_hashes.json

# 只重建航司知识库
rm -f /opt/rag_final_project/airline_storage/airline_kb_hashes.json
```

---

## 📊 配置文件位置

所有路径配置在：`config/settings.py`

```python
# 通用知识库
STORAGE_PATH = "/opt/rag_final_project/storage"
KNOWLEDGE_BASE_DIR = "/opt/rag_final_project/knowledge_base"
QDRANT_COLLECTION = "knowledge_base"

# 免签知识库
VISA_FREE_STORAGE_PATH = "/opt/rag_final_project/visa_free_storage"
VISA_FREE_KB_DIR = "/opt/rag_final_project/visa_free_knowledge_base"
VISA_FREE_COLLECTION = "visa_free_kb"

# 航司知识库
AIRLINE_STORAGE_PATH = "/opt/rag_final_project/airline_storage"
AIRLINE_KB_DIR = "/opt/rag_final_project/airline_knowledge_base"
AIRLINE_COLLECTION = "airline_kb"
```

---

## ⚠️ 注意事项

1. **哈希文件的作用**：
   - 记录知识库文件的 MD5 哈希值
   - 用于检测文件是否变化
   - 如果文件未变化，直接从 Qdrant 加载索引
   - 如果文件变化或哈希文件不存在，重建索引

2. **删除哈希文件的影响**：
   - 服务启动时会检测到哈希文件不存在
   - 自动触发索引重建流程
   - 重建完成后会生成新的哈希文件

3. **存储目录的内容**：
   - 主要存储哈希文件
   - 可能还有其他缓存文件（取决于 LlamaIndex 的实现）

---

## 🚀 重建索引的完整流程

```bash
# 1. 删除哈希文件
rm -f /opt/rag_final_project/storage/kb_hashes.json
rm -f /opt/rag_final_project/visa_free_storage/visa_free_kb_hashes.json
rm -f /opt/rag_final_project/airline_storage/airline_kb_hashes.json

# 2. 清理 Python 缓存
find /opt/rag_final_project/code_here/llm_pro -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find /opt/rag_final_project/code_here/llm_pro -name "*.pyc" -delete

# 3. 重启服务
pkill -f app.py
cd /opt/rag_final_project/code_here/llm_pro
nohup python app.py > app.log 2>&1 &

# 4. 查看日志
tail -f app.log
```

---

## ✅ 验证重建成功

启动日志中应该看到：

```
[通用知识库] 检测到文件变化，重建索引...
已将 XXX 个 Document 转换为 TextNode
BM25检索器初始化: 总节点XXX个, 有效节点XXX个, 跳过0个异常节点

[免签知识库] 检测到文件变化，重建索引...
已将 XXX 个 Document 转换为 TextNode
BM25检索器初始化: 总节点XXX个, 有效节点XXX个, 跳过0个异常节点

[航司知识库] 检测到文件变化，重建索引...
已将 XXX 个 Document 转换为 TextNode
BM25检索器初始化: 总节点XXX个, 有效节点XXX个, 跳过0个异常节点
```

关键指标：
- ✅ "已将 XXX 个 Document 转换为 TextNode" - 说明修复代码生效
- ✅ "跳过0个异常节点" - 说明所有节点都是有效的
