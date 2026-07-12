"""
多智能体并行协同节点 — 真正的并行协作 + 交叉验证

架构参照 LangGraph Send API 并行模式：
  - 同一任务由 2 个 Agent 线程并行处理
  - 结果交叉验证后合并输出
  - Agent 间通过 state.agent_outputs 直接通信

协同模式：
  1. QA 协同:    Question Agent(出题) ∥ Evaluation Agent(审题)
  2. 资源协同:   Resource Agent(生成) ∥ Quality Reviewer(质检)
  3. 路径协同:   Path Agent(规划) ∥ Resource Agent(预生成首节点)
"""

import logging

from app.agents.state import AgentState
from app.agents._msg_compat import last_msg_content  # 兼容 checkpoint 恢复后 dict 格式
logger = logging.getLogger(__name__)


def _build_qa_review(q_outputs: dict, e_outputs: dict) -> dict:
    """从 Evaluation Agent 输出构建审题反馈"""
    notes = []
    dims = e_outputs.get("dimension_scores", {})

    # 薄弱维度 → 建议题目侧重
    weak = [(k, v) for k, v in dims.items() if isinstance(v, (int, float)) and v < 40]
    if weak:
        weak_names = [k for k, _ in weak[:3]]
        notes.append(f"建议题目侧重薄弱维度: {', '.join(weak_names)}")

    # BKT 难度匹配检查（防御: key 存在但值为 None 时兜底）
    bkt_p = q_outputs.get("bkt_p_known", 0.5)
    if bkt_p is None:
        bkt_p = 0.5
    if bkt_p > 0.8:
        notes.append(f"BKT P={bkt_p:.0%}(精通)，应出挑战题/综合题")
    elif bkt_p < 0.35:
        notes.append(f"BKT P={bkt_p:.0%}(入门)，应出基础概念题")

    # 题型建议
    topic = q_outputs.get("topic", "")
    if topic:
        notes.append(f"建议混合选择题+填空题+代码题，覆盖'{topic}'的不同层次")

    score = max(0, 100 - len(notes) * 8)
    return {"score": score, "notes": notes, "bkt_level": round(bkt_p or 0.5, 2)}


def _quality_review_node(state: dict) -> dict:
    """质量审查 Agent — 检查 Resource Agent 输出质量

    与 Resource Agent 并行运行，审查维度:
      1. BKT 难度匹配
      2. 认知风格适配
      3. 内容完整性预估
    """
    state = AgentState.model_validate(state)
    s = dict(state)
    profile = s.get("user_profile") or {}
    teaching_ctx = s.get("teaching_context") or {}
    topic = (teaching_ctx.get("active_path") or [None])[teaching_ctx.get("current_index", 0)] \
        if teaching_ctx.get("mode") == "teaching" else s.get("context", {}).get("topic", "")

    from app.services.bkt_service import get_tracker
    tracker = get_tracker(s.get("user_id", 0))
    bkt_data = tracker.to_dict()
    summary = bkt_data.get("summary", {})
    mastered = summary.get("real_mastered", summary.get("mastered", 0))  # P1-#6: 优先用 real_mastered
    # P1-#6 (2026-07-11): 用 real_total 替代 total 判断, 避免占位节点误判
    total = summary.get("real_total", summary.get("total", 0))
    total_attempts = summary.get("real_attempts", summary.get("total_attempts", 0))
    avg_mastery = mastered / max(total, 1)

    issues = []
    level = "适中"
    # P1-#6 (2026-07-11): 有意义的 BKT 至少 1 个真实概念 + 有答题记录
    has_meaningful_bkt = total >= 1 and total_attempts > 0

    # 难度匹配（仅当有足够的BKT数据时才有参考价值）
    if has_meaningful_bkt:
        if avg_mastery > 0.8:
            issues.append(f"学生已掌握{mastered}/{total}个真实学习概念，内容应偏向进阶/综合应用")
            level = "应偏难"
        elif avg_mastery < 0.3:
            issues.append(f"学生仅掌握{mastered}/{total}个真实学习概念，内容应注重基础讲解")
            level = "应偏易"
    elif total == 0:
        # P1-#6: 新用户/未学习用户, 明确说"无学习数据", 而不是 0/9
        issues.append("暂无BKT学习数据（用户尚未开始学习），按默认难度生成基础概念内容")
    else:
        issues.append(f"BKT数据不足（仅{total}个真实概念有记录），按默认难度生成")

    # 认知风格适配
    style = str(profile.get("cognitive_style", "")).lower()
    style_hints = {
        "visual": "应多使用图表/流程图/Mermaid图示",
        "kinesthetic": "应多包含可执行代码示例和动手练习",
        "reading": "应结构化文档，使用清晰的标题层级",
        "auditory": "内容应有良好的朗读节奏",
    }
    hint = style_hints.get(style)
    if hint:
        issues.append(f"[{style}型学习者] {hint}")

    # 结构完整性检查 — 检查 resource_agent 的元数据 (P1-FIX: stream_buffer 在流式模式下始终为空,
    # 因为 resource_agent 返回 stream_pending(messages), 实际内容由 chat.py 后续生成)
    _struct_issues = []
    _ao_inner = s.get("agent_outputs", {}) or {}
    _res_meta = _ao_inner.get("resource_agent", {}) or {}
    _has_stream_pending = bool(_res_meta.get("stream_pending"))
    _res_topic = _res_meta.get("topic", "")
    _res_title = _res_meta.get("title", "")
    if not _has_stream_pending and not _res_topic:
        _struct_issues.append("resource_agent 未生成有效请求, 可能提示词构建失败")
    elif not _res_title:
        _struct_issues.append("资源标题缺失, 建议检查话题提取逻辑")

    weak_penalty = sum(20 for i in issues if ("薄弱" in i or "难度" in i) and has_meaningful_bkt)
    # P0-#3 2026-07-11: 移除"应包含"形式化扣分 (struct_penalty)
    struct_penalty = 0
    # 仅排除纯信息性消息（以"["开头的风格提示），难度/结构类问题仍参与扣分
    misc_penalty = sum(10 for i in issues if not i.startswith("["))
    # 从基线分扣减，上限 100（P0-#4 2026-07-11 修复: max→min 使评分可低于基线）
    base_score = 85 if not has_meaningful_bkt else 60
    score = min(100, base_score - weak_penalty - struct_penalty - misc_penalty)
    score = max(score, 20)

    qc_text = "评分 " + str(score) + "/100"
    if issues:
        qc_text += "\n建议:\n" + "\n".join(issues[:5])
    return {
        "agent_outputs": {
            **s.get("agent_outputs", {}),
            "quality_reviewer": {
                "score": score,
                "issues": issues,
                "difficulty_target": level,
                "bkt_avg_mastery": round(avg_mastery, 2),
                "cognitive_style": style or "unknown",
            },
        },
    }

# ═══════════════════════════════════════════════════════════
# 并行协同 Join 节点 — 从 supervisor.py 提取，保持单一职责
# ═══════════════════════════════════════════════════════════

NL = "\n"


def qa_join_node(state):
    """QA 并行协同合并: question_agent + evaluation_agent

    P0-DEDUP (2026-07-12): 若 question_agent 已通过 stream_pending 流式输出，
    不再重复 yield stream_buffer。
    """
    state = AgentState.model_validate(state)
    s = dict(state)
    ao = s.get("agent_outputs") or {}
    q = ao.get("question_agent") or {}
    e = ao.get("evaluation_agent") or {}
    merged = {**ao, "_collaboration_mode": "qa_parallel"}
    if q.get("stream_pending"):
        buf = ""
    else:
        buf = q.get("stream_buffer", "") or ""
    ebuf = e.get("stream_buffer", "") or ""
    if ebuf:
        buf += NL + NL + "> **评估反馈**" + NL + "> " + ebuf.replace(NL, NL + "> ")
    return {"agent_outputs": merged, "stream_buffer": buf, "current_agent": "qa_join", "next_agent": "supervisor"}


def rc_join_node(state):
    """资源协同合并: resource_agent 输出 + 串行质量审查

    质量审查(_quality_review_node)从并行改为串行后处理:
    - 优点: 可以检查 resource_agent 的实际输出内容
    - 质量反馈写入 agent_outputs.quality_reviewer, 供 supervisor 质量门使用
    """
    state = AgentState.model_validate(state)
    s = dict(state)
    ao = s.get("agent_outputs") or {}
    r = ao.get("resource_agent") or {}

    # 串行质量审查 — 现在可以检查 resource_agent 的实际输出文本
    # P1-3 (2026-07-12): 质量审查包裹 try/except，防止异常导致 rc_join 崩溃
    try:
        qc_result = _quality_review_node(s)
    except Exception as _qc_err:
        logger.warning("rc_join: 质量审查失败 (non-fatal): %s", _qc_err)
        qc_result = {"agent_outputs": {}}
    qc = qc_result.get("agent_outputs", {}).get("quality_reviewer", {})

    merged = {**ao, **qc_result.get("agent_outputs", {}), "_collaboration_mode": "resource_serial_qc"}
    # P0 (2026-07-12): 质量审查结果只写入 agent_outputs 供 supervisor 内部使用，
    # 不再追加到 stream_buffer 泄露给用户
    buf = r.get("stream_buffer", "") or ""
    return {"agent_outputs": merged, "stream_buffer": buf, "current_agent": "rc_join", "next_agent": "supervisor"}



def path_join_node(state):
    """路径并行协同合并: path_agent + prefetch_agent

    P0-DEDUP (2026-07-12): path_agent 通过 stream_pending 流式输出时，
    path_join 不应再次 yield 同样的 stream_buffer，避免前端重复显示。
    """
    state = AgentState.model_validate(state)
    s = dict(state)
    ao = s.get("agent_outputs") or {}
    p = ao.get("path_agent") or {}
    pr = ao.get("prefetch_agent") or {}
    merged = {**ao, "_collaboration_mode": "path_parallel"}
    # P0-DEDUP: 若 path_agent 已通过 stream_pending 流式输出，跳过 stream_buffer
    # 避免同一内容被 yield 两次 (一次流式 + 一次 buffer)
    if p.get("stream_pending"):
        buf = ""
    else:
        buf = p.get("stream_buffer", "") or ""
    pf_buf = pr.get("stream_buffer", "") or ""
    # 只在教学模式合并 prefetch 资源（避免与后续 resource_agent 的推荐重复）
    tc = p.get("teaching_context") or {}
    if pf_buf and tc.get("mode") == "teaching":
        buf += NL + NL + "> **预生成资源**" + NL + "> "
        buf += pf_buf[:300].replace(NL, NL + "> ")
    elif pf_buf:
        logger.info("path_join: 非教学模式，跳过 prefetch 资源合并（由 resource_agent 处理）")
    tc = p.get("teaching_context")
    r = {"agent_outputs": merged, "stream_buffer": buf, "current_agent": "path_join", "next_agent": "supervisor"}
    if tc:
        r["teaching_context"] = tc
    return r


def _prefetch_resource_meta(state: dict) -> dict:
    """轻量资源预取: 简化为空 stub，避免 RAG 检索开销"""
    return {
        "current_agent": "prefetch_agent",
        "agent_outputs": {
            "prefetch_agent": {"topic": "", "stream_buffer": ""},
        },
        "stream_buffer": "",
    }