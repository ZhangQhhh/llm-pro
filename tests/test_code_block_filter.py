# -*- coding: utf-8 -*-
"""
测试代码块符号过滤功能
"""
import sys
sys.path.insert(0, 'e:/project/code_here/llm_pro')

from utils.knowledge_utils.llm_stream_parser import _remove_code_blocks


def test_code_block_filter():
    """测试各种代码块符号的过滤"""
    
    test_cases = [
        # (输入, 期望输出, 描述)
        ("```python\nprint('hello')\n```", "python\nprint('hello')\n", "标准代码块"),
        ("```python\nprint('hello')\n```", "python\nprint('hello')\n", "全角代码块"),
        ("这是```代码```示例", "这是代码示例", "行内代码块"),
        ("```\n代码内容\n```", "\n代码内容\n", "无语言标识的代码块"),
        ("正常文本没有代码块", "正常文本没有代码块", "无代码块"),
        ("``混合``代码块", "混合代码块", "混合反引号"),
        ("```````多个反引号", "多个反引号", "连续反引号"),
        ("核验1精简改这些证可正常出国上述规格报业规范立业务规定1-某数符号\"Q2签证\"", 
         "核验1精简改这些证可正常出国上述规格报业规范立业务规定1-某数符号\"Q2签证\"", 
         "实际问题文本（无代码块）"),
    ]
    
    print("=" * 80)
    print("代码块符号过滤测试")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for i, (input_text, expected, description) in enumerate(test_cases, 1):
        result = _remove_code_blocks(input_text)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        
        if result == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"\n测试 {i}: {description}")
        print(f"  输入: {repr(input_text)}")
        print(f"  期望: {repr(expected)}")
        print(f"  实际: {repr(result)}")
        print(f"  {status}")
    
    print("\n" + "=" * 80)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 80)
    
    return failed == 0


if __name__ == "__main__":
    success = test_code_block_filter()
    sys.exit(0 if success else 1)
