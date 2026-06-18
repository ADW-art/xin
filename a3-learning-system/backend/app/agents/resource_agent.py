"""
Resource Agent — 根据用户画像 + 当前知识点生成个性化学习资源

资源类型：
1. document      → 结构化知识文档
2. mindmap       → Markdown 标题层级（前端 markmap 渲染为导图）
3. question_set  → 3-5 道练习题，含答案解析
4. code_example  → 可执行代码案例
5. video_script  → 5 分钟讲解脚本
"""

import json
import logging
import re

from app.agents.state import AgentState
from app.services.rag_service import retrieve_context, hybrid_search
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)

#英文key转化为中文
TYPE_LABELS = {
    "document": "知识文档",
    "mindmap": "思维导图",
    "question_set": "练习题",
    "code_example": "代码案例",
    "video_script": "讲解脚本",
    "comparison": "对比分析",
}
#核心prompt模板
RESOURCE_PROMPT = """你是一个个性化学习资源生成专家，风格对标 Khan Academy + LeetCode 官方题解。

## 核心铁律（违反即为不合格输出）
1. **不写维基百科式空洞定义** — 每个概念必须配代码示例+运行结果
2. **不写"XXX很有用"** — 必须说出具体在哪里用、怎么用、什么时候不该用
3. **不写"顾名思义"** — 不要把读者当傻子，用代码和例子说清楚
4. **不写"试着自己练习"** — 给具体题目描述、输入输出要求、难度标签
5. **不跳过运行结果** — 每个代码块后面必须紧接一个 ``` 展示实际输出
6. **全文至少3个代码块** — 少于3个即为不合格，每个至少有运行结果

## 学生画像
{profile_text}

## 当前学习需求
{topic}

## 要生成的资源类型：{type_label}
{type_guide}

{references}{rag_rule}

## 教程结构（每份文档必须完整包含，缺一不可）

### 第1部分：概述
- 用1-2句话精准定义概念，说明它解决什么问题
- 正确示范：「装饰器让你在不修改原函数的情况下，给函数添加额外行为（日志、计时、权限检查）」
- 错误示范：「装饰器是Python中一种重要的设计模式」（没说为什么重要、怎么用）
- 禁止："XXX是一种特殊的..."（这种定义等于没定义）

### 第2部分：核心概念
- 将主题拆解为2-4个核心子概念
- **每个子概念配一个代码示例**
- 格式：子概念名称 → 一句话说明 → 代码块 → 运行结果 → 1句话解释
- 代码块必须使用 ```语言 语法标注（```python, ```javascript, ```cpp, ```java 等）

### 第3部分：代码实战
- 一个完整的综合示例，展示多个核心概念如何组合使用
- 包含文件头注释说明目的和运行环境
- 关键行必须加行内注释解释为什么这样写（不是重复代码内容）
- **运行结果**紧跟代码块，用 ``` 代码块展示实际输出（不是描述输出）

### 第4部分：常见陷阱
- 至少列出2个真实常见错误
- 每个陷阱严格格式：
  **陷阱名称**：一句话说清楚坑在哪
  ```语言
  # 错误写法
  ```
  **为什么错**：1句话解释原因
  ```语言
  # 正确写法
  ```
  **运行结果**：展示正确写法的输出

### 第5部分：练习
- 至少2道具体题目
- 每道题格式：
  **题目N**（难度：简单/中等/较难，考察：[知识点列表]）
  [具体题目描述 - 包含输入输出要求、约束条件]
- 禁止："尝试修改上面的代码"（太模糊）
- 禁止："试着实现一个XXX"（没有约束条件等于没出）

### 第6部分：下一步
- 推荐1个具体的下一步学习知识点
- 说明为什么它是自然的下一步（如"装饰器掌握后，可以学习带参数的装饰器和类装饰器，它们需要闭包基础"）

## 内容质量标准
{difficulty_rule}

## 编程语言与约束（系统内部指令，不要输出给用户）
- 必须使用对话历史中用户指定的编程语言（C++→C++，Java→Java，JavaScript→JavaScript，Python→Python）
- 即使本轮消息未明确提及语言，也要沿用对话历史中已确立的语言
- 如果对话历史中有排除约束（"不要递归""不用算法""只用基础语法""不要第三方库"），必须严格遵守
- 代码必须能直接复制运行，不含占位符（# TODO / pass / ...）

## 回复格式
- 返回纯 Markdown，不要套 ```markdown 外壳
- 正文结束后，用 > 引用格式加一句自然的追问引导，只加一句：
  - 教完概念后：「这个概念清楚了吗？要不要我出两道题帮你巩固一下？」
  - 生成代码后：「代码可以直接跑，需要我逐行讲解关键部分吗？」
  - 完成教程后：「接下来想学 XX 的进阶用法，还是换一个主题？」

---

## ⚠️ 强制检查清单（你的回复必须包含以下每一项，缺一不可）
- [ ] ### 概述（精准定义，禁止维基百科式表述）
- [ ] ### 核心概念（至少2个，每个配代码块+运行结果）
- [ ] ### 代码实战（完整综合示例，注释说明设计决策）
- [ ] ### 常见陷阱（至少2个，错误示例→为什么错→正确做法）
- [ ] ### 练习（至少2道具体题目，有难度标注和知识点列表）
- [ ] ### 下一步（推荐1个具体知识点+原因）
- [ ] 至少3个 ```语言 代码块
- [ ] 每个代码块紧接运行结果

如果你遗漏任何一个部分，这个回复就是不合格的。"""

TYPE_GUIDES = {
    "document": """生成一份完整的教程文档，必须严格包含以下6个部分：

## [概念名称]

### 概述
1-2句话精准定义，说明概念解决什么问题、什么时候该用、什么时候不该用。
禁止：维基百科式定义（"XXX是一种特殊的..."）。必须具体。

### 核心概念
- 将主题拆解为2-4个核心子概念
- 每个子概念配独立代码示例：代码块 → 运行结果 → 一句话解释
- 至少3个 ```语言 代码块，每个跟运行结果

### 代码实战
- 一个完整的综合示例，把多个核心概念串起来
- 包含头注释（说明目的、运行环境、输入输出）
- 关键行加注释解释设计决策（不是重复代码内容）
- 运行结果紧跟代码块

### 常见陷阱
至少2个真实易错点，每个格式：
1. **陷阱名称**: 错误示例 → 为什么错 → 正确写法（用对比代码块）

### 练习
至少2道具体题目，每道包含：
- 题目描述（明确输入/输出/约束）
- 难度标签：[简单/中等/较难]
- 考察知识点列表

### 下一步
推荐一个具体的下一步知识点，说明为什么是自然延续""",

    "mindmap": """生成 Markdown 标题层级结构（前端 markmap 渲染为思维导图）。

严格格式要求：
- # 根节点 = 主题名（必须包含具体技术术语，如「Python装饰器体系」不是「装饰器」）
- ## 核心分类（如「基础机制」「核心应用」「高级模式」「常见误区」）
- ### 具体知识点（如「@语法糖本质」「闭包捕获自由变量」）
- #### 细节/示例（如「示例：@timer 计时装饰器」「示例：@retry 重试机制」）

节点要求：15-30个，每个节点标签必须是具体技术术语。
禁止使用模糊标签：禁止「其他」「更多」「等等」「扩展」「进阶」（用具体术语替代）
节点命名示范：禁止「基础知识」→ 允许「变量作用域与闭包」；禁止「常见问题」→ 允许「循环引用与内存泄漏」

建议：### 和 #### 节点附带括号注明语言/框架，如「@wraps保留元信息 (Python)」""",

    "question_set": """生成 3-5 道精心设计的练习题，每道题必须包含以下完整字段：

每道题格式模板：
```
### 第 N 题 — [选择题/代码阅读/代码编写] — 难度：[简单/中等/较难] — 预计 [2-10] 分钟

**考察知识点**：[知识点1, 知识点2, 知识点3]

[题目正文]
- 选择题：必须列出 A/B/C/D 四个完整选项，每个选项有具体技术内容
- 代码阅读题：给出完整代码，问输出什么
- 代码编写题：给函数签名 + 输入输出示例 + 约束条件

> **答案**：[正确答案或完整代码]
> **解析**：逐选项/逐行解释对错 + 标注易错点
```

题型分布：至少1道代码阅读题 + 至少1道代码编写题
禁止：死记硬背题（"以下哪个是XXX的定义"）、选项含臆造概念、无输入输出示例的代码题""",

    "code_example": """生成一个完整的、可直接运行的代码文件。

必须包含：
1. 文件头注释块：代码目的、语言版本要求、依赖（标注"仅标准库"或列出第三方库）、输入输出说明
2. 清晰的代码结构：导入 → 配置/常量 → 核心函数（带 docstring）→ main 入口 → `if __name__ == '__main__'`
3. 关键决策点注释：解释算法选择、数据结构选择、边界处理（注释要解释"为什么"而不是"是什么"）
4. 运行结果：代码块后必须紧跟一个 ``` 代码块展示完整输出
5. 算法复杂度：如涉及算法，在文件头注释中标注时间/空间复杂度
6. 错误处理：不忽略异常，给出合理的错误提示

格式模板：
```python
# ============================================================
# 功能：XXX
# 语言：Python 3.9+
# 依赖：标准库（无第三方依赖）
# 时间复杂度：O(n log n)  空间复杂度：O(n)
# ============================================================
# ... 完整代码 ...
```

绝对禁止：
- 占位符：# TODO / pass / ... / 此处省略
- 不完整的导入语句
- 有代码无输出结果
- 代码不能直接运行（缺少 import、变量未定义等）""",

    "video_script": """【已弃用】video_script 类型不再生成。

原因：描述性脚本过于模糊，无法提供可验证的学习效果。已替换为「互动式教程」格式：
以对话式讲解 + 可执行代码示例穿插的形式呈现内容。每个关键点配一个代码示例和思考问题。

如果你被路由到这里，请改为生成 document 类型的教程，并遵循 document 的完整6部分结构。
video_script 统一降级为 document。""",

    "comparison": """生成对比分析文档，严格按以下格式：

1. **表格对比**（至少 4 列 × 3 行，用 Markdown 表格）：
   | 对比维度 | 方案A | 方案B | 选型建议 |
   维度包括但不限于：性能、内存、可读性、适用场景、社区生态

2. **每项差异配最小代码示例**（不超过 8 行）：
   - 方案A 典型写法
   - 方案B 典型写法
   - 同一场景下的对比（输入相同、输出相同）

3. **选型决策树**：
   - 用条件判断句式给出明确建议
   - 格式：「如果 XXX，选择 A；如果 YYY，选择 B」
   - 禁止：「各有优劣」（等于没说）

4. **总结表**：一行总结什么时候用什么""",
}


def _normalize_title(raw: str) -> str:
    """Extract a clean display title from user-message-like topics.

    Strips prefixes (e.g. "教我"/"帮我"/"解释一下") and suffixes
    (e.g. "是什么"/"怎么用") and removes code-added annotations.

    Examples:
        "教我Python闭包"            → "Python闭包"
        "给我讲一下C++指针（使用C++语言）" → "C++指针"
        "解释一下什么是链表"          → "链表"
        "帮我写一下排序算法的代码"     → "排序算法"
    """
    if not raw or len(raw) < 2:
        return raw

    text = raw.strip()

    # Remove code-added annotations: （使用XXX语言）, （排除：XXX）
    text = re.sub(r'[（(][^）)]*[）)]', '', text).strip()

    # ── Strip common user-message prefixes ──
    text = re.sub(
        r'^(?:教|给|帮|请)(?:我|你|您)?(?:讲|解释|介绍|讲解|说明|告诉|教|学|写)?(?:一下|下)?(?:关于|这个|那个)?',
        '', text
    ).strip()
    text = re.sub(
        r'^(?:我想?|我要|帮我|给我|请你?|麻烦)(?:学|了解|知道|看看|理解|掌握|做|写)?(?:一下|下)?(?:关于|这个|那个)?',
        '', text
    ).strip()
    text = re.sub(
        r'^(?:什么(?:是|叫)|怎么(?:用|学|做|写|理解)|如何(?:用|学|做|写|理解))',
        '', text
    ).strip()
    text = re.sub(
        r'^(?:能否|可以|能|能不能|可不可以)(?:给我|帮我|为我)?(?:讲|解释|介绍|讲解)?(?:一下|下)?(?:关于|这个|那个)?',
        '', text
    ).strip()

    # ── Strip common user-message suffixes ──
    text = re.sub(
        r'(?:是什么|啥意思|什么意思|怎么用|如何用|怎么做|怎么学|怎么实现|如何实现|如何理解|怎么理解|怎么弄)\s*$',
        '', text
    ).strip()
    text = re.sub(
        r'(?:一下|一下你|吧|吗|呢|啊|哦|呀|嘛|呗)\s*$',
        '', text
    ).strip()
    text = re.sub(
        r'(?:的(?:原理|概念|用法|语法|写法|实现|例子|案例|实例|区别|联系|关系|代码))\s*$',
        '', text
    ).strip()

    return text if len(text) >= 2 else raw


def resource_agent_node(state: AgentState, spark: SparkClient) -> dict:
    """资源生成 Agent 的主逻辑 — 含教学流程感知"""
    state = dict(state)  # TypedDict → dict
    profile = state.get("user_profile") or {}
    context = state.get("context", {})
    topic = context.get("topic", state["messages"][-1].content if state["messages"] else "")

    # 教学流程感知：获取当前节点和下一节点信息
    teaching_context = state.get("teaching_context") or {}
    is_teaching = teaching_context.get("mode") == "teaching"
    teaching_next_node: str = ""
    if is_teaching:
        active_path = teaching_context.get("active_path", [])
        current_idx = teaching_context.get("current_index", 0)
        if current_idx + 1 < len(active_path):
            teaching_next_node = active_path[current_idx + 1]

    # 读取话题上下文（用户语言偏好 + 排除约束）
    topic_ctx = context.get("topic_context", {})
    user_lang = topic_ctx.get("user_language", "")
    user_constraints = topic_ctx.get("user_constraints", [])

    # 如果用户指定了语言，在主题中标注
    if user_lang:
        topic = f"{topic}（使用{user_lang}语言）"
    if user_constraints:
        exclude_text = "、".join(user_constraints)
        topic = f"{topic}（排除：{exclude_text}）"

    # 从画像中提取关键信息 → 拼进 Prompt
    profile_lines = [] #只拼接有值的
    if profile.get("knowledge_base"):
        profile_lines.append(f"知识基础：{profile['knowledge_base']}")
    if profile.get("cognitive_style"):
        profile_lines.append(f"认知风格：{profile['cognitive_style']}")
    if profile.get("learning_goal"):
        profile_lines.append(f"学习目标：{profile['learning_goal']}")
    if profile.get("preferred_resource_type"):
        profile_lines.append(f"偏好资源类型：{profile['preferred_resource_type']}")

    profile_text = "\n".join(profile_lines) if profile_lines else "暂无画像信息，按通用方式生成"
    #"\n".join-->把列表的每个元素用\n连接成一个字符串

    # RAG 检索：从知识库中查找与当前主题相关的教材片段
    # BGE 未就绪时跳过 RAG，直接 LLM 生成（避免首次请求超时）
    references = ""
    from app.services.rag_service import is_rag_ready
    if is_rag_ready():
        try:
            references = retrieve_context(topic, n=3)
            if references:
                logger.info("ResourceAgent: RAG 检索到参考资料（主题=%s）", topic)
        except Exception as e:
            logger.warning("ResourceAgent: RAG 检索失败: %s", e)
    else:
        logger.info("ResourceAgent: BGE 未就绪，跳过 RAG 检索 (纯 LLM 生成)")

    # Content Store 降级：轻量教材库作为备选知识注入（不依赖 BGE 模型）
    if not references:
        try:
            from app.services.content_store import search_content, is_content_ready, load_content_store
            load_content_store()  # 惰性初始化（已加载则直接返回）
            if is_content_ready():
                store_results = search_content(topic, top_k=3)
                if store_results:
                    references = "\n\n".join(
                        f"[教材：《{r['title']}》] {r['content'][:200]}"
                        for r in store_results[:2]
                    )
                    logger.info("ResourceAgent: 教材库检索到 %d 条参考资料（主题=%s）", len(store_results), topic)
        except Exception:
            pass  # 教材库不可用时静默跳过，不影响主流程

    # 根据画像偏好决定资源类型，默认生成文档
    # 但用户显式请求优先（如"生成思维导图"→mindmap）
    pref = profile.get("preferred_resource_type", "text")
    pref_map = {"video": "document", "code": "code_example", "text": "document", "interactive": "question_set"}
    resource_type = pref_map.get(pref, "document")

    # 用户显式资源类型请求覆盖画像偏好
    user_msg = state["messages"][-1].content if state["messages"] else ""
    override_map = {
        "思维导图": "mindmap", "脑图": "mindmap", "导图": "mindmap", "mindmap": "mindmap",
        "代码": "code_example", "编程": "code_example", "code": "code_example",
        "题目": "question_set", "题": "question_set", "练习": "question_set", "考题": "question_set",
        "视频": "document", "脚本": "document", "讲解视频": "document",
        "文档": "document", "文章": "document", "教程": "document", "笔记": "document",
        "对比": "comparison", "比较": "comparison", "区别": "comparison", "差异": "comparison",
    }
    for keyword, rtype in override_map.items():
        if keyword in user_msg:
            resource_type = rtype
            logger.info("ResourceAgent: 用户显式请求类型=%s (关键词=%s)", rtype, keyword)
            break

    type_label = TYPE_LABELS.get(resource_type, "学习资源")

    # ── 标题规范化：清理用户消息式的话题 ──
    clean_title = _normalize_title(topic)
    if clean_title != topic:
        logger.info("ResourceAgent: 标题规范化 '%s' → '%s'", topic, clean_title)

    # ── 类型指南动态增强 ──
    type_guide = TYPE_GUIDES[resource_type]

    # 数据结构/算法主题 → 要求输出 ASCII 可视化
    _ds_algo_keywords = [
        "链表", "栈", "队列", "树", "图", "堆", "哈希", "排序", "查找", "搜索",
        "二叉树", "红黑树", "B树", "B+树", "AVL", "Trie", "跳表", "并查集",
        "linked list", "stack", "queue", "tree", "graph", "heap", "hash",
        "sort", "search", "binary tree", "linkedlist", "双指针", "滑动窗口",
        "递归", "回溯", "动态规划", "贪心", "分治", "前缀和", "单调栈", "单调队列",
        "反转链表", "合并", "环检测",
    ]
    if any(kw in topic.lower() for kw in _ds_algo_keywords):
        type_guide += (
            "\n\n**ASCII 可视化要求**：请用 ASCII 字符画来辅助说明数据结构或算法流程。"
            "例如用箭头(→ ← ↑ ↓)、分隔线(┌ ─ ┐ │ └ ┘)、方向指示符"
            "来绘制内存布局、指针变化或算法步骤。至少包含 1 个 ASCII 示意图。"
        )

    # 难度适配规则：根据画像中的知识基础自动调整
    kb_data = profile.get("knowledge_base", {})
    if isinstance(kb_data, dict) and kb_data:
        avg_score = sum(v for v in kb_data.values() if isinstance(v, (int, float))) / max(len(kb_data), 1)
        if avg_score >= 7:
            difficulty_rule = "学生水平较高（自评均分 {:.0f}/10），减少基础解释，增加进阶内容和高级用法。代码示例可以直接展示最佳实践，不必从零讲起。".format(avg_score)
        elif avg_score >= 4:
            difficulty_rule = "学生处于中等水平（自评均分 {:.0f}/10），保持基础概念讲解，但可以适度引入进阶话题。代码示例要有适当注释。".format(avg_score)
        else:
            difficulty_rule = "学生处于入门阶段（自评均分 {:.0f}/10），每个概念要从最基础讲起，代码注释要详尽，多用类比辅助理解，避免跳步。".format(avg_score)
    else:
        difficulty_rule = "学生画像中无知识基础数据，按入门水平讲解：每个概念从基础讲起，代码注释详尽，多用类比辅助理解。"

    # 构建系统提示词（含画像+RAG上下文）
    resource_system = RESOURCE_PROMPT.format(
        profile_text=profile_text,
        topic=topic,
        type_label=type_label,
        type_guide=type_guide,
        references=f"\n## 参考教材\n{references}\n" if references else "",
        rag_rule="\n你必须严格遵守以下规则：\n1. 优先使用参考教材中的知识点组织内容\n2. 如果参考资料中有相关内容，可以直接引用并标注来源\n3. 不要编造教材中没有的概念、函数名或代码示例\n4. 如果教材内容与学生画像冲突，以教材为准" if references else "",
        difficulty_rule=difficulty_rule,
    )

    # 教学流程提示注入：告知 LLM 当前教学进度并引导下一节点
    if is_teaching:
        tc = teaching_context
        current_idx = tc.get("current_index", 0)
        total_nodes = len(tc.get("active_path", []))
        current_node = tc.get("active_path", [topic])[current_idx] if tc.get("active_path") else topic
        resource_system += (
            f"\n\n## 教学流程上下文（系统指令，不要原样输出）\n"
            f"你正在按照知识图谱教学路径授课，当前是第 {current_idx + 1}/{total_nodes} 个节点。\n"
            f"当前教学节点：「{current_node}」\n"
        )
        if teaching_next_node:
            resource_system += (
                f"下一节点：「{teaching_next_node}」\n"
                f"教学完成后，请在「下一步」中明确引导用户继续下一节点。"
                f"引导文案示例：「> 学得不错！接下来要学的是「{teaching_next_node}」，要继续吗？」\n"
                f"注意：用 > 引用格式引导，只加1句，不要添加其他追问。"
            )
        else:
            resource_system += (
                "这是最后一个节点。教学完成后，请祝贺用户完成学习路径，并推荐做一次评估测试。"
            )
        resource_system += (
            f"\n已完成节点（{len(tc.get('completed_nodes', []))}/{total_nodes - 1}）："
            f"{', '.join(tc.get('completed_nodes', [])[-5:]) or '(尚无)'}"
        )

    # 携带对话历史上下文，确保多轮对话中代词语义连贯、约束条件跨轮传递
    from app.core.shared_utils import _build_llm_messages
    all_msgs = state.get("messages", [])
    last_user_msg = state["messages"][-1].content if state["messages"] else topic
    messages = _build_llm_messages(
        resource_system,
        all_msgs,
        last_user_msg,
        max_history=6,
        topic_context=topic_ctx,
    )

    logger.info("ResourceAgent: 准备生成 %s（主题=%s, RAG=%s, 教学流程=%s）", resource_type, topic, "启用" if references else "降级", "是" if is_teaching else "否")

    # 构建 resource_agent 输出元数据（含教学流程信息）
    resource_output: dict = {
        "type": resource_type,
        "topic": topic,
        "title": clean_title,
        "stream_pending": {
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 2048,
            "use_safe": True,
            "chunk_size": 2,
        },
    }

    if is_teaching:
        current_idx = teaching_context.get("current_index", 0)
        total_nodes = len(teaching_context.get("active_path", []))
        resource_output["teaching_stage"] = "node_complete"
        resource_output["current_index"] = current_idx
        resource_output["total_nodes"] = total_nodes
        if teaching_next_node:
            resource_output["next_node"] = teaching_next_node
            logger.info("ResourceAgent: 教学节点完成 %d/%d → 下一节点: %s",
                         current_idx + 1, total_nodes, teaching_next_node)
        else:
            resource_output["next_node"] = None
            logger.info("ResourceAgent: 教学最后一个节点完成 %d/%d", current_idx + 1, total_nodes)

    # 统一走 stream_pending 流式管线：Agent 只准备 messages，不自行调用 LLM
    # _bridge_stream 在 chat.py 中负责 true streaming（逐 chunk yield）
    return {
        "current_agent": "resource_agent",
        "stream_buffer": "",
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "resource_agent": resource_output,
        },
    }
