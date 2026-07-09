"""T3 质量诊断 v2：只检测学科知识点内容"""
import requests, random, string, json, time, re

s = requests.Session()
s.trust_env = False
BASE = 'http://localhost:8001'

uname = 'qdiag_' + ''.join(random.choices(string.ascii_lowercase, k=8))
r = s.post(f'{BASE}/api/auth/register', json={'username': uname, 'password': 'Test123456'})
token = r.json().get('access_token', '')
h = {'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}

# 知识点级别关键词（每个都检测具体学科内容）
tests = [
    ("chat-问候", "你好", "chat",
     ["帮助"], []),
    ("chat-闲聊", "你喜欢什么编程语言", "chat",
     ["python|java|c\\+\\+|go|javascript|rust"], []),
    # evaluation: 必须提到具体知识领域或量化分析
    ("evaluation-评估", "评估一下我的学习情况", "evaluation",
     ["python|数据结构|算法|数据库|前端|后端|机器学习|web开发",   # 具体知识领域
      "函数|列表|字典|类|循环|递归|排序|树|图|数组|字符串",       # 具体知识点
      "优势|不足|强项|弱项|擅长|欠缺",                            # 有针对性分析
      "\\d+%|\\d+/10|\\d+分|程度|水平"],                         # 量化指标
     ["错误", "失败"]),
    # question: 题目必须包含真实的编程概念
    ("question-出题", "出3道Python基础题", "question",
     ["变量|参数|返回值|函数|def ",                               # 函数概念
      "列表|字典|元组|集合|字符串|整数|浮点",                      # 数据类型
      "for |while |if |else |循环|条件|判断",                     # 控制流
      "\\[\\]|\\(\\)|\\{\\}|\\.append|\\.get|len\\(|print\\(",   # 实际代码符号
      "选择|填空|编写|实现|计算|输出|输入",                        # 题目动作
      "第\\d+题|题目|答案|解析"],                                  # 题目结构
     ["错误", "无法"]),
    # resource: 教学必须包含目标概念的代码和讲解
    ("resource-教学", "教我Python列表推导式", "resource",
     ["列表", "推导式|推导",
      "\\[.*for .*in .*\\]|\\[.*for.*in.*\\]",                   # 列表推导式代码
      "表达式|迭代|元素|生成|新列表|映射|过滤",                    # 核心概念
      "例子|示例|例如|比如",
      "语法|写法|格式|结构"],
     ["错误", "无法"]),
    # path: 规划必须包含具体可学的技术主题
    ("path-规划", "我下一步该学什么", "path",
     ["python|数据结构|算法|数据库|web|框架|项目|django|flask",   # 具体技术栈
      "基础|进阶|高级|实战|入门",                                   # 学习层级
      "变量|函数|类|模块|包|api|接口|面向对象",                     # 具体知识点
      "周|天|小时|月|阶段|步骤",                                    # 时间/阶段
      "复习|练习|项目|实战|作业"],
     ["错误", "无法"]),
    # profile: 采集用户背景信息
    ("profile-画像", "我想学Python数据分析", "profile",
     ["基础|水平|经验|学过|了解|掌握|背景",
      "目标|方向|求职|工作|兴趣|打算",
      "时间|每天|每周|投入|多少",
      "告诉|说说|简单|介绍一下|请问"],
     ["错误", "失败"]),
]

print("=" * 70)
print("T3 知识点提取质量诊断")
print("=" * 70)

for label, msg, expected, pos_kw, neg_kw in tests:
    resp = s.post(f'{BASE}/api/chat/send', headers=h, json={'content': msg}, timeout=60, stream=True)
    agent = ''
    parts = []
    for line in resp.iter_lines():
        if not line:
            continue
        try:
            text = line.decode('utf-8')
        except:
            text = line.decode('latin-1')
        if text.startswith('data: '):
            try:
                d = json.loads(text[6:])
                if 'agent' in d:
                    agent = d['agent']
                if 'content' in d:
                    parts.append(d['content'])
            except:
                pass

    content = ''.join(parts)

    # 正则/OR关键词匹配
    pos_hits = 0
    hit_details = []
    for kw in pos_kw:
        is_regex = ('\\' in kw or '|' in kw or
                    re.search(r'[.+*?\[\](){}|^$].*[.+*?\[\](){}|^$]', kw) or
                    kw.startswith('^') or kw.endswith('$'))
        matched = False
        if is_regex:
            try:
                m = re.search(kw, content, re.IGNORECASE)
                if m:
                    matched = True
                    hit_details.append(f'  [RE] "{kw}" -> "{m.group()[:50]}"')
            except:
                pass
        else:
            if kw.lower() in content.lower():
                matched = True
                idx = content.lower().index(kw.lower())
                ctx = content[max(0,idx-10):idx+len(kw)+10].replace('\n',' ')
                hit_details.append(f'  [KW] "{kw}" -> "...{ctx}..."')
        if matched:
            pos_hits += 1

    neg_hits = sum(1 for kw in neg_kw if kw.lower() in content.lower())
    length_score = min(100, len(content) / 2)
    quality = (pos_hits / max(len(pos_kw), 1) * 50 +
               max(0, 30 - neg_hits * 15) +
               min(20, length_score / 5))
    quality = min(100, max(0, quality))

    grade = "A" if quality >= 80 else "B" if quality >= 60 else "C" if quality >= 40 else "D"
    print(f'\n{"="*60}')
    print(f'[{grade}] {label} | 质量={quality:.0f}/100 | 字数={len(content)} | agent={agent}')
    print(f'  知识点命中: {pos_hits}/{len(pos_kw)} (负向:{neg_hits})')
    if hit_details:
        print(f'  命中的知识点:')
        for hd in hit_details:
            print(hd)
    else:
        print(f'  未命中任何知识点!')
    print(f'  内容预览:\n{content[:400]}')
    if len(content) > 400:
        print(f'  ...({len(content)-400}字省略)')
    time.sleep(0.3)

print(f'\n{"="*60}')
print('诊断完成!')
