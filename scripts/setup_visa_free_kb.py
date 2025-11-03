#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
免签知识库初始化脚本
创建目录结构并复制免签相关文档
"""
import os
import sys
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Settings
from utils.logger import logger


def setup_visa_free_kb():
    """初始化免签知识库目录和文档"""
    
    logger.info("=" * 60)
    logger.info("免签知识库初始化")
    logger.info("=" * 60)
    
    # 1. 创建免签知识库目录
    visa_kb_dir = Settings.VISA_FREE_KB_DIR
    visa_storage_dir = Settings.VISA_FREE_STORAGE_PATH
    
    logger.info(f"\n[步骤1] 创建目录结构")
    logger.info(f"免签知识库目录: {visa_kb_dir}")
    logger.info(f"免签索引存储目录: {visa_storage_dir}")
    
    try:
        os.makedirs(visa_kb_dir, exist_ok=True)
        os.makedirs(visa_storage_dir, exist_ok=True)
        logger.info("✓ 目录创建成功")
    except Exception as e:
        logger.error(f"✗ 目录创建失败: {e}")
        return False
    
    # 2. 检查是否有免签文档
    source_doc = os.path.join(Settings.BASE_DIR, "中国与外国互免签证协定一览表.txt")
    
    logger.info(f"\n[步骤2] 复制免签文档")
    logger.info(f"源文档: {source_doc}")
    
    if os.path.exists(source_doc):
        target_doc = os.path.join(visa_kb_dir, "中国与外国互免签证协定一览表.txt")
        try:
            shutil.copy2(source_doc, target_doc)
            logger.info(f"✓ 文档复制成功: {target_doc}")
        except Exception as e:
            logger.error(f"✗ 文档复制失败: {e}")
            return False
    else:
        logger.warning(f"✗ 源文档不存在: {source_doc}")
        logger.info("请手动将免签相关文档放入免签知识库目录")
    
    # 3. 检查目录内容
    logger.info(f"\n[步骤3] 检查目录内容")
    try:
        files = os.listdir(visa_kb_dir)
        logger.info(f"免签知识库文件数: {len(files)}")
        for f in files:
            file_path = os.path.join(visa_kb_dir, f)
            file_size = os.path.getsize(file_path)
            logger.info(f"  - {f} ({file_size} bytes)")
    except Exception as e:
        logger.error(f"✗ 读取目录失败: {e}")
        return False
    
    # 4. 创建 README
    readme_path = os.path.join(visa_kb_dir, "README.md")
    readme_content = """# 免签知识库

## 说明
此目录用于存放免签相关的知识文档。

## 支持的文档格式
- .txt (纯文本)
- .md (Markdown)
- .pdf (PDF文档)
- .docx (Word文档)

## 使用方法
1. 将免签相关文档放入此目录
2. 启动应用时会自动构建索引
3. 通过环境变量 `ENABLE_VISA_FREE_FEATURE=true` 启用功能

## 注意事项
- 文档应包含国家/地区名称、免签政策等信息
- 建议使用结构化的文档格式
- 文档更新后需要重启应用以重建索引
"""
    
    try:
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        logger.info(f"\n✓ README 创建成功: {readme_path}")
    except Exception as e:
        logger.warning(f"✗ README 创建失败: {e}")
    
    logger.info("\n" + "=" * 60)
    logger.info("免签知识库初始化完成")
    logger.info("=" * 60)
    logger.info("\n下一步:")
    logger.info("1. 确认免签文档已放入目录")
    logger.info("2. 设置环境变量: export ENABLE_VISA_FREE_FEATURE=true")
    logger.info("3. 启动应用构建索引")
    
    return True


if __name__ == "__main__":
    success = setup_visa_free_kb()
    sys.exit(0 if success else 1)
