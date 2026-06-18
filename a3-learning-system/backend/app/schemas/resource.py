"""
学习资源 Schema

作用：
  定义学习资源 API 的请求/响应数据格式
  列表响应不含详细内容，详情响应含 content 字段

关联文件：
  api/resources.py        ← 使用本 Schema 做响应格式化
  models/resource.py      ← 对应的 ORM 模型字段
"""
from pydantic import BaseModel, Field
from datetime import datetime


class ResourceListResponse(BaseModel):
    id: int
    resource_type: str
    title: str
    knowledge_points: dict | None = None
    difficulty_level: int | None = None
    generated_by: str | None = None
    created_at: datetime


class ResourceDetailResponse(ResourceListResponse):
    content: str | None = None
    feedback_score: int | None = None


class FeedbackRequest(BaseModel):
    score: int = Field(ge=1, le=5, description="评分 1-5")


class FeedbackResponse(BaseModel):
    id: int
    feedback_score: int
    message: str


class DeleteResponse(BaseModel):
    deleted: bool
