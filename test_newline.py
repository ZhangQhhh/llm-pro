# 测试换行符转换
text = "第一行\n第二行\n\n第三行"
print("原始文本:")
print(repr(text))
print()

# 模拟 clean_for_sse_text 的处理
cleaned = text.replace('\r\n', '\n').replace('\r', '')
while '\n\n' in cleaned:
    cleaned = cleaned.replace('\n\n', '\n')
cleaned = cleaned.replace('\n', '\\n')

print("处理后:")
print(repr(cleaned))
print()
print("实际显示:")
print(cleaned)
print()

# 前端应该如何处理
frontend_result = cleaned.replace('\\n', '\n')
print("前端转换后:")
print(repr(frontend_result))
print()
print("前端显示:")
print(frontend_result)
