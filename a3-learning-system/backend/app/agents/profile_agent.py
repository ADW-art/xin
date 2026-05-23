"""
Profile Agent — 对话式采集 6 维学习画像

工作流程：
1. 检查当前画像哪些维度已填
2. 针对空白维度生成自然对话提问（每次只问 1-2 个）
3. 用星火 API 从用户回复中提取结构化数据
4. 更新画像 → 流式输出回复 → 回到 Supervisor
5.即使 AI 抽风返回了非法 JSON,也不会崩,只是跳过当前维度
"""

import json
import logging

from app.agents.state import AgentState
from app.core.database import SessionLocal #会话工厂
from app.models.profile import LearningProfile #画像orm模型
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)

# 6 个维度及其引导提问（按优先级排列）
DIMENSION_QUESTIONS = [
    ("knowledge_base", "你之前学过哪些相关内容？比如编程语言、数学基础，自评掌握程度 1-10 分"),
    ("cognitive_style", "你更喜欢通过什么方式学习？看视频、读文档、动手做项目、还是听讲解？"),
    ("learning_goal", "你学习的主要目标是什么？考试拿高分、找工作、技能提升、还是纯粹兴趣？"),
    ("weekly_hours", "你每周大概能投入多少小时来学习？"),
    ("preferred_resource_type", "你最喜欢哪种学习材料？文档资料、思维导图、代码案例、还是视频教程？"),
    ("error_patterns", "回顾你之前的学习经历，有没有经常混淆或犯错的知识点？"),
]

# 结构化提取 Prompt
EXTRACT_PROMPT = """你是一个学习画像分析专家。根据用户的回复，提取对应的维度信息，返回 JSON。

当前正在采集的维度：{dimension}
维度说明：{description}

用户说：{user_input}

提取规则：
- 如果能从用户话中提取出有效信息，填写对应字段
- cognitive_style 可选值：visual / auditory / kinesthetic / reading
- learning_goal 可选值：exam / skill / career / interest
- preferred_resource_type 可选值：video / text / code / interactive
- knowledge_base 格式：{"知识点名": 自评分数, ...}
- 如果用户说"不知道"、"随便"、"不清楚"，填 null
- 如果用户答非所问，填 null

请只返回一行 JSON：{"field": "维度名", "value": ...}"""


def profile_agent_node(state: AgentState, spark: SparkClient) -> dict:
    """画像采集 Agent 的主逻辑"""
    profile = state.get("user_profile") or {}#读取已有画像
    last_msg = state["messages"][-1].content if state["messages"] else "" #读取最新消息
    buffered_reply = ""

    # 1. 找出第一个未填写的维度（空/null/不存在）
    next_dimension = None
    for key, question in DIMENSION_QUESTIONS: #维度-对应prompt
        if key not in profile or profile[key] is None or profile[key] == "": #如果维度不在/null/空
            next_dimension = (key, question)
            break #跳出，一次只填一个维度

    # 2. 如果有未填维度，问下一个
    if next_dimension:
        key, question = next_dimension

        if len(profile) == 0: #历史记录为空
            # 第一次对话 → 先自我介绍
            buffered_reply = (
                f"你好！我是你的 AI 学习助手。为了更好地给你定制学习计划，"
                f"我想先了解一下你的情况。\n\n{question}"
            )
        else:
            # 从上一条用户回复中提取结构化数据
            try:
                #构造prompt，把信息打包
                extract_messages = [
                    {"role": "system", "content": EXTRACT_PROMPT.format(
                        dimension=key, description=question, user_input=last_msg
                    )},
                ]
                raw = spark.chat_sync(extract_messages, temperature=0.2) #获取完整结果->同步模式
                extracted = json.loads( #解析json
                    raw.strip().removeprefix("```json").removesuffix("```").strip()
                )
                if extracted.get("value") is not None:
                    profile[key] = extracted["value"] #填入对应画像内容
                    logger.info("ProfileAgent: 采集到 %s = %s", key, extracted["value"])
            except Exception as e:
                logger.warning("ProfileAgent: JSON 解析失败，跳过当前维度: %s", e)

            # 取生成器的第一个值，没有就返回none
            still_need = next(
                (d for d in DIMENSION_QUESTIONS if d[0] not in profile or profile[d[0]] is None),
                None,
            )
            #没填完，填下一个
            if still_need:
                buffered_reply = f"好的收到了！接下来，{still_need[1]}"
            else:
                # 全部填完了 → 总结
                buffered_reply = _build_summary(profile)

    # 3. 全部已采集 → 总结 + 写入 MySQL
    else:
        _save_to_db(state.get("user_id", 0), profile) #写入mysql
        buffered_reply = _build_summary(profile)

    # 全部维度已填完 → 持久化
    #all()写法只要有一个不满足就返回false
    all_filled = all(
        key in profile and profile[key] is not None and profile[key] != ""
        for key, _ in DIMENSION_QUESTIONS
    )
    if all_filled:
        _save_to_db(state.get("user_id", 0), profile)

    return {
        "current_agent": "profile_agent",
        "user_profile": profile, #更新后的画像
        "stream_buffer": buffered_reply, #总结文案
        "agent_outputs": {**state.get("agent_outputs", {}), "profile_agent": profile},#更新
        #**解包操作符->展开旧数据  叠加新数据
    }


#画像写入sql
def _save_to_db(user_id: int, profile: dict):
    """将采集完成的画像写入 MySQL"""
    if not user_id:
        return
    db = SessionLocal() #创建数据库会话
    try:
        row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()#是否有画像
        if not row:
            row = LearningProfile(user_id=user_id) #创建画像
            db.add(row)
        for key, _ in DIMENSION_QUESTIONS: #元组(字段：文案)
            if key in profile and profile[key] is not None: #检查存在且不为空
                setattr(row, key, profile[key]) #row.key=profile[key] 写入数据库
        db.commit()
        logger.info("ProfileAgent: 画像已存入 MySQL user_id=%d", user_id)
    except Exception as e:
        db.rollback()#失败回滚
        logger.error("ProfileAgent: MySQL 写入失败: %s", e)
    finally:
        db.close() #关闭会话

#前端显示总结文案
def _build_summary(profile: dict) -> str:
    """生成画像总结文案"""
    lines = ["你的学习画像已更新，来确认一下：\n"]
    lines.append(f"知识基础：{profile.get('knowledge_base', '未填写')}") #安全取值，null就填后面的
    lines.append(f"认知风格：{profile.get('cognitive_style', '未填写')}")
    lines.append(f"学习目标：{profile.get('learning_goal', '未填写')}")
    lines.append(f"每周时间：{profile.get('weekly_hours', '未填写')} 小时")
    lines.append(f"偏好资源：{profile.get('preferred_resource_type', '未填写')}")
    lines.append(f"易错模式：{profile.get('error_patterns', '未填写')}")
    lines.append("\n如果有需要修改的，随时告诉我！")
    return "\n".join(lines)
