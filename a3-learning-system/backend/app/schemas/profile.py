'''
pydantic模型,格式约定
'''
from pydantic import BaseModel, Field

#前端写入后端
class ProfileUpdate(BaseModel):
    knowledge_base: dict | None = None
    cognitive_style: str | None = None
    learning_goal: str | None = None
    weekly_hours: float | None = None
    error_patterns: list | None = None
    preferred_resource_type: str | None = None
    dimension_scores: dict | None = None

#后端提供给前端
class ProfileResponse(BaseModel):
    user_id: int
    knowledge_base: dict | None = None
    cognitive_style: str | None = None
    learning_goal: str | None = None
    weekly_hours: float | None = None
    error_patterns: list | None = None
    preferred_resource_type: str | None = None
    dimension_scores: dict | None = None
    suggestions: list | None = None  # Agent联动建议列表，Dashboard主动推送用
