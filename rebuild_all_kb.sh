#!/bin/bash

echo "========================================"
echo "清理所有知识库索引，强制重建"
echo "========================================"

echo ""
echo "删除通用知识库哈希文件..."
if rm -f /opt/rag_final_project/storage/kb_hashes.json 2>/dev/null; then
    echo "[成功] 通用知识库哈希文件已删除"
else
    echo "[跳过] 通用知识库哈希文件不存在"
fi

echo ""
echo "删除免签知识库哈希文件..."
if rm -f /opt/rag_final_project/visa_free_storage/visa_free_kb_hashes.json 2>/dev/null; then
    echo "[成功] 免签知识库哈希文件已删除"
else
    echo "[跳过] 免签知识库哈希文件不存在"
fi

echo ""
echo "删除航司知识库哈希文件..."
if rm -f /opt/rag_final_project/airline_storage/airline_kb_hashes.json 2>/dev/null; then
    echo "[成功] 航司知识库哈希文件已删除"
else
    echo "[跳过] 航司知识库哈希文件不存在"
fi

echo ""
echo "========================================"
echo "清理完成！现在可以重启服务"
echo "服务启动时会自动重建所有知识库"
echo "========================================"
