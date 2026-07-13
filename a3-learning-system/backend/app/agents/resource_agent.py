"""
Resource Agent — 根据用户画像 + 当前知识点生成个性化学习资源

资源类型：
1. document      → 结构化知识文档
2. mindmap       → Markdown 标题层级（前端 markmap 渲染为导图）
3. question_set  → 3-5 道练习题，含答案解析
4. code_example  → 可执行代码案例
5. video_script  → 5 分钟讲解脚本
"""

import json
import logging
import re

import jieba

from app.agents.state import AgentState
from app.agents._msg_compat import last_msg_content  # 兼容 checkpoint 恢复后 dict 格式
from app.services.rag_service import retrieve_context, hybrid_search
from app.services.spark_client import SparkClient
from app.services.sse_bridge import StreamRequest, stream_request_to_dict

logger = logging.getLogger(__name__)

#英文key转化为中文
TYPE_LABELS = {
    "document": "知识文档",
    "mindmap": "思维导图",
    "question_set": "练习题",
    "code_example": "代码案例",
    "video_script": "讲解脚本",
    "reading_material": "扩展阅读",
    "diagram": "图解说明",
    "smart_tutoring": "智能辅导",
    "comparison": "对比分析",
    "notebook": "Notebook 交互案例",
    "audio_lecture": "AI 语音讲解",
    "video_animation": "AI 动画视频",
    "visual_diagram": "AI 知识图解",
}
#核心prompt模板
RESOURCE_PROMPT = """你是一个个性化学习资源生成专家，风格对标 Khan Academy + LeetCode 官方题解。

## 核心铁律（违反即为不合格输出）
1. **不写维基百科式空洞定义** — 每个概念必须配代码示例+运行结果
2. **不写"XXX很有用"** — 必须说出具体在哪里用、怎么用、什么时候不该用
3. **不写"顾名思义"** — 不要把读者当傻子，用代码和例子说清楚
4. **不写"试着自己练习"** — 给具体题目描述、输入输出要求、难度标签
5. **不跳过运行结果** — 每个代码块后面必须紧接一个独立的 ``` 代码块展示实际输出
6. **全文至少3个代码块** — 少于3个即为不合格，每个至少有运行结果
7. **禁止在代码行内写 # 输出：注释猜测运行结果** — 这是最严重的错误
   - 错误示范：`print(fruits)  # 输出：['apple', 'banana']` ← 这行注释99%是错的！
   - 错误示范：`print(x)  # 输出：42` ← 不要猜输出！用独立代码块展示！
   - 正确做法：代码块只写代码（不写输出注释），之后用独立 ``` 代码块展示真实输出
   - 原因：你无法知道代码在真实环境中的确切输出，猜错会误导学生
8. **不要给代码行加行尾注释猜测返回值** — `x.pop()  # 返回'banana'` 这种全是错的
   - 如果想说明返回值，用独立文本段落说明，不要放在代码行尾
9. **每个代码块后必须紧跟运行结果** — 用独立 ``` 块展示，不要用注释猜

## 学生画像
{profile_text}

## 当前学习需求
{topic}

## 要生成的资源类型：{type_label}
{type_guide}

{references}{rag_rule}

## 教程结构（每份文档必须完整包含，缺一不可）

### 第1部分：概述
- 用1-2句话精准定义概念，说明它解决什么问题
- 格式示范：「{{概念名称}}让你能够...（说明具体能力或解决的问题）」
- 错误示范：「XXX是XXX中一种重要的设计模式」（没说为什么重要、怎么用）
- 禁止："XXX是一种特殊的..."（这种定义等于没定义）

### 第2部分：核心概念
- 将主题拆解为2-4个核心子概念
- **每个子概念配一个代码示例**
- 格式：子概念名称 → 一句话说明 → 代码块 → 运行结果 → 1句话解释
- 代码块必须使用 ```语言 语法标注（```python, ```javascript, ```cpp, ```java 等）

### 第3部分：代码实战
- 一个完整的综合示例，展示多个核心概念如何组合使用
- 包含文件头注释说明目的和运行环境
- 关键行必须加行内注释解释为什么这样写（不是重复代码内容）
- **运行结果**紧跟代码块，用 ``` 代码块展示实际输出（不是描述输出）

### 第4部分：常见陷阱
- 至少列出2个真实常见错误
- 每个陷阱严格格式：
  **陷阱名称**：一句话说清楚坑在哪
  ```语言
  # 错误写法
  ```
  **为什么错**：1句话解释原因
  ```语言
  # 正确写法
  ```
  **运行结果**：展示正确写法的输出

### 第5部分：练习
- 至少2道具体题目
- 每道题格式：
  **题目N**（难度：简单/中等/较难，考察：[知识点列表]）
  [具体题目描述 - 包含输入输出要求、约束条件]
- 禁止："尝试修改上面的代码"（太模糊）
- 禁止："试着实现一个XXX"（没有约束条件等于没出）

### 第6部分：下一步
- 推荐1个具体的下一步学习知识点
- 说明为什么它是自然的下一步（如"掌握列表基础操作后，可以学习列表推导式和生成器表达式，它们能让代码更简洁"）

## 内容质量标准
{difficulty_rule}

## 编程语言与约束（系统内部指令，不要输出给用户）
- 必须使用对话历史中用户指定的编程语言（C++→C++，Java→Java，JavaScript→JavaScript，Python→Python）
- 即使本轮消息未明确提及语言，也要沿用对话历史中已确立的语言
- 如果对话历史中有排除约束（"不要递归""不用算法""只用基础语法""不要第三方库"），必须严格遵守
- 代码必须能直接复制运行，不含占位符（# TODO / pass / ...）

## 回复格式
- 返回纯 Markdown，不要套 ```markdown 外壳
- 正文结束后，**必须**用 > 引用格式加一句自然的追问引导（必须包含「下一步」或「继续」）：
  - 教完概念后：「> 这个概念清楚了吗？下一步要不要我出两道题帮你巩固一下？」
  - 生成代码后：「> 代码可以直接跑。接下来想继续学 XX 的进阶用法，还是换一个主题？」
  - 完成教程后：「> 学得不错！建议继续学习 [具体知识点]，需要我接着讲吗？」
  - **禁止不写引导语就结束回复**

## 图解说明（必须包含）
- **当涉及以下内容时必须插入 Mermaid 图表**：
  · 比较/对比多个概念时 → 用 ```mermaid graph TD 绘制关系图
  · 解释算法流程时 → 用 ```mermaid flowchart LR 绘制流程图
  · 展示数据结构关系时 → 用 ```mermaid graph TD 绘制结构图
  · 总结知识点层次时 → 用 ```mermaid mindmap 绘制思维导图
- 示例：
```mermaid
graph TD
    A[输入数据] --> B[处理步骤1]
    B --> C[处理步骤2]
    C --> D[输出结果]
```
- 图表后紧跟1-2句文字解读
- **禁止在 mermaid 中写中文标签时加引号（除非含特殊字符）**
- **如果内容不适合图解则跳过，不要强行插入**

---

## ⚠️ 强制检查清单（你的回复必须包含以下每一项，缺一不可）

**绝对禁止的做法（这些是不合格的输出）**：
- 只给代码不给练习 → 不合格
- 只讲概念不给陷阱 → 不合格
- 练完不给下一步推荐 → 不合格
- 代码没有运行结果 → 不合格

**强制包含清单**：
1. ### 概述 — 精准定义（1-2句话），说明解决什么问题
2. ### 核心概念 — 至少2个子概念，每个配代码块+运行结果
3. ### 代码实战 — 完整综合示例，关键行注释解释设计决策
4. ### 常见陷阱 — 至少2个：错误示例 → 为什么错 → 正确写法
5. ### 练习 — 至少2道具体题目，标注难度和考察知识点
6. ### 下一步 — 推荐1个具体下一步知识点+原因

每个部分都必须使用 ### 标题，代码块使用 ```语言 标记。
**少任何一部分，这份输出就是废品。**

## 格式参考（仅展示结构，实际生成时根据用户请求替换所有内容）

### 概述
{{概念名称}}让你能够...（1-2句话精准定义，说明解决什么问题）

### 核心概念
**子概念1**: 一句话说明
```python
# 代码示例
```
```
运行结果
```
一句话解释

### 代码实战
综合示例，把多个核心概念串起来

### 常见陷阱
**陷阱1: 名称**: 错误示例 → 为什么错 → 正确写法

### 练习
**题目1** (难度, 考察: 知识点列表)
具体题目描述

### 下一步
> 推荐下一步学习内容和原因，需要我接着讲吗？"""

TYPE_GUIDES = {
    "document": """生成一份完整的教程文档，必须严格包含以下6个部分：

## [概念名称]

### 概述
1-2句话精准定义，说明概念解决什么问题、什么时候该用、什么时候不该用。
禁止：维基百科式定义（"XXX是一种特殊的..."）。必须具体。

### 核心概念
- 将主题拆解为2-4个核心子概念
- 每个子概念配独立代码示例：代码块 → 运行结果 → 一句话解释
- 至少3个 ```语言 代码块，每个跟运行结果

### 代码实战
- 一个完整的综合示例，把多个核心概念串起来
- 包含头注释（说明目的、运行环境、输入输出）
- 关键行加注释解释设计决策（不是重复代码内容）
- 运行结果紧跟代码块

### 常见陷阱
至少2个真实易错点，每个格式：
1. **陷阱名称**: 错误示例 → 为什么错 → 正确写法（用对比代码块）

### 练习
至少2道具体题目，每道包含：
- 题目描述（明确输入/输出/约束）
- 难度标签：[简单/中等/较难]
- 考察知识点列表

### 下一步
推荐一个具体的下一步知识点，说明为什么是自然延续""",

    "mindmap": """生成 Markdown 标题层级结构（前端 markmap 渲染为思维导图）。

严格格式要求：
- # 根节点 = 主题名（必须包含具体技术术语，如「Python列表与元组」不是「列表」）
- ## 核心分类（如「基础机制」「核心应用」「高级模式」「常见误区」）
- ### 具体知识点（如「@语法糖本质」「闭包捕获自由变量」）
- #### 细节/示例（如「示例：list.append() 添加元素」「示例：list.sort() 排序」）

节点要求：15-30个，每个节点标签必须是具体技术术语。
禁止使用模糊标签：禁止「其他」「更多」「等等」「扩展」「进阶」（用具体术语替代）
节点命名示范：禁止「基础知识」→ 允许「变量作用域与闭包」；禁止「常见问题」→ 允许「循环引用与内存泄漏」

建议：### 和 #### 节点附带括号注明语言/框架，如「@wraps保留元信息 (Python)」""",

    "question_set": """生成 3-5 道精心设计的练习题，每道题必须包含以下完整字段：

每道题格式模板：
```
### 第 N 题 — [选择题/代码阅读/代码编写] — 难度：[简单/中等/较难] — 预计 [2-10] 分钟

**考察知识点**：[知识点1, 知识点2, 知识点3]

[题目正文]
- 选择题：必须列出 A/B/C/D 四个完整选项，每个选项有具体技术内容
- 代码阅读题：给出完整代码，问输出什么
- 代码编写题：给函数签名 + 输入输出示例 + 约束条件

> **答案**：[正确答案或完整代码]
> **解析**：逐选项/逐行解释对错 + 标注易错点
```

题型分布：至少1道代码阅读题 + 至少1道代码编写题
禁止：死记硬背题（"以下哪个是XXX的定义"）、选项含臆造概念、无输入输出示例的代码题""",

    "code_example": """生成一个完整的、可直接运行的代码文件。

必须包含：
1. 文件头注释块：代码目的、语言版本要求、依赖（标注"仅标准库"或列出第三方库）、输入输出说明
2. 清晰的代码结构：导入 → 配置/常量 → 核心函数（带 docstring）→ main 入口 → `if __name__ == '__main__'`
3. 关键决策点注释：解释算法选择、数据结构选择、边界处理（注释要解释"为什么"而不是"是什么"）
4. 运行结果：代码块后必须紧跟一个 ``` 代码块展示完整输出
5. 算法复杂度：如涉及算法，在文件头注释中标注时间/空间复杂度
6. 错误处理：不忽略异常，给出合理的错误提示

格式模板：
```python
# ============================================================
# 功能：XXX
# 语言：Python 3.9+
# 依赖：标准库（无第三方依赖）
# 时间复杂度：O(n log n)  空间复杂度：O(n)
# ============================================================
# ... 完整代码 ...
```

绝对禁止：
- 占位符：# TODO / pass / ... / 此处省略
- 不完整的导入语句
- 有代码无输出结果
- 代码不能直接运行（缺少 import、变量未定义等）""",

    "reading_material": """输出格式严格遵循如下结构：
1. 推荐主题与学习理由（与本主题和用户画像的关联）
2. 3-5篇推荐阅读（书名/文章名 + 作者 + 推荐原因 + 难度）
3. 阅读顺序建议
4. 延伸方向和关键词

注意：
- 只能推荐真实存在的书籍、论文和技术文档（如Python官方文档、算法导论、CSAPP等知名教材）
- 严禁编造不存在的参考资料
- 必须说明每项推荐与当前学习主题的关联性
- 难度标注：入门/中等/进阶
""",
    "video_script": """生成「互动式教程」—— 对标 Khan Academy 视频讲解风格的结构化教程。

## 教程格式（三步递进，必须完整）

### 第一步：场景引入
- 用 2-3 句话设定一个具体的学习场景（如「假设你要给网站添加用户登录功能...」）
- 说明这个知识点在实际项目中的位置
- 提出一个核心问题，引导学生思考

### 第二步：分步讲解（3-5步，每步必须配代码）
每步格式：
**Step N — [具体操作名称]**（预计 1-2 分钟）
- 这一步要做什么
- 代码示例（```语言 代码块）
- 运行结果（``` 输出块）
- [思考] 提出一个引导学生理解的小问题

### 第三步：总结与挑战
- 用 3-5 个要点总结核心收获
- 给出一个具体的进阶挑战任务（可独立完成）
- 使用 ```mermaid flowchart 绘制本教程的知识结构图

## 禁止事项
- 禁止生成纯概念描述（每一步必须有代码）
- 禁止跳过运行结果
- 禁止挑战任务过于模糊（必须有输入输出要求）""",

    "comparison": """生成对比分析文档，严格按以下格式：

1. **表格对比**（至少 4 列 × 3 行，用 Markdown 表格）：
   | 对比维度 | 方案A | 方案B | 选型建议 |
   维度包括但不限于：性能、内存、可读性、适用场景、社区生态

2. **每项差异配最小代码示例**（不超过 8 行）：
   - 方案A 典型写法
   - 方案B 典型写法
   - 同一场景下的对比（输入相同、输出相同）

3. **选型决策树**：
   - 用条件判断句式给出明确建议
   - 格式：「如果 XXX，选择 A；如果 YYY，选择 B」
   - 禁止：「各有优劣」（等于没说）

4. **总结表**：一行总结什么时候用什么""",

    "diagram": """生成 Mermaid 图解的 Markdown 文档。

严格格式要求：
1. **图示标题与说明**：用1-2句话说明图解的用途和适用场景
2. **Mermaid 代码块**：输出至少 1 个 Mermaid 图表代码块（```mermaid）
   - 流程图 (flowchart/graph)：展示流程、决策分支
   - 时序图 (sequenceDiagram)：展示交互过程
   - 类图 (classDiagram)：展示类关系和继承结构
   - 状态图 (stateDiagram)：展示状态转移
3. **图表解读**：对每个图表用3-5句话说明关键节点和逻辑
4. **相关概念连接**：说明图中各元素在实际应用中的对应关系

图表内容要求：
- 节点标签必须使用具体技术术语（禁止"其他""等等"）
- 至少包含 6 个节点
- 节点间关系标注要清晰
- 如涉及算法流程，标注时间/空间复杂度""",

    "smart_tutoring": """生成「文字解答 + 图解说明 + 短视频讲解」三合一智能辅导包。

这是三种模态的组合输出，必须用 `---SECTION---` 分割三个部分：

---SECTION---
## 第一部分：文字解答

用 3-5 段结构化讲解核心概念，包含：
- 概念定义与适用场景
- 至少 2 个代码示例（每个附带运行结果）
- 常见误区和正确写法
- 至少 1 个练习题

---SECTION---
## 第二部分：图解说明

用 1 个 Mermaid 图表总结核心流程：
```mermaid
flowchart TD
  A[起点] --> B[步骤1]
  ...
```
图表至少包含 6 个节点，标注关键决策点。

---SECTION---
## 第三部分：短视频讲解脚本

生成 3-5 分钟的讲解脚本，格式：
### 场景引入（30秒）
### 分步讲解（2-3分钟，每步标注预计时长）
### 总结与挑战（30秒）

禁止事项：
- 禁止三个部分内容重复（每部分从不同角度讲解）
- 图解部分必须用 Mermaid 代码块
- 视频脚本必须有明确的时间标注""",

    "notebook": """生成 Jupyter Notebook 交互式代码案例。

输出格式要求：
- 使用 Markdown 格式，```python 代码块将自动转为 notebook code cells
- 解释性文本将自动转为 notebook markdown cells

内容结构：
1. **标题与概述** — 用 # 标题说明本 notebook 的目的和适用场景
2. **环境准备** — 用 ```python 代码块展示 import 和配置
3. **分步讲解** — 每个核心概念配一个 markdown 说明段落 + 一个 ```python 代码块
4. **综合实战** — 一个完整的 ```python 代码块，展示多个概念组合使用
5. **练习挑战** — 至少 2 个练习，每个用 markdown 描述题目 + ```python 代码骨架

代码要求：
- 每个 ```python 代码块必须可独立运行
- 包含必要的 import 语句
- 关键行加注释解释设计决策
- 禁止使用 pass / TODO / ... 占位符
- 至少包含 4 个 ```python 代码块""",

    "audio_lecture": """生成适合语音朗读的讲解稿。

语音讲解不同于文本文档，必须遵循口语化原则：

格式要求：
1. **标题** — 用 # 标题，简洁明了
2. **引入** — 用 2-3 句口语化开场白（如"今天我们来学习..."）
3. **核心讲解** — 分 3-5 个自然段，每段讲一个要点
4. **总结** — 用 2-3 句总结核心收获
5. **引导** — 用 1-2 句自然引导下一步学习

口语化规则：
- 句子短小精悍（每句不超过 30 字）
- 使用口语连接词（"那么""比如说""接下来""好"）
- 避免长串代码（只讲思路，不讲语法细节）
- 避免复杂表格和数学公式
- 用类比和举例代替抽象描述
- 全文控制在 800-1500 字（约 3-5 分钟朗读时长）
- 禁止使用 Markdown 代码块（语音无法朗读代码）
- 禁止使用表格、Mermaid 图表

示例风格：
"今天我们来学习 Python 中的列表推导式。这个概念听起来可能有点绕，但其实它可以让你用一行代码完成原本需要三四行循环才能做到的事情。比如说，你想从一个列表中筛选出所有的偶数..." """,

    "video_animation": """生成 AI 动画视频脚本。

为视频生成模型（如 SeeDance）准备结构化的视频脚本：

## 脚本结构

### 场景 1：标题引入（5-8 秒）
- 大标题文字 + 简洁背景描述
- 配旁白：1 句话说明主题

### 场景 2-N：分步讲解（每场景 8-15 秒）
每场景包含：
- **画面描述**：具体描述画面中应该出现什么（文字、图形、动画效果）
- **旁白文本**：该场景的语音讲解（1-3 句）
- **字幕文本**：画面底部显示的关键文字

### 场景 N+1：总结回顾（5-8 秒）
- 要点总结文字 + 旁白收尾

## 画面描述规范
- 使用具体视觉描述（"蓝色背景上出现 Python 图标"而非"显示 Python"）
- 每场景描述不超过 3 行
- 标注颜色偏好：蓝白配色为主，代码区域深色背景
- 动画效果：淡入(fadeIn)、滑入(slideIn)、放大(zoomIn)

## 禁止事项
- 禁止场景数超过 10 个（控制在 2-3 分钟）
- 禁止单场景旁白超过 50 字
- 禁止画面描述过于抽象（必须可执行）""",

    "visual_diagram": """生成 AI 知识图解 —— 图文结合的知识点可视化讲解。

重要: 本类型的核心输出是"适合生成配图的画面描述 + 文字讲解"的组合。

## 输出结构

每节包含两个部分:

### 图解描述 (用 [IMAGE_PROMPT] 标记)
为 AI 图像生成模型提供详细的画面描述, 要求:
- 蓝白配色为主的教育风格信息图
- 具体描述: 元素位置/大小/颜色/文字内容
- 适合中文教育场景, 文字用中文标注
- 画面描述控制在 60-120 字 (Spark 图像生成 API 限制)
- 禁止抽象描述: 必须具体到"左上角放XX图标, 中间用蓝色粗体写YY, 底部用箭头连接ZZ"

### 文字讲解 (用 [EXPLANATION] 标记)
对该图解的配套文字说明, 2-4 句即可。

## 完整示例

[IMAGE_PROMPT]
蓝色渐变背景的信息图。顶部居中用白色粗体字写"二叉树遍历三种方式"。中部从左到右排列3个圆角矩形框, 分别标注"前序: 根左右"、"中序: 左根右"、"后序: 左右根"。每个框用不同深浅蓝色区分, 框之间用白色箭头连接。底部用灰色小字标注"三种遍历的核心区别在于访问根节点的时机"。
[/IMAGE_PROMPT]

[EXPLANATION]
二叉树遍历是数据结构中的核心操作。前序遍历先访问根节点再左右子树, 适合复制树结构。中序遍历按左-根-右顺序, 对二叉搜索树会得到有序序列。后序遍历最后访问根节点, 适合删除树。理解这三种方式的关键是记住"根节点什么时候被访问"。

## 数量要求
- 至少输出 3 组 [IMAGE_PROMPT] + [EXPLANATION] 对
- 每组覆盖核心概念的一个方面
- 组与组之间用 --- 分隔""",
}


def _normalize_title(raw: str) -> str:
    """Extract a clean display title from user-message-like topics.

    Strips prefixes (e.g. "教我"/"帮我"/"解释一下") and suffixes
    (e.g. "是什么"/"怎么用") and removes code-added annotations.

    Examples:
        "教我Python闭包"            → "Python闭包"
        "给我讲一下C++指针（使用C++语言）" → "C++指针"
        "解释一下什么是链表"          → "链表"
        "帮我写一下排序算法的代码"     → "排序算法"
    """
    if not raw or len(raw) < 2:
        return raw

    text = raw.strip()

    # Remove code-added annotations: （使用XXX语言）, （排除：XXX）
    text = re.sub(r'[（(][^）)]*[）)]', '', text).strip()

    # ── Strip common user-message prefixes ──
    text = re.sub(
        r'^(?:教|给|帮|请)(?:我|你|您)?(?:讲|解释|介绍|讲解|说明|告诉|教|学|写)?(?:一下|下)?(?:关于|这个|那个)?',
        '', text
    ).strip()
    text = re.sub(
        r'^(?:我想?|我要|帮我|给我|请你?|麻烦)(?:学|了解|知道|看看|理解|掌握|做|写)?(?:一下|下)?(?:关于|这个|那个)?',
        '', text
    ).strip()
    text = re.sub(
        r'^(?:什么(?:是|叫)|怎么(?:用|学|做|写|理解)|如何(?:用|学|做|写|理解))',
        '', text
    ).strip()
    text = re.sub(
        r'^(?:能否|可以|能|能不能|可不可以)(?:给我|帮我|为我)?(?:讲|解释|介绍|讲解)?(?:一下|下)?(?:关于|这个|那个)?',
        '', text
    ).strip()

    # ── Strip common user-message filler suffixes only ──
    # 仅删除真正的无意义语气后缀，保留"原理""机制""源码"等有信息量的词
    text = re.sub(
        r'(?:一下|一下你|吧|吗|呢|啊|哦|呀|嘛|呗)\s*$',
        '', text
    ).strip()

    return text if len(text) >= 2 else raw


def resource_agent_node(state: AgentState, spark: SparkClient) -> dict:
    """资源生成 Agent 的主逻辑 — 含教学流程感知"""
    state = AgentState.model_validate(state)
    state = dict(state)  # TypedDict → dict
    profile = state.get("user_profile") or {}
    context = state.get("context", {})
    topic = context.get("topic", last_msg_content(state.get("messages", [])))

    # 教学流程感知：获取当前节点和下一节点信息
    teaching_context = state.get("teaching_context") or {}
    is_teaching = teaching_context.get("mode") == "teaching"
    teaching_next_node: str = ""
    if is_teaching:
        active_path = teaching_context.get("active_path", [])
        current_idx = teaching_context.get("current_index", 0)
        if current_idx + 1 < len(active_path):
            teaching_next_node = active_path[current_idx + 1]

    # 读取话题上下文（用户语言偏好 + 排除约束）
    topic_ctx = context.get("topic_context", {})
    user_lang = topic_ctx.get("user_language", "")
    user_constraints = topic_ctx.get("user_constraints", [])

    # 保存原始话题用于 RAG 检索（不带语言/约束后缀）
    rag_topic = topic

    # 如果用户指定了语言，在主题中标注
    if user_lang:
        topic = f"{topic}（使用{user_lang}语言）"
    if user_constraints:
        exclude_text = "、".join(user_constraints)
        topic = f"{topic}（排除：{exclude_text}）"

    # 从画像中提取关键信息 → 拼进 Prompt
    profile_lines = [] #只拼接有值的
    if profile.get("knowledge_base"):
        profile_lines.append(f"知识基础：{profile['knowledge_base']}")
    if profile.get("cognitive_style"):
        profile_lines.append(f"认知风格：{profile['cognitive_style']}")
    if profile.get("learning_goal"):
        profile_lines.append(f"学习目标：{profile['learning_goal']}")
    if profile.get("preferred_resource_type"):
        profile_lines.append(f"偏好资源类型：{profile['preferred_resource_type']}")

    profile_text = "\n".join(profile_lines) if profile_lines else "暂无画像信息，按通用方式生成"
    #"\n".join-->把列表的每个元素用\n连接成一个字符串

    # RAG 检索：从知识库中查找与当前主题相关的教材片段
    # BGE 未就绪时跳过 RAG，直接 LLM 生成（避免首次请求超时）
    references = ""
    rag_degraded = False
    from app.services.rag_service import is_rag_ready
    if is_rag_ready():
        try:
            references = retrieve_context(rag_topic, n=3)
            if references:
                logger.info("ResourceAgent: RAG 检索到参考资料（主题=%s）", rag_topic)
        except Exception as e:
            logger.warning("ResourceAgent: RAG 检索失败: %s", e)
    else:
        rag_degraded = True
        logger.info("ResourceAgent: BGE 未就绪，跳过 RAG 检索 (纯 LLM 生成)")

    # Content Store 降级：轻量教材库作为备选知识注入（不依赖 BGE 模型）
    if not references:
        try:
            from app.services.content_store import search_content, is_content_ready, load_content_store
            load_content_store()  # 惰性初始化（已加载则直接返回）
            if is_content_ready():
                store_results = search_content(rag_topic, top_k=3)
                if store_results:
                    references = "\n\n".join(
                        f"[教材：《{r['title']}》] {r['content'][:200]}"
                        for r in store_results[:2]
                    )
                    logger.info("ResourceAgent: 教材库检索到 %d 条参考资料（主题=%s）", len(store_results), topic)
        except Exception:
            pass  # 教材库不可用时静默跳过，不影响主流程

    # 根据画像偏好决定资源类型，默认生成文档
    # 但用户显式请求优先（如"生成思维导图"→mindmap）
    pref = profile.get("preferred_resource_type", "text")
    pref_map = {"video": "video_script", "code": "code_example", "text": "document", "interactive": "question_set"}
    resource_type = pref_map.get(pref, "document")

    # 用户显式资源类型请求覆盖画像偏好
    user_msg = last_msg_content(state.get("messages", []))
    override_map = {
        "思维导图": "mindmap", "脑图": "mindmap", "导图": "mindmap", "mindmap": "mindmap",
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
    # jieba 分词后集合匹配 — O(n+m) 代替 O(n*m) 子串扫描，消除短词误匹配
    tokens = set(jieba.cut(user_msg)) if user_msg else set()
    for keyword, rtype in sorted(override_map.items(), key=lambda x: -len(x[0])):
        if keyword in tokens or (len(keyword) >= 3 and keyword in user_msg):
            resource_type = rtype
            logger.info("ResourceAgent: 用户显式请求类型=%s (关键词=%s)", rtype, keyword)
            break

    type_label = TYPE_LABELS.get(resource_type, "学习资源")

    # ── 标题规范化：清理用户消息式的话题 ──
    clean_title = _normalize_title(topic)
    if clean_title != topic:
        logger.info("ResourceAgent: 标题规范化 '%s' → '%s'", topic, clean_title)

    # ── 类型指南动态增强 ──
    type_guide = TYPE_GUIDES[resource_type]

    # 数据结构/算法主题 → 要求输出 ASCII 可视化
    _ds_algo_keywords = [
        "链表", "栈", "队列", "树", "图", "堆", "哈希", "排序", "查找", "搜索",
        "二叉树", "红黑树", "B树", "B+树", "AVL", "Trie", "跳表", "并查集",
        "linked list", "stack", "queue", "tree", "graph", "heap", "hash",
        "sort", "search", "binary tree", "linkedlist", "双指针", "滑动窗口",
        "递归", "回溯", "动态规划", "贪心", "分治", "前缀和", "单调栈", "单调队列",
        "反转链表", "合并", "环检测",
    ]
    if any(kw in topic.lower() for kw in _ds_algo_keywords):
        type_guide += (
            "\n\n**ASCII 可视化要求**：请用 ASCII 字符画来辅助说明数据结构或算法流程。"
            "例如用箭头(→ ← ↑ ↓)、分隔线(┌ ─ ┐ │ └ ┘)、方向指示符"
            "来绘制内存布局、指针变化或算法步骤。至少包含 1 个 ASCII 示意图。"
        )

    # 难度适配规则：根据画像中的知识基础自动调整
    kb_data = profile.get("knowledge_base", {})
    if isinstance(kb_data, dict) and kb_data:
        scores = [v for v in kb_data.values() if isinstance(v, (int, float))]
        if scores:
            avg_score = sum(scores) / len(scores)
            # P1-FIX: 自动检测标度 (1-10 vs 百分制), 统一归一化到 1-10
            _max_score = max(scores)
            if _max_score > 15:
                avg_score = avg_score / 10  # 百分制 → 1-10
            if avg_score >= 7:
                difficulty_rule = "学生水平较高（自评均分 {:.0f}/10），减少基础解释，增加进阶内容和高级用法。代码示例可以直接展示最佳实践，不必从零讲起。".format(avg_score)
            elif avg_score >= 4:
                difficulty_rule = "学生处于中等水平（自评均分 {:.0f}/10），保持基础概念讲解，但可以适度引入进阶话题。代码示例要有适当注释。".format(avg_score)
            else:
                difficulty_rule = "学生处于入门阶段（自评均分 {:.0f}/10），每个概念要从最基础讲起，代码注释要详尽，多用类比辅助理解，避免跳步。".format(avg_score)
        else:
            difficulty_rule = "学生画像中无有效知识基础数据，按入门水平讲解：每个概念从基础讲起，代码注释详尽，多用类比辅助理解。"
    else:
        difficulty_rule = "学生画像中无知识基础数据，按入门水平讲解：每个概念从基础讲起，代码注释详尽，多用类比辅助理解。"

    # P2 (2026-07-13): 不注入画像引导 — 用户明确请求教学资源,
    # 画像采集由 supervisor 的 profile guard 统一处理。

    # P1-#4 (2026-07-11): 注入 BKT 掌握度 + 最近对话历史, 强化差异化和上下文
    try:
        from app.services.bkt_service import get_tracker
        _bkt_tracker = get_tracker(state.get("user_id", 0))
        _bkt_dict = _bkt_tracker.to_dict()
        _bkt_summary = _bkt_dict.get("summary", {})
        _mastered = _bkt_tracker.get_mastered()[:5]   # 已掌握 (最多5个)
        _weak = _bkt_tracker.get_weak_points()[:3]   # 薄弱 (最多3个)
        _has_bkt_data = _bkt_summary.get("has_real_data", False)
        bkt_context = "\n## BKT 学习追踪 (P1-#4 2026-07-11 注入)\n"
        if _has_bkt_data:
            bkt_context += (
                f"- 已掌握概念({len(_mastered)}/5): {', '.join(_mastered) if _mastered else '无'}\n"
                f"- 薄弱概念({len(_weak)}/3): {', '.join(_weak) if _weak else '无'}\n"
                f"- 真实学习节点: {_bkt_summary.get('real_total', 0)} (答题 {_bkt_summary.get('real_attempts', 0)} 次)\n"
                f"- **必须针对薄弱概念加强讲解**, 已掌握概念可简要带过\n"
            )
        else:
            bkt_context += (
                "- 用户尚无 BKT 学习数据 (新用户/未答题), 按通用方式生成\n"
                "- 不要假设用户已掌握任何概念, 基础部分要详细\n"
            )
    except Exception as _bkt_err:
        logger.debug("P1-#4 BKT context 注入跳过: %s", _bkt_err)
        bkt_context = ""

    # P1-#4 (2026-07-11): 注入最近对话历史, 防止重复讲过内容
    # 关键修复 (2026-07-11 P1-#4 副作用): 必须过滤掉系统自动追加的"质量审核"块,
    # 否则 LLM 会模仿着写一个, 造成回复末尾出现 2 个 "> **质量审核**"
    def _strip_quality_block(text: str) -> str:
        """剥离系统自动追加的'质量审核'块, 只保留 LLM 真实生成内容"""
        if not text:
            return text
        # 截断到 "> **质量审核**" 之前
        idx = text.find("> **质量审核**")
        if idx > 0:
            return text[:idx].rstrip()
        return text

    _history_msgs = state.get("messages", [])[-6:]  # 最近3轮 (user+assistant)
    history_context = ""
    if _history_msgs:
        history_lines = ["\n## 最近对话历史 (P1-#4 2026-07-11 注入, 防止重复)"]
        for m in _history_msgs:
            role = "用户" if m.__class__.__name__ == "HumanMessage" else "助手"
            raw_content = (m.content if hasattr(m, "content") else str(m))
            # 关键: 过滤助手消息中的"质量审核"块, 避免 LLM 模仿
            if role == "助手":
                raw_content = _strip_quality_block(raw_content)
            content = raw_content[:150]
            history_lines.append(f"- {role}: {content}")
        history_lines.append("**要求**: 本次回复必须跟历史内容差异化, 不要重复讲过的话题")
        history_context = "\n".join(history_lines) + "\n"

    # 构建系统提示词（含画像+RAG上下文+BKT+history）
    resource_system = RESOURCE_PROMPT.format(
        profile_text=profile_text,
        topic=topic,
        type_label=type_label,
        type_guide=type_guide,
        references=f"\n## 参考教材\n{references}\n" if references else "",
        rag_rule="\n你必须严格遵守以下规则：\n1. 优先使用参考教材中的知识点组织内容\n2. 如果参考资料中有相关内容，可以直接引用并标注来源\n3. 不要编造教材中没有的概念、函数名或代码示例\n4. 如果教材内容与学生画像冲突，以教材为准" if references else "",
        difficulty_rule=difficulty_rule,
    )

    # P2 (2026-07-13): 画像引导已移除 — supervisor profile guard 统一处理
    # P1-#4 (2026-07-11): 追加 BKT + history 上下文
    if bkt_context:
        resource_system += "\n" + bkt_context
    if history_context:
        resource_system += history_context

    # 教学流程提示注入：告知 LLM 当前教学进度并引导下一节点
    if is_teaching:
        tc = teaching_context
        current_idx = tc.get("current_index", 0)
        total_nodes = len(tc.get("active_path", []))
        current_node = tc.get("active_path", [topic])[current_idx] if tc.get("active_path") else topic
        completed = tc.get("completed_nodes", [])

        is_stage_boundary = (current_idx > 0 and (current_idx + 1) % 3 == 0)
        is_last = (current_idx + 1 >= total_nodes)

        # 教学模式: 在 RESOURCE_PROMPT (9条铁律 + 6部分结构) 基础上叠加教学约束
        # 保留 RESOURCE_PROMPT 的反幻觉规则和结构要求，追加单节点聚焦限制
        teaching_append = (
            "\n\n---\n"
            "## 教学模式额外约束（叠加在上述铁律之上，冲突时以教学约束为准）\n\n"
            f"**当前知识点**: {current_node}（教学路径第 {current_idx + 1}/{total_nodes} 节点）\n"
        )
        if completed:
            teaching_append += f"已学完: {' → '.join(completed[-5:])}\n"
        teaching_append += (
            "\n**教学模式专用规则**:\n"
            "1. **只讲当前这一个知识点** — 不要在一个回复中涵盖多个主题或生成学习计划\n"
            "2. **禁止列举后续学习内容** — 不要写'接下来会学XXX'(系统自动推进路径)\n"
            "3. **跳过练习部分** — 第5部分(练习)不需要生成（出题由 question_agent 负责）\n"
            "4. **精简代码实战** — 第3部分(代码实战)只需一个典型示例，不必过于综合\n"
            "5. **常见陷阱至少1个** — 第4部分至少列出1个真实易错点\n"
        )
        if is_last:
            teaching_append += (
                "\n**这是最后一个节点**。在结尾祝贺用户完成学习路径，"
                "用 > 引用格式推荐: 做评估测试 / 学新主题 / 复习薄弱点。\n"
            )
        elif teaching_next_node:
            teaching_append += (
                "\n在结尾用一句话自然引导到下一个知识点"
                f"「{teaching_next_node}」，但不要展开讲解它。\n"
            )

        # 注入上一轮质量审查反馈
        qc_hints = tc.get("_quality_hints")
        if qc_hints:
            qc_issues = qc_hints.get("issues", [])
            qc_diff = qc_hints.get("difficulty_target", "")
            if qc_issues or qc_diff:
                teaching_append += "\n## 上一轮质量反馈（请据此改进本次输出）\n"
                if qc_diff:
                    teaching_append += f"- 难度建议: {qc_diff}\n"
                for qi in qc_issues:
                    teaching_append += f"- {qi}\n"
                teaching_append += "\n"

        resource_system += teaching_append

    # 携带对话历史上下文，确保多轮对话中代词语义连贯、约束条件跨轮传递
    from app.core.shared_utils import _build_llm_messages
    all_msgs = state.get("messages", [])
    last_user_msg = last_msg_content(state.get("messages", []), default=topic)
    messages = _build_llm_messages(
        resource_system,
        all_msgs,
        last_user_msg,
        max_history=12,
        topic_context=topic_ctx,
    )

    logger.info("ResourceAgent: 准备生成 %s（主题=%s, RAG=%s, 教学流程=%s）", resource_type, topic, "启用" if references else "降级", "是" if is_teaching else "否")

    # 构建 resource_agent 输出元数据（含教学流程信息）
    resource_output: dict = {
        "type": resource_type,
        "topic": topic,
        "title": clean_title,
        "rag_degraded": rag_degraded,  # 知识库未就绪时标记，前端/chat.py 据此提示用户
        "stream_pending": stream_request_to_dict(StreamRequest(
            messages=messages,
            temperature=0.7,
            max_tokens=4096,
            use_safe=True,
            chunk_size=16,  # P1-FIX: 从2增加到16，确保5字符Spark token能在一个chunk内被清洗
        )),
    }

    if is_teaching:
        current_idx = teaching_context.get("current_index", 0)
        total_nodes = len(teaching_context.get("active_path", []))
        resource_output["teaching_stage"] = "node_complete"
        resource_output["current_index"] = current_idx
        resource_output["total_nodes"] = total_nodes
        if teaching_next_node:
            resource_output["next_node"] = teaching_next_node
            logger.info("ResourceAgent: 教学节点完成 %d/%d → 下一节点: %s",
                         current_idx + 1, total_nodes, teaching_next_node)
        else:
            resource_output["next_node"] = None
            logger.info("ResourceAgent: 教学最后一个节点完成 %d/%d", current_idx + 1, total_nodes)

    # 统一走 stream_pending 流式管线：Agent 只准备 messages，不自行调用 LLM
    # _bridge_stream 在 chat.py 中负责 true streaming（逐 chunk yield）
    return {
        "current_agent": "resource_agent",
        "stream_buffer": "",
        "agent_outputs": {
            **state.get("agent_outputs", {}),
            "resource_agent": resource_output,
        },
    }
