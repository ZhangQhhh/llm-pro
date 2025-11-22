# -*- coding: utf-8 -*-
"""
快速检查特殊规定路径配置
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import Settings

print("=" * 80)
print("特殊规定路径配置检查")
print("=" * 80)

print(f"\n当前配置的特殊规定目录: {Settings.SPECIAL_RULES_DIR}")
print(f"目录是否存在: {os.path.exists(Settings.SPECIAL_RULES_DIR)}")

if not os.path.exists(Settings.SPECIAL_RULES_DIR):
    print("\n❌ 目录不存在！")
    print("\n可能的原因:")
    print("1. 这是 Linux 路径，但你在 Windows 系统上")
    print("2. 目录尚未创建")
    
    print("\n建议的解决方案:")
    print("1. 在 config/settings.py 中修改 SPECIAL_RULES_DIR 为:")
    print(f"   SPECIAL_RULES_DIR = r'e:\\project\\code_here\\llm_pro\\special_rules'")
    print("   或使用相对路径:")
    print(f"   SPECIAL_RULES_DIR = os.path.join(os.path.dirname(__file__), '..', 'special_rules')")
    
    print("\n2. 创建目录并添加特殊规定文件:")
    suggested_path = os.path.join(os.path.dirname(__file__), 'special_rules')
    print(f"   mkdir {suggested_path}")
    print(f"   # 然后在该目录下创建 .txt 或 .md 文件")
else:
    print("\n✓ 目录存在")
    
    # 列出目录中的文件
    try:
        files = os.listdir(Settings.SPECIAL_RULES_DIR)
        txt_md_files = [f for f in files if f.endswith('.txt') or f.endswith('.md')]
        
        print(f"\n目录中的文件总数: {len(files)}")
        print(f"特殊规定文件数量 (.txt/.md): {len(txt_md_files)}")
        
        if txt_md_files:
            print("\n特殊规定文件列表:")
            for f in txt_md_files:
                file_path = os.path.join(Settings.SPECIAL_RULES_DIR, f)
                file_size = os.path.getsize(file_path)
                print(f"  - {f} ({file_size} 字节)")
        else:
            print("\n❌ 目录中没有 .txt 或 .md 文件")
            print("请在该目录下创建特殊规定文件")
    except Exception as e:
        print(f"\n❌ 读取目录失败: {str(e)}")

print("\n" + "=" * 80)
