#!/bin/bash

echo "========================================"
echo "BM25 修复 - 完整修复和重建流程"
echo "========================================"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目路径
PROJECT_DIR="/opt/rag_final_project/code_here/llm_pro"
SERVICES_DIR="$PROJECT_DIR/services"
CORE_DIR="$PROJECT_DIR/core"

echo ""
echo -e "${BLUE}=== 步骤 1/6: 检查代码是否已更新 ===${NC}"
echo ""

# 检查 knowledge_service.py
echo "检查 services/knowledge_service.py ..."
if grep -q "⭐ 关键修复：将 Document 转换为 TextNode" "$SERVICES_DIR/knowledge_service.py"; then
    echo -e "${GREEN}✓ knowledge_service.py 已包含修复代码${NC}"
else
    echo -e "${RED}✗ knowledge_service.py 缺少修复代码！${NC}"
    echo -e "${YELLOW}请确保已上传最新的 knowledge_service.py 文件${NC}"
    exit 1
fi

# 检查 retriever.py
echo "检查 core/retriever.py ..."
if grep -q "验证内容是否有效（不是JSON格式的元数据）" "$CORE_DIR/retriever.py"; then
    echo -e "${GREEN}✓ retriever.py 已包含修复代码${NC}"
else
    echo -e "${YELLOW}⚠ retriever.py 可能缺少最新修复${NC}"
fi

echo ""
echo -e "${BLUE}=== 步骤 2/6: 停止服务 ===${NC}"
echo ""

# 查找并停止 app.py 进程
APP_PID=$(ps aux | grep "python.*app.py" | grep -v grep | awk '{print $2}')

if [ -n "$APP_PID" ]; then
    echo "发现运行中的服务 (PID: $APP_PID)"
    echo "正在停止服务..."
    kill $APP_PID
    sleep 2
    
    # 确认是否已停止
    if ps -p $APP_PID > /dev/null 2>&1; then
        echo -e "${YELLOW}进程未响应，强制终止...${NC}"
        kill -9 $APP_PID
        sleep 1
    fi
    
    echo -e "${GREEN}✓ 服务已停止${NC}"
else
    echo -e "${YELLOW}未发现运行中的服务${NC}"
fi

echo ""
echo -e "${BLUE}=== 步骤 3/6: 清理 Python 缓存 ===${NC}"
echo ""

echo "清理 __pycache__ 目录..."
CACHE_COUNT=$(find "$PROJECT_DIR" -type d -name "__pycache__" 2>/dev/null | wc -l)
find "$PROJECT_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
echo -e "${GREEN}✓ 已清理 $CACHE_COUNT 个缓存目录${NC}"

echo "清理 .pyc 文件..."
PYC_COUNT=$(find "$PROJECT_DIR" -name "*.pyc" 2>/dev/null | wc -l)
find "$PROJECT_DIR" -name "*.pyc" -delete 2>/dev/null
echo -e "${GREEN}✓ 已清理 $PYC_COUNT 个 .pyc 文件${NC}"

echo ""
echo -e "${BLUE}=== 步骤 4/6: 删除知识库哈希文件 ===${NC}"
echo ""

# 删除通用知识库哈希
echo "删除通用知识库哈希文件..."
if rm -f /opt/rag_final_project/storage/kb_hashes.json 2>/dev/null; then
    echo -e "${GREEN}✓ 通用知识库哈希文件已删除${NC}"
else
    echo -e "${YELLOW}⚠ 通用知识库哈希文件不存在（可能已删除）${NC}"
fi

# 删除免签知识库哈希
echo "删除免签知识库哈希文件..."
if rm -f /opt/rag_final_project/visa_free_storage/visa_free_kb_hashes.json 2>/dev/null; then
    echo -e "${GREEN}✓ 免签知识库哈希文件已删除${NC}"
else
    echo -e "${YELLOW}⚠ 免签知识库哈希文件不存在（可能已删除）${NC}"
fi

# 删除航司知识库哈希
echo "删除航司知识库哈希文件..."
if rm -f /opt/rag_final_project/airline_storage/airline_kb_hashes.json 2>/dev/null; then
    echo -e "${GREEN}✓ 航司知识库哈希文件已删除${NC}"
else
    echo -e "${YELLOW}⚠ 航司知识库哈希文件不存在（可能已删除）${NC}"
fi

echo ""
echo -e "${BLUE}=== 步骤 5/6: 启动服务 ===${NC}"
echo ""

cd "$PROJECT_DIR"
echo "当前目录: $(pwd)"
echo "启动命令: nohup python app.py > app.log 2>&1 &"
echo ""

nohup python app.py > app.log 2>&1 &
NEW_PID=$!

sleep 3

# 检查进程是否启动成功
if ps -p $NEW_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 服务启动成功 (PID: $NEW_PID)${NC}"
else
    echo -e "${RED}✗ 服务启动失败！${NC}"
    echo "查看错误日志:"
    tail -20 app.log
    exit 1
fi

echo ""
echo -e "${BLUE}=== 步骤 6/6: 监控启动日志 ===${NC}"
echo ""
echo "正在监控启动日志（30秒）..."
echo "按 Ctrl+C 可以提前退出监控"
echo ""
echo "----------------------------------------"

# 监控日志 30 秒
timeout 30 tail -f app.log &
TAIL_PID=$!

sleep 30
kill $TAIL_PID 2>/dev/null

echo ""
echo "----------------------------------------"
echo ""
echo -e "${GREEN}========================================"
echo "修复流程完成！"
echo "========================================${NC}"
echo ""
echo "📋 验证清单："
echo ""
echo "1. 检查日志中是否有以下关键信息："
echo "   ✓ '已将 XXX 个 Document 转换为 TextNode'"
echo "   ✓ 'BM25检索器初始化: ... 跳过0个异常节点'"
echo ""
echo "2. 如果看到上述信息，说明修复成功！"
echo ""
echo "3. 如果没有看到，请运行以下命令查看完整日志："
echo "   tail -100 $PROJECT_DIR/app.log"
echo ""
echo "4. 验证 Qdrant 数据是否正确："
echo "   cd $PROJECT_DIR"
echo "   python debug_qdrant_detailed.py"
echo ""
echo "----------------------------------------"
echo ""
echo "📝 日志文件位置: $PROJECT_DIR/app.log"
echo "🔍 实时查看日志: tail -f $PROJECT_DIR/app.log"
echo ""
