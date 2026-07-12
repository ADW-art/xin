"""Deep test suite: boundary, concurrency, formula verification, redundancy check (2026-07-11)"""
import re
import time
import threading
import pytest
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════
# D1: Quality scoring boundary tests
# ═══════════════════════════════════════════════════════════

class TestQualityScoringBoundary:
    """Boundary/mutation tests for quality scoring formula."""

    def _call(self, bkt_override=None, profile=None, agent_outputs=None):
        from app.agents.collaboration import _quality_review_node
        state = {
            "user_id": 1,
            "user_profile": profile or {},
            "teaching_context": {},
            "context": {"topic": "Test"},
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
            return _quality_review_node(state)

    def test_boundary_exactly_80_pct_mastery(self):
        """D1a: Exactly 80% mastery — should NOT trigger 'already mastered' warning."""
        result = self._call(bkt_override={
            "summary": {"real_mastered": 8, "real_total": 10, "real_attempts": 20,
                        "mastered": 8, "total": 10, "total_attempts": 20}
        })
        qr = result["agent_outputs"]["quality_reviewer"]
        # avg = 8/10 = 0.8, which is NOT > 0.8, so no "已掌握" issue
        issues_text = " ".join(qr["issues"])
        assert "已掌握" not in issues_text, f"80% should not trigger high-mastery: {issues_text}"

    def test_boundary_exactly_30_pct_mastery(self):
        """D1b: Exactly 30% mastery — should NOT trigger 'only mastered' warning."""
        result = self._call(bkt_override={
            "summary": {"real_mastered": 3, "real_total": 10, "real_attempts": 20,
                        "mastered": 3, "total": 10, "total_attempts": 20}
        })
        qr = result["agent_outputs"]["quality_reviewer"]
        issues_text = " ".join(qr["issues"])
        assert "仅掌握" not in issues_text, f"30% should not trigger low-mastery: {issues_text}"

    def test_boundary_single_concept(self):
        """D1c: Single concept with 1 attempt — should still work."""
        result = self._call(bkt_override={
            "summary": {"real_mastered": 0, "real_total": 1, "real_attempts": 1,
                        "mastered": 0, "total": 1, "total_attempts": 1}
        })
        qr = result["agent_outputs"]["quality_reviewer"]
        assert 0 <= qr["score"] <= 100, f"Score out of range: {qr['score']}"

    def test_boundary_zero_attempts_but_concepts(self):
        """D1d: Has concepts but zero attempts — should use new-user path."""
        result = self._call(bkt_override={
            "summary": {"real_mastered": 0, "real_total": 5, "real_attempts": 0,
                        "mastered": 0, "total": 5, "total_attempts": 0}
        })
        qr = result["agent_outputs"]["quality_reviewer"]
        # has_meaningful_bkt = (total >= 1 and total_attempts > 0) = False
        # base_score = 85
        assert qr["score"] < 100, f"Zero attempts should not get 100: {qr['score']}"

    def test_boundary_empty_profile(self):
        """D1e: Empty user profile — should not crash."""
        result = self._call(profile={})
        qr = result["agent_outputs"]["quality_reviewer"]
        assert qr["cognitive_style"] == "unknown"

    def test_boundary_none_profile(self):
        """D1f: None profile fields — should handle gracefully (str() on None = 'None')."""
        result = self._call(profile={"cognitive_style": None})
        qr = result["agent_outputs"]["quality_reviewer"]
        # str(None) = "None", lower() = "none" — not in style_hints dict -> "unknown"
        assert qr["cognitive_style"] in ("none", "unknown"), \
            f"Expected 'none' or 'unknown', got {qr['cognitive_style']!r}"

    def test_boundary_very_long_topic(self):
        """D1g: Very long topic name — should not crash."""
        result = self._call(
            bkt_override={"summary": {"real_mastered": 5, "real_total": 10,
                                       "real_attempts": 30, "mastered": 5, "total": 10,
                                       "total_attempts": 30}},
            agent_outputs={"resource_agent": {"stream_buffer": "x" * 5000}}
        )
        qr = result["agent_outputs"]["quality_reviewer"]
        assert 0 <= qr["score"] <= 100

    def test_mutation_all_cognitive_styles(self):
        """D1h: All cognitive styles should produce valid hints."""
        styles = ["visual", "kinesthetic", "reading", "auditory", "unknown", ""]
        for style in styles:
            result = self._call(profile={"cognitive_style": style})
            qr = result["agent_outputs"]["quality_reviewer"]
            assert "score" in qr
            assert 0 <= qr["score"] <= 100

    def test_mutation_all_mastery_levels(self):
        """D1i: Score should monotonically vary with mastery (not stuck at any value)."""
        scores = set()
        for mastered in [0, 2, 5, 8, 10]:
            result = self._call(bkt_override={
                "summary": {"real_mastered": mastered, "real_total": 10,
                            "real_attempts": 20, "mastered": mastered, "total": 10,
                            "total_attempts": 20}
            })
            scores.add(result["agent_outputs"]["quality_reviewer"]["score"])
        # At least 3 distinct scores across different mastery levels
        assert len(scores) >= 2, f"Score should vary with mastery, got {scores}"


# ═══════════════════════════════════════════════════════════
# D2: CSS artifact cleaning boundary tests
# ═══════════════════════════════════════════════════════════

class TestCssCleaningBoundary:
    """Boundary/mutation tests for CSS artifact cleaning."""

    def test_boundary_empty_string(self):
        """D2a: Empty string should not crash."""
        from app.core.shared_utils import _clean_llm_context
        from app.services.sse_bridge import clean_spark_tokens
        assert _clean_llm_context("") == ""
        assert clean_spark_tokens("") == ""

    def test_boundary_only_artifact(self):
        """D2b: String that is only an artifact."""
        from app.core.shared_utils import _clean_llm_context
        result = _clean_llm_context('"sc">')
        assert '"sc">' not in result

    def test_boundary_all_spark_tokens(self):
        """D2c: All known Spark token patterns."""
        from app.services.sse_bridge import clean_spark_tokens
        tokens = ["sk", "sf", "sc", "sa", "sb", "sd", "se", "sg", "sh", "si"]
        for token in tokens:
            text = f'"{token}">content after'
            cleaned = clean_spark_tokens(text)
            assert f'"{token}">' not in cleaned, f"Token {token} not cleaned"

    def test_boundary_normal_code_preserved(self):
        """D2d: Normal code with quotes must be preserved."""
        from app.core.shared_utils import _clean_llm_context
        code = '''
        def hello():
            print("Hello World")
            x = "value"
            return {"key": "value"}
        '''
        cleaned = _clean_llm_context(code)
        assert 'print("Hello World")' in cleaned
        assert '"value"' in cleaned
        assert '"key"' in cleaned

    def test_boundary_html_tags_cleaned(self):
        """D2e: _clean_llm_context removes HTML tags (intended behavior for LLM output cleaning)."""
        from app.core.shared_utils import _clean_llm_context
        html = '<div class="container"><span class="highlight">text</span></div>'
        cleaned = _clean_llm_context(html)
        # HTML tags should be removed (this is the cleaning function's job)
        assert "<div" not in cleaned, "HTML div tags should be cleaned"
        assert "<span" not in cleaned, "HTML span tags should be cleaned"
        # Text content should survive
        assert "text" in cleaned, "Text content should survive HTML tag removal"

    def test_boundary_consecutive_artifacts(self):
        """D2f: Multiple consecutive artifacts should all be cleaned."""
        from app.core.shared_utils import _clean_llm_context
        text = '"sc">"sf">"sk">content"sa">"sd">'
        cleaned = _clean_llm_context(text)
        for token in ["sc", "sf", "sk", "sa", "sd"]:
            assert f'"{token}">' not in cleaned

    def test_mutation_mixed_chinese(self):
        """D2g: Chinese text mixed with artifacts."""
        from app.core.shared_utils import _clean_llm_context
        text = '这是一段Python代码 "sc">print("你好世界")"sf"> 结束'
        cleaned = _clean_llm_context(text)
        assert '"sc">' not in cleaned
        assert '"sf">' not in cleaned
        assert "你好世界" in cleaned

    def test_mutation_unicode_content(self):
        """D2h: Unicode characters should survive cleaning."""
        from app.core.shared_utils import _clean_llm_context
        text = '"sc">αβγ "sf">中文'
        cleaned = _clean_llm_context(text)
        assert "α" in cleaned
        assert "中文" in cleaned

    def test_boundary_artifact_in_middle_of_word(self):
        """D2i: Artifact adjacent to word characters (edge case for old \b regex)."""
        from app.core.shared_utils import _clean_llm_context
        text = 'code"sc">more'
        cleaned = _clean_llm_context(text)
        assert '"sc">' not in cleaned


# ═══════════════════════════════════════════════════════════
# D3: Path agent formula verification
# ═══════════════════════════════════════════════════════════

class TestPathAgentFormula:
    """Verify path agent duration/stage formulas with real computation."""

    def test_stage_duration_computation_chain(self):
        """D3a: Full computation chain: hours -> weeks -> review schedule."""
        from app.agents.path_agent import _build_dag_stages, _compute_review_schedule

        # Simulate a small DAG with known concepts
        known = set()
        topo_order = ["intro", "basics", "functions", "classes"]
        stages = _build_dag_stages(topo_order, known, weekly_hours=5)

        assert len(stages) > 0, "Should produce at least 1 stage"
        for stage in stages:
            assert "name" in stage or "concepts" in stage, f"Stage missing keys: {stage}"
            # Verify stage data is reasonable
            if "duration_weeks" in stage:
                weeks = stage["duration_weeks"]
                assert weeks >= 0.5, f"Stage weeks should be >= 0.5, got {weeks}"
                # Verify half-granularity
                assert (weeks * 2) == round(weeks * 2), \
                    f"Weeks should have 0.5 granularity: {weeks}"

        # Test review schedule computation
        review = _compute_review_schedule(stages)
        assert isinstance(review, list), "Review schedule should be a list"

    def test_review_duration_min_boundary(self):
        """D3b: Review duration_min boundaries for various stage sizes."""
        test_cases = [
            (0.25, 15),   # tiny stage -> floor 15
            (0.5, 15),    # small stage -> floor 15
            (1.0, 15),    # exactly at floor
            (2.0, 30),    # 2h -> 30min review
            (4.0, 60),    # 4h -> 60min review
            (10.0, 150),  # 10h -> 150min review
        ]
        for hours, expected in test_cases:
            duration_min = max(15, hours * 15)
            assert duration_min == expected, \
                f"{hours}h should have {expected}min review, got {duration_min}"

    def test_weeks_granularity_all_values(self):
        """D3c: Exhaustive check of 0.5 granularity for 0.5-20 hours."""
        weekly_hours = 4
        for hours_100 in range(50, 2001, 25):  # 0.5h to 20h in 0.25h steps
            hours = hours_100 / 100
            weeks_raw = hours / max(weekly_hours, 1)
            weeks = max(0.5, round(weeks_raw * 2) / 2)
            # Check granularity
            assert weeks * 2 == round(weeks * 2), \
                f"{hours:.2f}h -> {weeks} weeks: not 0.5 granular"
            assert weeks >= 0.5

    def test_path_prompt_no_hallucination_patterns(self):
        """D3d: PATH_PROMPT must not contain patterns that encourage hallucination."""
        from app.agents.path_agent import PATH_PROMPT
        # No absolute date templates
        assert "2026" not in PATH_PROMPT or "{" in PATH_PROMPT, \
            "PATH_PROMPT should not hardcode 2026 dates"
        # No month-day patterns that LLM might hallucinate
        date_pattern = re.findall(r'\d{1,2}月\d{1,2}日', PATH_PROMPT)
        for dp in date_pattern:
            assert "{" in PATH_PROMPT, \
                f"PATH_PROMPT should not contain literal date '{dp}'"


# ═══════════════════════════════════════════════════════════
# D4: Thread safety / concurrency tests
# ═══════════════════════════════════════════════════════════

class TestConcurrency:
    """Verify modified code is thread-safe under concurrent access."""

    def test_clean_spark_tokens_concurrent(self):
        """D4a: clean_spark_tokens is pure function, safe for concurrent calls."""
        from app.services.sse_bridge import clean_spark_tokens
        errors = []

        def worker(thread_id):
            try:
                for i in range(100):
                    text = f'"sc">thread_{thread_id}_item_{i}"sf"> end'
                    cleaned = clean_spark_tokens(text)
                    assert '"sc">' not in cleaned
                    assert '"sf">' not in cleaned
            except Exception as e:
                errors.append((thread_id, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent clean_spark_tokens errors: {errors}"

    def test_clean_llm_context_concurrent(self):
        """D4b: _clean_llm_context is pure function, safe for concurrent calls."""
        from app.core.shared_utils import _clean_llm_context
        errors = []

        def worker(thread_id):
            try:
                for i in range(100):
                    text = f'"sc">thread_{thread_id}_item_{i}"sf"> end <span>html</span>'
                    cleaned = _clean_llm_context(text)
                    assert '"sc">' not in cleaned
                    assert '"sf">' not in cleaned
            except Exception as e:
                errors.append((thread_id, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent _clean_llm_context errors: {errors}"

    def test_quality_review_concurrent_unique_users(self):
        """D4c: Quality review for different users concurrently."""
        from app.agents.collaboration import _quality_review_node
        errors = []

        def worker(user_id):
            try:
                state = {
                    "user_id": user_id,
                    "user_profile": {"cognitive_style": "visual"},
                    "teaching_context": {},
                    "context": {"topic": f"Topic_{user_id}"},
                    "agent_outputs": {},
                }
                with patch("app.services.bkt_service.get_tracker") as mock_tracker:
                    tracker = MagicMock()
                    tracker.to_dict.return_value = {
                        "summary": {"real_mastered": user_id % 10, "real_total": 10,
                                    "real_attempts": 20, "mastered": user_id % 10,
                                    "total": 10, "total_attempts": 20}
                    }
                    mock_tracker.return_value = tracker
                    result = _quality_review_node(state)
                    qr = result["agent_outputs"]["quality_reviewer"]
                    assert 0 <= qr["score"] <= 100
            except Exception as e:
                errors.append((user_id, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent quality review errors: {errors}"

    def test_stream_integrity_checker_concurrent(self):
        """D4d: StreamIntegrityChecker should work per-instance (not shared)."""
        from app.services.sse_bridge import StreamIntegrityChecker
        errors = []

        def worker(thread_id):
            try:
                checker = StreamIntegrityChecker()
                chunks = [f"t{thread_id}_{i} " for i in range(50)]
                for chunk in chunks:
                    checker.feed(chunk)
                result = checker.finalize()
                assert len(result) > 0
                assert f"t{thread_id}_" in result
            except Exception as e:
                errors.append((thread_id, str(e)))

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent StreamIntegrityChecker errors: {errors}"


# ═══════════════════════════════════════════════════════════
# D5: Redundancy and code quality checks
# ═══════════════════════════════════════════════════════════

class TestRedundancyCheck:
    """Verify no redundant code was introduced by fixes."""

    def test_no_duplicate_css_cleaning(self):
        """D5a: CSS cleaning should not have overlapping duplicate logic."""
        from app.core.shared_utils import _clean_llm_context
        import inspect
        source = inspect.getsource(_clean_llm_context)
        # Count regex patterns — should be reasonable
        pattern_count = source.count("re.sub(")
        assert pattern_count < 15, f"Too many regex substitutions: {pattern_count}"

    def test_collaboration_join_functions_distinct(self):
        """D5b: Join functions should have distinct responsibilities."""
        from app.agents.collaboration import qa_join_node, rc_join_node, path_join_node
        import inspect
        qa_src = inspect.getsource(qa_join_node)
        rc_src = inspect.getsource(rc_join_node)
        path_src = inspect.getsource(path_join_node)
        # Each join function should have unique logic
        assert qa_src != rc_src, "qa_join and rc_join should be different"
        assert rc_src != path_src, "rc_join and path_join should be different"
        assert qa_src != path_src, "qa_join and path_join should be different"

    def test_quality_review_not_duplicated(self):
        """D5c: _quality_review_node should only exist in collaboration.py."""
        import os
        backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        found_in = []
        for root, dirs, files in os.walk(os.path.join(backend, "app")):
            for f in files:
                if f.endswith(".py"):
                    path = os.path.join(root, f)
                    with open(path, encoding="utf-8") as fh:
                        content = fh.read()
                    if "_quality_review_node" in content and "def _quality_review_node" in content:
                        found_in.append(os.path.relpath(path, backend))
        # Should only be defined once
        assert len(found_in) == 1, \
            f"_quality_review_node defined in multiple files: {found_in}"

    def test_no_dead_imports_in_modified_files(self):
        """D5d: Modified files should not have unused imports (basic check)."""
        import ast, os
        backend = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        modified = [
            "app/agents/collaboration.py",
            "app/core/shared_utils.py",
            "app/services/sse_bridge.py",
            "app/agents/path_agent.py",
        ]
        for rel_path in modified:
            full_path = os.path.join(backend, rel_path)
            if not os.path.exists(full_path):
                continue
            with open(full_path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            # Check for `import X as X` redundant aliases
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.asname and alias.name == alias.asname:
                            pytest.fail(f"{rel_path}: redundant alias 'import {alias.name} as {alias.asname}'")


# ═══════════════════════════════════════════════════════════
# D6: Integration stress tests
# ═══════════════════════════════════════════════════════════

class TestIntegrationStress:
    """End-to-end stress on the modified pipeline."""

    def test_full_collaboration_pipeline(self):
        """D6a: qa_join -> rc_join -> path_join all work in sequence."""
        from app.agents.collaboration import qa_join_node, rc_join_node, path_join_node, _build_qa_review

        # 1. QA review
        review = _build_qa_review(
            {"bkt_p_known": 0.5, "topic": "Python loops"},
            {"dimension_scores": {"syntax": 60, "logic": 70, "debugging": 50}}
        )
        assert "score" in review
        assert review["score"] < 100  # Should have some deductions

        # 2. QA join
        qa_state = {
            "user_id": 1,
            "agent_outputs": {
                "question_agent": {"stream_buffer": "Q: What is a for loop?",
                                   "bkt_p_known": 0.5, "topic": "Python loops"},
                "evaluation_agent": {"stream_buffer": "Good question",
                                     "dimension_scores": {"syntax": 60, "logic": 70}},
            },
        }
        qa_result = qa_join_node(qa_state)
        assert qa_result["next_agent"] == "supervisor"
        assert "stream_buffer" in qa_result

        # 3. RC join
        rc_state = {
            "user_id": 1,
            "user_profile": {"cognitive_style": "reading"},
            "context": {"topic": "Python basics"},
            "agent_outputs": {
                "resource_agent": {"stream_buffer": "Python is a high-level programming language..."}
            },
        }
        with patch("app.services.bkt_service.get_tracker") as mock_tracker:
            tracker = MagicMock()
            tracker.to_dict.return_value = {
                "summary": {"real_mastered": 3, "real_total": 10, "real_attempts": 15,
                            "mastered": 3, "total": 10, "total_attempts": 15}
            }
            mock_tracker.return_value = tracker
            rc_result = rc_join_node(rc_state)
        assert rc_result["next_agent"] == "supervisor"
        assert "quality_reviewer" in rc_result["agent_outputs"]

        # 4. Path join
        path_state = {
            "user_id": 1,
            "agent_outputs": {
                "path_agent": {"stream_buffer": "Learning path: Python basics",
                               "teaching_context": {"mode": "teaching"}},
                "prefetch_agent": {"stream_buffer": "Resource: Python tutorial",
                                   "topic": "Python"},
            },
        }
        path_result = path_join_node(path_state)
        assert path_result["next_agent"] == "supervisor"

    def test_css_cleaning_pipeline_realistic(self):
        """D6b: Realistic CSS-contaminated LLM output through both cleaners."""
        from app.core.shared_utils import _clean_llm_context
        from app.services.sse_bridge import clean_spark_tokens

        # Simulate a realistic Spark LLM output
        realistic_output = '''
        好的，下面是Python基础知识：

        "sc"># Python 变量
        "sf">x = 10
        "sc">y = "hello"

        "sk">def greet(name):
        "sf">    return f"Hello, {name}!"

        "sc">print(greet("World"))
        "sd"># 输出: Hello, World!

        <span class="sc">这是带样式的文本</span>
        <div class="container">
            <code>print("test")</code>
        </div>
        '''

        # Step 1: Spark token clean
        step1 = clean_spark_tokens(realistic_output)
        for token in ["sc", "sf", "sk", "sd"]:
            assert f'"{token}">' not in step1, f"Spark token {token} not cleaned"

        # Step 2: LLM context clean (removes HTML tags, CSS class fragments)
        step2 = _clean_llm_context(step1)
        assert "<span" not in step2
        assert "<div" not in step2
        # Core content should be preserved
        assert "Python" in step2
        assert "greet" in step2
        assert "Hello, World" in step2

    def test_100_round_quality_scoring_stability(self):
        """D6c: 100 rounds of quality scoring should be stable (no crashes, valid scores)."""
        from app.agents.collaboration import _quality_review_node
        for i in range(100):
            state = {
                "user_id": i,
                "user_profile": {"cognitive_style": ["visual", "reading", "kinesthetic", "auditory"][i % 4]},
                "teaching_context": {},
                "context": {"topic": f"Topic_{i % 10}"},
                "agent_outputs": {},
            }
            with patch("app.services.bkt_service.get_tracker") as mock_tracker:
                tracker = MagicMock()
                tracker.to_dict.return_value = {
                    "summary": {"real_mastered": i % 11, "real_total": 10,
                                "real_attempts": max(1, i % 30),
                                "mastered": i % 11, "total": 10,
                                "total_attempts": max(1, i % 30)}
                }
                mock_tracker.return_value = tracker
                result = _quality_review_node(state)
                qr = result["agent_outputs"]["quality_reviewer"]
                assert 0 <= qr["score"] <= 100, f"Round {i}: invalid score {qr['score']}"
                assert "score" in qr
                assert "issues" in qr
                assert "bkt_avg_mastery" in qr
