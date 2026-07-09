"""Agent output persistence — saves generated content to DB tables"""

import logging
from app.core.database import get_session
from app.models.resource import Resource
from app.models.assessment import AssessmentReport
from app.models.learning_path import LearningPath
from app.models.profile import LearningProfile
from app.services.knowledge_boost import _boost_knowledge_score

logger = logging.getLogger(__name__)


def _load_profile(user_id: int) -> dict | None:
    """从 MySQL 加载用户画像"""
    if not user_id:
        return None
    with get_session() as db:
        row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
        if not row:
            return None
        return {
            "knowledge_base": row.knowledge_base,
            "cognitive_style": row.cognitive_style,
            "learning_goal": row.learning_goal,
            "weekly_hours": row.weekly_hours,
            "error_patterns": row.error_patterns,
            "preferred_resource_type": row.preferred_resource_type,
            "dimension_scores": row.dimension_scores,
        }


def _persist_agent_output(agent_name: str, content: str, user_id: int, agent_outputs: dict, teaching_context: dict | None = None) -> dict | None:
    """将 Agent 生成的完整内容写入对应数据表 + 回写画像反馈

    增强: 当 agent_name 不匹配时，遍历 agent_outputs 查找实际产生输出的 Agent
    v4: 教学模式下，资源生成后自动关联到当前路径节点 (P1-16 NodeResource)
    """
    if not user_id or not content:
        return

    # 如果 agent_name 不是已知 worker agent，尝试从 agent_outputs 推断
    worker_agents = {"resource_agent", "evaluation_agent", "path_agent", "question_agent", "profile_agent"}
    if agent_name not in worker_agents:
        # 从 agent_outputs 中找到有实际输出的 agent
        for key in agent_outputs:
            if key in worker_agents:
                logger.info("Persist: agent_name '%s' → 从 agent_outputs 推断为 '%s'", agent_name, key)
                agent_name = key
                break

    boosted_topic: str = ""
    try:
        with get_session() as db:
            if agent_name == "resource_agent":
                meta = agent_outputs.get("resource_agent", {})
                title = meta.get("title") or meta.get("topic", "")
                resource_type = meta.get("type", "document")
                r = Resource(user_id=user_id, resource_type=resource_type,
                            title=title, content=content, generated_by="resource_agent")
                db.add(r)
                db.flush()
                logger.info("Persist: 资源已入库 id=%d type=%s title='%s' chars=%d",
                            r.id, resource_type, title, len(content))
                if meta:
                    meta["db_id"] = r.id
                if title:
                    _boost_knowledge_score(db, user_id, title)
                    boosted_topic = title

                # ── P1-16: 教学模式 → 资源关联到当前路径节点 ──
                if teaching_context and teaching_context.get("mode") == "teaching":
                    try:
                        active_path = teaching_context.get("active_path", [])
                        current_idx = teaching_context.get("current_index", 0)
                        if 0 <= current_idx < len(active_path):
                            current_node = active_path[current_idx]
                            from app.models.node_resource import NodeResource
                            nr = NodeResource(
                                user_id=user_id,
                                node_name=current_node,
                                resource_id=r.id,
                            )
                            db.add(nr)
                            logger.info("P1-16: 资源 id=%d 已关联到路径节点 '%s' (idx=%d)",
                                        r.id, current_node, current_idx)
                    except Exception as link_err:
                        logger.warning("P1-16: 资源关联路径节点失败 (non-fatal): %s", link_err)
            elif agent_name == "evaluation_agent":
                eval_meta = agent_outputs.get("evaluation_agent", {})
                ds = eval_meta.get("dimension_scores", {})
                if not ds:
                    profile = _load_profile(user_id)
                    ds = profile.get("dimension_scores") if profile else {}
                r = AssessmentReport(user_id=user_id, report_type="progress",
                                    report_data={"content": content},
                                    dimension_scores=ds or {},
                                    suggestions=[])
                db.add(r)
            elif agent_name == "path_agent":
                r = LearningPath(user_id=user_id,
                               path_data={"content": content,
                                         "topic": agent_outputs.get("path_agent", {}).get("topic", "")},
                               status="active")
                db.add(r)
            elif agent_name == "question_agent":
                meta = agent_outputs.get("question_agent", {})
                # 出题模式：缓存完整题目文本，供下次评阅使用
                # (Agent 不自行调用 LLM，完整文本在此处获取后写入缓存)
                if meta.get("mode") == "generate" and content:
                    try:
                        from app.agents.question_agent import cache_questions_text
                        cache_questions_text(user_id, content)
                    except Exception as e:
                        logger.warning("缓存题目文本失败: %s", e)
                # 评阅模式：解析 LLM 批改结果 → 逐题更新 BKT → 同步回 Profile
                elif meta.get("mode") == "grade" and content:
                    topic = meta.get("topic", "")
                    if topic:
                        try:
                            from app.agents.question_agent import parse_grading_result
                            from app.services.bkt_service import get_tracker, sync_bkt_to_profile

                            result = parse_grading_result(content)
                            per_question = result.get("per_question", [])
                            correct_count = result.get("correct_count", 0)
                            total_count = result.get("total_count", 0)

                            if per_question and total_count > 0:
                                tracker = get_tracker(user_id)
                                for is_correct in per_question:
                                    tracker.record_answer(topic, correct=is_correct)
                                tracker.persist_to_db()
                                logger.info(
                                    "BKT评分闭环: topic='%s' %d/%d correct → p_known=%.3f [%s]",
                                    topic, correct_count, total_count,
                                    tracker.get_or_create(topic).p_known,
                                    tracker.get_or_create(topic).level,
                                )
                                # 回写 Profile: BKT 后验概率 → knowledge_base 分数
                                sync_bkt_to_profile(user_id)
                            elif total_count > 0:
                                # 解析出汇总但无逐题明细，用聚合准确率更新
                                from app.services.bkt_service import get_tracker, sync_bkt_to_profile
                                tracker = get_tracker(user_id)
                                accuracy = correct_count / total_count
                                tracker.record_answer(topic, correct=accuracy >= 0.6)
                                tracker.persist_to_db()
                                sync_bkt_to_profile(user_id)
                        except Exception as e:
                            logger.warning("BKT评分闭环执行失败: %s", e)
        # commit 已完成（get_session 退出时自动 commit）
        # 将资源生成新增的知识点同步到 BKT 作为先验
        if boosted_topic:
            try:
                from app.services.bkt_service import sync_profile_to_bkt
                kb_sync = _load_profile(user_id)
                if kb_sync:
                    sync_profile_to_bkt(user_id, kb_sync.get("knowledge_base", {}))
            except Exception as _e:
                logger.warning("Profile→BKT 资源同步失败: %s", _e)
    except Exception as e:
        logger.warning("持久化 %s 输出失败: %s", agent_name, e)
