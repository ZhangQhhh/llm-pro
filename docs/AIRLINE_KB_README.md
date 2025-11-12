# 航司知识库功能说明

## 概述

航司知识库是一个独立的知识库模块，专门用于存储和检索**民航办事处常驻人员和机组人员签证协议**相关的内容。当用户询问与航司、机组人员、民航协议相关的问题时，系统会自动调用该知识库。

## 核心特性

### 1. 插件式设计
- 通过环境变量 `ENABLE_AIRLINE_FEATURE` 一键启用/关闭
- 默认关闭，不影响现有系统
- 与免签库、通用库完全独立，互不干扰

### 2. 智能意图分类
意图分类器已扩展支持三类问题：
- **airline**: 航司相关问题（机组人员、民航协议等）
- **visa_free**: 免签相关问题（普通旅客签证政策）
- **general**: 通用问题（边检流程、证件办理等）

### 3. 灵活检索策略
- **单库检索**: 只查航司库
- **组合检索**: 航司库 + 通用库 / 航司库 + 免签库
- **自适应合并**: 根据得分动态调整各库的比例

## 配置方式

### 环境变量配置

```bash
# 启用航司知识库功能
export ENABLE_AIRLINE_FEATURE=true

# 航司知识库路径（可选，有默认值）
export AIRLINE_KB_DIR="/opt/rag_final_project/airline_knowledge_base"
export AIRLINE_STORAGE_PATH="/opt/rag_final_project/airline_storage"
```

### 配置参数说明

在 `config/settings.py` 中：

```python
# 航司功能开关
ENABLE_AIRLINE_FEATURE = os.getenv("ENABLE_AIRLINE_FEATURE", "false").lower() == "true"

# 航司知识库路径
AIRLINE_KB_DIR = "/opt/rag_final_project/airline_knowledge_base"
AIRLINE_STORAGE_PATH = "/opt/rag_final_project/airline_storage"
AIRLINE_COLLECTION = "airline_kb"  # Qdrant collection名称

# 航司检索参数
AIRLINE_RETRIEVAL_TOP_K = 30        # 初始检索数量
AIRLINE_RETRIEVAL_TOP_K_BM25 = 30   # BM25检索数量
AIRLINE_RERANK_TOP_N = 15           # 重排序后返回数量
AIRLINE_RETRIEVAL_COUNT = 5         # 多库检索时航司库取5条
```

## 知识库内容

航司知识库主要包含：

### 数据来源
- **民航办事处常驻人员和机组人员签证协议一览表.txt**
  - 中国与各国的民航协议
  - 机组人员签证/免签规定
  - 民航办事处常驻人员签证要求
  - 包机、专机机组人员入境规定

### 覆盖国家（部分）
- 亚洲：日本、韩国、新加坡、泰国、马来西亚、印度尼西亚、越南、缅甸等
- 欧洲：英国、法国、德国、意大利、西班牙、荷兰、瑞士、俄罗斯等
- 美洲：美国、加拿大
- 大洋洲：澳大利亚、新西兰
- 非洲：埃及、肯尼亚、埃塞俄比亚等
- 中东：阿联酋、卡塔尔、阿曼、以色列等
- 特别行政区：香港、澳门

## 意图分类示例

### 航司相关问题（会调用航司库）
✅ "执行中美航班的机组人员需要签证吗？"
✅ "民航办事处常驻人员如何办理签证？"
✅ "飞往日本的机组人员入境要求是什么？"
✅ "包机机组人员免签吗？"
✅ "中国与澳大利亚的民航协议内容是什么？"

### 免签相关问题（会调用免签库）
✅ "去泰国旅游需要签证吗？"
✅ "中国护照可以免签去哪些国家？"
✅ "过境免签政策是什么？"

### 通用问题（会调用通用库）
✅ "如何办理护照？"
✅ "边检的职责是什么？"
✅ "港澳通行证如何续签？"

## 工作流程

```
用户提问
    ↓
意图分类器判断
    ↓
┌─────────────┬──────────────┬──────────────┐
│  airline    │  visa_free   │   general    │
│  航司相关   │  免签相关    │   通用问题   │
└─────────────┴──────────────┴──────────────┘
    ↓              ↓               ↓
航司库检索    免签库检索      通用库检索
    ↓              ↓               ↓
  重排序         重排序           重排序
    ↓              ↓               ↓
  生成回答       生成回答         生成回答
```

## 检索策略

### 航司问题检索（airline）
当问题被分类为航司相关时，采用**航司库 + 通用库保底**策略：

**核心原则**: 即使是航司问题，也要保证通用库至少返回5条内容

**检索策略**（15条总计）：
1. **前5条**: 航司库最高分（专业航司协议内容）
2. **中5条**: 通用库最高分（保底，确保基础知识覆盖）
3. **后5条**: 从两库剩余文档中综合比较（灵活分配）

**优势**：
- ✅ 航司专业内容优先展示
- ✅ 通用知识库保底，避免信息缺失
- ✅ 综合比较确保最相关内容不遗漏
- ✅ 最终按得分排序，保证质量

### 组合检索（未来扩展）
可以支持：
- `airline_visa_free`: 航司库 + 免签库
- `airline_general_visa`: 三库同时检索

## 部署步骤

### 1. 准备知识库文件
```bash
# 创建航司知识库目录
mkdir -p /opt/rag_final_project/airline_knowledge_base

# 复制航司协议文件
cp "民航办事处常驻人员和机组人员签证协议一览表.txt" \
   /opt/rag_final_project/airline_knowledge_base/
```

### 2. 构建向量索引
```bash
# 运行索引构建脚本（需要先创建该脚本）
python scripts/build_airline_index.py
```

### 3. 启用功能
```bash
# 设置环境变量
export ENABLE_AIRLINE_FEATURE=true
export ENABLE_INTENT_CLASSIFIER=true  # 必须同时启用意图分类器

# 重启服务
systemctl restart llm_pro
```

### 4. 验证功能
```bash
# 测试航司问题
curl -X POST http://localhost:5000/api/knowledge \
  -H "Content-Type: application/json" \
  -d '{"question": "执行中美航班的机组人员需要签证吗？"}'
```

## 日志示例

启用航司库后，日志会显示：

```
[INFO] 多库检索器初始化完成 | 策略: adaptive | 已启用: 通用库, 免签库, 航司库
[INFO] ✓ 知识库功能已启用: 多库检索+意图分类, 免签库, 航司库
[INFO] [意图分类] 开始分类问题: 执行中美航班的机组人员需要签证吗？
[INFO] [意图分类] ✓ 判定结果: airline
[INFO] [智能路由] 意图分类结果: airline
[INFO] [智能路由] 使用航司知识库
[INFO] [航司检索] 查询: 执行中美航班的机组人员需要签证吗？
[INFO] [航司检索] 返回 15 条结果
```

## 注意事项

### 1. 依赖关系
- 航司功能依赖意图分类器，必须同时启用 `ENABLE_INTENT_CLASSIFIER=true`
- 需要先构建航司库的向量索引

### 2. 文件格式
- 航司协议文件使用 `|||` 作为切分标记
- 每条协议独立成段，便于精确检索

### 3. 性能考虑
- 航司库文件较小（113条协议），检索速度快
- 意图分类增加约100-200ms延迟，但提高准确性

### 4. 扩展性
- 可以添加更多航司相关文件到知识库目录
- 支持定期更新协议内容，重新构建索引即可

## 故障排查

### 问题1: 航司问题未调用航司库
**原因**: 意图分类器未正确识别
**解决**: 
- 检查提示词是否包含"机组"、"民航"等关键词
- 查看日志中的意图分类结果
- 调整 `prompts.py` 中的航司特征描述

### 问题2: 检索结果为空
**原因**: 航司库索引未构建或路径错误
**解决**:
- 检查 `AIRLINE_KB_DIR` 路径是否正确
- 确认向量索引已构建
- 查看 Qdrant 中是否存在 `airline_kb` collection

### 问题3: 功能未生效
**原因**: 环境变量未设置或服务未重启
**解决**:
```bash
# 检查环境变量
echo $ENABLE_AIRLINE_FEATURE
echo $ENABLE_INTENT_CLASSIFIER

# 重启服务
systemctl restart llm_pro
```

## 未来优化方向

1. **混合检索策略**: 支持航司+免签+通用三库同时检索
2. **细粒度分类**: 区分"常驻人员"和"机组人员"的不同需求
3. **国家级索引**: 按国家建立子索引，提高检索精度
4. **协议更新提醒**: 监控协议变更，自动更新知识库

## 相关文档

- [意图分类器说明](./INTENT_CLASSIFIER_README.md)
- [多库检索策略](./MULTI_KB_RETRIEVAL_STRATEGY.md)
- [免签知识库说明](./VISA_FREE_KB_README.md)

## 技术支持

如有问题，请查看：
- 日志文件: `/opt/rag_final_project/qa_logs/`
- 配置文件: `config/settings.py`
- 提示词文件: `prompts.py`
