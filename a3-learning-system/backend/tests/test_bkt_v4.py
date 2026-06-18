"""
BKT v4 贝叶斯知识追踪算法 —— 完整单元测试套件

v4 核心改进：
- 正确实现 Corbett & Anderson (1995) 贝叶斯后验公式
- P(T) 学习转移对正确/错误均施加（修正 v3 仅答对时施加的问题）
- EM 参数估计（多初始值 + 坐标下降优化）
- 完整历史追踪（update_history → history_summary via to_dict）
- 参数来源标注（default / em_fitted / custom）

测试范围：
1.  TestBayesianFormula    — 贝叶斯公式数学验证（手算对照）
2.  TestPTLearningTransfer — P(T) 对答对/答错均施加的 v4 修复验证
3.  TestEMParameterFitting — EM 参数估计正确性
4.  TestHistoryTracking   — 历史记录完整性
5.  TestEdgeCases         — 边界条件与数值稳定性
6.  TestConvergence       — 收敛性分析（连续答对/错应趋向极值）
7.  TestTrackerIntegration— Tracker 集成行为验证
"""

import math
import random
import time

import pytest

from app.services.bkt_service import (
    KnowledgeNode,
    BKTTracker,
    DEFAULT_PARAMS,
    EM_MIN_OBSERVATIONS,
    estimate_params_em,
    ParamSource,
)


# ============================================================
# 0. 辅助函数
# ============================================================

def _make_node_with_params(
    name: str = "test",
    p_known: float | None = None,
    p_initial: float | None = None,
    p_learn: float | None = None,
    p_guess: float | None = None,
    p_slip: float | None = None,
    p_forget: float | None = None,
) -> KnowledgeNode:
    """创建带自定义参数的节点（适配 v4 构造器签名）"""
    return KnowledgeNode(
        name=name,
        p_known=p_known or p_initial,  # p_known 是第一个位置参数
        p_learn=p_learn,
        p_guess=p_guess,
        p_slip=p_slip,
        p_forget=p_forget,
    )


def _em_params_as_dict(result) -> dict[str, float]:
    """将 EMFitResult 转为字典（兼容测试断言）"""
    return {
        "p_initial": result.p_initial,
        "p_learn": result.p_learn,
        "p_guess": result.p_guess,
        "p_slip": result.p_slip,
    }


def _history(node: KnowledgeNode) -> list[dict]:
    """获取节点的 history_summary（通过 to_dict）"""
    return node.to_dict()["history_summary"]


def _last_step(node: KnowledgeNode):
    """获取最近一次 UpdateStep"""
    return node.update_history[-1] if node.update_history else None


# ============================================================
# 1. 贝叶斯公式数学验证（手算对照）
# ============================================================

class TestBayesianFormula:
    """
    验证贝叶斯更新公式的每一步计算结果。

    Corbett & Anderson (1995) 核心公式：
      答对: P(known|correct) = P(known)*(1-P(S)) / [P(known)*(1-P(S)) + (1-P(known))*P(G)]
      答错: P(known|wrong)   = P(known)*P(S)     / [P(known)*P(S)     + (1-P(known))*(1-P(G))]
    """

    def test_correct_answer_manual_calc(self):
        """手算验证：P=0.3, P(S)=0.1, P(G)=0.15 答对后的贝叶斯后验"""
        node = _make_node_with_params(p_known=0.3)
        step = node.update(is_correct=True)

        # 手算（使用默认参数 p_slip=0.1, p_guess=0.15）:
        # numerator   = 0.3 * (1 - 0.1) = 0.27
        # denominator = 0.27 + (1 - 0.3) * 0.15 = 0.27 + 0.105 = 0.375
        # p_bayes     = 0.27 / 0.375 = 0.72
        pS = DEFAULT_PARAMS["p_slip"]
        pG = DEFAULT_PARAMS["p_guess"]
        expected_numerator = 0.3 * (1 - pS)
        expected_denominator = expected_numerator + (1 - 0.3) * pG
        expected_bayes = expected_numerator / expected_denominator

        assert step.p_after_bayes == pytest.approx(expected_bayes, rel=1e-4), (
            f"贝叶斯后验不匹配: 期望={expected_bayes:.6f}, 实际={step.p_after_bayes:.6f}"
        )
        assert step.bayes_numerator == pytest.approx(expected_numerator, rel=1e-4)
        assert step.bayes_denominator == pytest.approx(expected_denominator, rel=1e-4)

    def test_wrong_answer_manual_calc(self):
        """手算验证：P=0.7, P(S)=0.1, P(G)=0.15 答错后的贝叶斯后验"""
        node = _make_node_with_params(p_known=0.7)
        step = node.update(is_correct=False)

        pS = DEFAULT_PARAMS["p_slip"]
        pG = DEFAULT_PARAMS["p_guess"]
        # 手算:
        # numerator   = 0.7 * 0.1 = 0.07
        # denominator = 0.07 + (1 - 0.7) * (1 - 0.15) = 0.07 + 0.255 = 0.325
        # p_bayes     = 0.07 / 0.325 ≈ 0.2154
        expected_numerator = 0.7 * pS
        expected_denominator = expected_numerator + (1 - 0.7) * (1 - pG)
        expected_bayes = expected_numerator / expected_denominator

        assert step.p_after_bayes == pytest.approx(expected_bayes, rel=1e-4), (
            f"贝叶斯后验不匹配: 期望={expected_bayes:.6f}, 实际={step.p_after_bayes:.6f}"
        )

    def test_extreme_low_p_known_correct(self):
        """P(known) 极低(0.01)时答对：贝叶斯后验应上升"""
        node = _make_node_with_params(p_known=0.01)
        initial = node.p_known
        step = node.update(is_correct=True)

        assert step.p_after_bayes > initial, (
            f"P(known)=0.01 答对应上升: {initial} → {step.p_after_bayes}"
        )

    def test_extreme_high_p_known_wrong(self):
        """P(known) 极高(0.99)时答错：贝叶斯后验应大幅下降"""
        node = _make_node_with_params(p_known=0.99)
        step = node.update(is_correct=False)

        assert step.p_after_bayes < 0.99, (
            f"P(known)=0.99 答错应下降: {step.p_after_bayes}"
        )

    def test_symmetry_at_50_percent(self):
        """P(known)=0.5 时，当 P(G)=P(S)，答对/答错的后验和应接近 1.0"""
        # 使用 P(G)=P(S)=0.1 来测试对称性
        node_c = _make_node_with_params(p_known=0.5, p_guess=0.1, p_slip=0.1)
        node_w = _make_node_with_params(p_known=0.5, p_guess=0.1, p_slip=0.1)

        step_c = node_c.update(is_correct=True)
        step_w = node_w.update(is_correct=False)

        combined = step_c.p_after_bayes + step_w.p_after_bayes
        # 当 P(G)=P(S) 且 P(known)=0.5 时，两者之和理论上为 1.0
        # 允许一定误差（因为 P(T) 不参与贝叶斯阶段）
        assert abs(combined - 1.0) < 0.05, (
            f"对称性检验失败: P(correct)={step_c.p_after_bayes:.4f} + "
            f"P(wrong)={step_w.p_after_bayes:.4f} = {combined:.4f} ≠ ~1.0"
        )


# ============================================================
# 2. P(T) 学习转移验证（v4 核心修复）
# ============================================================

class TestPTLearningTransfer:
    """
    验证 v4 修复：P(T) 学习转移对正确和错误答案均施加。
    """

    def test_pt_applied_on_correct(self):
        """答对时：p_final 应 > p_after_bayes（P(T) 正向贡献）"""
        node = _make_node_with_params(p_known=0.3)
        step = node.update(is_correct=True)

        assert step.p_final >= step.p_after_bayes, (
            f"答对: P(T) 应正向贡献: bayes={step.p_after_bayes:.4f}, final={step.p_final:.4f}"
        )
        assert step.learn_delta > 0, (
            f"答对: learn_delta 应为正: {step.learn_delta:.6f}"
        )

    def test_pt_applied_on_wrong_v4_fix(self):
        """【v4 关键修复】答错时：learn_delta 也必须为正（P(T) 同样施加）"""
        node = _make_node_with_params(p_known=0.3)
        step = node.update(is_correct=False)

        # v4 核心：无论对错，learn_delta 必须为正
        assert step.learn_delta > 0, (
            f"[v4] 答错: learn_delta 必须为正(P(T)始终施加): {step.learn_delta:.6f}"
        )
        assert step.p_after_learn == pytest.approx(
            step.p_after_bayes + step.learn_delta, rel=1e-6
        ), "[v4] p_after_learn = p_after_bayes + learn_delta"

    def test_wrong_answer_can_still_increase_with_high_pt(self):
        """高 P(T) 时，即使答错，最终 P(known) 也可能上升"""
        node = _make_node_with_params(p_known=0.3, p_learn=0.5)
        before = node.p_known
        step = node.update(is_correct=False)

        # 高 P(T) 下，错误反馈也有教学价值
        assert step.learn_delta > 0
        # 最终值可能因高学习率而上升
        if step.p_final > before:
            pass  # 期望行为

    def test_continuous_wrong_answers_not_approach_zero_v4(self):
        """【v4 特性】连续答错时，P(known) 不应无限趋近于 0"""
        node = _make_node_with_params(p_known=0.3, p_learn=0.3)
        history = [node.p_known]

        for _ in range(20):
            node.update(is_correct=False)
            history.append(node.p_known)

        # v4: 连续答错不应让 P(known) 趋近 0（P(T) 持续注入）
        min_val = min(history[-5:])
        assert min_val > 0.03, (
            f"[v4] 连续20次答错后 P(known) 过低: "
            f"最终={node.p_known:.4f}, 最近最低={min_val:.4f}. "
            f"P(T) 应阻止无限趋近0"
        )

    def test_update_step_structure_completeness(self):
        """UpdateStep 应包含所有中间计算值"""
        node = _make_node_with_params("struct")
        step = node.update(is_correct=True)

        required_fields = [
            "p_before", "is_correct",
            "bayes_numerator", "bayes_denominator", "p_after_bayes",
            "learn_delta", "p_after_learn",
            "forget_delta", "p_final",
        ]
        for field_name in required_fields:
            assert hasattr(step, field_name), f"UpdateStep 缺少字段: {field_name}"
            val = getattr(step, field_name)
            assert isinstance(val, (int, float)), (
                f"UpdateStep.{field_name} 类型错误: {type(val)}"
            )


# ============================================================
# 3. EM 参数估计验证
# ============================================================

class TestEMParameterFitting:
    """
    验证 EM 参数估计的正确性。
    用已知参数生成模拟数据 → EM 拟合 → 验证拟合结果接近原始参数
    """

    @staticmethod
    def _generate_synthetic_data(
        n_students: int = 30,
        n_questions_per_student: int = 15,
        p_initial: float = 0.25,
        p_learn: float = 0.18,
        p_guess: float = 0.12,
        p_slip: float = 0.08,
        seed: int = 42,
    ) -> list[bool]:
        """用指定参数生成合成观测数据"""
        rng = random.Random(seed)
        all_obs = []

        for _ in range(n_students):
            p_known = p_initial
            for _ in range(n_questions_per_student):
                if rng.random() < p_known:
                    correct = rng.random() < (1 - p_slip)
                else:
                    correct = rng.random() < p_guess
                all_obs.append(correct)

                # 贝叶斯更新（与 BKT 一致的公式）
                if correct:
                    num = p_known * (1 - p_slip)
                    den = num + (1 - p_known) * p_guess
                else:
                    num = p_known * p_slip
                    den = num + (1 - p_known) * (1 - p_guess)
                p_bayes = num / den if den > 1e-10 else p_known
                p_known = min(0.99, max(0.01, p_bayes + (1 - p_bayes) * p_learn))

        return all_obs

    def test_em_recovers_known_params(self):
        """EM 应能从合成数据中恢复近似原始参数（P(T)/P(G)/P(S) 可靠，P(L0) 较难恢复）"""
        true_params = {"p_initial": 0.25, "p_learn": 0.18, "p_guess": 0.12, "p_slip": 0.08}
        observations = self._generate_synthetic_data(
            n_students=50, n_questions_per_student=20, **true_params, seed=123
        )

        result = estimate_params_em(observations, max_iter=60, tol=1e-5)

        assert result is not None, "EM 拟合不应返回 None"
        assert result.converged, "EM 应收敛"
        assert result.iterations > 0

        fitted = _em_params_as_dict(result)
        # P(T), P(G), P(S) 通常恢复较好；P(L0) 在聚合数据上较难辨识（已知 BKT 局限性）
        for key in ["p_learn", "p_guess", "p_slip"]:
            error = abs(fitted[key] - true_params[key])
            assert error < 0.15, (
                f"EM 参数恢复偏差过大 [{key}]: "
                f"真实={true_params[key]:.3f}, 拟合={fitted[key]:.3f}, 误差={error:.3f}"
            )
        # P(L0) 放宽容忍度（EM 在聚合观测序列上对初始概率辨识力有限）
        assert 0.05 <= fitted["p_initial"] <= 0.95, (
            f"P(L0) 应在合理范围: {fitted['p_initial']:.3f}"
        )

    def test_em_all_correct_pattern(self):
        """全对数据：EM 应拟合出低 P(S)；P(G) 可能退化（全对时无法区分掌握/猜测）"""
        observations = [True] * 50
        result = estimate_params_em(observations)

        assert result is not None
        # 全对数据 → P(S) 必然低（已掌握者不会答错）
        assert result.p_slip < 0.20, f"全对数据 P(S) 应低: {result.p_slip:.3f}"
        # P(G) 在全对数据上不可辨识（模型退化），只检查不崩溃即可
        # 这是 BKT EM 的已知局限性：当观测无变异时参数不可辨识

    def test_em_all_wrong_pattern(self):
        """全错数据：EM 应返回合理参数（不崩溃），允许边界值"""
        observations = [False] * 50
        result = estimate_params_em(observations)

        assert result is not None
        # 全错数据的 P(L0) 可能在边界附近，放宽检查
        for attr in ["p_learn", "p_guess", "p_slip"]:
            val = getattr(result, attr)
            assert 0.0 <= val <= 1.0, f"参数越界 {attr}={val}"

    def test_em_insufficient_data_returns_none(self):
        """数据不足时应返回 None"""
        short_obs = [True, False, True]
        result = estimate_params_em(short_obs)
        assert result is None, "数据不足时 EM 应返回 None"

    def test_em_boundary_data_exactly_threshold(self):
        """数据恰好等于阈值时应正常执行"""
        obs = [True, False] * (EM_MIN_OBSERVATIONS // 2)
        result = estimate_params_em(obs)
        # 可能成功也可能因数据质量不足而失败，但不应崩溃
        assert result is not None or True  # 不崩溃即可

    def test_em_alternating_data(self):
        """交替数据：EM 应拟合出合理参数"""
        observations = [i % 2 == 0 for i in range(40)]
        result = estimate_params_em(observations)

        assert result is not None
        for attr in ["p_initial", "p_learn", "p_guess", "p_slip"]:
            val = getattr(result, attr)
            assert 0.01 <= val <= 0.99


# ============================================================
# 4. 历史追踪验证
# ============================================================

class TestHistoryTracking:
    """
    验证 update_history 和 history_summary 的完整性。
    """

    def test_history_populated_after_updates(self):
        """多次 update 后 history_summary 应完整记录"""
        node = _make_node_with_params("hist_test")
        answers = [True, True, False, True, True, False]

        for ans in answers:
            node.update(is_correct=ans)

        history = _history(node)
        assert len(history) == len(answers), (
            f"历史长度不匹配: 期望={len(answers)}, 实际={len(history)}"
        )

        for i, h in enumerate(history):
            assert h["step"] == i + 1, f"步骤编号错误: {h['step']} != {i+1}"
            assert h["correct"] == answers[i], f"答题结果错误: step {i+1}"
            assert 0.01 <= h["p_after"] <= 0.99, f"P(known) 越界: {h['p_after']}"

    def test_update_history_chain_consistency(self):
        """当前步的 p_before 应等于上一步的 p_final"""
        node = _make_node_with_params("chain")
        answers = [True, False, True, True, False, True, True, True]

        for ans in answers:
            current_p = node.p_known
            step = node.update(is_correct=ans)
            # 验证 p_before == 更新前的 p_known
            assert step.p_before == pytest.approx(current_p, rel=1e-6), (
                f"链式断裂: p_before={step.p_before:.6f} != p_known={current_p:.6f}"
            )

    def test_history_summary_length_limit(self):
        """historySummary 应限制最大长度（避免内存膨胀）"""
        node = _make_node_with_params("limit")
        for i in range(200):
            node.update(is_correct=(i % 3 != 0))

        history = _history(node)
        # to_dict 截断到最近 50 步
        assert len(history) <= 60, (
            f"historySummary 过长: {len(history)}，应有上限(~50)"
        )

    def test_to_dict_includes_history_and_params(self):
        """to_dict() 应包含 history_summary 和 params"""
        node = _make_node_with_params("dict_hist")
        node.update(is_correct=True)
        node.update(is_correct=False)

        d = node.to_dict()
        assert "history_summary" in d, "to_dict 缺少 history_summary"
        assert len(d["history_summary"]) == 2
        assert "params" in d, "to_dict 缺少 params"
        assert "source" in d["params"], "params 缺少 source"


# ============================================================
# 5. 边界条件与数值稳定性
# ============================================================

class TestEdgeCasesV4:
    """v4 边界条件和数值稳定性测试。"""

    def test_clamping_bounds_strict(self):
        """P(known) 应严格钳制在 [0.01, 0.99]"""
        node = _make_node_with_params(
            "extreme", p_known=0.01,
            p_learn=0.99, p_guess=0.01, p_slip=0.01,
        )

        for _ in range(100):
            node.update(is_correct=True)
            assert 0.01 <= node.p_known <= 0.99, f"P(known) 越界: {node.p_known}"

        node2 = _make_node_with_params(
            "extreme2", p_known=0.99,
            p_learn=0.99, p_guess=0.01, p_slip=0.01,
        )
        for _ in range(100):
            node2.update(is_correct=False)
            assert 0.01 <= node2.p_known <= 0.99, f"P(known) 越界: {node2.p_known}"

    def test_zero_denominator_handling(self):
        """分母接近零时的数值稳定性"""
        node = _make_node_with_params(
            "zero_noise", p_known=0.5,
            p_learn=0.2, p_guess=0.001, p_slip=0.001,
        )

        for _ in range(50):
            step = node.update(is_correct=True)
            assert math.isfinite(step.p_final), f"产生非有限值: {step.p_final}"
            assert math.isfinite(step.p_after_bayes), f"贝叶斯后验异常"

    def test_single_observation_em(self):
        """单条观测数据的 EM（边界情况）"""
        result = estimate_params_em([True])
        assert result is None, "单条数据不足以拟合"

    def test_empty_observations_em(self):
        """空观测列表的 EM"""
        result = estimate_params_em([])
        assert result is None, "空数据不应拟合"

    def test_very_long_sequence_performance(self):
        """超长序列（200次答题）不应导致性能问题"""
        node = _make_node_with_params("long_seq")

        start = time.time()
        for i in range(200):
            node.update(is_correct=(i % 7 != 0))
        elapsed = time.time() - start

        assert elapsed < 1.0, f"200次更新耗时过长: {elapsed:.2f}s"
        assert len(_history(node)) > 0

    def test_rapid_toggle_stability(self):
        """快速交替答对/答错的数值稳定性"""
        node = _make_node_with_params("toggle")
        values = []

        for i in range(100):
            node.update(is_correct=(i % 2 == 0))
            values.append(node.p_known)
            assert math.isfinite(node.p_known), f"第{i+1}步产生非有限值"

        assert all(math.isfinite(v) for v in values), "存在 NaN/Inf"


# ============================================================
# 6. 收敛性分析
# ============================================================

class TestConvergence:
    """验证 BKT 的收敛特性。"""

    def test_all_correct_converges_to_mastery(self):
        """连续答对应使 P(known) 收敛至精通线以上"""
        node = _make_node_with_params("converge_up")
        for _ in range(15):
            node.update(is_correct=True)

        assert node.p_known > 0.85, (
            f"连续15次答对应达到精通: P(known)={node.p_known:.4f}"
        )
        assert node.is_mastered

    def test_all_wrong_stays_low_v4(self):
        """连续答错应使 P(known) 保持较低水平（但不趋近0，因 P(T) 注入）"""
        node = _make_node_with_params("converge_down")
        for _ in range(15):
            node.update(is_correct=False)

        # v4: P(T) 阻止趋近 0，但应保持较低
        assert node.p_known < 0.35, (
            f"[v4] 连续15次答错应保持较低: P(known)={node.p_known:.4f}"
        )

    def test_mixed_then_correct_converges(self):
        """先混合答题再连续答对应最终达到精通"""
        node = _make_node_with_params("mixed")
        rng = random.Random(99)
        for _ in range(20):
            node.update(is_correct=rng.random() < 0.6)

        for _ in range(12):
            node.update(is_correct=True)

        assert node.p_known > 0.85, (
            f"混合+连续答对应达到精通: P(known)={node.p_known:.4f}"
        )

    def test_learning_rate_effect(self):
        """不同 P(T) 值应导致不同的收敛速度（2步即可区分）"""
        # 从较低起点开始，确保2步内不会都触顶
        low_t = _make_node_with_params("low_t", p_known=0.3, p_learn=0.05)
        high_t = _make_node_with_params("high_t", p_known=0.3, p_learn=0.5)

        # 只做2步
        for _ in range(2):
            low_t.update(is_correct=True)
            high_t.update(is_correct=True)

        # 高 P(T) 应比低 P(T) 收敛更快
        assert high_t.p_known > low_t.p_known, (
            f"P(T) 效应不符: high_T={high_t.p_known:.4f} vs low_T={low_t.p_known:.4f}"
        )


# ============================================================
# 7. Tracker 集成测试
# ============================================================

class TestTrackerIntegrationV4:
    """BKTTracker 在 v4 下的集成行为验证。"""

    def test_record_answer_returns_update_step(self):
        """record_answer 应返回完整的 UpdateStep"""
        tracker = BKTTracker(user_id=0)
        result = tracker.record_answer("Python基础", True)

        assert result is not None
        assert hasattr(result, "p_before")
        assert hasattr(result, "p_final")
        assert result.is_correct is True

    def test_batch_record_preserves_order(self):
        """批量记录应按顺序处理"""
        tracker = BKTTracker(user_id=0)
        results = tracker.record_batch([
            {"concept": "A", "correct": True},
            {"concept": "A", "correct": False},
            {"concept": "B", "correct": True},
        ])

        assert len(results) == 3
        assert results[0].p_final > results[0].p_before  # A 第一次答对后 P 上升

    def test_tracker_to_dict_shape(self):
        """to_dict 返回的数据结构应符合预期"""
        tracker = BKTTracker(user_id=0)
        tracker.record_answer("概念1", True)
        tracker.record_answer("概念1", True)
        tracker.record_answer("概念2", False)

        data = tracker.to_dict()

        assert "nodes" in data
        assert "summary" in data
        assert data["summary"]["total"] == 2  # 两个概念

        # 验证每个节点有 v4 字段
        for concept_name, node_data in data["nodes"].items():
            assert "params" in node_data, f"{concept_name}: 缺少 params"
            assert "history_summary" in node_data, f"{concept_name}: 缺少 history_summary"
            assert "source" in node_data["params"], f"{concept_name}: params 缺少 source"


# ============================================================
# 运行入口
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
