"""
Evaluation Agent — 学习效果评估

根据学生的答题记录和行为数据，生成多维度评估报告。
- 6 维评估：知识掌握/学习速度/薄弱环节/进步趋势/投入度/推荐策略
- 生成文本评估 + 建议
"""

import logging

from app.agents.state import AgentState
from app.agents._msg_compat import last_msg_content  # 兼容 checkpoint 恢复后 dict 格式
from app.services.spark_client import SparkClient
from app.services.bkt_service import get_tracker

logger = logging.getLogger(__name__)

EVALUATION_PROMPT = """你是一个学习效果评估专家，风格对标专业教研机构的学习诊断报告。根据学生的学习画像和BKT知识追踪数据，生成结构化的多维度评估报告。

## 核心铁律（违反即为不合格输出）
1. **禁止编造数据** — 所有数字（掌握率、知识点数量、进度百分比）必须来自下方提供的画像数据和BKT追踪数据，不得凭空生成
2. **禁止猜测掌握率** — 知识点掌握程度只能使用BKT数据中的 p_known 值，不得自行估计"大概掌握了80%"
3. **禁止横向对标** — 不得说"你的水平相当于大学二年级""达到中级工程师水平"等外部基准，除非画像数据中有明确的外部评测成绩
4. **禁止空洞鼓励** — 不得出现"加油""别灰心""你很棒""继续努力"等无信息量的鼓励语。鼓励必须基于具体进步数据（如"你的列表操作正确率从上周的45%提升到本周的72%，说明刻意练习起了作用"）
5. **禁止模糊评价** — 每个维度结论必须引用画像中的具体数字。禁止"你的基础知识还不错"（太模糊），必须说"你已掌握 X/Y 个知识点（掌握率 Z%），其中 [A]、[B]、[C] 最牢固(p>0.8)，[D]、[E]、[F] 最薄弱(p<0.4)"
6. **禁止跳过数据** — 若画像中某维度显示"未填写"，必须明确指出"该维度数据不足，建议补充"，不得跳过或用默认值填充

## 数据来源标注规则（必须遵守）
每个数据/结论必须用标签标注其来源：
- **[BKT算法]**：来自贝叶斯知识追踪的 p_known 值、掌握概率、正确率
- **[答题记录]**：来自answer_records表的统计数据
- **[用户自报]**：来自用户学习画像的自评数据
- **[AI分析]**：基于上述数据的推理分析（非原始数据）
- **[教材数据]**：来自知识库RAG检索的教材内容

示例：
- "已掌握 5/12 个知识点（掌握率 42%）[BKT算法]"
- "近7天共完成 15 道题 [答题记录]"
- "建议每天增加1道代码编写题 [AI分析]"

## 学生画像
{profile_summary}

## 输出模板（必须严格按此结构，缺一不可）

### 图解
- 基于BKT数据中的知识点掌握概率，生成一张 Mermaid 饼图，直观展示知识分布
- 饼图分三类：「已掌握」（p_known ≥ 0.85）、「学习中」（0.5 ≤ p_known < 0.85）、「未掌握」（p_known < 0.5）
```mermaid
pie title 知识点掌握分布
    "已掌握 (p≥0.85)" : X
    "学习中 (0.5≤p<0.85)" : Y
    "未掌握 (p<0.5)" : Z
```
- 饼图后紧跟1-2句数据解读（X/Y/Z 必须替换为BKT真实数据中的计数）

### 1. 知识掌握度
- 直接引用BKT数据：已掌握 X/Y 个知识点，总掌握率 Z%
- 列出掌握最牢固的3个知识点（名称 + p_known 值 + 强项原因简析）
- 列出掌握最薄弱的3个知识点（名称 + p_known 值 + 可能的卡点原因）
- **禁止**："不错""还行""一般" → **必须**："掌握率 X%，其中 A/B/C 最强(p值均>0.8)，D/E/F 最弱(p值均<0.4)"

### 2. 薄弱环节分析
- 逐一列出每个薄弱知识点，包含：知识点名称、当前掌握概率(p_known)、错误模式类型（概念混淆/边界遗漏/语法生疏/逻辑断层）
- 每个薄弱点必须给出量化改进方案
- **禁止**："多练习""多看资料""加强复习" → **必须**："针对[XX]类型每天做[N]道题（推荐[具体平台/题型]），重点练习[具体子技能]，预计[Y]周可将掌握率从[a]%提升到[b]%"

### 3. 学习风格适配
- 基于 cognitive_style 字段评估当前学习方式与认知风格的匹配度
- visual(视觉型) → 推荐思维导图/流程图/代码可视化工具
- kinesthetic(动手型) → 推荐动手编码练习/项目实战/交互式编程环境
- auditory(听觉型) → 推荐视频讲解/音频教程/口头复述
- reading(阅读型) → 推荐结构化文档/技术书籍/笔记整理
- **禁止**："当前学习方式比较合适""可以继续保持" → **必须**："你的认知风格是[X型]，但当前偏好资源类型是[Y]，存在不匹配（因为[具体原因]）。建议调整为[Z]，预计调整后学习效率可提升约[X]%"

### 4. 进度评估
- 基于 weekly_hours 与 BKT 已掌握知识点数，计算学习效率（知识点/周）
- 结合 learning_goal 预估还需掌握的知识点数及完成时间
- 如果BKT数据中有累计答题记录，结合正确率趋势（上升/持平/下降）评估学习效果
- **禁止**："进度正常""学得不错" → **必须**："你每周投入 X 小时，目前已掌握 Y 个知识点（平均 Z 知识点/周），按此速度，完成[学习目标]还需掌握 N 个知识点，预计需要 M 周"

### 5. 改进建议（2-3条，每条必须可执行）
格式：**建议N**（优先级：高/中）: [具体做法] — [预期效果] — [预计见效时间]
- **禁止**："加强学习""多做练习""巩固基础""多看视频" → **必须**："每天做2道[字符串处理]代码编写题（推荐牛客网入门题库），重点练习split/join的嵌套使用，预计2周内该类题目正确率可从55%提升到80%"

### 6. 下一步计划（未来3天具体安排）
- 每天格式：**第N天**：[知识点名称] — 预计X小时 — [学习资源类型] — 原因：[为什么选这个知识点]
- 说明为什么这些知识点是当前最优路径（关联薄弱环节 + 前置知识要求）

### 总结
- 2-3句话概括当前学习状态（含最关键的1个量化数据点）
- 1个核心行动建议（最重要的1件事）

---

## 难度适配规则（系统内部指令，不要输出给用户）
- BKT 总掌握率 ≥ 80%：聚焦薄弱点深度分析和进阶路线规划，减少基础概念解释
- BKT 总掌握率 40%-80%：兼顾知识巩固与薄弱补强，建议分配 60%时间补弱 + 40%时间进阶
- BKT 总掌握率 < 40%：以基础夯实为主，优先梳理知识体系骨架，避免推荐高级话题
- 无 BKT 数据时：报告中必须明确指出"当前答题数据不足，以下评估基于画像自评数据，建议完成至少10道测试题以获得更精准的BKT评估"

---

**主动引导（用 > 引用格式，仅选最相关的1条）**：
- 薄弱突出时：> 你的 [XX] 掌握率仅 [Y]%。需要我帮你系统讲解一遍，从基础概念开始吗？
- 进步明显时：> 你的 [XX] 正确率从 [A]% 提升到 [B]%，进步显著！要不要挑战更难的进阶题？
- 数据不足时：> 当前答题数据不够充分，建议先完成5-10道测试题。要我现在出题吗？
- 需调整时：> 当前学习节奏下预计还需 [X] 周完成目标。需要我帮你重新规划更紧凑的路线吗？

---

## ⚠️ 强制检查清单（少任何一项即为不合格输出）

**绝对禁止的做法（这些是不合格的输出）**：
- 没有 Mermaid 饼图 → 不合格
- 没有具体数字（掌握率%、p值、知识点名称）→ 不合格
- 出现空洞鼓励（"加油""别灰心""你很棒"）→ 不合格
- 出现模糊建议（"多练习""加强学习"）→ 不合格
- 跳过任何维度 → 不合格

**强制包含清单**：
1. ### 图解 — Mermaid 饼图（基于BKT掌握概率分三类）+ 1-2句数据解读
2. ### 1. 知识掌握度 — 具体掌握率% + 最强3知识点(含p值) + 最弱3知识点(含p值+卡点)
3. ### 2. 薄弱环节分析 — 每个薄弱点含：知识点名 + p_known值 + 错误模式类型 + 量化改进方案
4. ### 3. 学习风格适配 — cognitive_style匹配度评估 + 具体调整建议(含推荐资源类型)
5. ### 4. 进度评估 — 知识点/周效率 + 完成学习目标预估时间
6. ### 5. 改进建议 — 2-3条可执行方案(每条含：具体做法+预期效果+见效时间)
7. ### 6. 下一步计划 — 未来3天每天具体安排(知识点+小时数+资源类型+原因)
8. ### 总结 — 2-3句话概括 + 1个核心行动建议

每个部分都必须使用 ### 标题。**少任何一部分，这份输出就是废品。**

## 示例（标准报告模板）
以下是一个合格的评估报告示例：

### 图解
```mermaid
pie title 知识点掌握分布
    "已掌握 (p>=0.85)" : 3
    "学习中 (0.5<=p<0.85)" : 5
    "未掌握 (p<0.5)" : 7
```
当前已掌握 3/15 个知识点，5个处于学习中，7个尚未掌握。

### 1. 知识掌握度
已掌握 3/15 个知识点，总掌握率 20% [BKT算法]。最强: 变量与赋值(p=0.92), 条件判断(p=0.88), 循环基础(p=0.86)。最弱: 装饰器(p=0.18), 闭包(p=0.22), 协程(p=0.25)。

### 2. 薄弱环节分析
- 装饰器(p=0.18, 概念混淆) [BKT算法]: 学生对@语法糖和函数作为一等对象的理解不足。建议每天做2道装饰器专项练习(牛客网Python入门题库)，预计2周可将掌握率从18%提升到60%。
- 闭包(p=0.22, 逻辑断层): 变量捕获时机理解有误。建议先巩固"函数作用域"基础概念，再学习闭包。

### 3. 学习风格适配
认知风格为动手型(kinesthetic)，当前偏好资源为文档(text)，存在不匹配 [用户自报]。建议增加代码实操练习比例，将60%学习时间分配给动手编码 [AI分析]。

### 4. 进度评估
每周投入5小时 [用户自报]，已掌握3个知识点，平均0.6知识点/周。按此速度完成当前目标还需掌握12个知识点，预计需要20周 [AI分析]。

### 5. 改进建议
**建议1**(高): 每天做2道装饰器专项练习 → 预期正确率从20%提升到60% → 预计2周见效
**建议2**(中): 用VS Code交互式调试功能跟踪闭包变量 → 建立对变量捕获的直观理解 → 预计1周见效

### 6. 下一步计划
第1天: 装饰器基础(2h, 代码案例) — 当前最薄弱的概念
第2天: 闭包与作用域(2h, 知识文档) — 装饰器的前置知识
第3天: 装饰器进阶: 带参数的装饰器(2h, 代码案例) — 在掌握基础后自然进阶

### 总结
当前处于Python入门阶段，已掌握基本语法但函数高级特性薄弱。核心行动: 接下来2周集中攻克装饰器和闭包。"""


# v3: speed_score 计算缓存 (TTL 300s, 避免每次评估都查全表)
_speed_cache: dict[int, tuple[float, float]] = {}  # {user_id: (score, timestamp)}
_SPEED_CACHE_TTL = 300  # 5 分钟


def _compute_speed_score(user_id: int) -> int:
    """从 answer_records 计算日均答题量 → 映射到 0-100 分 (含缓存)"""
    import time as _t
    now = _t.time()
    if user_id in _speed_cache:
        score, ts = _speed_cache[user_id]
        if now - ts < _SPEED_CACHE_TTL:
            return int(score)

    try:
        from app.core.database import SessionLocal
        from app.models.answer_record import AnswerRecord
        db = SessionLocal()
        try:
            records = db.query(AnswerRecord).filter(
                AnswerRecord.user_id == user_id
            ).all()
            if records and len(records) >= 2:
                dates = sorted(set(r.created_at.date() for r in records if r.created_at))
                if len(dates) >= 1:
                    active_days = max((max(dates) - min(dates)).days + 1, 1)
                    q_per_day = len(records) / active_days
                    score = min(100, round(max(0, q_per_day) * 5))
                else:
                    score = 50
            else:
                score = 50
        finally:
            db.close()
    except Exception:
        score = 50
    _speed_cache[user_id] = (float(score), now)
    return int(score)


def evaluation_agent_node(state: AgentState, spark: SparkClient) -> dict:
    state = dict(state)  # TypedDict → dict
    profile = state.get("user_profile") or {}

    parts = [
        f"- 知识基础：{profile.get('knowledge_base', '未填写')}",
        f"- 认知风格：{profile.get('cognitive_style', '未填写')}",
        f"- 学习目标：{profile.get('learning_goal', '未填写')}",
        f"- 每周投入：{profile.get('weekly_hours', '未填写')} 小时",
        f"- 易错模式：{profile.get('error_patterns', '未填写')}",
        f"- 偏好资源：{profile.get('preferred_resource_type', '未填写')}",
    ]
    # 加入 BKT 知识追踪数据
    tracker = get_tracker(state.get("user_id", 0))
    bkt_data = tracker.to_dict()
    has_bkt = bool(bkt_data["nodes"])
    has_profile = bool(profile.get("knowledge_base"))
    if has_bkt:
        parts.append("\n## BKT 知识追踪数据（算法推算，非用户自评）")
        parts.append(f"- 已掌握知识点：{bkt_data['summary']['mastered']}/{bkt_data['summary']['total']}")
        parts.append(f"- 各知识点掌握概率：{bkt_data['nodes']}")
        parts.append(f"- 薄弱环节：{tracker.get_weak_points()}")

    # 守卫：BKT 无数据且画像为空 → 不调用 LLM，直接返回引导消息
    if not has_bkt and not has_profile:
        logger.info("EvaluationAgent: 无评估数据(BKT+画像均为空)，返回引导消息")
        return {
            "current_agent": "evaluation_agent",
            "stream_buffer": (
                "我目前还没有足够的数据来评估你的学习情况。\n\n"
                "要生成有意义的评估报告，系统需要了解：\n"
                "- 你的知识基础（可以通过对话告诉我，如\"我学过Python基础\"）\n"
                "- 答题记录（完成几道练习题后，BKT算法会追踪你的掌握度）\n\n"
                "> 你可以先描述一下你的学习背景，或者让我出几道题测试一下你的水平？"
            ),
            "agent_outputs": {
                **state.get("agent_outputs", {}),
                "evaluation_agent": {"insufficient_data": True},
            },
        }

    profile_summary = "\n".join(parts) #把列表的每个元素用分隔符连成字符串

    # ── 计算真实 dimension_scores（复用上方已获取的 BKT 数据） ──
    kb = profile.get("knowledge_base") or {}
    ds = profile.get("dimension_scores") or {}

    # 从 BKT 推算真实维度分
    mastered = bkt_data["summary"]["mastered"]
    total = bkt_data["summary"]["total"]
    knowledge_score = round((mastered / max(total, 1)) * 100)  # 知识掌握: BKT已掌握率

    # 学习速度：从 answer_records 按天统计该用户的日均答题量 → 映射到 0-100 分
    # 实践能力：从 BKT 累计数据计算正确率 → 映射到 0-100 分
    total_attempts = 0
    total_correct = 0
    for node in tracker.nodes.values():
        total_attempts += node.total_attempts
        total_correct += node.correct_count

    if total_attempts > 0:
        practice_score = round((total_correct / total_attempts) * 100)
    else:
        practice_score = 0  # 无答题记录时默认为 0

    # v3: 学习速度 — 统一函数 + 5分钟缓存 (避免每次评估查全表)
    speed_score = _compute_speed_score(state.get("user_id", 0))

    # v3: focus — 4因子加权: 近7天会话×20 + 日均在线×30 + 答题频率×25 + 复习完成×25
    try:
        from app.core.database import SessionLocal as _SessionLocal2
        from app.models.conversation import Conversation as _Conv
        from app.models.answer_record import AnswerRecord as _AnsRec
        from app.models.review_schedule import ReviewScheduleModel as _RevSch
        from datetime import datetime as _dt2, timedelta as _td2
        _db2 = _SessionLocal2()
        _now = _dt2.utcnow()
        _week_ago = _now - _td2(days=7)
        _uid = state.get("user_id", 0)
        try:
            # 因子1: 近7天会话天数 (权重20)
            _convs_7d = _db2.query(_Conv).filter(
                _Conv.user_id == _uid,
                _Conv.created_at >= _week_ago
            ).all()
            if _convs_7d:
                _conv_dates_7d = set(c.created_at.date() for c in _convs_7d if c.created_at)
                _recent_7d_sessions = min(1.0, len(_conv_dates_7d) / 7.0)
            else:
                _recent_7d_sessions = 0.0

            # 因子2: 日均在线时长 (权重30) — 从所有会话时间跨度估算
            _all_convs = _db2.query(_Conv).filter(_Conv.user_id == _uid).all()
            if _all_convs and len(_all_convs) >= 2:
                _all_dates = sorted(set(c.created_at.date() for c in _all_convs if c.created_at))
                _active_days = max((max(_all_dates) - min(_all_dates)).days + 1, 1)
                _daily_sessions = len(_all_convs) / max(_active_days, 1)
                _est_hours = min(_daily_sessions * 0.5, 4.0)
                _daily_online_hours = min(1.0, _est_hours / 2.0)
            else:
                _daily_online_hours = 0.0

            # 因子3: 答题频率 (权重25) — 近7天日均答题数
            _answers_7d = _db2.query(_AnsRec).filter(
                _AnsRec.user_id == _uid,
                _AnsRec.created_at >= _week_ago
            ).all()
            _ans_per_day = len(_answers_7d) / 7.0 if _answers_7d else 0.0
            _answer_freq = min(1.0, _ans_per_day / 3.0)

            # 因子4: 复习完成率 (权重25) — 已完成复习数 / 到期应复习数
            _reviews = _db2.query(_RevSch).filter(_RevSch.user_id == _uid).all()
            if _reviews:
                _intervals = [1, 3, 7, 14, 30, 90]
                _due = 0
                _completed = 0
                for _r in _reviews:
                    if _r.review_count > 0:
                        _completed += 1
                    if _r.last_reviewed:
                        _intv = _intervals[min(_r.interval_index, len(_intervals) - 1)]
                        if _r.last_reviewed + _td2(days=_intv) <= _now:
                            _due += 1
                    else:
                        _due += 1
                _review_completion = min(1.0, _completed / max(_due, 1))
            else:
                _review_completion = 0.0

            focus_score = round(
                _recent_7d_sessions * 20 + _daily_online_hours * 30 +
                _answer_freq * 25 + _review_completion * 25
            )
            focus_score = max(0, min(100, focus_score))
        finally:
            _db2.close()
    except Exception:
        focus_score = 50  # 数据库不可用时降级

    # v3: logic — BKT方差×40 + 跨领域迁移×35 + 代码调试×25
    if len(tracker.nodes) >= 2:
        # 因子1: BKT掌握度方差 (权重40) — 低方差=知识体系均衡=逻辑强
        p_values = [n.p_known for n in tracker.nodes.values()]
        mean_p = sum(p_values) / len(p_values)
        variance = sum((p - mean_p) ** 2 for p in p_values) / len(p_values)
        cv = (variance ** 0.5) / max(mean_p, 0.01)
        variance_score = (1.0 - min(cv, 0.5) * 2.0) * 40  # cv=0→40, cv≥0.5→0

        # 因子2: 跨领域迁移 (权重35) — 检查用户在不同KG领域均有答题且正确
        _domain_keywords = {
            "python": ["python", "django", "flask", "numpy", "pandas"],
            "cpp": ["c++", "cpp", "c语言"],
            "java": ["java", "spring"],
            "javascript": ["javascript", "js", "node", "vue", "react", "typescript"],
            "algorithm": ["算法", "数据结构", "排序", "搜索", "树", "图", "动态规划"],
            "database": ["数据库", "sql", "mysql", "postgresql"],
            "network": ["网络", "http", "tcp", "ip"],
        }
        _domain_stats = {}
        for name, node in tracker.nodes.items():
            name_lower = name.lower()
            _matched = False
            for _dom, _kws in _domain_keywords.items():
                if any(kw in name_lower for kw in _kws):
                    if _dom not in _domain_stats:
                        _domain_stats[_dom] = {"correct": 0, "total": 0}
                    _domain_stats[_dom]["correct"] += node.correct_count
                    _domain_stats[_dom]["total"] += node.total_attempts
                    _matched = True
            if not _matched:
                if "other" not in _domain_stats:
                    _domain_stats["other"] = {"correct": 0, "total": 0}
                _domain_stats["other"]["correct"] += node.correct_count
                _domain_stats["other"]["total"] += node.total_attempts

        _domains_with_data = {k: v for k, v in _domain_stats.items() if v["total"] > 0}
        if len(_domains_with_data) >= 2:
            _cross_correct = sum(d["correct"] for d in _domains_with_data.values())
            _cross_total = sum(d["total"] for d in _domains_with_data.values())
            cross_domain_score = min(1.0, _cross_correct / max(_cross_total, 1)) * 35
        else:
            cross_domain_score = 17.5

        # 因子3: 代码调试成功率 (权重25) — 涉及代码编写/调试类题目的正确率
        _code_kw = ["代码", "实现", "编写", "debug", "调试", "coding", "implement"]
        code_correct = 0
        code_total = 0
        try:
            from app.core.database import SessionLocal as _SLC
            from app.models.answer_record import AnswerRecord as _ARec
            _dbc = _SLC()
            try:
                _code_records = _dbc.query(_ARec).filter(
                    _ARec.user_id == state.get("user_id", 0),
                    _ARec.is_correct.isnot(None)
                ).all()
                for _r in _code_records:
                    _conc = str(_r.concept or "") + str(_r.user_answer or "")
                    if any(kw in _conc.lower() for kw in _code_kw):
                        code_total += 1
                        if _r.is_correct:
                            code_correct += 1
            finally:
                _dbc.close()
        except Exception:
            pass
        if code_total > 0:
            code_score = min(1.0, code_correct / code_total) * 25
        else:
            code_score = 0

        logic_score = round(variance_score + cross_domain_score + code_score)
    else:
        logic_score = 50

    # v3: overall — 覆盖全部 6 维
    # trend: 最近10次正确率 vs 总正确率 → 上升(>总)/持平(≈总)/下降(<总)
    if total_attempts >= 5 and tracker.nodes:
        recent_total = sum(len(n._recent_results) for n in tracker.nodes.values())
        recent_correct = sum(n.recent_correct for n in tracker.nodes.values())
        if recent_total >= 3:
            recent_rate = recent_correct / recent_total
            overall_rate = total_correct / max(total_attempts, 1)
            # trend = 基线50 + (最近率 - 总率)*100 → 50=持平, >50=上升, <50=下降
            trend_score = round(max(0, min(100, 50 + (recent_rate - overall_rate) * 100)))
        else:
            trend_score = round((total_correct / max(total_attempts, 1)) * 100)
    else:
        trend_score = 50 if total_attempts > 0 else 50
    overall_score = round(
        (knowledge_score * 0.25 + speed_score * 0.15 + practice_score * 0.20 +
         focus_score * 0.15 + logic_score * 0.15 + trend_score * 0.10)
    )

    real_dimension_scores = {
        "knowledge": knowledge_score,
        "speed": speed_score,
        "practice": practice_score,
        "focus": focus_score,
        "logic": logic_score,
        "trend": trend_score,      # v3 新增: 学习趋势
        "overall": overall_score,
    }

    eval_system = EVALUATION_PROMPT.format(profile_summary=profile_summary)

    # 画像引导注入 — 新用户首次使用时收集画像
    from app.core.shared_utils import _build_profile_guide
    profile_guide = _build_profile_guide(profile)
    if profile_guide:
        eval_system += profile_guide

    # 注意：Mermaid 饼图由 chat.py 在流式结束后统一追加（使用真实 BKT 数据）
    # 此处不再注入到 system prompt，避免 LLM 重复生成导致图表重复

    # 携带对话历史上下文，确保评估报告聚焦用户当前的学科领域和编程语言
    from app.core.shared_utils import _build_llm_messages
    all_msgs = state.get("messages", [])
    last_user_msg = last_msg_content(state.get("messages", []), default="评估学习情况")
    topic_ctx = state.get("context", {}).get("topic_context", {})
    messages = _build_llm_messages(
        eval_system,
        all_msgs,
        last_user_msg,
        max_history=12,
        topic_context=topic_ctx,
    )

    # Token 截断：防止画像数据过大导致 API 超限
    from app.utils.llm_helper import truncate_messages
    messages = truncate_messages(messages, max_tokens=6000)

    logger.info("EvaluationAgent: 准备流式生成评估报告 dim_scores=%s", real_dimension_scores)

    return {
        "current_agent": "evaluation_agent",
        "stream_buffer": "",
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "evaluation_agent": {
                "stream_pending": {"messages": messages, "temperature": 0.6, "max_tokens": 4096},
                "dimension_scores": real_dimension_scores,
            },
        },
    }
