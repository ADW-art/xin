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

    # -- 内容安全黑名单（中英文关键词）--
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

    # -- 教育场景特有的不适当内容 --
    UNSAFE_EDUCATION_PATTERNS = [
        r'(考试.*作弊|代考|替考|泄题|买.*答案)',
        r'(cheat.*exam|proxy.*test|buy.*answers|leak.*exam)',
    ]

    # -- 系统 prompt 泄漏检测 --
    SYSTEM_LEAK_PATTERNS = [
        # 画像采集任务标记（中括号中文格式）
        r'【画像采集任务[^】]*】',
        r'【画像补充任务[^】]*】',
        r'【画像软引导[^】]*】',
        r'【画像引导[^】]*】',
        # 系统指令泄露
        r'当前用户画像(缺失|还缺)[：:]\s*[^\n]+',
        r'你必须在回复的\*\*开头\*\*先自然地了解用户背景',
        r'示例回复结构[：:]\s*「',
        r'禁止[：:]\s*忽略此任务',
        # profile_collection 英文标记泄露
        r'\[system:\s*profile_collection[^\]]*\]',
        r'\[system:\s*profile_guide[^\]]*\]',
    ]

    # -- 教育领域白名单（这些领域的正常教学内容不应被拦截）--
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

    def _has_repetition(self, text: str) -> tuple[bool, Optional[str]]:
        """检测 LLM 输出中的退化重复 (参考 NVIDIA garak RepeatedToken)

        Returns:
            (has_repetition, warning_message)
        """
        if not text or len(text) < 60:
            return False, None
        match = self._repetition_phrase.search(text)
        if match:
            phrase = match.group(1)[:40]
            # P3-FIX: markdown 表格分隔行 (如 |------|------|) 中
            # 短模式 (如 "---------|") 会正常重复，不构成退化重复
            stripped = phrase.strip()
            if stripped and all(c in '|-: ' for c in stripped):
                pass  # 纯表格格式化字符，跳过
            else:
                logger.warning("ContentGuard: 检测到短语重复 '%s'...", phrase)
                return True, f"生成内容出现异常重复，已触发质量保护。"
        match = self._repetition_word.search(text)
        if match:
            word = match.group(1)
            logger.warning("ContentGuard: 检测到单词重复 '%s'...", word)
            return True, f"生成内容出现异常重复 '{word}'，已触发质量保护。"
        return False, None

    # -- 幻觉检测标志 --

    def __init__(self):
        self._compiled_safe = [re.compile(p, re.IGNORECASE) for p in self.UNSAFE_PATTERNS]
        self._compiled_edu = [re.compile(p, re.IGNORECASE) for p in self.UNSAFE_EDUCATION_PATTERNS]
        self._compiled_leak = [re.compile(p, re.IGNORECASE) for p in self.SYSTEM_LEAK_PATTERNS]
        # Compile hallucination patterns (was previously left as None)
        self._compiled_hallucination = [
            (re.compile(r'(?:Python|python)\s*(?:中|的|有一个|内置的函数叫|标准库中有)\s*`?(\w+)`?\s*(?:函数|方法|模块)', re.IGNORECASE), '可能编造了不存在的Python函数'),
            (re.compile(r'(?:根据|据|参考)\s*(?:[A-Z][a-z]+\s*(?:et\s*al\.?|和|and)\s*(?:19|20)\d{2})', re.IGNORECASE), '可能引用虚构的学术文献'),
            (re.compile(r'https?://(?!spark-api\.xf-yun\.com|(?:[a-zA-Z0-9-]+\.)*python\.org|github\.com|wikipedia\.org|developer\.mozilla\.org|stackoverflow\.com|pypi\.org)[a-zA-Z0-9.-]+\.[a-z]{2,}', re.IGNORECASE), '包含未经验证的外部链接'),
        ]
        # 重复检测: 参考 NVIDIA garak RepeatedToken detector
        # (.{10,100}?)\1{2,} — 10-100字符序列重复3+次
        # \b(\w+)(?:\s+\1){4,} — 单词重复5+次
        self._repetition_phrase = re.compile(r'(.{10,100}?)\1{2,}')
        self._repetition_word = re.compile(r'\b(\w{2,20})\b[,\s]*(\1[,\s]*){4,}', re.IGNORECASE)

    # -- 安全过滤 --
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

    # -- 防幻觉检测 --
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
        CRITICAL_PATTERNS = {"可能引用虚构的学术文献", "包含未经验证的外部链接"}

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

    # -- 学习计划输出检测 --
    # resource_agent 在非规划模式下不应输出完整的学习计划/课程表
    LEARNING_PLAN_PATTERNS = [
        # 多周/多天课程表结构 (两个或以上带编号的时间段)
        r'(?:第\s*[一二三四五六七八九十\d]+\s*[周天课节章步])[\s\S]{0,30}?(?:第\s*[一二三四五六七八九十\d]+\s*[周天课节章步])',
        # 独立的学习计划标题（允许标题标记和关键词之间有主题名）
        r'(?:^|\n)\s*#*\s*[^\n]{0,40}?(?:学习计划|课程大纲|教学计划|学习路线图|学习安排|课程表)',
        # 明显的多阶段课程结构 (>=2个阶段/模块)
        r'(?:第\s*[一二三四五六七八九十\d]+\s*(?:阶段|模块|单元|部分))[\s\S]{0,50}?(?:第\s*[一二三四五六七八九十\d]+\s*(?:阶段|模块|单元|部分))',
    ]

    def is_learning_plan_output(self, text: str) -> bool:
        """检测内容是否为学习计划/课程表（而非聚焦单知识点的教学资源）

        当 resource_agent 在教学模式下应输出单个知识点的讲解，
        但 LLM 可能错误地输出完整的课程计划。

        P3-FIX (2026-07-11): 降低激进程度，避免正常教学内容被误判。
        关键区分: 教学回复可以有编号列表(1. 主题 / 2. 主题), 但不能有时间结构(第X周/天/阶段)。
        - 时间编号(第X天/周/阶段/模块) >= 2 → 计划
        - 关键词 + 时间编号 → 计划
        - 关键词 + 顺序描述(先...再...最后...) → 计划
        - 仅内容编号(1. 2. 3.) 无时间结构 → NOT 计划(是教学内容)

        Returns:
            True 如果检测到计划模式（应拒绝/重新生成）
        """
        if not text or len(text) < 15:
            return False

        # 时间编号: 第X天/周/阶段/模块/单元/部分/课/节/章
        time_numbered = re.findall(
            r'第\s*[一二三四五六七八九十\d]+\s*(?:天|周|阶段|模块|单元|部分|课|节|章)', text
        )
        # >=2个时间编号 → 明显是计划
        if len(time_numbered) >= 2:
            return True

        # 关键词: 学习计划/课程大纲/教学计划等
        has_plan_keyword = bool(re.search(
            r'(?:学习计划|课程大纲|教学计划|学习路线图|学习安排|课程表)', text
        ))
        if not has_plan_keyword:
            return False

        # 关键词 + 至少2个时间编号 → 计划 (单个"第一阶段"提及可能只是引用上下文)
        if len(time_numbered) >= 2:
            return True

        # 关键词 + 顺序描述结构 (先...再...最后.../首先...然后.../第一步...第二步...)
        has_sequential = bool(re.search(
            r'先\s*.{1,20}\s*再\s*.{1,20}\s*(?:最后|然后)'
            r'|首先\s*.{1,20}\s*然后'
            r'|第一步\s*.{1,20}\s*第二步',
            text
        ))
        if has_sequential:
            return True

        # 关键词 + 多周引用 (为期X周 / X周课程)
        has_week_ref = bool(re.search(
            r'(?:为期|共计|总计|约)\s*[\d一二三四五六七八九十]+\s*[周个]'
            r'|[\d一二三四五六七八九十]+\s*周\s*(?:课程|计划|学习)',
            text
        ))
        if has_week_ref:
            return True

        # 仅有关键词但没有时间结构/顺序描述/多周引用 → 不触发
        # （例如: "以下是 Python 学习计划中的基础内容概述" + "1. 安装 Python\n2. 变量"）
        # 这是教学内容的结构化列表，不是学习计划
        return False

    # -- 综合检查 --
    def check(self, text: str) -> tuple[bool, Optional[str]]:
        """综合安全检查：安全过滤 + 防幻觉

        Returns:
            (passed, warning_or_none)
            passed=False 表示内容不应该展示
        """
        safe, warning = self.safety_check(text)
        if not safe:
            return False, warning

        repeat, r_warning = self._has_repetition(text)
        if repeat:
            return False, r_warning

        reliable, h_warning = self.hallucination_check(text)
        if not reliable:
            return False, h_warning

        return True, None

    # -- 系统 prompt 泄漏检测 --
    def system_leak_check(self, text: str) -> tuple[bool, Optional[str]]:
        """检测 LLM 输出中是否泄露了系统 prompt 内容

        Returns:
            (is_clean, leaked_pattern_or_none)
            is_clean=False 表示检测到泄露
        """
        if not text:
            return True, None
        for pattern in self._compiled_leak:
            match = pattern.search(text)
            if match:
                leaked = match.group(0)
                logger.warning("ContentGuard: 检测到系统 prompt 泄漏 '%s'", leaked[:60])
                return False, leaked
        return True, None

    def filter_leaked_content(self, text: str) -> str:
        """移除 LLM 输出中泄露的系统 prompt 片段

        用正则替换方式清除泄露文本，保留剩余的合法内容。
        """
        if not text:
            return text
        result = text
        for pattern in self._compiled_leak:
            result = pattern.sub("", result)
        import re as _re
        result = _re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()


# =============================================================
# 输出净化器（流式兼容）
# =============================================================

class StreamGuard:
    """流式内容守卫：逐块检测，累积到一定量后执行完整检查

    用于包裹 LLM 流式输出，确保不安全/幻觉内容被及时拦截。
    同时检测教学模式下 resource_agent 错误输出的学习计划。
    """

    def __init__(self, check_interval: int = 200):
        self._guard = ContentGuard()
        self._buffer = ""
        self._check_interval = check_interval
        self._blocked = False
        self._warning = None
        self._last_check_len = 0
        self._plan_detected = False

    def feed(self, chunk: str) -> str | None:
        """喂入一个chunk，返回应输出的内容（None表示此chunk应丢弃）"""
        if self._blocked or self._plan_detected:
            return None

        self._buffer += chunk

        # 每个chunk单独快速检查明显的不安全关键词
        chunk_safe, _ = self._guard.safety_check(chunk)
        if not chunk_safe:
            self._blocked = True
            self._warning = "检测到不安全内容"
            logger.warning("StreamGuard: chunk级不安全内容被拦截")
            return None

        # 系统 prompt 泄漏检测 — 逐块过滤
        chunk_clean, leaked = self._guard.system_leak_check(chunk)
        if not chunk_clean:
            logger.warning("StreamGuard: chunk级系统prompt泄漏已过滤 '%s'", str(leaked)[:60])
            filtered = self._guard.filter_leaked_content(chunk)
            if not filtered or not filtered.strip():
                return None
            self._buffer = self._buffer[:-len(chunk)] + filtered
            return filtered

        # 累积到检查间隔时执行完整检查（安全 + 幻觉 + 泄漏 + 学习计划）
        if len(self._buffer) - self._last_check_len >= self._check_interval:
            passed, warning = self._guard.check(self._buffer)
            if not passed:
                self._blocked = True
                self._warning = warning
                logger.warning("StreamGuard: 完整检查拦截: %s", warning)
                return None
            # 累积检查也检测系统泄漏（防止跨chunk边界泄漏逃逸）
            buf_clean, leaked_full = self._guard.system_leak_check(self._buffer)
            if not buf_clean:
                self._blocked = True
                self._warning = "检测到系统信息泄露"
                logger.warning("StreamGuard: 累积检查拦截系统泄漏: %s", str(leaked_full)[:80])
                return None
            if not self._plan_detected and self._guard.is_learning_plan_output(self._buffer):
                self._plan_detected = True
                logger.warning("StreamGuard: 检测到学习计划输出，阻断后续输出 (len=%d)", len(self._buffer))
                return None
            self._last_check_len = len(self._buffer)

        return chunk

    def finalize(self) -> bool:
        """流式完成后调用，对完整缓冲区执行全面检查（安全 + 泄漏 + 学习计划）

        Returns:
            True 如果检测到学习计划（调用方应使用 get_safe_content 替换输出）
        """
        if not self._blocked:
            # 完整缓冲区安全 + 幻觉检查
            passed, warning = self._guard.check(self._buffer)
            if not passed:
                self._blocked = True
                self._warning = warning
                logger.warning("StreamGuard: finalize 安全拦截: %s", warning)
            # 完整缓冲区系统泄漏检查（防止跨chunk边界泄漏逃逸）
            if not self._blocked:
                buf_clean, leaked_full = self._guard.system_leak_check(self._buffer)
                if not buf_clean:
                    self._blocked = True
                    self._warning = "检测到系统信息泄露"
                    logger.warning("StreamGuard: finalize 拦截系统泄漏: %s", str(leaked_full)[:80])
            # 学习计划检测
            if not self._blocked and not self._plan_detected:
                if self._guard.is_learning_plan_output(self._buffer):
                    self._plan_detected = True
                    logger.warning("StreamGuard: finalize 检测到学习计划输出 (len=%d)", len(self._buffer))
        return self._plan_detected

    @property
    def blocked(self) -> bool:
        return self._blocked

    @property
    def plan_detected(self) -> bool:
        return self._plan_detected

    @property
    def warning(self) -> Optional[str]:
        return self._warning

    def get_safe_content(self) -> str:
        """返回已通过检查的安全内容"""
        if self._blocked:
            return (
                "抱歉，检测到生成内容可能存在不准确或不适当的信息。\n\n"
                "建议您换个提问方式重新尝试，或者尝试以下操作：\n"
                "- 指定具体的学习知识点\n"
                "- 让我出几道练习题\n"
                "- 制定学习计划"
            )
        if self._plan_detected:
            return (
                "抱歉，生成的内容格式不符合当前教学模式要求。\n\n"
                "正在为您重新生成聚焦于该知识点的讲解内容，请稍候..."
            )
        return self._buffer

    def reset(self):
        self._buffer = ""
        self._blocked = False
        self._warning = None
        self._last_check_len = 0
        self._plan_detected = False


# =============================================================
# 模块级单例
# =============================================================

_guard_instance: Optional[ContentGuard] = None


def get_guard() -> ContentGuard:
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = ContentGuard()
    return _guard_instance
