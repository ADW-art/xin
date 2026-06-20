"""
内容安全守卫（Content Safety Guard）

竞赛要求"防幻觉"与"内容安全过滤机制":
  1. 安全过滤 — 检测并屏蔽不当内容（暴力/色情/政治敏感/违法）
  2. 防幻觉 — 当生成内容与知识库严重不符时，标记警告并降级为基于知识的回复

使用方式:
  from app.utils.content_guard import ContentGuard
  guard = ContentGuard()
  safe, warning = guard.check(text)
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ContentGuard:
    """内容安全守卫：安全过滤 + 幻觉检测"""

    # ── 内容安全黑名单（中英文关键词）──
    UNSAFE_PATTERNS = [
        # 暴力/自残
        r'(自杀|杀人|谋杀|爆炸物|制作炸弹|枪支|武器制造)',
        r'(kill|murder|suicide|bomb|terrorist|weapon)',
        # 色情
        r'(色情|成人内容|裸照|性交|淫秽|情色)',
        r'\b(porn|adult content|explicit|obscene)\b',
        # 政治敏感
        r'(颠覆|政变|暴动|独立运动|分裂|邪教|法轮功)',
        r'(overthrow|regime change|coup|secession|cult)',
        # 违法
        r'(黑客.*攻击|破解.*密码|入侵.*系统|DDoS|木马|病毒.*传播)',
        r'(hack.*attack|crack.*password|ddos|malware.*spread)',
        # 赌博/毒品
        r'(赌博|博彩|赌场|毒品|吸毒|大麻|海洛因)',
        r'(gambling|casino|drugs|cocaine|heroin|marijuana)',
    ]

    # ── 教育场景特有的不适当内容 ──
    UNSAFE_EDUCATION_PATTERNS = [
        r'(考试.*作弊|代考|替考|泄题|买.*答案)',
        r'(cheat.*exam|proxy.*test|buy.*answers|leak.*exam)',
    ]

    # ── 教育领域白名单（这些领域的正常教学内容不应被拦截）──
    EDU_DOMAIN_PATTERNS = [
        r'(?:Python|Java|C\+\+|Go|Rust|JavaScript|TypeScript|算法|数据结构|计算机|编程|网络|数据库|机器学习|深度学习|人工智能|数学|物理|化学)',
        r'(?:def |class |import |function|variable|loop|recursion|closure|decorator|generator|iterator|lambda)',
        r'(?:闭包|装饰器|生成器|迭代器|列表推导|字典|集合|元组|数组|链表|栈|队列|树|图|排序|搜索|递归|动态规划|贪心)',
        r'(?:前端|后端|全栈|API|REST|HTTP|TCP|UDP|DNS|SSL|TLS|Docker|Kubernetes|Git|Linux|Windows|MacOS)',
    ]

    def is_education_domain(self, text: str) -> bool:
        """检查文本是否属于教育/技术领域"""
        if not text:
            return False
        for pattern in self.EDU_DOMAIN_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    # ── 幻觉检测标志 ──
    HALLUCINATION_SIGNALS = [
        # 伪造Python函数
        (r'(?:Python|python)\s*(?:中|的|有一个|内置的函数叫|标准库中有)\s*`?(\w+)`?\s*(?:函数|方法|模块)', None),
        # 不存在的学术引用
        (r'(?:根据|据|参考)\s*(?:[A-Z][a-z]+\s*(?:et\s*al\.?|和|and)\s*(?:19|20)\d{2})', None),
        # 伪造URL
        (r'https?://(?!spark-api\.xf-yun\.com|docs\.python\.org|github\.com|wikipedia\.org)[a-zA-Z0-9.-]+\.[a-z]{2,}', None),
    ]

    def __init__(self):
        self._compiled_safe = [re.compile(p, re.IGNORECASE) for p in self.UNSAFE_PATTERNS]
        self._compiled_edu = [re.compile(p, re.IGNORECASE) for p in self.UNSAFE_EDUCATION_PATTERNS]
        # Compile hallucination patterns (was previously left as None)
        self._compiled_hallucination = [
            (re.compile(r'(?:Python|python)\s*(?:中|的|有一个|内置的函数叫|标准库中有)\s*`?(\w+)`?\s*(?:函数|方法|模块)'), '可能编造了不存在的Python函数'),
            (re.compile(r'(?:根据|据|参考)\s*(?:[A-Z][a-z]+\s*(?:et\s*al\.?|和|and)\s*(?:19|20)\d{2})'), '可能引用虚构的学术文献'),
            (re.compile(r'https?://(?!spark-api\.xf-yun\.com|docs\.python\.org|github\.com|wikipedia\.org|developer\.mozilla\.org|stackoverflow\.com|pypi\.org)[a-zA-Z0-9.-]+\.[a-z]{2,}'), '包含未经验证的外部链接'),
        ]

    # ── 安全过滤 ──
    def safety_check(self, text: str) -> tuple[bool, Optional[str]]:
        """内容安全检查

        Returns:
            (is_safe, warning_message)
            is_safe=False 表示检测到不安全内容
        """
        if not text or len(text.strip()) < 3:
            return True, None

        # 检查通用不安全模式
        for pattern in self._compiled_safe:
            match = pattern.search(text)
            if match:
                keyword = match.group(0)
                logger.warning("ContentGuard: 检测到不安全内容 '%s'", keyword)
                return False, f"内容安全过滤：检测到不当关键词 '{keyword}'，已屏蔽相关内容。"

        # 检查教育场景特有模式
        for pattern in self._compiled_edu:
            match = pattern.search(text)
            if match:
                keyword = match.group(0)
                logger.warning("ContentGuard: 检测到教育场景不当内容 '%s'", keyword)
                return False, f"内容安全过滤：检测到违反学术诚信的内容 '{keyword}'。"

        return True, None

    # ── 防幻觉检测 ──
    def hallucination_check(self, text: str) -> tuple[bool, Optional[str]]:
        """检测生成的文本是否存在幻觉（编造不存在的事实）

        分级处理：
        - 伪造引用/URL → 始终阻断（严重幻觉）
        - 伪造函数名 → 教育内容仅警告，非教育内容阻断
        """
        if not text:
            return True, None

        is_edu = self.is_education_domain(text)
        # 总是阻断的严重幻觉模式
        CRITICAL_PATTERNS = {"伪造学术引用", "伪造外部URL"}

        for pattern, desc in self._compiled_hallucination:
            match = pattern.search(text)
            if match:
                detail = match.group(1) if match.groups() else match.group(0)
                if desc in CRITICAL_PATTERNS:
                    # 伪造引用/URL → 无论什么领域都阻断
                    logger.warning("ContentGuard: 严重幻觉阻断 '%s': %s", desc, detail[:80])
                    return False, f"内容审核：{desc} '{detail[:60]}'，请验证信息准确性。"
                if is_edu:
                    # 教育内容的伪造函数名 → 仅警告
                    logger.info("ContentGuard: 教育领域疑似幻觉(仅warn): %s: %s", desc, detail[:80])
                    return True, None
                logger.warning("ContentGuard: 疑似幻觉 '%s': %s", desc, detail[:80])
                return False, f"内容审核：{desc} '{detail[:60]}'，请验证信息准确性。"

        return True, None

    # ── 综合检查 ──
    def check(self, text: str) -> tuple[bool, Optional[str]]:
        """综合安全检查：安全过滤 + 防幻觉

        Returns:
            (passed, warning_or_none)
            passed=False 表示内容不应该展示
        """
        safe, warning = self.safety_check(text)
        if not safe:
            return False, warning

        reliable, h_warning = self.hallucination_check(text)
        if not reliable:
            return False, h_warning

        return True, None


# ═══════════════════════════════════════════════════════════
# 输出净化器（流式兼容）
# ═══════════════════════════════════════════════════════════

class StreamGuard:
    """流式内容守卫：逐块检测，累积到一定量后执行完整检查

    用于包裹 LLM 流式输出，确保不安全/幻觉内容被及时拦截。
    """

    def __init__(self, check_interval: int = 200):
        self._guard = ContentGuard()
        self._buffer = ""
        self._check_interval = check_interval
        self._blocked = False
        self._warning = None
        self._last_check_len = 0

    def feed(self, chunk: str) -> str | None:
        """喂入一个chunk，返回应输出的内容（None表示此chunk应丢弃）"""
        if self._blocked:
            return None

        self._buffer += chunk

        # 每个chunk单独快速检查明显的不安全关键词
        chunk_safe, _ = self._guard.safety_check(chunk)
        if not chunk_safe:
            self._blocked = True
            self._warning = "检测到不安全内容"
            logger.warning("StreamGuard: chunk级不安全内容被拦截")
            return None

        # 累积到检查间隔时执行完整检查（含幻觉检测）
        if len(self._buffer) - self._last_check_len >= self._check_interval:
            passed, warning = self._guard.check(self._buffer)
            if not passed:
                self._blocked = True
                self._warning = warning
                logger.warning("StreamGuard: 完整检查拦截: %s", warning)
                return None
            self._last_check_len = len(self._buffer)

        return chunk

    @property
    def blocked(self) -> bool:
        return self._blocked

    @property
    def warning(self) -> Optional[str]:
        return self._warning

    def get_safe_content(self) -> str:
        """返回已通过检查的安全内容"""
        if self._blocked:
            safe_msg = (
                "抱歉，检测到生成内容可能存在不准确或不适当的信息。\n\n"
                "建议您换个提问方式重新尝试，或者尝试以下操作：\n"
                "- 指定具体的学习知识点\n"
                "- 让我出几道练习题\n"
                "- 制定学习计划"
            )
            return safe_msg
        return self._buffer

    def reset(self):
        self._buffer = ""
        self._blocked = False
        self._warning = None
        self._last_check_len = 0


# ═══════════════════════════════════════════════════════════
# 模块级单例
# ═══════════════════════════════════════════════════════════

_guard_instance: Optional[ContentGuard] = None


def get_guard() -> ContentGuard:
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = ContentGuard()
    return _guard_instance
