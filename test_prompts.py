# -*- coding: utf-8 -*-
"""
测试提示词加载功能
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.prompt_loader import PromptLoader

def test_prompt_loader():
    """测试提示词加载器"""
    print("=" * 60)
    print("测试提示词加载功能")
    print("=" * 60)

    # 初始化加载器
    loader = PromptLoader("prompts.json")

    # 测试场景1: 加载字符串格式的提示词
    print("\n【测试1】加载字符串格式提示词:")
    general_system = loader.get("judge_option.system.general")
    print(f"judge_option.system.general: {general_system}")

    # 测试场景2: 加载数组格式的提示词
    print("\n【测试2】加载数组格式提示词:")
    rag_simple = loader.get("knowledge.system.rag_simple")
    print(f"knowledge.system.rag_simple:")
    print(rag_simple)

    # 测试场景3: 加载长提示词
    print("\n【测试3】加载长提示词 (rag_advanced):")
    rag_advanced = loader.get("knowledge.system.rag_advanced")
    print(f"长度: {len(rag_advanced)} 字符")
    print(f"前100个字符: {rag_advanced[:100]}...")
    print(f"是否包含换行符: {'\\n' in rag_advanced}")

    # 测试场景4: 加载用户提示词
    print("\n【测试4】加载用户提示词:")
    user_rag_simple = loader.get("knowledge.user.rag_simple")
    print(f"knowledge.user.rag_simple:")
    print(user_rag_simple)

    # 测试场景5: 测试带占位符的提示词
    print("\n【测试5】测试占位符替换:")
    user_prompt = loader.get("knowledge.user.rag_simple")
    filled_prompt = user_prompt.replace("{question}", "港澳台居民往来内地通行证的有效期是多久？")
    print("替换后的提示词:")
    print(filled_prompt)

    # 测试场景6: 测试不存在的路径
    print("\n【测试6】测试不存在的路径:")
    not_exist = loader.get("not.exist.path", "默认值")
    print(f"不存在的路径返回: {not_exist}")

    # 测试场景7: 测试所有关键路径
    print("\n【测试7】验证所有关键路径:")
    test_paths = [
        "judge_option.system.general",
        "judge_option.system.rag",
        "judge_option.general.think_on",
        "judge_option.rag.think_on",
        "knowledge.system.rag_simple",
        "knowledge.system.rag_advanced",
        "knowledge.system.no_rag_think",
        "knowledge.system.no_rag_simple",
        "knowledge.user.rag_simple",
        "knowledge.user.rag_advanced",
        "knowledge.user.no_rag_think",
        "knowledge.user.no_rag_simple",
    ]

    success_count = 0
    for path in test_paths:
        result = loader.get(path)
        if result:
            success_count += 1
            status = "✓"
        else:
            status = "✗"
        print(f"{status} {path}: {len(result) if result else 0} 字符")

    print(f"\n成功加载: {success_count}/{len(test_paths)}")

    # 总结
    print("\n" + "=" * 60)
    if success_count == len(test_paths):
        print("✓ 所有测试通过！提示词配置正常工作。")
    else:
        print(f"✗ 部分测试失败！成功: {success_count}/{len(test_paths)}")
    print("=" * 60)

if __name__ == "__main__":
    test_prompt_loader()

