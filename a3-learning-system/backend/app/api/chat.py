"""
对话 API —— SSE 流式端点

POST /api/chat/send → 接收用户消息 → 调用星火 → 逐字流式返回
"""

import json
import uuid
import logging
import asyncio
import re
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from langchain_core.messages import HumanMessage

from app.core.database import get_session
from app.core.shared_utils import _normalize_concept_name, _build_llm_messages, _structure_knowledge_base
from app.core.security import decode_access_token
from app.core.sanitize import sanitize_input
from app.models.profile import LearningProfile
from app.models.user import User
from app.models.conversation import Conversation
from app.models.resource import Resource
from app.models.assessment import AssessmentReport
from app.models.learning_path import LearningPath
from app.dependencies import get_graph, get_spark_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["对话"])

_SENTINEL = object()


# ============================================================
# 请求模型
# ============================================================
class ImageInput(BaseModel):
    """用户上传的图片（base64 编码）"""
    base64: str = Field(..., description="图片 base64 数据（不含 data URI 前缀）")
    mime_type: str = Field(default="image/png", description="图片 MIME 类型")
    name: str = Field(default="image.png", description="原始文件名")

class ChatRequest(BaseModel):
    content: str = Field(..., min_length=1, description="用户输入的消息")
    images: list[ImageInput] | None = Field(default=None, description="多模态：用户上传的图片列表（最多4张）")

    @field_validator("content")
    @classmethod
    def content_must_be_meaningful(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("消息内容不能为空")
        if len(stripped) > 4000:
            raise ValueError("消息内容不能超过4000字")
        return sanitize_input(stripped)

    @field_validator("images")
    @classmethod
    def images_must_be_valid(cls, v: list | None) -> list | None:
        if v is None:
            return v
        if len(v) > 4:
            raise ValueError("最多支持上传4张图片")
        for img in v:
            if len(img.base64) > 10 * 1024 * 1024:  # 10MB base64 ≈ 7.5MB 图片
                raise ValueError(f"图片 '{img.name}' 过大，请压缩后重试")
        return v


# ============================================================
# 工具函数
# ============================================================
def _optional_user(authorization: str | None = Header(None)):
    """可选认证：有 token 就解析用户，没有就返回 None"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = decode_access_token(authorization[7:])
    if not payload:
        return None
    with get_session() as db:
        user = db.query(User).filter(User.id == int(payload["sub"])).first()
        if user:
            db.expunge(user)  # 分离实例，防止 session 关闭后 DetachedInstanceError
        return user


def _persist_agent_output(agent_name: str, content: str, user_id: int, agent_outputs: dict):
    """将 Agent 生成的完整内容写入对应数据表 + 回写画像反馈

    增强: 当 agent_name 不匹配时，遍历 agent_outputs 查找实际产生输出的 Agent
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
    """存储 Agent 联动建议 (写入 Redis 或 Profile 的 suggestions 字段)"""
    try:
        from app.models.profile import LearningProfile
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
            if row:
                suggestions = list(row.suggestions or []) if isinstance(row.suggestions, list) else []
                # 去重: 同意图30分钟内不重复建议
                import time
                now = time.time()
                recent = any(
                    s.get("intent") == intent and now - s.get("ts", 0) < 1800
                    for s in suggestions[-5:]  # 只检查最近5条
                )
                if not recent:
                    suggestions.append({"intent": intent, "ts": now, **context})
                    row.suggestions = suggestions[-10:]  # 保留最近10条
                    db.commit()
        finally:
            db.close()
    except Exception:
        pass  # 建议存储失败不影响主流程


def _extract_and_boost(user_id: int, user_message: str):
    """从用户消息中提取知识点 → 更新 knowledge_base（不依赖 Agent 路由）

    原则：
      1. 先判断消息是否有学习意图（闲聊/问候/感谢等直接跳过）
      2. 从知识图谱 51 个专有名词中匹配，而非用通配正则提取
      3. 匹配到的 KG 节点名 = 标准化概念名，无需二次 normalize
    """
    if not user_id or not user_message:
        return

    user_message_lower = user_message.lower()

    # ═══════════════════════════════════════════════════════════
    # Step 1: 学习意图预过滤 — 非学习意图的消息不触发知识更新 (中英双语)
    # ═══════════════════════════════════════════════════════════
    LEARNING_INTENT_KEYWORDS = [
        # 明确学习意图 (CN)
        '学', '教', '讲', '解释', '介绍', '什么是', '什么叫', '怎么做', '如何',
        '帮我', '给我', '我要', '我想', '帮我学', '教我', '讲一下', '说说',
        # 做题意图
        '出题', '做题', '测试', '考', '练习', '题目', '来点', '给我出',
        # 资源意图
        '生成', '资料', '笔记', '导图', '代码', '案例', '资源', '文档',
        # 评估意图
        '评估', '掌握', '学得', '水平', '报告', '分析',
        # 明确学习意图 (EN)
        'learn', 'teach', 'explain', 'what is', 'how to', 'how does',
        'tell me about', 'show me', 'i want to', 'help me',
        # 做题意图 (EN)
        'exercise', 'question', 'problem', 'quiz', 'practice', 'test',
        # 资源意图 (EN)
        'generate', 'code', 'example', 'tutorial', 'mindmap', 'document',
        # 评估意图 (EN)
        'evaluate', 'assess', 'report', 'progress', 'check my',
    ]
    has_learning_intent = any(kw in user_message_lower for kw in LEARNING_INTENT_KEYWORDS)
    if not has_learning_intent:
        return  # 闲聊/问候/感谢/日常对话 — 不触发知识更新

    # ═══════════════════════════════════════════════════════════
    # Step 2: 加载知识图谱节点作为专有名词词表
    # ═══════════════════════════════════════════════════════════
    try:
        from app.services.bkt_service import _load_kg_vocabulary
        kg_nodes = _load_kg_vocabulary()
    except Exception:
        return
    if not kg_nodes:
        return

    # ═══════════════════════════════════════════════════════════
    # Step 3: 在用户消息中查找知识图谱专有名词（含子串匹配）
    # ═══════════════════════════════════════════════════════════
    matched_concepts = []
    for node in kg_nodes:
        if node in user_message:
            matched_concepts.append(node)
            continue
        # 子串匹配：将节点名按中英文边界切分后匹配
        # 例如 "Python基础" → ["Python", "基础"], "C++基础" → ["C++", "基础"]
        node_parts = re.split(r'(?<=[a-zA-Z0-9+#])(?=[一-鿿])|(?<=[一-鿿])(?=[a-zA-Z0-9+#])|与|和|/', node)
        node_parts = [p.strip() for p in node_parts if len(p.strip()) >= 2]
        for part in node_parts:
            if part in user_message:
                matched_concepts.append(node)
                break
        else:
            # 纯中文节点（如 "排序算法"），取其前2字做前缀匹配
            # 用户说 "来点排序题目" 可以匹配到 "排序算法"
            if len(node) >= 3 and all('一' <= c <= '鿿' or c in '·' for c in node[:2]):
                prefix = node[:2]
                if prefix in user_message and prefix not in ('什么', '怎么', '如何', '为什么', '哪个'):
                    matched_concepts.append(node)

    if not matched_concepts:
        # 没有匹配到 KG 专有名词 → 不更新（避免把"列表"之外的无关词条入库）
        return

    # ═══════════════════════════════════════════════════════════
    # Step 4: 更新 Profile + 同步到 BKT
    # ═══════════════════════════════════════════════════════════
    for topic in matched_concepts:
        try:
            with get_session() as db:
                _boost_knowledge_score(db, user_id, topic)
                logger.info("学习闭环: KG节点 '%s' → Profile 已更新", topic)
        except Exception as e:
            logger.warning("学习闭环失败 (topic=%s): %s", topic, e)

    # 批量同步 BKT
    try:
        from app.services.bkt_service import sync_profile_to_bkt
        kb_sync = _load_profile(user_id)
        if kb_sync:
            sync_profile_to_bkt(user_id, kb_sync.get("knowledge_base", {}))
    except Exception as _e:
        logger.warning("Profile→BKT 同步失败: %s", _e)


def _silent_profile_collect(user_id: int, user_message: str):
    """静默画像采集：从非 profile 交互中提取背景信息 (中英双语)

    限制：仅对含学习相关关键词的消息触发，闲聊/问候等无关语句跳过。
    """
    if not user_id or not user_message:
        return

    text = user_message.strip()
    text_lower = text.lower()

    # 学习意图预过滤 — 中英双语
    LEARNING_KEYWORDS = [
        '学', '教', '讲', '解释', '介绍', '什么是', '怎么做', '如何',
        '帮我', '给我', '我要', '我想', '做题', '考试', '面试',
        '学过', '用过', '会', '懂', '熟悉', '了解', '做过',
        '喜欢', '偏好', '倾向于', '目标', '希望', '打算',
        # EN
        'learn', 'teach', 'explain', 'study', 'code', 'programming',
        'exercise', 'practice', 'know', 'familiar', 'experienced',
        'background', 'goal', 'prefer', 'want to', 'would like',
    ]
    if not any(kw in text_lower for kw in LEARNING_KEYWORDS):
        return

    # ── 知识基础提取 (CN + EN) ──
    kb_patterns = [
        # CN
        r'(?:我)?(?:已经?|以前|之前|学过|用过|会|懂|熟悉|了解|做过)[的\s]*([\w一-鿿]{2,15})',
        r'(?:我是|作为)([一二三四五六七八九十\d]+年?[的\s]*[\w一-鿿]{2,10})',
        # EN
        r"(?:i(?:'ve|\s+have)?\s+(?:learned|studied|used|worked\s+with))\s+([\w\s+#]{2,20}?)(?:\.|,|and|\s+but|$)",
        r"(?:i\s+(?:know|am\s+familiar\s+with|have\s+experience\s+in))\s+([\w\s+#]{2,20}?)(?:\.|,|$)",
        r"(?:my\s+background\s+(?:is\s+)?in)\s+([\w\s+#]{2,20}?)(?:\.|,|$)",
    ]
    goal_patterns = [
        # CN
        r'(?:为了|准备|想找|目标是|希望|打算)([\w一-鿿]{2,12})',
        r'(?:求职|找工作|面试|考试|考研|转行|升职|加薪)',
        # EN
        r"(?:i\s+(?:want|plan|hope|aim)\s+to\s+(?:learn|study|become|get))\s+([\w\s+#]{2,20}?)(?:\.|,|$)",
        r"(?:my\s+goal\s+(?:is\s+)?(?:to\s+)?)([\w\s+#]{2,20}?)(?:\.|,|$)",
        r"(?:preparing\s+for)\s+([\w\s+#]{2,20}?)(?:\.|,|$)",
    ]
    style_patterns = [
        # CN
        r'(?:喜欢|偏好|更愿|倾向于|习惯)(?:看|读|听|写|做|动手)([\w一-鿿]{2,8})',
        # EN
        r"(?:i\s+(?:prefer|like|enjoy)\s+(?:reading|watching|listening|doing|hands-on|coding))\s*([\w\s+#]{2,12})?",
        r"(?:i(?:'m|\s+am)\s+a\s+(visual|auditory|kinesthetic|reading|hands-on)\s+learner)",
    ]
    updates = {}

    # ── 时间投入提取 ──
    hours_patterns = [
        r'每[周天日月年][\s]*(?:大概|大约|能|可[以能]|要|可以|想)?(?:投[入人]|学[习]?|花[费]?)[\s]*(\d+)[\s]*(?:个|小时|h|H|钟头)',
        r'(\d+)[\s]*(?:小时|个?钟头|h|H)[/每][周天]',
        r'(?:每周|每天)[\s]*(?:大概|大约|能|可以)?[\s]*(\d+)[\s]*(?:小时|h|H)',
        r'(?:weekly|per week)[\s]*[:：]?[\s]*(\d+)[\s]*(?:hours?|hrs?|h)',
        r'i\s+(?:can|have|spend)\s+(?:about\s+)?(\d+)\s+(?:hours?|hrs?)\s+(?:per|a|each)\s+week',
    ]
    for pattern in hours_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            try:
                hours_val = float(m.group(1))
                if 1 <= hours_val <= 100:
                    updates["weekly_hours"] = hours_val
                    break
            except (ValueError, IndexError):
                pass

    # ── 偏好资源类型提取 ──
    resource_patterns = [
        r'(?:喜欢|偏好|更愿|倾向于|习惯)(?:看|读)[\s]*(?:文档|资料|书|文章|笔记)',
        r'(?:喜欢|偏好|更愿|倾向于)(?:看|刷)[\s]*(?:视频|教程视频|讲解视频|录播)',
        r'(?:喜欢|偏好|更愿|倾向于)[\s]*(?:动手|敲代码|写代码|做项目|实践)',
        r'(?:喜欢|偏好)[\s]*(?:思维导图|脑图|导图|图解)',
    ]
    pref_map = [
        (['文档','资料','书','文章','笔记'], 'text'),
        (['视频','教程视频','讲解视频','录播','看视频'], 'video'),
        (['动手','敲代码','写代码','做项目','实践','代码'], 'code'),
        (['思维导图','脑图','导图','图解'], 'interactive'),
    ]
    for pattern in resource_patterns:
        m = re.search(pattern, text)
        if m:
            matched_text = m.group(0)
            for keywords, pref_val in pref_map:
                if any(kw in matched_text for kw in keywords):
                    updates["preferred_resource_type"] = pref_val
                    break
            break

    for pattern in kb_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip() if len(m.groups()) > 0 and m.group(1) else m.group(0)
            if len(val) >= 2:
                updates["knowledge_base"] = val
                break
    for pattern in goal_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip() if len(m.groups()) > 0 and m.group(1) else m.group(0)
            if len(val) >= 2:
                updates["learning_goal"] = val
            else:
                updates["learning_goal"] = m.group(0)
            break
    for pattern in style_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip() if m and m.group(1) else ""
            if val:
                # 规范化到标准值: visual/auditory/kinesthetic/reading
                val_lower = val.lower()
                if any(kw in val_lower for kw in ['看','读','视觉','图','视频','watch','read','visual']):
                    updates["cognitive_style"] = "visual"
                elif any(kw in val_lower for kw in ['听','音频','auditory','listen']):
                    updates["cognitive_style"] = "auditory"
                elif any(kw in val_lower for kw in ['动手','做','写代码','实践','操作','项目','敲','kinesthetic','hands-on','code']):
                    updates["cognitive_style"] = "kinesthetic"
                else:
                    updates["cognitive_style"] = "reading"
            break
    if not updates:
        return
    try:
        with get_session() as db:
            row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
            if row:
                for key, value in updates.items():
                    old_val = getattr(row, key, None)
                    if not old_val or (isinstance(old_val, str) and len(old_val) < 3):
                        setattr(row, key, value)
                        logger.info("静默采集: %s = '%s' (user_id=%d)", key, value, user_id)
                # 更新 dimension_scores
                try:
                    from app.agents.profile_agent import _compute_dimension_scores
                    profile_dict = {
                        "knowledge_base": str(row.knowledge_base or ""),
                        "cognitive_style": row.cognitive_style,
                        "learning_goal": row.learning_goal,
                        "weekly_hours": row.weekly_hours,
                        "preferred_resource_type": row.preferred_resource_type,
                        "error_patterns": row.error_patterns,
                    }
                    row.dimension_scores = _compute_dimension_scores(profile_dict)
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(row, "dimension_scores")
                except Exception:
                    pass  # 非关键路径
    except Exception as e:
        logger.warning("静默采集失败: %s", e)


def _boost_knowledge_score(db, user_id: int, topic: str, boost: float = 8.0):
    """资源生成/学习行为后，更新用户画像 knowledge_base + 同步 BKT 追踪器"""
    topic = _normalize_concept_name(topic)
    if topic == "未分类":
        return
    row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
    if not row:
        # 自动创建画像（用户首次对话时 profile 可能尚不存在）
        row = LearningProfile(user_id=user_id, knowledge_base={})
        db.add(row)
        db.flush()
        logger.info("FeedbackLoop: 自动创建画像 (user_id=%d)", user_id)
    kb = row.knowledge_base
    if not kb or isinstance(kb, str):
        kb = _structure_knowledge_base(str(kb or "")) if isinstance(kb, str) else {}
    matched_key = None
    for existing_key in kb:
        if topic.lower() in existing_key.lower() or existing_key.lower() in topic.lower():
            matched_key = existing_key
            break
    if matched_key:
        old_val = float(kb[matched_key]) if isinstance(kb[matched_key], (int, float)) else 55.0
        kb[matched_key] = round(min(95, old_val + boost), 1)
        logger.info("FeedbackLoop: 提升知识点 '%s' %.1f -> %.1f", matched_key, old_val, kb[matched_key])
    else:
        kb[topic] = 40.0
        logger.info("FeedbackLoop: 新增知识点 '%s' -> 40.0", topic)
    row.knowledge_base = kb
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(row, "knowledge_base")

    # 每次知识更新后重算 dimension_scores（确保雷达图数据始终最新）
    try:
        from app.agents.profile_agent import _compute_dimension_scores
        pdict = {
            "knowledge_base": str(row.knowledge_base or ""),
            "cognitive_style": row.cognitive_style,
            "learning_goal": row.learning_goal,
            "weekly_hours": row.weekly_hours,
            "preferred_resource_type": row.preferred_resource_type,
            "error_patterns": row.error_patterns,
        }
        row.dimension_scores = _compute_dimension_scores(pdict)
        flag_modified(row, "dimension_scores")
    except Exception:
        pass  # 非关键路径，不影响主流程


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


def _load_conversation_history(user_id: int, limit: int = 24) -> list:
    """加载最近的对话历史，构建 LangChain messages 列表"""
    if not user_id:
        return []
    with get_session() as db:
        rows = (
            db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        from langchain_core.messages import HumanMessage, AIMessage
        messages = []
        for row in rows:
            if row.role == "user":
                messages.append(HumanMessage(content=row.content))
            else:
                messages.append(AIMessage(content=row.content))
        return messages


def _extract_topic_context(history_msgs: list, current_msg: str) -> dict:
    """从对话历史中提取当前话题上下文"""
    result = {
        "current_topic": "",
        "recent_topics": [],
        "pronoun_map": {},
        "domain": "",
        "user_language": "",
        "user_constraints": [],
    }
    if not history_msgs:
        return result
    all_text = current_msg + " "
    for msg in history_msgs[-8:]:
        content = str(getattr(msg, 'content', msg))
        all_text += content + " "
    language_patterns = [
        r'(?:我要学|想学|学|用|写|教我|帮我|给我)[\s]*([Cc][+\#]*|[Gg]o|[Rr]ust|[Jj]ava[Ss]cript|[Pp]ython|[Jj]ava|[Ss]wift|[Kk]otlin|[Rr]uby|[Pp]hp|[Tt]ype[Ss]cript)',
        r'(?:用|使用|基于|基于?)[\s]*([Cc][+\#]+|[Gg]o|[Rr]ust|[Jj]ava[Ss]cript|[Pp]ython|[Jj]ava)',
        r'([Cc]\+\+|[Cc]#|[Gg]o|[Rr]ust|[Pp]ython|[Jj]ava|[Jj]ava[Ss]cript|[Ss]wift|[Kk]otlin)(?:语言|开发|编程)?',
    ]
    for pattern in language_patterns:
        m = re.search(pattern, all_text)
        if m and m.lastindex and m.lastindex >= 1:
            lang = m.group(1).strip()
            if lang and len(lang) >= 2:
                result["user_language"] = lang
                break
    exclude_patterns = [
        r'(?:不要|别|不用|不要给我|不想|排除|跳过)[\s]*(.{2,10}?)(?:[，。！？\s]|$)',
    ]
    for pattern in exclude_patterns:
        matches = re.findall(pattern, all_text)
        for m2 in matches:
            m2 = m2.strip()
            if len(m2) >= 2:
                result["user_constraints"].append(m2)
    domain_keywords = {
        "C++基础": ["c++", "cpp", "指针", "引用", "内存管理", "模板", "STL", "面向对象", "虚函数", "多态", "继承"],
        "Python基础": ["python", "列表", "字典", "元组", "函数", "类", "装饰器", "推导式", "迭代器", "生成器"],
        "Java基础": ["java", "spring", "maven", "jvm", "集合", "stream", "注解", "接口", "抽象类"],
        "Go语言": ["go", "goroutine", "channel", "协程", "并发", "interface", "struct", "slice", "map"],
        "JavaScript": ["javascript", "js", "node", "react", "vue", "angular", "promise", "async", "dom"],
        "数据结构": ["树", "图", "链表", "栈", "队列", "哈希", "排序", "查找", "二叉树", "红黑树", "B树", "数组"],
        "算法": ["递归", "动态规划", "贪心", "分治", "回溯", "DFS", "BFS", "二分", "快排", "归并"],
        "数据库": ["SQL", "MySQL", "索引", "事务", "JOIN", "查询优化", "NoSQL", "Redis", "PostgreSQL"],
        "前端开发": ["HTML", "CSS", "JavaScript", "React", "Vue", "DOM", "组件", "响应式", "CSS3"],
        "后端开发": ["API", "REST", "Flask", "Django", "Spring", "微服务", "接口", "认证", "中间件"],
        "机器学习": ["神经网络", "深度学习", "训练", "模型", "特征", "分类", "回归", "聚类", "TensorFlow", "PyTorch"],
    }
    domain_scores = {}
    for domain, keywords in domain_keywords.items():
        score = sum(1 for kw in keywords if kw.lower() in all_text.lower())
        if score >= 1:
            domain_scores[domain] = score
    if result["user_language"]:
        lang_lower = result["user_language"].lower()
        for domain in domain_keywords:
            if lang_lower in domain.lower() or any(kw.lower() == lang_lower for kw in domain_keywords[domain]):
                result["domain"] = domain
                break
        if not result["domain"] and domain_scores:
            result["domain"] = max(domain_scores, key=domain_scores.get)
    elif domain_scores:
        result["domain"] = max(domain_scores, key=domain_scores.get)
    topic_patterns = [
        r'(?:[Cc]\+\+|[Pp]ython|[Jj]ava|[Gg]o|[Jj]avascript)[\s]*(?:的)?[\s]*(?:列表|字典|数组|字符串|函数|类|指针|引用|容器|模板|迭代器|STL|集合|对象|变量|循环|条件|异常|内存|线程|并发|协程)',
        r'(?:二叉|平衡|红黑|B[\s]*树|AVL|堆|线段| Trie |前缀)*树',
        r'(?:快速|归并|冒泡|插入|选择|桶|基数|希尔|计数)*排序',
        r'(链表|栈|队列|哈希表|散列表|堆栈|数组|矩阵|图|有向图|无向图)',
        r'(递归|迭代|遍历|搜索|查找|回溯|贪心|分治|动态规划|DFS|BFS|二分|双指针|滑动窗口)',
        r'(指针|引用|虚函数|纯虚函数|模板|特化|偏特化|STL|vector|map|set|智能指针|unique_ptr|shared_ptr|移动语义|右值引用)',
        r'(装饰器|推导式|生成器|迭代器|闭包|lambda|切片|解包|上下文管理符|元类|描述符|@property)',
        r'(封装|继承|多态|重载|覆盖|抽象|接口|泛型|类型推断|内存管理|垃圾回收|并发|并行|异步|回调|Promise)',
    ]
    topics_found = []
    for pattern in topic_patterns:
        matches = re.findall(pattern, all_text, re.IGNORECASE)
        for m3 in matches:
            if isinstance(m3, tuple):
                m3 = m3[0]
            m3 = m3.strip()
            if len(m3) >= 2 and len(m3) <= 20 and m3 not in topics_found:
                topics_found.append(m3)
    if result["user_language"] and result["user_language"] not in topics_found:
        topics_found.append(result["user_language"])
    if topics_found:
        result["current_topic"] = topics_found[-1]
        result["recent_topics"] = topics_found[-5:]
    pronouns = ["它", "这个", "这个概念", "那个", "那", "这种"]
    if result["current_topic"]:
        for pronoun in pronouns:
            if pronoun in current_msg:
                result["pronoun_map"][pronoun] = result["current_topic"]
                break
    return result


async def _bridge_stream(spark, messages: list, temperature: float, max_tokens: int, use_safe: bool = False, chunk_size: int = 2):
    """线程安全队列桥接：把同步的 chat_stream 转成异步生成器"""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _run():
        try:
            pre_collected = messages[0].get("__pre_collected__") if messages and isinstance(messages[0], dict) else None
            if pre_collected:
                for chunk in pre_collected:
                    if chunk:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
            elif use_safe:
                from app.utils.llm_helper import safe_chat_stream
                gen = safe_chat_stream(spark, messages, temperature=temperature, max_tokens=max_tokens, retries=2, fallback="服务繁忙，请稍后再试~")
                for chunk in gen:
                    if chunk:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
            else:
                gen = spark.chat_stream(messages, temperature=temperature, max_tokens=max_tokens)
                for chunk in gen:
                    if chunk:
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    ThreadPoolExecutor(max_workers=1).submit(_run)

    # True streaming: yield chunks as they arrive (NOT buffered)
    # chunk_size > 0 enables character-level typewriter effect
    accumulated = ""
    while True:
        item = await queue.get()
        if item is _SENTINEL:
            if accumulated:
                yield accumulated
            break
        if isinstance(item, Exception):
            if accumulated:
                yield accumulated
            raise item

        if chunk_size > 0:
            accumulated += item
            while len(accumulated) >= chunk_size:
                yield accumulated[:chunk_size]
                accumulated = accumulated[chunk_size:]
        else:
            yield item


# ============================================================
# POST /api/chat/send —— 核心 SSE 端点
# ============================================================
@router.post("/send")
async def chat_send(
    request: ChatRequest,
    graph=Depends(get_graph),
    spark=Depends(get_spark_client),
    current_user: User | None = Depends(_optional_user),
):
    """发送消息 -> LangGraph Supervisor 调度 -> Agent 处理 -> SSE 流式返回"""

    user_id = current_user.id if current_user else 0

    history_msgs = _load_conversation_history(user_id, limit=12)
    topic_ctx = _extract_topic_context(history_msgs, request.content)

    # ── 多模态：构建用户消息（支持纯文本 / 文本+图片）──
    if request.images:
        # OpenAI Vision API 格式的多模态 content
        multimodal_content: list[dict] = [
            {"type": "text", "text": request.content}
        ]
        for img in request.images:
            data_url = f"data:{img.mime_type};base64,{img.base64}"
            multimodal_content.append({
                "type": "image_url",
                "image_url": {"url": data_url},
            })
        user_msg = HumanMessage(content=multimodal_content)
    else:
        user_msg = HumanMessage(content=request.content)

    config = {"configurable": {"thread_id": f"user-{user_id}"}, "recursion_limit": 50}

    # 从 checkpoint 恢复 teaching_context（跨轮次持久化）
    prev_teaching_ctx = None
    try:
        snapshot = await asyncio.to_thread(graph.get_state, config)
        if snapshot and snapshot.values:
            prev_teaching_ctx = snapshot.values.get("teaching_context")
            if prev_teaching_ctx and prev_teaching_ctx.get("mode") == "teaching":
                logger.info("SSE: 恢复教学流程 state (current=%d/%d)",
                            prev_teaching_ctx.get("current_index", 0) + 1,
                            len(prev_teaching_ctx.get("active_path", [])))
    except Exception as _e:
        logger.debug("SSE: 获取 checkpoint 教学状态失败（新用户正常）: %s", _e)

    initial_state = {
        "messages": history_msgs + [user_msg],
        "current_agent": "supervisor",
        "next_agent": None,
        "user_profile": _load_profile(user_id),
        "context": {"topic_context": topic_ctx},
        "agent_outputs": {},
        "stream_buffer": "",
        "user_id": user_id,
        "teaching_context": prev_teaching_ctx,
    }

    if user_id:
        with get_session() as db:
            db.add(Conversation(user_id=user_id, role="user", content=request.content))

    async def event_stream():
        prev_agent = "supervisor"
        assistant_content = ""
        assistant_agent = ""
        _captured_outputs = {}
        _agent_switch_count = 0

        try:
            async for update in graph.astream(initial_state, config, stream_mode="updates"):
                for node_name, node_update in update.items():
                    if node_name == "__end__":
                        continue
                    agent_name = node_name

                    if agent_name != prev_agent:
                        _agent_switch_count += 1
                        yield f"event: agent_switch\ndata: {json.dumps({'from': prev_agent, 'to': agent_name}, ensure_ascii=False)}\n\n"
                        prev_agent = agent_name
                        # Only track worker agents as the "assistant agent" — supervisor is a router
                        if agent_name != "supervisor":
                            assistant_agent = agent_name

                    agent_output = node_update.get("agent_outputs", {})
                    if agent_output:
                        _captured_outputs.update(agent_output)

                    _resource_meta = agent_output.get(agent_name, {})
                    if _resource_meta and "type" in _resource_meta and agent_name == "resource_agent":
                        _res_payload = json.dumps({
                            "type": "resource",
                            "resource_type": _resource_meta.get("type", "document"),
                            "title": _resource_meta.get("title") or _resource_meta.get("topic", "学习资源"),
                        }, ensure_ascii=False)
                        yield f"event: resource\ndata: {_res_payload}\n\n"

                    pending = agent_output.get(agent_name, {}).get("stream_pending")
                    if pending:
                        try:
                            from app.utils.content_guard import StreamGuard
                            guard = StreamGuard()
                            chunk_count = 0
                            estimated_total = max(1, pending.get("max_tokens", 2048) // 3)
                            yield f"event: progress\ndata: {json.dumps({'stage': 'generating', 'agent': agent_name, 'progress': 0, 'message': '正在生成...'}, ensure_ascii=False)}\n\n"
                            async for chunk in _bridge_stream(
                                spark,
                                pending["messages"],
                                pending.get("temperature", 0.7),
                                pending.get("max_tokens", 2048),
                                use_safe=pending.get("use_safe", False),
                                chunk_size=pending.get("chunk_size", 2),
                            ):
                                if chunk:
                                    safe_chunk = guard.feed(chunk)
                                    if safe_chunk is not None:
                                        assistant_content += safe_chunk
                                        chunk_count += 1
                                        yield f"event: message\ndata: {json.dumps({'content': safe_chunk, 'agent': agent_name}, ensure_ascii=False)}\n\n"
                                        if chunk_count % 50 == 0:
                                            pct = min(90, int(chunk_count / estimated_total * 100))
                                            yield f"event: progress\ndata: {json.dumps({'stage': 'generating', 'agent': agent_name, 'progress': pct}, ensure_ascii=False)}\n\n"
                            if guard.blocked:
                                logger.warning("SSE: %s 输出被内容安全守卫拦截", agent_name)
                                safe_fallback = guard.get_safe_content()
                                assistant_content = safe_fallback
                                yield f"event: message\ndata: {json.dumps({'content': safe_fallback, 'agent': agent_name}, ensure_ascii=False)}\n\n"
                            yield f"event: progress\ndata: {json.dumps({'stage': 'complete', 'agent': agent_name, 'progress': 100}, ensure_ascii=False)}\n\n"
                        except Exception as stream_err:
                            logger.warning("SSE: %s 流式输出异常: %s", agent_name, stream_err)
                            error_msg = f"\n（{agent_name} 输出中断，请稍后重试）"
                            assistant_content += error_msg
                            yield f"event: message\ndata: {json.dumps({'content': error_msg, 'agent': agent_name}, ensure_ascii=False)}\n\n"
                        continue

                    buf = node_update.get("stream_buffer", "")
                    if buf:
                        from app.utils.content_guard import get_guard
                        guard = get_guard()
                        safe, warning = guard.check(buf)
                        if safe:
                            assistant_content += buf
                            yield f"event: message\ndata: {json.dumps({'content': buf, 'agent': agent_name}, ensure_ascii=False)}\n\n"
                        else:
                            safe_msg = guard.get_safe_content() if hasattr(guard, 'get_safe_content') else "抱歉，生成的内容未通过安全检查。请换一种方式提问。"
                            assistant_content += safe_msg
                            yield f"event: message\ndata: {json.dumps({'content': safe_msg, 'agent': agent_name}, ensure_ascii=False)}\n\n"

            yield f"event: done\ndata: {json.dumps({'status': 'complete', 'agent_switches': _agent_switch_count})}\n\n"

            if user_id and assistant_content:
                with get_session() as db2:
                    db2.add(Conversation(user_id=user_id, role="assistant", content=assistant_content, agent_type=assistant_agent))
                _persist_agent_output(assistant_agent, assistant_content, user_id, _captured_outputs)
                # v3: 事件驱动闭环 — Agent完成后自动触发下游
                _post_agent_event_hook(assistant_agent, user_id, _captured_outputs)
                _extract_and_boost(user_id, request.content)
                _silent_profile_collect(user_id, request.content)

            # v4: 推送智能建议 (SSE suggestion事件) — 前端弹窗提醒下一步操作
            if user_id and assistant_agent:
                try:
                    profile = _load_profile(user_id)
                    sg_list = (profile or {}).get('suggestions', []) or []
                    if sg_list:
                        latest = sg_list[-1]
                        yield f"event: suggestion\ndata: {json.dumps(latest, ensure_ascii=False)}\n\n"
                except Exception:
                    pass

        except Exception as e:
            logger.error("SSE: event_stream 异常: %s", e)
            err_type = type(e).__name__
            err_msg = str(e)
            if "timeout" in err_msg.lower() or "超时" in err_msg:
                user_friendly = "请求超时了~ 处理时间较长，请稍后再试。"
            elif "token" in err_msg.lower() or "limit" in err_msg.lower():
                user_friendly = "内容过长啦~ 能不能简化一下问题？"
            else:
                user_friendly = "处理过程中遇到了一点问题，请稍后重试。"
            yield f"event: error\ndata: {json.dumps({'message': user_friendly, 'detail': err_msg[:200]}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
