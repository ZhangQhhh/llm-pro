#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
航司意图分类测试脚本
测试意图分类器是否能正确识别航司相关问题
"""
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.intent_classifier import IntentClassifier
from services.llm_service import LLMService
from config import Settings
from utils.logger import logger


def test_airline_intent():
    """测试航司意图分类"""
    
    logger.info("=" * 60)
    logger.info("航司意图分类测试")
    logger.info("=" * 60)
    
    # 初始化 LLM 服务
    logger.info("初始化 LLM 服务...")
    llm_service = LLMService()
    llm_client = llm_service.get_llm(Settings.INTENT_CLASSIFIER_LLM_ID)
    
    # 初始化意图分类器
    logger.info("初始化意图分类器...")
    classifier = IntentClassifier(llm_client)
    
    # 测试用例
    test_cases = [
        # 航司相关问题
        ("执行中美航班的机组人员需要签证吗？", "airline"),
        ("民航办事处常驻人员如何办理签证？", "airline"),
        ("飞往日本的机组人员入境要求是什么？", "airline"),
        ("包机机组人员免签吗？", "airline"),
        ("中国与澳大利亚的民航协议内容是什么？", "airline"),
        ("空乘人员去美国需要办理签证吗？", "airline"),
        
        # 免签相关问题
        ("去泰国旅游需要签证吗？", "visa_free"),
        ("中国护照可以免签去哪些国家？", "visa_free"),
        ("过境免签政策是什么？", "visa_free"),
        ("厄瓜多尔对中国免签吗？", "visa_free"),
        
        # 通用问题
        ("如何办理护照？", "general"),
        ("边检的职责是什么？", "general"),
        ("港澳通行证如何续签？", "general"),
        ("JS0和JS1是什么意思？", "general"),
    ]
    
    logger.info(f"\n开始测试 {len(test_cases)} 个用例...\n")
    
    correct = 0
    total = len(test_cases)
    
    for i, (question, expected) in enumerate(test_cases, 1):
        logger.info(f"[{i}/{total}] 问题: {question}")
        logger.info(f"       期望: {expected}")
        
        try:
            result = classifier.classify(question)
            logger.info(f"       结果: {result}")
            
            if result == expected:
                logger.info("       ✓ 正确")
                correct += 1
            else:
                logger.warning("       ✗ 错误")
        except Exception as e:
            logger.error(f"       ✗ 分类失败: {e}")
        
        logger.info("")
    
    # 统计结果
    accuracy = (correct / total) * 100
    logger.info("=" * 60)
    logger.info(f"测试完成！")
    logger.info(f"正确: {correct}/{total}")
    logger.info(f"准确率: {accuracy:.1f}%")
    logger.info("=" * 60)
    
    if accuracy >= 80:
        logger.info("✓ 测试通过（准确率 >= 80%）")
        return True
    else:
        logger.warning("✗ 测试未通过（准确率 < 80%）")
        logger.warning("建议调整 prompts.py 中的意图分类提示词")
        return False


def test_edge_cases():
    """测试边界情况"""
    
    logger.info("\n" + "=" * 60)
    logger.info("边界情况测试")
    logger.info("=" * 60)
    
    # 初始化
    llm_service = LLMService()
    llm_client = llm_service.get_llm(Settings.INTENT_CLASSIFIER_LLM_ID)
    classifier = IntentClassifier(llm_client)
    
    edge_cases = [
        # 混合问题
        ("机组人员去泰国旅游需要签证吗？", ["airline", "visa_free"]),  # 可能是两者之一
        ("民航办事处人员的护照如何办理？", ["airline", "general"]),
        
        # 模糊问题
        ("签证怎么办？", ["general", "visa_free"]),
        ("去美国需要什么？", ["visa_free", "general"]),
    ]
    
    logger.info(f"\n测试 {len(edge_cases)} 个边界用例...\n")
    
    for i, (question, acceptable) in enumerate(edge_cases, 1):
        logger.info(f"[{i}] 问题: {question}")
        logger.info(f"    可接受结果: {acceptable}")
        
        try:
            result = classifier.classify(question)
            logger.info(f"    实际结果: {result}")
            
            if result in acceptable:
                logger.info("    ✓ 在可接受范围内")
            else:
                logger.warning(f"    ⚠ 超出预期（但可能合理）")
        except Exception as e:
            logger.error(f"    ✗ 分类失败: {e}")
        
        logger.info("")


if __name__ == "__main__":
    try:
        # 检查配置
        if not Settings.ENABLE_INTENT_CLASSIFIER:
            logger.warning("意图分类器未启用！")
            logger.warning("请设置: export ENABLE_INTENT_CLASSIFIER=true")
            sys.exit(1)
        
        # 运行测试
        success = test_airline_intent()
        
        # 运行边界测试
        test_edge_cases()
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        sys.exit(1)
