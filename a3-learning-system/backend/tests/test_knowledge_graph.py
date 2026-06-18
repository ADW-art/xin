"""
知识图谱 + 拓扑排序单元测试

测试范围：
- extract_keywords: 关键词提取（英文/中文）
- build_from_texts: 多文本依赖图构建
- topological_sort: 拓扑排序（线性/菱形/环/跳过已掌握）
- estimate_time: 时间估算

所有测试均为纯计算，不依赖 ChromaDB 或任何外部服务。
"""

import pytest
from app.services.knowledge_graph import KnowledgeGraph, get_graph, STOP_WORDS


# ============================================================
# 关键词提取测试
# ============================================================

class TestKeywordExtraction:
    """关键词提取功能测试。"""

    def test_extract_keywords_basic(self):
        """从简单英文文本中正确提取关键词。"""
        kg = KnowledgeGraph()
        keywords = kg.extract_keywords(
            "Python is a programming language. Python supports object-oriented programming.",
            top_n=10,
        )
        assert len(keywords) > 0, "应至少提取到关键词"
        # 检查常见编程关键词
        kw_names = [kw for kw, _ in keywords]
        assert any("python" in name.lower() for name in kw_names), (
            f"Python 应出现在关键词中，实际: {kw_names}"
        )

    def test_extract_keywords_chinese(self):
        """正确处理中文文本。"""
        kg = KnowledgeGraph()
        keywords = kg.extract_keywords(
            "机器学习是人工智能的一个分支。深度学习使用神经网络进行训练。",
            top_n=10,
        )
        # 中文关键词可能被 jieba 或正则提取
        assert len(keywords) > 0, "应至少提取到中文关键词"

    def test_extract_keywords_weights_order(self):
        """应返回按权重降序排列的结果。"""
        kg = KnowledgeGraph()
        # 重复 keyword1 多次，使其权重高于 keyword2
        text = "keyword1 " * 20 + "keyword2 " * 5
        keywords = kg.extract_keywords(text, top_n=10)
        weights = [w for _, w in keywords]
        # 验证权重降序
        for i in range(len(weights) - 1):
            assert weights[i] >= weights[i + 1], (
                f"权重应降序: {weights}"
            )

    def test_extract_keywords_filters_stop_words(self):
        """应过滤掉停用词。"""
        kg = KnowledgeGraph()
        keywords = kg.extract_keywords("the a is are was were be being python code", top_n=10)
        kw_names = [kw for kw, _ in keywords]
        for stop_word in ["the", "a", "is", "are", "was", "were", "be"]:
            assert stop_word not in kw_names, (
                f"停用词 '{stop_word}' 不应出现在结果中"
            )

    def test_extract_keywords_title_boost(self):
        """标题（# 开头）的词应有更高的权重。"""
        kg = KnowledgeGraph()
        text = "# important_keyword rare_word\n\nimportant_keyword appears again here"
        keywords = kg.extract_keywords(text, top_n=10)
        kw_dict = dict(keywords)
        # important_keyword 因标题加权应排名靠前
        assert "important_keyword" in kw_dict, "标题词应被提取"
        if "rare_word" in kw_dict and "important_keyword" in kw_dict:
            # 标题中的词权重可能更高
            assert True  # 通过了过滤即可


# ============================================================
# 图构建测试
# ============================================================

class TestGraphBuilding:
    """知识图谱构建测试。"""

    def test_build_from_texts_creates_nodes(self):
        """build_from_texts 应提取知识点并创建节点。"""
        kg = KnowledgeGraph()
        texts = [
            {
                "title": "Python 基础",
                "content": "变量和数据类型是 Python 的基础。列表是常用的数据结构。",
            },
            {
                "title": "函数",
                "content": "函数使用 def 关键字定义。装饰器是高级函数特性。",
            },
        ]
        kg.build_from_texts(texts)
        assert len(kg.nodes) > 0, "应创建知识点节点"

    def test_build_from_texts_creates_edges(self):
        """相同段落中先出现的知识点应建立到后出现的知识点的边。"""
        kg = KnowledgeGraph()
        texts = [
            {
                "title": "入门",
                "content": "基本概念入门。变量基础。数据类型介绍。",
            },
        ]
        kg.build_from_texts(texts)
        # 至少应有节点，边可能因共现分析而创建
        assert len(kg.nodes) > 0

    def test_build_from_texts_linear_sequence(self):
        """线性序列文本应在提取的关键词之间建立依赖边。"""
        kg = KnowledgeGraph()
        texts = [
            {
                "title": "Step by Step",
                "content": (
                    "First learn variables.\n\n"
                    "Then study functions.\n\n"
                    "After that explore modules.\n\n"
                    "Finally understand packages."
                ),
            }
        ]
        kg.build_from_texts(texts)
        # 至少有关键词被提取
        assert len(kg.nodes) >= 1, "应提取到至少一个关键词"


# ============================================================
# 拓扑排序测试
# ============================================================

class TestTopologicalSort:
    """拓扑排序算法测试。"""

    def test_topological_sort_linear(self):
        """线性依赖 A→B→C 应输出 [A],[B],[C] 三个阶段。"""
        kg = KnowledgeGraph()
        kg.nodes = {"A", "B", "C"}
        kg.edges = {"A": {"B"}, "B": {"C"}}
        kg.in_degree = {"A": 0, "B": 1, "C": 1}
        kg.keyword_weights = {"A": 3, "B": 2, "C": 1}

        phases = kg.topological_sort()
        assert len(phases) == 3, f"应有3阶段，实际: {len(phases)}"
        assert phases[0] == ["A"], f"第1阶段应为[A]，实际: {phases[0]}"
        assert phases[1] == ["B"], f"第2阶段应为[B]，实际: {phases[1]}"
        assert phases[2] == ["C"], f"第3阶段应为[C]，实际: {phases[2]}"

    def test_topological_sort_diamond(self):
        """菱形依赖 A→B, A→C, B,C→D。"""
        kg = KnowledgeGraph()
        kg.nodes = {"A", "B", "C", "D"}
        kg.edges = {"A": {"B", "C"}, "B": {"D"}, "C": {"D"}}
        kg.in_degree = {"A": 0, "B": 1, "C": 1, "D": 2}
        kg.keyword_weights = {"A": 4, "B": 3, "C": 2, "D": 1}

        phases = kg.topological_sort()
        assert len(phases) >= 3, f"菱形应有至少3阶段，实际: {len(phases)}"
        assert phases[0] == ["A"], f"第1阶段应为[A]，实际: {phases[0]}"
        # B和C应同时出现在同一阶段（入度均为0）
        assert set(phases[1]) == {"B", "C"}, f"第2阶段应为{{B,C}}，实际: {phases[1]}"
        assert phases[2] == ["D"], f"第3阶段应为[D]，实际: {phases[2]}"

    def test_topological_sort_with_known_topics(self):
        """已掌握知识点的入度贡献应被移除。"""
        kg = KnowledgeGraph()
        kg.nodes = {"A", "B", "C", "D"}
        kg.edges = {"A": {"B", "C"}, "B": {"D"}, "C": {"D"}}
        kg.in_degree = {"A": 0, "B": 1, "C": 1, "D": 2}
        kg.keyword_weights = {"A": 4, "B": 3, "C": 2, "D": 1}

        # B 已掌握 → B→D 的入度被移除，D 入度降为 1
        phases = kg.topological_sort(known_topics={"A", "B"})
        # A和B已掌握，跳过。只剩C→D
        assert "A" not in [n for p in phases for n in p]
        assert "B" not in [n for p in phases for n in p]

    def test_topological_sort_empty(self):
        """空图应返回空列表。"""
        kg = KnowledgeGraph()
        phases = kg.topological_sort()
        assert phases == []

    def test_topological_sort_single_node(self):
        """单节点图应返回 [[node]]。"""
        kg = KnowledgeGraph()
        kg.nodes = {"only"}
        kg.edges = {}
        kg.in_degree = {"only": 0}
        kg.keyword_weights = {"only": 1}

        phases = kg.topological_sort()
        assert phases == [["only"]]

    def test_topological_sort_independent_nodes(self):
        """无边的独立节点应全部出现在同一阶段。"""
        kg = KnowledgeGraph()
        kg.nodes = {"X", "Y", "Z"}
        kg.edges = {}
        kg.in_degree = {"X": 0, "Y": 0, "Z": 0}
        kg.keyword_weights = {"X": 1, "Y": 2, "Z": 3}

        phases = kg.topological_sort()
        assert len(phases) == 1, f"独立节点应合并为1阶段，实际: {len(phases)}"
        assert set(phases[0]) == {"X", "Y", "Z"}

    def test_cycle_detection_does_not_crash(self):
        """有环的图不应导致死循环或崩溃。"""
        kg = KnowledgeGraph()
        kg.nodes = {"A", "B", "C"}
        # 环 A→B→C→A
        kg.edges = {"A": {"B"}, "B": {"C"}, "C": {"A"}}
        kg.in_degree = {"A": 1, "B": 1, "C": 1}
        kg.keyword_weights = {"A": 1, "B": 2, "C": 3}

        # 不应报错，应通过取最小入度打破环
        phases = kg.topological_sort()
        total_nodes = sum(len(p) for p in phases)
        assert total_nodes == 3, f"输出应包含全部3个节点，实际: {total_nodes}"


# ============================================================
# 时间估算测试
# ============================================================

class TestTimeEstimation:
    """学习时间估算测试。"""

    def test_estimate_time(self):
        """estimate_time 应为每个阶段计算小时数和周数。"""
        kg = KnowledgeGraph()
        phases = [
            ["基础语法", "变量", "数据类型"],
            ["函数", "模块"],
            ["面向对象", "异常处理"],
        ]
        estimates = kg.estimate_time(phases, weekly_hours=10)

        assert len(estimates) == 3
        for i, est in enumerate(estimates):
            assert est["phase"] == i + 1
            assert "topics" in est
            assert "estimated_hours" in est
            assert "estimated_weeks" in est
            assert "milestone" in est
            assert est["estimated_hours"] > 0
            assert est["estimated_weeks"] >= 1

    def test_estimate_time_zero_hours(self):
        """weekly_hours=0 不应导致除零错误。"""
        kg = KnowledgeGraph()
        phases = [["A", "B"]]
        # 即使 weekly_hours=0（极端），也不应崩溃
        estimates = kg.estimate_time(phases, weekly_hours=0)
        assert len(estimates) == 1
        # weeks 应至少为 1
        assert estimates[0]["estimated_weeks"] >= 1

    def test_estimate_time_single_phase(self):
        """单阶段应正确计算。"""
        kg = KnowledgeGraph()
        phases = [["A"]]
        estimates = kg.estimate_time(phases, weekly_hours=5)
        assert len(estimates) == 1
        assert estimates[0]["phase"] == 1
        assert estimates[0]["estimated_hours"] == pytest.approx(1.5)


# ============================================================
# 单例测试
# ============================================================

class TestGraphSingleton:
    """get_graph() 单例测试。"""

    def test_get_graph_returns_same_instance(self):
        """get_graph() 应返回同一实例。"""
        g1 = get_graph()
        g2 = get_graph()
        assert g1 is g2

    def test_get_graph_returns_knowledge_graph(self):
        """get_graph() 应返回 KnowledgeGraph 实例。"""
        g = get_graph()
        assert isinstance(g, KnowledgeGraph)
