#!/bin/bash

echo "========================================"
echo "BM25 修复状态检查脚本"
echo "========================================"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo ""
echo "=== 1. 检查代码是否已更新 ==="
CODE_FILE="/opt/rag_final_project/code_here/llm_pro/services/knowledge_service.py"

if [ -f "$CODE_FILE" ]; then
    TEXTNODE_COUNT=$(grep -c "TextNode" "$CODE_FILE")
    FIX_COMMENT=$(grep -c "⭐ 关键修复：将 Document 转换为 TextNode" "$CODE_FILE")
    
    echo "TextNode 出现次数: $TEXTNODE_COUNT"
    echo "修复注释存在: $FIX_COMMENT"
    
    if [ $FIX_COMMENT -gt 0 ]; then
        echo -e "${GREEN}✓ 代码已更新${NC}"
        
        # 显示修复代码片段
        echo ""
        echo "修复代码片段："
        grep -A 8 "⭐ 关键修复：将 Document 转换为 TextNode" "$CODE_FILE" | head -10
    else
        echo -e "${RED}✗ 代码未更新！需要重新上传代码${NC}"
    fi
else
    echo -e "${RED}✗ 文件不存在: $CODE_FILE${NC}"
fi

echo ""
echo "=== 2. 检查服务是否在运行 ==="
APP_PROCESS=$(ps aux | grep "python.*app.py" | grep -v grep)

if [ -n "$APP_PROCESS" ]; then
    echo -e "${GREEN}✓ 服务正在运行${NC}"
    echo "$APP_PROCESS"
else
    echo -e "${RED}✗ 服务未运行${NC}"
fi

echo ""
echo "=== 3. 检查哈希文件状态 ==="
HASH_FILES=(
    "/opt/rag_final_project/storage/kb_hashes.json"
    "/opt/rag_final_project/visa_free_storage/visa_free_kb_hashes.json"
    "/opt/rag_final_project/airline_storage/airline_kb_hashes.json"
)

for hash_file in "${HASH_FILES[@]}"; do
    if [ -f "$hash_file" ]; then
        echo -e "${YELLOW}⚠ 存在: $hash_file${NC}"
        echo "   修改时间: $(stat -c %y "$hash_file" 2>/dev/null || stat -f "%Sm" "$hash_file")"
    else
        echo -e "${GREEN}✓ 不存在（正常）: $hash_file${NC}"
    fi
done

echo ""
echo "=== 4. 检查 Python 缓存 ==="
CACHE_COUNT=$(find /opt/rag_final_project/code_here/llm_pro -type d -name "__pycache__" 2>/dev/null | wc -l)
PYC_COUNT=$(find /opt/rag_final_project/code_here/llm_pro -name "*.pyc" 2>/dev/null | wc -l)

echo "__pycache__ 目录数: $CACHE_COUNT"
echo ".pyc 文件数: $PYC_COUNT"

if [ $CACHE_COUNT -gt 0 ] || [ $PYC_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠ 存在缓存文件，建议清理${NC}"
else
    echo -e "${GREEN}✓ 无缓存文件${NC}"
fi

echo ""
echo "=== 5. 检查 Qdrant 数据 ==="
echo "正在检查 Qdrant 中的节点内容..."

# 创建临时 Python 脚本检查 Qdrant
cat > /tmp/check_qdrant.py << 'EOF'
from qdrant_client import QdrantClient
import sys
import json
sys.path.insert(0, '/opt/rag_final_project/code_here/llm_pro')
from config import Settings

try:
    client = QdrantClient(host=Settings.QDRANT_HOST, port=Settings.QDRANT_PORT)
    result = client.scroll(
        collection_name=Settings.QDRANT_COLLECTION,
        limit=1,
        with_payload=True,
        with_vectors=False
    )
    
    if result[0]:
        point = result[0][0]
        node_content = point.payload.get("_node_content", "")
        text_field = point.payload.get("text", "")
        
        print(f"Payload 字段: {list(point.payload.keys())}")
        print()
        
        # 检查 _node_content
        print("=== _node_content 字段 ===")
        if node_content:
            if node_content.startswith('{"id_"'):
                print("❌ 格式: JSON（异常）")
                print(f"预览: {node_content[:150]}...")
                
                # 尝试解析 JSON，看看里面有没有 text 字段
                try:
                    parsed = json.loads(node_content)
                    if "text" in parsed:
                        print(f"\n⚠ JSON 内部的 text 字段: {parsed['text'][:100]}...")
                except:
                    pass
            else:
                print("✓ 格式: 纯文本（正常）")
                print(f"预览: {node_content[:150]}...")
        else:
            print("✗ 字段为空")
        
        print()
        
        # 检查 text 字段
        print("=== text 字段 ===")
        if text_field:
            print(f"✓ 存在")
            print(f"预览: {text_field[:150]}...")
        else:
            print("✗ 不存在")
        
        print()
        
        # 判断最终状态
        if node_content.startswith('{"id_"'):
            if text_field:
                print("⚠ 结论: _node_content 是 JSON，但 text 字段存在")
                print("   这就是为什么日志显示正常（代码从 text 字段读取）")
                print("   但 Qdrant 数据仍然异常，需要重建索引")
                sys.exit(1)
            else:
                print("❌ 结论: _node_content 是 JSON，且 text 字段不存在")
                print("   数据完全异常，必须重建索引")
                sys.exit(1)
        else:
            print("✓ 结论: 数据正常")
            sys.exit(0)
    else:
        print("⚠ 警告：集合为空")
        sys.exit(2)
except Exception as e:
    print(f"✗ 错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(3)
EOF

python /tmp/check_qdrant.py
QDRANT_STATUS=$?

if [ $QDRANT_STATUS -eq 0 ]; then
    echo -e "${GREEN}✓ Qdrant 数据正常${NC}"
elif [ $QDRANT_STATUS -eq 1 ]; then
    echo -e "${RED}✗ Qdrant 数据异常！需要重建索引${NC}"
elif [ $QDRANT_STATUS -eq 2 ]; then
    echo -e "${YELLOW}⚠ Qdrant 集合为空，需要构建索引${NC}"
else
    echo -e "${RED}✗ 无法连接 Qdrant${NC}"
fi

rm -f /tmp/check_qdrant.py

echo ""
echo "========================================"
echo "检查完成"
echo "========================================"

echo ""
echo "=== 建议操作 ==="

# 根据检查结果给出建议
if [ $FIX_COMMENT -eq 0 ]; then
    echo -e "${RED}1. 代码未更新，请重新上传 knowledge_service.py${NC}"
fi

if [ $CACHE_COUNT -gt 0 ] || [ $PYC_COUNT -gt 0 ]; then
    echo -e "${YELLOW}2. 清理 Python 缓存:${NC}"
    echo "   find /opt/rag_final_project/code_here/llm_pro -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null"
    echo "   find /opt/rag_final_project/code_here/llm_pro -name '*.pyc' -delete"
fi

if [ $QDRANT_STATUS -eq 1 ] || [ $QDRANT_STATUS -eq 2 ]; then
    echo -e "${YELLOW}3. 删除哈希文件并重启服务:${NC}"
    echo "   rm -f /opt/rag_final_project/storage/kb_hashes.json"
    echo "   rm -f /opt/rag_final_project/visa_free_storage/visa_free_kb_hashes.json"
    echo "   rm -f /opt/rag_final_project/airline_storage/airline_kb_hashes.json"
    echo "   pkill -f app.py"
    echo "   cd /opt/rag_final_project/code_here/llm_pro && nohup python app.py > app.log 2>&1 &"
fi

if [ $FIX_COMMENT -gt 0 ] && [ $QDRANT_STATUS -eq 0 ]; then
    echo -e "${GREEN}✓ 所有检查通过，系统正常！${NC}"
fi
