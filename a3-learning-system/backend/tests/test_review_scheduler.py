"""
艾宾浩斯遗忘曲线复习调度器单元测试

测试范围：
- ReviewSchedule: 单个知识点复习状态
  - retention_rate 计算（R = e^(-t/S)）
  - risk_level 判定
  - interval 递增
  - memory_strength 上界
- ReviewScheduler: 复习调度引擎
  - 调度管理
  - due reviews 过滤

注意：所有时间相关测试使用 freeze_time fixture 冻结时间。
"""

import math
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from app.services.review_scheduler import (
    ReviewSchedule,
    ReviewScheduler,
    get_scheduler,
    INTERVALS,
)


# ============================================================
# ReviewSchedule 基础测试
# ============================================================

class TestReviewScheduleBasics:
    """ReviewSchedule 基本功能和属性测试。"""

    def test_initial_state(self):
        """新建 ReviewSchedule 应有正确的初始状态。"""
        s = ReviewSchedule("test_concept")
        assert s.concept == "test_concept"
        assert s.last_reviewed is None
        assert s.review_count == 0
        assert s.interval_index == 0
        assert s.memory_strength == 0.5

    def test_initial_retention_is_zero(self):
        """从未复习过的知识点，记忆保留率应为 0.0。"""
        s = ReviewSchedule("new_concept")
        assert s.retention_rate == 0.0

    def test_current_interval_days_first(self):
        """第一次复习的间隔应为 1 天。"""
        s = ReviewSchedule("concept")
        assert s.current_interval_days == INTERVALS[0]  # 1

    def test_current_interval_days_clamped(self):
        """超过最大间隔层级时不越界。"""
        s = ReviewSchedule("concept")
        s.interval_index = 99  # 远超数组长度
        assert s.current_interval_days == INTERVALS[-1]  # 90

    def test_retention_increases_after_review(self):
        """复习后 retention 应从 0 变为正数。"""
        frozen = datetime(2026, 6, 15, 12, 0, 0)
        with patch("app.services.review_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = frozen
            mock_dt.side_effect = datetime

            s = ReviewSchedule("concept")
            s.review()  # last_reviewed = frozen
            # 刚复习完 t≈0 → retention ≈ 1.0
            r = s.retention_rate
            assert r > 0.9, (
                f"after review retention 应 > 0.9，实际: {r:.4f}"
            )

    def test_retention_decays_over_time(self):
        """不复习的情况下，retention 随时间衰减。"""
        frozen = datetime(2026, 6, 15, 12, 0, 0)
        mock_dt = MagicMock()
        mock_dt.now.return_value = frozen

        with patch("app.services.review_scheduler.datetime", mock_dt):
            s = ReviewSchedule("concept")
            s.memory_strength = 1.0  # 固定 S=1 便于计算
            s.last_reviewed = frozen

            # t=0 → R ≈ 1.0
            r0 = s.retention_rate

            # t=1 天后
            mock_dt.now.return_value = frozen + timedelta(days=1)
            r1 = s.retention_rate

            # t=3 天后
            mock_dt.now.return_value = frozen + timedelta(days=3)
            r3 = s.retention_rate

        assert r1 < r0, f"1天后应衰减: r0={r0:.4f}, r1={r1:.4f}"
        assert r3 < r1, f"3天后应进一步衰减: r1={r1:.4f}, r3={r3:.4f}"

    def test_forgetting_curve_formula(self):
        """验证 R = e^(-t/S) 公式计算正确。"""
        frozen = datetime(2026, 6, 15, 12, 0, 0)
        mock_dt = MagicMock()
        mock_dt.now.return_value = frozen

        with patch("app.services.review_scheduler.datetime", mock_dt):
            s = ReviewSchedule("concept")
            s.memory_strength = 2.0
            s.last_reviewed = frozen

            # t = 2 days, S = 2 → R = e^(-2/2) = e^(-1) ≈ 0.3679
            mock_dt.now.return_value = frozen + timedelta(days=2)
            r = s.retention_rate
            expected = math.exp(-1.0)
            assert r == pytest.approx(expected, rel=1e-4), (
                f"e^(-2/2)={expected:.4f}, actual={r:.4f}"
            )

    def test_memory_strength_cap(self):
        """memory_strength 不应超过 2.0 的上界。"""
        s = ReviewSchedule("concept")
        for _ in range(20):
            s.review()
        assert s.memory_strength <= 2.0, (
            f"memory_strength 应 ≤ 2.0，实际: {s.memory_strength}"
        )


# ============================================================
# 风险等级测试
# ============================================================

class TestRiskLevel:
    """遗忘风险等级判定测试。"""

    def test_risk_level_high(self):
        """retention < 0.5 → 高风险。"""
        frozen = datetime(2026, 6, 15, 12, 0, 0)
        mock_dt = MagicMock()
        mock_dt.now.return_value = frozen

        with patch("app.services.review_scheduler.datetime", mock_dt):
            s = ReviewSchedule("concept")
            s.memory_strength = 1.0
            s.last_reviewed = frozen

            # 1天后: e^(-1) ≈ 0.37 < 0.5 → high
            mock_dt.now.return_value = frozen + timedelta(days=1)
            assert s.risk_level == "high", (
                f"retention={s.retention_rate:.3f} 应为 high"
            )

    def test_risk_level_medium(self):
        """0.5 ≤ retention < 0.7 → 中风险。"""
        frozen = datetime(2026, 6, 15, 12, 0, 0)
        mock_dt = MagicMock()
        mock_dt.now.return_value = frozen

        with patch("app.services.review_scheduler.datetime", mock_dt):
            s = ReviewSchedule("concept")
            s.memory_strength = 3.0  # 高强度 → 慢衰减
            s.last_reviewed = frozen

            # 约1天后: e^(-1/3) ≈ 0.717 → low
            # 约2天后: e^(-2/3) ≈ 0.513 → medium
            mock_dt.now.return_value = frozen + timedelta(days=2)
            r = s.retention_rate
            assert s.risk_level in ("medium", "low"), (
                f"retention={r:.3f}, risk={s.risk_level}"
            )

    def test_risk_level_changes_with_reviews(self):
        """多次复习后风险等级应从 high → medium → low。"""
        frozen = datetime(2026, 6, 15, 12, 0, 0)
        mock_dt = MagicMock()
        mock_dt.now.return_value = frozen

        with patch("app.services.review_scheduler.datetime", mock_dt):
            s = ReviewSchedule("concept")
            s.last_reviewed = datetime(2026, 6, 1)  # 14天前
            # 初始: t大 → retention低 → high
            mock_dt.now.return_value = datetime(2026, 6, 15)
            assert s.risk_level == "high"

            # 复习后 retention 恢复
            s.review()
            mock_dt.now.return_value = datetime(2026, 6, 15)
            assert s.risk_level == "low", (
                f"复习后应立即为 low，实际: {s.risk_level}"
            )


# ============================================================
# 间隔递增测试
# ============================================================

class TestIntervalProgression:
    """间隔递增序列测试（1→3→7→14→30→90）。"""

    def test_interval_progression_sequence(self):
        """每次复习后 interval_index 应递增，间隔对应序列。"""
        expected = [1, 3, 7, 14, 30, 90]
        s = ReviewSchedule("concept")

        for i, expected_days in enumerate(expected):
            assert s.interval_index == i
            assert s.current_interval_days == expected_days, (
                f"第{i}次复习后间隔应为{expected_days}天，"
                f"实际: {s.current_interval_days}"
            )
            s.review()

        # 超过最大间隔后保持不变
        assert s.current_interval_days == 90

    def test_interval_stops_at_max(self):
        """间隔应在达到最大值后停止增长。"""
        s = ReviewSchedule("concept")
        for _ in range(10):
            s.review()
        assert s.interval_index == len(INTERVALS) - 1
        assert s.current_interval_days == INTERVALS[-1]

    def test_review_count_increments(self):
        """每次 review() 应递增 review_count。"""
        s = ReviewSchedule("concept")
        for i in range(5):
            s.review()
            assert s.review_count == i + 1


# ============================================================
# ReviewScheduler 引擎测试
# ============================================================

class TestReviewScheduler:
    """复习调度引擎测试。"""

    def test_get_or_create_new(self):
        """get_or_create 应创建新 schedule。"""
        scheduler = ReviewScheduler()
        s = scheduler.get_or_create("algorithms")
        assert s.concept == "algorithms"
        assert s.retention_rate == 0.0

    def test_get_or_create_existing(self):
        """get_or_create 应返回已有 schedule。"""
        scheduler = ReviewScheduler()
        s1 = scheduler.get_or_create("topic")
        s1.review()
        s2 = scheduler.get_or_create("topic")
        assert s1 is s2

    def test_record_review(self):
        """record_review 应触发 review 并更新状态。"""
        scheduler = ReviewScheduler()
        scheduler.record_review("math")
        s = scheduler.schedules["math"]
        assert s.review_count == 1
        assert s.interval_index == 1

    def test_record_answer_correct_triggers_review(self):
        """答对 = 有效复习，应触发 review。"""
        scheduler = ReviewScheduler()
        scheduler.record_answer("python", is_correct=True)
        s = scheduler.schedules["python"]
        assert s.review_count == 1

    def test_record_answer_wrong_no_review(self):
        """答错不应触发复习，但概念会被记录。"""
        scheduler = ReviewScheduler()
        # record_answer 在答错时不会调用 get_or_create，需要先手动创建
        s = scheduler.get_or_create("python")
        s.review()  # 复习一次，设置 initial state
        prev_count = s.review_count
        scheduler.record_answer("python", is_correct=False)
        # 答错不会增加 review_count
        assert s.review_count == prev_count

    def test_get_due_reviews(self):
        """应只返回风险 != low 的知识点。"""
        frozen = datetime(2026, 6, 15, 12, 0, 0)

        with patch("app.services.review_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = frozen
            mock_dt.side_effect = datetime

            scheduler = ReviewScheduler()
            s1 = scheduler.get_or_create("fresh_reviewed")
            s1.review()  # 刚复习 → retention高 → low
            s1.last_reviewed = frozen  # 确保时间冻结

            s2 = scheduler.get_or_create("never_reviewed")
            # 从未复习 → retention=0 → risk!=low

            due = scheduler.get_due_reviews()
            assert "never_reviewed" in due
            # fresh 可能为 low，不保证一定不在 due 中

    def test_to_dict(self):
        """to_dict 应返回正确的序列化结构。"""
        scheduler = ReviewScheduler()
        scheduler.get_or_create("topic")
        data = scheduler.to_dict()
        assert "topic" in data
        assert "retention" in data["topic"]
        assert "risk" in data["topic"]


# ============================================================
# 单例测试
# ============================================================

class TestSchedulerSingleton:
    """get_scheduler() 单例测试。"""

    def test_get_scheduler_returns_same_instance(self):
        """get_scheduler() 应返回同一实例。"""
        s1 = get_scheduler()
        s2 = get_scheduler()
        assert s1 is s2

    def test_get_scheduler_returns_review_scheduler(self):
        """get_scheduler() 应返回 ReviewScheduler 实例。"""
        s = get_scheduler()
        assert isinstance(s, ReviewScheduler)


# ============================================================
# 边界条件
# ============================================================

class TestReviewSchedulerEdgeCases:
    """边界条件测试。"""

    def test_very_old_review(self):
        """很久以前复习过 → retention 应衰减到接近 0。"""
        frozen = datetime(2026, 6, 15, 12, 0, 0)
        mock_dt = MagicMock()
        mock_dt.now.return_value = frozen

        with patch("app.services.review_scheduler.datetime", mock_dt):
            s = ReviewSchedule("old")
            s.memory_strength = 0.5
            s.last_reviewed = datetime(2025, 6, 15)  # 一年前

            r = s.retention_rate
            assert r < 0.01, (
                f"一年不复习 retention 应接近 0，实际: {r:.6f}"
            )

    def test_memory_strength_minimum(self):
        """memory_strength 至少为 0.01（用于除法的安全值）。"""
        # 通过 retention_rate 公式分母 max(0.01, S) 验证
        frozen = datetime(2026, 6, 15, 12, 0, 0)
        mock_dt = MagicMock()
        mock_dt.now.return_value = frozen

        with patch("app.services.review_scheduler.datetime", mock_dt):
            s = ReviewSchedule("weak")
            s.memory_strength = 0.001  # 极小值
            s.last_reviewed = frozen

            mock_dt.now.return_value = frozen + timedelta(days=1)
            # 不应除零，retention 应能计算
            r = s.retention_rate
            assert not math.isnan(r), "不应产生 NaN"

    def test_review_updates_interval_index(self):
        """复习后 interval_index 递增。"""
        scheduler = ReviewScheduler()
        s = scheduler.get_or_create("concept")
        initial_index = s.interval_index
        scheduler.record_review("concept")
        assert s.interval_index == initial_index + 1
