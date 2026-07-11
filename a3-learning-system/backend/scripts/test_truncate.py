"""测试 truncate_messages 是否修复 13→1 激进截断问题"""
import sys
sys.path.insert(0, r"E:\code\claude-1\a3-learning-system\backend")

from app.utils.llm_helper import truncate_messages, count_messages_tokens

# 场景1: 模拟主人在 question_agent.py:515 的情况
# 1 system + 12 history (max_history=12), 其中一条是 RAG 检索结果很大
print("=" * 60)
print("场景 1: RAG 检索结果撑爆 token")
print("=" * 60)

messages = [
    {"role": "system", "content": "You are an AI tutor. " * 100},  # ~700 tokens
]
# 11 条小对话历史
for i in range(11):
    role = "user" if i % 2 == 0 else "assistant"
    messages.append({"role": role, "content": f"对话 {i}: " + "normal content here. " * 20})
# 1 条大 RAG 检索结果 (模拟 3500 tokens)
messages.append({"role": "user", "content": "RAG参考资料:\n" + ("Python 是一种广泛使用的高级编程语言. " * 200)})

total_before = count_messages_tokens(messages)
result = truncate_messages(messages, max_tokens=6000)
total_after = count_messages_tokens(result)

print(f"Before: {len(messages)} msgs, {total_before} tokens")
print(f"After:  {len(result)} msgs, {total_after} tokens")
print(f"Truncated: {len(messages)} -> {len(result)}")
print()
for i, m in enumerate(result):
    c = m.get("content", "")
    print(f"  [{i:2d}] {m.get('role'):10s} {len(c):4d} chars, {count_messages_tokens([m]):4d} tokens")

# 场景2: 没有大 content, 正常多轮对话
print()
print("=" * 60)
print("场景 2: 正常多轮对话, 不应截断")
print("=" * 60)

messages2 = [
    {"role": "system", "content": "You are an AI tutor. " * 50},
]
for i in range(8):
    role = "user" if i % 2 == 0 else "assistant"
    messages2.append({"role": role, "content": f"问题/回答 {i}: 关于 Python 的某个话题"})

result2 = truncate_messages(messages2, max_tokens=6000)
print(f"Before: {len(messages2)} msgs, {count_messages_tokens(messages2)} tokens")
print(f"After:  {len(result2)} msgs, {count_messages_tokens(result2)} tokens")

# 场景3: 极端情况, 全部都是大 content
print()
print("=" * 60)
print("场景 3: 全部都是大 content (极端)")
print("=" * 60)

messages3 = [
    {"role": "system", "content": "You are an AI tutor. " * 50},
]
for i in range(12):
    role = "user" if i % 2 == 0 else "assistant"
    messages3.append({"role": role, "content": f"对话 {i}: " + "大量内容. " * 500})

result3 = truncate_messages(messages3, max_tokens=6000)
print(f"Before: {len(messages3)} msgs, {count_messages_tokens(messages3)} tokens")
print(f"After:  {len(result3)} msgs, {count_messages_tokens(result3)} tokens")
for i, m in enumerate(result3):
    c = m.get("content", "")
    print(f"  [{i:2d}] {m.get('role'):10s} {len(c):4d} chars, {count_messages_tokens([m]):4d} tokens")
