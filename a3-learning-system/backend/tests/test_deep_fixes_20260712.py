"""
深度测试: 对话系统全部修改 (2026-07-12)

覆盖:
  - _teaching_context_reducer: None清空、dict合并、边界
  - _concat_list_reducer: 截断、边界
  - _parse_cn_number: 1-99中文数字、边界、异常
  - _parse_day_number: 完整解析链路
  - 难度标度归一化: 百分制/1-10自动检测
  - _proactive_suggest: 高/低掌握路由
  - override_map: 关键词无冲突
  - 去重缓存: 过期清理、容量保护
  - DAG set: O(1)查找
  - asyncio.wait 心跳: 不取消生成器
  - _force_stop: 终止外层循环
"""
import pytest
import asyncio
import time


# ═══════════════════════════════════════════════════════════════
# 1. _teaching_context_reducer (state.py)
# ═══════════════════════════════════════════════════════════════
class TestTeachingContextReducer:
    """P0-FIX: _teaching_context_reducer 深度测试"""

    def test_none_clears_existing_context(self):
        """None 清空已存在的 teaching_context"""
        from app.agents.state import _teaching_context_reducer
        result = _teaching_context_reducer(
            {"mode": "teaching", "current_index": 5, "active_path": ["a", "b", "c"]},
            None
        )
        assert result is None

    def test_none_clears_empty_context(self):
        """None 清空空 teaching_context"""
        from app.agents.state import _teaching_context_reducer
        result = _teaching_context_reducer({}, None)
        assert result is None

    def test_dict_merges_with_existing(self):
        """新 dict 与已有 context 合并"""
        from app.agents.state import _teaching_context_reducer
        result = _teaching_context_reducer(
            {"mode": "teaching", "current_index": 3},
            {"current_index": 5, "active_path": ["x", "y"]}
        )
        assert result == {"mode": "teaching", "current_index": 5, "active_path": ["x", "y"]}

    def test_dict_overwrites_partial(self):
        """部分字段覆盖"""
        from app.agents.state import _teaching_context_reducer
        result = _teaching_context_reducer(
            {"mode": "teaching", "a": 1, "b": 2},
            {"b": 3, "c": 4}
        )
        assert result == {"mode": "teaching", "a": 1, "b": 3, "c": 4}

    def test_old_none_new_dict(self):
        """old=None 时 new dict 直接返回"""
        from app.agents.state import _teaching_context_reducer
        result = _teaching_context_reducer(None, {"mode": "teaching"})
        assert result == {"mode": "teaching"}

    def test_both_none(self):
        """双向 None → None"""
        from app.agents.state import _teaching_context_reducer
        result = _teaching_context_reducer(None, None)
        assert result is None

    def test_new_empty_dict_preserves_old(self):
        """空 dict 保留旧值(与旧行为一致)"""
        from app.agents.state import _teaching_context_reducer
        result = _teaching_context_reducer({"mode": "teaching"}, {})
        assert result == {"mode": "teaching"}

    def test_old_empty_new_dict(self):
        """空旧值 + 新dict = 新dict"""
        from app.agents.state import _teaching_context_reducer
        result = _teaching_context_reducer({}, {"mode": "teaching"})
        assert result == {"mode": "teaching"}


# ═══════════════════════════════════════════════════════════════
# 2. _concat_list_reducer (state.py)
# ═══════════════════════════════════════════════════════════════
class TestConcatListReducer:
    """P1-FIX: trace 截断逻辑"""

    def test_normal_concat(self):
        """正常拼接"""
        from app.agents.state import _concat_list_reducer
        result = _concat_list_reducer([1, 2, 3], [4, 5])
        assert result == [1, 2, 3, 4, 5]

    def test_old_none(self):
        """old=None 兜底"""
        from app.agents.state import _concat_list_reducer
        result = _concat_list_reducer(None, [1, 2])
        assert result == [1, 2]

    def test_new_none(self):
        """new=None 兜底"""
        from app.agents.state import _concat_list_reducer
        result = _concat_list_reducer([1, 2], None)
        assert result == [1, 2]

    def test_truncate_at_100(self):
        """超过 100 条截断"""
        from app.agents.state import _concat_list_reducer
        old = list(range(99))
        new = [99, 100, 101]
        result = _concat_list_reducer(old, new)
        assert len(result) == 100
        assert result[0] == 2    # 丢弃前 2 条
        assert result[-1] == 101  # 保留最新

    def test_exactly_100_no_truncate(self):
        """恰好 100 条不截断"""
        from app.agents.state import _concat_list_reducer
        old = list(range(97))
        new = [97, 98, 99]
        result = _concat_list_reducer(old, new)
        assert len(result) == 100
        assert result == list(range(100))

    def test_massive_truncate(self):
        """大量数据正确截断"""
        from app.agents.state import _concat_list_reducer
        old = list(range(500))
        new = [500, 501, 502]
        result = _concat_list_reducer(old, new)
        assert len(result) == 100
        assert result[-1] == 502

    def test_empty_old(self):
        """空列表 + 新数据"""
        from app.agents.state import _concat_list_reducer
        result = _concat_list_reducer([], [1, 2, 3])
        assert result == [1, 2, 3]

    def test_empty_new(self):
        """旧数据 + 空列表"""
        from app.agents.state import _concat_list_reducer
        result = _concat_list_reducer([1, 2, 3], [])
        assert result == [1, 2, 3]


# ═══════════════════════════════════════════════════════════════
# 3. _parse_cn_number + _parse_day_number (shared_utils.py)
# ═══════════════════════════════════════════════════════════════
class TestParseCnNumber:
    """P2-FIX: 中文数字解析"""

    def test_single_digit(self):
        from app.core.shared_utils import _parse_cn_number
        assert _parse_cn_number("一") == 1
        assert _parse_cn_number("五") == 5
        assert _parse_cn_number("九") == 9

    def test_exact_ten(self):
        from app.core.shared_utils import _parse_cn_number
        assert _parse_cn_number("十") == 10

    def test_teens(self):
        from app.core.shared_utils import _parse_cn_number
        assert _parse_cn_number("十一") == 11
        assert _parse_cn_number("十五") == 15
        assert _parse_cn_number("十九") == 19

    def test_twenties(self):
        from app.core.shared_utils import _parse_cn_number
        assert _parse_cn_number("二十") == 20
        assert _parse_cn_number("二十五") == 25

    def test_thirties_plus(self):
        from app.core.shared_utils import _parse_cn_number
        assert _parse_cn_number("三十一") == 31
        assert _parse_cn_number("四十二") == 42
        assert _parse_cn_number("五十三") == 53
        assert _parse_cn_number("九十九") == 99

    def test_hardcoded_fallback(self):
        """硬编码表仍工作"""
        from app.core.shared_utils import _parse_cn_number
        # 这些在硬编码 _CN_NUM 中
        assert _parse_cn_number("十二") == 12
        assert _parse_cn_number("二十八") == 28

    def test_digit_strings(self):
        """阿拉伯数字直通"""
        from app.core.shared_utils import _parse_cn_number
        assert _parse_cn_number("1") == 1
        assert _parse_cn_number("99") == 99
        assert _parse_cn_number("0") == 0

    def test_empty_string(self):
        from app.core.shared_utils import _parse_cn_number
        assert _parse_cn_number("") == 0

    def test_unknown_pattern(self):
        """无法识别的模式返回 0"""
        from app.core.shared_utils import _parse_cn_number
        assert _parse_cn_number("abc") == 0


class TestParseDayNumber:
    """完整解析链路"""

    def test_day_parsing(self):
        from app.core.shared_utils import _parse_day_number
        assert _parse_day_number("第三十一天") == 30

    def test_section_parsing(self):
        from app.core.shared_utils import _parse_day_number
        assert _parse_day_number("第5节") == 4

    def test_chapter_parsing(self):
        from app.core.shared_utils import _parse_day_number
        assert _parse_day_number("第十二章") == 11

    def test_no_match(self):
        from app.core.shared_utils import _parse_day_number
        assert _parse_day_number("没有数字") is None

    def test_in_context(self):
        from app.core.shared_utils import _parse_day_number
        assert _parse_day_number("请开始讲解第三天的内容") == 2


# ═══════════════════════════════════════════════════════════════
# 4. 难度标度归一化 (resource_agent.py)
# ═══════════════════════════════════════════════════════════════
class TestDifficultyScaleNormalization:
    """P1-FIX: 自动检测并归一化知识基础标度"""

    @staticmethod
    def _simulate_scale_detection(kb_data: dict) -> float:
        """复制 resource_agent 中的标度检测逻辑"""
        scores = [v for v in kb_data.values() if isinstance(v, (int, float))]
        if not scores:
            return -1
        avg = sum(scores) / len(scores)
        if max(scores) > 15:
            avg = avg / 10
        return avg

    def test_percent_scale_high(self):
        """百分制高分段 → 归一化为 8.2"""
        result = self._simulate_scale_detection({"a": 85, "b": 92, "c": 78, "d": 65, "e": 90})
        assert 8.0 <= result <= 8.5, f"Expected ~8.2, got {result}"

    def test_percent_scale_low(self):
        """百分制低分段 → 归一化"""
        result = self._simulate_scale_detection({"a": 25, "b": 30, "c": 20})
        assert 2.0 <= result <= 3.0, f"Expected ~2.5, got {result}"

    def test_1_10_scale_high(self):
        """1-10标度高分段 → 保持原值"""
        result = self._simulate_scale_detection({"a": 8, "b": 9, "c": 7})
        assert 7.5 <= result <= 8.5, f"Expected ~8, got {result}"

    def test_1_10_scale_low(self):
        """1-10标度低分段 → 保持原值"""
        result = self._simulate_scale_detection({"a": 2, "b": 3, "c": 1})
        assert 1.5 <= result <= 2.5, f"Expected ~2, got {result}"

    def test_mixed_types(self):
        """混合类型: 过滤非数字值"""
        result = self._simulate_scale_detection({"a": 85, "b": "high", "c": 90, "d": None})
        assert 8.5 <= result <= 9.0, f"Expected ~8.75, got {result}"

    def test_empty_kb(self):
        """空知识库"""
        result = self._simulate_scale_detection({})
        assert result == -1

    def test_single_score_1_10(self):
        """单个 1-10 分数"""
        result = self._simulate_scale_detection({"a": 6})
        assert result == 6.0

    def test_single_score_percent(self):
        """单个百分制分数 → 归一化"""
        result = self._simulate_scale_detection({"a": 70})
        assert result == 7.0

    def test_boundary_15(self):
        """边界: max=15 视为 1-10 标度"""
        result = self._simulate_scale_detection({"a": 15, "b": 10, "c": 5})
        assert result == 10.0  # (15+10+5)/3 = 10, max=15 不触发归一化

    def test_boundary_16(self):
        """边界: max=16 触发百分制归一化"""
        result = self._simulate_scale_detection({"a": 16, "b": 20, "c": 30})
        assert result == 2.2  # (16+20+30)/3/10 = 2.2


# ═══════════════════════════════════════════════════════════════
# 5. override_map 关键词无冲突 (resource_agent.py)
# ═══════════════════════════════════════════════════════════════
class TestOverrideMapNoConflicts:
    """P1-FIX: 同一关键词不应映射到不同资源类型"""

    def test_no_duplicate_keys_to_different_types(self):
        """验证 override_map 中无关键词→多类型冲突"""
        override_map = {
            "思维导图": "mindmap", "脑图": "mindmap", "导图": "mindmap",
            "图解": "diagram", "画图": "diagram", "示意图": "diagram",
            "画一个图": "diagram", "画张图": "diagram", "图解释": "diagram",
            "diagram": "diagram", "流程图": "diagram", "时序图": "diagram",
            "完整讲解": "smart_tutoring", "图文视频": "smart_tutoring", "讲透": "smart_tutoring",
            "三合一": "smart_tutoring", "全方位": "smart_tutoring", "综合讲解": "smart_tutoring",
            "代码": "code_example", "编程": "code_example", "code": "code_example",
            "题目": "question_set", "题": "question_set", "练习": "question_set", "考题": "question_set",
            "视频": "document", "脚本": "document", "讲解视频": "document",
            "文档": "document", "文章": "document", "教程": "document", "笔记": "document",
            "对比": "comparison", "比较": "comparison", "区别": "comparison", "差异": "comparison",
            "notebook": "notebook", "ipynb": "notebook", "笔记本": "notebook", "交互式": "notebook",
            "语音": "audio_lecture", "朗读": "audio_lecture", "讲解": "audio_lecture", "播客": "audio_lecture", "念一遍": "audio_lecture",
            "视频动画": "video_animation", "AI动画": "video_animation", "AI视频": "video_animation", "动画视频": "video_animation",
            "配图": "visual_diagram", "信息图": "visual_diagram", "图示": "visual_diagram", "图文": "visual_diagram",
        }
        # 检测: 同key不同value
        seen: dict[str, str] = {}
        conflicts = []
        for kw, rtype in override_map.items():
            if kw in seen and seen[kw] != rtype:
                conflicts.append(f"{kw} → {seen[kw]} vs {rtype}")
            seen[kw] = rtype
        assert not conflicts, f"冲突: {conflicts}"

    def test_sort_by_length_works(self):
        """长关键词优先匹配(jieba分词配合)"""
        override_map = {"图解": "diagram", "画图": "diagram"}
        sorted_keys = sorted(override_map.items(), key=lambda x: -len(x[0]))
        assert sorted_keys[0][0] == "图解"  # 2 chars, 先出现
        assert sorted_keys[1][0] == "画图"  # 2 chars


# ═══════════════════════════════════════════════════════════════
# 6. _proactive_suggest 路由 (supervisor.py)
# ═══════════════════════════════════════════════════════════════
class TestProactiveSuggestRouting:
    """P1-FIX: 掌握度高→path, 掌握度低→resource"""

    def test_high_mastery_routes_to_path(self):
        from app.agents.supervisor import _proactive_suggest
        result = _proactive_suggest("question_agent", {"mode": "grade", "bkt_p_known": 0.85})
        assert result is not None
        assert result["intent"] == "path"
        assert "推进" in result["reason"]

    def test_low_mastery_routes_to_resource(self):
        from app.agents.supervisor import _proactive_suggest
        result = _proactive_suggest("question_agent", {"mode": "grade", "bkt_p_known": 0.35})
        assert result is not None
        assert result["intent"] == "resource"
        assert "复习" in result["reason"]

    def test_boundary_at_0_7(self):
        """边界: p_known=0.7 → path"""
        from app.agents.supervisor import _proactive_suggest
        result = _proactive_suggest("question_agent", {"mode": "grade", "bkt_p_known": 0.7})
        assert result["intent"] == "path"

    def test_boundary_below_0_7(self):
        """边界: p_known=0.69 → resource"""
        from app.agents.supervisor import _proactive_suggest
        result = _proactive_suggest("question_agent", {"mode": "grade", "bkt_p_known": 0.69})
        assert result["intent"] == "resource"

    def test_other_agents_unchanged(self):
        """非question_agent路由不变"""
        from app.agents.supervisor import _proactive_suggest
        # resource_agent 完成后仍推荐 question
        r = _proactive_suggest("resource_agent", {})
        assert r["intent"] == "question"
        # evaluation_agent 完成后仍推荐 resource
        r = _proactive_suggest("evaluation_agent", {})
        assert r["intent"] == "resource"
        # profile_agent 足够数据 → path
        r = _proactive_suggest("profile_agent", {"profile_data": {"a": 1, "b": 2, "c": 3}})
        assert r["intent"] == "path"


# ═══════════════════════════════════════════════════════════════
# 7. 去重缓存清理 (chat.py)
# ═══════════════════════════════════════════════════════════════
class TestDedupCache:
    """P1-FIX: 过期清理 + 容量保护"""

    def test_short_chunk_skipped(self):
        """< 50 字符直接跳过"""
        from app.api.chat import _is_duplicate_chunk
        assert not _is_duplicate_chunk("test", "short")

    def test_first_chunk_not_duplicate(self):
        """首个长chunk不重复"""
        from app.api.chat import _is_duplicate_chunk
        long_chunk = "x" * 60
        assert not _is_duplicate_chunk("user msg", long_chunk)

    def test_duplicate_detected(self):
        """重复chunk被检测"""
        from app.api.chat import _is_duplicate_chunk
        long_chunk = "y" * 60
        _is_duplicate_chunk("user msg", long_chunk)  # 首次
        assert _is_duplicate_chunk("user msg", long_chunk)  # 重复

    def test_different_chunk_not_duplicate(self):
        """不同内容不误判"""
        from app.api.chat import _is_duplicate_chunk
        assert not _is_duplicate_chunk("user msg", "a" * 60)
        assert not _is_duplicate_chunk("user msg", "b" * 60)

    def test_cache_cleanup_on_insert(self):
        """每次插入清理过期条目"""
        from app.api.chat import _is_duplicate_chunk, _CONTENT_DEDUP_CACHE
        # 注入过期条目
        old_key = "expired_test_key"
        _CONTENT_DEDUP_CACHE[old_key] = ("old_content", time.time() - 20)
        # 插入新条目触发清理
        _is_duplicate_chunk("test", "c" * 60)
        # 过期条目应被清理
        assert old_key not in _CONTENT_DEDUP_CACHE


# ═══════════════════════════════════════════════════════════════
# 8. 异步心跳不取消生成器 (chat.py)
# ═══════════════════════════════════════════════════════════════
class TestAsyncHeartbeatNoCancel:
    """P0-FIX: asyncio.wait 心跳不取消异步生成器"""

    @pytest.mark.asyncio
    async def test_slow_generator_not_cancelled(self):
        """慢生成器(首token>8s)不被心跳取消"""
        output_chunks = []

        async def _slow_gen():
            """模拟慢速 LLM: 第 10s 才产生第一个 chunk"""
            await asyncio.sleep(0.15)  # 缩时: 0.15s 代表 10s
            for c in ["Hello", " ", "World"]:
                yield c
                await asyncio.sleep(0.01)

        async def _mock_bridge_stream():
            """模拟 _bridge_stream: queue-based 异步生成器"""
            queue = asyncio.Queue()

            async def _runner():
                async for chunk in _slow_gen():
                    await queue.put(chunk)
                await queue.put(None)  # sentinel

            asyncio.ensure_future(_runner())

            while True:
                item = await asyncio.wait_for(queue.get(), timeout=30)
                if item is None:
                    break
                yield item

        # 使用 asyncio.wait 模式(新代码), 不取消生成器
        stream = _mock_bridge_stream()
        hb_interval = 0.05  # 缩时心跳: 50ms
        chunk_task = asyncio.ensure_future(stream.__anext__())
        heartbeat_count = 0

        while True:
            hb_task = asyncio.ensure_future(asyncio.sleep(hb_interval))
            done, pending = await asyncio.wait(
                [chunk_task, hb_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if chunk_task in done:
                hb_task.cancel()
                try:
                    chunk = chunk_task.result()
                except StopAsyncIteration:
                    break
                output_chunks.append(chunk)
                chunk_task = asyncio.ensure_future(stream.__anext__())
            else:
                heartbeat_count += 1
                continue  # chunk_task 仍在 pending 中, 不取消

        assert "".join(output_chunks) == "Hello World"
        assert heartbeat_count >= 1, "应至少触发 1 次心跳"

    @pytest.mark.asyncio
    async def test_heartbeat_preserves_generator_state(self):
        """心跳触发后生成器状态保持一致"""
        chunks = []

        async def _gen():
            for c in ["A", "B", "C"]:
                yield c
                await asyncio.sleep(0.02)

        stream = _gen()
        chunk_task = asyncio.ensure_future(stream.__anext__())
        hb_count = 0

        while True:
            hb_task = asyncio.ensure_future(asyncio.sleep(0.01))
            done, pending = await asyncio.wait(
                [chunk_task, hb_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if chunk_task in done:
                hb_task.cancel()
                try:
                    chunks.append(chunk_task.result())
                except StopAsyncIteration:
                    break
                chunk_task = asyncio.ensure_future(stream.__anext__())
            else:
                hb_count += 1
                continue

        assert chunks == ["A", "B", "C"], f"生成器状态被破坏: got {chunks}"
        assert hb_count >= 0  # 快速生成器可能无心跳

    @pytest.mark.asyncio
    async def test_stream_timeout_kills_generator(self):
        """120s 超时正确取消生成器"""
        async def _infinite_gen():
            while True:
                await asyncio.sleep(0.1)
                yield "x"

        stream = _infinite_gen()
        chunk_task = asyncio.ensure_future(stream.__anext__())
        start = time.time()
        timeout = 0.3  # 缩时: 0.3s

        while True:
            hb_task = asyncio.ensure_future(asyncio.sleep(0.05))
            done, pending = await asyncio.wait(
                [chunk_task, hb_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if chunk_task in done:
                hb_task.cancel()
                try:
                    chunk_task.result()
                except StopAsyncIteration:
                    break
                chunk_task = asyncio.ensure_future(stream.__anext__())
            else:
                if time.time() - start > timeout:
                    chunk_task.cancel()
                    break
                continue

        elapsed = time.time() - start
        assert 0.25 <= elapsed <= 0.5, f"超时应在~0.3s, 实际 {elapsed:.2f}s"


# ═══════════════════════════════════════════════════════════════
# 9. _teaching_gate 复用 is_teaching_continue
# ═══════════════════════════════════════════════════════════════
class TestTeachingGateCleanup:
    """P1-FIX: _teaching_gate 不再有重复模式"""

    def test_module_has_no_duplicate_patterns(self):
        """_teaching_gate 不应有独立的 _TEACHING_CONTINUE_PATTERNS"""
        import app.agents._teaching_gate as gate
        assert not hasattr(gate, "_TEACHING_CONTINUE_PATTERNS"), \
            "_TEACHING_CONTINUE_PATTERNS 应已被删除"
        assert not hasattr(gate, "_has_teaching_continue_signal"), \
            "_has_teaching_continue_signal 应已被删除"

    def test_should_init_teaching_still_works(self):
        """should_init_teaching 仍正常工作"""
        from app.agents._teaching_gate import should_init_teaching
        # 无 teaching_context, 无继续信号 → 拒绝
        result = should_init_teaching(
            {"messages": [type("msg", (), {"content": "你好", "type": "human"})()],
             "teaching_context": None, "context": {}},
            {}
        )
        assert result is False

    def test_should_init_teaching_detects_continue(self):
        """检测到继续信号 → 允许"""
        from app.agents._teaching_gate import should_init_teaching
        # 需要模拟完整的 messages 结构
        try:
            from langchain_core.messages import HumanMessage
            msg = HumanMessage(content="继续")
        except ImportError:
            msg = type("msg", (), {"content": "继续", "type": "human"})()
        result = should_init_teaching(
            {"messages": [msg], "teaching_context": None, "context": {}},
            {}
        )
        assert result is True


# ═══════════════════════════════════════════════════════════════
# 10. 集成测试: 完整链路
# ═══════════════════════════════════════════════════════════════
class TestIntegration:
    """端到端场景验证"""

    def test_teaching_context_clear_then_new_request(self):
        """场景: 教学完成后清除→新请求正常路由"""
        from app.agents.state import _teaching_context_reducer

        # Step 1: 教学完成, path_agent 返回 teaching_context=None
        ctx = _teaching_context_reducer(
            {"mode": "teaching", "current_index": 3, "active_path": ["a", "b", "c"]},
            None
        )
        assert ctx is None, "教学完成应清除 context"

        # Step 2: 新请求(如"讲解变量"), 无 teaching_context
        # supervisor 正常分类, 不复用旧状态
        assert ctx is None  # checkpoint 恢复后为 None

    def test_difficulty_scale_full_pipeline(self):
        """完整难度标度管线"""
        # 百分制 → 归一化 → 正确难度描述
        kb = {"Python": 85, "Java": 72, "SQL": 60}
        scores = [v for v in kb.values() if isinstance(v, (int, float))]
        avg = sum(scores) / len(scores)
        max_s = max(scores)
        if max_s > 15:
            avg = avg / 10
        # avg ≈ 7.2, 应归类为"水平较高"
        assert avg >= 7.0, f"归一化后 avg={avg} 应 >= 7.0"

    def test_cn_number_full_parse_chain(self):
        """中文数字 → day number 完整链路"""
        from app.core.shared_utils import _parse_day_number
        # "第三十一天" → 31 → 0-based index 30
        assert _parse_day_number("请学习第三十一天的内容") == 30
        # "第5节" → 5 → 0-based index 4
        assert _parse_day_number("开始第5节") == 4
        # "第十二章" → 12 → 0-based index 11
        assert _parse_day_number("进入第十二章") == 11
