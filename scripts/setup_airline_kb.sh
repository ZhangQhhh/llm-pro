#!/bin/bash
# 航司知识库快速配置脚本

set -e

echo "=========================================="
echo "  航司知识库配置脚本"
echo "=========================================="
echo ""

# 配置路径
AIRLINE_KB_DIR="/opt/rag_final_project/airline_knowledge_base"
AIRLINE_STORAGE_PATH="/opt/rag_final_project/airline_storage"
SOURCE_FILE="民航办事处常驻人员和机组人员签证协议一览表.txt"

# 步骤1: 创建目录
echo "[1/5] 创建航司知识库目录..."
mkdir -p "$AIRLINE_KB_DIR"
mkdir -p "$AIRLINE_STORAGE_PATH"
echo "✓ 目录创建完成"
echo ""

# 步骤2: 复制文件
echo "[2/5] 复制航司协议文件..."
if [ -f "$SOURCE_FILE" ]; then
    cp "$SOURCE_FILE" "$AIRLINE_KB_DIR/"
    echo "✓ 文件复制完成: $SOURCE_FILE"
else
    echo "⚠ 警告: 未找到源文件 $SOURCE_FILE"
    echo "   请手动将文件复制到: $AIRLINE_KB_DIR/"
fi
echo ""

# 步骤3: 设置环境变量
echo "[3/5] 配置环境变量..."
cat >> ~/.bashrc << EOF

# 航司知识库配置 ($(date +%Y-%m-%d))
export ENABLE_AIRLINE_FEATURE=true
export AIRLINE_KB_DIR="$AIRLINE_KB_DIR"
export AIRLINE_STORAGE_PATH="$AIRLINE_STORAGE_PATH"
EOF

echo "✓ 环境变量已添加到 ~/.bashrc"
echo "  请运行: source ~/.bashrc"
echo ""

# 步骤4: 构建索引提示
echo "[4/5] 构建向量索引..."
echo "⚠ 注意: 需要手动运行索引构建脚本"
echo ""
echo "  方法1: 使用专用脚本（推荐）"
echo "    python scripts/build_airline_index.py"
echo ""
echo "  方法2: 使用通用构建脚本"
echo "    python build_index.py --kb-dir $AIRLINE_KB_DIR \\"
echo "                          --storage-path $AIRLINE_STORAGE_PATH \\"
echo "                          --collection airline_kb"
echo ""

# 步骤5: 启用意图分类器
echo "[5/5] 启用意图分类器..."
if grep -q "ENABLE_INTENT_CLASSIFIER=true" ~/.bashrc; then
    echo "✓ 意图分类器已启用"
else
    echo "export ENABLE_INTENT_CLASSIFIER=true" >> ~/.bashrc
    echo "✓ 已添加意图分类器配置"
fi
echo ""

# 完成提示
echo "=========================================="
echo "  配置完成！"
echo "=========================================="
echo ""
echo "后续步骤："
echo "1. 重新加载环境变量: source ~/.bashrc"
echo "2. 构建向量索引（见上方提示）"
echo "3. 重启服务: systemctl restart llm_pro"
echo "4. 测试功能:"
echo "   curl -X POST http://localhost:5000/api/knowledge \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"question\": \"执行中美航班的机组人员需要签证吗？\"}'"
echo ""
echo "查看文档: docs/AIRLINE_KB_README.md"
echo ""
