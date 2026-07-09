"""Silent profile collection — extracts knowledge from user messages"""

import logging
import re
from app.core.database import get_session
from app.models.profile import LearningProfile

logger = logging.getLogger(__name__)


def _silent_profile_collect(user_id: int, user_message: str) -> dict | None:
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
        return None

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
                    row.dimension_scores = _compute_dimension_scores(profile_dict, user_id)
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(row, "dimension_scores")
                except Exception:
                    pass  # 非关键路径
            # v3: 通知 Supervisor 画像已变更 (P1-11)
            try:
                from app.core.security import _get_redis
                r = _get_redis()
                r.setex(f"profile_dirty:{user_id}", 300, "1")
            except Exception:
                pass
    except Exception as e:
        logger.warning("静默采集失败: %s", e)
