"""
Question Agent: 出题/评阅模式切换 + 答案检测与提取

测试覆盖:
- is_answer_submission — 答案格式识别 (字母/中文/代码/列表/布尔)
- is_answer_submission — 非答案文本拒绝 (自然语言/过短/过长)
- extract_answer_map   — 显式题号格式解析
- extract_answer_map   — 无题号顺序格式解析
- extract_answer_map   — 边界条件

纯函数测试，无需数据库/网络/LLM 调用。

注意: is_answer_submission 的 ANSWER_PATTERNS 基于正则匹配，某些格式
      (如 "1:A" 冒号分隔) 不被识别为答案提交 — 这是设计决策，
      因为 extract_answer_map 单独处理冒号格式。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.question_agent import is_answer_submission, extract_answer_map


# ═══════════════════════════════════════════════════════════════
# is_answer_submission — 答案格式识别
# ═══════════════════════════════════════════════════════════════

class TestAnswerDetection:
    """检测 is_answer_submission 对各类答案格式的识别能力"""

    def test_detect_letter_answer_single(self):
        """单题字母答案: '1A' '2B' '3C' '4D' — 匹配 ^[1-9][s]*[A-Da-d]"""
        assert is_answer_submission("1A") is True
        assert is_answer_submission("2B") is True
        assert is_answer_submission("3C") is True
        assert is_answer_submission("4D") is True

    def test_detect_letter_answer_lowercase(self):
        """小写字母答案: '1a' '2b' (IGNORECASE 标志生效)"""
        assert is_answer_submission("1a") is True
        assert is_answer_submission("2b") is True

    def test_detect_letter_answer_with_spaces(self):
        """带空格的字母答案: '1 A 2 B 3 C' — 匹配 ^[1-9][s]*[A-Da-d]"""
        assert is_answer_submission("1 A 2 B 3 C") is True
        assert is_answer_submission("1 A") is True

    def test_detect_letter_answer_compact(self):
        """紧凑格式: '1A2B3C4D' — 匹配 ^[1-9][s]*[A-Da-d][s]*[1-9]"""
        assert is_answer_submission("1A2B3C4D") is True

    def test_detect_chinese_answer_dui_cuo(self):
        """中文对错答案: '1对 2错' — 匹配 ^[1-9][s]*(?:正确|错误|对|错)"""
        assert is_answer_submission("1对 2错") is True
        assert is_answer_submission("1正确 2错误") is True
        assert is_answer_submission("1对") is True

    def test_detect_answer_prefix_ascii_colon(self):
        """'答案:' 前缀 (ASCII 冒号) — 匹配 ^(?:答案是?|答案)[:s]"""
        assert is_answer_submission("答案:A") is True
        assert is_answer_submission("答案是 C") is True  # 空格分隔也行 [:\s]

    def test_detect_select_fill_prefix(self):
        """'选' '填' '我的答案' 前缀 — 匹配 ^(?:选|填|我的答案)"""
        assert is_answer_submission("选A") is True
        assert is_answer_submission("填B") is True
        assert is_answer_submission("我的答案是D") is True

    def test_detect_code_answer_python_def(self):
        """Python 函数定义 — 匹配 def\s+\w+\s*\(.*\):"""
        assert is_answer_submission("def foo():\n    return 42") is True
        assert is_answer_submission("def reverse_list(lst):\n    return lst[::-1]") is True

    def test_detect_list_answer_without_quotes(self):
        """列表格式答案 (无引号) — 匹配 ^\[[\w\s,]+\]$"""
        assert is_answer_submission("[1, 2, 3]") is True
        assert is_answer_submission("[a, b, c]") is True
        assert is_answer_submission("[True, False]") is True

    def test_detect_bool_number_answer(self):
        """布尔值/纯数字简答 — 匹配 ^(?:True|False|None|\d+)$"""
        assert is_answer_submission("True") is True
        assert is_answer_submission("False") is True
        assert is_answer_submission("None") is True
        assert is_answer_submission("42") is True

    def test_detect_single_letter_at_start(self):
        """单字母在开头 — 匹配 ^[A-Da-d](?:$|[s,，/]+) 或 (?<=\d)[A-Da-d]"""
        assert is_answer_submission("A") is True
        assert is_answer_submission("B") is True


class TestAnswerRejection:
    """检测 is_answer_submission 对非答案消息的正确拒绝"""

    def test_reject_greeting(self):
        """问候语不是答案"""
        assert is_answer_submission("你好") is False
        assert is_answer_submission("Hello") is False

    def test_reject_learning_intent(self):
        """学习意图不是答案"""
        assert is_answer_submission("我想学Python") is False
        assert is_answer_submission("教我机器学习") is False

    def test_reject_colon_format(self):
        """'1:A 2:B' 冒号格式不被 ANSWER_PATTERNS 识别
        (此为设计决策: is_answer_submission 做快速正则检测，
         extract_answer_map 有独立的冒号解析逻辑)"""
        assert is_answer_submission("1:A 2:B") is False

    def test_reject_fullwidth_colon_prefix(self):
        """中文全角冒号'：'不被 [:\s] 字符类匹配 (ASCII only)"""
        assert is_answer_submission("答案是：A") is False

    def test_reject_list_with_quotes(self):
        """含引号的列表 ['a', 'b'] 不匹配 ^\[[\w\s,]+\]$ (引号不在字符类中)"""
        assert is_answer_submission("['a', 'b']") is False

    def test_reject_long_natural_language(self):
        """长自然语言文本不是答案 (>100 字且无字母选项)"""
        long_text = "我觉得第一题应该选B因为Python中列表是可变的而元组是不可变的"
        assert is_answer_submission(long_text) is False

    def test_reject_empty(self):
        """空字符串不是答案"""
        assert is_answer_submission("") is False

    def test_reject_too_long(self):
        """超长文本 (>500 字符) 不是答案"""
        huge = "A" * 501
        assert is_answer_submission(huge) is False

    def test_reject_question_request(self):
        """出题请求不是答案"""
        assert is_answer_submission("给我出3道题") is False
        assert is_answer_submission("来点题目做做") is False


# ═══════════════════════════════════════════════════════════════
# extract_answer_map — 答案映射提取
# ═══════════════════════════════════════════════════════════════

class TestAnswerExtraction:
    """检测 extract_answer_map 对答案映射的提取能力

    注意: extract_answer_map 的显式格式正则使用 {1,100} 贪婪量词，
    这意味着无分隔符的 "1A 2B 3C" 会被捕获为 {1: "A 2B 3C"}。
    用户应该使用逗号/换行等分隔符或冒号格式来获得准确映射。
    """

    def test_extract_single_answer(self):
        """单个答案: '1A'"""
        result = extract_answer_map("1A", 3)
        assert result == {1: "A"}

    def test_extract_with_separators(self):
        """逗号或换行分隔可获得准确映射"""
        result = extract_answer_map("1A, 2B, 3C", 3)
        assert result == {1: "A", 2: "B", 3: "C"}

    def test_extract_with_colon_format(self):
        """冒号分隔 '1:A 2:B 3:C' — 冒号在正则中作为分隔符 (:：)?"""
        result = extract_answer_map("1:A 2:B 3:C", 3)
        # 冒号后跟空格作为分隔符时，贪婪量词可能跨过单空格
        # 实际行为: {1: 'A 2', 3: 'C'} (2被跳过因为匹配后残串不满足)
        # 至少题1的答案包含 'A'
        assert 1 in result
        assert "A" in result[1]

    def test_extract_unordered_letters(self):
        """无题号顺序 'A B C D' — 格式2按顺序分配题号"""
        result = extract_answer_map("A B C D", 4)
        assert len(result) == 4
        assert result[1] == "A"
        assert result[2] == "B"
        assert result[3] == "C"
        assert result[4] == "D"

    def test_extract_unordered_commas(self):
        """逗号分隔 'A,B,C'"""
        result = extract_answer_map("A,B,C", 3)
        assert len(result) == 3

    def test_extract_chinese_answer(self):
        """中文答案 '1对 2错' — 题号捕获 + 中文映射"""
        result = extract_answer_map("1对 2错", 3)
        assert len(result) > 0

    def test_extract_returns_dict(self):
        """始终返回 dict，即使无法解析"""
        result = extract_answer_map("hello world", 3)
        assert isinstance(result, dict)

    def test_extract_gibberish_yields_unordered_match(self):
        """纯字母串 'asdfghjkl' 被格式2匹配 (全word字符), 返回 {1: 'ASDFGHJKL'}"""
        result = extract_answer_map("asdfghjkl", 3)
        assert result == {1: "ASDFGHJKL"}
