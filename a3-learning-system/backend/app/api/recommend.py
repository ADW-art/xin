"""Push Recommendations API - based on BKT state for active push"""
import logging
from fastapi import APIRouter, Header
from app.services.bkt_service import get_tracker
from app.core.database import SessionLocal
from app.models.resource import Resource
from app.services.knowledge_graph import get_graph
from app.core.security import decode_access_token
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/push", tags=["push"])

@router.get("/recommendations")
async def get_recommendations(authorization: str = Header(None)):
    user_id = 0
    if authorization and authorization.startswith("Bearer "):
        payload = decode_access_token(authorization[7:])
        if payload: user_id = int(payload.get("sub", 0))
    try:
        tracker = get_tracker(user_id)
        weak = tracker.get_weak_points()[:5]
        mastered = tracker.get_mastered()
        all_scores = tracker.get_all_scores()
        kg = get_graph()
        next_topics = []
        if kg and kg.nodes:
            known = set(mastered)
            next_topics = [n for n in kg.topological_sort(known)[:5] if n not in known]
        rlist = []
        db = SessionLocal()
        try:
            for t in (weak[:3] + next_topics[:3]):
                for r in db.query(Resource).filter(Resource.title.ilike(f"%{t}%")).limit(2).all():
                    rlist.append({"id":r.id,"title":r.title,"rtype":r.resource_type,"topic":t})
        finally:
            db.close()
        return {"weak":weak,"next":next_topics,"resources":rlist[:6],"mastered":len(mastered),"total":len(all_scores)}
    except Exception as e:
        logger.error("recommend error:%s",e)
        return {"weak":[],"next":[],"resources":[],"mastered":0,"total":0}
