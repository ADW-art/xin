"""
Profile Agent — 对话式采集 6 维学习画像

v2: 规则提取 + LLM提取混合模式
  - 规则提取(快速): 学习时长/学习目标/认知风格/偏好资源
  - LLM提取(精准): 知识基础
"""

import json
import logging
import random
import re

from app.agents.state import AgentState
from app.core.database import SessionLocal
from app.core.shared_utils import _structure_knowledge_base
from app.models.profile import LearningProfile
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)

# 知识库提取黑名单：非技术词、prompt 中出现的元词汇
KB_BLACKLIST = {
    "时间", "小时", "目标", "基础", "程度", "掌握程度", "自评",
    "编程语言", "数学", "数学基础", "内容", "入门", "初学者",
    "学习", "经验", "项目", "工作", "考试", "技能", "兴趣",
    "了解", "熟悉", "掌握", "精通", "知道", "学过", "做过",
    "每周", "每天", "投入", "安排", "方式", "风格", "偏好",
}

DIMENSION_QUESTIONS = [
    ("knowledge_base", "你之前学过哪些相关内容？比如编程语言、数学基础，自评掌握程度 1-10 分"),
    ("learning_goal", "你学习的主要目标是什么？考试拿高分、找工作、技能提升、还是纯粹兴趣？"),
    ("weekly_hours", "你每周大概能投入多少小时来学习？"),
    ("cognitive_style", "你更喜欢通过什么方式学习？看视频、读文档、动手做项目、还是听讲解？"),
    ("preferred_resource_type", "你最喜欢哪种学习材料？文档资料、思维导图、代码案例、还是视频教程？"),
    ("error_patterns", "回顾你之前的学习经历，有没有经常混淆或犯错的知识点？"),
]

EXTRACT_PROMPT = """你是一个学习画像分析专家。根据用户的回复，提取对应的维度信息，返回 JSON。

当前正在采集的维度：{dimension}
维度说明：{description}

用户说：{user_input}

提取规则：
- 如果能从用户话中提取出有效信息，填写对应字段
- cognitive_style 可选值：visual / auditory / kinesthetic / reading
- learning_goal 可选值：exam / skill / career / interest
- preferred_resource_type 可选值：video / text / code / interactive
- knowledge_base 格式：{{"知识点名": 自评分数, ...}}
- 如果用户说"不知道"、"随便"、"不清楚"，填 null

请只返回一行 JSON：{{"field": "维度名", "value": ...}}"""


def _save_to_db(user_id: int, profile: dict):
    if not user_id:
        return
    db = SessionLocal()
    try:
        row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
        if not row:
            row = LearningProfile(user_id=user_id)
            db.add(row)
        for key, _ in DIMENSION_QUESTIONS:
            if key in profile and profile[key] is not None:
                setattr(row, key, profile[key])
        kb_raw = profile.get("knowledge_base")
        if kb_raw and isinstance(kb_raw, str):
            row.knowledge_base = _structure_knowledge_base(kb_raw)
        row.dimension_scores = _compute_dimension_scores(profile)
        db.commit()
        logger.info("ProfileAgent: 画像已存入 MySQL user_id=%d", user_id)

        # 同步 Profile → BKT：新概念用画像自评分初始化 BKT 先验
        kb = profile.get("knowledge_base")
        if kb and isinstance(kb, dict) and len(kb) > 0:
            try:
                from app.services.bkt_service import sync_profile_to_bkt
                sync_profile_to_bkt(user_id, kb)
            except Exception as e:
                logger.warning("ProfileAgent: Profile→BKT 同步失败: %s", e)
    except Exception as e:
        db.rollback()
        logger.error("ProfileAgent: MySQL 写入失败: %s", e)
    finally:
        db.close()


def _compute_dimension_scores(profile: dict) -> dict:
    import re as _re
    kb_raw = str(profile.get("knowledge_base", "") or "")
    kb_topics = [t.strip() for t in _re.split(r"[,，、;；/]", kb_raw) if t.strip()]
    topic_count = len(kb_topics)
    tech_keywords = ["python", "java", "javascript", "c++", "go", "rust", "sql", "html", "css",
                     "react", "vue", "django", "flask", "spring", "算法", "数据结构", "机器学习",
                     "深度学习", "前端", "后端", "数据库", "linux", "docker"]
    has_tech = any(any(kw in t.lower() for kw in tech_keywords) for t in kb_topics)
    knowledge_score = min(95, 30 + topic_count * 12 + (25 if has_tech else 0))
    if "入门" in kb_raw or "零基础" in kb_raw or "没学过" in kb_raw:
        knowledge_score = min(knowledge_score, 35)

    style = str(profile.get("cognitive_style", "") or "").lower()
    logic_score = 78 if any(w in style for w in ["逻辑","推理","分析","系统"]) else \
                  58 if any(w in style for w in ["视觉","图像","图表","直观"]) else \
                  52 if any(w in style for w in ["动手","实践","操作"]) else 62

    hours = float(profile.get("weekly_hours") or 0)
    goal = str(profile.get("learning_goal", "") or "").lower()
    practice_score = min(90, 25 + int(hours * 7))
    if any(w in goal for w in ["项目","实战","工作","求职","面试"]):
        practice_score = min(95, practice_score + 15)
    elif any(w in goal for w in ["兴趣","了解","入门"]):
        practice_score = max(30, practice_score - 10)

    pref = str(profile.get("preferred_resource_type", "") or "").lower()
    speed_score = 72 if pref in ["video","视频"] else 65 if pref in ["code","代码"] else 78 if pref in ["interactive","交互"] else 60

    err = str(profile.get("error_patterns", "") or "")
    focus_score = 75 if (not err or err in ["无","暂无"]) else max(30, 70 - len(_re.split(r"[,，、;；]", err)) * 8)

    overall_score = round(knowledge_score*0.25 + logic_score*0.18 + practice_score*0.22 + speed_score*0.15 + focus_score*0.20, 1)

    return {
        "knowledge": round(knowledge_score, 1), "logic": round(logic_score, 1),
        "practice": round(practice_score, 1), "speed": round(speed_score, 1),
        "focus": round(focus_score, 1), "overall": round(overall_score, 1),
    }


def _build_summary(profile: dict) -> str:
    """生成画像采集完成的自然总结，并给出个性化下一步建议"""
    lines = ["## 你的学习画像已就绪\n"]

    # 简短概述，不用生硬的表格
    kb_val = profile.get('knowledge_base', '')
    kb_display = ''
    if isinstance(kb_val, dict) and kb_val:
        kb_items = [f"{k}（自评 {int(v) if isinstance(v, float) and v == int(v) else v} 分）" for k, v in list(kb_val.items())[:4]]
        kb_display = '、'.join(kb_items)
    elif isinstance(kb_val, str) and kb_val.strip():
        kb_display = kb_val.strip()
    else:
        kb_display = '待补充'

    style_map = {"visual": "视觉型（喜欢看视频/图示）", "auditory": "听觉型（喜欢听讲解）",
                 "kinesthetic": "动手型（喜欢写代码/做项目）", "reading": "阅读型（喜欢看文档/书籍）"}
    goal_map = {"exam": "考试拿高分", "skill": "技能提升", "career": "找工作/求职", "interest": "兴趣探索"}
    pref_map = {"video": "视频教程", "text": "文档资料", "code": "代码案例", "interactive": "互动练习"}

    style_display = style_map.get(str(profile.get('cognitive_style', '')).lower(), profile.get('cognitive_style', '待补充'))
    goal_display = goal_map.get(str(profile.get('learning_goal', '')).lower(), profile.get('learning_goal', '待补充'))
    pref_display = pref_map.get(str(profile.get('preferred_resource_type', '')).lower(), profile.get('preferred_resource_type', '待补充'))
    hours_display = f"{profile.get('weekly_hours', '待补充')} 小时/周"

    lines.append(f"你的知识基础主要是 {kb_display}，偏好 {style_display} 的学习方式，目标是 {goal_display}，每周能投入约 {hours_display}。")
    lines.append(f"最喜欢的学习材料是 {pref_display}。")

    err = str(profile.get('error_patterns', '') or '')
    if err and err not in ('无', '暂无', 'None', ''):
        lines.append(f"易错方面：{err}，后续会重点关注。")

    # 主动引导：根据画像内容给出个性化建议
    goal = str(profile.get('learning_goal', '') or '')
    kb = str(profile.get('knowledge_base', '') or '')

    lines.append("")
    if '找工作' in goal or '面试' in goal or '求职' in goal or goal == 'career':
        lines.append("> 了解了你的求职目标，我建议先从一次全面评估开始，看看当前水平和目标岗位的差距在哪里。要不要现在评估一下？回复「评估」就行~")
    elif '考试' in goal or goal == 'exam':
        lines.append("> 针对考试目标，我建议先制定一个系统的复习计划，然后重点突破高频考点。要我帮你规划一下吗？回复「规划」就好~")
    elif '入门' in kb or '零基础' in kb or '初学' in kb:
        lines.append("> 看起来你是刚入门，我建议先来几道简单的基础题感受一下水平，然后从最基础的概念开始系统学。要试试吗？说「出题」就开始~")
    else:
        lines.append("> 画像已经就绪！想从哪开始？评估当前水平、制定学习计划、还是直接学新知识，告诉我就好~")

    return "\n".join(lines)


def profile_agent_node(state: AgentState, spark: SparkClient) -> dict:
    state = dict(state)  # TypedDict → dict
    profile = state.get("user_profile") or {}
    last_msg = state["messages"][-1].content if state["messages"] else ""
    buffered_reply = ""

    unfilled = [(k, q) for k, q in DIMENSION_QUESTIONS
                if k not in profile or profile[k] is None or profile[k] == ""]

    if unfilled:
        extracted_any = False

        # ── 规则提取（快速、可靠）──
        # 学习时长
        if "weekly_hours" in dict(unfilled):
            for pat in [r'(\d+)\s*小时', r'(\d+)[-~至](\d+)\s*小时', r'每天\s*(\d+)\s*小时', r'每周\s*(\d+)']:
                m = re.search(pat, last_msg)
                if m:
                    hrs = float(m.group(1))
                    profile["weekly_hours"] = hrs
                    extracted_any = True
                    logger.info("ProfileAgent: 规则提取 weekly_hours=%s", hrs)
                    break

        # 学习目标
        if "learning_goal" in dict(unfilled):
            for goal, kws in [("career", ["找工作","求职","转行","面试","入职","上班","工作"]),
                              ("exam", ["考试","考研","考证","高考","考级"]),
                              ("skill", ["技能","提升","提高","学.*技术","掌握"]),
                              ("interest", ["兴趣","好奇","了解","随便学","爱好"])]:
                if any(kw in last_msg for kw in kws):
                    profile["learning_goal"] = goal
                    extracted_any = True
                    logger.info("ProfileAgent: 规则提取 learning_goal=%s", goal)
                    break

        # 认知风格
        if "cognitive_style" in dict(unfilled):
            for style, kws in [("visual", ["看视频","视频","观看","图示"]),
                               ("reading", ["读文档","看书","阅读","文档","书本"]),
                               ("kinesthetic", ["动手","写代码","练习","项目","操作","做"]),
                               ("auditory", ["听","讲解","听课","音频","讲座"])]:
                if any(kw in last_msg for kw in kws):
                    profile["cognitive_style"] = style
                    extracted_any = True
                    logger.info("ProfileAgent: 规则提取 cognitive_style=%s", style)
                    break

        # 偏好资源类型
        if "preferred_resource_type" in dict(unfilled):
            for ptype, kws in [("video", ["视频","录像"]), ("text", ["文档","书籍","书本","文章"]),
                               ("code", ["代码","案例","示例","例子"]), ("interactive", ["交互","练习","题目","刷题"])]:
                if any(kw in last_msg for kw in kws):
                    profile["preferred_resource_type"] = ptype
                    extracted_any = True
                    logger.info("ProfileAgent: 规则提取 preferred_resource_type=%s", ptype)
                    break

        # ── LLM 提取 知识基础 ──
        if "knowledge_base" in dict(unfilled):
            if any(kw in last_msg for kw in ["学过","基础","了解","熟悉","掌握","懂","会","知道","入门","初学者","零基础","经验","年"]):
                try:
                    extract_messages = [
                        {"role": "system", "content": EXTRACT_PROMPT.format(
                            dimension="knowledge_base",
                            description="提取用户的知识基础，返回JSON如 {\"knowledge_base\": {\"Python\": 8}}",
                            user_input=last_msg
                        )},
                    ]
                    from app.utils.llm_helper import safe_chat_sync
                    raw = safe_chat_sync(spark, extract_messages, temperature=0.2, max_tokens=256,
                                        fallback='{"field":"knowledge_base","value":null}', retries=2)
                    extracted = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
                    val = extracted.get("value")
                    if val is None and "knowledge_base" in extracted:
                        val = extracted["knowledge_base"]
                    if val and isinstance(val, dict) and len(val) > 0:
                        clean_val = {
                            k: v for k, v in val.items()
                            if isinstance(v, (int, float))
                            and len(str(k)) >= 2
                            and not k.isdigit()
                            and str(k) not in KB_BLACKLIST
                            and not any(bl in str(k) for bl in ["小时", "分钟", "每天", "每周"])
                        }
                        if clean_val:
                            profile["knowledge_base"] = clean_val
                            extracted_any = True
                            logger.info("ProfileAgent: LLM提取 knowledge_base=%s", clean_val)
                except Exception as e:
                    logger.warning("ProfileAgent: LLM提取 knowledge_base 失败: %s", e)

            # If LLM extraction returned empty or was filtered out, try regex fallback
            if "knowledge_base" not in profile or not profile.get("knowledge_base"):
                fallback_kb = {}
                skill_patterns = [
                    r'(?:学过|熟悉|掌握|精通|会|懂|了解|用过)[的]?\s*([A-Za-z+#]{2,20}|[一-鿿]{2,8})',
                    r'(\d+)年\s*([A-Za-z+#]{2,20}|[一-鿿]{2,8})',
                    r'([A-Za-z+#]{2,20})\s*(?:基础|入门|进阶|开发|编程)',
                ]
                for pat in skill_patterns:
                    for m in re.findall(pat, last_msg):
                        skill = m.strip() if isinstance(m, str) else m[-1].strip()
                        if skill and len(skill) >= 2 and skill not in KB_BLACKLIST:
                            fallback_kb[skill] = 60  # default confidence for regex match
                if fallback_kb:
                    profile["knowledge_base"] = fallback_kb
                    extracted_any = True
                    logger.info("ProfileAgent: 正则回退提取 knowledge_base=%s", fallback_kb)

        # ── 持久化 + 生成回复 ──
        still_unfilled = [(k, q) for k, q in DIMENSION_QUESTIONS
                          if k not in profile or profile[k] is None or profile[k] == ""]

        if still_unfilled:
            if extracted_any:
                # 增量持久化：仍有维度待采集，先保存已有数据防止丢失
                _save_to_db(state.get("user_id", 0), profile)
                next_dim, next_q = still_unfilled[0]
                # 自然过渡：根据下一个要问的维度生成不同的过渡语（已包含完整提问）
                transitions = {
                    "knowledge_base": ["了解了！方便说说你之前学过哪些内容吗？比如编程语言、数学基础之类的~", "好的~那你之前有接触过编程或相关课程吗？"],
                    "learning_goal": ["记下了。那你这次学习主要是为了什么呢？考试、找工作还是兴趣？", "明白了！方便说说你的学习目标吗？"],
                    "weekly_hours": ["收到~那你每周大概能抽出多少时间来学习呢？", "了解！平时一周能投入多少小时在学习上？"],
                    "cognitive_style": ["好的！你平时更喜欢看视频学、看书学、还是动手做项目学？", "记下了。学习方式上你是视觉型还是动手型呀？"],
                    "preferred_resource_type": ["嗯嗯。那你最喜欢哪种学习材料？文档、代码示例还是视频？", "理解了。学习材料方面有偏好吗？"],
                    "error_patterns": ["最后一个问题~回顾之前的学习，有没有经常记混或搞错的知识点？", "差不多了！以前学习时有没有容易混淆的地方？"],
                }
                options = transitions.get(next_dim, [f"了解了！那 {next_q}"])
                opener = random.choice(options) if len(options) > 1 else options[0]
                buffered_reply = opener
            else:
                if len(profile) == 0 or all(v is None or v == "" for v in profile.values()):
                    # 首次进入画像采集 → 丰富引导
                    topic_hint = ""
                    user_msg_lower = last_msg.lower()
                    if any(kw in last_msg for kw in ["python", "java", "javascript", "c++", "go", "数据结构", "算法", "机器学习"]):
                        topic_hint = f"\n\n注意到你想学 **{last_msg[:30]}** 相关内容，我会根据这个方向来定制你的学习方案。"
                    elif any(kw in last_msg for kw in ["编程", "开发", "前端", "后端", "数据分析", "人工智能"]):
                        topic_hint = f"\n\n收到你的学习方向了！我会围绕 **{last_msg[:20]}** 来帮你规划。"

                    buffered_reply = (
                        f"你好！我是 A3 智能学习助手\n\n"
                        f"为了给你定制**个性化**的学习方案，我想先了解你几个方面：\n\n"
                        f"先从最简单的开始——{unfilled[0][1]}\n\n"
                        f"{topic_hint}"
                        f"\n> 提示：随意说就行，比如「学过Python基础」「零基础入门」「有Java工作经验」都可以"
                    )
                else:
                    # 已采集部分 → 自然追问（本轮没有提取到新信息）
                    next_dim, next_q = still_unfilled[0]
                    natural_openers = {
                        "knowledge_base": "方便说说你之前学过哪些内容吗？",
                        "learning_goal": "那你这次学习主要是为了什么呢？",
                        "weekly_hours": "对了，你每周大概能投入多少时间来学习呀？",
                        "cognitive_style": "说起来，你平时更喜欢看视频学、看书学、还是动手做项目学？",
                        "preferred_resource_type": "学习材料方面，你更喜欢文档、代码示例还是视频呢？",
                        "error_patterns": "回顾之前的学习，有没有哪些知识点你经常搞混的？",
                    }
                    opener = natural_openers.get(next_dim, next_q)
                    buffered_reply = f"{opener}"
        else:
            # 本轮采集刚好完成全部维度 → 最终持久化
            _save_to_db(state.get("user_id", 0), profile)
            buffered_reply = _build_summary(profile)
    else:
        # 画像已完整（从DB加载或先前已采集完毕），无需重复写入
        buffered_reply = _build_summary(profile)

    if not buffered_reply or not buffered_reply.strip():
        buffered_reply = "好的，已记录。请继续告诉我更多关于你的学习情况。"

    # 将静态文本拆为逐字chunk，通过stream_pending实现打字机效果
    chunks = [buffered_reply[i:i+2] for i in range(0, len(buffered_reply), 2)]
    return {
        "current_agent": "profile_agent",
        "user_profile": profile,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "profile_agent": {
                **profile,
                "stream_pending": {
                    "messages": [{"__pre_collected__": chunks, "role": "system", "content": ""}],
                    "temperature": 0,
                    "max_tokens": 0,
                    "chunk_size": 0,
                },
            },
        },
    }
