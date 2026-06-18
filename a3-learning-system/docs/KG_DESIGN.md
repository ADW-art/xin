# 多学科知识图谱设计规范

> 参考标准：ACM/IEEE-CS/AAAI CS2023 Curricula + 国内教育知识图谱研究
> 设计原则：学科独立、4层递进、先修关系、Bloom认知分层、跨学科关联

---

## 一、统一框架

### 1.1 文件结构

每个学科一个独立 JSON 文件 `kg_{domain}.json`：

```json
{
  "domain": "学科标识",
  "name": "学科中文名",
  "cs2023_area": "对应CS2023知识领域",
  "phases": [ 4个阶段定义 ],
  "nodes": [ 知识点节点 ],
  "edges": [ 学科内先修关系 ],
  "cross_domain_edges": [ 跨学科依赖关系 ]
}
```

### 1.2 四层递进阶段

| 阶段 | 名称 | Bloom层级 | 说明 |
|------|------|-----------|------|
| `foundation` | 入门基础 | Remember/Understand | 概念认知、环境搭建、基本语法 |
| `core` | 核心能力 | Apply | 核心API/库/框架的使用能力 |
| `advanced` | 进阶深入 | Analyze/Evaluate | 原理理解、性能优化、架构设计 |
| `practice` | 工程实战 | Create | 项目实战、综合应用、最佳实践 |

### 1.3 知识点节点结构

```json
{
  "id": "{domain}:{short_name}",
  "name": "知识点中文名",
  "phase": "foundation|core|advanced|practice",
  "difficulty": 1-5,
  "blooms": "remember|understand|apply|analyze|evaluate|create",
  "hours": 预计学习小时数,
  "description": "一句话描述",
  "prerequisites": ["前置节点id列表"],
  "keywords": ["用于文本匹配的关键词列表"]
}
```

### 1.4 边的类型

- `prerequisite` — 必须先掌握source才能学target
- `extends` — target是source的深入/扩展
- `relates_to` — 相关但不强制先后

### 1.5 跨学科边

```json
{
  "source": "{domain}:{node_id}",
  "target": "{other_domain}:{node_id}",
  "relation": "enables|depends_on|complements",
  "description": "关系说明"
}
```

---

## 二、10 个学科及其 CS2023 对齐

| 学科 | domain | CS2023 知识领域 | 节点数(目标) |
|------|--------|-----------------|:--:|
| Python 编程 | python | SDF / FPL | 35-40 |
| C++ 编程 | cpp | SDF / FPL / SPD | 30-35 |
| Java 编程 | java | SDF / FPL / SE | 35-40 |
| 数据结构与算法 | algorithm | AL | 40-45 |
| 机器学习 | ml | AI / MSF | 40-45 |
| 计算机网络 | network | NC | 25-30 |
| 数据库系统 | database | DM | 25-30 |
| 计算机系统 | system | AR / OS / SF | 30-35 |
| 前端开发 | frontend | GIT / HCI / SPD | 40-45 |
| Go 语言 | go | SDF / PDC | 25-30 |

---

## 三、跨学科依赖关系

```
Mathematics ──→ Algorithm ──→ Machine Learning
    │               │               │
    └──→ System ←───┤               │
    │               │               │
Python ──→ ML ──────┤               │
    │               │               │
    └──→ Database ←─┘               │
    │                               │
    └──→ Network ←──────────────────┘
    
C++ ──→ System ──→ Algorithm
Java ──→ Database ──→ Frontend(backend)
```

---

## 四、设计参考来源

1. **ACM/IEEE-CS/AAAI CS2023**: 17 Knowledge Areas, 4-level Bloom's taxonomy
2. **北京信息科技大学 课程体系知识图谱**: Neo4j先修关系模型
3. **基于MOOC的高等教育知识图谱构建**: KNN分类 + 年级分层
4. **国防科技大学 第一性原理驱动课程图谱**: 知识锚点→隐性方法论→能力体系
5. **CS2023 Skill Levels**: Explain → Apply → Evaluate → Develop
