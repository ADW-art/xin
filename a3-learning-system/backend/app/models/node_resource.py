"""
Path node ↔ Resource association table

Links resources generated during teaching to the current path node.
Enables the frontend node detail panel to show associated learning materials.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func
from app.core.database import Base


class NodeResource(Base):
    __tablename__ = "node_resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    node_name = Column(String(200), nullable=False, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
