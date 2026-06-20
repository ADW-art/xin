"""
Evaluation Agent — 学习效果评估

根据学生的答题记录和行为数据，生成多维度评估报告。
- 6 维评估：知识掌握/学习速度/薄弱环节/进步趋势/投入度/推荐策略
- 生成文本评估 + 建议
"""

import logging

from app.agents.state import AgentState
from app.services.spark_client import SparkClient
from app.services.bkt_service import get_tracker

logger = logging.getLogger(__name__)

EVALUATION_PROMPT = """你是一个学习效果评估专家，风格对标专业教研报告。根据学生的学习数据，生成多维度评估报告。

## 学生画像
{profile_summary}

## 输出格式要求（必须遵守）

### 图解说明（必须在报告开头插入）
- **必须**用 Mermaid 图表可视化评估数据，使用 ```mermaid 代码块格式
- 至少包含1个图表（最多3个），选择以下类型：
  · pie chart（饼图）：展示已掌握/学习中/未掌握的知识点分布
  · graph TD（流程图）：展示推荐的学习路径改进方向
  · quadrantChart（象限图）：展示各知识点的掌握度-重要度分布
- Mermaid 图表后紧跟文字解读
- 示例格式：
```mermaid
pie title 知识点掌握分布
    "已掌握" : 3
    "学习中" : 5
    "未掌握" : 9
```
> 禁止：在 mermaid 代码块中写中文标签时加引号（除非标签含特殊字符）

## 评估维度（逐一分析，每个维度必须有具体数据支撑，禁止空泛评价）

### 1. 知识掌握度
- 基于 BKT 已掌握知识点数量/比例，给出量化评价（如"已掌握 X/Y 个知识点，掌握率 Z%"）
- 标注掌握最牢的3个知识点和掌握最弱的3个知识点
- 禁止："你的基础知识还不错"（太模糊）→ 必须说清"不错在哪里、哪个主题强、哪个主题弱"

### 2. 薄弱环节
- 列出具体的薄弱知识点（名称+当前掌握概率+出错频率）
- 分析错误模式（是概念混淆？是边界条件遗漏？是语法不熟？）
- 每个薄弱点标注一个具体改进方案（不是"多练习"而是"重点练习XX类型的题目"）

### 3. 学习风格适配
- 基于认知风格和偏好资源类型，评价当前学习方式是否高效
- 如果不匹配，给出具体调整建议（如"你是视觉型但一直在看文档，建议尝试XX视频教程"）

### 4. 进度评估
- 基于每周投入时间和已掌握知识点，给出学习效率评价
- 与同阶段学习者对比（如"同龄段学习Python基础的周均进步速度约为X个知识点/周"）
- 预估完成当前学习目标还需要的时间

### 5. 改进建议（2-3条，每条必须可执行）
格式：**建议N**（优先级：高/中）: [具体做法] — 为什么这样做 — 预期效果
禁止："多做练习" → 允许："每天做2道代码编写题（推荐LeetCode简单难度），重点练习字符串和列表操作，预计2周内正确率可从60%提升到80%"

### 6. 下一步计划
- 推荐接下来3天具体学什么（知识点名 + 预计小时数 + 学习资源类型）
- 说明为什么这些知识点是当前最优选择

## 输出要求
- 每个维度用 ### 标题，至少3句话，必须有数据（数字/百分比/知识点名称）
- 语气积极鼓励，但数据要真实——不掩盖问题，不夸大进步
- 最后用 **总结** 收尾：2-3句话概括 + 一个核心建议
- 如果对话历史中用户指定了编程语言或学习领域，评估报告必须聚焦该领域

---

**主动引导（用 > 引用格式，只选最相关的1条）**：
- 薄弱点突出时：> 你最薄弱的环节是 XXX。要我帮你系统讲解一遍，从基础概念开始吗？
- 进步明显时：> 进步不错！要不要挑战一下更难的题目？我可以帮你出几道进阶题。
- 需调整计划时：> 当前的学习节奏偏慢，需要我帮你重新规划一份更紧凑的学习路线吗？
- 画像不完整时：> 为了让评估更准确，方便补充一下你每周能投入多少学习时间吗？"""


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
    if bkt_data["nodes"]:
        parts.append("\n## BKT 知识追踪数据（算法推算，非用户自评）")
        parts.append(f"- 已掌握知识点：{bkt_data['summary']['mastered']}/{bkt_data['summary']['total']}")
        parts.append(f"- 各知识点掌握概率：{bkt_data['nodes']}")
        parts.append(f"- 薄弱环节：{tracker.get_weak_points()}")
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
        practice_score = 50  # 无答题记录时默认 50

    # v3: 学习速度 — 统一函数 + 5分钟缓存 (避免每次评估查全表)
    speed_score = _compute_speed_score(state.get("user_id", 0))

    # v3: focus — 从每周投入时间推算 (0h→0分, 15h→50分, 30h→100分)
    weekly = float(profile.get("weekly_hours", 0) or 0)
    focus_score = round(min(weekly / 30, 1) * 100) if weekly > 0 else 50

    # v3: logic — 从 BKT 正确率和掌握率综合推算 (无数据时默认 50)
    accuracy_rate = total_correct / max(total_attempts, 1)
    mastered_rate = mastered / max(total, 1)
    logic_score = round((accuracy_rate * 0.5 + mastered_rate * 0.5) * 100) if total_attempts > 0 else 50

    # v3: overall — 覆盖全部 6 维 (knowledge/speed/practice/focus/logic + trend)
    # trend: 从 BKT 掌握率推算学习趋势 (mastered/total * 100)
    trend_score = round(mastered / max(total, 1) * 100) if total > 0 else 50
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

    # 携带对话历史上下文，确保评估报告聚焦用户当前的学科领域和编程语言
    from app.core.shared_utils import _build_llm_messages
    all_msgs = state.get("messages", [])
    last_user_msg = state["messages"][-1].content if state["messages"] else "评估学习情况"
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
