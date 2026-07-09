"""
艾宾浩斯遗忘曲线复习调度器

自研算法模块。
基于艾宾浩斯遗忘曲线 Ebbinghaus Forgetting Curve，
计算每个知识点的遗忘风险并在临界点触发复习。

艾宾浩斯公式：
  R = e^(-t / S)
  - R: 记忆保留率
  - t: 距离上次学习的时间
  - S: 记忆强度（取决于复习次数和间隔）

间隔递增复习法（Spaced Repetition）:
  间隔序列：[1天, 3天, 7天, 14天, 30天, 90天]
  每次复习后将间隔推进到下一级

遗忘风险阈值：
  R < 0.5 → 高风险（即将遗忘）→ 立即复习
  R < 0.7 → 中风险 → 建议复习
  R >= 0.7 → 安全

v2 改进：从纯内存单例 → MySQL 持久化，服务重启不丢进度。
每个用户独立追踪，支持多用户并发。
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.core.database import SessionLocal
from app.models.review_schedule import ReviewScheduleModel

logger = logging.getLogger(__name__)

# 间隔递增序列（天）
INTERVALS = [1, 3, 7, 14, 30, 90]


class ReviewSchedule:
    """单个知识点的复习进度"""

    def __init__(self, concept: str):
        self.concept = concept
        self.last_reviewed: Optional[datetime] = None
        self.interval_index: int = 0       # 当前间隔索引
        self.review_count: int = 0          # 总复习次数
        self.memory_strength: float = 4.0   # 记忆强度 S（初始 4.0 → 1天后约78%保留率）
        self._dirty: bool = False           # 标记是否有未持久化的变更

    @property
    def current_interval_days(self) -> int:
        return INTERVALS[min(self.interval_index, len(INTERVALS) - 1)]

    @property
    def next_review_at(self) -> Optional[datetime]:
        if self.last_reviewed is None:
            return None
        return self.last_reviewed + timedelta(days=self.current_interval_days)

    @property
    def retention_rate(self) -> float:
        """当前记忆保留率 R = e^(-t/S)"""
        if self.last_reviewed is None:
            return 0.0
        t = (datetime.now() - self.last_reviewed).total_seconds() / 86400  # 天数
        import math
        return math.exp(-t / max(self.memory_strength, 0.01))

    @property
    def risk_level(self) -> str:
        """遗忘风险等级"""
        r = self.retention_rate
        if r < 0.5:
            return "high"
        if r < 0.7:
            return "medium"
        return "low"

    def review(self):
        """记录一次复习"""
        self.last_reviewed = datetime.now()
        self.interval_index = min(self.interval_index + 1, len(INTERVALS) - 1)
        self.review_count += 1
        self.memory_strength += 1.5   # 每次复习显著增强记忆强度
        self.memory_strength = min(self.memory_strength, 20.0)
        self._dirty = True

    def to_dict(self) -> dict:
        return {
            "concept": self.concept,
            "retention": round(self.retention_rate, 3),
            "risk": self.risk_level,
            "next_review": self.next_review_at.isoformat() if self.next_review_at else None,
            "review_count": self.review_count,
            "interval_days": self.current_interval_days,
        }


class ReviewScheduler:
    """复习调度引擎（支持 MySQL 持久化）"""

    def __init__(self, user_id: int = 0):
        self.user_id = user_id
        self.schedules: dict[str, ReviewSchedule] = {}
        # 启动时从 DB 加载历史状态
        self._load_from_db()

    def _load_from_db(self):
        """从 MySQL 加载该用户的所有复习进度"""
        if not self.user_id:
            return
        db = SessionLocal()
        try:
            rows = db.query(ReviewScheduleModel).filter(
                ReviewScheduleModel.user_id == self.user_id
            ).all()
            for row in rows:
                s = ReviewSchedule(row.concept)
                s.last_reviewed = row.last_reviewed
                s.interval_index = row.interval_index or 0
                s.review_count = row.review_count or 0
                s.memory_strength = row.memory_strength or 4.0
                s._dirty = False  # 从 DB 加载的，不需要回写
                self.schedules[row.concept] = s
            if rows:
                logger.info(
                    "ReviewScheduler: 从DB加载 user_id=%d 的 %d 个知识点复习进度",
                    self.user_id, len(rows),
                )
        except Exception as e:
            logger.warning("ReviewScheduler: 加载历史状态失败，将使用空状态: %s", e)
        finally:
            db.close()

    def persist_to_db(self):
        """将所有脏节点写入 MySQL"""
        if not self.user_id:
            return
        dirty = {c: s for c, s in self.schedules.items() if s._dirty}
        if not dirty:
            return
        db = SessionLocal()
        try:
            for concept, sched in dirty.items():
                row = db.query(ReviewScheduleModel).filter(
                    ReviewScheduleModel.user_id == self.user_id,
                    ReviewScheduleModel.concept == concept,
                ).first()
                if not row:
                    row = ReviewScheduleModel(
                        user_id=self.user_id,
                        concept=concept,
                    )
                    db.add(row)
                row.last_reviewed = sched.last_reviewed
                row.interval_index = sched.interval_index
                row.review_count = sched.review_count
                row.memory_strength = sched.memory_strength
                sched._dirty = False  # 清除脏标记
            db.commit()
            logger.info(
                "ReviewScheduler: 持久化 %d 个知识点到DB user_id=%d",
                len(dirty), self.user_id,
            )
        except Exception as e:
            db.rollback()
            logger.error("ReviewScheduler: 持久化失败: %s", e)
        finally:
            db.close()

    def get_or_create(self, concept: str) -> ReviewSchedule:
        if concept not in self.schedules:
            self.schedules[concept] = ReviewSchedule(concept)
        return self.schedules[concept]

    def record_review(self, concept: str):
        """记录一次复习（概念名自动规范化）"""
        try:
            from app.services.bkt_service import normalize_concept_name
            normalized = normalize_concept_name(concept)
            if normalized and normalized != "未分类":
                concept = normalized
        except Exception:
            pass
        s = self.get_or_create(concept)
        s.review()
        self.persist_to_db()
        logger.info(
            "Scheduler: %s 已复习, 下次复习=%s, 记忆强度=%.2f",
            concept, s.next_review_at, s.memory_strength,
        )

    def record_answer(self, concept: str, is_correct: bool):
        """记录答题：答对 = 有效复习"""
        if is_correct:
            self.record_review(concept)

    def get_due_reviews(self) -> list[str]:
        """所有应该复习的知识点（遗忘风险 > 低）"""
        return [c for c, s in self.schedules.items() if s.risk_level != "low"]

    def get_review_nodes(self) -> list[dict]:
        """获取应该插入学习路径的复习节点"""
        due = self.get_due_reviews()
        return [self.schedules[c].to_dict() for c in due]

    def to_dict(self) -> dict:
        return {c: s.to_dict() for c, s in self.schedules.items()}


# 按 user_id 缓存 scheduler 实例（替代原来的全局单例）
_scheduler_cache: dict[int, ReviewScheduler] = {}
MAX_SCHEDULER_CACHE = 100


def get_scheduler(user_id: int = 0) -> ReviewScheduler:
    """获取指定用户的复习调度器（带缓存和持久化）"""
    uid = user_id or 0
    if uid not in _scheduler_cache:
        if len(_scheduler_cache) >= MAX_SCHEDULER_CACHE:
            _scheduler_cache.pop(next(iter(_scheduler_cache)))
        _scheduler_cache[uid] = ReviewScheduler(user_id=uid)
    return _scheduler_cache[uid]
