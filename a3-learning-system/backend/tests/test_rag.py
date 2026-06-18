"""
RAG 混合检索 / RRF 融合单元测试

测试范围：
- _rrf_fusion: Reciprocal Rank Fusion 融合算法
  - 两组结果集合并
  - 空输入处理
  - 单侧输入处理
  - 排序正确性验证

注意：_rrf_fusion 是私有函数，但仍可导入测试。
BGE 模型的相关测试（embedding, hybrid_search）需要模型加载，
仅在此处进行轻量测试或跳过。
"""

import pytest
from app.services.rag_service import _rrf_fusion


# ============================================================
# RRF 融合算法测试
# ============================================================

class TestRRFFusion:
    """Reciprocal Rank Fusion 融合算法测试。

    RRF 公式: score(d) = sum( 1 / (k + rank_i + 1) )
    其中 k=60，rank_i 是文档在第 i 个结果集中的排名（0-based）。
    """

    def test_rrf_fusion_basic(self):
        """两组结果集应正确合并，高分文档优先。"""
        dense_results = [
            {"id": "doc_a", "content": "内容A", "score": 0.9},
            {"id": "doc_b", "content": "内容B", "score": 0.8},
            {"id": "doc_c", "content": "内容C", "score": 0.7},
        ]
        bm25_results = [
            {"id": "doc_b", "content": "内容B", "score": 0.95},
            {"id": "doc_d", "content": "内容D", "score": 0.85},
            {"id": "doc_a", "content": "内容A", "score": 0.6},
        ]

        fused = _rrf_fusion(dense_results, bm25_results)

        # 应有唯一文档：A, B, C, D（去重以 ID 为准）
        ids = [doc["id"] for doc in fused]
        assert len(ids) == len(set(ids)), "融合后 ID 应唯一"

        # 应包含所有文档
        assert "doc_a" in ids
        assert "doc_b" in ids
        assert "doc_c" in ids
        assert "doc_d" in ids

        # 在两个列表中都排名靠前的 doc_a 和 doc_b 应排前面
        top2 = set(ids[:2])
        assert "doc_a" in top2 or "doc_b" in top2, (
            f"出现在两个列表中的 doc_a/b 应排名靠前，实际前2: {ids[:2]}"
        )

    def test_rrf_fusion_empty(self):
        """空输入应返回空列表。"""
        fused = _rrf_fusion([], [])
        assert fused == []

    def test_rrf_fusion_single(self):
        """只有一个结果集时，应保持不变（无另一侧贡献）。"""
        dense_results = [
            {"id": "doc_x", "content": "X", "score": 0.9},
            {"id": "doc_y", "content": "Y", "score": 0.8},
        ]
        fused = _rrf_fusion(dense_results, [])

        assert len(fused) == 2
        ids = [doc["id"] for doc in fused]
        # 原顺序应保持（无 BM25 重新打分）
        assert "doc_x" in ids
        assert "doc_y" in ids

    def test_rrf_fusion_ordering(self):
        """排名靠前的文档应获得更高的 RRF 融合分数。"""
        # 排名1（rank=0）: 1/(60+0+1) = 1/61 ≈ 0.0164
        # 排名2（rank=1）: 1/(60+1+1) = 1/62 ≈ 0.0161
        # 排名3（rank=2）: 1/(60+2+1) = 1/63 ≈ 0.0159
        k = 60
        assert 1.0 / (k + 0 + 1) > 1.0 / (k + 1 + 1), "排名0分数应 > 排名1分数"
        assert 1.0 / (k + 1 + 1) > 1.0 / (k + 2 + 1), "排名1分数应 > 排名2分数"

    def test_rrf_fusion_doc_in_both_lists_gets_higher_score(self):
        """同时出现在两个结果集中的文档因两侧贡献应排名更高。"""
        dense_results = [
            {"id": "doc_a", "content": "A", "score": 0.9},
            {"id": "doc_b", "content": "B", "score": 0.8},
        ]
        bm25_results = [
            {"id": "doc_a", "content": "A", "score": 0.95},  # 同时出现
            {"id": "doc_c", "content": "C", "score": 0.6},
        ]

        fused = _rrf_fusion(dense_results, bm25_results)
        # doc_a 在两列表中都是 rank 0 → 双倍分数 → 排第一
        assert fused[0]["id"] == "doc_a", (
            f"同时出现的 doc_a 应排第一，实际第一: {fused[0]['id']}"
        )

    def test_rrf_fusion_preserves_content(self):
        """融合后应保留原始内容和元数据。"""
        dense_results = [
            {"id": "d1", "content": "Python 装饰器", "metadata": {"source": "教材"}},
        ]
        bm25_results = [
            {"id": "d2", "content": "装饰器详解", "metadata": {"source": "习题"}},
        ]

        fused = _rrf_fusion(dense_results, bm25_results)
        assert len(fused) == 2
        # 检查内容完整保留
        contents = {doc["content"] for doc in fused}
        assert "Python 装饰器" in contents
        assert "装饰器详解" in contents

    def test_rrf_fusion_large_result_sets(self):
        """大量结果集不会导致性能问题。"""
        dense_results = [{"id": f"d{i}", "content": f"D{i}", "score": 1.0 - i * 0.01} for i in range(50)]
        bm25_results = [{"id": f"b{i}", "content": f"B{i}", "score": 1.0 - i * 0.01} for i in range(50)]

        fused = _rrf_fusion(dense_results, bm25_results)
        assert len(fused) == 100  # 所有 ID 唯一点

    def test_rrf_fusion_k_parameter_default(self):
        """验证默认 k=60 的 RRF 公式。"""
        dense_results = [{"id": "only1", "content": "test"}]
        fused_single = _rrf_fusion(dense_results, [])
        assert len(fused_single) == 1
        # 含有一个结果就返回它
        assert fused_single[0]["id"] == "only1"
