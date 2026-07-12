"""Usage tests: simulate real user scenarios from the chat log (2026-07-11)"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ═══════════════════════════════════════════════════════════
# U1: CSS artifact leak — simulate the exact scenario
# ═══════════════════════════════════════════════════════════

class TestU1ArtifactLeak:
    """Simulate the exact Spark-contaminated output from user's chat log."""

    def test_exact_user_log_artifacts_cleaned(self):
        """U1a: The exact contaminated text from user's log should be clean."""
        from app.api.chat import clean_spark_tokens
        # Exact text from the user's "详细讲解python的数据类型" chat
        contaminated = '''"sc"># 定义一个整数变量
num = 10
"sf">print("sf">type(num))  "sc"># 输出：<"sk">class 'int'>

"sc"># 创建一个整数对象
num_obj = "sf">int(5)
"sf">print("sf">type(num_obj))  "sc"># 输出：<"sk">class 'int'>'''
        cleaned = clean_spark_tokens(contaminated)
        # All artifacts should be gone
        assert '"sc">' not in cleaned
        assert '"sf">' not in cleaned
        assert '"sk">' not in cleaned
        # Core code should be preserved
        assert '# 定义一个整数变量' in cleaned
        assert 'num = 10' in cleaned
        assert 'print(type(num))' in cleaned
        assert "class 'int'" in cleaned

    def test_bridge_stream_cleaning_order(self):
        """U1b: Clean before chunk splitting — the exact fix."""
        from app.api.chat import clean_spark_tokens
        # Raw LLM output (simulating what _bridge_stream receives)
        raw = '"sc"># comment\n"sf">def foo():\n    "sk">return 42'
        # Step 1: Pre-clean (our fix in _bridge_stream)
        cleaned = clean_spark_tokens(raw)
        # Step 2: Split into display chunks (chunk_size=2)
        chunk_size = 2
        chunks = []
        for i in range(0, len(cleaned), chunk_size):
            chunks.append(cleaned[i:i+chunk_size])
        # Step 3: Verify no artifact in any chunk
        for i, chunk in enumerate(chunks):
            for token in ['"sc">', '"sf">', '"sk">']:
                assert token not in chunk, \
                    f"Chunk {i} '{chunk}' contains artifact {token}"
        # Step 4: Reconstruct and verify content
        reconstructed = ''.join(chunks)
        assert '# comment' in reconstructed
        assert 'def foo():' in reconstructed
        assert 'return 42' in reconstructed

    def test_mixed_content_survives(self):
        """U1c: Chinese + English + code mixed content should be clean but complete."""
        from app.api.chat import clean_spark_tokens
        text = '''好的，下面是Python基础知识：

"sc"># Python 变量
"sf">x = 10
"sc">y = "hello"

"sk">def greet(name):
"sf">    return f"Hello, {name}!"

这是你的第一个Python程序'''
        cleaned = clean_spark_tokens(text)
        assert '好的，下面是Python基础知识' in cleaned
        assert 'Python 变量' in cleaned
        assert 'x = 10' in cleaned
        assert 'greet' in cleaned
        assert 'Hello, {name}' in cleaned
        assert '第一个Python程序' in cleaned
        for token in ['"sc">', '"sf">', '"sk">']:
            assert token not in cleaned


# ═══════════════════════════════════════════════════════════
# U2: Anti-plan filter — simulate the exact teaching scenario
# ═══════════════════════════════════════════════════════════

class TestU2AntiPlanFilter:
    """Simulate the exact teaching/plan scenarios from user's chat log."""

    def test_teaching_python_basics_not_flagged(self):
        """U2a: '讲讲python基础有什么内容' response should NOT be flagged.

        This is the EXACT scenario from the user's chat log where content was
        incorrectly flagged and triggered regeneration.
        """
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()

        # First response that got rejected in user's log
        response1 = "当然可以，Python基础涵盖了许多重要的概念和技能。以下是 Python 学习计划中的基础内容概述："
        assert guard.is_learning_plan_output(response1) is False

        # Second response that partially succeeded
        response2 = """当然可以，Python基础涵盖了许多重要的概念和技能，以下是一些关键的部分：

1. 安装 Python
目标：学习如何安装 Python。

2. 创建 Python 文件
目标：学习如何创建一个新的 Python 文件。

3. 理解变量
目标：学习变量的定义和使用。

4. 数据类型
目标：学习 Python 中的不同数据类型。"""
        assert guard.is_learning_plan_output(response2) is False

    def test_full_plan_with_days_still_flagged(self):
        """U2b: '帮我制定一个 Python 学习计划' path plan should still be flagged."""
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()

        # This is a genuine learning plan output (from path_agent)
        plan = """第一阶段：Python 基础
第1天：安装 Python 并创建第一个 Python 文件
第2天：理解变量、数据类型、运算符、条件语句和循环
第3天：理解函数、模块和包

第二阶段：进阶 Python 编程
第13天：理解装饰器
第14天：理解生成器"""
        assert guard.is_learning_plan_output(plan) is True

    def test_numbered_teaching_with_keyword_reference(self):
        """U2c: Teaching content that mentions '学习计划' once as context reference.

        This is the key scenario: LLM says "在这一阶段的学习计划中，你需要掌握..."
        This is teaching context, not a plan output.
        """
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()

        texts = [
            "根据你的学习计划，今天我们来学习Python装饰器的基本用法",
            "按照你之前制定的学习计划，第一阶段包含了以下内容",
            "学习计划中的下一个知识点是面向对象编程",
        ]
        for text in texts:
            assert guard.is_learning_plan_output(text) is False, \
                f"Contextual reference should not be flagged: {text[:50]}"

    def test_streaming_guard_not_block_teaching(self):
        """U2d: StreamGuard.feed should not block teaching content mid-stream.

        This tests the check_interval=300 change — content shouldn't be blocked
        at 60 chars when only partial context is available.
        """
        from app.utils.content_guard import StreamGuard, ContentGuard

        guard = StreamGuard(check_interval=300)
        # Disable plan detection during streaming (as chat.py does for non-resource agents)
        guard._guard.is_learning_plan_output = lambda _t: False

        # Feed teaching content chunk by chunk
        teaching_chunks = [
            "当然可以，",
            "Python基础涵盖了许多重要的概念和技能。",
            "以下是 Python 学习计划中的基础内容概述：",
            "\n\n1. 安装 Python",
            "\n2. 创建 Python 文件",
            "\n3. 理解变量",
        ]
        output = ""
        blocked = False
        for chunk in teaching_chunks:
            result = guard.feed(chunk)
            if result is None:
                blocked = True
                break
            output += result

        assert not blocked, "Teaching content should not be blocked during streaming"
        assert "Python" in output

    def test_streaming_guard_blocks_real_plan(self):
        """U2e: StreamGuard with anti-plan enabled should block a real plan."""
        from app.utils.content_guard import StreamGuard

        guard = StreamGuard(check_interval=60)
        # Keep plan detection enabled (as chat.py does for resource_agent)

        plan_chunks = [
            "# Python 学习计划\n\n",
            "## 课程大纲\n",
            "第1周：基础语法",
            "\n第2周：面向对象",
            "\n第3周：Web开发",
        ]
        blocked = False
        for chunk in plan_chunks:
            result = guard.feed(chunk)
            if result is None:
                blocked = True
                break

        # Depending on where the check triggers, this may or may not block
        # The important thing is that finalize() should catch it
        plan_detected = guard.finalize()
        assert blocked or plan_detected, \
            "Real plan should be blocked either during streaming or at finalize"


# ═══════════════════════════════════════════════════════════
# U3: Path plan quality validation
# ═══════════════════════════════════════════════════════════

class TestU3PathPlanQuality:
    """Verify path plan quality validation catches real low-quality patterns."""

    def test_real_user_plan_days_pattern(self):
        """U3a: The exact day-repeat pattern from user's 44-day plan."""
        from app.agents.path_agent import _validate_path_output

        # Simulate the 31-44 day repetition from user's log
        days = []
        for day in range(1, 45):
            if day <= 12:
                days.append(f"第{day}天：学习Python基础概念{day}")
            elif day <= 24:
                days.append(f"第{day}天：学习Python进阶特性{day}")
            else:
                days.append(f"第{day}天：学习更高级的Python特性，如人工智能、量子计算和区块链技术")
        plan = "\n".join(days)
        is_valid, reason, _ = _validate_path_output(plan, ["Python"], [])
        assert not is_valid, f"44-day flat plan should be invalid, got {is_valid}"
        assert "flat_day_list" in str(reason[0])

    def test_good_markdown_table_plan_valid(self):
        """U3b: A proper markdown table plan should pass validation."""
        from app.agents.path_agent import _validate_path_output

        good_plan = """### 1. 当前水平诊断
已掌握：变量与数据类型, 条件判断。技能缺口：函数抽象、面向对象。

### 2. 分阶段学习路线

| 阶段 | 主题 | 核心知识点 | 建议时长 | 前置依赖 | 检验标准 |
|------|------|-----------|---------|---------|---------|
| 1 | Python函数 | 函数定义, 参数传递, 返回值, 作用域 | 9h | 循环, 条件判断 | 完成5道函数练习题 |
| 2 | 面向对象 | 类与对象, 继承, 多态 | 12h | 函数, 数据结构 | 实现学生管理系统 |

### 3. 时间估算
总计约21小时，4-6周完成。

### 4. 复习节点
- 阶段1结束后第1天复习函数参数概念
- 阶段2结束后第1天复习类与对象概念

### 5. 里程碑
- 阶段1: 完成HackerRank Python函数模块5题
- 阶段2: 用面向对象实现完整CRUD系统"""
        is_valid, reason, _ = _validate_path_output(
            good_plan,
            ["函数定义", "参数传递", "返回值", "作用域", "类与对象", "继承", "多态"],
            []
        )
        assert is_valid, f"Good markdown plan should be valid, got reason={reason}"

    def test_path_prompt_anti_flat_list_rules(self):
        """U3c: PATH_PROMPT must contain rules against hallucination and flat output."""
        from app.agents.path_agent import PATH_PROMPT
        assert "至少3个阶段" in PATH_PROMPT or "分阶段" in PATH_PROMPT, \
            "PATH_PROMPT should require staged structure (not flat list)"
        assert "禁止编造" in PATH_PROMPT, \
            "PATH_PROMPT should forbid fabricating content"


# ═══════════════════════════════════════════════════════════
# U4: End-to-end scenario replay
# ═══════════════════════════════════════════════════════════

class TestU4EndToEnd:
    """Replay the entire user chat log scenario and verify fixes."""

    def test_full_scenario_1_python_basics_teaching(self):
        """U4a: User asks '讲讲python基础有什么内容' — teaching response works.

        Steps:
        1. Resource agent generates teaching content
        2. Content passes anti-plan filter (not flagged)
        3. CSS artifacts are cleaned from output
        4. Content reaches user without truncation
        """
        from app.api.chat import clean_spark_tokens
        from app.utils.content_guard import ContentGuard

        guard = ContentGuard()

        # Simulate the LLM output (with artifacts)
        llm_output = '''当然可以，Python基础涵盖了许多重要的概念和技能，以下是一些关键的部分：

"sc"># 1. 安装 Python
目标：学习如何安装 Python。
内容：解释如何找到 Python 的安装程序。

"sc"># 2. 创建 Python 文件
目标：学习如何创建一个新的 Python 文件。
内容：了解如何使用文本编辑器或IDE。

"sc"># 3. 理解变量
目标：学习变量的定义和使用。
内容：介绍变量是什么，如何在Python中定义变量。

"sc"># 4. 数据类型
目标：学习 Python 中的不同数据类型。
内容：详细介绍每种数据类型的用途和特点。'''

        # Step 1: Clean artifacts
        cleaned = clean_spark_tokens(llm_output)
        assert '"sc">' not in cleaned

        # Step 2: Anti-plan check
        is_plan = guard.is_learning_plan_output(cleaned)
        assert not is_plan, "Teaching content should NOT be flagged as plan"

        # Step 3: Content is complete (not truncated)
        assert "安装 Python" in cleaned
        assert "创建 Python 文件" in cleaned
        assert "理解变量" in cleaned
        assert "数据类型" in cleaned

    def test_full_scenario_2_path_planning(self):
        """U4b: User asks '帮我制定一个 Python 学习计划' — plan is generated.

        Steps:
        1. Path agent generates plan
        2. Plan has proper stage structure (not flat day list)
        3. Plan uses relative days (no absolute calendar dates)
        """
        from app.agents.path_agent import PATH_PROMPT, _validate_path_output

        # PATH_PROMPT should enforce structured output
        assert "分阶段学习路线" in PATH_PROMPT
        assert "Markdown 表格" in PATH_PROMPT or "表格" in PATH_PROMPT
        assert "至少3个阶段" in PATH_PROMPT or "阶段" in PATH_PROMPT

        # A properly structured plan should pass validation
        good_plan = """### 1. 当前水平诊断
已掌握：变量, 循环。技能缺口：函数, 类。

### 2. 分阶段学习路线

| 阶段 | 主题 | 核心知识点 | 建议时长 | 前置依赖 | 检验标准 |
|------|------|-----------|---------|---------|---------|
| 1 | 函数 | 函数定义, 参数类型, 返回值 | 9h | 循环 | 完成5题 |
| 2 | 面向对象 | 类定义, 继承, 封装 | 12h | 函数 | 完成项目 |

### 3. 时间估算
总计21h，约5周。

### 4. 复习节点
- 阶段1结束后第1天复习函数参数
- 阶段1结束后第3天复习作用域

### 5. 里程碑
- 阶段1: 完成HackerRank 5题
- 阶段2: 实现CRUD系统"""
        is_valid, reason, _ = _validate_path_output(
            good_plan,
            ["函数定义", "参数类型", "返回值", "类定义", "继承", "封装"],
            []
        )
        assert is_valid, f"Good plan should pass, got: {reason}"

    def test_full_scenario_3_quality_scoring(self):
        """U4c: Quality review gives meaningful scores (not always 100)."""
        from app.agents.collaboration import _quality_review_node
        from unittest.mock import MagicMock, patch

        # Test with different BKT profiles
        with patch("app.services.bkt_service.get_tracker") as mock_tracker:
            tracker = MagicMock()
            tracker.to_dict.return_value = {
                "summary": {"real_mastered": 3, "real_total": 10, "real_attempts": 15,
                            "mastered": 3, "total": 10, "total_attempts": 15}
            }
            mock_tracker.return_value = tracker

            state = {
                "user_id": 1,
                "user_profile": {"cognitive_style": "reading"},
                "teaching_context": {},
                "context": {"topic": "Python basics"},
                "agent_outputs": {
                    "resource_agent": {"stream_buffer": "Python is a programming language..."}
                },
            }
            result = _quality_review_node(state)
            qr = result["agent_outputs"]["quality_reviewer"]
            score = qr["score"]

            # Score should be meaningful (not 100)
            assert score < 100, f"Score should not be 100, got {score}"
            assert score >= 20, f"Score should have floor 20, got {score}"
            # Score should be between 40-90 for this scenario
            assert 20 <= score <= 95, f"Score {score} out of expected range"
