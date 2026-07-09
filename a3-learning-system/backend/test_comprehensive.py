"""
A3 学习系统 — 全流程深度测试（省一标准判定）
============================================
测试维度：
  T2: 意图分类准确性 (6意图 × 3用例 = 18组)
  T3: Agent路由 + 回复质量深度评估
  T4: 多轮对话上下文连续性
  T5: 边界/异常鲁棒性
  T6: SSE 流式输出格式验证
  T7: 综合评分 + 省一标准判定
"""

import json
import time
import random
import string
import re
import requests

BASE = "http://localhost:8001"

# 禁用系统代理（避免代理不可达导致连接失败）
_session = requests.Session()
_session.trust_env = False

# ============================================================
# 工具函数
# ============================================================

def new_user():
    """注册新用户，返回 token 和用户名"""
    uname = "stu_" + ''.join(random.choices(string.ascii_lowercase, k=8))
    r = _session.post(f"{BASE}/api/auth/register", json={"username": uname, "password": "Test123456"})
    token = r.json().get("access_token", "")
    return token, uname


def send_msg(token, content, timeout=120):
    """
    发送消息，解析 SSE 流，返回结构化结果
    返回: {
        "ok": bool,
        "agent": str,           # 最终 agent 名
        "content": str,          # 完整回复内容
        "events": list[dict],    # 所有 SSE 事件
        "error": str,            # 错误信息
        "latency_ms": float,     # 响应耗时(ms)
    }
    """
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    t0 = time.time()
    try:
        resp = _session.post(f"{BASE}/api/chat/send", headers=h, json={"content": content}, timeout=timeout, stream=True)
        latency = (time.time() - t0) * 1000

        events = []
        full_content = ""
        final_agent = ""

        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if line.startswith("event:"):
                event_type = line.split(":", 1)[1].strip()
                continue
            if line.startswith("data:"):
                data_str = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    data = {"raw": data_str}
                data["_event"] = event_type
                events.append(data)

                if event_type == "message":
                    full_content += data.get("content", "")
                if event_type == "agent_switch":
                    final_agent = data.get("to", "")

        # 从 done 事件后检查最终 agent
        for ev in events:
            if ev.get("_event") == "message" and "agent" in ev:
                final_agent = ev["agent"]

        return {
            "ok": True,
            "agent": final_agent,
            "content": full_content.strip(),
            "events": events,
            "error": "",
            "latency_ms": round(latency, 1),
        }
    except Exception as e:
        return {
            "ok": False,
            "agent": "",
            "content": "",
            "events": [],
            "error": str(e),
            "latency_ms": round((time.time() - t0) * 1000, 1),
        }


def print_result(label, result, expected_intent=None):
    """格式化打印单条测试结果"""
    status = "PASS" if result["ok"] else "FAIL"
    agent = result.get("agent", "?")
    content_preview = result.get("content", "")[:80].replace("\n", " ")
    latency = result.get("latency_ms", 0)

    # 意图匹配判断
    intent_match = "?"
    if expected_intent:
        if expected_intent == "chat" and agent in ("supervisor", ""):
            intent_match = "OK"
        elif expected_intent != "chat" and agent == f"{expected_intent}_agent":
            intent_match = "OK"
        else:
            intent_match = f"MISMATCH(期望{expected_intent})"

    print(f"  [{status}] {label}")
    print(f"         agent={agent}  intent={intent_match}  latency={latency}ms")
    print(f"         reply={content_preview}")
    if not result["ok"]:
        print(f"         ERROR: {result['error']}")
    print()

    return result


# ============================================================
# T2: 意图分类准确性测试 (6意图 × 3用例)
# ============================================================

def test_intent_classification(token):
    """意图分类准确性：每种意图 3 个变体用例"""
    print("=" * 70)
    print("T2: 意图分类准确性测试 (6意图 × 3用例 = 18组)")
    print("=" * 70)

    test_cases = [
        # === chat (闲聊) ===
        ("你好", "chat"),
        ("今天天气怎么样", "chat"),
        ("你叫什么名字", "chat"),

        # === evaluation (学习评估) ===
        ("评估一下我的学习情况", "evaluation"),
        ("看看我最近学得怎么样", "evaluation"),
        ("生成一份学习报告", "evaluation"),

        # === question (出题/练习) ===
        ("出几道Python算法题", "question"),
        ("给我出5道数据结构的题", "question"),
        ("我想刷一些算法题", "question"),

        # === resource (资源学习) ===
        ("教我一下Python装饰器", "resource"),
        ("解释一下什么是递归", "resource"),
        ("帮我学一下快速排序", "resource"),

        # === path (学习路径) ===
        ("我下一步该学什么", "path"),
        ("Python学到哪了，接下来呢", "path"),
        ("给我制定一个学习计划", "path"),

        # === profile (画像收集) ===
        ("我是初学者，想学Python", "profile"),
        ("我有一定编程基础", "profile"),
        ("我的目标是找一份Python开发工作", "profile"),
    ]

    results = []
    pass_count = 0
    total = len(test_cases)

    for msg, expected in test_cases:
        r = send_msg(token, msg)
        results.append((msg, expected, r))

        # 判断意图是否正确
        correct = False
        if expected == "chat" and r["agent"] in ("supervisor", ""):
            correct = True
        elif expected != "chat" and r["agent"] == f"{expected}_agent":
            correct = True

        if correct:
            pass_count += 1

        print_result(msg, r, expected)

    score = pass_count / total * 100
    print(f">>> T2 结果: {pass_count}/{total} 通过 ({score:.1f}%)")
    print()

    return score, results


# ============================================================
# T3: Agent 路由 + 回复质量深度测试
# ============================================================

def test_response_quality(token):
    """每个 Agent 的回复质量深度评估"""
    print("=" * 70)
    print("T3: Agent 回复质量深度评估")
    print("=" * 70)

    quality_tests = [
        # 核心原则：只检测回复中包含的具体学科知识点
        # 不是检测"报告格式词"，而是检测"真的教了什么/出了什么题/分析了什么领域"

        ("chat-问候", "你好", "chat",
         ["帮助"], []),  # 问候只需正常响应
        ("chat-闲聊", "你喜欢什么编程语言", "chat",
         ["python", "java", "c\\+\\+", "go", "javascript", "rust"],  # 必须提到具体语言名
         []),
        # evaluation: 检测是否分析了具体知识领域，而非泛泛的"掌握度"
        ("evaluation-评估", "评估一下我的学习情况", "evaluation",
         ["python|数据结构|算法|数据库|前端|后端|机器学习",  # 具体知识领域
          "函数|列表|字典|类|循环|递归|排序|树|图",           # 具体知识点
          "优势|不足|强项|弱项|建议.*学|接下来.*学",          # 有针对性的分析
          "程度|百分比|%|\\d+/10|\\d+分"],                    # 量化指标
         ["错误", "失败"]),
        # question: 检测题目中包含具体的编程知识点概念
        ("question-出题", "出3道Python基础题", "question",
         # 题目必须涉及真实的编程概念，不是空壳格式
         ["变量|参数|返回值|函数|def ",                        # 函数相关
          "列表|字典|元组|集合|字符串",                         # 数据类型
          "循环|for |while |if |条件",                          # 控制流
          "\\[\\]|\\(\\)|\\{\\}|\\.append|\\.get|len\\(",     # 实际代码符号/方法
          "输出|打印|print|return",                             # IO操作
          "选择|填空|判断|编写|实现"],                           # 题目动作词
         ["错误", "无法"]),
        # 【新增】question-C++出题（验证语言遵守）
        ("question-C++出题", "我要学C++，给我出道题", "question",
         # 必须使用C++相关概念，不能出现Python
         ["c\\+\\+|指针|引用|include|#include|std::|vector|int main|cout|cin|namespace|class \\w+\\s*\\{",
          "void|int\\s+\\w+\\s*\\(|return\\s*\\d+|\\*|&|->|::",   # C++语法特征
          "对象|类|构造|析构|模板|STL|数组|内存"],                # C++概念
         ["python|print\\(|def \\w+\\(|列表|字典|\\.append|self"]),  # 绝对不能出现Python
        # 【新增】question-排除算法（验证约束遵守）
        ("question-排除算法", "我要学C++基础，不要算法题", "question",
         # 必须是C++基础概念，不是算法
         ["c\\+\\+|指针|引用|include|std::|vector|string|int\\s+\\w+|cout|class",
          "变量|数据类型|循环|条件|函数|输入输出"],
         ["动态规划|递归|贪心|分治|回溯|DFS|BFS|时间复杂度|空间复杂度"]),  # 不能有算法
        # resource: 检测教学中包含了目标知识点的核心概念和代码示例
        ("resource-教学", "教我Python列表推导式", "resource",
         ["列表", "推导式|推导",                                  # 核心术语
          "\\[.*for .*in .*\\]|\\[.*for.*in.*\\]",              # 列表推导式代码模式
          "表达式|迭代|元素|生成|新列表",                         # 核心概念解释
          "例子|示例|例如|比如",                                 # 有实例说明
          "语法|写法|格式"],                                     # 语法讲解
         ["错误", "无法"]),
        # 【新增】resource-C++教学（验证语言遵守）
        ("resource-C++教学", "讲一下C++的指针和引用", "resource",
         # 必须讲解C++指针/引用概念
         ["指针|pointer|引用|reference",                          # 核心术语
          "\\*|&|int\\s*\\*|&\\w+|->|\\.|address|内存地址",      # 指针语法特征
          "变量|地址|解引用|传值|传址|堆|栈",                     # 指针相关概念
          "例子|示例|代码|例如|比如"],                           # 有实例说明
         ["python|print\\(|def \\w+\\(|列表|字典|self"]),        # 绝对不能出现Python
        # path: 检测路径规划包含具体的学习主题/阶段内容
        ("path-规划", "我下一步该学什么", "path",
         # 必须提到具体可学的知识主题，不是空洞的"第一阶段"
         ["python|数据结构|算法|数据库|web|框架|项目",            # 具体技术栈
          "基础|进阶|高级|实战",                                  # 学习层级
          "周|天|小时|月",                                       # 时间单位
          "变量|函数|类|模块|包|api|接口",                       # 具体知识点
          "复习|练习|项目|实战"],                                # 学习方式
         ["错误", "无法"]),
        # 【新增】path-C++路径（验证语言遵守）
        ("path-C++路径", "我想学C++，帮我规划学习路线", "path",
         # 路径必须围绕C++
         ["c\\+\\+",                                              # 必须提到C++
          "基础|进阶|面向对象|STL|模板|内存管理",                 # C++学习阶段
          "指针|引用|类|继承|多态|虚函数",                        # C++核心概念
          "周|小时|阶段|步骤"],                                  # 规划要素
         ["python|django|flask|react|vue|列表|字典|装饰器"]),    # 不应有其他语言
        # profile: 检测画像采集是否在了解用户的具体背景信息
        ("profile-画像", "我想学Python数据分析", "profile",
         ["基础|水平|经验|学过|了解|掌握",                        # 了解背景
          "目标|方向|求职|工作|兴趣",                            # 了解目标
          "时间|每天|每周|投入",                                 # 了解时间
          "告诉|说说|简单|介绍一下"],                           # 引导语
         ["错误", "无法"]),
    ]

    scores = []
    for label, msg, expected, positive_kw, negative_kw in quality_tests:
        r = send_msg(token, msg)
        content = r.get("content", "")
        content_lower = content.lower()

        # 关键词命中评分（支持显式正则/OR模式）
        pos_hits = 0
        for kw in positive_kw:
            # 判断是否为正则：含转义符 | 复杂结构 | 管道符(OR) | 显式锚点
            is_regex = ('\\' in kw or                        # 含转义如 \[, \d
                        '|' in kw or                          # OR 模式如 python|java|c++
                        re.search(r'[.+*?\[\](){}|^$].*[.+*?\[\](){}|^$]', kw) or  # 多个连续特殊字符
                        kw.startswith('^') or kw.endswith('$'))  # 显式锚点
            if is_regex:
                try:
                    if re.search(kw, content, re.IGNORECASE):
                        pos_hits += 1
                except re.error:
                    pass  # 正则无效则跳过
            elif kw.lower() in content_lower:
                pos_hits += 1

        neg_hits = sum(1 for kw in negative_kw if kw.lower() in content_lower)

        # 内容长度评分 (期望至少50字符)
        length_score = min(100, len(r.get("content", "")) / 2)

        # 综合质量分
        quality = (pos_hits / max(len(positive_kw), 1) * 50 +
                   max(0, 30 - neg_hits * 15) +
                   min(20, length_score / 5))
        quality = min(100, max(0, quality))
        scores.append(quality)

        grade = "A" if quality >= 80 else "B" if quality >= 60 else "C" if quality >= 40 else "D"
        print(f"  [{grade}] {label} | 质量={quality:.0f}/100 | "
              f"关键词+={pos_hits}/{len(positive_kw)} -={neg_hits} | "
              f"字数={len(r.get('content',''))} | agent={r['agent']}")
        print(f"       预览: {r.get('content', '')[:100].replace(chr(10), ' ')}")
        print()

    avg = sum(scores) / len(scores) if scores else 0
    print(f">>> T3 平均质量分: {avg:.1f}/100")
    print()

    return avg, scores


# ============================================================
# T4: 多轮对话上下文连续性测试
# ============================================================

def test_context_continuity(token):
    """多轮对话中上下文是否保持连续（多维度检测）"""
    print("=" * 70)
    print("T4: 多轮对话上下文连续性测试")
    print("=" * 70)

    conversations = [
        # 对话组1: 学习主题连续性（同一用户同一会话）
        [
            ("第一轮: 学Python", "我想学Python基础", "resource"),
            ("第二轮: 追问细节", "那列表和元组有什么区别", "resource"),
            ("第三轮: 再次追问", "能给我举个例子吗", "resource"),
        ],
        # 对话组2: 出题→答题→再出题（递进关系）
        [
            ("第一轮: 要题目", "给我出道算法题", "question"),
            ("第二轮: 做完了", "我做完了，再来一道更难的", "question"),
            ("第三轮: 评估", "评估一下我现在水平", "evaluation"),
        ],
        # 对话组3: 显式上下文依赖（代词指代）
        [
            ("第一轮: 提问", "什么是二叉树", "resource"),
            ("第二轮: 代词指代", "它的遍历方式有哪些", "resource"),
            ("第三轮: 深入追问", "递归和非递归哪个更好", "chat"),
        ],
    ]

    all_results = []
    context_scores = []

    for conv_idx, conv in enumerate(conversations):
        print(f"  --- 对话组 {conv_idx + 1} ---")
        conv_results = []
        prev_msgs = []  # 保存所有历史消息用于跨轮检测

        for step_label, msg, expected in conv:
            r = send_msg(token, msg)
            conv_results.append((step_label, msg, expected, r))
            content = r.get("content", "")

            # 多维度上下文检测
            has_context = False
            ctx_method = ""

            if not prev_msgs:
                # 第一轮无历史
                has_context = True  # N/A 不扣分
                ctx_method = "N/A"
            else:
                prev_topic = prev_msgs[-1] if prev_msgs else ""
                all_prev = " ".join(prev_msgs)

                # 方法1: 关键词重叠（前文关键词出现在回复中）
                keywords = set(re.findall(r'[\u4e00-\u9fff]{2,}', prev_topic))
                kw_overlap = sum(1 for kw in keywords if kw in content)

                # 方法2: 代词/指代检测（回复中出现"它""这个""上述"等且前文有主题）
                pronouns = ["它", "这个", "上面", "前面", "刚才", "之前", "那种"]
                has_pronoun = any(p in content for p in pronouns) and len(prev_topic) > 3

                # 方法3: 领域一致性（前后讨论同一技术领域）
                tech_domains = {
                    "python": ["python", "列表", "元组", "字典", "推导"],
                    "算法": ["算法", "二叉树", "遍历", "递归", "排序", "复杂度"],
                    "数据结构": ["数组", "链表", "树", "图", "栈", "队列"],
                    "编程": ["代码", "函数", "变量", "循环", "条件", "类"],
                }
                prev_domain = None
                curr_domain = None
                for domain, terms in tech_domains.items():
                    if any(t in all_prev.lower() for t in terms):
                        prev_domain = domain
                    if any(t in content.lower() for t in terms):
                        curr_domain = domain

                # 综合判断：任一方法通过即认为有上下文
                has_context = kw_overlap > 0 or has_pronoun or (
                    prev_domain and curr_domain and prev_domain == curr_domain
                )

                if kw_overlap > 0:
                    ctx_method = f"关键词({kw_overlap})"
                elif has_pronoun:
                    ctx_method = "代词指代"
                elif prev_domain == curr_domain:
                    ctx_method = f"领域({prev_domain})"
                else:
                    ctx_method = "无关联"

            # 评分：有上下文80分，首轮N/A给70分，无上下文30分
            if not prev_msgs:
                ctx_score = 70  # 首轮不扣分但也不满分
            elif has_context:
                ctx_score = 85 + min(15, kw_overlap * 5) if '关键词' in ctx_method else 80
            else:
                ctx_score = 30

            context_scores.append(ctx_score)
            prev_msgs.append(msg)

            status = "✓" if has_context or not prev_msgs[:-1] else "✗"
            print(f"    [{status}] [{step_label}] \"{msg}\"")
            print(f"      agent={r['agent']} 字数={len(content)} "
                  f"方法={ctx_method} 得分={ctx_score}")

        all_results.append(conv_results)
        print()

    avg_ctx = sum(context_scores) / len(context_scores) if context_scores else 0
    print(f">>> T4 上下文连续性得分: {avg_ctx:.1f}/100")
    print()

    return avg_ctx, all_results


# ============================================================
# T5: 边界/异常鲁棒性测试
# ============================================================

def test_robustness(token):
    """边界条件和异常输入处理能力"""
    print("=" * 70)
    print("T5: 边界/异常鲁棒性测试")
    print("=" * 70)

    edge_cases = [
        ("空格输入", "   "),
        ("超长输入", "请解释" + "很长的内容" * 50),
        ("纯符号", "!@#$%^&*()_+-=[]{}|;':\",./<>?"),
        ("混合语言", "Hello 我想 learn Python 编程 can you help me?"),
        ("数字输入", "1234567890"),
        ("单字输入", "好"),
        ("SQL注入尝试", "'; DROP TABLE users; --"),
        ("XSS尝试", "<script>alert('xss')</script>"),
        ("特殊Unicode", "🎉🐱‍👓 红豆喵~ 🎉"),
        ("极简提问", "？"),
    ]

    robust_scores = []
    for label, msg in edge_cases:
        r = send_msg(token, msg, timeout=30)
        # 鲁棒性评分：不崩溃=60分，有合理回复=+40分
        score = 60 if r["ok"] else 0
        if r["ok"] and len(r.get("content", "")) > 5:
            score += 40
        robust_scores.append(score)

        status = "STABLE" if r["ok"] else "CRASH"
        print(f"  [{status}] {label} | 得分={score}/100 | "
              f"response={'OK('+str(len(r.get('content','')))+'字)' if r['ok'] else r['error'][:60]}")

    avg = sum(robust_scores) / len(robust_scores) if robust_scores else 0
    print(f"\n>>> T5 鲁棒性得分: {avg:.1f}/100")
    print()

    return avg, robust_scores


# ============================================================
# T6: SSE 流式输出格式验证
# ============================================================

def test_sse_format(token):
    """SSE 事件流格式完整性验证"""
    print("=" * 70)
    print("T6: SSE 流式输出格式验证")
    print("=" * 70)

    r = send_msg(token, "你好，测试SSE格式")
    events = r.get("events", [])

    # 检查必需事件类型
    event_types = [e.get("_event", "") for e in events]
    has_message = "message" in event_types
    has_done = "done" in event_types
    has_switch = "agent_switch" in event_types

    # 检查 message 事件的 JSON 结构
    msg_events = [e for e in events if e.get("_event") == "message"]
    valid_json = all(
        "content" in e and isinstance(e["content"], str)
        for e in msg_events
    )

    # 检查 done 事件
    done_events = [e for e in events if e.get("_event") == "done"]
    valid_done = len(done_events) > 0

    format_checks = {
        "包含 message 事件": has_message,
        "包含 done 事件": has_done,
        "包含 agent_switch 事件": has_switch,
        "message 事件含 content 字段": valid_json,
        "done 事件存在": valid_done,
        "总事件数 >= 3": len(events) >= 3,
    }

    sse_score = sum(format_checks.values()) / len(format_checks) * 100
    print(f"  总事件数: {len(events)}")
    print(f"  事件类型分布: {dict((t, event_types.count(t)) for t in set(event_types))}")
    print()
    for check_name, passed in format_checks.items():
        print(f"  [{'PASS' if passed else 'FAIL'}] {check_name}")

    print(f"\n>>> T6 SSE 格式得分: {sse_score:.1f}/100")
    print()

    return sse_score, format_checks


# ============================================================
# T7: 综合评分 & 省一标准判定
# ============================================================

def generate_report(scores):
    """生成综合评测报告"""
    print()
    print("#" * 70)
    print("#  A3 学习系统 — 省一标准综合评测报告")
    print("#" * 70)
    print()

    intent_score, _ = scores.get("T2", (0, []))
    quality_score, _ = scores.get("T3", (0, []))
    context_score, _ = scores.get("T4", (0, []))
    robust_score, _ = scores.get("T5", (0, []))
    sse_score, _ = scores.get("T6", (0, []))

    weighted = (
        intent_score * 0.25 +   # 意图分类最重要
        quality_score * 0.25 +   # 回复质量
        context_score * 0.20 +   # 上下文连续
        robust_score * 0.15 +    # 鲁棒性
        sse_score * 0.15         # 技术规范
    )

    print(f"┌{'─'*56}┐")
    print(f"│ {'测试维度':<20} {'得分':>8} {'权重':>6} {'加权分':>8} │")
    print(f"├{'─'*56}┤")
    print(f"│ {'T2 意图分类准确性':<20} {intent_score:>7.1f} {'25%':>6} {intent_score*0.25:>7.1f} │")
    print(f"│ {'T3 回复质量':<20} {quality_score:>7.1f} {'25%':>6} {quality_score*0.25:>7.1f} │")
    print(f"│ {'T4 上下文连续性':<20} {context_score:>7.1f} {'20%':>6} {context_score*0.20:>7.1f} │")
    print(f"│ {'T5 鲁棒性':<20} {robust_score:>7.1f} {'15%':>6} {robust_score*0.15:>7.1f} │")
    print(f"│ {'T6 SSE格式规范':<20} {sse_score:>7.1f} {'15%':>6} {sse_score*0.15:>7.1f} │")
    print(f"├{'─'*56}┤")
    print(f"│ {'综合得分':<20} {'':<8} {'':<6} {weighted:>7.1f} │")
    print(f"└{'─'*56}┘")
    print()

    # 省一标准判定
    if weighted >= 85:
        level = "省一 (优秀)"
        verdict = "达到省级一等奖标准！系统整体表现优秀。"
    elif weighted >= 75:
        level = "省二 (良好)"
        verdict = "接近省一标准，部分维度需要优化。"
    elif weighted >= 60:
        level = "省三 (合格)"
        verdict = "基本功能可用，距离省一仍有较大差距。"
    else:
        level = "未达标"
        verdict = "存在较多问题，需要重点修复后再评。"

    print(f"  评定等级: ★★★ {level} ★★★")
    print(f"  综合评价: {verdict}")
    print()

    # 改进建议
    print("  ── 改进建议 ──")
    if intent_score < 90:
        print("  • 意图分类: 优化 LLM prompt 或增加更多关键词规则")
    if quality_score < 70:
        print("  • 回复质量: 检查 API 配额、优化各 Agent 的 system prompt")
    if context_score < 60:
        print("  • 上下文: 增强 _build_llm_messages 的历史窗口或 prompt 引导")
    if robust_score < 80:
        print("  • 鲁棒性: 加强输入校验、添加默认降级回复")
    if sse_score < 90:
        print("  • SSE格式: 确保 event/done 事件完整发送")
    print()

    return weighted, level


# ============================================================
# 主流程
# ============================================================

if __name__ == "__main__":
    print("A3 学习系统 全流程深度测试")
    print("测试时间:", time.strftime("%Y-%m-%d %H:%M:%S"))
    print()

    # 注册测试用户
    token, uname = new_user()
    print(f"测试用户: {uname}")
    print(f"Token: {token[:20]}...")
    print()

    scores = {}

    # T2: 意图分类
    scores["T2"] = test_intent_classification(token)

    # T3: 回复质量
    scores["T3"] = test_response_quality(token)

    # T4: 上下文连续性
    scores["T4"] = test_context_continuity(token)

    # T5: 鲁棒性
    scores["T5"] = test_robustness(token)

    # T6: SSE 格式
    scores["T6"] = test_sse_format(token)

    # T7: 综合报告
    generate_report(scores)
