"""
知识图谱治理模块 — 将 TF-IDF 原始词 → 教育学知识点

对 knowledge_graph.json 进行后处理：
  1. 过滤停用词/数字/短词/非教学词
  2. 将原始关键词映射为标准知识点名称
  3. 去重合并
  4. 输出可展示的知识图谱
"""

import json
import os
import re
import logging

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# 停用词表（非教学意义的通用词/符号/数字）
# ═══════════════════════════════════════════════════════════
STOP_WORDS = {
    # 中文停用词
    "那么", "以及", "形式", "介绍", "得到", "证明", "情形", "因此",
    "区域", "封闭", "本书", "本书", "移动", "目标", "标准", "查找",
    "时间", "元素", "语言", "程序", "代码", "文件", "运行",
    # 英文/符号停用词
    "windows", "int", "++", "book", "head", "http", "include",
    "log", "top", "tail", "life", "stdio", "unix",
    # 数字/代码
    "2m", "2n", "10", "q1", "直线", "圆盘",
}


# ═══════════════════════════════════════════════════════════
# 知识点映射表（原始 TF-IDF 词 → 标准知识点名称）
# ═══════════════════════════════════════════════════════════
KNOWLEDGE_MAP = {
    # 数据结构
    "排序": "排序算法",
    "二分": "二分查找",
    "链表": "链表",
    "数组": "数组",
    "列表": "列表",
    "队列": "队列",
    "递归": "递归算法",
    # 算法
    "算法": "算法基础",
    "约瑟夫": "约瑟夫问题",
    # 编程语言
    "c语言": "C语言基础",
    "编译器": "编译原理",
    "编程": "编程基础",
    # 计算机系统
    "计算机": "计算机系统",
    "系统": "操作系统",
    # 函数
    "函数": "函数与模块",
}

# 标准化：如果不在映射表中但也不是停用词，保持原词
# 这些是有意义但不需要改名的词：如 "队列"→"队列"

# ═══════════════════════════════════════════════════════════
# 必须包含的核心知识点（从教材推断 + 手动补充）
# 用于丰富被过滤掉的图谱
# ═══════════════════════════════════════════════════════════
CORE_KNOWLEDGE_POINTS = [
    # Python 核心
    "Python基础", "变量与类型", "运算符", "流程控制",
    "函数与模块", "面向对象", "继承与多态",
    "列表与元组", "字典与集合", "字符串处理",
    "列表推导式", "生成器", "迭代器", "装饰器",
    "异常处理", "文件操作", "正则表达式",
    # 数据结构
    "数组", "链表", "栈", "队列", "树", "图",
    "排序算法", "查找算法", "哈希表", "递归算法",
    # 算法
    "算法基础", "时间复杂度", "动态规划", "贪心算法",
    "二分查找", "深度优先搜索", "广度优先搜索",
    # 计算机基础
    "操作系统", "计算机网络", "数据库基础", "编译原理",
    "计算机组成", "C语言基础", "编程基础",
]


def _is_valid_concept(word: str) -> bool:
    """判断是否为有效知识点"""
    if not word or len(word) < 2:
        return False
    if word in STOP_WORDS:
        return False
    if re.match(r'^[\d\W]+$', word):  # 纯数字/符号
        return False
    if re.match(r'^[a-z]{1,3}$', word, re.IGNORECASE):  # 短英文缩写 (int, log, top)
        return False
    return True


def _normalize_concept(word: str) -> str:
    """将原始词映射为标准知识点名称"""
    if word in KNOWLEDGE_MAP:
        return KNOWLEDGE_MAP[word]
    return word


def govern_knowledge_graph(input_path: str, output_path: str = None) -> dict:
    """治理知识图谱 JSON

    Args:
        input_path: 原始 knowledge_graph.json 路径
        output_path: 输出路径 (可选)

    Returns:
        治理后的图谱 dict
    """
    if not os.path.exists(input_path):
        logger.warning("知识图谱文件不存在: %s", input_path)
        return {"nodes": [], "edges": [], "nodes_count": 0, "edges_count": 0}

    with open(input_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    raw_nodes = raw.get("nodes", [])
    raw_edges = raw.get("edges", [])

    # ── 1. 过滤 + 映射节点 ──
    seen = set()
    governed_nodes = []

    # 先添加核心知识点（保证展示质量）
    for cp in CORE_KNOWLEDGE_POINTS:
        if cp not in seen:
            governed_nodes.append({"name": cp, "weight": 1.0, "source": "curated"})
            seen.add(cp)

    # 再添加过滤后的原始节点
    for n in raw_nodes:
        name = n if isinstance(n, str) else n.get("name", "")
        if not _is_valid_concept(name):
            continue
        normalized = _normalize_concept(name)
        if normalized not in seen:
            governed_nodes.append({"name": normalized, "weight": 0.5, "source": "tfidf"})
            seen.add(normalized)

    # ── 2. 过滤边（edges 是 dict: {source: [targets]}） ──
    valid_names = {n["name"] for n in governed_nodes}
    governed_edges = []
    raw_name_map = {}
    for n in raw_nodes:
        raw = n if isinstance(n, str) else n.get("name", "")
        if _is_valid_concept(raw):
            raw_name_map[raw] = _normalize_concept(raw)

    if isinstance(raw_edges, dict):
        for src_raw, targets in raw_edges.items():
            src_norm = raw_name_map.get(src_raw, _normalize_concept(src_raw))
            if src_norm not in valid_names:
                continue
            for tgt_raw in (targets if isinstance(targets, list) else []):
                tgt_norm = raw_name_map.get(tgt_raw, _normalize_concept(tgt_raw))
                if tgt_norm in valid_names and src_norm != tgt_norm:
                    governed_edges.append({
                        "source": src_norm,
                        "target": tgt_norm,
                    })

    # ── 3. 注入 CS 前置依赖边（教育学期望的依赖关系） ──
    # TF-IDF 共现无法推导真实的前置关系，需要手动补充 CS 课程依赖
    CS_PREREQUISITES = [
        # Python 学习路线
        ("Python基础", "变量与类型"),
        ("变量与类型", "运算符"),
        ("运算符", "流程控制"),
        ("流程控制", "函数与模块"),
        ("函数与模块", "面向对象"),
        ("面向对象", "继承与多态"),
        ("函数与模块", "装饰器"),
        ("面向对象", "装饰器"),
        ("流程控制", "列表与元组"),
        ("列表与元组", "列表推导式"),
        ("列表推导式", "生成器"),
        ("生成器", "迭代器"),
        ("函数与模块", "异常处理"),
        ("函数与模块", "文件操作"),
        ("字符串处理", "正则表达式"),
        # 数据结构路线
        ("数组", "链表"),
        ("链表", "栈"),
        ("栈", "队列"),
        ("链表", "树"),
        ("树", "图"),
        ("数组", "排序算法"),
        ("链表", "查找算法"),
        ("查找算法", "哈希表"),
        ("递归算法", "动态规划"),
        ("排序算法", "算法基础"),
        ("查找算法", "算法基础"),
        ("算法基础", "时间复杂度"),
        ("时间复杂度", "动态规划"),
        # CS 基础路线
        ("C语言基础", "编程基础"),
        ("编程基础", "Python基础"),
        ("计算机组成", "操作系统"),
        ("操作系统", "计算机网络"),
        ("操作系统", "编译原理"),
    ]
    valid_names = {n["name"] for n in governed_nodes}
    for src, tgt in CS_PREREQUISITES:
        if src in valid_names and tgt in valid_names and src != tgt:
            governed_edges.append({"source": src, "target": tgt, "weight": 1.0})

    result = {
        "nodes": governed_nodes,
        "edges": governed_edges,
        "nodes_count": len(governed_nodes),
        "edges_count": len(governed_edges),
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info("治理后知识图谱已保存: %s (nodes=%d, edges=%d)",
                    output_path, len(governed_nodes), len(governed_edges))

    return result


if __name__ == "__main__":
    # 直接运行：治理知识图谱
    base = os.path.dirname(os.path.abspath(__file__))
    input_path = os.path.join(base, "..", "..", "..", "docs", "knowledge_graph.json")
    output_path = os.path.join(base, "..", "..", "..", "docs", "knowledge_graph_governed.json")

    result = govern_knowledge_graph(input_path, output_path)
    print(f"治理前: 55 nodes, 1580 edges")
    print(f"治理后: {result['nodes_count']} nodes, {result['edges_count']} edges")
    print(f"节点样例:")
    for n in result["nodes"][:15]:
        print(f"  {n['name']} (source={n['source']})")
