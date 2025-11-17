# -*- coding: utf-8 -*-
"""
测试 ||| 分隔符是否被正确移除
"""
from core.document_processor import DocumentProcessor

def test_separator_removal():
    """测试分隔符移除功能"""
    # 创建处理器
    processor = DocumentProcessor("|||")
    
    # 测试文本（包含 ||| 分隔符）
    test_text = """中国与阿富汗的协议规定：自1996年8月22日起生效，执行协议航班任务的机组人员凭机组名单和有效护照可免办签证入境。
|||中国与丹麦的协议规定：自1988年12月10日起生效，民航办事处常驻人员及其随行家属可获发一年多次签证（由使馆签发）。
|||中国与挪威的协议规定：自1988年12月10日起生效，民航办事处常驻人员及其随行家属可获发一年多次签证（由使馆签发）。"""
    
    # 执行切分
    chunks = processor._split_by_pattern(test_text)
    
    print(f"切分结果：共 {len(chunks)} 个块\n")
    print("=" * 80)
    
    # 检查每个块
    for i, chunk in enumerate(chunks, 1):
        print(f"\n【块 {i}】")
        print(f"长度: {len(chunk)} 字符")
        print(f"内容: {chunk[:100]}..." if len(chunk) > 100 else f"内容: {chunk}")
        
        # 检查是否包含分隔符
        if "|||" in chunk:
            print("❌ 错误：块中仍包含分隔符 |||")
        else:
            print("✓ 正确：块中不包含分隔符")
        
        print("-" * 80)
    
    # 验证结果
    all_clean = all("|||" not in chunk for chunk in chunks)
    
    print("\n" + "=" * 80)
    if all_clean:
        print("✓✓✓ 测试通过：所有块都不包含 ||| 分隔符")
    else:
        print("❌❌❌ 测试失败：某些块仍包含 ||| 分隔符")
    
    return all_clean

if __name__ == "__main__":
    test_separator_removal()
