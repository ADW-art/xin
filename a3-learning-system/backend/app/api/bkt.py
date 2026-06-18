"""
BKT 知识追踪 API（v4 重构版）

提供完整的 BKT 知识追踪接口：
  POST /api/bkt/answer       — 提交单条答题结果 → 返回分步计算明细
  POST /api/bkt/answers      — 批量提交答题结果
  GET  /api/bkt/status       — 查看当前BKT状态概览（含参数来源/历史曲线/预测指标）
  POST /api/bkt/em-fit       — 手动触发批量EM参数拟合

v4 改进：
  - 答题接口返回完整 UpdateStep 明细（前端可展示分步贝叶斯计算）
  - status 接口返回 params.source（区分 default/em_fitted/custom）
  - status 接口返回 history_summary（时间序列学习曲线数据）
  - status 接口返回 metrics（全局 RMSE/对数似然等预测精度指标）
  - 新增 em-fit 端点支持手动触发批量参数拟合
"""

from typing import Optional
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.models.user import User
from app.models.answer_record import AnswerRecord
from app.services.bkt_service import (
    get_tracker,
    invalidate_tracker,
    estimate_params_em,
    EM_MIN_OBSERVATIONS,
    DEFAULT_PARAMS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bkt", tags=["BKT知识追踪"])

# v4: 共享 6 维学习画像维度定义 (BKT/Profile/Evaluation 统一使用)
LEARNING_DIMENSIONS = ("knowledge", "speed", "practice", "focus", "logic", "trend")
DIMENSION_DEFAULTS = {"knowledge": 50, "speed": 50, "practice": 50, "focus": 50, "logic": 50, "trend": 50}


# ══════════ 请求/响应 Schema ══════════

class SubmitAnswerRequest(BaseModel):
    """提交单条答题结果"""
    concept: str = Field(..., description="知识点名称，如'Python装饰器'", min_length=1, max_length=128)
    is_correct: bool = Field(..., description="是否答对")
    user_answer: Optional[str] = Field(None, description="用户的答案原文")
    time_spent: Optional[int] = Field(None, description="答题耗时（秒）")


class SubmitAnswersRequest(BaseModel):
    """批量提交答题结果"""
    answers: list[SubmitAnswerRequest] = Field(..., min_length=1, max_length=50)


class BKTStatusResponse(BaseModel):
    """BKT状态响应（v4 扩展版）"""
    total_concepts: int = 0
    mastered_count: int = 0
    learning_count: int = 0
    weak_count: int = 0
    average_mastery: float = 0.0
    concepts: list[dict] = []
    # v4 新增字段
    metrics: dict = {}
    model_info: dict = {}


class EMFitRequest(BaseModel):
    """手动触发EM拟合请求"""
    concepts: Optional[list[str]] = Field(None, description="指定要拟合的知识点列表，为空则拟合所有符合条件的")


class EMFitResponse(BaseModel):
    """EM拟合响应"""
    fitted: int = 0
    skipped: int = 0
    results: list[dict] = []


# ══════════ 内部辅助函数 ══════════

def _sync_bkt_to_profile(user_id: int, tracker):
    """将 BKT 追踪数据同步到用户画像的 knowledge_base 和 dimension_scores"""
    if not user_id:
        return
    all_scores = tracker.get_all_scores()
    if not all_scores:
        return
    from app.core.database import SessionLocal as _SL
    from app.models.profile import LearningProfile
    db = _SL()
    try:
        row = db.query(LearningProfile).filter(LearningProfile.user_id == user_id).first()
        if not row:
            row = LearningProfile(user_id=user_id)
            db.add(row)
        kb = {}
        for name, score in all_scores.items():
            kb[name] = round(score * 100, 1)
        if row.knowledge_base and isinstance(row.knowledge_base, dict):
            for k, v in row.knowledge_base.items():
                if k not in kb:
                    kb[k] = v
        row.knowledge_base = kb
        avg = sum(all_scores.values()) / max(len(all_scores), 1)
        mastered = sum(1 for v in all_scores.values() if v >= 0.85)
        total = len(all_scores)
        prev = row.dimension_scores or {}
        row.dimension_scores = {
            "knowledge": round(avg * 100, 1),
            "speed": prev.get("speed", DIMENSION_DEFAULTS["speed"]),
            "practice": round(mastered / max(total, 1) * 100, 1),
            "focus": prev.get("focus", DIMENSION_DEFAULTS["focus"]),
            "logic": prev.get("logic", DIMENSION_DEFAULTS["logic"]),
            "trend": round(mastered / max(total, 1) * 100, 1),
            "overall": round(avg * 100, 1),
        }
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("BKT→Profile 同步失败: %s", e)
    finally:
        db.close()


# ══════════ 端点实现 ══════════

@router.post("/answer")
def submit_answer(
    body: SubmitAnswerRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """提交单条答题结果 → 更新BKT掌握概率 + 返回分步计算明细（v4）

    v4 改进：返回值包含 UpdateStep 完整明细，
    前端可用此数据展示贝叶斯公式的每一步计算过程。
    """
    from app.services.bkt_service import normalize_concept_name as normalize
    norm_concept = normalize(body.concept)
    concept = norm_concept if norm_concept and norm_concept != "未分类" else body.concept

    tracker = get_tracker(current_user.id)
    step = tracker.record_answer(concept, body.is_correct)
    node = tracker.get_or_create(concept)
    logger.info("BKT API: step type=%s, step.p_final=%s, step.p_before=%s",
                type(step).__name__, getattr(step, 'p_final', 'N/A'), getattr(step, 'p_before', 'N/A'))

    # 持久化到 DB
    tracker.persist_to_db()

    # BKT→Profile 同步
    _sync_bkt_to_profile(current_user.id, tracker)

    # 失效缓存
    invalidate_tracker(current_user.id)

    # 记录到 answer_records
    from app.core.database import SessionLocal as _SL
    db = _SL()
    try:
        record = AnswerRecord(
            user_id=current_user.id,
            concept=concept,
            user_answer=body.user_answer,
            is_correct=body.is_correct,
            time_spent=body.time_spent,
        )
        db.add(record)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning("答题记录写入失败: %s", e)
    finally:
        db.close()

    # v4: 构建 update_step 明细
    update_step = {
        "step_no": step.step_no,
        "is_correct": step.is_correct,
        "p_before": step.p_before,
        "p_after_bayes": step.p_after_bayes,
        "p_after_learn": step.p_after_learn,
        "p_final": step.p_final,
        "bayes_numerator": step.bayes_numerator,
        "bayes_denominator": step.bayes_denominator,
        "learn_delta": step.learn_delta,
        "forget_delta": step.forget_delta,
        "formula_type": "correct" if step.is_correct else "wrong",
        "params_used": step.params_used,
    }
    logger.debug("BKT answer: update_step=%s", {k: v for k, v in update_step.items() if v is not None})

    return {
        "concept": body.concept,
        "concept_normalized": concept,
        "p_known": round(node.p_known, 4),
        "level": node.level,
        "is_mastered": node.is_mastered,
        "attempts": node.total_attempts,
        "correct_rate": round(node.correct_count / max(node.total_attempts, 1), 2),
        "update_step": update_step,
        "params": node.to_dict()["params"],
    }


@router.post("/answers")
def submit_answers(
    body: SubmitAnswersRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """批量提交多条答题结果（v4：返回每条的步骤明细）"""
    tracker = get_tracker(current_user.id)
    results = []

    from app.services.bkt_service import normalize_concept_name as normalize
    from app.core.database import SessionLocal as _SL
    db = _SL()
    try:
        for ans in body.answers:
            norm_concept = normalize(ans.concept)
            concept = norm_concept if norm_concept and norm_concept != "未分类" else ans.concept

            step = tracker.record_answer(concept, ans.is_correct)
            node = tracker.get_or_create(concept)

            record = AnswerRecord(
                user_id=current_user.id,
                concept=concept,
                user_answer=ans.user_answer,
                is_correct=ans.is_correct,
                time_spent=ans.time_spent,
            )
            db.add(record)

            results.append({
                "concept": ans.concept,
                "concept_normalized": concept,
                "p_known": round(node.p_known, 4),
                "level": node.level,
                "is_mastered": node.is_mastered,
                "params_source": node.param_source.value,
            })

        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("批量答题记录写入失败: %s", e)
        raise HTTPException(status_code=500, detail="批量写入失败")
    finally:
        db.close()

    tracker.persist_to_db()
    _sync_bkt_to_profile(current_user.id, tracker)
    invalidate_tracker(current_user.id)

    return {
        "updated": len(results),
        "results": results,
    }


@router.get("/status", response_model=BKTStatusResponse)
def get_bkt_status(
    current_user: User = Depends(get_current_user),
) -> BKTStatusResponse:
    """获取当前用户的BKT知识追踪状态概览（v4 扩展版）

    v4 返回增强内容：
    - concepts[].params: 含 source 字段（default/em_fitted/custom）
    - concepts[].history_summary: 最近50步的 P(known) 变化（用于绘制学习曲线）
    - metrics: 全局预测精度指标（RMSE、对数似然等）
    - model_info: 模型版本和默认参数说明
    """
    tracker = get_tracker(current_user.id)

    # ── 自动初始化：画像 → BKT ──
    if not tracker.nodes:
        try:
            from app.models.profile import LearningProfile
            from app.core.database import SessionLocal as _SL
            db = _SL()
            try:
                row = db.query(LearningProfile).filter(
                    LearningProfile.user_id == current_user.id
                ).first()
                if row and row.knowledge_base and isinstance(row.knowledge_base, dict):
                    from app.services.bkt_service import sync_profile_to_bkt
                    sync_profile_to_bkt(current_user.id, row.knowledge_base)
                    logger.info(
                        "BKT状态: user=%d 从画像初始化 %d 个概念",
                        current_user.id, len(row.knowledge_base),
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning("BKT自动初始化失败: %s", e)

    all_scores = tracker.get_all_scores()
    mastered = tracker.get_mastered()
    weak = tracker.get_weak_points()

    # v4: 构建概念详情（含参数来源和历史）
    concepts_detail = []
    for name, score in sorted(all_scores.items(), key=lambda x: -x[1]):
        node = tracker.get_or_create(name)
        node_dict = node.to_dict()
        concepts_detail.append({
            "name": name,
            "p_known": round(score, 4),
            "level": node.level,
            "is_mastered": node.is_mastered,
            "attempts": node.total_attempts,
            "correct_count": node.correct_count,
            "correct_rate": round(
                node.correct_count / max(node.total_attempts, 1), 2
            ),
            # v4: 参数信息（含来源）
            "params": node_dict["params"],
            # v4: 历史摘要（用于曲线）
            "history_summary": node_dict.get("history_summary", []),
        })

    # v4: 获取预测指标
    metrics = tracker.get_prediction_metrics()

    return BKTStatusResponse(
        total_concepts=len(all_scores),
        mastered_count=len(mastered),
        learning_count=len([n for n in all_scores if 0.35 <= all_scores[n] < 0.85]),
        weak_count=len(weak),
        average_mastery=round(sum(all_scores.values()) / max(len(all_scores), 1), 4),
        concepts=concepts_detail[:20],
        metrics=metrics,
        model_info={
            "version": "v4",
            "formula": "Corbett-Anderson-1995-Bayesian-Update",
            "default_params": {k: round(v, 3) for k, v in DEFAULT_PARAMS.items()},
            "em_threshold": EM_MIN_OBSERVATIONS,
            "mastery_threshold": 0.85,
            "note_v4_fix": "P(T)学习转移对正确/错误均施加（修正了v3仅答对时施加的问题）",
        },
    )


@router.post("/em-fit", response_model=EMFitResponse)
def run_em_fit(
    body: EMFitRequest = EMFitRequest(),
    current_user: User = Depends(get_current_user),
) -> EMFitResponse:
    """手动触发批量 EM 参数拟合（v4 新增）

    对所有积累足够答题数据（≥10条）的知识点执行 EM 参数估计。
    拟合完成后参数自动应用到对应节点并持久化。

    可选参数 concepts 指定只拟合特定知识点。
    """
    tracker = get_tracker(current_user.id)

    target_concepts = set(body.concepts) if body.concepts else None
    results = []
    fitted_count = 0
    skipped_count = 0

    for name, node in tracker.nodes.items():
        if target_concepts and name not in target_concepts:
            skipped_count += 1
            continue

        if node.param_source.value == "custom":
            results.append({
                "concept": name,
                "status": "skipped_custom",
                "reason": "已有自定义参数，跳过EM拟合",
            })
            skipped_count += 1
            continue

        if len(node.update_history) < EM_MIN_OBSERVATIONS:
            results.append({
                "concept": name,
                "status": "skipped_insufficient_data",
                "reason": f"答题记录不足（{len(node.update_history)}/{EM_MIN_OBSERVATIONS}）",
            })
            skipped_count += 1
            continue

        try:
            from app.services.bkt_service import estimate_params_from_node
            fit_result = estimate_params_from_node(node)
            if fit_result:
                fitted_count += 1
                results.append({
                    "concept": name,
                    "status": "fitted",
                    "params": {
                        "p_initial": fit_result.p_initial,
                        "p_learn": fit_result.p_learn,
                        "p_guess": fit_result.p_guess,
                        "p_slip": fit_result.p_slip,
                    },
                    "rmse": fit_result.rmse,
                    "iterations": fit_result.iterations,
                    "converged": fit_result.converged,
                    "n_obs": fit_result.n_observations,
                })
            else:
                skipped_count += 1
                results.append({
                    "concept": name,
                    "status": "skipped_fit_failed",
                    "reason": "EM拟合未能收敛",
                })
        except Exception as e:
            skipped_count += 1
            results.append({
                "concept": name,
                "status": "error",
                "reason": str(e)[:200],
            })

    # 统一持久化
    tracker.persist_to_db()
    invalidate_tracker(current_user.id)

    logger.info(
        "EM-FIT: user=%d 完成 fitted=%d skipped=%d total=%d",
        current_user.id, fitted_count, skipped_count, len(tracker.nodes),
    )

    return EMFitResponse(
        fitted=fitted_count,
        skipped=skipped_count,
        results=results,
    )
