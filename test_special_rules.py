# -*- coding: utf-8 -*-
"""
测试特殊规定加载功能
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prompts import load_special_rules_from_files
from config.settings import Settings
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

def test_special_rules():
    """测试特殊规定加载"""
    print("=" * 80)
    print("测试特殊规定加载功能")
    print("=" * 80)
    
    print(f"\n特殊规定目录: {Settings.SPECIAL_RULES_DIR}")
    print(f"目录是否存在: {os.path.exists(Settings.SPECIAL_RULES_DIR)}")
    
    if os.path.exists(Settings.SPECIAL_RULES_DIR):
        files = [f for f in os.listdir(Settings.SPECIAL_RULES_DIR) 
                if f.endswith('.txt') or f.endswith('.md')]
        print(f"找到的文件数量: {len(files)}")
        print(f"文件列表: {files}")
    
    print("\n" + "=" * 80)
    print("开始加载特殊规定...")
    print("=" * 80 + "\n")
    
    # 调用加载函数
    special_rules = load_special_rules_from_files()
    
    print("\n" + "=" * 80)
    print("加载结果:")
    print("=" * 80)
    
    if special_rules:
        print(f"\n✓ 成功加载特殊规定")
        print(f"总长度: {len(special_rules)} 字符")
        print(f"\n前 500 字符预览:")
        print("-" * 80)
        print(special_rules[:500])
        print("-" * 80)
        
        # 统计规定数量
        rule_count = special_rules.count("【特殊规定")
        print(f"\n特殊规定条数: {rule_count}")
    else:
        print("\n✗ 未加载到任何特殊规定")
        print("可能的原因:")
        print("1. 特殊规定目录不存在")
        print("2. 目录中没有 .txt 或 .md 文件")
        print("3. 文件内容为空")
        print("4. 文件读取权限问题")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_special_rules()
