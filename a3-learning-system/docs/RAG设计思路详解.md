# RAG 设计思路详解 —— 从概念到实现

> 本文档面向学习者：每个专业名词都会拆开讲清楚它是什么、为什么需要、在你项目里对应哪段代码。

---

## 第一章：RAG 是什么，为什么要用

### 1.1 大模型的先天缺陷

大模型训练完那一刻，知识就冻结了。训练数据里没有的内容，它不会。更危险的是，它会**幻觉（Hallucination）**——对不知道的问题，它不是回答"不知道"，而是编造一个看起来合理的答案。

**你的 A3 项目如果不用 RAG**：用户问"Python 装饰器怎么用"，星火凭记忆回答，可能准确也可能编一个不存在的语法。

**用了 RAG 之后**：先从你的教材库里搜出"Python 官方文档 第5章 装饰器"，把这段原文塞到 Prompt 里，星火基于原文回答。准确率从"看运气"变成"几乎不编造"。

### 1.2 核心思想一句话

**在大模型回答之前，先翻资料库，找到相关内容，和问题一起给大模型。**

```
没有 RAG：用户问 → 大模型回答（纯记忆）

有 RAG：  用户问 → 检索资料库 → 找到相关段落 → 拼进 Prompt → 大模型基于资料回答
```

---

## 第二章：Embedding —— 把文字变成数学

### 2.1 为什么需要 Embedding

计算机只懂数字。要在几万段教材里找到"和用户问题意思相近"的段落，不能靠关键词匹配——用户问"怎么优化代码速度"，教材里写的是"性能调优方法"，关键词完全不重合但意思一样。

Embedding 就是把**任意文字 → 固定长度的浮点数数组（向量）**。语义相近的文字，向量也相近。

### 2.2 直观理解

想象一个三维空间（实际是 1024 维）：

```
"装饰器"      → [0.82, 0.71, 0.15, ..., -0.03]  (1024个数字)
"@语法"       → [0.79, 0.68, 0.18, ..., -0.01]  ← 和上面很接近
"天气预报"    → [-0.45, -0.33, 0.87, ..., 0.62]  ← 和上面完全不同
```

### 2.3 余弦相似度 —— 怎么算"相近"

两个向量夹角越小越相似。用余弦公式量化：

```
cos(θ) = (A·B) / (|A| × |B|)

值域 [-1, 1]：
  1   = 方向完全相同（意思一样）
  0   = 正交（无关）
  -1  = 方向完全相反
```

### 2.4 BGE 模型——谁来做这个转换

**BGE = BAAI General Embedding**，智源研究院训练的开源 Embedding 模型。

- **输入**：一段文字（如"Python 装饰器"）
- **输出**：一个 1024 维的浮点数数组
- **原理**：用数十亿条中英文文本训练出来的神经网络，学会了"把语义相近的文字映射到空间中相近的位置"

**你的项目当前用的是 BGE-large-zh-v1.5，升级方案是 BGE-M3**：

| | BGE-large-zh | BGE-M3 |
|------|------|------|
| 维度 | 1024 | 1024 |
| 最大输入 | 512 字 | 8192 字 |
| 语言 | 中英 | 100+ 语言 |
| 稀疏向量 | ❌ | ✅ 同时输出 BM25 稀疏向量 |

### 2.5 代码在哪

```python
# backend/app/services/rag_service.py
def _embed(texts: list[str]) -> list[list[float]]:
    model = _get_dense_model()   # 加载 BGE-M3 模型
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()
```

`normalize_embeddings=True` 把向量长度缩放到 1，这样余弦相似度可以直接用点积算（ChromaDB 内部就是这样做的）。

---

## 第三章：向量数据库 —— ChromaDB / FAISS

### 3.1 为什么需要专门的向量库

普通 MySQL 用 `WHERE name = 'xxx'` 做精确匹配。向量检索需要的是 **"找出和这个向量最相似的 K 个向量"**——这是完全不同的计算方式，需要专门的数据结构（向量索引）。

### 3.2 ChromaDB —— 你当前在用的

一个 Python 原生的轻量向量数据库。API 设计得像 Python 字典：

```python
# 存
collection.add(
    documents=["装饰器是一种高阶函数..."],
    embeddings=[[0.82, 0.71, ...]],  # 1024维向量
    ids=["doc_001"]
)

# 查
results = collection.query(
    query_embeddings=[[0.01, -0.34, ...]],  # 用户问题的向量
    n_results=3  # 返回最相似的3条
)
```

**核心概念 Collection**：就是向量库里的一张"表"。你的项目有 4 个 Collection：
- `knowledge_base`：教材正文切片
- `exercise_bank`：习题题库
- `concept_graph`：知识图谱节点
- `error_patterns`：错误模式

### 3.3 FAISS —— 升级方案

FAISS = Facebook AI Similarity Search，Meta 开源的生产级向量库。

和 ChromaDB 的区别：

| | ChromaDB | FAISS |
|------|------|------|
| 运行方式 | 独立服务（Docker） | Python 库（进程内） |
| 检索速度 | 中等 | 极快（C++ 实现） |
| 索引类型 | 1 种（HNSW） | 10+ 种（IVF/Flat/PQ/HNSW...） |
| 多子索引 | ❌ 不支持 | ✅ 可按学科分库 |
| 部署复杂度 | 简单 | 中等 |

**你的项目计划用 FAISS 按学科划分子索引**：

```
faiss_indices/
├── python_faiss.index        ← Python 相关教材
├── datastructure_faiss.index ← 数据结构教材
├── os_faiss.index             ← 操作系统教材
└── ...
```

用户问 Python 问题时，只检索 Python 子索引，速度快而且结果更相关。

### 3.4 代码在哪

```python
# backend/app/core/chroma_client.py  —— ChromaDB 客户端封装
def get_collection(name): ...
def add_to_collection(...): ...
def search_in_collection(...): ...
```

---

## 第四章：文本分块 —— Chunking

### 4.1 为什么不能整本书当一条

1. **大模型输入有限**：星火一次最多 8192 token，一整本教材几十万字塞不进去
2. **检索精度下降**：整本书的向量是"平均语义"，不如章节片段的向量精确
3. **相关性判断**：用户问的是"装饰器"，应该返回第 5 章那一段，不是整本书

### 4.2 切片三要素

| 参数 | 你的设置 | 为什么 |
|------|---------|------|
| 切片大小 | 320 字 | 太小语义不全，太大检索不精确 |
| 重叠度 | 15% | 防止关键信息正好被切在边界 |
| 分隔策略 | 段落优先 → 句子切分 | 保证切出来的都是完整语义单元 |

### 4.3 为什么需要重叠

```
原文: "...前面讲了变量。装饰器是一种高阶函数，它接受一个函数作为参数..."

没有重叠（切300字）:
  切片1: "...前面讲了变量。装饰"     ← "装饰"被截断了！
  切片2: "器是一种高阶函数，它..."   ← 前半截在切片1里

加了15%重叠:
  切片1: "...前面讲了变量。装饰器是一种高阶函数，它接受一个..." ← 完整语义
  切片2: "...高阶函数，它接受一个函数作为参数..."           ← 也完整
```

### 4.4 特殊内容的处理

**代码块**：以函数/类定义边界切分，不截断函数体，保证代码块完整可执行。

**公式**：以 `$$...$$` 或段落结束为边界，整个公式保留不拆散。

**表格**：整表保留，不按行拆分。

### 4.5 代码在哪

```python
# backend/app/services/rag_service.py
def chunk_text(text: str, chunk_size=320, overlap=48) -> list[dict]:
    """按段落边界分块，每块 ~320字，重叠 ~48字"""
```

---

## 第五章：混合检索 —— 三路融合

### 5.1 为什么需要多路检索

只用一种检索方式有盲区：

- **纯向量检索（稠密）**：理解语义，但对专有名词/精确术语匹配差
- **纯关键词检索（BM25）**：精确匹配好，但不理解同义词/改写

三路融合 = 各取所长。

### 5.2 第一路：稠密向量召回 —— 语义理解

**这是什么**：用户问题 → BGE-M3 向量化 → FAISS/ChromaDB 向量索引 → Top-30 候选。

**擅长**：同义改写。"怎么提升代码效率"能匹配到"性能调优方法"。

**不擅长**：精确术语。"@property"可能匹配到"房地产属性"（语义接近但无关）。

### 5.3 第二路：BM25 稀疏召回 —— 关键词匹配

**这是什么**：把文档和查询都切词 → 统计词频 → 计算 TF-IDF 分数 → Top-30 候选。

**TF-IDF 原理**：一个词在某个文档中出现频率高（TF 高），但在所有文档中少见（IDF 高），这个词在这个文档中的权重就大。

```
TF = 词在本文档中的次数 / 本文档总词数
IDF = log(总文档数 / 包含该词的文档数)
TF-IDF = TF × IDF
```

**擅长**："@property"精确命中只讨论 property 的段落。

**不擅长**："如何写得快"无法匹配"代码优化技巧"。

### 5.4 RRF 融合 —— Recriprocal Rank Fusion

两种方法各产出 Top-30 → 用 RRF 算法合并排名：

```
RRF_score(doc) = Σ 1/(k + rank_i)

k = 60（常数，防止单个极端排名主导结果）
rank_i = 在方法 i 中的排名
```

一个文档在稠密召回排第 3、BM25 排第 5 → 最终分数 = 1/63 + 1/65 ≈ 0.031。

### 5.5 第三路：Cross-Encoder 精排 —— 最精确但最慢

稠密和 BM25 都是"独立打分"——算出每个文档和查询的相关性分数后排序。Cross-Encoder 是"成对打分"——把 [查询, 文档] 作为一个整体输入模型，模型同时读两个文本后给出相关性判断。

**为什么只用在前 15 个**：Cross-Encoder 很慢，每个 [查询, 文档] 对都要跑一次模型。用在全部文档上不可行。所以它的角色是：粗排选出 Top-15 → Cross-Encoder 精排 → 取 Top-7。

### 5.6 完整流程

```
用户查询: "Python装饰器怎么实现"
│
├── ① 稠密召回 (BGE-M3 dense → FAISS) → Top-30
├── ② BM25召回 (jieba分词 + rank-bm25) → Top-30
│
├── ③ RRF 融合 (k=60) → Top-15 候选
│
├── ④ Cross-Encoder 精排 (BGE-Reranker-v2-m3) → 逐对打分
│
└── ⑤ 取 Top-7 最终结果
    每条结果包含: content(教材原文) + score(0~1) + metadata(来源/章节)
```

### 5.7 代码在哪

```python
# backend/app/services/rag_service.py
def hybrid_search(query, top_k=7, use_reranker=True) -> list[dict]:
    """三路融合检索：稠密 + BM25 + RRF + CrossEncoder → Top-K"""
```

---

## 第六章：Reranker —— 精排模型

### 6.1 和 Embedding 模型有什么区别

| | Embedding 模型 | Reranker 模型 |
|------|------|------|
| 输入 | 单段文字 | [查询, 文档] 成对输入 |
| 输出 | 一个向量 | 一个相关性分数 |
| 原理 | 独立编码每段文字 | 同时编码两段文字，判断它们的语义匹配度 |
| 速度 | 快（一次编码所有文档） | 慢（每对都要跑一次模型） |
| 精度 | 中 | 高 |
| 你的模型 | BGE-M3 | BGE-Reranker-v2-m3 |

### 6.2 为什么 Reranker 更准

Cross-Encoder 能利用"交叉注意力（Cross-Attention）"——查询和文档的每个词之间都建立注意力连接。比如查询里有"装饰器"，文档里有"@语法"，Cross-Encoder 能发现这两个词在上下文中指的是同一概念。Embedding 模型做不到这一点——它对每个文本独立编码，没有交叉注意力。

### 6.3 代码在哪

```python
# backend/app/services/rag_service.py
def _get_reranker():
    return CrossEncoder("BAAI/bge-reranker-v2-m3")

# 在 hybrid_search 中：
pairs = [[query, doc["content"]] for doc in candidates]
ce_scores = reranker.predict(pairs)  # 逐对打分
```

---

## 第七章：GraphRAG —— 知识图谱增强

### 7.1 普通 RAG 的局限

普通 RAG 是**扁平检索**——所有文档切片在同一个向量空间里，没有层次关系。用户问"学完 Python 基础后应该学什么"，普通 RAG 只能搜到相关片段，但不知道知识点之间的先后关系。

### 7.2 GraphRAG 的思路

在普通 RAG 之上加一层**知识点关系图谱**：

```
变量 → 函数 → 装饰器（必须按这个顺序学）
列表 → 列表推导式 → 生成器（生成器依赖前两者）
```

每个知识点是一个节点，前置依赖是一条有向边。路径规划 Agent 用拓扑排序输出学习路线。

### 7.3 怎么构建知识图谱

1. **提取知识点**：TF-IDF 关键词提取，每个知识点分配权重
2. **分析依赖关系**：在教材中，知识点 A 出现早于 B 且频繁共现 → A 是 B 的前置
3. **构建有向图**：Python `networkx` 或自定义 `KnowledgeGraph` 类
4. **拓扑排序**：入度为 0 的节点是第一阶段，移除后继续找入度 0 的节点

### 7.4 代码在哪

```python
# backend/app/services/knowledge_graph.py
class KnowledgeGraph:
    def extract_keywords(text)      # 提取知识点
    def build_from_texts(texts)     # 构建依赖图
    def topological_sort(known)     # 拓扑排序 → 分阶段学习路径
    def estimate_time(phases, hours) # 时间估算
```

---

## 第八章：评测体系

### 8.1 为什么需要评测

没有评测 = 不知道 RAG 好不好用。评测给你量化数据——召回率、准确率、幻觉率——答辩时说"我们达到 XX%"比"我们做得不错"有说服力一百倍。

### 8.2 核心指标

| 指标 | 英文 | 算法 | 目标 |
|------|------|------|:--:|
| 召回率 | Recall@K | 检索到的相关数 / 所有相关总数 | ≥88% |
| 精确率 | Precision@K | 检索到的相关数 / K | ≥80% |
| 答案准确率 | Accuracy | LLM回答和标准答案的语义一致率 | ≥83% |
| 幻觉率 | Hallucination | 回答中不属于检索文档的内容占比 | <9% |
| 忠实度 | Faithfulness | Ragas 评分，回答是否完全基于检索结果 | ≥0.88 |

### 8.3 Ragas —— 自动化评测框架

Ragas（Retrieval Augmented Generation Assessment）是专门评测 RAG 系统的 Python 库。

```python
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy

result = evaluate(
    dataset=test_dataset,       # 你的测试集：[{question, answer, contexts, ground_truth}, ...]
    metrics=[faithfulness, answer_relevancy]
)
```

它内部用 LLM 来打分：把生成的答案、检索到的上下文、标准答案一起给 LLM，让它判断答案是否忠实于上下文、是否相关。

### 8.4 评测集怎么建

你需要准备一组 {问题, 标准答案, 应该检索到的教材片段}：

```json
{
  "question": "Python 装饰器是什么",
  "ground_truth": "装饰器是接受函数作为参数并返回新函数的可调用对象...",
  "relevant_contexts": ["教材第5章 第142页: 装饰器是一种高阶函数..."]
}
```

从你的入库教材中人工抽 20 道题验证即可，答辩时不要求 420 道全做完。

---

## 第九章：学习路线 —— 你想深入哪部分

| 你想学 | 从哪开始 | 预计时间 |
|------|---------|:--:|
| Embedding 原理 | 第二章 → 看 BGE 论文摘要 | 2h |
| 向量数据库 | 第三章 → ChromaDB 官方 Quick Start | 1h |
| 混合检索怎么实现的 | 第五章 → 看 `hybrid_search()` 源码 | 1h |
| Reranker 为什么更准 | 第六章 → 理解 Cross-Attention | 30min |
| GraphRAG | 第七章 → NetworkX 拓扑排序教程 | 1h |
| 怎么评测 RAG | 第八章 → Ragas 官方文档 | 1h |
| 全部串一遍 | 按顺序读 → 看项目代码对应部分 | 4h |

---

## 附录：关键术语速查

| 术语 | 一句话 |
|------|------|
| RAG | 检索增强生成——回答前先查资料 |
| Embedding | 文字→向量 |
| 向量 | 一组浮点数，代表文字的语义 |
| 余弦相似度 | 两个向量的夹角越小越相似 |
| BGE | 智源的中文 Embedding 模型 |
| ChromaDB | Python 原生向量数据库 |
| FAISS | Meta 的生产级向量库 |
| Chunk/切片 | 把大文档切成小段 |
| Overlap/重叠 | 相邻切片间的共享内容 |
| BM25 | 基于词频的经典检索算法 |
| TF-IDF | 词频×逆文档频率，衡量词的重要性 |
| RRF | 融合多种检索排名的算法 |
| Cross-Encoder | 同时读查询和文档判断相关性 |
| Reranker | 精排模型——对粗排结果再做精细打分 |
| Top-K | 返回最相似的 K 个结果 |
| 幻觉 | 大模型编造不存在的事实 |
| Ragas | RAG 评测 Python 框架 |
| GraphRAG | 知识图谱增强的 RAG |
| 拓扑排序 | 有向无环图中的线性顺序 |
