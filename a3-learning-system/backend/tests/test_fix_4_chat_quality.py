"""Targeted tests for 4 agent chat quality fixes (2026-07-11)"""
import re
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


# ═══════════════════════════════════════════════════════════
# P1: CSS artifact leak fix
# ═══════════════════════════════════════════════════════════

class TestP1CssArtifactLeak:
    """Verify Spark tokens cleaned BEFORE chunk splitting in _bridge_stream."""

    def test_clean_spark_tokens_full_pattern(self):
        """P1a: Full 5-char pattern cleaned in one pass."""
        from app.api.chat import clean_spark_tokens
        text = '"sc"># comment\n"sf">def foo():\n    "sk">pass'
        cleaned = clean_spark_tokens(text)
        assert '"sc">' not in cleaned
        assert '"sf">' not in cleaned
        assert '"sk">' not in cleaned
        assert '# comment' in cleaned
        assert 'def foo():' in cleaned

    def test_small_chunks_would_have_failed(self):
        """P1b: Simulate chunk_size=2 — pattern is split but pre-cleaning catches it."""
        from app.api.chat import clean_spark_tokens
        # If we DON'T pre-clean, chunk_size=2 splits "sc"> into "s|c"|">" — regex misses it
        text = '"sc">code'
        # With pre-cleaning (our fix), clean BEFORE splitting
        cleaned = clean_spark_tokens(text)
        assert '"sc">' not in cleaned
        # Now split into 2-char chunks — all chunks should be clean
        chunks = [cleaned[i:i+2] for i in range(0, len(cleaned), 2)]
        for chunk in chunks:
            assert '"sc">' not in chunk
            assert '"sf">' not in chunk

    def test_spark_token_after_special_chars(self):
        """P1c: Token after :, space, #, etc — all should be cleaned."""
        from app.api.chat import clean_spark_tokens
        cases = [
            'code: "sc">comment',
            'x = "sf">func()',
            'key "sk">value',
            'end. "sa">next',
            'test# "sd">data',
        ]
        for case in cases:
            cleaned = clean_spark_tokens(case)
            for token in ['"sc">', '"sf">', '"sk">', '"sa">', '"sd">']:
                assert token not in cleaned, f"Token {token} not cleaned from: {case!r}"

    def test_normal_quotes_preserved(self):
        """P1d: Normal Python strings with quotes must not be corrupted."""
        from app.api.chat import clean_spark_tokens
        code = 'print("hello world")\nx = "value"\nreturn {"key": "val"}'
        cleaned = clean_spark_tokens(code)
        assert '"hello world"' in cleaned
        assert '"value"' in cleaned
        assert '"key"' in cleaned
        assert '"val"' in cleaned

    def test_chinese_with_artifacts(self):
        """P1e: Chinese text mixed with artifacts — clean but preserve Chinese."""
        from app.api.chat import clean_spark_tokens
        text = '这是一段"sc">Python代码"sf">示例 结束'
        cleaned = clean_spark_tokens(text)
        assert '"sc">' not in cleaned
        assert '"sf">' not in cleaned
        assert '这是一段' in cleaned
        assert 'Python代码' in cleaned
        assert '示例' in cleaned


# ═══════════════════════════════════════════════════════════
# P3: Anti-plan filter less aggressive
# ═══════════════════════════════════════════════════════════

class TestP3AntiPlanFilter:
    """Verify is_learning_plan_output no longer triggers on teaching intros."""

    def test_teaching_intro_not_flagged(self):
        """P3a: '以下是Python学习计划中的基础内容概述' should NOT be flagged.

        This is the exact scenario from the user's chat log that was broken.
        """
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()
        text = "当然可以，Python基础涵盖了许多重要的概念和技能。以下是 Python 学习计划中的基础内容概述："
        assert guard.is_learning_plan_output(text) is False, \
            "Teaching intro should NOT be flagged as learning plan"

    def test_genuine_plan_still_flagged(self):
        """P3b: Full learning plan with numbered items should still be flagged."""
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()
        text = """# Python 学习计划
第1周：基础语法和数据类型
第2周：函数和面向对象
第3周：项目实战"""
        assert guard.is_learning_plan_output(text) is True, \
            "Full plan with numbered days should be flagged"

    def test_stages_structure_flagged(self):
        """P3c: Multi-stage structure should be flagged."""
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()
        text = "第1阶段：基础入门\n第2阶段：进阶学习"
        assert guard.is_learning_plan_output(text) is True

    def test_keyword_only_no_structure_not_flagged(self):
        """P3d: Just the word '学习计划' without structure — NOT flagged."""
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()
        text = "根据你的学习计划，今天我们来学习Python装饰器的基本用法"
        assert guard.is_learning_plan_output(text) is False, \
            "Single keyword mention without structure should not be flagged"

    def test_focused_teaching_content_not_flagged(self):
        """P3e: Single-topic teaching content should never be flagged."""
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()
        texts = [
            "## Python 装饰器\n\n装饰器是一种高阶函数...",
            "## 变量和数据类型\n\nPython中有多种数据类型...",
            "什么是闭包？闭包是指...",
            "1. 安装 Python\n2. 创建第一个文件\n3. 理解变量",
        ]
        for text in texts:
            assert guard.is_learning_plan_output(text) is False, \
                f"Teaching content should not be flagged: {text[:50]}"

    def test_numbered_teaching_list_not_flagged(self):
        """P3f: Numbered teaching topic list (without plan keywords) — NOT flagged.

        This was the exact content that triggered false positive in user's chat:
        '1. 安装 Python\n2. 创建 Python 文件\n3. 理解变量\n...'
        """
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()
        text = """1. 安装 Python
目标：学习如何安装 Python。
内容：解释如何找到 Python 的安装程序...

2. 创建 Python 文件
目标：学习如何创建一个新的 Python 文件。
内容：了解如何使用文本编辑器..."""
        assert guard.is_learning_plan_output(text) is False, \
            "Numbered teaching content without plan keywords should not be flagged"


# ═══════════════════════════════════════════════════════════
# P2: Path plan quality validation
# ═══════════════════════════════════════════════════════════

class TestP2PathPlanQuality:
    """Verify path plan quality validation catches low-quality output."""

    def test_flat_day_list_detected(self):
        """P2a: Flat list with >15 '第X天' should be invalid."""
        from app.agents.path_agent import _validate_path_output
        days = "\n".join([f"第{i}天：学习Python特性{i}" for i in range(1, 20)])
        is_valid, reason, _ = _validate_path_output(days, ["Python", "变量", "函数"], [])
        assert not is_valid, f"Flat day list should be invalid, got {is_valid}"
        assert "flat_day_list" in str(reason[0])

    def test_repetitive_template_detected(self):
        """P2b: Same template repeated >=5 times should be invalid."""
        from app.agents.path_agent import _validate_path_output
        lines = []
        for i in range(31, 45):
            lines.append(f"第{i}天：学习更高级的Python特性，如人工智能、量子计算和区块链技术")
        text = "\n".join(lines)
        is_valid, reason, _ = _validate_path_output(text, ["Python", "AI"], [])
        assert not is_valid, f"Repetitive template should be invalid, got {is_valid}"

    def test_good_path_plan_is_valid(self):
        """P2c: Proper structured plan should pass validation."""
        from app.agents.path_agent import _validate_path_output
        text = """### 1. 当前水平诊断
已掌握：变量、循环。技能缺口：函数、面向对象。

### 2. 分阶段学习路线
| 阶段 | 主题 | 核心知识点 | 建议时长 |
|------|------|-----------|---------|
| 1 | Python函数 | 函数定义, 参数传递, 返回值 | 9h |
| 2 | 面向对象 | 类与对象, 继承, 多态 | 9h |

### 3. 时间估算
总计约18小时，4-5周完成。"""
        is_valid, reason, _ = _validate_path_output(
            text, ["函数定义", "参数传递", "返回值", "类与对象", "继承", "多态"], []
        )
        assert is_valid, f"Good plan should be valid, got reason={reason}"


# ═══════════════════════════════════════════════════════════
# Integration: Full pipeline test
# ═══════════════════════════════════════════════════════════

class TestIntegrationAllFixes:
    """Verify all fixes work together end-to-end."""

    def test_artifact_to_cleaned_pipeline(self):
        """Simulate full LLM output -> clean -> chunk -> frontend pipeline."""
        from app.api.chat import clean_spark_tokens
        # Raw Spark LLM output (contaminated)
        raw = '"sc"># Python基础\n"sf">print("sf">type(x))\n"sk">class MyClass:\n"sc">    pass'
        # Step 1: Pre-clean (our fix in _bridge_stream)
        cleaned = clean_spark_tokens(raw)
        # Verify no artifacts
        for token in ['"sc">', '"sf">', '"sk">']:
            assert token not in cleaned
        # Step 2: Split into display chunks
        chunk_size = 2
        chunks = [cleaned[i:i+chunk_size] for i in range(0, len(cleaned), chunk_size)]
        # Step 3: Each chunk should be clean
        for chunk in chunks:
            assert '"sc">' not in chunk
            assert '"sf">' not in chunk
        # Content preserved
        assert 'Python基础' in cleaned
        assert 'print(' in cleaned
        assert 'class MyClass' in cleaned

    def test_anti_plan_teaching_flow(self):
        """Teaching request -> LLM outputs intro with '学习计划' -> should NOT be blocked."""
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()

        # Scenario: User asks about Python basics, LLM responds with teaching content
        teaching_response = """当然可以，Python基础涵盖了许多重要的概念和技能。

以下是 Python 学习计划中的基础内容概述：

1. 安装 Python — 学习如何下载和安装Python
2. 变量和数据类型 — Python的基本数据存储
3. 控制流 — if语句和循环的使用
4. 函数 — 代码复用的基本单元"""
        # Should NOT be flagged (teaching content, not a plan)
        assert guard.is_learning_plan_output(teaching_response) is False

    def test_anti_plan_real_plan_flow(self):
        """Path planning request -> LLM outputs real plan -> should be flagged."""
        from app.utils.content_guard import ContentGuard
        guard = ContentGuard()

        # Scenario: User asks for a plan, LLM generates a full course schedule
        plan_response = """# Python 学习计划

## 课程大纲
第1周：Python基础语法和数据类型
第2周：函数、模块和面向对象编程
第3周：文件操作、异常处理和测试
第4周：Web开发基础和项目实战

总计4周课程，每周投入5-8小时。"""
        # Should be flagged (this is a real plan, not teaching content)
        assert guard.is_learning_plan_output(plan_response) is True
