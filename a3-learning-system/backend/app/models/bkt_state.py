"""
BKT 知识追踪持久化模型

存储每个用户每个知识点的贝叶斯知识追踪状态。
解决 BKTTracker 内存单例重启丢失的问题。

v3: 新增 per-skill 个性化参数存储，支持按知识点区分 P(T)/P(G)/P(S)/P(F)。
    全局默认值仅作为回退，数据库中有值则使用个性化参数。
"""
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class BKTState(Base):
    __tablename__ = "bkt_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    concept: Mapped[str] = mapped_column(String(128), nullable=False)  # 知识点名称

    # BKT 核心状态
    p_known: Mapped[float] = mapped_column(Float, default=0.3)  # 当前掌握概率 P(L)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)  # 总答题次数
    correct_count: Mapped[int] = mapped_column(Integer, default=0)  # 正确次数

    # ── v3: 个性化 BKT 参数（每个知识点独立，NULL 表示使用全局默认值）──
    # 这些参数可通过 EM 算法或经验调参为每个知识点独立拟合。
    # 参考: Yudelson, Koedinger & Gordon (2013) "Individualized Bayesian Knowledge Tracing Models"
    p_learn: Mapped[float | None] = mapped_column(Float, default=None)    # 学习率 P(T)——从未掌握到掌握的概率
    p_guess: Mapped[float | None] = mapped_column(Float, default=None)    # 猜测率 P(G)——未掌握但猜对的概率
    p_slip: Mapped[float | None] = mapped_column(Float, default=None)     # 失误率 P(S)——已掌握但答错的概率
    p_forget: Mapped[float | None] = mapped_column(Float, default=None)   # 遗忘率 P(F)——已掌握但在间隔后遗忘的概率（5参数BKT新增）

    # 元数据
    level: Mapped[str] = mapped_column(String(16), default="入门")  # 入门/学习中/熟悉/精通
    is_mastered: Mapped[bool] = mapped_column(default=False)  # p_known > 0.85
    updated_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    created_at: Mapped[DateTime] = mapped_column(DateTime, server_default=func.now())

    # 联合唯一约束：同一用户的同一知识点只有一条记录
    __table_args__ = (
        UniqueConstraint("user_id", "concept", name="uq_user_concept"),
        {"comment": "BKT贝叶斯知识追踪状态表——支持个性化4/5参数模型"},
    )
