# -*- coding: utf-8 -*-
"""
测试会话过滤逻辑
验证只显示当前用户的会话
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.session_helper import parse_session_id, validate_session_ownership


def test_session_filter():
    """测试会话ID过滤逻辑"""

    # 测试数据
    test_cases = [
        # (session_id, user_id, expected_result)
        ("123_abc-def-123", 123, True),   # 匹配
        ("123_abc-def-123", 456, False),  # 不匹配
        ("456_xyz-789", 456, True),       # 匹配
        ("456_xyz-789", 123, False),      # 不匹配
        ("789_test_session", 789, True),  # 匹配（UUID中有下划线）
        ("789_test_session", 123, False), # 不匹配
        ("invalid_session", 123, False),  # 无效格式
        ("", 123, False),                  # 空字符串
    ]

    print("=" * 60)
    print("测试会话ID过滤逻辑")
    print("=" * 60)

    passed = 0
    failed = 0

    for session_id, user_id, expected in test_cases:
        # 测试 parse_session_id
        parsed = parse_session_id(session_id)

        # 测试 validate_session_ownership
        is_valid = validate_session_ownership(session_id, user_id)

        status = "✅ PASS" if is_valid == expected else "❌ FAIL"

        if is_valid == expected:
            passed += 1
        else:
            failed += 1

        print(f"\n{status}")
        print(f"  Session ID: {session_id}")
        print(f"  User ID: {user_id}")
        print(f"  Parsed: {parsed}")
        print(f"  Valid: {is_valid} (Expected: {expected})")

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


def test_session_id_format():
    """测试会话ID格式验证"""

    print("\n" + "=" * 60)
    print("测试会话ID格式")
    print("=" * 60)

    # 模拟 get_user_sessions 中的过滤逻辑
    user_id = 123
    user_id_str = str(user_id)

    test_sessions = [
        "123_abc-def-123",      # 应该匹配
        "123_xyz-789",          # 应该匹配
        "456_abc-def-123",      # 不应该匹配
        "123abc_def",           # 不应该匹配（没有正确的分隔符）
        "12_abc",               # 不应该匹配（用户ID不同）
        "1234_abc",             # 不应该匹配（用户ID不同）
    ]

    matched = []
    skipped = []

    for session_id in test_sessions:
        # 模拟过滤逻辑
        if not session_id.startswith(f"{user_id_str}_"):
            skipped.append(session_id)
            continue

        # 双重验证
        try:
            parts = session_id.split('_', 1)
            if len(parts) < 2:
                skipped.append(session_id)
                continue

            session_user_id = parts[0]
            if session_user_id != user_id_str:
                skipped.append(session_id)
                continue

            matched.append(session_id)
        except (IndexError, ValueError):
            skipped.append(session_id)

    print(f"\n用户ID: {user_id}")
    print(f"\n✅ 匹配的会话 ({len(matched)}):")
    for sid in matched:
        print(f"  - {sid}")

    print(f"\n🚫 跳过的会话 ({len(skipped)}):")
    for sid in skipped:
        print(f"  - {sid}")

    # 验证结果
    expected_matched = ["123_abc-def-123", "123_xyz-789"]
    success = set(matched) == set(expected_matched)

    print(f"\n结果: {'✅ 通过' if success else '❌ 失败'}")

    return success


if __name__ == "__main__":
    print("\n🧪 开始测试会话过滤逻辑...\n")

    result1 = test_session_filter()
    result2 = test_session_id_format()

    print("\n" + "=" * 60)
    if result1 and result2:
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败！")
    print("=" * 60)

