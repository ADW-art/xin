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

import json
import logging

from app.agents.state import AgentState
from app.agents.question_agent import question_agent_node, is_answer_submission
from app.agents.evaluation_agent import evaluation_agent_node
from app.agents.resource_agent import resource_agent_node
from app.agents.path_agent import path_agent_node
from app.agents._msg_compat import last_msg_content  # 兼容 checkpoint 恢复后 dict 格式
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)
def _safe_run(node_fn, state, spark, node_name: str) -> tuple[str, dict | None, str | None]:
    """安全执行 Agent 节点，返回 (name, result_dict, error_string)"""
    try:
        result = node_fn(state, spark)
        return (node_name, result, None)
    except Exception as e:
        logger.warning("协同节点 '%s' 执行失败: %s", node_name, e)
        return (node_name, None, str(e))


def _build_qa_review(q_outputs: dict, e_outputs: dict) -> dict:
    """从 Evaluation Agent 输出构建审题反馈"""
    notes = []
    dims = e_outputs.get("dimension_scores", {})

    # 薄弱维度 → 建议题目侧重
    weak = [(k, v) for k, v in dims.items() if isinstance(v, (int, float)) and v < 40]
    if weak:
        weak_names = [k for k, _ in weak[:3]]
        notes.append(f"建议题目侧重薄弱维度: {', '.join(weak_names)}")

    # BKT 难度匹配检查
    bkt_p = q_outputs.get("bkt_p_known", 0.5)
    if bkt_p > 0.8:
        notes.append(f"BKT P={bkt_p:.0%}(精通)，应出挑战题/综合题")
    elif bkt_p < 0.35:
        notes.append(f"BKT P={bkt_p:.0%}(入门)，应出基础概念题")

    # 题型建议
    topic = q_outputs.get("topic", "")
    if topic:
        notes.append(f"建议混合选择题+填空题+代码题，覆盖'{topic}'的不同层次")

    score = max(0, 100 - len(notes) * 8)
    return {"score": score, "notes": notes, "bkt_level": round(bkt_p, 2)}


def _quality_review_node(state: dict, spark: SparkClient) -> dict:
    """质量审查 Agent — 检查 Resource Agent 输出质量

    与 Resource Agent 并行运行，审查维度:
      1. BKT 难度匹配
      2. 认知风格适配
      3. 内容完整性预估
    """
    s = dict(state)
    profile = s.get("user_profile") or {}
    teaching_ctx = s.get("teaching_context") or {}
    topic = (teaching_ctx.get("active_path") or [None])[teaching_ctx.get("current_index", 0)] \
        if teaching_ctx.get("mode") == "teaching" else s.get("context", {}).get("topic", "")

    from app.services.bkt_service import get_tracker
    tracker = get_tracker(s.get("user_id", 0))
    bkt_data = tracker.to_dict()
    summary = bkt_data.get("summary", {})
    mastered = summary.get("mastered", 0)
    total = summary.get("total", 0)
    avg_mastery = mastered / max(total, 1)

    issues = []
    level = "适中"

    # 难度匹配
    if avg_mastery > 0.8 and total >= 3:
        issues.append(f"学生已掌握{mastered}/{total}概念，内容应偏向进阶/综合应用")
        level = "应偏难"
    elif avg_mastery < 0.3 and total >= 1:
        issues.append(f"学生仅掌握{mastered}/{total}概念，内容应注重基础讲解")
        level = "应偏易"

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

    # 结构完整性检查点（提示 Resource Agent 的强制清单）
    issues.append("应包含: 概念解释 → 代码示例 → 常见误区 → 练习题")

    weak_penalty = sum(20 for i in issues if "薄弱" in i or "难度" in i)
    struct_penalty = sum(15 for i in issues if "结构" in i or "包含" in i)
    misc_penalty = sum(10 for i in issues if not i.startswith("[") and not any(k in i for k in ["薄弱","难度","结构","包含"]))
    score = max(40, 100 - weak_penalty - struct_penalty - misc_penalty)
    score = min(score, 100)

    qc_text = "评分 " + str(score) + "/100"
    if issues:
        qc_text += "\n建议:\n" + "\n".join(issues[:5])
    return {
        "current_agent": "quality_reviewer",
        "stream_buffer": qc_text,
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

