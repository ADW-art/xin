"""
Supervisor: 教学继续信号检测 + 关键词兜底路由 + 主动建议

测试覆盖:
- _is_teaching_continue  — 确认/继续信号识别 (短确认/否定/复合消息)
- _keyword_fallback      — 10组关键歧义消解用例 (resource/question/evaluation/path/profile/chat)
- _proactive_suggest     — 教学完成后的主动调度建议

纯函数测试，无需数据库/网络/LLM 调用。

注意: _keyword_fallback 的完整测试在 test_supervisor_routing.py 中，
      本文件只补测关键歧义消解用例和未覆盖的 _is_teaching_continue / _proactive_suggest。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.supervisor import _keyword_fallback, _is_teaching_continue, _proactive_suggest


# ═══════════════════════════════════════════════════════════════
# _is_teaching_continue — 教学流程继续信号检测
# ═══════════════════════════════════════════════════════════════

class TestTeachingContinue:
    """检测 _is_teaching_continue 对教学继续信号的识别"""

    def test_accept_short_confirm_cn(self):
        """简短中文确认词"""
        assert _is_teaching_continue("好") is True
        assert _is_teaching_continue("好的") is True
        assert _is_teaching_continue("可以") is True
        assert _is_teaching_continue("行") is True
        assert _is_teaching_continue("来") is True
        assert _is_teaching_continue("开始") is True
        assert _is_teaching_continue("没问题") is True
        assert _is_teaching_continue("嗯") is True
        assert _is_teaching_continue("是") is True
        assert _is_teaching_continue("对") is True

    def test_accept_continue_signals_cn(self):
        """含'继续'关键词的短消息 (len ≤ 10)"""
        assert _is_teaching_continue("继续") is True
        assert _is_teaching_continue("下一个") is True
        assert _is_teaching_continue("下一节") is True
        assert _is_teaching_continue("接着") is True
        assert _is_teaching_continue("继续学") is True
        assert _is_teaching_continue("往下学") is True
        assert _is_teaching_continue("学下一个") is True
        assert _is_teaching_continue("继续吧") is True
        assert _is_teaching_continue("下一个吧") is True  # len=5, 含"下一个"

    def test_accept_confirm_en(self):
        """英文确认信号"""
        assert _is_teaching_continue("ok") is True
        assert _is_teaching_continue("OK") is True
        assert _is_teaching_continue("yes") is True
        assert _is_teaching_continue("sure") is True
        assert _is_teaching_continue("yep") is True
        assert _is_teaching_continue("yeah") is True
        assert _is_teaching_continue("go on") is True
        assert _is_teaching_continue("next") is True
        assert _is_teaching_continue("continue") is True

    def test_reject_not_in_list(self):
        """不在精确匹配列表中的单字 → 不是继续信号"""
        # "不" "别" "停" 等不在正则匹配列表中
        assert _is_teaching_continue("不") is False
        assert _is_teaching_continue("别") is False
        assert _is_teaching_continue("停") is False

    def test_reject_compound_message(self):
        """含额外内容的复合消息 (>10 字符或非精确匹配)"""
        assert _is_teaching_continue("好的，但是我想先复习一下前面的内容") is False
        assert _is_teaching_continue("可以，不过能不能慢一点") is False

    def test_reject_learning_request(self):
        """学习请求不是继续信号"""
        assert _is_teaching_continue("教我Python") is False
        assert _is_teaching_continue("我想学数据结构") is False

    def test_reject_empty(self):
        """空字符串不是继续信号"""
        assert _is_teaching_continue("") is False

    def test_continue_with_spaces(self):
        """带首尾空格的确认信号 (正则中有 strip)"""
        assert _is_teaching_continue("  好的  ") is True
        assert _is_teaching_continue("  ok  ") is True


# ═══════════════════════════════════════════════════════════════
# _keyword_fallback — 歧义消解关键用例
# (test_supervisor_routing.py 已覆盖大部分, 这里只补关键歧义场景和边界)
# ═══════════════════════════════════════════════════════════════

class TestSupervisorRoutingDisambiguation:
    """记录关键的意图歧义消解规则，防止回归

    _keyword_fallback 优先级顺序:
    evaluation > question > path > profile > resource > chat(兜底)

    关键词匹配使用 Python `in` 检查子串包含，
    这要求触发词必须是输入字符串的连续子串。
    """

    def test_teach_triggers_resource(self):
        """'教我' → resource"""
        assert _keyword_fallback("教我Python装饰器")["intent"] == "resource"

    def test_exercise_triggers_question(self):
        """'出题' → question (早于 resource 检查)"""
        assert _keyword_fallback("出3道数据结构题")["intent"] == "question"

    def test_evaluate_triggers_evaluation(self):
        """'评估' → evaluation (最高优先级)"""
        assert _keyword_fallback("评估我的学习情况")["intent"] == "evaluation"

    def test_plan_triggers_path(self):
        """'规划路线' → path"""
        assert _keyword_fallback("帮我规划C++学习路线")["intent"] == "path"

    def test_profile_with_contiguous_keyword(self):
        """自述背景: 关键词必须是连续子串
        "我是做前端开发的" 含 "我是做" → profile
        "我零基础" 作为连续子串 → profile
        """
        assert _keyword_fallback("我是做前端开发的")["intent"] == "profile"
        assert _keyword_fallback("我零基础可以学吗")["intent"] == "profile"
        assert _keyword_fallback("我是初学者")["intent"] == "profile"

    def test_profile_with_intervening_chars_falls_to_chat(self):
        """关键词被插入字符打断 → 不匹配
        "我是零基础初学者" 不包含 "我是初学者" 或 "我零基础" 作为连续子串
        (因为"零基础"几个字隔开了"我是"和"初学者")
        → 所有规则都不匹配 → 兜底 chat
        """
        assert _keyword_fallback("我是零基础初学者")["intent"] == "chat"

    def test_chat_fallback(self):
        """闲聊 → chat (兜底)"""
        assert _keyword_fallback("你好今天天气不错")["intent"] == "chat"

    def test_code_request_is_resource_not_question(self):
        """关键歧义消解: '写一个快速排序的代码'
        question 关键词不匹配 (无'出题'/'做题'等) → 继续
        resource 关键词 '写一个' 命中 → resource
        """
        assert _keyword_fallback("写一个快速排序的代码")["intent"] == "resource"

    def test_implement_python_with_keywords(self):
        """'实现'关键词不在任何分类列表中
        "用Python实现链表反转" 不含任何触发子串 → chat
        """
        assert _keyword_fallback("用Python实现链表反转")["intent"] == "chat"

    def test_explain_is_resource(self):
        """'解释' → resource"""
        assert _keyword_fallback("解释一下什么是闭包")["intent"] == "resource"

    def test_mindmap_request(self):
        """思维导图请求 → resource"""
        assert _keyword_fallback("画个思维导图总结Python基础")["intent"] == "resource"

    def test_diagram_request(self):
        """图解/图请求 → resource ('图解' 命中)"""
        assert _keyword_fallback("图解二叉树遍历")["intent"] == "resource"

    def test_evaluation_before_resource(self):
        """优先级验证: evaluation > resource
        "评估" 和 "掌握" 在 evaluation 检查中命中
        """
        result = _keyword_fallback("评估我的Python掌握情况")
        assert result["intent"] == "evaluation"

    def test_evaluation_keyword_trumps_question(self):
        """优先级验证: evaluation > question
        "出题测试我的Python水平" 含 evaluation 关键词 '水平'
        evaluation 先于 question 检查 → evaluation
        """
        result = _keyword_fallback("出题测试我的Python水平")
        assert result["intent"] == "evaluation"

    def test_profile_keyword_trumps_resource(self):
        """优先级验证: profile > resource
        "我是做数据挖掘的" 含 profile 关键词 '我是做'
        → profile (即使 '挖掘' 不加触发)
        """
        result = _keyword_fallback("我是做数据挖掘的")
        assert result["intent"] == "profile"


# ═══════════════════════════════════════════════════════════════
# _proactive_suggest — 主动调度建议
# ═══════════════════════════════════════════════════════════════

class TestProactiveSuggest:
    """检测 _proactive_suggest 的主动调度逻辑

    _proactive_suggest 根据上一轮 Agent 输出决定下一步:
    - resource_agent 完成后 → 推荐练题 (question)
    - evaluation_agent 完成后 → 推荐针对性学习 (resource)
    - path_agent 完成后 → 推荐开始学习 (resource)
    - profile_agent 完成 (画像 ≥ 3 维) → 推荐规划 (path)
    - question_agent 评阅后 → 根据正确率推荐学习 (resource)
    - supervisor / 未知 agent → None (不主动调度)
    """

    def test_after_resource_agent_suggests_question(self):
        """教学完成后 → 推荐练题"""
        result = _proactive_suggest("resource_agent", {"type": "document"})
        assert result is not None
        assert result["intent"] == "question"
        assert "教学后推荐练习" in result.get("reason", "")

    def test_after_evaluation_agent_suggests_resource(self):
        """评估完成后 → 推荐针对性学习"""
        result = _proactive_suggest("evaluation_agent", {})
        assert result is not None
        assert result["intent"] == "resource"
        assert "评估后推荐针对性学习" in result.get("reason", "")

    def test_after_path_agent_suggests_resource(self):
        """路径规划完成后 → 推荐开始学习"""
        result = _proactive_suggest("path_agent", {})
        assert result is not None
        assert result["intent"] == "resource"
        assert "规划后推荐开始学习" in result.get("reason", "")

    def test_profile_with_enough_data_suggests_path(self):
        """画像采集完成 (≥ 3 维) → 推荐规划"""
        result = _proactive_suggest("profile_agent", {
            "profile_data": {"knowledge": 60, "goal": "exam", "hours": 10}
        })
        assert result is not None
        assert result["intent"] == "path"

    def test_profile_with_insufficient_data_returns_none(self):
        """画像采集不足 → 不主动调度"""
        result = _proactive_suggest("profile_agent", {
            "profile_data": {"knowledge": 60}  # only 1 dimension
        })
        assert result is None

    def test_question_grade_high_mastery_suggests_resource(self):
        """评阅后正确率高 → 推荐进阶"""
        result = _proactive_suggest("question_agent", {
            "mode": "grade",
            "bkt_p_known": 0.85,
        })
        assert result is not None
        assert result["intent"] == "resource"

    def test_question_grade_low_mastery_suggests_resource(self):
        """评阅后正确率低 → 推荐复习"""
        result = _proactive_suggest("question_agent", {
            "mode": "grade",
            "bkt_p_known": 0.35,
        })
        assert result is not None
        assert result["intent"] == "resource"

    def test_question_generate_mode_returns_none(self):
        """出题模式 (非评阅) → 不主动调度"""
        result = _proactive_suggest("question_agent", {
            "mode": "generate",
        })
        assert result is None

    def test_supervisor_returns_none(self):
        """supervisor 自身 → 不主动调度"""
        assert _proactive_suggest("supervisor", {}) is None

    def test_unknown_agent_returns_none(self):
        """未知 agent 名称 → 不主动调度"""
        assert _proactive_suggest("unknown_agent", {}) is None
