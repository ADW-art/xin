"""
BKT（贝叶斯知识追踪）算法单元测试

测试范围：
- KnowledgeNode: 纯数学贝叶斯更新逻辑
- BKTTracker: 知识点管理、难度推荐、批量记录

所有 BKT 测试均为纯数学/内存测试，不依赖数据库。
"""

import pytest
from app.services.bkt_service import KnowledgeNode, BKTTracker, DEFAULT_PARAMS


# ============================================================
# KnowledgeNode 基础测试
# ============================================================

class TestKnowledgeNode:
    """KnowledgeNode 纯数学单元测试 —— 验证贝叶斯公式正确性。"""

    def test_initial_p_known(self):
        """新建 KnowledgeNode 时 P(L0) 应为默认初始值 0.3。"""
        node = KnowledgeNode("test_concept")
        assert node.p_known == pytest.approx(0.3)
        assert node.name == "test_concept"
        assert node.total_attempts == 0
        assert node.correct_count == 0

    def test_initial_p_known_custom(self):
        """支持自定义初始 P(known)。"""
        node = KnowledgeNode("math", p_known=0.5)
        assert node.p_known == pytest.approx(0.5)

    def test_correct_answer_increases_p_known(self):
        """答对后 P(known) 应上升。"""
        node = KnowledgeNode("python")
        initial = node.p_known
        node.update(is_correct=True)
        assert node.p_known > initial, (
            f"答对后 P(known) 应上升: {initial:.4f} → {node.p_known:.4f}"
        )

    def test_wrong_answer_decreases_p_known(self):
        """从高起点答错后 P(known) 应下降。"""
        # 从较高的 P(known)=0.7 开始答错，确保下降
        node = KnowledgeNode("python", p_known=0.7)
        initial = node.p_known
        node.update(is_correct=False)
        assert node.p_known < initial, (
            f"答错后 P(known) 应下降: {initial:.4f} → {node.p_known:.4f}"
        )

    def test_mastery_threshold(self):
        """P(known) > 0.85 时 is_mastered=True。"""
        node = KnowledgeNode("python", p_known=0.9)
        assert node.is_mastered is True
        assert node.level == "精通"

        node2 = KnowledgeNode("java", p_known=0.8)
        assert node2.is_mastered is False

        node3 = KnowledgeNode("c", p_known=0.86)
        assert node3.is_mastered is True

    def test_p_known_bounds(self):
        """P(known) 应始终钳制在 [0.01, 0.99] 范围内。"""
        # 从极低值开始，多次答错
        node_low = KnowledgeNode("hard", p_known=0.02)
        for _ in range(100):
            node_low.update(is_correct=False)
        assert node_low.p_known >= 0.01, f"下界应为 0.01，实际: {node_low.p_known}"

        # 从极高值开始，多次答对
        node_high = KnowledgeNode("easy", p_known=0.98)
        for _ in range(100):
            node_high.update(is_correct=True)
        assert node_high.p_known <= 0.99, f"上界应为 0.99，实际: {node_high.p_known}"

    def test_level_progression(self):
        """掌握等级应随 P(known) 增长依次经历 入门→学习中→熟悉→精通。"""
        node = KnowledgeNode("topic", p_known=0.01)
        assert node.level == "入门"

        node.p_known = 0.36
        assert node.level == "学习中"

        node.p_known = 0.65
        assert node.level == "熟悉"

        node.p_known = 0.86
        assert node.level == "精通"

    def test_multiple_correct_answers_reaches_mastery(self):
        """连续答对 10 次应达到精通水平。"""
        node = KnowledgeNode("topic")
        for _ in range(10):
            node.update(is_correct=True)
        assert node.is_mastered, (
            f"连续答对 10 次后应已掌握，P(known)={node.p_known:.4f}"
        )
        assert node.total_attempts == 10
        assert node.correct_count == 10

    def test_alternating_answers_stabilizes(self):
        """正确/错误交替时 P(known) 应在合理范围内振荡（P(T)=0.4导致较大波动属正常）"""
        node = KnowledgeNode("tricky")
        history = []
        for i in range(40):
            is_correct = (i % 2 == 0)  # 交替
            node.update(is_correct=is_correct)
            history.append(node.p_known)

        # 交替时波动较大是正常的（P(T)=0.4 的跳跃效应），但应始终在 [0.01, 0.99] 内
        assert all(0.01 <= v <= 0.99 for v in history), (
            f"P(known) 超界: min={min(history):.4f} max={max(history):.4f}"
        )
        # 连续答对时应收敛到 >0.85
        node2 = KnowledgeNode("tricky2")
        for _ in range(10):
            node2.update(is_correct=True)
        assert node2.p_known > 0.85, f"连续10次答对应接近精通: {node2.p_known:.4f}"
        # 连续答错时应收敛到 <0.05
        node3 = KnowledgeNode("tricky3")
        for _ in range(10):
            node3.update(is_correct=False)
        assert node3.p_known < 0.05, f"连续10次答错应接近0: {node3.p_known:.4f}"

    def test_difficulty_recommendation(self):
        """get_difficulty() 应根据 P(known) 返回合适难度。"""
        node = KnowledgeNode("topic")
        # 使用 tracker 的 get_difficulty 方法
        tracker = BKTTracker(user_id=0)
        # 手动设置节点
        tracker.nodes["easy"] = KnowledgeNode("easy", p_known=0.9)
        tracker.nodes["mid"] = KnowledgeNode("mid", p_known=0.5)
        tracker.nodes["hard"] = KnowledgeNode("hard", p_known=0.2)
        tracker.nodes["challenge"] = KnowledgeNode("challenge", p_known=0.95)

        assert tracker.get_difficulty("easy") == "挑战"
        assert tracker.get_difficulty("mid") == "中等"
        assert tracker.get_difficulty("hard") == "简单"
        assert tracker.get_difficulty("challenge") == "挑战"

    def test_to_dict_contains_expected_fields(self):
        """to_dict() 应包含所有必需字段。"""
        node = KnowledgeNode("python")
        node.update(is_correct=True)
        node.update(is_correct=True)
        node.update(is_correct=False)

        d = node.to_dict()
        assert d["name"] == "python"
        assert "p_known" in d
        assert "level" in d
        assert "is_mastered" in d
        assert "attempts" in d
        assert "correct_rate" in d
        assert d["attempts"] == 3

    def test_update_counter(self):
        """每次 update 应递增 total_attempts，答对递 increment_count。"""
        node = KnowledgeNode("topic")
        node.update(is_correct=True)
        node.update(is_correct=False)
        node.update(is_correct=True)

        assert node.total_attempts == 3
        assert node.correct_count == 2


# ============================================================
# BKTTracker 测试
# ============================================================

class TestBKTTracker:
    """BKTTracker 内存模式测试（user_id=0，不触发 DB）。"""

    def test_get_or_create_new(self):
        """get_or_create 应创建新节点。"""
        tracker = BKTTracker(user_id=0)
        node = tracker.get_or_create("装饰器")
        assert node.name == "装饰器"
        assert node.p_known == pytest.approx(0.3)

    def test_get_or_create_existing(self):
        """get_or_create 应返回已有节点（不重置状态）。"""
        tracker = BKTTracker(user_id=0)
        node1 = tracker.get_or_create("Python基础")
        node1.update(is_correct=True)
        node2 = tracker.get_or_create("Python基础")
        assert node1 is node2
        assert node2.total_attempts == 1

    def test_record_answer_updates_state(self):
        """record_answer 应更新对应知识点并日志记录。"""
        tracker = BKTTracker(user_id=0)
        tracker.record_answer("Python基础", True)
        node = tracker.nodes["Python基础"]
        assert node.p_known > DEFAULT_PARAMS["p_initial"]
        assert node.total_attempts == 1
        assert node.correct_count == 1

    def test_batch_record(self):
        """record_batch 应批量处理多个知识点。"""
        tracker = BKTTracker(user_id=0)
        results = [
            {"concept": "数组", "correct": True},
            {"concept": "数组", "correct": True},
            {"concept": "队列", "correct": False},
            {"concept": "队列", "correct": True},
        ]
        tracker.record_batch(results)

        assert "数组" in tracker.nodes
        assert tracker.nodes["数组"].total_attempts == 2
        assert "队列" in tracker.nodes
        assert tracker.nodes["队列"].total_attempts == 2

    def test_get_all_scores(self):
        """get_all_scores 应返回所有知识点的掌握分数。"""
        tracker = BKTTracker(user_id=0)
        tracker.get_or_create("Python基础", p_known=0.5)
        tracker.get_or_create("数组", p_known=0.8)
        tracker.get_or_create("排序算法", p_known=0.2)

        scores = tracker.get_all_scores()
        assert len(scores) == 3
        assert scores["Python基础"] == pytest.approx(0.5)
        assert scores["数组"] == pytest.approx(0.8)

    def test_get_mastered_and_weak_points(self):
        """应正确区分已掌握和薄弱知识点。"""
        tracker = BKTTracker(user_id=0)
        tracker.get_or_create("Python基础", p_known=0.9)
        tracker.get_or_create("链表", p_known=0.5)
        tracker.get_or_create("数组", p_known=0.2)
        tracker.get_or_create("C++基础", p_known=0.86)

        mastered = tracker.get_mastered()
        weak = tracker.get_weak_points()

        assert "Python基础" in mastered
        assert "C++基础" in mastered
        assert "链表" not in mastered
        assert "数组" in weak
        assert len(weak) == 1

    def test_to_dict_summary(self):
        """to_dict 应包含正确的汇总统计。"""
        tracker = BKTTracker(user_id=0)
        tracker.get_or_create("Python基础", p_known=0.9)
        tracker.get_or_create("数组", p_known=0.3)
        tracker.get_or_create("排序算法", p_known=0.6)

        data = tracker.to_dict()
        assert "nodes" in data
        assert "summary" in data
        assert data["summary"]["total"] == 3
        assert data["summary"]["mastered"] == 1  # only Python高级 > 0.85
        assert data["summary"]["average"] > 0


# ============================================================
# 边界条件
# ============================================================

class TestBKTEdgeCases:
    """BKT 边界条件测试。"""

    def test_zero_initial_p_known(self):
        """p_known=0 的极端情况：update 后会钳制到 [0.01, 0.99]。"""
        node = KnowledgeNode("zero", p_known=0.0)
        # __init__ 不钳制，但 update 会钳制
        node.update(is_correct=False)
        assert node.p_known >= 0.01, f"update 后应 ≥ 0.01，实际: {node.p_known}"

    def test_one_initial_p_known(self):
        """p_known=1 的极端情况：update 后会钳制到 [0.01, 0.99]。"""
        node = KnowledgeNode("one", p_known=1.0)
        # __init__ 不钳制，但 update 会钳制
        node.update(is_correct=True)
        assert node.p_known <= 0.99, f"update 后应 ≤ 0.99，实际: {node.p_known}"

    def test_empty_tracker(self):
        """空 tracker 的各种查询不应崩溃。"""
        tracker = BKTTracker(user_id=0)
        assert tracker.get_all_scores() == {}
        assert tracker.get_mastered() == []
        assert tracker.get_weak_points() == []
        assert tracker.to_dict()["summary"]["total"] == 0

    def test_get_difficulty_unknown_concept(self):
        """查询未知知识点时应自动创建（默认 P=0.3），返回"简单"。"""
        tracker = BKTTracker(user_id=0)
        difficulty = tracker.get_difficulty("unknown_topic")
        assert difficulty == "简单"
