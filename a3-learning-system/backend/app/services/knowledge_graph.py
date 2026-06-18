"""
知识图谱 + 拓扑路径规划

自研算法模块。
从教材中提取知识点 → 共现分析构建依赖图 → 拓扑排序输出最优学习顺序。
相比纯 LLM "猜"学习路线，知识图谱更可靠、可解释。

算法流程：
  1. 从教材文本中提取知识点（TF-IDF 关键词提取）
  2. 统计知识点在文本中的共现关系和前后位置
  3. 构建有向无环图（DAG）：频繁共现且 A 出现早于 B → A 是 B 的前置知识
  4. 拓扑排序 → 最优学习顺序
  5. 根据用户画像的 weekly_hours 计算时间分配
"""
import logging
import re
from collections import defaultdict

logger = logging.getLogger(__name__)

# 英文停用词
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "shall", "should",
    "may", "might", "must", "can", "could", "it", "its", "of", "for", "in", "on",
    "at", "to", "from", "by", "with", "about", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "and", "but", "or", "nor",
    "not", "so", "yet", "both", "either", "neither", "each", "every", "all",
    "this", "that", "these", "those", "which", "what", "who", "whom", "whose",
    "how", "why", "when", "where", "if", "then", "else", "than", "too", "very",
    "just", "only", "also", "such", "other", "more", "some", "any", "one", "two",
    "use", "used", "using", "get", "set", "let", "like", "make", "made",
    "work", "works", "need", "needs", "way", "ways", "new", "old", "see",
    "know", "known", "first", "last", "part", "type", "types", "name", "call",
    "called", "code", "data", "value", "values", "return", "returns",
    "write", "run", "running", "define", "defined", "here", "now", "does",
    "many", "much", "over", "under", "well", "same",
    # 中文常见噪音词
    "一个", "可以", "这个", "那个", "我们", "他们", "什么", "怎么", "为什么",
    "不是", "但是", "因为", "所以", "如果", "虽然", "而且", "或者", "然后",
    "已经", "正在", "没有", "所有", "每个", "一些", "这样", "那样", "这些",
    "那些", "自己", "它们", "就是", "只是", "这里", "那里", "问题", "使用",
    "现在", "需要", "应该", "能够", "通过", "进行", "对于", "作为", "由于",
    "用于", "其中", "其他", "一种", "以及", "知道", "看到", "出来", "起来",
    "来说", "对于", "在于", "属于", "有关", "不同", "时候", "就是", "并且",
    "可能", "之间", "一定", "只有", "总是", "任何", "一样", "基本", "比较",
    "表示", "称为", "定义", "如下", "上面", "下面", "前面", "后面", "之间",
    "也就是说", "例如", "比如", "包括", "除了", "关于", "等等", "之类",
    "标号", "次移动", "个区域", "第一次", "第二次", "第三次", "最后",
}
MIN_WORD_LEN = 2


class KnowledgeGraph:
    """知识点依赖图谱"""

    def __init__(self):
        self.edges: dict[str, set[str]] = defaultdict(set)     # 前置 → 后置
        self.in_degree: dict[str, int] = defaultdict(int)       # 入度（有多少前置）
        self.nodes: set[str] = set()                             # 所有知识点
        self.keyword_weights: dict[str, float] = {}              # TF-IDF 权重（简化版）

    def extract_keywords(self, text: str, top_n: int = 15) -> list[tuple[str, float]]:
        """从文本中提取知识点关键词（简化 TF-IDF）

        用词频 + 位置加权代替完整的 TF-IDF。
        标题中的词权重 ×3，首段 ×2。
        """
        lines = text.split("\n")
        word_count: dict[str, float] = defaultdict(float)

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            # 用 jieba 分词提取中文词（效果远好于正则）
            try:
                import jieba
                chinese_words = [w for w in jieba.lcut(line) if len(w) >= 2 and not w.isspace()]
            except ImportError:
                chinese_words = re.findall(r'[一-鿿]{2,}', line)
            english_words = re.findall(r'[a-zA-Z_]\w+', line)
            words = chinese_words + english_words
            weight = 1.0
            if line.startswith("#"):
                weight = 3.0   # 标题权重最高
            elif i < 3:
                weight = 2.0   # 首段次高

            for w in words:
                wl = w.lower()
                if len(wl) < MIN_WORD_LEN or wl in STOP_WORDS:
                    continue
                word_count[wl] += weight

        # 排序取 top_n
        ranked = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
        result = ranked[:top_n]
        for kw, w in result:
            self.keyword_weights[kw] = w
            self.nodes.add(kw)
        return result

    def build_from_texts(self, texts: list[dict]):
        """从多篇文本构建知识点图谱

        texts: [{"title": "...", "content": "..."}, ...]
        """
        # 1. 提取所有知识点
        all_keywords: set[str] = set()
        for t in texts:
            kws = self.extract_keywords(t["content"])
            for kw, _ in kws:
                all_keywords.add(kw)

        # 2. 分析共现和位置关系
        for t in texts:
            content = t["content"]
            paragraphs = content.split("\n\n")
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                # 找出段落中出现的知识点
                present = [kw for kw in all_keywords if kw.lower() in para.lower()]
                # 按出现顺序排列
                present_sorted = sorted(present, key=lambda k: para.lower().index(k.lower()))
                # 建立依赖边（先出现的 → 后出现的）
                for i in range(len(present_sorted)):
                    for j in range(i + 1, len(present_sorted)):
                        a, b = present_sorted[i], present_sorted[j]
                        if b not in self.edges[a]:
                            self.edges[a].add(b)
                            self.in_degree[b] += 1
                            self.in_degree.setdefault(a, 0)
                            logger.debug("KG: %s → %s", a, b)

        logger.info("KG: 构建完成 nodes=%d edges=%d", len(self.nodes), sum(len(e) for e in self.edges.values()))

    def topological_sort(self, known_topics: set[str] = None) -> list[list[str]]:
        """拓扑排序，返回分阶段的学习路径

        known_topics: 用户已掌握的知识点集合
        返回：[[阶段1知识点], [阶段2知识点], ...]
        """
        known = known_topics or set()

        # 计算入度（跳过已掌握的知识点）
        in_deg = {n: d for n, d in self.in_degree.items()}
        # 移除已掌握的入度贡献
        for known_node in known:
            if known_node in self.edges:
                for neighbor in self.edges[known_node]:
                    if neighbor in in_deg:
                        in_deg[neighbor] = max(0, in_deg[neighbor] - 1)

        phases = []
        remaining = set(self.nodes) - known

        while remaining:
            # 找出所有入度为 0 的节点
            current = [n for n in remaining if in_deg.get(n, 0) == 0]
            if not current:
                # 有环 → 选入度最小的
                min_deg = min(in_deg.get(n, 0) for n in remaining)
                current = [n for n in remaining if in_deg.get(n, 0) == min_deg]
                logger.warning("KG: 检测到循环依赖，取入度最小层=%d 共%d个节点", min_deg, len(current))
            phases.append(sorted(current, key=lambda k: -self.keyword_weights.get(k, 0)))

            # 移出这些节点，更新入度
            for node in current:
                remaining.discard(node)
                if node in self.edges:
                    for neighbor in self.edges[node]:
                        if neighbor in in_deg:
                            in_deg[neighbor] -= 1

        return phases

    def estimate_time(self, phases: list[list[str]], weekly_hours: float) -> list[dict]:
        """估算每个阶段的学习时间

        每个知识点约需 1-2 小时，每阶段包含 group 讨论和练习
        """
        result = []
        week_hours_per_phase = weekly_hours / max(len(phases), 1)

        for i, phase in enumerate(phases):
            topic_hours = len(phase) * 1.5
            weeks = max(1, round(topic_hours / max(week_hours_per_phase, 1)))
            result.append({
                "phase": i + 1,
                "topics": phase,
                "estimated_hours": round(topic_hours, 1),
                "estimated_weeks": weeks,
                "milestone": f"第 {i + 1} 阶段完成：掌握 {'、'.join(phase[:3])}等 {len(phase)} 个知识点",
            })

        return result


# 模块级单例
_graph: KnowledgeGraph | None = None


def get_graph() -> KnowledgeGraph:
    """获取知识图谱单例"""
    global _graph
    if _graph is None:
        _graph = KnowledgeGraph()
    return _graph
