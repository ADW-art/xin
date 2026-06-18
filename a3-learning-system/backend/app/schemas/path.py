"""
学习路径 Schema

作用：
  定义学习路径 API 的请求/响应数据格式
  提供 Pydantic 数据校验

关联文件：
  api/learning_path.py    ← 使用本 Schema 做响应格式化
  models/learning_path.py ← 对应的 ORM 模型字段
"""
from pydantic import BaseModel
from typing import Optional


class PathResponse(BaseModel):
    phases: list
    next_topics: list
    recommendations: list = []
    weak_points: list = []
    mastered_count: int
    total_nodes: int
    unlocked_count: int = 0
    stored_path_id: Optional[int] = None
    algorithm: str
