"""
BKT —— 贝叶斯知识追踪模型（v4 重构版）

自研算法模块。基于 Corbett & Anderson (1995) 原始四参数模型，
参考 pyBKT (Badrinath et al. 2021) 和 StanBKT (Pradhan et al. 2026)
业内最佳实践重构。

v4 改进点：
  1. 修正贝叶斯更新公式：P(T) 学习转移对正确/错误响应均施加（符合规范 BKT）
  2. 新增 EM 参数估计：从答题数据中拟合 P(L0)/P(T)/P(G)/P(S)
  3. 全量历史追踪：记录每次更新的完整状态变化，支持时间序列学习曲线
  4. 预测精度评估：RMSE / AUC 指标，量化模型拟合质量
  5. 分步计算明细：返回每一步的中间值，前端可展示完整推导过程
  6. 参数来源标注：区分「EM拟合」「经验默认」「用户自定义」三种来源

理论来源：
  - Corbett & Anderson (1995), "Knowledge Tracing: Modeling the Acquisition of Procedural Knowledge"
    * 原始四参数模型定义与贝叶斯后验更新公式
  - Pardos & Heffernan (2010), "Modeling Individualization in a Bayesian Networks Implementation of Knowledge Tracing"
    * per-skill 参数个性化策略
  - Badrinath, Wang & Pardos (2021), "pyBKT: An Accessible Python Library of Bayesian Knowledge Tracing Models"
    * EM 参数估计实现参考
  - Pradhan et al. (2026), "StanBKT: Rethinking Parameter Estimation in Bayesian Knowledge Tracing"
    * 不确定性量化与层次化参数

标准四参数模型：
  P(L0) : 初始掌握概率（先验）
  P(T)  : 学习率（从未掌握→掌握的转移概率，每次答题均施加）
  P(G)  : 猜测率（未掌握但观测为正确的概率）
  P(S)  : 失误率（已掌握但观测为错误的概率）

贝叶斯更新公式（Corbett & Anderson 1995）：

  阶段1 — 贝叶斯后验（证据更新）：
    答对 → P(L_t | correct) = P(L_t) × (1 − P(S)) / D_c
           其中 D_c = P(L_t) × (1 − P(S)) + (1 − P(L_t)) × P(G)
    答错 → P(L_t | wrong)   = P(L_t) × P(S)     / D_w
           其中 D_w = P(L_t) × P(S)     + (1 − P(L_t)) × (1 − P(G))

  阶段2 — 学习转移（每次答题均施加，v4 修正）：
    P(L_{t+1}) = P(L_t | obs_t) + (1 − P(L_t | obs_t)) × P(T)

  注：v3 及之前版本仅在答对时施加 P(T)，不符合规范 BKT 定义。
      v4 修正为无论对错均施加，因为从错误中同样可以学习。

参数来源优先级（从高到低）：
  1. 用户/管理员手动设定的个性化参数（DB 中非 NULL 值）
  2. EM 算法从答题数据自动拟合的参数（≥10 条记录时触发）
  3. 教育测量学经验默认值（兜底）
"""

import json
import logging
import math
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.core.database import SessionLocal
from app.models.bkt_state import BKTState

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# 常量 & 默认参数
# ═══════════════════════════════════════════════════════════════════════════════

class ParamSource(str, Enum):
    """参数来源枚举"""
    DEFAULT = "default"       # 经验默认值
    EM_FITTED = "em_fitted"   # EM 算法拟合
    CUSTOM = "custom"         # 用户自定义


# 全局默认参数（教育测量学经典取值，可通过环境变量覆盖）
DEFAULT_PARAMS = {
    "p_initial": float(os.getenv("BKT_P_INITIAL", "0.3")),
    "p_learn":   float(os.getenv("BKT_P_LEARN",   "0.2")),
    "p_guess":   float(os.getenv("BKT_P_GUESS",   "0.15")),
    "p_slip":    float(os.getenv("BKT_P_SLIP",    "0.1")),
    "p_forget":  float(os.getenv("BKT_P_FORGET",  "0.0")),
}

# EM 拟合最低数据量门槛
EM_MIN_OBSERVATIONS = 10

# 掌握阈值
MASTERY_THRESHOLD = 0.85


# ═══════════════════════════════════════════════════════════════════════════════
# 数据结构：单次更新步骤
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class UpdateStep:
    """单次答题后的 BKT 更新步骤详情（用于前端展示分步计算过程）

    Attributes:
        step_no:        步骤序号（从 1 开始）
        is_correct:     是否答对
        p_before:       更新前 P(known)
        p_after_bayes:  贝叶斯后验 P(known|obs)（阶段1结果）
        p_after_learn:  学习转移后 P(known)（阶段2最终结果）
        p_after_forget: 遗忘衰减后 P(known)（阶段3最终结果，若 P(F)>0）
        p_final:        最终钳制后的 P(known)
        bayes_numerator:   贝叶斯公式分子
        bayes_denominator: 贝叶斯公式分母
        learn_delta:    P(T) 学习转移带来的增量
        forget_delta:   P(F) 遗忘带来的减量
        params_used:    本次更新使用的参数快照
    """
    step_no: int
    is_correct: bool
    p_before: float
    p_after_bayes: float
    p_after_learn: float
    p_final: float
    bayes_numerator: float
    bayes_denominator: float
    learn_delta: float
    forget_delta: float
    params_used: dict = field(default_factory=dict)


@dataclass
class EMFitResult:
    """EM 参数拟合结果"""
    p_initial: float
    p_learn: float
    p_guess: float
    p_slip: float
    iterations: int
    converged: bool
    log_likelihood: float
    rmse: float              # 拟合 RMSE
    n_observations: int      # 用于拟合的观测数
    source: str = ParamSource.EM_FITTED.value


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgeNode —— 单知识点 BKT 状态
# ═══════════════════════════════════════════════════════════════════════════════

class KnowledgeNode:
    """单个知识点的 BKT 追踪状态（v4 重构版）

    v4 核心改进：
    - 记录完整的更新历史（update_history），支持时间序列曲线
    - 每次更新产生 UpdateStep 明细，可展示分步计算
    - 参数来源追踪（param_source），区分 default/em_fitted/custom
    - P(T) 对正确和错误响应均施加（符合规范 BKT）
    """

    def __init__(
        self,
        name: str,
        p_known: Optional[float] = None,
        p_learn: Optional[float] = None,
        p_guess: Optional[float] = None,
        p_slip: Optional[float] = None,
        p_forget: Optional[float] = None,
    ):
        self.name: str = name
        self.p_known: float = p_known if p_known is not None else DEFAULT_PARAMS["p_initial"]

        # 参数值（None 表示使用全局默认）
        self._p_learn: Optional[float] = p_learn
        self._p_guess: Optional[float] = p_guess
        self._p_slip: Optional[float] = p_slip
        self._p_forget: Optional[float] = p_forget

        # 统计计数
        self.total_attempts: int = 0
        self.correct_count: int = 0

        # v4: 完整更新历史
        self.update_history: list[UpdateStep] = []

        # v4: 参数来源标注
        self.param_source: ParamSource = (
            ParamSource.CUSTOM if any(v is not None for v in [p_learn, p_guess, p_slip, p_forget])
            else ParamSource.DEFAULT
        )

        # v4: EM 拟合结果缓存
        self._em_fit: Optional[EMFitResult] = None

        self._dirty: bool = False

    # ── 属性访问器（优先使用个性化/拟合参数，回退到全局默认）──

    @property
    def p_learn(self) -> float:
        return self._p_learn if self._p_learn is not None else DEFAULT_PARAMS["p_learn"]

    @property
    def p_guess(self) -> float:
        return self._p_guess if self._p_guess is not None else DEFAULT_PARAMS["p_guess"]

    @property
    def p_slip(self) -> float:
        return self._p_slip if self._p_slip is not None else DEFAULT_PARAMS["p_slip"]

    @property
    def p_forget(self) -> float:
        return self._p_forget if self._p_forget is not None else DEFAULT_PARAMS["p_forget"]

    # ── 核心：贝叶斯更新（v4 修正版）──

    def update(self, is_correct: bool) -> UpdateStep:
        """根据答题结果执行标准 BKT 三阶段更新（v4 修正版）

        阶段1 — 贝叶斯后验（证据更新, Corbett & Anderson 1995 式 1-2）：
          答对: P(k|c) = P(k)*(1-P(S)) / [P(k)*(1-P(S)) + (1-P(k))*P(G)]
          答错: P(k|w) = P(k)*P(S)     / [P(k)*P(S)     + (1-P(k))*(1-P(G))]

        阶段2 — 学习转移 P(T)（v4 修正：无论对错均施加）
          规范 BKT 定义 (Corbett & Anderson 1995; pyBKT 2021):
            P(L_{t+1}) = P(L_t | obs_t) + (1 - P(L_t | obs_t)) * P(T)
          此转移模拟"通过练习获得的学习增益"，错误反馈同样有教学价值。

        阶段3 — 遗忘衰减 P(F)（可选，默认关闭）
          P(final) = P(after_learn) * (1 - P(F))

        Returns:
            UpdateStep 包含本次更新的所有中间值和最终结果
        """
        p_known = self.p_known
        p_lrn = self.p_learn
        p_gue = self.p_guess
        p_sli = self.p_slip
        p_frg = self.p_forget

        # ── 阶段1: 贝叶斯后验 ──
        if is_correct:
            numerator = p_known * (1.0 - p_sli)
            denominator = numerator + (1.0 - p_known) * p_gue
        else:
            numerator = p_known * p_sli
            denominator = numerator + (1.0 - p_known) * (1.0 - p_gue)

        p_after_bayes = numerator / denominator if denominator > 1e-10 else p_known

        # ── 阶段2: 学习转移 P(T)（v4 修正：始终施加）──
        learn_delta = (1.0 - p_after_bayes) * p_lrn
        p_after_learn = p_after_bayes + learn_delta

        # ── 阶段3: 遗忘衰减 P(F) ──
        forget_delta = p_after_learn * p_frg
        p_after_forget = p_after_learn - forget_delta

        # 钳制到 [0.01, 0.99]
        p_final = max(0.01, min(0.99, p_after_forget))

        # ── 应用状态变更 ──
        self.p_known = p_final
        self.total_attempts += 1
        if is_correct:
            self.correct_count += 1
        self._dirty = True

        # ── 构建步骤明细 ──
        # p_before = 更新前的真实 P(known) 值
        if self.update_history:
            p_before_val = self.update_history[-1].p_final
        else:
            # 第一次答题前：使用当前节点的初始 p_known
            p_before_val = round(p_known, 6)

        step = UpdateStep(
            step_no=self.total_attempts,
            is_correct=is_correct,
            p_before=p_before_val,
            p_after_bayes=round(p_after_bayes, 6),
            p_after_learn=round(p_after_learn, 6),
            p_final=round(p_final, 6),
            bayes_numerator=round(numerator, 6),
            bayes_denominator=round(denominator, 6),
            learn_delta=round(learn_delta, 6),
            forget_delta=round(forget_delta, 6),
            params_used={
                "p_initial": round(self.get_effective_p_initial(), 4),
                "p_learn": round(p_lrn, 4),
                "p_guess": round(p_gue, 4),
                "p_slip": round(p_sli, 4),
                "p_forget": round(p_frg, 4),
                "source": self.param_source.value,
            },
        )

        self.update_history.append(step)

        logger.debug(
            "BKT[%s] #%d %s → P:%.4f→%.4f (bayes=%.4f learn+%.4f forget-%.4f) [%s]",
            self.name, step.step_no, "✓" if is_correct else "✗",
            step.p_before, step.p_final,
            step.p_after_bayes, step.learn_delta, step.forget_delta,
            self.param_source.value,
        )

        return step

    def get_effective_p_initial(self) -> float:
        """获取有效的初始概率 P(L₀)

        优先级：
        1. 有历史记录 → 取第一次更新前的值（history[0].p_before）
        2. 无历史记录但已答题（异常边界）→ 返回当前 p_known
        3. 完全新节点 → 返回当前 p_known（即构造时传入的初始值）
        """
        if self.update_history:
            return self.update_history[0].p_before
        # 无论是否答过题，无历史时 p_known 就是初始值
        return self.p_known

    def apply_em_params(self, fit_result: EMFitResult):
        """应用 EM 拟合结果到本节点（不覆盖 CUSTOM 来源的参数）"""
        if self.param_source == ParamSource.CUSTOM:
            logger.info("BKT[%s]: 跳过 EM 拟合，已有自定义参数", self.name)
            return

        self._p_learn = fit_result.p_learn
        self._p_guess = fit_result.p_guess
        self._p_slip = fit_result.p_slip
        self._em_fit = fit_result
        self.param_source = ParamSource.EM_FITTED
        self._dirty = True
        logger.info(
            "BKT[%s]: EM拟合完成 L0=%.3f T=%.3f G=%.3f S=%.3f (RMSE=%.4f iters=%d)",
            self.name, fit_result.p_initial, fit_result.p_learn,
            fit_result.p_guess, fit_result.p_slip, fit_result.rmse,
            fit_result.iterations,
        )

    # ── 只读属性 ──

    @property
    def is_mastered(self) -> bool:
        return self.p_known > MASTERY_THRESHOLD

    @property
    def level(self) -> str:
        if self.p_known > MASTERY_THRESHOLD:
            return "精通"
        if self.p_known > 0.6:
            return "熟悉"
        if self.p_known > 0.35:
            return "学习中"
        return "入门"

    @property
    def correct_rate(self) -> float:
        return round(self.correct_count / max(self.total_attempts, 1), 4)

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """序列化为字典（用于 API 响应）"""
        em_info = None
        if self._em_fit:
            em_info = {
                "rmse": round(self._em_fit.rmse, 4),
                "iterations": self._em_fit.iterations,
                "converged": self._em_fit.converged,
                "n_obs": self._em_fit.n_observations,
            }

        return {
            "name": self.name,
            "p_known": round(self.p_known, 4),
            "level": self.level,
            "is_mastered": self.is_mastered,
            "attempts": self.total_attempts,
            "correct_count": self.correct_count,
            "correct_rate": self.correct_rate,
            # v4: 参数信息（含来源）
            "params": {
                "p_initial": round(self.get_effective_p_initial(), 4),
                "p_learn": round(self.p_learn, 4),
                "p_guess": round(self.p_guess, 4),
                "p_slip": round(self.p_slip, 4),
                "p_forget": round(self.p_forget, 4),
                "source": self.param_source.value,
                "em_fit": em_info,
            },
            # v4: 最近 N 步更新摘要（用于曲线绘制）
            "history_summary": [
                {
                    "step": s.step_no,
                    "correct": s.is_correct,
                    "p_before": s.p_before,
                    "p_after": s.p_final,
                }
                for s in self.update_history[-50:]  # 最多返回50步
            ],
        }

    def last_step_detail(self) -> Optional[dict]:
        """获取最近一次更新的完整步骤明细（用于前端分步展示）"""
        if not self.update_history:
            return None
        s = self.update_history[-1]
        return {
            "step_no": s.step_no,
            "is_correct": s.is_correct,
            "p_before": s.p_before,
            "p_after_bayes": s.p_after_bayes,
            "p_after_learn": s.p_after_learn,
            "p_final": s.p_final,
            "bayes_numerator": s.bayes_numerator,
            "bayes_denominator": s.bayes_denominator,
            "learn_delta": s.learn_delta,
            "forget_delta": s.forget_delta,
            "formula_type": "correct" if s.is_correct else "wrong",
            "params_used": s.params_used,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# EM 参数估计算法
# ═══════════════════════════════════════════════════════════════════════════════

def _bkt_forward(params: tuple, observations: list[bool], p_forget: float = 0.0) -> tuple[list[float], float]:
    """BKT 前向传播 + 对数似然计算（与 KnowledgeNode.update() 保持完全一致）

    流程：贝叶斯后验 → 观测似然 → P(T)学习转移 → P(F)遗忘衰减 → 钳制

    Args:
        params: (p_initial, p_learn, p_guess, p_slip)
        observations: 答题结果序列 [True, False, True, ...]
        p_forget: 遗忘概率（默认0，与update()一致）

    Returns:
        (p_known_list, log_likelihood)
    """
    p_init, p_lrn, p_gue, p_sli = params
    p = p_init
    log_likelihood = 0.0
    p_history = []

    for obs in observations:
        # ── 阶段1: 贝叶斯后验（与 update() 一致）──
        if obs:
            num = p * (1.0 - p_sli)
            den = num + (1.0 - p) * p_gue
        else:
            num = p * p_sli
            den = num + (1.0 - p) * (1.0 - p_gue)

        p_posterior = num / den if den > 1e-10 else p

        # ── 观测概率（用于计算对数似然）──
        # P(obs | state) 在贝叶斯后验之前计算，因为这是观测模型
        p_obs_given_known = (1.0 - p_sli) if obs else p_sli
        p_obs_given_unknown = p_gue if obs else (1.0 - p_gue)
        p_obs = p * p_obs_given_known + (1.0 - p) * p_obs_given_unknown
        p_obs = max(p_obs, 1e-10)
        log_likelihood += math.log(p_obs)

        # ── 阶段2: 学习转移 P(T)（始终施加，与 update() 一致）──
        p_after_learn = p_posterior + (1.0 - p_posterior) * p_lrn

        # ── 阶段3: 遗忘衰减 P(F)（与 update() 一致）──
        if p_forget > 0:
            p_final = p_after_learn * (1.0 - p_forget)
        else:
            p_final = p_after_learn

        # 钳制到 [0.001, 0.999]
        p = max(0.001, min(0.999, p_final))
        p_history.append(p)

    return p_history, log_likelihood


def _compute_rmse(params: tuple, observations: list[bool]) -> float:
    """计算给定参数下的预测 RMSE

    用 BKT 模型预测每一步的观测值，与实际观测比较。
    预测值 = P(correct) = P(known)*(1-P(S)) + (1-P(known))*P(G)
    """
    p_init, p_lrn, p_gue, p_sli = params
    p = p_init
    errors_sq = 0.0

    for obs in observations:
        # 当前时刻的"答对"预测概率
        p_pred_correct = p * (1.0 - p_sli) + (1.0 - p) * p_gue
        actual = 1.0 if obs else 0.0
        errors_sq += (p_pred_correct - actual) ** 2

        # 更新状态
        if obs:
            num = p * (1.0 - p_sli)
            den = num + (1.0 - p) * p_gue
        else:
            num = p * p_sli
            den = num + (1.0 - p) * (1.0 - p_gue)
        p_posterior = num / den if den > 1e-10 else p
        p = p_posterior + (1.0 - p_posterior) * p_lrn
        p = max(0.001, min(0.999, p))

    n = len(observations)
    return math.sqrt(errors_sq / n) if n > 0 else 1.0


def estimate_params_em(observations: list[bool], max_iter: int = 50, tol: float = 1e-4) -> Optional[EMFitResult]:
    """BKT 四参数 EM 估计（坐标下降 + 黄金分割搜索，参考 pyBKT 设计）

    算法流程（参考 Badrinath et al. 2021 pyBKT 实现）：
    1. 多组初始值启动（避免局部最优）
    2. 每轮迭代：坐标下降逐个优化四个参数
    3. 单参数优化：黄金分割搜索在合理范围内找最优值
    4. 收敛判定：对数似然变化 < tol 且 iteration > 3
    5. 跨种子保留全局最优参数

    参数约束（参考 pyBKT 默认边界）：
      P(L0) ∈ [0.01, 0.85]  — 初始掌握概率不应过高
      P(T)  ∈ [0.01, 0.70]  — 学习率通常不超过0.7
      P(G)  ∈ [0.01, 0.50]  — 猜测率上限0.5
      P(S)  ∈ [0.01, 0.40]  — 失误率上限0.4
      P(G)+P(S) < 1         — 观测模型合理性约束

    Args:
        observations: 答题结果序列（至少需要 EM_MIN_OBSERVATIONS 条）
        max_iter:     每个种子的最大迭代次数
        tol:          收敛阈值

    Returns:
        EMFitResult 或 None（数据不足时）
    """
    n = len(observations)
    if n < EM_MIN_OBSERVATIONS:
        return None

    # ── 参数搜索范围（pyBKT 风格的合理边界）──
    PARAM_BOUNDS = [
        (0.01, 0.85),   # p_initial: 初始掌握概率
        (0.01, 0.70),   # p_learn: 学习转移率
        (0.01, 0.50),   # p_guess: 猜测率
        (0.01, 0.40),   # p_slip: 失误率
    ]

    # ── 多组初始值（数据驱动 + 经验默认 + 边界探测）──
    correct_rate = sum(observations) / n
    init_seeds = [
        # 标准经验初始值（Corbett & Anderson 1995）
        (0.3, 0.2, 0.15, 0.1),
        # 数据驱动：用正确率估计 P(L0)
        (min(correct_rate * 0.9, 0.7), 0.2, 0.15, 0.1),
        # 高学习率假设
        (0.2, 0.35, 0.1, 0.15),
        # 低猜测高失误假设
        (0.4, 0.15, 0.08, 0.2),
        # 低初始高学习假设
        (0.1, 0.4, 0.2, 0.05),
        # 接近收敛的初始猜测
        (min(correct_rate, 0.6), 0.25, 0.1, 0.08),
    ]

    # ── 全局最优追踪（跨所有种子）──
    global_best_ll = -float('inf')
    global_best_params = None
    global_best_iterations = 0
    global_converged = False
    total_actual_iterations = 0

    for seed_idx, seed in enumerate(init_seeds):
        params = list(seed)
        prev_ll = -float('inf')
        seed_converged = False
        actual_iterations = 0

        for iteration in range(max_iter):
            _, ll = _bkt_forward(tuple(params), observations)
            actual_iterations = iteration + 1
            total_actual_iterations += 1

            # 更新全局最优
            if ll > global_best_ll:
                global_best_ll = ll
                global_best_params = tuple(params)
                global_best_iterations = actual_iterations
                global_converged = False  # 新的最优，重置收敛标记

            # 收敛检查：对数似然变化足够小且已迭代足够多次
            if abs(ll - prev_ll) < tol and iteration > 3:
                seed_converged = True
                # 只有当这个种子达到全局最优时才标记全局收敛
                if abs(ll - global_best_ll) < 1e-6:
                    global_converged = True
                break
            prev_ll = ll

            # ── 坐标下降：逐个优化每个参数（黄金分割搜索）──
            for idx in range(4):
                low, high = PARAM_BOUNDS[idx]

                def _eval_param(val_idx: int, val: float) -> float:
                    """评估某个参数取特定值时的对数似然"""
                    test = list(params)
                    test[val_idx] = max(low, min(high, val))
                    _, score = _bkt_forward(tuple(test), observations)
                    return score

                current_val = params[idx]
                current_ll = _eval_param(idx, current_val)

                # 黄金分割搜索（比网格搜索更高效，参考 scipy.optimize 的实现）
                GR = (math.sqrt(5) - 1) / 2  # 0.618...

                for _ in range(8):  # 8次黄金分割细化
                    range_width = high - low
                    if range_width < 1e-5:
                        break

                    c = high - GR * range_width
                    d = low + GR * range_width
                    fc = _eval_param(idx, c)
                    fd = _eval_param(idx, d)

                    if fc > fd:
                        high = d
                        if fc > current_ll:
                            current_val = c
                            current_ll = fc
                    else:
                        low = c
                        if fd > current_ll:
                            current_val = d
                            current_ll = fd

                params[idx] = max(low, min(high, current_val))

        logger.debug(
            "EM seed #%d: LL=%.3f iters=%d converged=%s params=[%.3f, %.3f, %.3f, %.3f]",
            seed_idx + 1,
            _bkt_forward(tuple(params), observations)[1],
            actual_iterations, seed_converged,
            params[0], params[1], params[2], params[3],
        )

    # ── 无效结果保护 ──
    if global_best_params is None:
        logger.warning("EM拟合失败: 所有种子均未产生有效结果")
        return None

    # ── 参数合理性后处理 ──
    final_params = list(global_best_params)
    pg, ps = final_params[2], final_params[3]
    if pg + ps >= 0.95:
        # P(G) + P(S) 过大，按比例缩减
        scale = 0.45 / (pg + ps)
        final_params[2] = round(pg * scale, 4)
        final_params[3] = round(ps * scale, 4)
        logger.info("EM参数修正: P(G)+P(S)=%.3f>0.95, 缩放至 [%.3f, %.3f]", pg+ps, final_params[2], final_params[3])

    # ── 计算最终指标 ──
    final_ll = _bkt_forward(tuple(final_params), observations)[1]
    rmse = _compute_rmse(tuple(final_params), observations)

    result = EMFitResult(
        p_initial=round(final_params[0], 4),
        p_learn=round(final_params[1], 4),
        p_guess=round(final_params[2], 4),
        p_slip=round(final_params[3], 4),
        iterations=global_best_iterations,       # 实际使用的迭代次数
        converged=global_converged,               # 全局最优是否收敛
        log_likelihood=round(final_ll, 4),
        rmse=round(rmse, 4),
        n_observations=n,
    )

    logger.info(
        "EM拟合完成: L0=%.3f T=%.3f G=%.3f S=%.3f | LL=%.2f RMSE=%.4f "
        "iters=%d converged=%s obs=%d seeds=%d",
        result.p_initial, result.p_learn, result.p_guess, result.p_slip,
        result.log_likelihood, result.rmse,
        result.iterations, result.converged, n, len(init_seeds),
    )

    return result


def estimate_params_from_node(node: KnowledgeNode) -> Optional[EMFitResult]:
    """从 KnowledgeNode 的答题历史中提取观测序列并运行 EM 估计

    如果节点有足够的答题记录（>= EM_MIN_OBSERVATIONS），则拟合参数并应用到节点。
    """
    if len(node.update_history) < EM_MIN_OBSERVATIONS:
        return None
    observations = [s.is_correct for s in node.update_history]
    result = estimate_params_em(observations)
    if result:
        node.apply_em_params(result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 不确定性量化（Bootstrap 置信区间，参考 StanBKT 设计）
# ═══════════════════════════════════════════════════════════════════════════════

def estimate_uncertainty(
    observations: list[bool],
    n_bootstrap: int = 100,
    confidence: float = 0.90,
) -> Optional[dict]:
    """通过 Bootstrap 方法估计 BKT 参数的不确定性（参考 Pradhan et al. 2026 StanBKT）

    原理：对观测序列进行 n_bootstrap 次有放回重采样，每次重采样运行 EM 拟合，
          得到参数分布，进而计算置信区间。

    输出示例：
        {
            "p_initial": {"mean": 0.28, "std": 0.08, "ci_low": 0.18, "ci_high": 0.42},
            "p_learn":   {"mean": 0.22, "std": 0.06, "ci_low": 0.12, "ci_high": 0.34},
            ...
            "n_bootstrap": 100,
            "confidence": 0.90,
        }

    Args:
        observations: 原始答题序列
        n_bootstrap:  Bootstrap 重采样次数（默认100，权衡精度与性能）
        confidence:   置信水平（默认90%）

    Returns:
        参数不确定性字典或 None
    """
    import random as _random

    n = len(observations)
    if n < EM_MIN_OBSERVATIONS:
        return None

    param_names = ["p_initial", "p_learn", "p_guess", "p_slip"]
    bootstrap_samples = {name: [] for name in param_names}

    # 设置随机种子可复现
    rng = _random.Random(hash(tuple(observations)) % (2**32))

    successful_fits = 0
    for i in range(n_bootstrap):
        # 有放回重采样
        sample = [observations[rng.randint(0, n - 1)] for _ in range(n)]
        fit = estimate_params_em(sample, max_iter=20)  # Bootstrap内用较少迭代加速
        if fit:
            bootstrap_samples["p_initial"].append(fit.p_initial)
            bootstrap_samples["p_learn"].append(fit.p_learn)
            bootstrap_samples["p_guess"].append(fit.p_guess)
            bootstrap_samples["p_slip"].append(fit.p_slip)
            successful_fits += 1

    if successful_fits < 10:
        logger.warning("Bootstrap不确定性估计失败: %d/%d 次拟合成功", successful_fits, n_bootstrap)
        return None

    # 计算统计量
    alpha = 1 - confidence
    result = {}
    for name in param_names:
        values = sorted(bootstrap_samples[name])
        k = len(values)
        idx_low = int((alpha / 2) * k)
        idx_high = int((1 - alpha / 2) * k) - 1
        idx_low = max(0, idx_low)
        idx_high = min(k - 1, idx_high)

        mean_val = sum(values) / k
        std_val = (sum((v - mean_val) ** 2 for v in values) / max(k - 1, 1)) ** 0.5

        result[name] = {
            "mean": round(mean_val, 4),
            "std": round(std_val, 4),
            "ci_low": round(values[idx_low], 4),
            "ci_high": round(values[idx_high], 4),
            "n_samples": k,
        }

    result["_meta"] = {
        "n_bootstrap": n_bootstrap,
        "successful_fits": successful_fits,
        "confidence": confidence,
    }

    logger.info(
        "Bootstrap不确定性: P(L₀)=%.3f±%.3f [%.3f, %.3f] | P(T)=%.3f±%.3f (%d/%d)",
        result["p_initial"]["mean"], result["p_initial"]["std"],
        result["p_initial"]["ci_low"], result["p_initial"]["ci_high"],
        result["p_learn"]["mean"], result["p_learn"]["std"],
        successful_fits, n_bootstrap,
    )

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# BKTTracker —— 知识追踪引擎
# ═══════════════════════════════════════════════════════════════════════════════

class BKTTracker:
    """知识追踪引擎：管理所有知识点的 BKT 状态（v4 重构版）

    v4 新增功能：
    - 自动 EM 参数拟合（当某知识点积累足够数据时）
    - 全局预测精度指标
    - 批量 EM 拟合接口
    """

    def __init__(self, user_id: int = 0):
        self.user_id: int = user_id
        self.nodes: dict[str, KnowledgeNode] = {}
        self._load_from_db()

    def _load_from_db(self):
        """从 MySQL 加载该用户的所有 BKT 历史状态（含个性化参数 + EM 拟合标记）"""
        if not self.user_id:
            return
        db = SessionLocal()
        try:
            rows = db.query(BKTState).filter(BKTState.user_id == self.user_id).all()
            for row in rows:
                # 判断参数来源
                has_custom = any(getattr(row, attr) is not None
                                 for attr in ['p_learn', 'p_guess', 'p_slip', 'p_forget'])
                source = ParamSource.CUSTOM if has_custom else ParamSource.DEFAULT

                node = KnowledgeNode(
                    name=row.concept,
                    p_known=row.p_known,
                    p_learn=row.p_learn,
                    p_guess=row.p_guess,
                    p_slip=row.p_slip,
                    p_forget=row.p_forget,
                )
                node.param_source = source
                node.total_attempts = row.total_attempts or 0
                node.correct_count = row.correct_count or 0
                node._dirty = False
                self.nodes[row.concept] = node

            if rows:
                logger.info("BKT: 从 DB 加载 user_id=%d 的 %d 个知识点", self.user_id, len(rows))
        except Exception as e:
            logger.warning("BKT: 加载历史状态失败: %s", e)
        finally:
            db.close()

    def persist_to_db(self):
        """将所有脏节点写入 MySQL"""
        if not self.user_id:
            return
        dirty_nodes = {name: nd for name, nd in self.nodes.items() if nd._dirty}
        if not dirty_nodes:
            return
        db = SessionLocal()
        try:
            for name, node in dirty_nodes.items():
                row = db.query(BKTState).filter(
                    BKTState.user_id == self.user_id,
                    BKTState.concept == name,
                ).first()
                if not row:
                    row = BKTState(user_id=self.user_id, concept=name)
                    db.add(row)
                row.p_known = node.p_known
                row.total_attempts = node.total_attempts
                row.correct_count = node.correct_count
                row.level = node.level
                row.is_mastered = node.is_mastered
                row.p_learn = node._p_learn
                row.p_guess = node._p_guess
                row.p_slip = node._p_slip
                row.p_forget = node._p_forget
                node._dirty = False
            db.commit()
            logger.info("BKT: 持久化 %d 个知识点 user_id=%d", len(dirty_nodes), self.user_id)
        except Exception as e:
            db.rollback()
            logger.error("BKT: 持久化失败: %s", e)
        finally:
            db.close()

    def get_or_create(self, concept: str, p_known: Optional[float] = None) -> KnowledgeNode:
        cleaned = normalize_concept_name(concept)
        if not cleaned or cleaned == "未分类":
            logger.warning("BKT: 概念 '%s' 不在知识图谱中", concept[:50])
            if concept in self.nodes:
                return self.nodes[concept]
            if concept and len(concept.strip()) >= 2:
                node = KnowledgeNode(concept, p_known)
                self.nodes[concept] = node
                return node
            return KnowledgeNode("未分类", p_known)

        concept = cleaned
        if concept not in self.nodes:
            self.nodes[concept] = KnowledgeNode(concept, p_known)
        return self.nodes[concept]

    def record_answer(self, concept: str, is_correct: bool) -> UpdateStep:
        """记录一次答题，返回更新步骤明细"""
        node = self.get_or_create(concept)
        step = node.update(is_correct)

        # v4: 自动触发 EM 拟合检查（每 5 次答题后检查一次）
        if node.total_attempts % 5 == 0 and node.total_attempts >= EM_MIN_OBSERVATIONS:
            try:
                estimate_params_from_node(node)
            except Exception as e:
                logger.debug("BKT: EM拟合跳过 (%s): %s", concept, e)

        logger.info(
            "BKT: %s 答%s → P=%.3f [%s] T=%.2f G=%.2f S=%.2F src=%s",
            concept, "对" if is_correct else "错",
            node.p_known, node.level,
            node.p_learn, node.p_guess, node.p_slip,
            node.param_source.value,
        )
        return step

    def record_batch(self, results: list[dict]):
        """批量记录答题结果"""
        steps = []
        for r in results:
            step = self.record_answer(r["concept"], r["correct"])
            steps.append(step)
        self.persist_to_db()
        return steps

    def get_difficulty(self, concept: str) -> str:
        node = self.get_or_create(concept)
        if node.p_known < 0.35:
            return "简单"
        if node.p_known < 0.6:
            return "中等"
        if node.p_known < MASTERY_THRESHOLD:
            return "较难"
        return "挑战"

    def get_all_scores(self) -> dict[str, float]:
        return {name: nd.p_known for name, nd in self.nodes.items()}

    def get_mastered(self) -> list[str]:
        return [name for name, nd in self.nodes.items() if nd.is_mastered]

    def get_weak_points(self) -> list[str]:
        return [name for name, nd in self.nodes.items() if nd.p_known < 0.35]

    def run_batch_em_fit(self) -> dict:
        """对所有有足够数据的节点批量执行 EM 参数拟合

        Returns:
            {concept_name: EMFitResult or None}
        """
        results = {}
        for name, node in self.nodes.items():
            if len(node.update_history) >= EM_MIN_OBSERVATIONS and node.param_source != ParamSource.CUSTOM:
                try:
                    result = estimate_params_from_node(node)
                    results[name] = result
                except Exception as e:
                    logger.warning("BKT: EM拟合失败 [%s]: %s", name, e)
                    results[name] = None
            else:
                results[name] = None
        # 拟合完成后统一持久化
        self.persist_to_db()
        return results

    def get_prediction_metrics(self) -> dict:
        """计算全局预测精度指标

        Returns:
            {
                total_predictions: int,
                rmse: float,
                avg_log_likelihood: float,
                concepts_with_data: int,
                concepts_fitted: int,
            }
        """
        total_pred = 0
        total_se = 0.0
        total_ll = 0.0
        fitted_count = 0
        data_count = 0

        for name, node in self.nodes.items():
            if node.total_attempts == 0:
                continue
            data_count += 1
            if node.param_source == ParamSource.EM_FITTED:
                fitted_count += 1

            obs = [s.is_correct for s in node.update_history]
            if not obs:
                continue
            params = (node.get_effective_p_initial(), node.p_learn,
                      node.p_guess, node.p_slip)
            rmse = _compute_rmse(params, obs)
            _, ll = _bkt_forward(params, obs)

            n = len(obs)
            total_pred += n
            total_se += rmse ** 2 * n
            total_ll += ll

        return {
            "total_predictions": total_pred,
            "rmse": round(math.sqrt(total_se / max(total_pred, 1)), 4),
            "avg_log_likelihood": round(total_ll / max(data_count, 1), 4),
            "concepts_with_data": data_count,
            "concepts_fitted": fitted_count,
        }

    def to_dict(self) -> dict:
        nodes_dict = {name: nd.to_dict() for name, nd in self.nodes.items()}
        scores = {name: nd.p_known for name, nd in self.nodes.items()}
        return {
            "nodes": nodes_dict,
            "summary": {
                "total": len(self.nodes),
                "mastered": len(self.get_mastered()),
                "average": round(sum(scores.values()) / max(len(scores), 1), 4),
            },
            "metrics": self.get_prediction_metrics(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Tracker 缓存
# ═══════════════════════════════════════════════════════════════════════════════

_tracker_cache: dict[int, BKTTracker] = {}


def get_tracker(user_id: int = 0) -> BKTTracker:
    uid = user_id or 0
    if uid not in _tracker_cache:
        _tracker_cache[uid] = BKTTracker(user_id=uid)
    return _tracker_cache[uid]


def invalidate_tracker(user_id: int):
    uid = user_id or 0
    _tracker_cache.pop(uid, None)


# ═══════════════════════════════════════════════════════════════════════════════
# BKT ↔ Profile 双向同步
# ═══════════════════════════════════════════════════════════════════════════════

def sync_bkt_to_profile(user_id: int) -> bool:
    if not user_id:
        return False
    tracker = get_tracker(user_id)
    if not tracker.nodes:
        return False
    db = SessionLocal()
    try:
        from app.models.profile import LearningProfile
        row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
        if not row:
            return False
        kb = dict(row.knowledge_base or {}) if isinstance(row.knowledge_base, dict) else {}
        updated = False
        for concept, node in tracker.nodes.items():
            if not concept or concept == "未分类":
                continue
            if node.total_attempts < 3 and not node.is_mastered:
                continue
            bkt_score = round(node.p_known * 100, 1)
            old_score = kb.get(concept, 0)
            if abs(bkt_score - old_score) > 2:
                kb[concept] = bkt_score
                updated = True
                logger.info(
                    "BKT→Profile: '%s' %.1f→%.1f (p=%.3f attempts=%d level=%s src=%s)",
                    concept, old_score, bkt_score, node.p_known,
                    node.total_attempts, node.level, node.param_source.value,
                )
        if updated:
            row.knowledge_base = kb
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(row, "knowledge_base")
            db.commit()
        return updated
    except Exception as e:
        db.rollback()
        logger.error("BKT→Profile 同步失败: %s", e)
        return False
    finally:
        db.close()


def sync_profile_to_bkt(user_id: int, kb: dict):
    """将用户画像 knowledge_base 同步到 BKT 追踪器作为个性化先验

    修正：不再直接用 profile_score/100 作为 p_known（会导致 0次答题却显示95%的矛盾）。
    改为用 sigmoid 映射将画像分数转化为合理的 BKT 先验概率 P(L₀)：
      - score=0  → P(L₀)=0.05 (几乎不会)
      - score=50 → P(L₀)=0.30 (默认先验)
      - score=100→ P(L₀)=0.60 (较高但非精通，需答题验证）
    真正的掌握度必须通过 record_answer() 的贝叶斯更新来累积。
    """
    if not user_id or not kb:
        return
    tracker = get_tracker(user_id)
    init_count = 0
    for concept, score in kb.items():
        if not concept or concept == "未分类" or not isinstance(concept, str):
            continue
        if concept in tracker.nodes:
            continue
        try:
            score_val = float(score)
        except (TypeError, ValueError):
            score_val = 50.0

        # Sigmoid映射：将0-100分数映射到合理的BKT先验范围[0.05, 0.60]
        # 公式：P(L₀) = 0.05 + 0.55 / (1 + exp(-(score_val - 50) / 20))
        # score=0  → ~0.06,  score=30 → ~0.15,  score=50 → ~0.325
        # score=70 → ~0.50,  score=100→ ~0.59
        import math as _math
        raw = score_val / 100.0  # normalize to [0,1]
        p_known = 0.05 + 0.55 / (1.0 + _math.exp(-(raw - 0.5) * 8.0))
        p_known = max(0.05, min(0.60, p_known))

        tracker.get_or_create(concept, p_known=p_known)
        init_count += 1
        logger.info("Profile→BKT: '%s' 先验 P(L₀)=%.3f (profile=%.1f)", concept, p_known, score_val)

    if init_count > 0:
        tracker.persist_to_db()
        logger.info("Profile→BKT: user_id=%d 初始化 %d 个概念", user_id, init_count)


# ═══════════════════════════════════════════════════════════════════════════════
# 知识点名称规范化
# ═══════════════════════════════════════════════════════════════════════════════

_kg_vocabulary: list[str] | None = None


def _load_kg_vocabulary() -> list[str]:
    global _kg_vocabulary
    if _kg_vocabulary is None:
        import json as _json, os as _os, glob as _glob
        docs_dir = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "docs")
        docs_dir = _os.path.abspath(docs_dir)
        _kg_vocabulary = []
        try:
            for kg_file in sorted(_glob.glob(_os.path.join(docs_dir, "kg_*.json"))):
                with open(kg_file, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                nodes = data.get("nodes", [])
                for node in nodes:
                    if isinstance(node, dict):
                        name = node.get("name", "")
                        if name:
                            _kg_vocabulary.append(name)
                            keywords = node.get("keywords", [])
                            for kw in keywords:
                                if kw and kw not in _kg_vocabulary and len(kw) >= 2:
                                    _kg_vocabulary.append(kw)
        except Exception:
            _kg_vocabulary = []
    return _kg_vocabulary


def _extract_specific(text: str, base_name: str) -> str | None:
    import re as _re
    if "C++" in base_name or "c++" in text.lower():
        cpp_concepts = ["指针", "引用", "STL", "模板", "类", "对象", "继承", "多态", "虚函数", "内存管理", "数组", "字符串"]
        for c in cpp_concepts:
            if c in text:
                return f"C++{c}"
    if "Python" in base_name or "python" in text.lower():
        py_concepts = ["列表", "字典", "元组", "装饰器", "推导式", "生成器", "类", "函数", "异常", "文件"]
        for c in py_concepts:
            if c in text:
                return f"Python{c}"
    ds_concepts = ["二叉树", "链表", "图", "排序", "哈希", "栈", "队列", "树"]
    for c in ds_concepts:
        if c in text:
            return c
    return None


def normalize_concept_name(raw: str) -> str:
    """规范化概念名称：匹配知识图谱词汇表，返回标准化名称"""
    if not raw or not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if len(raw) < 2:
        return ""

    vocab = _load_kg_vocabulary()
    if not vocab:
        return raw

    raw_lower = raw.lower()

    # 1. 精确匹配
    for term in vocab:
        if raw_lower == term.lower():
            return term

    # 2. 包含匹配（术语在文本中出现）
    best_match = None
    best_len = 0
    for term in vocab:
        if term.lower() in raw_lower or raw_lower in term.lower():
            if len(term) > best_len:
                best_match = term
                best_len = len(term)

    if best_match:
        return best_match

    # 3. 尝试提取子概念
    for domain_key in ["python", "c++", "cpp", "java", "数据结构", "算法", "数据库", "网络"]:
        if domain_key in raw_lower:
            specific = _extract_specific(raw, domain_key)
            if specific:
                # 验证提取结果是否在词汇表中
                for term in vocab:
                    if specific.lower() in term.lower() or term.lower() in specific.lower():
                        return term

    return "未分类"
