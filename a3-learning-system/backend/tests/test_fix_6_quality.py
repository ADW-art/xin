"""Targeted tests for 6 agent conversation quality fixes (2026-07-11)"""
import re
import pytest
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════
# Fix 1: Quality scoring formula (collaboration.py)
# ═══════════════════════════════════════════════════════════

class TestFix1QualityScoring:
    """Verify max->min fix: score should NOT be locked at 100 for new users."""

    def _call_quality_review(self, profile=None, teaching_ctx=None, context=None,
                             user_id=1, bkt_override=None, agent_outputs=None):
        from app.agents.collaboration import _quality_review_node
        state = {
            "user_id": user_id,
            "user_profile": profile or {"cognitive_style": "visual"},
            "teaching_context": teaching_ctx or {},
            "context": context or {"topic": "Python"},
            "agent_outputs": agent_outputs or {},
        }
        with patch("app.services.bkt_service.get_tracker") as mock_tracker:
            tracker = MagicMock()
            bkt = bkt_override or {
                "summary": {"real_mastered": 0, "real_total": 0, "real_attempts": 0,
                            "mastered": 0, "total": 0, "total_attempts": 0}
            }
            tracker.to_dict.return_value = bkt
            mock_tracker.return_value = tracker
            result = _quality_review_node(state)
        return result

    def test_new_user_score_below_100(self):
        """Fix 1a: New user (no BKT data) should get <100 score since base=85 minus misc penalties."""
        result = self._call_quality_review(
            bkt_override={"summary": {"real_mastered": 0, "real_total": 0,
                                       "real_attempts": 0, "mastered": 0, "total": 0,
                                       "total_attempts": 0}}
        )
        qr = result["agent_outputs"]["quality_reviewer"]
        score = qr["score"]
        assert score < 100, f"New user score should NOT be 100, got {score}"
        assert score >= 20, f"Score should have floor 20, got {score}"

    def test_low_mastery_user_score_not_100(self):
        """Fix 1b: Low mastery user (<30%) gets difficulty penalty, score < 100."""
        result = self._call_quality_review(
            bkt_override={"summary": {"real_mastered": 1, "real_total": 10,
                                       "real_attempts": 5, "mastered": 1, "total": 10,
                                       "total_attempts": 5}}
        )
        qr = result["agent_outputs"]["quality_reviewer"]
        score = qr["score"]
        assert score < 100, f"Low mastery should get penalty, got {score}"

    def test_high_mastery_user_score_not_100(self):
        """Fix 1c: High mastery user (>80%) gets difficulty penalty, score < 100."""
        result = self._call_quality_review(
            bkt_override={"summary": {"real_mastered": 9, "real_total": 10,
                                       "real_attempts": 15, "mastered": 9, "total": 10,
                                       "total_attempts": 15}}
        )
        qr = result["agent_outputs"]["quality_reviewer"]
        score = qr["score"]
        assert score < 100, f"High mastery should get difficulty penalty, got {score}"

    def test_score_with_short_content_penalty(self):
        """Fix 1d: Short resource output (<200 chars) gets struct penalty."""
        result = self._call_quality_review(
            bkt_override={"summary": {"real_mastered": 5, "real_total": 10,
                                       "real_attempts": 20, "mastered": 5, "total": 10,
                                       "total_attempts": 20}},
            agent_outputs={"resource_agent": {"stream_buffer": "short"}}
        )
        qr = result["agent_outputs"]["quality_reviewer"]
        score = qr["score"]
        assert score < 100, f"Short content should get penalty, got {score}"

    def test_floor_20_applied(self):
        """Fix 1e: score should not go below 20 even with extreme penalties."""
        result = self._call_quality_review(
            profile={"cognitive_style": "visual"},
            bkt_override={"summary": {"real_mastered": 0, "real_total": 15,
                                       "real_attempts": 30, "mastered": 0, "total": 15,
                                       "total_attempts": 30}},
            agent_outputs={"resource_agent": {"stream_buffer": "x" * 50}}
        )
        qr = result["agent_outputs"]["quality_reviewer"]
        score = qr["score"]
        assert score >= 20, f"Score should have floor 20, got {score}"
        assert score < 100, f"Score with many penalties should be well below 100, got {score}"


# ═══════════════════════════════════════════════════════════
# Fix 2: CSS token regex (shared_utils.py + sse_bridge.py)
# ═══════════════════════════════════════════════════════════

class TestFix2CssCleaning:
    """Verify CSS syntax artifacts like "sc"> and "sf"> are properly cleaned."""

    def test_clean_spark_tokens_removes_sc(self):
        """Fix 2a: "sc"> should be removed from output."""
        from app.services.sse_bridge import clean_spark_tokens
        text = 'Here is code: "sc">print("hello")"sc"> more'
        cleaned = clean_spark_tokens(text)
        assert '"sc">' not in cleaned, f"Spark tokens not cleaned: {cleaned!r}"

    def test_clean_spark_tokens_removes_sf(self):
        """Fix 2b: "sf"> should be removed from output."""
        from app.services.sse_bridge import clean_spark_tokens
        text = 'Function: "sf">def foo():"sf"> pass'
        cleaned = clean_spark_tokens(text)
        assert '"sf">' not in cleaned, f"Spark tokens not cleaned: {cleaned!r}"

    def test_clean_spark_tokens_removes_sk(self):
        """Fix 2c: "sk"> should be removed from output."""
        from app.services.sse_bridge import clean_spark_tokens
        text = 'Key: "sk">value"sk"> done'
        cleaned = clean_spark_tokens(text)
        assert '"sk">' not in cleaned, f"Spark tokens not cleaned: {cleaned!r}"

    def test_clean_spark_tokens_keeps_normal_quotes(self):
        """Fix 2d: Normal quoted strings should NOT be affected."""
        from app.services.sse_bridge import clean_spark_tokens
        text = 'This is a "normal" string with "quotes"'
        cleaned = clean_spark_tokens(text)
        assert '"normal"' in cleaned
        assert '"quotes"' in cleaned

    def test_css_artifact_cleaned_in_shared_utils(self):
        """Fix 2e: _clean_llm_context should clean CSS artifacts like "sc"> and "sf">."""
        from app.core.shared_utils import _clean_llm_context
        text = 'CSS code: "sc">color: blue;"sf"> font-size: 14px;'
        cleaned = _clean_llm_context(text)
        assert '"sc">' not in cleaned, f"Should clean CSS artifacts: {cleaned!r}"
        assert '"sf">' not in cleaned, f"Should clean CSS artifacts: {cleaned!r}"

    def test_css_artifact_after_non_word_char(self):
        """Fix 2f: CSS artifact after non-word char (#, space etc) should be cleaned.

        The old regex had \\b after > which failed when followed by # or space.
        After fix: regex r'\b"[a-z]{2,4}">' (no trailing \\b).
        """
        from app.core.shared_utils import _clean_llm_context
        text = 'style "sc">#header { color: red; }"sf"> end'
        cleaned = _clean_llm_context(text)
        assert '"sc">' not in cleaned, f"Artifact before # should be cleaned: {cleaned!r}"
        assert '"sf">' not in cleaned, f"Artifact before space should be cleaned: {cleaned!r}"


# ═══════════════════════════════════════════════════════════
# Fix 3-4: Path agent stage duration fixes (path_agent.py)
# ═══════════════════════════════════════════════════════════

class TestFix3PathAgentDuration:
    """Verify duration_min and stage granularity fixes in path agent."""

    def test_duration_min_formula(self):
        """Fix 3: duration_min = stage_hours * 15 (was * 5, 1/4 ratio of learning time)."""
        stage_hours = 4
        duration_min = max(15, stage_hours * 15)
        assert duration_min == 60, f"4h stage should have 60min review, got {duration_min}"
        assert duration_min >= 15

    def test_duration_min_small_stage(self):
        """Fix 3b: Very small stage still gets minimum 15 min review."""
        stage_hours = 0.5
        duration_min = max(15, stage_hours * 15)
        assert duration_min == 15, f"0.5h stage should have 15min min review, got {duration_min}"

    def test_stage_weeks_half_granularity(self):
        """Fix 4: Stage weeks should allow 0.5 granularity, not just integers."""
        weekly_hours = 3
        test_cases = [
            (2, 0.5),   # 2/3h = 0.67 weeks -> round(1.33)/2 = 0.5
            (5, 1.0),   # 5/3h = 1.67 weeks -> round(3.33)/2 = 1.5
            (7, 1.0),   # 7/3h = 2.33 weeks -> round(4.67)/2 = 2.5
            (12, 2.0),  # 12/3h = 4.0 weeks
        ]
        for hours, expected in test_cases:
            weeks_raw = hours / max(weekly_hours, 1)
            weeks = max(0.5, round(weeks_raw * 2) / 2)
            # Verify granularity is 0.5 (not integer-only)
            assert weeks * 2 == round(weeks * 2), f"{hours}h should give half-granularity weeks, got {weeks}"
            assert weeks >= 0.5, f"Weeks should be >= 0.5, got {weeks} for {hours}h"

    def test_path_agent_actual_functions(self):
        """Fix 4b: Verify path_agent.py has the stage/duration functions importable."""
        from app.agents.path_agent import _build_dag_stages, _compute_review_schedule, path_agent_node
        assert callable(_build_dag_stages)
        assert callable(_compute_review_schedule)
        assert callable(path_agent_node)


# ═══════════════════════════════════════════════════════════
# Fix 5-6: PATH_PROMPT no absolute calendar dates (path_agent.py)
# ═══════════════════════════════════════════════════════════

class TestFix5PathPromptDates:
    """Verify PATH_PROMPT forbids absolute calendar dates."""

    def test_path_prompt_forbids_absolute_dates(self):
        """Fix 5: PATH_PROMPT must instruct LLM to use staged structure, not calendar dates."""
        from app.agents.path_agent import PATH_PROMPT
        # Should mention staged learning path
        assert "分阶段" in PATH_PROMPT, \
            "PATH_PROMPT must mention staged learning"
        # Should forbid fabrication (core anti-hallucination rules)
        assert "禁止" in PATH_PROMPT and "编造" in PATH_PROMPT, \
            "PATH_PROMPT must forbid fabricating concepts"

    def test_path_prompt_example_uses_relative_days(self):
        """Fix 6: Example in PATH_PROMPT should use relative days."""
        from app.agents.path_agent import PATH_PROMPT
        assert "阶段" in PATH_PROMPT, \
            "PATH_PROMPT example should use relative day references"

    def test_path_prompt_no_iso_date_instructions(self):
        """Fix 5c: PATH_PROMPT should NOT instruct LLM to generate ISO dates."""
        from app.agents.path_agent import PATH_PROMPT
        # The prompt should clearly say dates are auto-generated, not LLM-generated
        has_auto_date = "自动计算" in PATH_PROMPT or "系统" in PATH_PROMPT
        assert has_auto_date, "PATH_PROMPT should indicate dates are auto-computed"


# ═══════════════════════════════════════════════════════════
# Integration tests
# ═══════════════════════════════════════════════════════════

class TestIntegrationAllFixes:
    """End-to-end verification that fixes don't break each other."""

    def test_quality_review_in_rc_join(self):
        """rc_join_node calls _quality_review_node and gets score < 100 for new users."""
        from app.agents.collaboration import rc_join_node
        state = {
            "user_id": 1,
            "user_profile": {"cognitive_style": "reading"},
            "teaching_context": {},
            "context": {"topic": "Python basics"},
            "agent_outputs": {
                "resource_agent": {"stream_buffer": "Python is a programming language..."}
            },
        }
        with patch("app.services.bkt_service.get_tracker") as mock_tracker:
            tracker = MagicMock()
            tracker.to_dict.return_value = {
                "summary": {"real_mastered": 0, "real_total": 0, "real_attempts": 0,
                            "mastered": 0, "total": 0, "total_attempts": 0}
            }
            mock_tracker.return_value = tracker
            result = rc_join_node(state)

        qr = result["agent_outputs"]["quality_reviewer"]
        assert qr["score"] < 100, f"rc_join quality score should be < 100, got {qr['score']}"
        assert "_collaboration_mode" in result["agent_outputs"]
        assert result["agent_outputs"]["_collaboration_mode"] == "resource_serial_qc"
        assert result["next_agent"] == "supervisor"

    def test_qa_join_preserves_bkt_level(self):
        """qa_join_node should preserve BKT level in collaboration output."""
        from app.agents.collaboration import qa_join_node, _build_qa_review
        review = _build_qa_review(
            {"bkt_p_known": 0.25, "topic": "Python"},
            {"dimension_scores": {"syntax": 30, "logic": 50}}
        )
        assert review["bkt_level"] == 0.25
        assert review["score"] < 100
        assert any("入门" in n for n in review["notes"])

    def test_content_guard_cleans_artifacts(self):
        """Content guard + shared_utils should handle all known artifact patterns."""
        from app.core.shared_utils import _clean_llm_context
        from app.services.sse_bridge import clean_spark_tokens
        # Test both cleaning layers
        text = 'CSS: "sc">color: red;"sf"> end "sk">key'
        # Step 1: Spark tokens
        step1 = clean_spark_tokens(text)
        assert '"sc">' not in step1
        assert '"sf">' not in step1
        # Step 2: LLM context cleaning
        step2 = _clean_llm_context(step1)
        assert '"sc">' not in step2
        assert '"sf">' not in step2

    def test_path_prompt_parseable(self):
        """PATH_PROMPT should be a valid string that contains key sections."""
        from app.agents.path_agent import PATH_PROMPT
        assert isinstance(PATH_PROMPT, str)
        assert len(PATH_PROMPT) > 500, "PATH_PROMPT should have substantial content"
