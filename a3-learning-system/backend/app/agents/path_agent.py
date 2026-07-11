"""
Path Agent — 学习路径规划 + 教学流程引擎

双模式:
1. 规划模式 (原): 根据画像 + KG 生成完整学习路径计划
2. 教学模式 (新): 逐节点教学 → 用户确认 → 下一个节点 (KG-Node Teaching Flow)

教学模式流程:
  - init_teaching: 构建 KG 拓扑序列 → 设置 teaching_context → 交棒 resource_agent
  - teaching_continue: 推进索引 → 下一节点 → 交棒 resource_agent
  - 全部完成: 模式 → completed + 祝贺
"""

import re
import logging
from datetime import datetime, timedelta

from app.agents.state import AgentState
from app.agents._msg_compat import last_msg_content  # 兼容 checkpoint 恢复后 dict 格式
from app.agents._teaching_gate import should_init_teaching  # P0-B 2026-07-11
from app.services.bkt_service import get_tracker
from app.services.dynamic_path_planner import build_planner_from_db
from app.services.knowledge_graph import get_graph
from app.services.rag_service import search_knowledge
from app.services.review_scheduler import get_scheduler, INTERVALS
from app.services.spark_client import SparkClient

logger = logging.getLogger(__name__)

PATH_PROMPT = """你是一个学习路径规划专家，风格对标 Coursera 课程大纲 + roadmap.sh。

## 学生画像
- 知识基础：{knowledge_base}
- 学习目标：{learning_goal}
- 每周可投入：{weekly_hours} 小时

## 当前需求
{topic}

## 可用知识点（知识图谱节点 — 必须从中选择，禁止编造）
{kg_nodes}

## 反幻觉铁律（违反即不合格，输出将被丢弃）
1. 禁止编造不在上述KG节点列表中的知识点 — 所有建议知识点必须来自KG，任意一个不在KG中的知识点将导致整条输出被丢弃
2. 禁止编造虚假的时间估算 — 每阶段时长必须基于 weekly_hours 和节点数计算
3. 禁止凭空推荐外部资源 — 不推荐具体书籍/课程/网站（KG可能没有这些数据）
4. 禁止捏造知识点间的依赖关系 — 前置依赖必须来自KG的edges数据

## 规划要求（必须完整输出以下5个部分，缺一不可）

### 1. 当前水平诊断
- 基于知识基础，明确列出已掌握知识点和待学习知识点
- 标注技能缺口（目标要求 vs 当前具备的技能）
- 给出量化水平评估（如"Python 基础：掌握率约 X%，距目标还差 Y 个核心知识点"）
- 禁止空泛："你有一定基础" → 必须说清"你已掌握列表/字典/函数，但缺少面向对象和异常处理"

### 2. 分阶段学习路线
用 Markdown 表格呈现（不是列表），每阶段一行：
| 阶段 | 主题 | 核心知识点(至少3个) | 建议时长 | 前置依赖 | 检验标准 |
|------|------|-------------------|----------|---------|---------|
| 1 | XXX | A, B, C | X小时 | 无 | 用XX实现YY |

要求：
- 至少3个阶段，最多7个阶段
- 每阶段核心知识点至少3个，必须是具体技术术语（不能是"基础""入门"等模糊词）
- 前置知识必须排在前面（拓扑顺序）
- 每个阶段末尾有具体可验证的检验标准

### 3. 时间估算
- 基于每周 {weekly_hours} 小时，计算每个阶段需要的日历周数
- 给出总工时和总周数
- 标注时间弹性（±X周），考虑复习和消化时间

### 4. 复习节点
- 在每个阶段的关键知识点上标注艾宾浩斯复习时间点（学完第1/3/7/14天）
- 用清单列出未来30天每天的复习任务（知识点 + 预计分钟数）

### 5. 里程碑与检验
每阶段的检验标准必须是可验证、可量化的：
- 禁止："掌握列表操作" → 允许："完成 LeetCode 第88、283、26题（列表相关），正确率 >= 80%"
- 禁止："理解面向对象" → 允许："用面向对象方式实现学生管理系统（CRUD），代码 >= 100 行"

## 输出格式
- 用 Markdown 标题和表格组织，表格必须有具体数据，不能留空
- 语言专业但不生硬，像导师给学生量身定制备考计划
- 如果对话历史中有排除约束或语言偏好，必须严格遵守，只规划允许范围内的内容

---

## 画像缺失处理（系统内部指令，不要输出给用户）

当知识基础、学习目标、每周投入中**任一项为空或"未填写"时**，你必须做到：

1. **绝对不能给出空泛建议** — 禁止输出"先巩固基础""逐步学进阶""通过练习巩固"等无具体知识点的空话
2. **必须诚实告知数据不足** — 用1句话说清缺少什么信息，例如"我还不太了解你的编程基础和目标，方便说一下吗？"
3. **基于KG数据给出初步建议** — 即使画像为空，KG拓扑排序结果仍然可用。基于KG输出一个**具体的最小路径**（至少展示阶段1的3个具体知识点名称+预计时间）
4. **禁止假装知道学生水平** — 禁止说"你有一定基础""你已掌握XXX"，因为你不知道

示例（画像全空但有KG数据）：
```
我还不太了解你的编程基础和每周可投入时间。基于Python知识图谱，我为你规划了一个通用的入门路径作为参考：

| 阶段 | 主题 | 核心知识点 | 建议时长 | 前置依赖 | 检验标准 |
|------|------|-----------|---------|---------|---------|
| 1 | Python基础语法 | 变量与数据类型、条件判断、循环 | 9h (约2周) | 无 | 用循环+条件写一个猜数字游戏 |
| 2 | 函数与模块 | 函数定义/参数/返回值、模块导入 | 9h (约2周) | 阶段1 | 用函数重构阶段1的猜数字游戏 |
| ... |

> 要给你生成更精准的个人化路径吗？只需要告诉我你每周能学多久、目标是什么就行。
```

**主动引导（用 > 引用格式，只加1句）**：
- 用户准备开始时：> 规划好了！要从第1阶段「XXX」开始吗？我现在就可以带你学第一个知识点。
- 计划较长时：> 这个计划总计 X 周。想先试一周看看节奏是否合适吗？
- 画像缺失时：> 告诉我你的编程基础和每周学习时间，我可以给你更精准的规划。
- 用户可能想调整时：> 觉得哪个阶段难度或时间需要调整？我可以实时修改。

---

## 示例（标准规划报告模板）
以下是一个合格的 path_agent 回复示例（假设画像已填写，KG有数据）：

我已经根据你的知识基础和Python知识图谱，规划了以下学习路径：

### 1. 当前水平诊断
已掌握：变量与数据类型, 条件判断, 循环(p>0.85)。技能缺口：缺少函数抽象能力，未接触面向对象编程。当前Python基础掌握率约35%，距入门水平还差7个核心知识点。

### 2. 分阶段学习路线

| 阶段 | 主题 | 核心知识点 | 建议时长 | 前置依赖 | 检验标准 |
|------|------|-----------|---------|---------|---------|
| 1 | Python函数 | 函数定义, 参数传递(位置/关键字/默认值), 返回值, 作用域 | 9h (约2周) | 循环, 条件判断 | 用函数重构之前的猜数字游戏，代码>=50行 |
| 2 | 数据结构 | 列表操作, 字典, 元组, 集合 | 12h (约3周) | 函数, 循环 | 完成LeetCode #1, #26, #88，正确率>=80% |
| 3 | 面向对象 | 类与对象, 继承, 多态, 封装 | 9h (约2周) | 函数, 数据结构 | 实现学生管理系统(CRUD)，代码>=120行 |

### 3. 时间估算
基于每周5小时投入：总工时30h，约6-7周完成。时间弹性±2周，预留复习消化时间。

### 4. 复习节点
- 阶段1学完第1天复习函数参数概念 | 第3天复习作用域规则 | 第7天综合复习函数章节
- 阶段2学完第1天复习列表字典操作 | 第3天复习集合操作 | 第7天综合复习数据结构

### 5. 里程碑与检验
- 阶段1: 完成HackerRank Python函数模块5题，正确率>=80%
- 阶段2: 完成LeetCode #1, #26, #88全部3题
- 阶段3: 用面向对象实现学生管理系统(CRUD)，包含至少3个类

> 规划好了！要从第1阶段「Python函数」开始吗？我现在就可以带你学第一个知识点。"""


def _compute_review_schedule_for_path(
    concepts: list[str], scheduler
) -> list[dict]:
    """为学习路径中的每个知识点计算艾宾浩斯间隔重复复习计划。

    对于已有复习历史的概念，返回当前保留率和下次复习时间。
    对于新概念，按 [1, 3, 7, 14, 30] 天间隔投射未来的复习日期。

    Args:
        concepts: 路径中所有知识点名称
        scheduler: ReviewScheduler 实例

    Returns:
        [{"concept": ..., "retention": ..., "risk": ...,
          "next_review_at": ... | "projected_reviews": [...]}, ...]
    """
    checkpoints: list[dict] = []
    today = datetime.now()

    for idx, concept in enumerate(concepts[:20]):  # 上限 20 个避免输出膨胀
        s = scheduler.get_or_create(concept)

        if s.last_reviewed is not None:
            # 已有复习历史 → 给出当前状态和下次复习时间
            checkpoints.append({
                "concept": concept,
                "retention": round(s.retention_rate, 3),
                "risk": s.risk_level,
                "next_review_at": s.next_review_at.isoformat()[:10] if s.next_review_at else None,
                "interval_days": s.current_interval_days,
                "review_count": s.review_count,
                "memory_strength": round(s.memory_strength, 3),
            })
        else:
            # 新概念 → 按间隔序列投射未来复习日期（按阶段错开起始日）
            projected: list[dict] = []
            cumulative = 0
            intervals = INTERVALS[:5]  # [1, 3, 7, 14, 30]
            # 按概念在路径中的位置错开起始复习日：前 5 个概念从 day 2 开始，后 5 个从 day 4 开始
            start_offset = (idx // 5) * 2 + 1
            for interval in intervals:
                cumulative += interval
                review_date = today + timedelta(days=start_offset + cumulative)
                projected.append({
                    "day": start_offset + cumulative,
                    "date": review_date.isoformat()[:10],
                    "interval": interval,
                })
            checkpoints.append({
                "concept": concept,
                "retention": 1.0,
                "risk": "low",
                "projected_reviews": projected,
            })

    return checkpoints


# ═══════════════════════════════════════════════════════════════
# v3 Refactoring: 拆分为 4 个辅助函数 (原 280 行单函数 → 职责分离)
# ═══════════════════════════════════════════════════════════════

def _collect_bkt_state(user_id: int) -> dict:
    """收集 BKT 知识追踪状态 → {concept: p_known, ...}"""
    try:
        from app.services.bkt_service import get_tracker
        tracker = get_tracker(user_id)
        return tracker.get_all_scores()
    except Exception as e:
        logger.warning("BKT state collection failed for user %s: %s", user_id, e)
        return {}


def _select_domain_files(topic: str) -> list[str]:
    """根据用户主题映射到对应的学科 KG 文件（精确匹配，避免多学科混杂）

    设计原则（参考 Khan Academy / roadmap.sh 领域划分）：
      - 一个主题只匹配一个最相关的学科 KG
      - 匹配规则：关键词子串匹配 KG 文件中的 domain 字段 + 节点名称
      - 无法匹配时返回空列表（调用方降级为通用输出）
    """
    import json as _json, os as _os, glob as _glob
    topic_lower = topic.lower().strip()

    # 关键词 → 学科文件映射（优先级从高到低）
    KEYWORD_DOMAIN_MAP = [
        # Python
        (["python", "py", "装饰器", "生成器", "迭代器", "django", "flask"], "kg_python.json"),
        # C++
        (["c++", "cpp", "cplusplus", "stl", "模板", "指针", "引用"], "kg_cpp.json"),
        # C (only if specifically asked, not generic "编程")
        (["c语言", "c基础", "k&r", "c编程"], "kg_cpp.json"),
        # Java
        (["java", "jvm", "spring", "maven", "gradle", "android"], "kg_java.json"),
        # Go
        (["golang", "go语言", "goroutine", "channel"], "kg_go.json"),
        # Frontend
        (["前端", "html", "css", "javascript", "js", "vue", "react", "typescript", "ts", "web"], "kg_frontend.json"),
        # ML/AI
        (["机器学习", "深度学习", "ml", "ai", "神经网络", "cnn", "rnn", "transformer", "nlp", "cv", "大模型", "llm", "pytorch", "tensorflow"], "kg_ml.json"),
        # Algorithm/Data Structure
        (["算法", "数据结构", "leetcode", "排序", "查找", "动态规划", "dp", "图论", "树", "链表", "栈", "队列", "哈希"], "kg_algorithm.json"),
        # Network
        (["网络", "tcp", "http", "ip", "dns", "协议", "socket", "路由", "交换机"], "kg_network.json"),
        # Database
        (["数据库", "sql", "mysql", "redis", "mongodb", "mongo", "索引", "事务", "acid", "nosql"], "kg_database.json"),
        # System/OS
        (["操作系统", "os", "系统", "编译", "进程", "线程", "内存", "cache", "cpu", "汇编", "指令"], "kg_system.json"),
        # Math (maps to algorithm's foundation)
        (["数学", "线性代数", "概率", "离散", "微积分", "统计"], "kg_algorithm.json"),
    ]

    for keywords, filename in KEYWORD_DOMAIN_MAP:
        for kw in keywords:
            if kw in topic_lower:
                return [filename]

    # 模糊匹配：检查 KG 文件中的节点名称
    docs_dir = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "docs")
    docs_dir = _os.path.abspath(docs_dir)
    for kg_file in sorted(_glob.glob(_os.path.join(docs_dir, "kg_*.json"))):
        try:
            with open(kg_file, "r", encoding="utf-8") as _f:
                data = _json.load(_f)
            for node in data.get("nodes", []):
                name = node.get("name", "")
                if name and (name.lower() in topic_lower or topic_lower in name.lower()):
                    return [kg_file]
        except Exception:
            pass

    return []  # 无法匹配 → 调用方降级


def _load_single_domain_kg(kg, filename: str) -> int:
    """加载单个学科的 KG 文件到 kg 对象"""
    import json as _json, os as _os
    docs_dir = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "docs")
    docs_dir = _os.path.abspath(docs_dir)
    kg_file = _os.path.join(docs_dir, filename)
    if not _os.path.exists(kg_file):
        return 0
    try:
        with open(kg_file, "r", encoding="utf-8") as _f:
            data = _json.load(_f)
        for node in data.get("nodes", []):
            name = node.get("name", "")
            if name and name not in kg.nodes:
                kg.nodes.add(name)
                kg.in_degree.setdefault(name, 0)
        for edge in data.get("edges", []):
            src, tgt = edge.get("source", ""), edge.get("target", "")
            if src and tgt and src in kg.nodes and tgt in kg.nodes:
                kg.edges.setdefault(src, set()).add(tgt)
                kg.in_degree[tgt] = kg.in_degree.get(tgt, 0) + 1
        return len(data.get("nodes", []))
    except Exception as e:
        logger.warning("KG file loading failed '%s': %s", filename, e)
        return 0


def _load_multidiscipline_kg(kg, topic: str = "") -> int:
    """加载知识图谱——优先按 topic 匹配单学科，无匹配时加载全部

    Args:
        kg: KnowledgeGraph 实例
        topic: 用户请求的学习主题（用于领域筛选）

    Returns: 加载的节点总数
    """
    import json as _json, os as _os, glob as _glob
    docs_dir = _os.path.join(_os.path.dirname(__file__), "..", "..", "..", "docs")
    docs_dir = _os.path.abspath(docs_dir)

    # 尝试按主题匹配单学科
    if topic:
        domain_files = _select_domain_files(topic)
        if domain_files:
            total = 0
            for f in domain_files:
                total += _load_single_domain_kg(kg, f)
            if total > 0:
                logger.info("PathAgent: 主题 '%s' → 学科 '%s', nodes=%d", topic, domain_files[0], total)
                return total

    # 降级：加载全部学科（无明确主题时）
    logger.info("PathAgent: 未匹配到单学科, 加载全部KG (topic='%s')", topic)
    total_nodes = 0
    for kg_file in sorted(_glob.glob(_os.path.join(docs_dir, "kg_*.json"))):
        try:
            with open(kg_file, "r", encoding="utf-8") as _f:
                data = _json.load(_f)
            for node in data.get("nodes", []):
                name = node.get("name", "")
                if name and name not in kg.nodes:
                    kg.nodes.add(name)
                    kg.in_degree.setdefault(name, 0)
                    total_nodes += 1
            for edge in data.get("edges", []):
                src, tgt = edge.get("source", ""), edge.get("target", "")
                if src and tgt and src in kg.nodes and tgt in kg.nodes:
                    kg.edges.setdefault(src, set()).add(tgt)
                    kg.in_degree[tgt] = kg.in_degree.get(tgt, 0) + 1
        except Exception:
            pass
    return total_nodes


def _compute_topology(kb: dict, kg, topic: str, known: set[str]) -> tuple[list[str], object]:
    """基于知识图谱拓扑排序计算学习顺序

    Args:
        kb: profile knowledge_base {concept: score}
        kg: KnowledgeGraph 实例 (已加载节点/边)
        topic: 用户请求的学习主题
        known: BKT 已掌握概念集合

    Returns:
        (topo_order, kg) — 拓扑排序后的概念列表和 KG 实例
    """
    if kg and kg.nodes:
        return kg.topological_sort(known), kg
    # 降级：按知识基础中的概念排序
    sorted_concepts = sorted(kb.items(), key=lambda x: -x[1]) if kb else []
    return [c for c, _ in sorted_concepts], kg


def _build_dag_stages(topo_order: list[str], known_concepts: set[str], weekly_hours: float) -> list[dict]:
    """将拓扑序列转换为 DAG 阶段结构 (含时间估算)

    Returns: [{"stage": 1, "concepts": [...], "hours": X, "milestone": "..."}, ...]
    """
    if not topo_order:
        return []
    # 每阶段 3-5 个概念, 每个概念 2-4 小时
    # P1: 小KG(节点<5)时每个概念独立成阶段，避免2节点被合并为1阶段
    total = len(topo_order)
    if total < 5:
        concepts_per_stage = 1
    else:
        concepts_per_stage = max(3, min(5, total // 3))
    stages = []
    for i in range(0, len(topo_order), concepts_per_stage):
        batch = topo_order[i:i + concepts_per_stage]
        hours = len(batch) * 3  # 每概念 3 小时估算
        weeks = max(1, round(hours / max(weekly_hours, 1)))
        stages.append({
            "stage": len(stages) + 1,
            "concepts": batch,
            "estimated_hours": hours,
            "estimated_weeks": weeks,
            "milestone": f"掌握 {', '.join(batch[:3])}" + ("..." if len(batch) > 3 else ""),
        })
    return stages


def _compute_review_schedule(stages: list[dict]) -> list[dict]:
    """为每个阶段计算艾宾浩斯遗忘曲线复习时间表 (1/3/7/14/30天)"""
    from datetime import datetime, timedelta
    from app.services.review_scheduler import INTERVALS as _RS_INTERVALS
    intervals = _RS_INTERVALS[:5]  # align with review_scheduler
    schedule = []
    today = datetime.now()
    cumulative_days = 0
    for stage in stages:
        stage_hours = stage.get("estimated_hours", 9)
        cumulative_days += stage.get("estimated_weeks", 1) * 7
        reviews = []
        for interval in intervals:
            review_date = today + timedelta(days=cumulative_days + interval)
            reviews.append({
                "day": cumulative_days + interval,
                "date": review_date.isoformat()[:10],
                "interval": f"第{interval}天",
                "duration_min": max(15, stage_hours * 5),  # 复习时间为学习时间的 1/4, 最少 15 分钟
            })
        schedule.append({"stage": stage["stage"], "reviews": reviews})
    return schedule


def _validate_path_output(llm_output: str, known_concepts: list[str], stages: list[dict]) -> tuple[bool, list[str], str]:
    """校验 LLM 生成的路径输出是否编造了不存在的知识点

    Returns:
        (is_valid, foreign_concepts, cleaned_output_or_error)
        is_valid=False 表示检测到编造内容
    """
    if not llm_output or not known_concepts:
        return True, [], llm_output

    known_set = {c.lower().strip() for c in known_concepts}
    # 从 LLM 输出中提取可能的"知识点"引用: 中文引号、加粗、列表项中的技术术语
    import re as _vre
    candidates = set()
    # 匹配 **粗体** 或 「」中的文本
    for m in _vre.finditer(r'\*\*(.+?)\*\*|「(.+?)」|`(.+?)`', llm_output):
        candidates.add((m.group(1) or m.group(2) or m.group(3)).strip())
    # 匹配 - 或数字. 开头的列表项中的核心术语
    for m in _vre.finditer(r'(?:^|\n)\s*[-•\d]\.?\s*\*?\*?(.+?)\*?\*?(?:\s*[:：\-—])', llm_output, _vre.MULTILINE):
        term = m.group(1).strip()
        if len(term) <= 30:
            candidates.add(term)

    foreign = []
    for cand in candidates:
        cand_lower = cand.lower().strip()
        if len(cand_lower) < 2:
            continue
        # 检查是否在已知概念列表中
        if cand_lower not in known_set:
            # 模糊匹配: 检查是否有已知概念包含此候选或此候选包含已知概念
            matched = False
            for kc in known_set:
                if len(kc) >= 3 and (kc in cand_lower or cand_lower in kc):
                    matched = True
                    break
            if not matched:
                # 过滤常见中文描述词（非知识点）
                common_words = {"学习", "阶段", "基础", "进阶", "高级", "核心", "知识点", "概念",
                                "掌握", "理解", "了解", "复习", "实践", "项目", "练习", "小时",
                                "目标", "内容", "计划", "路径", "时间", "安排", "建议"}
                if cand_lower not in common_words:
                    foreign.append(cand)

    if foreign:
        logger.warning("PathAgent: _validate_path_output 检测到 %d 个编造知识点: %s",
                       len(foreign), foreign[:10])
        # 尝试清理: 从输出中移除编造术语（保守策略：只在明显位置替换）
        cleaned = llm_output
        for f_term in foreign[:5]:
            cleaned = cleaned.replace(f"**{f_term}**", f"(参考: {f_term})")
            cleaned = cleaned.replace(f"「{f_term}」", f"(参考: {f_term})")
        return False, foreign, cleaned

    return True, [], llm_output


# ═══════════════════════════════════════════════════════════════
# 教学模式辅助函数
# ═══════════════════════════════════════════════════════════════

def _reorder_by_profile(path: list[str], profile: dict) -> list[str]:
    """根据画像偏好在同阶段内重排节点顺序（不破坏拓扑序）

    - 视觉型: 优先有"图/可视化/界面/UI"关键词的节点
    - 动手型: 优先有"编程/代码/项目/实现"关键词的节点
    - exam目标: 优先基础知识/核心概念节点
    - career目标: 优先实践/项目/框架节点
    - 时间少(<10h/周): 核心节点优先，边缘节点后置
    """
    if len(path) <= 1:
        return path

    style = str(profile.get("cognitive_style", "")).lower()
    goal = str(profile.get("learning_goal", "")).lower()
    hours = float(profile.get("weekly_hours") or 0)

    def _node_weight(node: str) -> float:
        w = 0.0
        nl = node.lower()
        # 认知风格权重
        if "visual" in style or "视觉" in style:
            if any(k in nl for k in ["图", "可视化", "界面", "ui", "视图", "渲染", "布局"]):
                w += 2.0
        if "kinesthetic" in style or "动手" in style:
            if any(k in nl for k in ["编程", "代码", "项目", "实现", "实战", "操作", "练习"]):
                w += 2.0
        if "reading" in style or "阅读" in style:
            if any(k in nl for k in ["原理", "概念", "理论", "基础", "概述", "结构"]):
                w += 1.5
        # 学习目标权重
        if "exam" in goal or "考试" in goal:
            if any(k in nl for k in ["基础", "核心", "概念", "原理", "算法", "数据结构"]):
                w += 1.5
        elif "career" in goal or "工作" in goal or "求职" in goal:
            if any(k in nl for k in ["项目", "实战", "框架", "应用", "面试", "设计模式"]):
                w += 1.5
        # 时间约束权重 (时间少→核心节点优先)
        if hours > 0 and hours < 10:
            if any(k in nl for k in ["基础", "核心", "概述", "入门"]):
                w += 1.0
            if any(k in nl for k in ["进阶", "高级", "优化", "扩展", "原理"]):
                w -= 0.5
        return w

    # 保持拓扑序的前提下，按权重降序排列
    scored = [(i, node, _node_weight(node)) for i, node in enumerate(path)]
    result = list(path)
    # 仅对相邻且同权重段内交换（不跨段交换，保持拓扑安全）
    i = 0
    while i < len(result) - 1:
        wi = _node_weight(result[i])
        wj = _node_weight(result[i + 1])
        if wj > wi + 1.0:  # 后续节点权重显著更高 → 前移
            result[i], result[i + 1] = result[i + 1], result[i]
            i = max(0, i - 1)
        else:
            i += 1
    return result


def _teaching_init(state: dict, topic: str) -> dict:
    """初始化教学流程: KG拓扑排序 → 构建 active_path → 返回首节点"""
    kg = get_graph()
    if not kg.nodes:
        loaded = _load_multidiscipline_kg(kg, topic=topic)
        logger.info("PathAgent(teaching): KG加载, topic='%s', nodes=%d", topic, loaded)

    if kg.nodes:
        tracker = get_tracker(state.get("user_id", 0))
        known = set(tracker.get_mastered())
        phases = kg.topological_sort(known)
        active_path: list[str] = []
        for phase in phases:
            active_path.extend(phase)
        # v5: 根据画像偏好重排同阶段内节点顺序
        profile = state.get("user_profile") or {}
        active_path = _reorder_by_profile(active_path, profile)
        logger.info("PathAgent(teaching): KG拓扑完成 phases=%d nodes=%d known=%d",
                     len(phases), len(active_path), len(known))
    else:
        # 降级: 从画像知识基础构建简单序列
        profile = state.get("user_profile") or {}
        kb = profile.get("knowledge_base", {})
        if isinstance(kb, dict) and kb:
            active_path = [k for k in kb if isinstance(k, str)]
            active_path.sort(key=lambda k: kb.get(k, 0) if isinstance(kb.get(k), (int, float)) else 50)
        else:
            active_path = [topic] if topic else []

    if not active_path:
        active_path = [topic] if topic else ["基础知识"]

    # 尝试按 topic 筛选相关知识节点（保持主题聚焦）
    if topic and len(active_path) > 1:
        topic_lower = topic.lower()
        # 提取 topic 的关键词用于模糊匹配
        topic_core = re.sub(r'（[^）]*）', '', topic).strip()
        matching = [n for n in active_path if topic_core.lower() in n.lower() or any(
            part in n for part in topic_core.split() if len(part) >= 2
        )]
        if matching and len(matching) >= 2:
            active_path = matching
            logger.info("PathAgent(teaching): 聚焦主题 '%s' → %d 个匹配节点", topic, len(matching))

    teaching_context = {
        "active_path": active_path,
        "current_index": 0,
        "completed_nodes": [],
        "mode": "teaching",
        "topic": topic,
    }

    first_node = active_path[0]
    logger.info("PathAgent(teaching): init 完成 first_node='%s' total=%d", first_node, len(active_path))

    # v4: 自动触发首次教学 — 不等用户说"好", 直接链式路由到 resource_agent
    from app.core.shared_utils import _build_llm_messages
    all_msgs = state.get("messages", [])
    intro = (
        f"## 学习路径: {topic}\n\n"
        f"共 {len(active_path)} 个知识点, 我们从 **{first_node}** 开始。\n\n"
    )
    # 注入教学进度上下文 → resource_agent 知道这是第几个节点
    teach_ctx_for_resource = {
        "topic": first_node,
        "teaching": True,
        "node_index": 0,
        "total_nodes": len(active_path),
        "active_path": active_path,
        "completed_nodes": [],
    }
    return {
        "current_agent": "path_agent",
        "next_agent": "resource_agent",  # 直接路由, 不等用户确认
        "teaching_context": teaching_context,
        "stream_buffer": intro,
        "context": teach_ctx_for_resource,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "path_agent": {
                "teaching_stage": "node_ready",
                "current_node": first_node,
                "active_path": active_path,
                "total_nodes": len(active_path),
                "teach_context": teach_ctx_for_resource,
            },
        },
    }


def _teaching_advance(state: dict, tc: dict) -> dict:
    """教学流程推进: current_index+1 → 返回下一节点 或 完成

    Issue 2 Fix: 增加防御性校验，防止教学流程卡在同一节点。
    - 校验 active_path 非空
    - 校验 next_index 严格大于 current_index
    - 校验下一节点与当前节点不同（防重复教学）
    """
    active_path: list = tc.get("active_path", [])
    current_index: int = tc.get("current_index", 0)
    completed_nodes: list = tc.get("completed_nodes", [])

    # 防御: 空路径 → 拒绝推进
    if not active_path:
        logger.warning("PathAgent(teaching): active_path 为空，无法推进教学")
        return {
            "current_agent": "path_agent",
            "teaching_context": tc,
            "stream_buffer": "",
            "agent_outputs": {
                **state.get("agent_outputs", {}),
                "path_agent": {"teaching_stage": "error", "reason": "empty_path"},
            },
        }

    # 防御: 索引越界 → 全部完成
    if current_index >= len(active_path):
        logger.info("PathAgent(teaching): current_index=%d 已超过路径长度=%d → 标记完成",
                     current_index, len(active_path))
        tc["mode"] = "completed"
        tc["completed_nodes"] = completed_nodes
        tc["current_index"] = len(active_path)
        return {
            "current_agent": "path_agent",
            "teaching_context": tc,
            "stream_buffer": "## 学习路径已完成\n\n所有节点已学完。来评估一下学习效果吧！",
            "agent_outputs": {
                **state.get("agent_outputs", {}),
                "path_agent": {
                    "teaching_stage": "completed",
                    "completed_nodes": completed_nodes,
                    "total_nodes": len(active_path),
                    "topic": tc.get("topic", ""),
                },
            },
        }

    # 标记当前节点为已完成
    current_node = active_path[current_index]
    if current_node not in completed_nodes:
        completed_nodes.append(current_node)
        logger.info("PathAgent(teaching): 标记完成 node='%s' (%d/%d)",
                     current_node, len(completed_nodes), len(active_path))
    else:
        logger.info("PathAgent(teaching): node='%s' 已在 completed_nodes 中，跳过重复标记", current_node)

    next_index = current_index + 1

    # 教学引用跳转: 用户指定了具体第X天 → 跳转到目标索引
    target_index = state.get("context", {}).get("teach_target_index")
    if target_index is not None and isinstance(target_index, int) and 0 <= target_index < len(active_path):
        if target_index != next_index:
            logger.info("PathAgent(teaching): 教学跳转 %d → %d (node='%s')",
                         current_index, target_index, active_path[target_index])
            next_index = target_index

    # 防御: next_index 必须严格大于 current_index
    if next_index <= current_index:
        logger.error("PathAgent(teaching): BUG — next_index=%d <= current_index=%d，强制纠正",
                      next_index, current_index)
        next_index = current_index + 1

    if next_index >= len(active_path):
        # ── 全部完成 ──
        tc["mode"] = "completed"
        tc["completed_nodes"] = completed_nodes
        tc["current_index"] = next_index

        topic_name = tc.get("topic", "")
        congrats = (
            f"## 学习路径完成\n\n"
            f"恭喜你完成了「**{topic_name}**」的全部 {len(completed_nodes)} 个知识点！\n\n"
            f"**已学内容**：{'  →  '.join(completed_nodes[:15])}"
            f"{'...' if len(completed_nodes) > 15 else ''}\n\n"
            f"你可以选择：\n"
            f"- **评估测试**：检验一下学习效果，生成6维雷达图报告\n"
            f"- **学新主题**：告诉我下一个想学的内容，我们继续\n"
            f"- **复习薄弱点**：针对容易忘记的知识点做间隔复习"
        )

        logger.info("PathAgent(teaching): 教学完成 total=%d completed=%d",
                     len(active_path), len(completed_nodes))

        return {
            "current_agent": "path_agent",
            "teaching_context": tc,
            "stream_buffer": congrats,
            "agent_outputs": {
                **state.get("agent_outputs", {}),
                "path_agent": {
                    "teaching_stage": "completed",
                    "completed_nodes": completed_nodes,
                    "total_nodes": len(active_path),
                    "topic": topic_name,
                },
            },
        }

    # ── 推进到下一节点 ──
    next_node = active_path[next_index]

    # Issue 2 Fix: 防御性检查 — 下一节点必须与当前节点不同
    if next_node == current_node and current_index != next_index:
        logger.warning("PathAgent(teaching): 下一节点与当前节点相同 '%s' → 可能是路径数据重复，跳过并继续推进",
                       next_node)
        # 强制跳过重复节点，继续向前推进
        tc["current_index"] = next_index
        tc["completed_nodes"] = completed_nodes
        # 递归尝试再推进一次（最多递归一层，防止无限循环）
        if next_index + 1 < len(active_path):
            next_next = active_path[next_index + 1]
            if next_next != next_node:
                tc["current_index"] = next_index + 1
                next_node = next_next
                next_index = next_index + 1
                logger.info("PathAgent(teaching): 跳过重复节点 → 实际推进到 '%s' (index=%d)", next_node, next_index)

    tc["current_index"] = next_index
    tc["completed_nodes"] = completed_nodes

    logger.info("PathAgent(teaching): advance %d/%d node='%s' → next='%s'",
                 current_index + 1, len(active_path),
                 active_path[current_index], next_node)

    # 阶段边界给结构化选项 (每3个节点一个阶段)
    stage_note = ""
    is_stage_boundary = (next_index > 0 and (next_index + 1) % 3 == 0)
    if is_stage_boundary and next_index + 1 < len(active_path):
        # 在 stream_buffer 中加入结构化选项标记，前端可渲染为按钮
        upcoming = active_path[next_index + 1] if next_index + 1 < len(active_path) else ""
        stage_note = (
            f"\n\n---\n"
            f"> 已学完第 {(next_index + 1) // 3} 阶段！接下来可以：\n"
            f"> [继续学{upcoming}] [做练习题巩固] [复习本阶段内容] [换个主题]\n"
        )

    return {
        "current_agent": "path_agent",
        "teaching_context": tc,
        "stream_buffer": stage_note,
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "path_agent": {
                "teaching_stage": "node_ready",
                "current_node": next_node,
                "current_index": next_index,
                "total_nodes": len(active_path),
                "completed_nodes": completed_nodes,
                "teach_context": {"topic": next_node, "teaching": True},
            },
        },
    }


def replan_remaining_path(state: dict) -> dict | None:
    """动态重规划：BKT状态变化后，重新计算剩余路径的拓扑排序

    当学生通过教学/练习掌握了新概念后，原本被前置依赖锁定的节点可能解锁。
    此函数重新运行拓扑排序，更新 teaching_context 中的 active_path。

    Returns:
        更新后的 teaching_context (dict) 或 None（路径无变化）
    """
    tc = state.get("teaching_context") or {}
    if tc.get("mode") != "teaching":
        return None

    active_path: list[str] = tc.get("active_path", [])
    completed_nodes: list[str] = tc.get("completed_nodes", [])
    current_index: int = tc.get("current_index", 0)

    if not active_path or current_index >= len(active_path):
        return None

    user_id = state.get("user_id", 0)
    if not user_id:
        return None

    # 获取最新 BKT 掌握状态
    tracker = get_tracker(user_id)
    known = set(tracker.get_mastered())

    # 标记已完成的节点为"已知"
    known.update(completed_nodes)

    # 重新加载 KG 并运行拓扑排序
    kg = get_graph()
    if not kg.nodes:
        try:
            _load_multidiscipline_kg(kg, topic=tc.get("topic", ""))
        except Exception:
            pass

    if not kg.nodes:
        return None

    # 重跑拓扑排序
    new_phases = kg.topological_sort(known)
    new_path: list[str] = []
    for phase in new_phases:
        new_path.extend(phase)

    # 保持已完成节点在路径头部
    remaining_new = [n for n in new_path if n not in completed_nodes]
    remaining_old = active_path[current_index:]

    # 检查路径是否有实际变化
    new_unlocked = [n for n in remaining_new if n not in remaining_old]
    removed = [n for n in remaining_old if n not in remaining_new]

    if not new_unlocked and not removed:
        logger.debug("PathAgent(replan): 路径无变化")
        return None

    # 构建新路径：已完成 + 新排序的剩余节点
    updated_path = completed_nodes + remaining_new

    tc["active_path"] = updated_path
    tc["current_index"] = len(completed_nodes)  # 指向第一个未完成节点
    tc["_replanned"] = True
    tc["_new_unlocked"] = new_unlocked
    tc["_removed"] = removed  # 因为已掌握而跳过的节点

    logger.info(
        "PathAgent(replan): 路径重规划完成 — 新解锁=%s, 跳过=%s, 剩余=%d节点",
        new_unlocked, removed, len(remaining_new),
    )

    return tc


def path_agent_node(state: AgentState, spark: SparkClient) -> dict:
    """Path Agent 主节点: BKT状态收集 → KG拓扑排序 → DAG阶段构建 → 复习调度"""
    state = dict(state)  # TypedDict → dict

    profile = state.get("user_profile") or {}
    context = state.get("context", {})
    # 兼容 BaseMessage / dict 两种格式（LangGraph checkpoint 恢复后 messages 可能为 dict）
    last_msg = ""
    if state.get("messages"):
        _last = state["messages"][-1]
        last_msg = _last["content"] if isinstance(_last, dict) else getattr(_last, "content", "")
    topic = context.get("topic", last_msg or "构建学习计划")

    # ═══════════════════════════════════════════════════════════════
    # 动态重规划入口: BKT变化触发路径重算
    # ═══════════════════════════════════════════════════════════════
    if context.get("replan_path"):
        updated_tc = replan_remaining_path(state)
        if updated_tc:
            next_node = updated_tc["active_path"][updated_tc["current_index"]] \
                if updated_tc["current_index"] < len(updated_tc["active_path"]) else ""
            new_unlocked = updated_tc.get("_new_unlocked", [])
            removed = updated_tc.get("_removed", [])

            msg_parts = ["学习路径已自动更新："]
            if removed:
                msg_parts.append(f"- 已掌握，跳过：{'、'.join(removed)}")
            if new_unlocked:
                msg_parts.append(f"- 新解锁：{'、'.join(new_unlocked)}")
            if next_node:
                msg_parts.append(f"- 下一节点：{next_node}")

            return {
                "current_agent": "path_agent",
                "teaching_context": updated_tc,
                "stream_buffer": "\n".join(msg_parts),
                "agent_outputs": {
                    **state.get("agent_outputs", {}),
                    "path_agent": {
                        "teaching_stage": "replanned",
                        "current_node": next_node,
                        "current_index": updated_tc["current_index"],
                        "total_nodes": len(updated_tc["active_path"]),
                        "completed_nodes": updated_tc.get("completed_nodes", []),
                        "new_unlocked": new_unlocked,
                        "skipped": removed,
                    },
                },
            }
        # 无变化 → 静默跳过
        return {
            "current_agent": "path_agent",
            "stream_buffer": "",
            "teaching_context": None,
            "agent_outputs": {**state.get("agent_outputs", {}), "path_agent": {"teaching_stage": "no_change"}},
        }

    # ═══════════════════════════════════════════════════════════════
    # 教学模式入口: teaching_continue 或 init_teaching
    # ═══════════════════════════════════════════════════════════════
    if context.get("teaching_continue"):
        tc = state.get("teaching_context") or {}
        if tc.get("mode") == "teaching":
            return _teaching_advance(state, tc)

    if context.get("init_teaching") and should_init_teaching(state, context):  # P0-B 2026-07-11
        tc = state.get("teaching_context") or {}
        if not tc or tc.get("mode") != "teaching":
            return _teaching_init(state, topic)

    # 读取话题上下文（用户语言偏好 + 排除约束）
    topic_ctx = context.get("topic_context", {})
    user_lang = topic_ctx.get("user_language", "")
    user_constraints = topic_ctx.get("user_constraints", [])

    # 如果用户指定了语言，在主题中标注
    if user_lang:
        topic = f"{topic}（使用{user_lang}语言）"
    if user_constraints:
        exclude_text = "、".join(user_constraints)
        topic = f"{topic}（排除：{exclude_text}）"

    weekly_raw = profile.get("weekly_hours")
    weekly = float(weekly_raw) if weekly_raw is not None else 5.0

    # 初始化变量（防止 UnboundLocalError）
    kg_path_text = None
    review_text = ""
    due_reviews = []  # ← 必须在 try 之前初始化，except 块会引用
    dag_plan = None           # Fix 1: 动态规划器输出的 DAG 计划
    dag_path_enrichment = ""  # Fix 1: DAG 数据注入 LLM 提示词的富文本
    all_path_concepts: list[str] = []    # Fix 2: 路径中所有知识点（用于复习调度）
    path_review_schedule: list[dict] = []  # Fix 2: 投射的复习计划
    kg: object | None = None  # 使 KG 在 try 块外也可访问（Fix 3 构建边数据用）

    # 尝试用知识图谱 + 拓扑排序生成学习路径
    try:
        kg = get_graph()
        if not kg.nodes:
            # v3: 按用户主题加载对应的学科 KG (不再混搭全部学科)
            loaded = _load_multidiscipline_kg(kg, topic=topic)
            logger.info("PathAgent: KG加载完成, topic='%s', nodes=%d", topic, loaded)

        if kg.nodes:
            # BKT 已掌握的知识点作为起点
            tracker = get_tracker(state.get("user_id", 0))
            known = set(tracker.get_mastered())
            phases = kg.topological_sort(known)
            time_plan = kg.estimate_time(phases, weekly)

            # 构建结构化路径文本
            lines = ["## 学习路径（知识图谱 + 拓扑排序）", "", f"**主题**：{topic}"]
            lines.append(f"**每周投入**：{weekly} 小时")
            lines.append(f"**已掌握**：{len(known)} 个知识点")
            lines.append("")
            for p in time_plan:
                lines.append(f"### 阶段 {p['phase']}：{'、'.join(p['topics'][:5])}")
                lines.append(f"- 知识点数：{len(p['topics'])} | 预计 {p['estimated_hours']} 小时 | 约 {p['estimated_weeks']} 周")

            # 艾宾浩斯复习节点（在知识图谱路径中插入）
            scheduler = get_scheduler(state.get("user_id", 0))
            due_reviews = scheduler.get_review_nodes()
            if due_reviews:
                review_lines = ["\n## 复习提醒（艾宾浩斯遗忘曲线）", ""]
                for r in due_reviews:
                    risk_label = {"high": "立即复习", "medium": "近期复习", "low": "跟踪"}.get(r["risk"], "跟踪")
                    review_lines.append(f"- **{r['concept']}**：记忆保留率 {r['retention']:.0%}，{risk_label}")
                review_text = "\n".join(review_lines)

            kg_path_text = "\n".join(lines) + review_text
            logger.info("PathAgent: 拓扑排序完成 phases=%d", len(phases))

            # ═══════════════════════════════════════════════════════════════
            # Fix 1: Wire dynamic_path_planner — 用 BKT 状态 + KG 拓扑 + 学习目标联合规划
            # ═══════════════════════════════════════════════════════════════
            try:
                planner = build_planner_from_db(state.get("user_id", 0), topic=topic)
                dag_plan = planner.plan(kg.nodes, dict(kg.edges), dict(kg.in_degree))

                # 收集路径中所有知识点名称
                for phase in dag_plan.get("phases", []):
                    all_path_concepts.extend(phase.get("topics", []))

                # ═══════════════════════════════════════════════════════════
                # Fix 2: 为路径中每个知识点投射艾宾浩斯间隔重复复习计划
                # ═══════════════════════════════════════════════════════════
                path_review_schedule = _compute_review_schedule_for_path(
                    all_path_concepts, scheduler
                )

                # 构建 DAG 规划数据（注入 LLM 提示词，但去掉 debug 内部信息）
                dag_lines = ["", "## 学习路径（阶段规划）", ""]
                dag_lines.append(
                    f"- 共 {dag_plan.get('total_nodes', 0)} 个知识点，"
                    f"已掌握: {dag_plan.get('mastered_count', 0)}"
                )
                dag_lines.append("")
                for phase in dag_plan.get("phases", []):
                    phase_topics = phase.get("topics", [])
                    dag_lines.append(
                        f"### 阶段 {phase['phase']}: "
                        f"{', '.join(phase_topics[:5])}"
                    )
                    _hours = phase.get("estimated_hours", 0)
                    _weeks = phase.get("estimated_weeks", 0)
                    # R-03: 动态规划器输出不含 estimated_hours/weeks，按知识点数估算
                    if not _hours and not _weeks:
                        _hours = max(1, len(phase_topics) * 1.5)
                        _weeks = max(1, round(_hours / max(weekly, 1)))
                    dag_lines.append(f"- 知识点数: {len(phase_topics)} | 预计 {_hours:.0f} 小时 | 约 {_weeks} 周")

                if dag_plan.get("next_topics"):
                    dag_lines.append(
                        f"\n**现在可以开始学习**: "
                        f"{', '.join(dag_plan['next_topics'][:5])}"
                    )
                # P2-03: 冷启动降级 — 新用户无 BKT 数据时给出初学者友好提示
                if dag_plan.get("mastered_count", 0) == 0:
                    dag_lines.append(
                        f"\n**学习建议**: 这是你的第一个学习路径，从第一阶段开始循序渐进。"
                        f"每个阶段完成后可通过做题检验掌握程度，系统将自动调整后续路径。"
                    )
                elif dag_plan.get("weak_points"):
                    # U-04: BKT 数据不足时避免"薄弱环节"标签 — 新手答1-2题就标记薄弱不合理
                    _bkt_total = dag_plan.get("total_nodes", 0)
                    _label = "重点关注（薄弱环节）" if _bkt_total >= 5 else "建议重点学习"
                    dag_lines.append(
                        f"\n**{_label}**: "
                        f"{', '.join(dag_plan['weak_points'])}"
                    )

                # 艾宾浩斯复习计划（投射未来的复习日期）
                if path_review_schedule:
                    dag_lines.append("")
                    dag_lines.append("## 艾宾浩斯复习计划（间隔重复）")
                    dag_lines.append("")
                    for r in path_review_schedule[:10]:
                        if "projected_reviews" in r:
                            dates_str = " → ".join([
                                f"第{pr['day']}天({pr['date']})"
                                for pr in r["projected_reviews"][:3]
                            ])
                            dag_lines.append(
                                f"- **{r['concept']}**: {dates_str}"
                            )
                        else:
                            dag_lines.append(
                                f"- **{r['concept']}**: "
                                f"下次复习 {r.get('next_review_at', '待定')} "
                                f"(保留率 {r.get('retention', 1.0):.0%})"
                            )

                dag_path_enrichment = "\n".join(dag_lines)
                logger.info(
                    "PathAgent: Dynamic planner success phases=%d "
                    "concepts=%d reviews=%d",
                    len(dag_plan.get("phases", [])),
                    len(all_path_concepts),
                    len(path_review_schedule),
                )
            except Exception as _e:
                logger.warning(
                    "PathAgent: Dynamic planner failed, using KG-only: %s", _e
                )
    except Exception as e:
        logger.warning("PathAgent: 知识图谱路径生成失败，回退到 LLM: %s", e)
        review_lines = ["\n## 复习提醒（艾宾浩斯遗忘曲线）", ""]
        for r in due_reviews:
            risk_label = {"high": "立即复习", "medium": "近期复习", "low": "跟踪"}.get(r["risk"], "跟踪")
            review_lines.append(f"- **{r['concept']}**：记忆保留率 {r['retention']:.0%}，{risk_label}")
        review_text = "\n".join(review_lines)

    # 兜底：知识图谱无数据时用 LLM 生成
    messages = None
    no_kg_fallback = None  # 无 KG 时的直接输出文本（不经过 LLM）
    # 准备公共变量：对话历史和用户消息，供两种路径使用
    all_msgs = state.get("messages", [])
    last_user_msg = last_msg_content(state.get("messages", []), default=topic)

    if kg_path_text:
        # 使用 DAG 动态规划数据作为 prompt 主数据（包含阶段+复习），
        # 避免 kg_path_text 与 dag_path_enrichment 两套阶段信息冲突
        if dag_path_enrichment:
            full_kg_text = dag_path_enrichment
        else:
            full_kg_text = kg_path_text

        kg_polish_system = (
            "你是一个学习路径规划专家。以下是由知识图谱和 BKT 算法"
            "生成的学习路径。请你润色为一份清晰易懂的学习计划。\n\n"
            "【铁律 — 违反将导致输出被丢弃】\n"
            "1. 知识点名称必须与下方完全一致，禁止翻译/改写/合并/拆分/添加\n"
            "2. 阶段数量、阶段名称、每个阶段的知识点列表不可改变\n"
            "3. 禁止引入下方未列出的任何概念、术语、技术名词\n"
            "4. 禁止发明'Web开发''数据分析''深度学习'等不在下方阶段列表中的阶段名\n"
            "5. 禁止将内部算法信息（如算法名、DAG动态规划等）输出给用户\n"
            "6. 禁止使用套话模板（如'通过实际案例来学习'、'练习解决实际问题'），每阶段必须给出该阶段特有的学习目标\n"
            "7. 输出前逐项核对：每个知识点名称是否与原文一字不差\n\n"
            + full_kg_text
        )

        # 携带对话历史，帮助 LLM 理解用户上下文
        from app.core.shared_utils import _build_llm_messages
        messages = _build_llm_messages(
            kg_polish_system,
            all_msgs,
            last_user_msg,
            max_history=12,
            topic_context=topic_ctx,
        )
    if not messages:
        # v4: 永远不让 LLM 凭空生成计划。从 KG 节点构建结构化计划, LLM 只做润色
        if kg and kg.nodes:
            # 从 KG 节点构建真实计划
            topo_nodes = list(kg.nodes)
            known = set()
            try:
                tracker = get_tracker(state.get("user_id", 0))
                known = set(tracker.get_mastered())
            except Exception as e:
                logger.warning("BKT mastered nodes retrieval failed for user %s: %s", state.get("user_id", 0), e)
                pass
            # 过滤已知节点, 保留待学节点
            remaining = [n for n in topo_nodes if n not in known]
            if not remaining:
                remaining = topo_nodes

            # 使用 _build_dag_stages 构建阶段
            dag_stages = _build_dag_stages(remaining, known, weekly)
            schema = get_scheduler(state.get("user_id", 0))
            schedule = _compute_review_schedule(dag_stages)

            # 构建结构化计划文本 — LLM 只润色, 不改变结构
            plan_lines = [f"## 知识图谱学习计划: {topic}", ""]
            plan_lines.append(f"**领域节点总数**: {len(kg.nodes)} | **待学**: {len(remaining)} | **已掌握**: {len(known)}")
            plan_lines.append(f"**每周投入**: {weekly} 小时 | **预计总耗时**: {sum(s['estimated_hours'] for s in dag_stages)} 小时")
            plan_lines.append("")
            for s in dag_stages:
                concepts = s['concepts']
                plan_lines.append(f"### 阶段 {s['stage']}: {concepts[0]}{' → ' + concepts[-1] if len(concepts) > 1 else ''}")
                plan_lines.append(f"- **知识点**({len(concepts)}个): {'、'.join(concepts)}")
                plan_lines.append(f"- **预计**: {s['estimated_hours']}小时 / {s['estimated_weeks']}周")
                plan_lines.append(f"- **检验标准**: 掌握{concepts[0] if concepts else ''}的核心用法")
                plan_lines.append("")
            if schedule:
                plan_lines.append("## 复习时间表")
                for sr in schedule[:5]:
                    reviews_str = " → ".join([f"第{r['day']}天" for r in sr.get('reviews', [])[:3]])
                    plan_lines.append(f"- 阶段{sr['stage']}: {reviews_str}")

            full_kg_text = "\n".join(plan_lines)

            # P1-05: 生成后二次校验 — 验证所有知识点是否在KG中、阶段数是否一致
            is_valid, invalid_concepts, validation_msg = _validate_path_output(
                full_kg_text, remaining, dag_stages
            )
            if not is_valid:
                logger.warning("PathAgent: _validate_path_output 检测到编造知识点: %s", invalid_concepts)
                # 使用清理后的文本替换原始输出
                full_kg_text = validation_msg

            kg_polish_system = (
                "你是一个学习路径规划专家。以下是由知识图谱拓扑排序算法自动生成的学习路径。"
                "请润色为清晰的学习计划——保持阶段顺序、知识点名称和数量不变, "
                "用热情专业的语气逐阶段说明学习内容和目标。\n\n"
                "【铁律 — 违反将导致输出被丢弃】\n"
                "1. 知识点名称必须与下方完全一致，禁止翻译/改写/合并/拆分/添加\n"
                "2. 阶段数量、每个阶段的知识点列表不可改变\n"
                "3. 禁止引入下方未列出的任何概念、术语、技术名词\n"
                "4. 只做语言润色：加说明、加目标、加复习提示\n"
                "5. 输出前逐项核对：每个知识点名称是否与原文一字不差\n"
                f"6. 禁止使用'第X周/第X天'扁平列表格式 — 保留原DAG阶段结构({len(dag_stages)}个阶段)\n"
                "7. 每个阶段必须标注前置依赖关系（如'前置: XXX'），体现学习路径的拓扑顺序\n"
                "8. 输出格式：每个阶段独立一节，包含\"前置\" → \"知识点\" → \"目标\" → \"检验\"四个部分\n\n" + full_kg_text
            )

            from app.core.shared_utils import _build_llm_messages
            messages = _build_llm_messages(
                kg_polish_system,
                all_msgs,
                last_user_msg,
                max_history=12,
                topic_context=topic_ctx,
            )
        else:
            # 无 KG 数据: 不调用 LLM 编造内容，直接返回引导消息
            from app.core.shared_utils import _get_profile_status
            filled_dims, _ = _get_profile_status(profile)
            kb = profile.get("knowledge_base", {})
            if isinstance(kb, dict) and kb:
                concepts = sorted(kb.keys(), key=lambda k: kb.get(k, 0) if isinstance(kb.get(k), (int, float)) else 50, reverse=True)
                no_kg_fallback = f"## 学习建议: {topic}\n\n基于你的知识基础, 建议按以下顺序学习:\n\n" + "\n".join(f"- {c}" for c in concepts[:10])
            elif len(filled_dims) < 2:
                no_kg_fallback = (
                    f"## 学习路径: {topic}\n\n"
                    f"你的学习画像尚未建立，知识图谱中也没有足够的数据来生成个性化学习路径。\n\n"
                    f"请先告诉我:\n"
                    f"- 你想学习什么方向？（如 Python、Java、算法等）\n"
                    f"- 你目前的基础如何？（零基础 / 有一定了解 / 比较熟悉）\n\n"
                    f"有了这些信息，我就能为你规划一条适合的学习路线。"
                )
            else:
                no_kg_fallback = (
                    f"## 学习路径: {topic}\n\n"
                    f"该领域的知识图谱数据暂不完整，无法生成结构化的学习路径。\n\n"
                    f"建议你先通过对话学习或资源浏览积累基础，系统会在知识图谱更新后自动生成个性化路径。\n\n"
                    f"你也可以尝试:\n"
                    f"- 换个更具体的学习方向提问\n"
                    f"- 让我推荐一些入门资源\n"
                    f"- 做几道练习题测试当前水平"
                )
            messages = None  # 不调用 LLM，直接使用 stream_buffer 输出

    # Token 截断：防止路径文本过长导致 API 超限
    if messages:
        from app.utils.llm_helper import truncate_messages
        messages = truncate_messages(messages, max_tokens=6000)

    logger.info("PathAgent: 准备流式生成学习路径")

    # 预生成兜底文本（如果 LLM 返回空）
    fallback_path = no_kg_fallback if no_kg_fallback else f"## 学习路径：{topic}\n\n基于你的知识图谱分析，推荐以下学习顺序：\n\n1. 先巩固基础概念\n2. 逐步学习进阶主题\n3. 通过练习巩固所学\n\n如需更详细的计划，可以告诉我具体想学的内容。"

    # ═══════════════════════════════════════════════════════════════
    # Fix 3: 构建结构化输出 — 供前端 LearningPathView 渲染 DAG 图和复习时间表
    # ═══════════════════════════════════════════════════════════════
    if dag_plan:
        algorithm = "topological_sort_bkt_dynamic"
    elif kg_path_text:
        algorithm = "topological_sort"
    else:
        algorithm = "llm"

    path_output: dict = {
        "topic": topic,
        "algorithm": algorithm,
    }
    if messages:
        # 非教学模式(无 init_teaching)的独立学习计划限制 1024 tokens
        # 防止 LLM 填充编造避免 54 天计划 + PGDCP 幻觉循环
        _is_teaching = context.get("init_teaching") or context.get("teaching_continue")
        _plan_max_tokens = 4096 if _is_teaching else 1024
        path_output["stream_pending"] = {
            "messages": messages,
            "temperature": 0.5,
            "max_tokens": _plan_max_tokens,
            "use_safe": True,
            "chunk_size": 2,
        }

    # 如果有 DAG 规划结果，附加结构化数据供前端渲染
    if dag_plan:
        # 构建路径内知识点之间的边数据（用于 ECharts / vue-flow 力导向图）
        dag_edges: list[dict] = []
        if kg is not None and hasattr(kg, "edges"):
            for src, tgts in kg.edges.items():
                if src in all_path_concepts:
                    for tgt in tgts:
                        if tgt in all_path_concepts:
                            dag_edges.append({"source": src, "target": tgt})

        path_output["dag"] = {
            "phases": dag_plan.get("phases", []),
            "edges": dag_edges,
            "next_topics": dag_plan.get("next_topics", []),
            "recommendations": dag_plan.get("recommendations", []),
            "weak_points": dag_plan.get("weak_points", []),
            "summary": {
                "mastered_count": dag_plan.get("mastered_count", 0),
                "total_nodes": dag_plan.get("total_nodes", 0),
                "unlocked_count": dag_plan.get("unlocked_count", 0),
                "algorithm": dag_plan.get("algorithm", ""),
            },
            "review_schedule": path_review_schedule,
        }

    return {
        "current_agent": "path_agent",
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "path_agent": path_output,
        },
        # P0-fix: 正常规划(非教学)清除残留 teaching_context，防止 checkpoint 污染
        # 导致 path_join handler 误判 mode=="teaching" 触发教学自动推进链
        "teaching_context": None,
        # 仅当 LLM 未产出 stream_pending 时使用兜底文本
        "stream_buffer": "" if path_output.get("stream_pending") else fallback_path,
    }
