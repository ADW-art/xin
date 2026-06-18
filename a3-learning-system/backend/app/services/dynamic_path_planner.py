"""
动态学习路径规划器 v2

核心思路：
  1. BKT 状态作为唯一数据源（取代 profile.knowledge_base 手动值）
  2. 知识图谱 DAG 提供结构约束（前置依赖不能跳）
  3. 学习目标（topic）作为聚焦权重
  4. 薄弱程度作为优先级

排序优先级：
  ① 可学性（所有前置都掌握） > 不可学（前置未掌握，跳过）
  ② 在目标主题链上（与 topic 距离近） > 不在链上
  ③ 薄弱程度高（≤35%）> 中（35-60%）> 高（≥60%）
  ④ TF-IDF 权重

返回结构：
  {
    "phases": [...],         # 分阶段路径
    "next_topics": [...],    # 下一步推荐
    "algorithm": "dynamic_bkt_v2",
    "summary": {
      "unlocked": int,        # 本次解锁的新节点数
      "mastered": int,        # 已掌握节点数
      "weak_points": [...],   # 薄弱点
    }
  }
"""
import logging
import os
import json
from collections import defaultdict

logger = logging.getLogger(__name__)


class DynamicPathPlanner:
    """基于 BKT 状态 + 知识图谱 + 学习目标的动态路径规划器"""

    # 掌握阈值：BKT p_known > 0.85 视为已掌握
    MASTERED_THRESHOLD = 0.85

    def __init__(self, knowledge_base: dict[str, float], topic: str = ""):
        """
        Args:
            knowledge_base: 知识点 → 掌握度（0-1 或 0-100，混用兼容）
                            推荐使用 BKT 真实状态
            topic: 用户当前学习目标主题
        """
        self.kb = self._normalize_kb(knowledge_base)
        self.topic = topic.strip() if topic else ""

    def _normalize_kb(self, kb: dict) -> dict[str, float]:
        """统一知识库到 0-1 范围（兼容 0-100 和 0-1 输入）"""
        norm = {}
        for k, v in kb.items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            # 如果值 > 1，说明是 0-100 范围，转换为 0-1
            if fv > 1.0:
                fv = fv / 100.0
            norm[str(k)] = max(0.0, min(1.0, fv))
        return norm

    def plan(self, kg_nodes: set[str], kg_edges: dict[str, set[str]],
             kg_in_degree: dict[str, int]) -> dict:
        """生成动态学习路径

        Args:
            kg_nodes: 知识图谱所有节点
            kg_edges: 邻接表 {src: {tgt1, tgt2, ...}}
            kg_in_degree: 入度表 {node: in_degree}

        Returns:
            路径规划结果
        """
        # ① 同步 BKT → 知识图谱（缺失节点默认为 0）
        all_nodes = set(kg_nodes)
        for node in all_nodes:
            self.kb.setdefault(node, 0.0)

        # ② 已掌握集合
        mastered = {n for n, v in self.kb.items() if v >= self.MASTERED_THRESHOLD}

        # ③ 计算当前真实入度（掌握节点不再阻塞）
        real_in_degree = {}
        for node in all_nodes:
            real_in_degree[node] = 0
        for src, tgts in kg_edges.items():
            for tgt in tgts:
                if tgt in real_in_degree:
                    real_in_degree[tgt] += 1

        # 移除已掌握节点的入度贡献
        for src in mastered:
            for tgt in kg_edges.get(src, set()):
                if tgt in real_in_degree:
                    real_in_degree[tgt] = max(0, real_in_degree[tgt] - 1)

        # ④ 计算到目标主题的图谱距离（用于聚焦权重）
        target_distances = self._compute_target_distances(kg_nodes, kg_edges, self.topic) if self.topic else {}

        # ⑤ 计算每个节点的优先级
        node_priorities = self._compute_priorities(
            all_nodes, mastered, real_in_degree, target_distances
        )

        # ⑥ 分阶段：每波取所有可学节点，移除后重算
        phases = []
        remaining = set(all_nodes) - mastered
        current_in_degree = dict(real_in_degree)

        # 最多迭代节点数次（防止死循环）
        max_iterations = len(all_nodes) + 1
        iteration = 0
        prev_size = -1

        while remaining and iteration < max_iterations:
            iteration += 1

            # 当前可学节点：入度为 0 且未掌握
            learnable = [n for n in remaining if current_in_degree.get(n, 0) == 0]

            if not learnable:
                # 死锁：剩余节点都有未掌握的前置
                # 取入度最小的几个（异常兜底）
                min_deg = min(current_in_degree.get(n, 0) for n in remaining)
                learnable = [n for n in remaining if current_in_degree.get(n, 0) == min_deg]
                logger.warning("PathPlanner: 死锁兜底，取入度最小层=%d 共%d个", min_deg, len(learnable))

            # 按优先级排序
            learnable_sorted = sorted(learnable, key=lambda n: -node_priorities.get(n, 0))

            # 防止无限循环
            if len(learnable_sorted) == prev_size:
                break
            prev_size = len(learnable_sorted)

            phases.append(learnable_sorted)

            # 移除这些节点，更新入度
            for node in learnable_sorted:
                remaining.discard(node)
                for tgt in kg_edges.get(node, set()):
                    if tgt in current_in_degree:
                        current_in_degree[tgt] = max(0, current_in_degree[tgt] - 1)

        # ⑦ 下一步推荐：优先级最高的可学节点
        next_topics = phases[0][:8] if phases else []

        # ⑦.5 推荐理由：说明每个 next_topic 为什么被推荐
        recommendations = []
        for name in next_topics:
            mastery = self.kb.get(name, 0.0)
            priority = node_priorities.get(name, 0)

            reasons = []
            # Reason 1: 前置知识缺失 — this node is a prereq for other unmastered topics
            if mastery < self.MASTERED_THRESHOLD:
                downstream = kg_edges.get(name, set())
                unmastered_downstream = [
                    d for d in downstream if self.kb.get(d, 0) < self.MASTERED_THRESHOLD
                ]
                if unmastered_downstream:
                    reasons.append("前置知识缺失")

            # Reason 2: BKT 薄弱 — mastery too low
            if mastery <= 0.35:
                reasons.append("BKT掌握率低于35%")

            # Reason 3: 拓扑排序下一层 — all prereqs done, naturally unlocked
            if real_in_degree.get(name, 0) == 0:
                reasons.append("拓扑排序下一层")

            # Reason 4: 与学习目标相关 — on the target chain
            if name in target_distances:
                reasons.append("与学习目标相关")

            recommendations.append({
                "name": name,
                "reason": "；".join(reasons) if reasons else "综合推荐",
                "reasons": reasons,
                "priority_score": round(priority, 1),
                "mastery": round(mastery * 100, 1),
            })

        # ⑧ 薄弱点（≤35% 且可学）
        weak_points = sorted(
            [n for n in next_topics if self.kb.get(n, 0) <= 0.35],
            key=lambda n: self.kb.get(n, 1.0)
        )[:5]

        # ⑨ 本次解锁数（因掌握度变化而新进入 next_topics 的节点）
        # 注：本次调用无"上一次"快照，由调用方传入 prev_mastered 即可比较
        unlocked = len(phases[0]) if phases else 0

        return {
            "phases": [{"phase": i + 1, "topics": p[:8], "count": len(p)}
                       for i, p in enumerate(phases[:5])],
            "next_topics": next_topics,
            "recommendations": recommendations,
            "weak_points": weak_points,
            "mastered_count": len(mastered),
            "total_nodes": len(all_nodes),
            "unlocked_count": unlocked,
            "algorithm": "dynamic_bkt_v2",
        }

    def _compute_target_distances(self, kg_nodes: set[str], kg_edges: dict[str, set[str]],
                                  topic: str) -> dict[str, int]:
        """计算每个节点到目标主题的最短距离（BFS）

        用于聚焦权重：在目标链上的节点优先级更高
        """
        if not topic or topic not in kg_nodes:
            # 模糊匹配：找包含 topic 子串的节点
            candidates = [n for n in kg_nodes if topic in n or n in topic]
            if not candidates:
                return {}
            topic = candidates[0]

        # BFS
        distances = {topic: 0}
        queue = [topic]
        while queue:
            cur = queue.pop(0)
            cur_dist = distances[cur]
            # 前置节点也属于"目标链"（学到 topic 必须先学前置）
            for src, tgts in kg_edges.items():
                if cur in tgts and src not in distances:
                    distances[src] = cur_dist + 1
                    queue.append(src)
            # 后置节点也算
            for tgt in kg_edges.get(cur, set()):
                if tgt not in distances:
                    distances[tgt] = cur_dist + 1
                    queue.append(tgt)

        return distances

    def _compute_priorities(self, all_nodes: set[str], mastered: set[str],
                            real_in_degree: dict[str, int],
                            target_distances: dict[str, int]) -> dict[str, float]:
        """计算每个节点的优先级分数

        优先级构成（分数越高越优先）：
          + 50.0  在目标主题链上（聚焦）
          + 30.0  可学（入度=0）
          + 20.0  薄弱（≤35%）
          + 10.0  较薄弱（35-60%）
          +  5.0  熟悉（60-85%）
          - 50.0  已掌握
          - 10.0  不可学（有未掌握前置）
        """
        priorities = {}
        for node in all_nodes:
            score = 0.0
            mastery = self.kb.get(node, 0.0)

            if mastery >= self.MASTERED_THRESHOLD:
                priorities[node] = -50.0
                continue

            # 可学性
            if real_in_degree.get(node, 0) == 0:
                score += 30.0
            else:
                score -= 10.0

            # 薄弱程度
            if mastery <= 0.35:
                score += 20.0
            elif mastery <= 0.60:
                score += 10.0
            elif mastery <= 0.85:
                score += 5.0

            # 目标聚焦
            if node in target_distances:
                dist = target_distances[node]
                # 距离越近分数越高（距离=0 给50，距离=5给~8）
                score += max(0, 50.0 - dist * 10.0)

            priorities[node] = score

        return priorities


def build_planner_from_db(user_id: int, topic: str = "") -> DynamicPathPlanner:
    """从 DB 加载 BKT 状态 + 用户学习目标，构造规划器

    这是推荐用法：直接传入 user_id，自动读取 BKT 真实状态
    """
    from app.core.database import SessionLocal
    from app.models.bkt_state import BKTState
    from app.models.profile import LearningProfile

    db = SessionLocal()
    try:
        # ① 加载 BKT 状态（归一化概念名，对齐知识图谱节点名）
        from app.services.bkt_service import normalize_concept_name as normalize
        bkt_rows = db.query(BKTState).filter(BKTState.user_id == user_id).all()
        knowledge_base = {}
        for row in bkt_rows:
            normalized = normalize(row.concept)
            if normalized and normalized != "未分类":
                knowledge_base[normalized] = max(knowledge_base.get(normalized, 0), row.p_known)

        # ② 加载用户学习目标（topic 缺省时取 profile 第一个）
        if not topic:
            profile = db.query(LearningProfile).filter(
                LearningProfile.user_id == user_id
            ).first()
            if profile:
                topic = profile.learning_goal or ""

        return DynamicPathPlanner(knowledge_base, topic=topic)
    finally:
        db.close()
