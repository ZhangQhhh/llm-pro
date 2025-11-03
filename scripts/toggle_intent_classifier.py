# -*- coding: utf-8 -*-
"""
意图分类器开关脚本
快速启用/关闭意图分类器功能
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import Settings


def show_status():
    """显示当前状态"""
    print("\n" + "=" * 60)
    print("意图分类器当前状态")
    print("=" * 60)
    print(f"启用状态: {Settings.ENABLE_INTENT_CLASSIFIER}")
    print(f"超时时间: {Settings.INTENT_CLASSIFIER_TIMEOUT}s")
    print(f"最大重试: {Settings.INTENT_CLASSIFIER_MAX_RETRIES}")
    print(f"LLM ID: {Settings.INTENT_CLASSIFIER_LLM_ID or '(使用默认)'}")
    print("=" * 60 + "\n")


def enable_classifier():
    """启用意图分类器"""
    print("\n启用意图分类器...")
    print("请在环境变量或 .env 文件中设置：")
    print("  ENABLE_INTENT_CLASSIFIER=true")
    print("\n或者在 config/settings.py 中修改：")
    print("  ENABLE_INTENT_CLASSIFIER = True")
    print("\n修改后需要重启应用。")


def disable_classifier():
    """关闭意图分类器"""
    print("\n关闭意图分类器...")
    print("请在环境变量或 .env 文件中设置：")
    print("  ENABLE_INTENT_CLASSIFIER=false")
    print("\n或者在 config/settings.py 中修改：")
    print("  ENABLE_INTENT_CLASSIFIER = False")
    print("\n修改后需要重启应用。")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("意图分类器开关工具")
    print("=" * 60)
    
    # 显示当前状态
    show_status()
    
    # 显示菜单
    print("请选择操作：")
    print("1. 启用意图分类器")
    print("2. 关闭意图分类器")
    print("3. 查看当前状态")
    print("4. 退出")
    print()
    
    try:
        choice = input("请输入选项 (1-4): ").strip()
        
        if choice == "1":
            enable_classifier()
        elif choice == "2":
            disable_classifier()
        elif choice == "3":
            show_status()
        elif choice == "4":
            print("\n退出。")
            sys.exit(0)
        else:
            print("\n无效的选项，请重新运行脚本。")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n操作被用户中断。")
        sys.exit(1)
    except Exception as e:
        print(f"\n错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
