# -*- coding: utf-8 -*-
"""
测试对话管理新增功能
包括：清空会话、获取统计、缓存优化
"""
import requests
import json
import time


BASE_URL = "http://localhost:5000"


def test_conversation_flow():
    """测试完整对话流程"""
    print("=" * 60)
    print("测试1: 完整对话流程")
    print("=" * 60)

    session_id = None

    # 第一轮对话
    print("\n[第1轮] 提问：什么是边检业务？")
    response = requests.post(
        f"{BASE_URL}/api/knowledge_chat_conversation",
        json={
            "question": "什么是边检业务？",
            "thinking": False,
            "model_id": "qwen3-32b"
        },
        stream=True
    )

    for line in response.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: SESSION:'):
                session_id = decoded.split('SESSION:')[1].strip()
                print(f"✅ 会话ID: {session_id}")
            elif decoded.startswith('data: CONTENT:'):
                content = decoded.split('CONTENT:')[1]
                print(content, end='', flush=True)

    print("\n")
    time.sleep(1)

    # 第二轮对话（追问）
    print("\n[第2轮] 追问：它的主要职责是什么？")
    response = requests.post(
        f"{BASE_URL}/api/knowledge_chat_conversation",
        json={
            "question": "它的主要职责是什么？",
            "session_id": session_id,
            "thinking": False
        },
        stream=True
    )

    for line in response.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: CONTENT:'):
                content = decoded.split('CONTENT:')[1]
                print(content, end='', flush=True)

    print("\n")

    return session_id


def test_get_statistics(session_id):
    """测试获取会话统计"""
    print("\n" + "=" * 60)
    print("测试2: 获取会话统计")
    print("=" * 60)

    response = requests.post(
        f"{BASE_URL}/api/conversation/statistics",
        json={"session_id": session_id}
    )

    result = response.json()
    if result.get("type") == "success":
        stats = result["data"]
        print(f"\n📊 会话统计信息:")
        print(f"  - 会话ID: {stats['session_id']}")
        print(f"  - 总轮次: {stats['total_turns']}")
        print(f"  - 总Token数: {stats['total_tokens']}")
        print(f"  - 平均每轮Token数: {stats['avg_tokens_per_turn']:.1f}")
        print(f"  - 首次对话: {stats.get('first_conversation', 'N/A')}")
        print(f"  - 最后对话: {stats.get('last_conversation', 'N/A')}")
    else:
        print(f"❌ 获取统计失败: {result.get('content')}")


def test_clear_session(session_id):
    """测试清空会话"""
    print("\n" + "=" * 60)
    print("测试3: 清空会话")
    print("=" * 60)

    response = requests.post(
        f"{BASE_URL}/api/conversation/clear",
        json={"session_id": session_id}
    )

    result = response.json()
    if result.get("type") == "success":
        print(f"✅ {result['message']}")
    else:
        print(f"❌ 清空失败: {result.get('content')}")

    # 验证清空后统计为0
    print("\n验证清空结果...")
    response = requests.post(
        f"{BASE_URL}/api/conversation/statistics",
        json={"session_id": session_id}
    )

    result = response.json()
    if result.get("type") == "success":
        stats = result["data"]
        if stats['total_turns'] == 0:
            print(f"✅ 确认已清空，当前轮次: {stats['total_turns']}")
        else:
            print(f"⚠️ 清空可能未成功，当前轮次: {stats['total_turns']}")


def test_clear_cache():
    """测试清空缓存"""
    print("\n" + "=" * 60)
    print("测试4: 清空全局缓存")
    print("=" * 60)

    response = requests.post(
        f"{BASE_URL}/api/conversation/cache/clear",
        json={}
    )

    result = response.json()
    if result.get("type") == "success":
        print(f"✅ {result['message']}")
    else:
        print(f"❌ 清空缓存失败: {result.get('content')}")


def test_token_warning():
    """测试Token数量监控告警"""
    print("\n" + "=" * 60)
    print("测试5: Token数量监控（超长问答）")
    print("=" * 60)

    # 构造一个超长问题
    long_question = "请详细介绍" + "边检业务的流程、规定、注意事项、历史沿革" * 50

    print(f"\n提问一个超长问题（{len(long_question)}字符）...")
    response = requests.post(
        f"{BASE_URL}/api/knowledge_chat_conversation",
        json={
            "question": long_question,
            "thinking": False
        },
        stream=True
    )

    for line in response.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: SESSION:'):
                session_id = decoded.split('SESSION:')[1].strip()
                print(f"✅ 会话ID: {session_id}")
                break

    print("⚠️ 检查服务器日志，应该有Token数量警告信息")


def main():
    """主测试流程"""
    print("\n" + "=" * 60)
    print("对话管理新功能测试套件")
    print("=" * 60)

    try:
        # 测试1: 完整对话流程
        session_id = test_conversation_flow()

        if not session_id:
            print("❌ 无法获取会话ID，测试终止")
            return

        time.sleep(1)

        # 测试2: 获取统计信息
        test_get_statistics(session_id)

        time.sleep(1)

        # 测试3: 清空会话
        test_clear_session(session_id)

        time.sleep(1)

        # 测试4: 清空缓存
        test_clear_cache()

        # 测试5: Token监控（可选，生成大量日志）
        # test_token_warning()

        print("\n" + "=" * 60)
        print("✅ 所有测试完成！")
        print("=" * 60)

    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请确保服务已启动在 http://localhost:5000")
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

