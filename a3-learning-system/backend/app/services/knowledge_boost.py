"""Knowledge graph entity extraction and profile boosting"""

import logging
import re
from app.core.database import get_session
from app.core.shared_utils import _normalize_concept_name, _structure_knowledge_base
from app.models.profile import LearningProfile

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
        row.dimension_scores = _compute_dimension_scores(pdict, user_id)
        flag_modified(row, "dimension_scores")
    except Exception:
        pass  # 非关键路径，不影响主流程
