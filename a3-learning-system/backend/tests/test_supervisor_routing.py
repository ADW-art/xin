"""
Supervisor 关键词兜底函数 _keyword_fallback 的单元测试。

测试覆盖: 资源/出题/评估/路径/画像/闲聊 6 种意图的识别准确性。

纯函数测试，无需数据库/网络/LLM 调用。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.supervisor import _keyword_fallback, supervisor_router


# ═══════════════════════════════════════════════════════════
# resource 意图测试 (A/B/C/D 四类资源触发词)
# ═══════════════════════════════════════════════════════════

def test_resource_concept_learning_cn():
    """A类: 中文概念学习"""
    assert _keyword_fallback("教我Python装饰器")["intent"] == "resource"
    assert _keyword_fallback("解释一下什么是闭包")["intent"] == "resource"
    assert _keyword_fallback("什么是面向对象")["intent"] == "resource"
    assert _keyword_fallback("讲一下SQL索引的原理")["intent"] == "resource"


def test_resource_concept_learning_en():
    """A类: 英文概念学习"""
    assert _keyword_fallback("teach me about decorators")["intent"] == "resource"
    assert _keyword_fallback("explain dynamic programming")["intent"] == "resource"
    assert _keyword_fallback("what is a closure in JavaScript")["intent"] == "resource"
    assert _keyword_fallback("how does garbage collection work")["intent"] == "resource"


def test_resource_code_generation_cn():
    """B类: 中文代码生成"""
    assert _keyword_fallback("写一个快速排序的代码")["intent"] == "resource"
    assert _keyword_fallback("写一段代码实现二叉树遍历")["intent"] == "resource"
    assert _keyword_fallback("用Python实现一个装饰器")["intent"] == "resource"
    assert _keyword_fallback("给我写一个爬虫脚本")["intent"] == "resource"


def test_resource_code_generation_en():
    """B类: 英文代码生成"""
    assert _keyword_fallback("write a function to reverse a string")["intent"] == "resource"
    assert _keyword_fallback("implement a binary search tree")["intent"] == "resource"
    assert _keyword_fallback("code example for async await")["intent"] == "resource"


def test_resource_debug_cn():
    """B类: 中文调试请求"""
    assert _keyword_fallback("这段代码为什么报错")["intent"] == "resource"
    assert _keyword_fallback("帮我debug一下这个bug")["intent"] == "resource"
    assert _keyword_fallback("错在哪 数组越界了")["intent"] == "resource"
    assert _keyword_fallback("帮我优化这段代码")["intent"] == "resource"


def test_resource_content_generation_cn():
    """C类: 中文资料生成"""
    assert _keyword_fallback("生成一份Python学习笔记")["intent"] == "resource"
    assert _keyword_fallback("制作一个知识图谱")["intent"] == "resource"
    assert _keyword_fallback("列一个Docker常用命令")["intent"] == "resource"
    assert _keyword_fallback("总结一下今天学的内容")["intent"] == "resource"
    assert _keyword_fallback("整理一下Git命令")["intent"] == "resource"


def test_resource_mindmap_cn():
    """C类: 思维导图触发词"""
    assert _keyword_fallback("画个思维导图解释二叉树")["intent"] == "resource"
    assert _keyword_fallback("画一个脑图展示数据挖掘流程")["intent"] == "resource"
    assert _keyword_fallback("生成一个思维导图")["intent"] == "resource"  # "生成"命中resource


def test_resource_comparison_cn():
    """D类: 中文对比分析"""
    assert _keyword_fallback("Python和Java的区别")["intent"] == "resource"
    assert _keyword_fallback("TCP和UDP的对比")["intent"] == "resource"
    assert _keyword_fallback("React vs Vue 优缺点")["intent"] == "resource"


def test_resource_comparison_en():
    """D类: 英文对比分析"""
    assert _keyword_fallback("difference between list and tuple")["intent"] == "resource"
    assert _keyword_fallback("compare SQL and NoSQL")["intent"] == "resource"


def test_resource_how_to_question():
    """概念性的'如何'问题 -> resource (不是出题请求)"""
    assert _keyword_fallback("如何学习Python")["intent"] == "resource"
    assert _keyword_fallback("怎么安装Docker")["intent"] == "resource"
    assert _keyword_fallback("如何实现多线程")["intent"] == "resource"


# ═══════════════════════════════════════════════════════════
# question 意图测试 (出题/练习)
# ═══════════════════════════════════════════════════════════

def test_question_generation_cn():
    """出题/练习请求"""
    assert _keyword_fallback("出3道数据结构题")["intent"] == "question"
    assert _keyword_fallback("给我出几道Python题")["intent"] == "question"
    assert _keyword_fallback("我想做题")["intent"] == "question"
    assert _keyword_fallback("来点机器学习测试题")["intent"] == "question"


def test_question_practice_cn():
    """练习/刷题"""
    assert _keyword_fallback("来几道算法题练手")["intent"] == "question"
    assert _keyword_fallback("刷题模式")["intent"] == "question"
    assert _keyword_fallback("再来一道编程题")["intent"] == "question"


def test_question_explicit_quiz_cn():
    """明确的题目数量请求（正则匹配）"""
    assert _keyword_fallback("出5道Java题目")["intent"] == "question"
    assert _keyword_fallback("给我3道Python基础题")["intent"] == "question"


def test_question_generation_en():
    """英文出题请求"""
    assert _keyword_fallback("generate 5 algorithm problems")["intent"] == "question"
    assert _keyword_fallback("give me 3 Python basic exercises")["intent"] == "question"


# ═══════════════════════════════════════════════════════════
# evaluation 意图测试
# ═══════════════════════════════════════════════════════════

def test_evaluation_cn():
    """评估/报告请求"""
    assert _keyword_fallback("评估一下我的学习情况")["intent"] == "evaluation"
    assert _keyword_fallback("给我生成一份学习报告")["intent"] == "evaluation"
    assert _keyword_fallback("我的Python水平怎么样")["intent"] == "evaluation"


def test_evaluation_progress():
    """进度检查"""
    assert _keyword_fallback("我的掌握程度如何")["intent"] == "evaluation"


def test_evaluation_en():
    """英文评估请求"""
    assert _keyword_fallback("evaluate my progress")["intent"] == "evaluation"
    assert _keyword_fallback("assess my learning")["intent"] == "evaluation"
    assert _keyword_fallback("how am i doing in Python")["intent"] == "evaluation"


# ═══════════════════════════════════════════════════════════
# path 意图测试
# ═══════════════════════════════════════════════════════════

def test_path_cn():
    """路线/计划请求"""
    assert _keyword_fallback("帮我规划学习路线")["intent"] == "path"
    assert _keyword_fallback("下一步学什么")["intent"] == "path"
    assert _keyword_fallback("学习计划怎么安排")["intent"] == "path"


def test_path_en():
    """英文路径请求"""
    assert _keyword_fallback("create a learning path for Python")["intent"] == "path"
    assert _keyword_fallback("what should i learn next")["intent"] == "path"
    assert _keyword_fallback("give me a study plan")["intent"] == "path"


# ═══════════════════════════════════════════════════════════
# profile 意图测试 (自述背景)
# ═══════════════════════════════════════════════════════════

def test_profile_beginner_cn():
    """初学者自述"""
    assert _keyword_fallback("我是初学者刚接触编程")["intent"] == "profile"
    assert _keyword_fallback("我零基础可以学吗")["intent"] == "profile"


def test_profile_background():
    """经验自述"""
    assert _keyword_fallback("我之前学过Java")["intent"] == "profile"
    assert _keyword_fallback("我是做前端开发的")["intent"] == "profile"


def test_profile_en():
    """英文背景自述"""
    assert _keyword_fallback("i am a beginner in machine learning")["intent"] == "profile"
    assert _keyword_fallback("my background is in data science")["intent"] == "profile"


# ═══════════════════════════════════════════════════════════
# chat 意图测试 (兜底/闲聊)
# ═══════════════════════════════════════════════════════════

def test_chat_fallback():
    """无明确学习意图的闲聊 -> chat"""
    assert _keyword_fallback("你好啊今天天气不错")["intent"] == "chat"
    assert _keyword_fallback("谢谢")["intent"] == "chat"
    assert _keyword_fallback("好的")["intent"] == "chat"
    assert _keyword_fallback("哈哈")["intent"] == "chat"


def test_chat_empty():
    """空消息 -> chat"""
    assert _keyword_fallback("")["intent"] == "chat"


# ═══════════════════════════════════════════════════════════
# 边界条件 / 歧义消解测试
# ═══════════════════════════════════════════════════════════

def test_priority_evaluation_over_resource():
    """'评估'关键词优先于'学习'关键词"""
    result = _keyword_fallback("帮我评估一下我对Python的掌握情况")
    assert result["intent"] == "evaluation"


def test_priority_question_over_resource():
    """'出题'关键词优先于通用resource触发词"""
    result = _keyword_fallback("教我做题，出3道Python题")
    # "出题" 先于 "教我" 被检查（evaluation > question > path > profile > resource）
    # 这里含"出题"所以命中question
    assert result["intent"] == "question"


def test_params_default_empty():
    """未指定resource_type时 params 为空字典"""
    result = _keyword_fallback("你好")
    assert result["params"] == {}


def test_case_insensitive_en():
    """英文小写触发词可识别（evaluation 关键词用原生 text，resource 用 text_lower）"""
    assert _keyword_fallback("TEACH ME PYTHON")["intent"] == "resource"
    # evaluation 关键词匹配用的是原始 text（区分大小写）
    assert _keyword_fallback("evaluate my progress")["intent"] == "evaluation"


def test_mixed_cn_en():
    """中英混合 — 中文关键词+英文术语"""
    assert _keyword_fallback("我想学Python的decorator")["intent"] == "resource"
    assert _keyword_fallback("teach me 关于机器学习")["intent"] == "resource"


def test_collaborative_qa_routing() -> None:
    """collaborative_qa intent routes to Send parallel qa+evaluation"""
    result = supervisor_router({"next_agent": "collaborative_qa"})
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].node == "question_agent"
    assert result[1].node == "evaluation_agent"

def test_collaborative_resource_routing() -> None:
    """collaborative_resource routes to Send resource+quality"""
    result = supervisor_router({"next_agent": "collaborative_resource"})
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].node == "resource_agent"
    assert result[1].node == "quality_reviewer"

def test_collaborative_path_routing() -> None:
    """collaborative_path routes to Send path+prefetch"""
    result = supervisor_router({"next_agent": "collaborative_path"})
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].node == "path_agent"
    assert result[1].node == "prefetch_agent"

def test_serial_routing_returns_string() -> None:
    """serial intents return agent name string, not Send list"""
    result = supervisor_router({"next_agent": "resource_agent"})
    assert isinstance(result, str)
    assert result == "resource_agent"
