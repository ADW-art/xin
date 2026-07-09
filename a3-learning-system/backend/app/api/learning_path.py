"""
学习路径 API

作用：
  提供学习路径的查询接口
  用户可以查看当前的活跃学习路径

关联文件：
  models/learning_path.py     ← LearningPath ORM 模型
  schemas/path.py             ← PathResponse 响应格式
  main.py                     ← app.include_router(learning_path_router)
"""
import json
import os

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.learning_path import LearningPath
from app.models.profile import LearningProfile
from app.models.user import User
from app.api.auth import get_current_user
from app.schemas.path import PathResponse

router = APIRouter(prefix="/api/path", tags=["学习路径"])


# ═══════════════════════════════════════════════════════════════════════════════
# BKT mastery → 前端可视化映射（颜色 + 等级标签）
# ═══════════════════════════════════════════════════════════════════════════════
def _compute_node_visual(p_known: float) -> dict:
    """根据 BKT 掌握概率 p_known (0-1) 返回可视化属性

    阈值依据：
      0.85 = 教育测量学"精通"基准线（85% 及格线）
      0.60 = "熟悉"——可独立应用但可能出错
      0.35 = "学习中"——超过初始先验 P(L0)=0.3，已有实质进步

    Returns:
        {"level": str, "color": str, "size": int}
    """
    if p_known >= 0.85:
        return {"level": "mastered", "label_zh": "精通", "color": "#1D4ED8", "size": 28}
    if p_known >= 0.60:
        return {"level": "learning", "label_zh": "熟悉", "color": "#2563EB", "size": 26}
    if p_known >= 0.35:
        return {"level": "familiar", "label_zh": "学习中", "color": "#60A5FA", "size": 22}
    if p_known > 0.0:
        return {"level": "beginner", "label_zh": "入门", "color": "#93C5FD", "size": 18}
    return {"level": "unknown", "label_zh": "未学习", "color": "#94A3B8", "size": 16}


def _enrich_nodes_with_visual(nodes: list, kb: dict) -> list:
    """为图谱节点注入 BKT 可视化数据（level/color/p_known/group）

    Args:
        nodes: 知识图谱节点列表（从 JSON 文件加载）
        kb: BKT 掌握度字典 {concept_name -> p_known (0-1)}
    """
    for node in nodes:
        name = str(node.get("name", ""))
        # v4: 保留 KG 文件中的 id 字段，确保边引用能正确匹配
        node_id = node.get("id", "")
        if node_id and "id" not in node:
            pass  # id already present
        p_known = kb.get(name, 0.0)
        # 同时尝试用 id 匹配 BKT（如 "py:env" → normalize → "Python环境搭建"）
        if p_known == 0.0 and node_id:
            from app.services.bkt_service import normalize_concept_name as _norm
            normed = _norm(name)
            if normed and normed != "未分类":
                p_known = kb.get(normed, 0.0)
        visual = _compute_node_visual(p_known)
        node["p_known"] = round(p_known, 4)
        node["level"] = visual["level"]
        node["label_zh"] = visual["label_zh"]
        node["color"] = visual["color"]
        node["size"] = visual["size"]
    return nodes

# ═════════ 领域定义（基于录入的41本CS书籍 + 业内知识图谱标准）═════════
# 参考来源：美团知识图谱可视化实践 / D3.js力导向图 / KnowLP AAAI 2026
# 提取到模块级别，供 get_knowledge_graph 和 switch_domain_graph 共用
DOMAIN_CONFIG = {
    "cpp": {
        "name": "C/C++ 编程",
        "file": "kg_cpp.json",
        "keywords": ["c++", "c加加", "cpp", "c语言", "指针", "引用", "stl", "模板", "面向对象c++", "内存管理", "new/delete", "虚函数"],
        "books": ["C程序设计语言", "算法导论（C语言版）"],
    },
    "python": {
        "name": "Python 编程",
        "file": "kg_python.json",
        "keywords": ["python", "py", "列表推导式", "装饰器", "生成器", "django", "flask", "pandas", "numpy", "异步编程", "上下文管理器"],
        "books": ["Python Cookbook", "python核心编程", "Python编程从入门到实践"],
    },
    "java": {
        "name": "Java 编程",
        "file": "kg_java.json",
        "keywords": ["java", "spring", "jvm", "servlet", "maven", "接口实现", "注解", "stream api", "多线程", "垃圾回收"],
        "books": ["Java编程思想"],
    },
    "frontend": {
        "name": "前端开发",
        "file": "kg_frontend.json",
        "keywords": ["前端", "vue", "react", "html", "css", "javascript", "js", "typescript", "dom", "组件化", "响应式", "webpack", "vite", "nodejs", "es6"],
        "books": ["JavaScript面向对象", "你不知道的JavaScript", "MVC的JavaScript Web富应用开发"],
    },
    "algorithm": {
        "name": "算法与数据结构",
        "file": "kg_algorithm.json",
        "keywords": ["算法", "数据结构", "leetcode", "动态规划", "贪心", "二叉树", "图论", "排序", "查找", "复杂度", "递归", "回溯", "分治", "链表", "栈", "队列", "哈希", "堆"],
        "books": ["算法导论", "算法（第4版）", "数据结构与算法分析"],
    },
    "go": {
        "name": "Go 语言开发",
        "file": "kg_go.json",
        "keywords": ["go语言", "golang", "go ", "goroutine", "channel", "并发", "接口", "slice", "map结构体", "defer", "gin", "echo框架"],
        "books": ["Go程序设计语言", "Go语言实战", "Go学习笔记", "Go源码剖析"],
    },
    "system": {
        "name": "计算机系统基础",
        "file": "kg_system.json",
        "keywords": ["操作系统", "编译原理", "计算机组成", "进程", "线程", "内存管理os", "文件系统", "虚拟内存", "csapp", "sicp", "汇编", "指令集"],
        "books": ["深入理解计算机系统", "编译原理", "现代操作系统", "SICP"],
    },
    "network": {
        "name": "计算机网络",
        "file": "kg_network.json",
        "keywords": ["tcp/ip", "http协议", "网络编程", "socket", "udp", "dns", "https", "restful", "websocket", "osi模型", "三次握手", "四次挥手"],
        "books": ["TCP/IP详解", "HTTP权威指南", "UNIX网络编程"],
    },
    "database": {
        "name": "数据库技术",
        "file": "kg_database.json",
        "keywords": ["mysql", "redis", "mongodb", "sql", "nosql", "索引", "事务", "锁", "缓存", "主从复制", "分库分表", "orm"],
        "books": ["MySQL必知必会", "高性能MySQL", "Redis设计与实现", "MongoDB实战"],
    },
}


@router.get("/current", response_model=PathResponse)
def get_current_path(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """返回动态学习路径 — 基于知识图谱拓扑排序 + BKT 掌握度

    每次请求时实时计算：
      1. 加载治理后知识图谱
      2. 读取用户 BKT 掌握度 (knowledge_base ≥85 = mastered)
      3. 拓扑排序 → 动态学习阶段
      4. 返回推荐下一步学习节点
    """
    from app.services.knowledge_graph import KnowledgeGraph
    from app.models.profile import LearningProfile

    # ── 加载治理图谱 ──
    kg = KnowledgeGraph()
    governed_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs", "knowledge_graph_governed.json")
    governed_path = os.path.abspath(governed_path)
    if os.path.exists(governed_path):
        with open(governed_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        for n in d.get("nodes", []):
            name = n["name"]
            kg.nodes.add(name)
            kg.in_degree.setdefault(name, 0)
        for e in d.get("edges", []):
            src, tgt = e["source"], e["target"]
            if src in kg.nodes and tgt in kg.nodes:
                kg.edges[src].add(tgt)
                kg.in_degree[tgt] += 1

    # ── 数据源：优先 BKT 真实状态，fallback profile ──
    from app.services.dynamic_path_planner import build_planner_from_db

    planner = build_planner_from_db(current_user.id)

    # 兼容：如果 BKT 表为空，使用 profile.knowledge_base 兜底
    if not planner.kb:
        profile_fb = db.query(LearningProfile).filter(
            LearningProfile.user_id == current_user.id
        ).first()
        if profile_fb and profile_fb.knowledge_base:
            for k, v in profile_fb.knowledge_base.items():
                try:
                    fv = float(v)
                except (ValueError, TypeError):
                    fv = 0.0
                # profile 使用 0-100 范围，BKT 使用 0-1，统一归一化
                planner.kb[k] = fv / 100.0 if fv > 1.0 else fv

    # ── 动态规划路径 ──
    result = planner.plan(kg.nodes, kg.edges, kg.in_degree)

    # ── 检查是否有已存储的路径（兼容旧逻辑） ──
    stored = db.query(LearningPath).filter(
        LearningPath.user_id == current_user.id, LearningPath.status == "active"
    ).order_by(LearningPath.created_at.desc()).first()

    return {
        "phases": result["phases"],
        "next_topics": result["next_topics"],
        "recommendations": result.get("recommendations", []),
        "weak_points": result.get("weak_points", []),
        "mastered_count": result["mastered_count"],
        "total_nodes": result["total_nodes"],
        "unlocked_count": result.get("unlocked_count", 0),
        "stored_path_id": stored.id if stored else None,
        "algorithm": result["algorithm"],
    }


@router.get("/debug/simulate")
def debug_simulate(
    test_concept: str = "闭包",
    initial_score: float = 0.20,
    after_score: float = 0.95,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """🧪 调试接口：模拟某知识点掌握度从 initial 变 after，对比路径变化

    用法：
      GET /api/path/debug/simulate?test_concept=闭包&initial_score=0.20&after_score=0.95

    返回：
      模拟前后的 next_topics / phases 快照，用于肉眼验证是否真的动态
    """
    from app.services.knowledge_graph import KnowledgeGraph
    from app.services.dynamic_path_planner import DynamicPathPlanner

    # 加载图谱
    kg = KnowledgeGraph()
    governed_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "docs", "knowledge_graph_governed.json"
    ))
    if os.path.exists(governed_path):
        with open(governed_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        for n in d.get("nodes", []):
            name = n["name"]
            kg.nodes.add(name)
            kg.in_degree.setdefault(name, 0)
        for e in d.get("edges", []):
            src, tgt = e["source"], e["target"]
            if src in kg.nodes and tgt in kg.nodes:
                kg.edges[src].add(tgt)
                kg.in_degree[tgt] += 1

    # 读取用户当前 BKT
    from app.models.bkt_state import BKTState
    bkt_rows = db.query(BKTState).filter(BKTState.user_id == current_user.id).all()
    kb_before = {row.concept: row.p_known for row in bkt_rows}
    # 加上其他图谱节点默认为 0
    for n in kg.nodes:
        kb_before.setdefault(n, 0.0)

    # 模拟"前"路径
    planner_before = DynamicPathPlanner(dict(kb_before))
    before = planner_before.plan(kg.nodes, kg.edges, kg.in_degree)

    # 模拟答对后：BKT 从 initial 升到 after
    kb_after = dict(kb_before)
    if test_concept in kb_after or test_concept in kg.nodes:
        kb_after[test_concept] = after_score
    # 同样补全图谱节点
    for n in kg.nodes:
        kb_after.setdefault(n, 0.0)

    planner_after = DynamicPathPlanner(kb_after)
    after = planner_after.plan(kg.nodes, kg.edges, kg.in_degree)

    # 对比
    next_topics_changed = before["next_topics"] != after["next_topics"]
    phases_changed = [p["topics"] for p in before["phases"]] != [p["topics"] for p in after["phases"]]
    mastered_changed = before["mastered_count"] != after["mastered_count"]

    return {
        "test_concept": test_concept,
        "scenario": f"{test_concept}: {initial_score} → {after_score}",
        "before": {
            "next_topics": before["next_topics"],
            "phases": before["phases"],
            "mastered_count": before["mastered_count"],
            "algorithm": before["algorithm"],
        },
        "after": {
            "next_topics": after["next_topics"],
            "phases": after["phases"],
            "mastered_count": after["mastered_count"],
            "algorithm": after["algorithm"],
        },
        "comparison": {
            "next_topics_changed": next_topics_changed,
            "phases_changed": phases_changed,
            "mastered_changed": mastered_changed,
            "is_dynamic": next_topics_changed or phases_changed or mastered_changed,
            "verdict": "✅ 真实动态" if (next_topics_changed or phases_changed) else "❌ 伪动态（路径未变化）",
        },
    }


@router.get("/graph")
def get_knowledge_graph(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """返回知识图谱结构数据

    核心设计（参考 Hierarchical KG-LLM ICAIDS 2026 / KnowLP AAAI 2026）：
      - 按学习领域动态加载对应知识图谱（C++/Python/Java/前端/算法/AI）
      - 不同领域有完全不同的知识点和先修依赖关系
      - 未选择学习方向时返回空图谱 + 引导提示
    """
    import re
    from app.models.bkt_state import BKTState
    from app.models.profile import LearningProfile
    from app.models.conversation import Conversation
    from app.services.bkt_service import normalize_concept_name as normalize

    # ═════════ 1. 检测用户学习领域（使用模块级 DOMAIN_CONFIG）═════════
    detected_domain = None

    # 优先级1: 从BKT追踪记录中检测（最可靠——用户实际学过的知识点）
    bkt_rows = db.query(BKTState).filter(BKTState.user_id == current_user.id).all()
    if bkt_rows:
        # 收集用户学过的所有概念名，统一小写匹配
        learned_concepts = []
        for row in bkt_rows:
            norm = normalize(row.concept)
            if norm and norm != "未分类":
                learned_concepts.append(norm.lower())
                # 也加入原始名
                learned_concepts.append(str(row.concept).lower())

        concept_text = " ".join(learned_concepts)
        for domain_id, config in DOMAIN_CONFIG.items():
            for kw in config["keywords"]:
                if kw.lower() in concept_text:
                    detected_domain = domain_id
                    break
            if detected_domain:
                break

    # 优先级2: 从画像学习目标中检测
    if not detected_domain:
        profile = db.query(LearningProfile).filter(LearningProfile.user_id == current_user.id).first()
        if profile and profile.learning_goal:
            goal_text = str(profile.learning_goal).lower()
            for domain_id, config in DOMAIN_CONFIG.items():
                for kw in config["keywords"]:
                    if kw.lower() in goal_text:
                        detected_domain = domain_id
                        break
                if detected_domain:
                    break

    # 优先级3: 从最近对话历史中检测
    if not detected_domain:
        conv_count = db.query(Conversation).filter(Conversation.user_id == current_user.id).count()
        if conv_count > 0:
            # 有对话但无法确定领域 → 使用默认的 algorithm 作为初始领域
            # （因为大多数编程学习者从算法/数据结构开始）
            detected_domain = "algorithm"

    # ═════════ 2. 无学习方向 → 展示默认算法图谱预览（参考美团：新用户也展示示例图谱）═════════
    if not detected_domain:
        # 设计决策：不返回空图谱，而是展示"算法与数据结构"作为默认预览
        # 理由：(1) 大多数CS学习者从算法开始 (2) 让用户立刻看到图谱效果 (3) 可切换其他领域
        detected_domain = "algorithm"
        _preview_mode = True
    else:
        _preview_mode = False

    # ═════════ 3. 加载对应领域的知识图谱 ════════
    config = DOMAIN_CONFIG[detected_domain]
    kg_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs")
    kg_path = os.path.abspath(os.path.join(kg_dir, config["file"]))

    if not os.path.exists(kg_path):
        return {
            "nodes": [],
            "edges": [],
            "status": "error",
            "message": f"知识图谱文件不存在: {config['file']}",
            "domain": detected_domain,
            "domain_name": config["name"],
        }

    with open(kg_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    # ═════════ 4. 注入用户 BKT 掌握度 + 可视化映射 ════════
    kb = {}
    for row in bkt_rows:
        norm_name = normalize(row.concept)
        if norm_name and norm_name != "未分类":
            kb[norm_name] = max(kb.get(norm_name, 0), row.p_known)

    raw_nodes = result.get("nodes", [])
    _enrich_nodes_with_visual(raw_nodes, kb)

    # 计算领域统计（供前端 Legend）
    node_levels = [n.get("level", "unknown") for n in raw_nodes]
    stats = {
        "mastered": node_levels.count("mastered"),
        "learning": node_levels.count("learning"),
        "familiar": node_levels.count("familiar"),
        "beginner": node_levels.count("beginner"),
        "unknown": node_levels.count("unknown"),
    }

    # ═════════ 5. 返回带领域信息的图谱 ════════
    result["status"] = "ready"
    result["domain"] = detected_domain
    result["domain_name"] = config["name"]
    result["description"] = config.get("description", "")
    result["preview_mode"] = _preview_mode
    result["stats"] = stats
    # 返回所有可用领域列表（供前端切换）
    result["available_domains"] = [
        {"id": k, "name": v["name"], "books": v.get("books", [])}
        for k, v in DOMAIN_CONFIG.items()
    ]
    # groups: 从领域名称 + 知识图谱 phase 分组推导
    phases_set = set()
    for n in raw_nodes:
        ph = n.get("phase", "")
        if ph:
            phases_set.add(ph)
    result["groups"] = sorted(phases_set)
    return result


@router.get("/graph/{domain_id}")
def switch_domain_graph(
    domain_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动切换知识图谱领域（前端领域选择器调用）

    支持的领域: cpp / python / java / frontend / algorithm / go / system / network / database
    """
    if domain_id not in DOMAIN_CONFIG:
        return {
            "nodes": [],
            "edges": [],
            "status": "error",
            "message": f"未知领域: {domain_id}，可用领域: {list(DOMAIN_CONFIG.keys())}",
            "domain": domain_id,
        }

    config = DOMAIN_CONFIG[domain_id]
    kg_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "docs")
    kg_path = os.path.abspath(os.path.join(kg_dir, config["file"]))

    if not os.path.exists(kg_path):
        return {"nodes": [], "edges": [], "status": "error", "message": f"图谱文件不存在: {config['file']}"}

    with open(kg_path, "r", encoding="utf-8") as f:
        result = json.load(f)

    # 注入用户 BKT 掌握度 + 可视化映射
    from app.models.bkt_state import BKTState
    from app.services.bkt_service import normalize_concept_name as normalize
    bkt_rows = db.query(BKTState).filter(BKTState.user_id == current_user.id).all()
    kb = {}
    for row in bkt_rows:
        norm_name = normalize(row.concept)
        if norm_name and norm_name != "未分类":
            kb[norm_name] = max(kb.get(norm_name, 0), row.p_known)

    raw_nodes = result.get("nodes", [])
    _enrich_nodes_with_visual(raw_nodes, kb)

    node_levels = [n.get("level", "unknown") for n in raw_nodes]
    stats = {
        "mastered": node_levels.count("mastered"),
        "learning": node_levels.count("learning"),
        "familiar": node_levels.count("familiar"),
        "beginner": node_levels.count("beginner"),
        "unknown": node_levels.count("unknown"),
    }

    result["status"] = "ready"
    result["domain"] = domain_id
    result["domain_name"] = config["name"]
    result["description"] = config.get("description", "")
    result["preview_mode"] = False
    result["stats"] = stats
    result["available_domains"] = [
        {"id": k, "name": v["name"], "books": v.get("books", [])}
        for k, v in DOMAIN_CONFIG.items()
    ]
    phases_set = set()
    for n in raw_nodes:
        ph = n.get("phase", "")
        if ph:
            phases_set.add(ph)
    result["groups"] = sorted(phases_set)
    return result


# ═══════════════════════════════════════════════════════════════
# v4: 自定义图谱 CRUD — 用户/Agent 可创建个人知识图谱
# ═══════════════════════════════════════════════════════════════

from pydantic import BaseModel, Field


class CustomGraphNode(BaseModel):
    name: str = Field(..., description="知识点名称")
    phase: str = Field(default="core", description="阶段: foundation/core/advanced/practice")
    notes: str = Field(default="", description="用户备注")
    color: str = Field(default="", description="节点颜色（可选，留空则按 phase/BKT 自动计算）")


class CustomGraphEdge(BaseModel):
    source: str
    target: str
    relation: str = Field(default="prerequisite")


class CustomGraphCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    domain: str = Field(default="custom")
    nodes: list[CustomGraphNode] = Field(default_factory=list)
    edges: list[CustomGraphEdge] = Field(default_factory=list)


class CustomGraphUpdate(BaseModel):
    title: str | None = None
    nodes: list[CustomGraphNode] | None = None
    edges: list[CustomGraphEdge] | None = None


@router.get("/custom")
def list_custom_graphs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的所有自定义图谱"""
    try:
        graphs = db.query(LearningPath).filter(
            LearningPath.user_id == current_user.id,
            LearningPath.status == "custom",
        ).order_by(LearningPath.created_at.desc()).all()

        result = []
        for g in graphs:
            try:
                raw = g.path_data
                # 兼容：path_data 可能是字符串（旧数据）或 dict
                if isinstance(raw, str):
                    try:
                        pd = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        pd = {}
                elif isinstance(raw, dict):
                    pd = raw
                else:
                    pd = {}
                result.append({
                    "id": g.id,
                    "title": pd.get("title", "未命名"),
                    "domain": pd.get("domain", "custom"),
                    "node_count": len(pd.get("nodes", [])),
                    "edge_count": len(pd.get("edges", [])),
                    "created_at": g.created_at.isoformat() if g.created_at else "",
                    "updated_at": g.updated_at.isoformat() if g.updated_at else "",
                })
            except Exception as e2:
                # 单条数据解析失败不影响其他条目
                import logging
                logging.warning(f"自定义图谱 id={g.id} 数据解析失败: {e2}")
                result.append({
                    "id": g.id,
                    "title": "数据异常",
                    "domain": "custom",
                    "node_count": 0,
                    "edge_count": 0,
                    "created_at": "",
                    "updated_at": "",
                })
        return result
    except Exception as e:
        import logging, traceback
        logging.error(f"list_custom_graphs 500错误: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"加载图谱列表失败: {str(e)}")


@router.post("/custom")
def create_custom_graph(
    body: CustomGraphCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建自定义图谱（用户或 Agent 调用）"""
    path_data = {
        "title": body.title,
        "domain": body.domain,
        "nodes": [n.model_dump() for n in body.nodes],
        "edges": [e.model_dump() for e in body.edges],
    }
    graph = LearningPath(
        user_id=current_user.id,
        path_data=path_data,
        status="custom",
    )
    db.add(graph)
    db.commit()
    db.refresh(graph)
    return {"id": graph.id, "title": body.title, "status": "created"}


@router.put("/custom/{graph_id}")
def update_custom_graph(
    graph_id: int,
    body: CustomGraphUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新自定义图谱的节点/边"""
    graph = db.query(LearningPath).filter(
        LearningPath.id == graph_id,
        LearningPath.user_id == current_user.id,
    ).first()
    if not graph:
        raise HTTPException(status_code=404, detail="图谱不存在")
    data = dict(graph.path_data or {})
    if body.title is not None:
        data["title"] = body.title
    if body.nodes is not None:
        data["nodes"] = [n.model_dump() for n in body.nodes]
    if body.edges is not None:
        data["edges"] = [e.model_dump() for e in body.edges]
    graph.path_data = data
    db.commit()
    return {"id": graph.id, "status": "updated"}


@router.delete("/custom/{graph_id}")
def delete_custom_graph(
    graph_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除自定义图谱"""
    graph = db.query(LearningPath).filter(
        LearningPath.id == graph_id,
        LearningPath.user_id == current_user.id,
    ).first()
    if not graph:
        raise HTTPException(status_code=404, detail="图谱不存在")
    db.delete(graph)
    db.commit()
    return {"status": "deleted"}


@router.get("/custom/{graph_id}")
def get_custom_graph(
    graph_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取单个自定义图谱（含 BKT 染色数据）"""
    import logging
    try:
        graph = db.query(LearningPath).filter(
            LearningPath.id == graph_id,
            LearningPath.user_id == current_user.id,
        ).first()
        if not graph:
            raise HTTPException(status_code=404, detail="图谱不存在")

        raw_data = graph.path_data
        # 兼容：path_data 可能是字符串（旧数据）或 dict
        if isinstance(raw_data, str):
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                logging.warning(f"图谱 id={graph_id} 的 path_data 不是有效JSON，使用空dict")
                data = {}
        elif isinstance(raw_data, dict):
            data = raw_data
        else:
            data = {}

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        # 注入 BKT 掌握度染色
        from app.models.bkt_state import BKTState
        bkt_rows = db.query(BKTState).filter(BKTState.user_id == current_user.id).all()
        kb = {}
        for row in bkt_rows:
            kb[row.concept] = max(kb.get(row.concept, 0), row.p_known)

        # Phase → 颜色映射（与前端系统图谱 BKT 色系一致）
        _phase_color = {
            "foundation": "#8B5CF6",   # 紫色 = 入门
            "core": "#2563EB",         # 蓝色 = 核心/学习中
            "advanced": "#F59E0B",     # 琥珀 = 进阶/熟悉
            "practice": "#10B981",     # 绿色 = 实战/精通
        }

        enriched_nodes = []
        for n in nodes:
            name = n.get("name", "")
            phase = n.get("phase", "core")
            p_known = kb.get(name, 0.0)

            # 染色优先级：用户指定color > BKT掌握度色 > phase阶段色 > 默认灰
            if n.get("color"):
                node_color = n["color"]
            elif p_known > 0:
                visual = _compute_node_visual(p_known)
                node_color = visual["color"]
            else:
                node_color = _phase_color.get(phase, "#94A3B8")

            visual = _compute_node_visual(p_known)
            enriched_nodes.append({
                **n,
                "p_known": round(p_known, 4),
                "level": visual["level"],
                "color": node_color,
                "size": visual["size"],
            })

        return {
            "id": graph.id,
            "title": data.get("title", ""),
            "domain": data.get("domain", "custom"),
            "nodes": enriched_nodes,
            "edges": edges,
            "status": "ready",
        }
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"get_custom_graph id={graph_id} 错误: {e}")
        import traceback
        logging.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"加载图谱失败: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# v4: 路径动态重规划 API
# ═══════════════════════════════════════════════════════════════

@router.post("/replan")
def replan_learning_path(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """动态重规划学习路径 — BKT状态变化后重新拓扑排序

    当学生通过答题/教学掌握了新知识点后，调用此接口重新计算剩余路径。
    返回更新后的 active_path，前端刷新 DAG 图。
    """
    user_id = current_user.id

    # 1. 查找活跃教学路径
    active_path_row = db.query(LearningPath).filter(
        LearningPath.user_id == user_id,
        LearningPath.status == "active",
    ).order_by(LearningPath.created_at.desc()).first()

    if not active_path_row or not active_path_row.path_data:
        return {"status": "no_active_path", "message": "无活跃学习路径"}

    path_data = active_path_row.path_data if isinstance(active_path_row.path_data, dict) \
        else json.loads(active_path_row.path_data) if isinstance(active_path_row.path_data, str) \
        else {}

    teaching_ctx = path_data.get("teaching_context", {})
    if teaching_ctx.get("mode") != "teaching":
        return {"status": "not_teaching", "message": "当前非教学模式"}

    # 2. 获取最新 BKT 掌握状态
    from app.services.bkt_service import get_tracker
    tracker = get_tracker(user_id)
    known = set(tracker.get_mastered())

    active_path = teaching_ctx.get("active_path", [])
    completed = teaching_ctx.get("completed_nodes", [])
    known.update(completed)

    # 3. 加载 KG 并重跑拓扑排序
    from app.services.knowledge_graph import get_graph
    kg = get_graph()
    if not kg.nodes:
        try:
            from app.agents.path_agent import _load_multidiscipline_kg
            _load_multidiscipline_kg(kg, topic=teaching_ctx.get("topic", ""))
        except Exception:
            pass

    if kg.nodes:
        new_phases = kg.topological_sort(known)
        new_path = []
        for phase in new_phases:
            new_path.extend(phase)
        remaining = [n for n in new_path if n not in completed]
    else:
        remaining = [n for n in active_path if n not in completed and n not in known]

    # 4. 更新路径
    updated_path = completed + remaining
    teaching_ctx["active_path"] = updated_path
    teaching_ctx["current_index"] = len(completed)
    path_data["teaching_context"] = teaching_ctx
    active_path_row.path_data = path_data
    db.commit()

    return {
        "status": "replanned",
        "active_path": updated_path,
        "completed_nodes": completed,
        "remaining_nodes": remaining,
        "current_index": len(completed),
        "total_nodes": len(updated_path),
    }


# ═══════════════════════════════════════════════════════════════
# P1-16: 路径节点关联资源查询 API
# ═══════════════════════════════════════════════════════════════

@router.get("/node-resources")
def get_node_resources(
    node_name: str = Query(..., description="路径节点名称（知识点名）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询某个路径节点关联的学习资源

    教学模式中，resource_agent 每次生成资源后自动关联到当前路径节点。
    前端节点详情面板调用此接口展示该节点下所有已生成的学习资料。
    """
    from app.models.node_resource import NodeResource
    from app.models.resource import Resource

    links = (
        db.query(NodeResource)
        .filter(
            NodeResource.user_id == current_user.id,
            NodeResource.node_name == node_name,
        )
        .all()
    )
    resource_ids = [l.resource_id for l in links]
    if not resource_ids:
        return []
    resources = (
        db.query(Resource)
        .filter(Resource.id.in_(resource_ids))
        .all()
    )
    return [
        {
            "id": r.id,
            "title": r.title,
            "resource_type": r.resource_type,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in resources
    ]
