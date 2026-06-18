"""
评估报告 Schema

作用：
  定义评估报告 API 的请求/响应数据格式
  提供 Pydantic 数据校验

关联文件：
  api/assessment.py       ← 使用本 Schema 做参数校验和响应格式化
  models/assessment.py    ← 对应的 ORM 模型字段
"""
from pydantic import BaseModel
from datetime import datetime


class AssessmentResponse(BaseModel):
    id: int
    user_id: int
    report_type: str
    report_data: dict | None = None
    dimension_scores: dict | None = None
    suggestions: list | None = None
    created_at: datetime
