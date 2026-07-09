"""Post-agent event hooks — BKT→Path→Review closed loop"""

import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# v3: 画像事件驱动闭环 — Agent 完成后自动触发下游操作
# ═══════════════════════════════════════════════════════════════

def _post_agent_event_hook(agent_name: str, user_id: int, agent_outputs: dict):
    """Agent 完成后的自动联动: 评估→重规划, BKT变化→重评估

    参考: LangGraph HITL pattern + 教育系统 event-driven assessment
    """
    if not user_id:
        return

    try:
        # ── 事件1: Question Agent 批改完成 → BKT显著变化 → 推评估 ──
        if agent_name == "question_agent":
            q_meta = agent_outputs.get("question_agent", {})
            if q_meta.get("mode") == "grade":
                p_known = q_meta.get("bkt_p_known", 0.5)
                # BKT < 0.4: 薄弱, 建议重评估
                if p_known < 0.4:
                    logger.info("闭环事件: question→evaluation (p_known=%.2f < 0.4)", p_known)
                    _store_suggestion(user_id, "evaluation", {
                        "reason": f"BKT检测到薄弱点(p_known={p_known:.2f})，建议评估",
                        "priority": "high",
                    })

        # ── 事件2: Evaluation Agent 完成 → 薄弱点变化 → 推路径重规划 ──
        elif agent_name == "evaluation_agent":
            eval_meta = agent_outputs.get("evaluation_agent", {})
            dims = eval_meta.get("dimension_scores", {})
            weak_dims = [k for k, v in dims.items() if isinstance(v, (int, float)) and v < 40]
            if weak_dims:
                logger.info("闭环事件: evaluation→path (薄弱维度: %s)", weak_dims)
                _store_suggestion(user_id, "path", {
                    "reason": f"评估发现薄弱维度: {', '.join(weak_dims)}，建议重新规划",
                    "weak_dims": weak_dims,
                    "priority": "high",
                })

        # ── 事件3: Resource Agent 教学完成 → 推练习 + 记录复习 ──
        elif agent_name == "resource_agent":
            # 记录到艾宾浩斯复习调度器（教学完一个知识点 = 首次复习节点）
            try:
                r_meta = agent_outputs.get("resource_agent", {})
                taught_topic = r_meta.get("title") or r_meta.get("topic", "")
                if taught_topic:
                    from app.services.review_scheduler import get_scheduler
                    sched = get_scheduler(user_id)
                    sched.record_review(taught_topic)
                    logger.info("闭环事件: resource→review_scheduler 已记录复习节点 '%s'", taught_topic)
            except Exception:
                pass  # 复习记录非关键路径
            _store_suggestion(user_id, "question", {
                "reason": "教学完成后推荐练习巩固",
                "priority": "medium",
            })

        # ── 事件4: Profile Agent 画像采集完成 → 推测试/路径 ──
        elif agent_name == "profile_agent":
            _store_suggestion(user_id, "path", {
                "reason": "画像更完善了，要不要规划一下学习路径？",
                "priority": "medium",
            })

        # ── 事件5: Path Agent / Collaborative Path → 路径规划完成后自动预生成首个节点资源 ──
        elif agent_name in ("path_agent", "collaborative_path"):
            p_meta = agent_outputs.get(agent_name, {})
            stage = p_meta.get("teaching_stage", "")
            if stage in ("starting", "node_ready"):
                current_node = p_meta.get("current_node", "")
                _store_suggestion(user_id, "resource", {
                    "reason": "路径已规划，正在为你预生成首个学习资源",
                    "topic": current_node,
                    "priority": "high",
                    "auto_trigger": True,
                })
                logger.info("闭环: %s→resource(prefetch) node='%s'", agent_name, current_node)

        # ── 所有Agent完成后的通用建议 ──
        if agent_name not in ("profile_agent",):
            _store_suggestion(user_id, agent_name.replace("_agent", ""), {
                "reason": _get_agent_suggestion_text(agent_name),
                "priority": "low",
            })

    except Exception as e:
        logger.warning("事件驱动钩子失败: %s", e)


def _get_agent_suggestion_text(agent_name: str) -> str:
    return {
        "resource_agent": "刚学完一个知识点，做两道题巩固一下吧",
        "question_agent": "题目做完了，看看评估报告了解自己的掌握情况",
        "evaluation_agent": "评估完成了，根据薄弱点针对学习效果更好",
        "path_agent": "路径规划好了，开始第一个知识点的学习吧",
        "profile_agent": "画像更完善了，系统能更好地为你个性化推荐",
    }.get(agent_name, "继续探索更多学习功能")


def _store_suggestion(user_id: int, intent: str, context: dict):
    """存储 Agent 联动建议 (写入 Redis 或 Profile 的 suggestions 字段)

    业内最佳实践 (参考 LangChain Supervisor + AutoGen):
      - 全文去重 (不只最近 5 条)，避免长会话历史导致重复
      - 同 intent 在去重窗口 (1h) 内只展示一次
      - 已点击的建议标记为 dismissed=true，不再展示
    """
    try:
        from app.models.profile import LearningProfile
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
            if row:
                # P1 修复: 修复 isinstance bug（原代码 isinstance(x, []) 永远 False）
                suggestions = list(row.suggestions or []) if isinstance(row.suggestions, list) else []
                # 去重: 同意图60分钟内不重复建议 (全量检查, P1 修复)
                import time
                now = time.time()
                DEDUP_WINDOW = 3600  # 1 小时 (原 30 分钟太短, 长会话会重复)
                recent = any(
                    s.get("intent") == intent and now - s.get("ts", 0) < DEDUP_WINDOW
                    for s in suggestions  # ✅ 全文扫描 (原来是 [-5:])
                )
                if not recent:
                    suggestions.append({"intent": intent, "ts": now, **context})
                    # P1 修复: 写入前对全量 suggestions 按 intent 去重（保留最新）
                    dedup_map: dict[str, dict] = {}
                    for sg in suggestions:
                        cur = dedup_map.get(sg["intent"])
                        if not cur or sg.get("ts", 0) > cur.get("ts", 0):
                            dedup_map[sg["intent"]] = sg
                    deduped = list(dedup_map.values())
                    # 按时间倒序 + 保留最近10条
                    deduped.sort(key=lambda x: x.get("ts", 0), reverse=True)
                    row.suggestions = deduped[:10]
                    db.commit()
        finally:
            db.close()
    except Exception:
        pass  # 建议存储失败不影响主流程
