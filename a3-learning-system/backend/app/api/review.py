"""
复习提醒 API

提供到期复习知识点的查询接口。
前端 Dashboard 卡片 + ChatView SSE 推送 + 浏览器 Notification 的源数据。
"""
import logging
from fastapi import APIRouter, Depends
from app.api.auth import get_current_user
from app.models.user import User
from app.services.review_scheduler import get_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/review", tags=["复习提醒"])


@router.get("/due")
def get_due_reviews(current_user: User = Depends(get_current_user)):
    """获取到期复习知识点列表

    返回按保留率升序排列的待复习节点（最紧急的在前）。
    前端 Dashboard 渲染待复习卡片，ChatView SSE 推送同名事件。
    """
    sched = get_scheduler(current_user.id)
    nodes = sched.get_review_nodes()
    return {
        "total": len(nodes),
        "high_risk": sum(1 for n in nodes if n["risk"] == "high"),
        "items": sorted(nodes, key=lambda n: n["retention"]),
    }


@router.get("/stats")
def get_review_stats(current_user: User = Depends(get_current_user)):
    """复习统计摘要

    返回到期数量 / 总知识点数 / 完成率，供 Dashboard 概览使用。
    """
    sched = get_scheduler(current_user.id)
    due = sched.get_due_reviews()
    all_count = len(sched.schedules)
    return {
        "due_count": len(due),
        "total_concepts": all_count,
        "completion_rate": (
            round((all_count - len(due)) / max(all_count, 1) * 100, 1)
            if all_count > 0
            else 0.0
        ),
    }
