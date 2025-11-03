# -*- coding: utf-8 -*-
"""
意图分类器测试脚本
"""
import sys
import os
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.intent_classifier import IntentClassifier
from services.llm_service import LLMService
from config import Settings
from utils.logger import logger


def test_intent_classifier():
    """测试意图分类器"""
    
    print("=" * 60)
    print("意图分类器测试")
    print("=" * 60)
    
    # 检查配置
    print(f"\n配置检查:")
    print(f"ENABLE_INTENT_CLASSIFIER: {Settings.ENABLE_INTENT_CLASSIFIER}")
    print(f"INTENT_CLASSIFIER_TIMEOUT: {Settings.INTENT_CLASSIFIER_TIMEOUT}s")
    print(f"INTENT_CLASSIFIER_LLM_ID: {Settings.INTENT_CLASSIFIER_LLM_ID}")
    
    # 1. 初始化 LLM 服务
    print("\n1. 初始化 LLM 服务...")
    try:
        llm_service = LLMService()
        llm_service.initialize()
        llm_client = llm_service.get_client(Settings.INTENT_CLASSIFIER_LLM_ID)
        print("✓ LLM 服务初始化成功")
    except Exception as e:
        print(f"✗ LLM 服务初始化失败: {e}")
        return False
    
    # 2. 初始化意图分类器
    print("\n2. 初始化意图分类器...")
    try:
        classifier = IntentClassifier(llm_client)
        print("✓ 意图分类器初始化成功")
    except Exception as e:
        print(f"✗ 意图分类器初始化失败: {e}")
        return False
    
    # 3. 测试用例
    test_cases = [
        # (问题, 预期策略, 描述)
        ("去泰国需要签证吗？", "both", "免签相关问题"),
        ("中国护照可以免签去哪些国家？", "both", "免签相关问题"),
        ("持普通护照去日本需要办理签证吗？", "both", "免签相关问题"),
        ("落地签和免签有什么区别？", "both", "免签相关问题"),
        ("新加坡对中国免签吗？", "both", "免签相关问题"),
        ("如何办理护照？", "general", "非免签问题"),
        ("边检的职责是什么？", "general", "非免签问题"),
        ("JS0和JS1是什么意思？", "general", "非免签问题"),
        ("港澳通行证怎么办理？", "general", "非免签问题"),
    ]
    
    print("\n3. 执行测试用例...")
    print("-" * 60)
    
    passed = 0
    failed = 0
    
    for i, (question, expected, description) in enumerate(test_cases, 1):
        print(f"\n测试 {i}/{len(test_cases)}: {description}")
        print(f"问题: {question}")
        print(f"预期策略: {expected}")
        
        try:
            result = classifier.classify(question)
            
            if result == expected:
                print(f"✓ 通过 - 实际策略: {result}")
                passed += 1
            else:
                print(f"✗ 失败 - 实际策略: {result}")
                failed += 1
                
        except Exception as e:
            print(f"✗ 错误: {e}")
            failed += 1
    
    # 4. 测试缓存
    print("\n" + "-" * 60)
    print("\n4. 测试缓存功能...")
    test_question = "去泰国需要签证吗？"
    
    # 清空缓存
    classifier.clear_cache()
    
    # 第一次调用（不使用缓存）
    start = time.time()
    result1 = classifier.classify(test_question)
    time1 = time.time() - start
    print(f"第一次调用: {time1:.3f}s - 结果: {result1}")
    
    # 第二次调用（使用缓存）
    start = time.time()
    result2 = classifier.classify(test_question)
    time2 = time.time() - start
    print(f"第二次调用: {time2:.3f}s - 结果: {result2}")
    
    if time2 < time1 / 10:  # 缓存应该快至少 10 倍
        print(f"✓ 缓存功能正常（加速 {time1/time2:.1f}x）")
    else:
        print("✗ 缓存可能未生效")
    
    # 5. 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"通过: {passed}/{len(test_cases)}")
    print(f"失败: {failed}/{len(test_cases)}")
    print(f"成功率: {passed/len(test_cases)*100:.1f}%")
    
    if failed == 0:
        print("\n✓ 所有测试通过！")
        print("\n下一步:")
        print("  - 设置环境变量: export ENABLE_INTENT_CLASSIFIER=true")
        print("  - 集成到 KnowledgeHandler")
        print("  - 在 app.py 中初始化")
    else:
        print(f"\n✗ {failed} 个测试失败")
    
    return failed == 0


if __name__ == "__main__":
    try:
        success = test_intent_classifier()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
