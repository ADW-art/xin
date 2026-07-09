"""
Curated Knowledge Base Ingestion
=================================
Generates well-structured knowledge documents from the governed knowledge graph
and exercise bank, then ingests them into ChromaDB.

This avoids encoding issues with garbled filenames/pre-parsed text files,
producing clean, curriculum-aligned knowledge chunks.

Usage: python ingest_curated_kb.py
"""

import json
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("curated_ingest")

# Load the governed knowledge graph for concept definitions
KG_PATH = BACKEND_DIR / ".." / "docs" / "knowledge_graph_governed.json"
KG_PATH = KG_PATH.resolve()

with open(KG_PATH, "r", encoding="utf-8") as f:
    gov_kg = json.load(f)

NODES = [n["name"] for n in gov_kg.get("nodes", [])]
logger.info("Loaded %d concepts from governed KG", len(NODES))

# Knowledge definitions for each concept (curated, competition-quality)
KNOWLEDGE_BANK = {
    # -- Python Core --
    "Python基础": """Python 是一种解释型、面向对象的高级编程语言，由 Guido van Rossum 于 1991 年首次发布。
Python 的设计哲学强调代码的可读性和简洁的语法（尤其是使用空格缩进划分代码块）。
Python 支持多种编程范式，包括面向对象、命令式、函数式和过程式编程。
Python 拥有动态类型系统和垃圾回收功能，能够自动管理内存。
Python 解释器易于扩展，可以使用 C 或 C++ 扩展新的功能和数据类型。
Python 标准库提供了丰富的模块和功能，涵盖了文件 I/O、系统调用、网络编程、数据库接口等各个方面。
核心特性：简洁语法、动态类型、自动内存管理、丰富的标准库、跨平台支持。
适用场景：Web 开发、数据科学、人工智能、自动化脚本、科学计算等。""",

    "变量与类型": """在 Python 中，变量不需要声明类型，类型由赋值时的值自动确定。
Python 是动态类型语言，同一个变量可以指向不同类型的对象。
基本数据类型：
- 整数（int）：支持任意精度，如 a = 42
- 浮点数（float）：双精度浮点数，如 b = 3.14
- 字符串（str）：不可变字符序列，用单引号或双引号括起，如 s = 'hello'
- 布尔值（bool）：True 或 False，是 int 的子类
- NoneType：None 表示空值
类型转换：int('42'), str(100), float('3.14'), bool(0) 等。
变量命名规则：字母/下划线开头，只能包含字母、数字、下划线，区分大小写。
使用 type() 函数可以查看变量的类型。""",

    "运算符": """Python 支持丰富的运算符：
算术运算符：+ - * / //（整除） %（取模） **（幂）
比较运算符：== != > < >= <=
逻辑运算符：and or not（注意短路求值）
赋值运算符：= += -= *= /= //= %= **=
位运算符：& | ^ ~ << >>
成员运算符：in, not in
身份运算符：is, is not
运算符优先级：** > 正负号 > * / // % > + - > 比较 > not > and > or
注意：Python 中 / 总是返回浮点数，// 才是整除。""",

    "流程控制": """Python 的流程控制语句通过缩进来定义代码块：
条件语句：if-elif-else
  if condition:
      # do something
  elif other_condition:
      # do something else
  else:
      # do default
循环语句：
  - for 循环：for item in iterable: 遍历可迭代对象
  - while 循环：while condition: 条件为真时执行
循环控制：
  - break：跳出当前循环
  - continue：跳过当前迭代，进入下一次
  - else 子句：循环正常结束（未被break中断）时执行
Python 没有传统的 switch/case 语句（Python 3.10+ 引入了 match-case）。
range() 函数用于生成整数序列：range(start, stop, step)。""",

    "函数与模块": """函数是组织代码的基本单元，使用 def 关键字定义：
  def function_name(param1, param2=default):
      '''docstring'''
      # function body
      return result
参数类型：
- 位置参数：按顺序传递
- 默认参数：提供默认值，必须在位置参数之后
- 关键字参数：按名称传递，顺序无关
- 可变参数：*args（元组）和 **kwargs（字典）
作用域规则：LEGB（Local -> Enclosing -> Global -> Built-in）
模块是一个包含 Python 定义和语句的文件，使用 import 导入：
  import module_name
  from module import function_name
  import module as alias
每个 .py 文件都是一个模块，__name__ 变量指示模块是被运行还是被导入。
包是包含 __init__.py 的目录，用于组织多个模块。""",

    "面向对象": """Python 是面向对象语言，一切皆对象。
类定义：
  class ClassName(ParentClass):
      class_var = 0  # 类变量（所有实例共享）
      def __init__(self, param):
          self.instance_var = param  # 实例变量
      def method(self):
          pass
核心概念：
- 封装：将数据和操作封装在类中，通过 _protected 和 __private 控制访问
- 继承：子类继承父类的属性和方法，支持多重继承
- 多态：不同类可以实现同名方法，通过鸭子类型实现
特殊方法（魔术方法）：
  __init__ 构造, __str__ 字符串表示, __repr__ 可打印表示
  __eq__ 相等比较, __lt__ 小于比较, __len__ 长度
  __getitem__ 索引访问, __iter__ 迭代器, __call__ 可调用
@property 装饰器将方法转为属性访问。
@classmethod 和 @staticmethod 定义类方法和静态方法。""",

    "继承与多态": """继承是面向对象编程的核心机制：
  class Dog(Animal):  # Dog 继承自 Animal
      def speak(self):
          return 'Woof!'
方法解析顺序（MRO）：Python 使用 C3 线性化算法确定多继承时的方法查找顺序。
使用 super() 调用父类方法：
  super().__init__(...)  # 调用父类构造器
多态：不同对象对同一消息做出不同响应。
  def make_sound(animal):
      print(animal.speak())  # 不关心具体类型，只要实现了 speak()
鸭子类型：'如果它走路像鸭子，叫声像鸭子，那它就是鸭子'
  Python 不检查类型，只关心对象是否有需要的方法
抽象基类（ABC）：使用 abc 模块定义接口规范。
Mixin 模式：通过多重继承组合功能，每个 Mixin 提供一组相关方法。""",

    "列表与元组": """列表和元组是 Python 最常用的序列类型。
列表（list）：可变有序序列
  创建：lst = [1, 2, 3] 或 list(range(5))
  操作：lst.append(x), lst.extend(seq), lst.insert(i, x)
       lst.remove(x), lst.pop(i), lst.clear()
       lst.sort(), lst.reverse(), lst.index(x), lst.count(x)
  切片：lst[start:stop:step]，支持负数索引
元组（tuple）：不可变有序序列
  创建：tup = (1, 2, 3) 或 tuple([1, 2, 3])
  单元素元组：(x,) 注意逗号
  用途：函数返回多个值、字典键、不可变数据
  解包：a, b, c = tup
列表推导式：[expr for item in iterable if condition]
元组比列表更轻量，访问更快，适合不需要修改的数据。""",

    "字典与集合": """字典（dict）和集合（set）是基于哈希表的数据结构。
字典：键值对映射，键必须可哈希
  创建：d = {'key': 'value'} 或 dict(a=1, b=2)
  操作：d[key], d.get(key, default), d.keys(), d.values(), d.items()
       d.update(other), d.pop(key), d.popitem()
  字典推导式：{k: v for k, v in iterable}
集合：无序不重复元素集合
  创建：s = {1, 2, 3} 或 set([1, 2, 3])
  操作：s.add(x), s.remove(x), s.discard(x), s.pop()
  集合运算：| & - ^（并集、交集、差集、对称差集）
  集合推导式：{expr for item in iterable}
底层实现：哈希表，平均 O(1) 查找/插入/删除。
Python 3.7+ 字典保持插入顺序。""",

    "字符串处理": """Python 字符串是不可变的 Unicode 字符序列。
创建：单引号、双引号、三引号（多行字符串）
转义字符：\\n \\t \\\\ \\' \\"
原始字符串：r'path\\to\\file' 不处理转义
字符串方法：
  s.upper(), s.lower(), s.strip(), s.split(sep), s.join(iterable)
  s.replace(old, new), s.find(sub), s.startswith(prefix), s.endswith(suffix)
  s.isdigit(), s.isalpha(), s.isalnum(), s.isspace()
格式化：f-string（推荐）
  name = 'Alice'; f'Hello, {name}!'
  f'{value:.2f}'  # 保留两位小数
  f'{name:>10}'  # 右对齐，宽度10
编码：str.encode('utf-8'), bytes.decode('utf-8')
正则表达式：re 模块提供模式匹配功能。""",

    "列表推导式": """列表推导式是 Python 中创建列表的简洁语法。
基本形式：[expression for item in iterable]
带条件：[expression for item in iterable if condition]
嵌套循环：[expression for x in seq1 for y in seq2]
示例：
  squares = [x**2 for x in range(10)]
  evens = [x for x in range(20) if x % 2 == 0]
  pairs = [(x, y) for x in [1,2,3] for y in [3,1,4] if x != y]
性能：列表推导式比等效的 for 循环更快，因为它在 C 层面执行。
其他推导式：
  字典推导式：{k: v for k, v in pairs}
  集合推导式：{x for x in sequence}
  生成器表达式：(x**2 for x in range(10))  # 返回生成器，惰性求值
注意：不要过度使用，复杂逻辑用常规 for 循环更清晰。""",

    "生成器": """生成器是 Python 中惰性产生值的迭代器。
创建方式：
1. 生成器函数：使用 yield 关键字
   def countdown(n):
       while n > 0:
           yield n
           n -= 1
2. 生成器表达式：(x**2 for x in range(10))
特性：
- 惰性求值：只在需要时计算下一个值
- 内存高效：不一次性存储所有值
- 只能遍历一次：不能倒回或重复遍历
yield vs return：
  yield 暂停函数执行，返回一个值，下次从暂停处继续
  return 结束函数执行
send() 方法可以向生成器发送值。
yield from 委托给子生成器。
应用场景：处理大文件、无限序列、数据管道、协程。""",

    "迭代器": """迭代器是 Python 中实现迭代协议的对象。
迭代协议：
  __iter__()：返回迭代器对象自身
  __next__()：返回下一个元素，耗尽时抛出 StopIteration
可迭代对象 vs 迭代器：
  可迭代对象：实现了 __iter__() 的对象（如 list, tuple, dict）
  迭代器：实现了 __iter__() 和 __next__() 的对象
iter() 函数：从可迭代对象获取迭代器
next() 函数：获取迭代器的下一个元素
for 循环本质：
  for item in iterable:
      # 等价于
      iterator = iter(iterable)
      while True:
          try:
              item = next(iterator)
          except StopIteration:
              break
自定义迭代器：实现 __iter__ 和 __next__ 方法。
itertools 模块提供丰富的迭代器工具。""",

    "装饰器": """装饰器是 Python 中修改函数或类行为的强大工具。
本质：装饰器是一个接受函数作为参数并返回新函数的可调用对象。
语法糖：@decorator 等价于 func = decorator(func)
基本装饰器：
  def my_decorator(func):
      def wrapper(*args, **kwargs):
          print('Before')
          result = func(*args, **kwargs)
          print('After')
          return result
      return wrapper
带参数的装饰器：需要三层嵌套函数
  @repeat(n=3) 等价于 func = repeat(n=3)(func)
functools.wraps：保留原函数的元数据（__name__, __doc__ 等）
常见应用：
  - 日志记录（@log）
  - 性能计时（@timer）
  - 访问控制/认证（@login_required）
  - 缓存（@lru_cache）
  - 参数验证
类装饰器：实现 __call__ 方法。
装饰器可以叠加（多个装饰器从下到上应用）。""",

    "异常处理": """Python 使用 try-except 机制处理异常。
基本结构：
  try:
      # 可能抛出异常的代码
  except ValueError as e:
      # 处理特定异常
  except (TypeError, KeyError):
      # 处理多个异常
  else:
      # 没有异常时执行
  finally:
      # 无论是否有异常都执行（清理资源）
常见内置异常：
  ValueError, TypeError, KeyError, IndexError, AttributeError, IOError, ZeroDivisionError
抛出异常：raise Exception('message')
自定义异常：
  class MyError(Exception):
      pass
上下文管理器（with 语句）：
  with open('file.txt') as f:
      data = f.read()
  # 文件自动关闭，即使发生异常
异常处理最佳实践：
  - 只捕获预期异常，不要用裸 except:
  - 尽早处理，但不要太早
  - 异常信息要清晰有用""",

    "文件操作": """Python 提供丰富的文件操作功能。
打开文件：open(filename, mode, encoding='utf-8')
常用模式：'r' 读 'w' 写（覆盖） 'a' 追加 'rb' 二进制读 'wb' 二进制写
推荐使用 with 语句自动关闭文件：
  with open('data.txt', 'r', encoding='utf-8') as f:
      content = f.read()  # 读全部
      line = f.readline()  # 读一行
      lines = f.readlines()  # 读所有行
写文件：
  f.write('text')
  f.writelines(list_of_strings)
文件指针：f.seek(offset), f.tell()
路径操作：os.path 和 pathlib.Path
目录操作：os.mkdir(), os.listdir(), os.walk()
文件检查：os.path.exists(), os.path.isfile(), os.path.isdir()
shutil 模块：高级文件操作（复制、移动、删除目录树）
JSON 文件：json.dump(), json.load()
CSV 文件：csv.reader(), csv.writer()""",

    "正则表达式": """正则表达式是处理字符串的强大工具。
Python 中使用 re 模块：
  import re
常用函数：
  re.search(pattern, text)：搜索第一个匹配
  re.match(pattern, text)：从开头匹配
  re.findall(pattern, text)：返回所有匹配的列表
  re.sub(pattern, replacement, text)：替换匹配
  re.split(pattern, text)：按模式分割
常用元字符：
  . 任意字符  ^ 开头  $ 结尾  * 0+次  + 1+次  ? 0或1次
  {n} n次  {n,m} n到m次  [abc] 字符类  [^abc] 非字符类
  \\d 数字  \\w 单词字符  \\s 空白  \\b 单词边界
  (group) 捕获组  (?:...) 非捕获组  | 或者
贪婪 vs 非贪婪：*? +? 表示尽可能少匹配。
编译正则表达式（复用）：
  pattern = re.compile(r'\\d+')
  pattern.findall(text)
预编译可提高性能，适合重复使用同一模式。""",

    # -- Data Structures --
    "数组": """数组是线性数据结构，存储相同类型的元素集合。
在内存中，数组元素连续存储，通过索引实现 O(1) 随机访问。
数组 vs 链表：
  数组：连续内存，O(1) 访问，O(n) 插入/删除（需移动元素）
  链表：非连续内存，O(n) 访问，O(1) 插入/删除（修改指针）
Python 中：
  list 是动态数组，自动扩容
  array 模块提供紧凑的类型化数组
  numpy.ndarray 提供多维数组
常见操作：访问、插入、删除、遍历、搜索、排序。
时间复杂度总结：访问 O(1)、搜索 O(n)、插入 O(n)、删除 O(n)。
动态数组扩容策略：通常是 2 倍增长，均摊 O(1) 插入。""",

    "链表": """链表是一种线性数据结构，由节点组成，每个节点包含数据和指向下一个节点的指针。
类型：
  单向链表：每个节点指向下一个节点
  双向链表：每个节点指向前后两个节点
  循环链表：尾节点指向头节点
基本操作（单向链表）：
  遍历：从头节点开始，沿指针访问
  插入：修改前驱节点的指针
  删除：修改前驱节点的指针，跳过待删除节点
  查找：从头遍历直到找到目标
时间复杂度：访问 O(n)、搜索 O(n)、插入 O(1)*、删除 O(1)*（*已知位置）
Python 中：没有内置链表，需自定义 Node 类。
优势：动态大小、高效的插入删除。
劣势：不支持随机访问、额外内存存储指针。""",

    "栈": """栈是一种后进先出（LIFO）的线性数据结构。
基本操作：
  push：将元素压入栈顶
  pop：移除并返回栈顶元素
  peek/top：查看栈顶元素（不移除）
  isEmpty：检查栈是否为空
实现方式：
  - 数组实现：维护 top 指针
  - 链表实现：在链表头部操作
Python 中：list 提供 O(1) 的 append() 和 pop() 作为栈使用。
也使用 collections.deque 实现。
应用场景：
  - 函数调用栈
  - 括号匹配验证
  - 表达式求值（中缀转后缀）
  - 撤销操作（Undo）
  - 深度优先搜索（DFS）
时间复杂度：push O(1), pop O(1), peek O(1)。""",

    "队列": """队列是一种先进先出（FIFO）的线性数据结构。
基本操作：
  enqueue：将元素加入队尾
  dequeue：移除并返回队首元素
  front/peek：查看队首元素（不移除）
  isEmpty：检查队列是否为空
实现方式：
  - 数组实现（循环队列）：优化空间利用
  - 链表实现：维护头尾指针
Python 中：
  from collections import deque
  queue = deque(); queue.append(x); queue.popleft()
变种：
  - 双端队列（Deque）：两端都可操作
  - 优先队列（Priority Queue）：按优先级出队
  - 循环队列（Circular Queue）：头尾相连
应用场景：
  - 任务调度、消息队列
  - 广度优先搜索（BFS）
  - 缓存系统（FIFO Cache）
时间复杂度：enqueue O(1), dequeue O(1)。""",

    "树": """树是一种层次化的非线性数据结构。
基本术语：
  根节点 root：树的顶层节点
  父节点/子节点：直接上下级关系
  叶节点 leaf：没有子节点的节点
  高度/深度：从根到叶的最长路径
二叉树 Binary Tree：每个节点最多两个子节点
  满二叉树：所有层都满
  完全二叉树：除最后一层外满，最后一层从左到右填充
遍历方式：
  深度优先（DFS）：
    前序 preorder：根→左→右
    中序 inorder：左→根→右
    后序 postorder：左→右→根
  广度优先（BFS）：层序遍历，从上到下从左到右
二叉搜索树（BST）：左子<父<右子，平均 O(log n) 查找
平衡树（AVL、红黑树）：自动保持平衡，保证 O(log n)
应用：文件系统、DOM 树、数据库索引、表达式树。""",

    "图": """图是一种由顶点（节点）和边组成的非线性数据结构。
图的基本概念：
  顶点 Vertex：图中的节点
  边 Edge：顶点之间的连接
  有向图 Directed Graph：边有方向
  无向图 Undirected Graph：边无方向
  权重 Weight：边上的数值
  路径 Path：顶点序列
  环 Cycle：起点=终点的路径
表示方法：
  邻接矩阵 Adjacency Matrix：O(V^2) 空间，适合稠密图
  邻接表 Adjacency List：O(V+E) 空间，适合稀疏图
常用算法：
  遍历：DFS（栈）、BFS（队列）
  最短路径：Dijkstra、Bellman-Ford、Floyd-Warshall
  最小生成树：Prim、Kruskal
  拓扑排序：DAG 中排序顶点
  强连通分量：Kosaraju、Tarjan
应用：社交网络、地图导航、网络路由、依赖分析。""",

    "排序算法": """排序算法将序列元素按顺序排列。
比较排序：通过比较元素来决定顺序
  - 冒泡排序 Bubble Sort：相邻比较交换，O(n^2)，稳定
  - 选择排序 Selection Sort：每次选最小，O(n^2)，不稳定
  - 插入排序 Insertion Sort：构建有序序列，O(n^2)，稳定，适合小数据/部分有序
  - 归并排序 Merge Sort：分治法，O(n log n)，稳定，需额外空间
  - 快速排序 Quick Sort：分区+递归，平均 O(n log n)，不稳定，原地排序
  - 堆排序 Heap Sort：利用堆，O(n log n)，不稳定，原地排序
非比较排序：
  - 计数排序 Counting Sort：O(n+k)，适合整数范围小
  - 桶排序 Bucket Sort：均匀分布时 O(n)
  - 基数排序 Radix Sort：逐位排序，O(d*(n+k))
稳定性：相等元素的相对位置不变。
Python 中：sorted() 和 .sort() 使用 Timsort（归并+插入混合，稳定, O(n log n)）。""",

    "查找算法": """查找算法在数据集中搜索特定元素。
线性查找 Linear Search：
  逐个检查每个元素，O(n)
  适用于无序数据
二分查找 Binary Search：
  前提：数据有序
  每次取中间元素比较，排除一半，O(log n)
  实现：while left <= right: mid = (left+right)//2
插值查找 Interpolation Search：
  改进的二分查找，根据值分布估计位置
  均匀分布数据 O(log log n)
哈希查找 Hash Search：
  通过哈希函数直接定位，平均 O(1)
  需考虑哈希冲突解决方案
二叉搜索树查找：
  平衡树 O(log n)，最坏 O(n)
查找算法的选择：
  - 小数据量：线性查找足够
  - 有序数组：二分查找
  - 频繁查找：哈希表
  - 需要范围查询：二叉搜索树/跳表""",

    "哈希表": """哈希表（散列表）是一种通过哈希函数将键映射到存储位置的数据结构。
核心概念：
  哈希函数 Hash Function：将键映射为数组索引
  冲突 Collision：不同键产生相同索引
  负载因子 Load Factor：已用槽数/总槽数
冲突解决：
  1. 链地址法 Chaining：每个槽是一个链表（Python dict 使用）
  2. 开放寻址法 Open Addressing：寻找下一个空槽
     - 线性探测：逐个找下一个
     - 二次探测：跳过平方数位置
     - 双重哈希：使用第二个哈希函数
Python dict 实现：基于哈希表，使用开放寻址+随机探测
时间复杂度：
  平均：查找 O(1)、插入 O(1)、删除 O(1)
  最坏：查找 O(n)（大量冲突时）
应用：
  - 数据库索引（Hash Index）
  - 缓存（LRU Cache）
  - 去重（Set）
  - 计数（Counter）
  - 路由表""",

    "递归算法": """递归是函数调用自身来解决问题的编程技术。
递归三要素：
  1. 基准条件 Base Case：递归终止条件（防止无限递归）
  2. 递归条件 Recursive Case：将问题分解为更小的子问题
  3. 向基准条件逼近
经典示例：
  阶乘：n! = n * (n-1)!  (base: 0! = 1)
  斐波那契：f(n) = f(n-1) + f(n-2)  (base: f(0)=0, f(1)=1)
递归 vs 迭代：
  递归：代码简洁，但可能栈溢出，有函数调用开销
  迭代：效率高，但代码可能更复杂
尾递归优化：递归调用是函数最后操作时可优化为迭代（Python 默认不支持）
递归树分析：通过递归树分析时间/空间复杂度
应用：
  - 树的遍历（天然递归结构）
  - 分治算法（归并排序、快速排序）
  - 回溯算法（N皇后、迷宫）
  - 图搜索（DFS）""",

    # -- Algorithms --
    "算法基础": """算法是解决特定问题的有限步骤序列。
算法的五大特性：
  1. 有穷性 Finiteness：算法必须在有限步内终止
  2. 确定性 Definiteness：每一步必须有明确的定义
  3. 输入 Input：有零个或多个输入
  4. 输出 Output：至少有一个输出
  5. 可行性 Effectiveness：每一步都可以在有限时间内完成
算法分析：
  时间复杂度：随输入规模增长，执行时间的变化
  空间复杂度：随输入规模增长，额外内存消耗
  大 O 表示法：描述算法的渐近上界
    O(1) 常数 < O(log n) 对数 < O(n) 线性 < O(n log n) 线性对数
    < O(n^2) 平方 < O(2^n) 指数 < O(n!) 阶乘
常见算法范式：
  - 暴力法 Brute Force
  - 分治法 Divide and Conquer
  - 贪心法 Greedy
  - 动态规划 Dynamic Programming
  - 回溯法 Backtracking""",

    "时间复杂度": """时间复杂度衡量算法执行时间随输入规模的增长趋势。
大 O 表示法 Big O Notation：最坏情况渐近上界
常见复杂度排序（从快至慢）：
  O(1)：常数时间 -- 直接访问数组元素
  O(log n)：对数时间 -- 二分查找
  O(n)：线性时间 -- 遍历数组
  O(n log n)：线性对数 -- 归并排序
  O(n^2)：平方时间 -- 冒泡排序、两重循环
  O(2^n)：指数时间 -- 递归求斐波那契（无记忆化）
  O(n!)：阶乘时间 -- 旅行商问题暴力法
复杂度分析技巧：
  - 循环 n 次 → O(n)
  - 嵌套循环 n × m → O(n*m)
  - 每次规模减半 → O(log n)
  - 取最高阶项，忽略常数和低阶项
均摊分析：多次操作的平均时间（如动态数组扩容）
最好/平均/最坏情况：排序算法常分析三种情况。""",

    "动态规划": """动态规划 Dynamic Programming 通过将问题分解为重叠子问题并存储中间结果来优化。
核心思想：
  1. 最优子结构 Optimal Substructure：最优解包含子问题的最优解
  2. 重叠子问题 Overlapping Subproblems：子问题被重复计算
两种实现方式：
  1. 自顶向下 Top-Down（记忆化 Memoization）：
     递归 + 缓存已计算结果（通常用字典/functools.lru_cache）
  2. 自底向上 Bottom-Up（表格法 Tabulation）：
     迭代填充 DP 表，每个子问题只计算一次
经典问题：
  - 斐波那契数列：dp[i] = dp[i-1] + dp[i-2]
  - 背包问题 0/1 Knapsack
  - 最长公共子序列 LCS
  - 最长递增子序列 LIS
  - 编辑距离 Edit Distance
  - 硬币找零 Coin Change
状态定义 → 状态转移方程 → 初始化 → 遍历顺序 → 返回结果
空间优化：滚动数组、状态压缩。""",

    "贪心算法": """贪心算法 Greedy Algorithm 在每一步都做出当前看来最优的选择。
贪心策略：局部最优 → 全局最优（不总是成立）
贪心算法适用条件：
  1. 贪心选择性质：全局最优可通过局部最优得到
  2. 最优子结构：问题的最优解包含子问题的最优解
经典贪心问题：
  - 活动选择问题 Activity Selection
  - 霍夫曼编码 Huffman Coding
  - 最小生成树 MST（Prim、Kruskal）
  - 最短路径 Dijkstra
  - 找零问题（某些硬币面额）
贪心 vs 动态规划：
  贪心：每步做最好选择，不回溯，快但不一定最优
  动态规划：考虑所有可能，一定最优，但更慢更耗空间
验证贪心正确性：
  - 交换论证 Exchange Argument
  - 归纳法 Induction
  - 拟阵理论 Matroid Theory""",

    "二分查找": """二分查找 Binary Search 在有序数组中高效查找目标元素。
算法流程：
  1. 设定左右边界 left=0, right=len(arr)-1
  2. 取中间位置 mid = (left + right) // 2
  3. 比较 arr[mid] 与 target
     - 等于 → 找到，返回 mid
     - arr[mid] < target → 在右半部分：left = mid + 1
     - arr[mid] > target → 在左半部分：right = mid - 1
  4. 当 left > right 时退出，表示未找到
时间复杂度：O(log n)
变体：
  - 查找第一个等于 target 的位置
  - 查找最后一个等于 target 的位置
  - 查找第一个大于等于 target 的位置（lower_bound）
  - 查找第一个大于 target 的位置（upper_bound）
边界注意：
  - mid 计算：mid = left + (right - left) // 2（防溢出）
  - 循环条件：left <= right
  - 缩小范围时 mid ± 1
应用：除查找外，还用于求平方根、最大值最小化等。""",

    "深度优先搜索": """深度优先搜索 DFS 沿着图的一条路径尽可能深入地探索，直到无路可走再回溯。
实现方式：
  1. 递归实现：
     def dfs(node, visited):
         visited.add(node)
         for neighbor in graph[node]:
             if neighbor not in visited:
                 dfs(neighbor, visited)
  2. 栈实现（迭代）：
     stack = [start]
     while stack:
         node = stack.pop()
         # process node
         for neighbor in graph[node]:
             if not visited[neighbor]:
                 stack.append(neighbor)
时间复杂度：O(V + E)（每个顶点和边各访问一次）
空间复杂度：O(V)（递归调用栈或显式栈）
应用：
  - 拓扑排序（后序遍历顺序）
  - 检测连通分量/环
  - 路径查找（走迷宫）
  - 回溯算法（排列、组合、N皇后）
DFS vs BFS：DFS 适合找任一解、空间消耗少；BFS 适合找最短路径。""",

    "广度优先搜索": """广度优先搜索 BFS 逐层探索图，从起点开始，先访问所有距离为 1 的节点，再访问距离为 2 的节点。
实现方式（队列）：
  from collections import deque
  queue = deque([start])
  visited.add(start)
  while queue:
      node = queue.popleft()
      for neighbor in graph[node]:
          if neighbor not in visited:
              visited.add(neighbor)
              queue.append(neighbor)
时间复杂度：O(V + E)
空间复杂度：O(V)
特性：
  - 在无权图中找到最短路径（按边数计）
  - 逐层访问，适合层次化结构
应用：
  - 最短路径（无权图）
  - 社交网络中的"N度人脉"
  - 网络爬虫
  - 迷宫最短路径
  - 最小生成树（Prim 算法）
BFS vs DFS 选择：
  找最短路径 → BFS
  找任一可行路径 → DFS
  树宽而浅 → DFS（省空间）
  树窄而深 → BFS（防栈溢出）""",

    # -- CS Fundamentals --
    "操作系统": """操作系统是管理计算机硬件和软件资源的系统软件。
核心功能：
  1. 进程管理 Process Management：
     进程创建/调度/终止、进程间通信 IPC、死锁检测与避免
  2. 内存管理 Memory Management：
     虚拟内存、分页/分段、地址转换、页面置换算法（LRU、FIFO）
  3. 文件系统 File System：
     文件组织、目录结构、磁盘调度、权限管理
  4. 输入/输出管理 I/O Management：
     设备驱动程序、缓冲/缓存、中断处理
进程 vs 线程：
  进程：资源分配的基本单位，独立地址空间
  线程：CPU 调度的基本单位，共享进程地址空间
CPU 调度算法：FCFS、SJF、优先级调度、轮转（Round Robin）
同步原语：互斥锁、信号量、条件变量
经典问题：生产者-消费者、读者-写者、哲学家就餐。""",

    "计算机网络": """计算机网络是计算机之间进行数据通信的互联系统。
网络分层模型：
  OSI 七层模型：物理层→数据链路层→网络层→传输层→会话层→表示层→应用层
  TCP/IP 四层模型：网络接入层→网络层→传输层→应用层
各层关键功能：
  应用层：HTTP/HTTPS、DNS、SMTP、FTP
  传输层：TCP（可靠连接）、UDP（无连接低延迟）
  网络层：IP 寻址、路由选择（OSPF、BGP）
  数据链路层：MAC 地址、以太网
TCP 三次握手：
  SYN → SYN-ACK → ACK
TCP 四次挥手：
  FIN → ACK → FIN → ACK
IP 地址：IPv4（32位）、IPv6（128位）
常见协议端口：HTTP 80、HTTPS 443、DNS 53、SSH 22
网络安全：防火墙、加密（SSL/TLS）、身份认证。""",

    "数据库基础": """数据库是组织、存储和管理数据的系统。
关系型数据库 RDBMS：
  核心概念：表 Table、行 Row、列 Column、主键 Primary Key、外键 Foreign Key
  SQL 语言：SELECT、INSERT、UPDATE、DELETE
  ACID 特性：原子性、一致性、隔离性、持久性
  事务隔离级别：读未提交、读已提交、可重复读、串行化
  索引：B+树索引、哈希索引，加速查询但减慢写入
数据库设计：
  ER 图（实体-关系模型）
  范式化 Normalization（1NF、2NF、3NF、BCNF）
  反范式化 Denormalization（性能优化）
NoSQL 数据库：
  文档型（MongoDB）、键值型（Redis）、列族型（Cassandra）、图数据库（Neo4j）
索引类型：
  聚簇索引 Clustered Index：数据物理按索引排序
  非聚簇索引 Non-clustered Index：单独存储索引结构
  复合索引 Composite Index：多列组合索引""",

    "编译原理": """编译原理研究如何将高级语言翻译为机器可执行的代码。
编译过程（阶段）：
  1. 词法分析 Lexical Analysis：
     将源代码分割为 Token（标识符、关键字、运算符等）
  2. 语法分析 Syntax Analysis：
     根据语法规则构建抽象语法树 AST
  3. 语义分析 Semantic Analysis：
     类型检查、作用域分析、语义正确性验证
  4. 中间代码生成：
     生成平台无关的中间表示 IR
  5. 代码优化：
     提高效率（常量折叠、死代码消除、循环优化）
  6. 目标代码生成：
     生成特定平台的机器码/汇编
编译器 vs 解释器：
  编译器：一次性翻译，生成可执行文件
  解释器：逐行翻译执行（如 Python CPython）
  即时编译 JIT：运行时编译热点代码（如 Java JVM、Python PyPy）
文法：上下文无关文法 CFG、BNF 表示法。
解析算法：递归下降、LL(1)、LR(1)、LALR。""",

    "编程基础": """编程是使用计算机语言解决问题的过程。
编程核心概念：
  变量 Variable：存储数据的命名容器
  数据类型 Data Type：整数、浮点数、字符、布尔、数组等
  控制结构 Control Flow：顺序、选择（if-else）、循环（for/while）
  函数/方法 Function：可重用的代码块
  输入/输出 I/O：与用户或文件系统交互
编程范式：
  过程式 Programming：以过程/函数为中心（C 语言）
  面向对象 OOP：以对象/类为中心，封装+继承+多态
  函数式 FP：数学函数，不可变数据，无副作用
  声明式 Declarative：描述'要什么'而非'怎么做'（SQL）
算法思维：
  分解问题 → 识别模式 → 抽象化 → 设计算法
调试技巧：
  打印调试、断点调试、单元测试、日志记录
版本控制：Git 跟踪代码变更历史。
软件开发生命周期：需求→设计→实现→测试→部署→维护。""",

    "计算机组成": """计算机组成原理研究计算机硬件系统的结构和基本原理。
冯·诺依曼体系结构：
  五大部件：运算器、控制器、存储器、输入设备、输出设备
  特点：存储程序思想（指令和数据存于同一内存）
CPU 中央处理器：
  运算器 ALU：算术逻辑运算
  控制器 CU：指令译码和控制信号
  寄存器：通用寄存器、PC（程序计数器）、IR（指令寄存器）
  指令周期：取指→译码→执行→写回
存储层次：
  寄存器 < 缓存 L1/L2/L3 < 主存 RAM < 磁盘/SSD
  时间局部性/空间局部性 → 缓存设计基础
数据表示：
  整数：原码/反码/补码
  浮点数：IEEE 754（符号+阶码+尾数）
  字符：ASCII、Unicode UTF-8
总线：地址总线+数据总线+控制总线。
指令集：CISC（复杂）vs RISC（精简）。""",
}

# Generate additional entries for concepts not in our curated bank
for node in NODES:
    if node not in KNOWLEDGE_BANK:
        KNOWLEDGE_BANK[node] = f"{node}是计算机科学中的一个重要概念。学生在学习计算机科学时需要掌握{node}的基本原理和应用场景。通过深入理解{node}，可以为后续更高阶主题的学习打下坚实基础。"


def main():
    from app.services.rag_service import ingest_document, get_knowledge_count, load_exercise_bank, is_rag_ready

    # Force BGE model loading
    from app.services.rag_service import _get_dense_model
    model = _get_dense_model()
    if model is None:
        logger.error("BGE model failed to load. Aborting.")
        return
    logger.info("BGE model loaded. RAG ready: %s", is_rag_ready())

    # Step 1: Ingest knowledge documents
    logger.info("=== Ingesting curated knowledge documents ===")
    count = 0
    safe_ids = set()  # Track used safe IDs to avoid collisions
    for concept, content in KNOWLEDGE_BANK.items():
        try:
            # Use ASCII-safe sequential IDs (Chinese IDs cause ChromaDB encoding issues on Windows)
            safe_id = f"kb_{count:04d}"
            while safe_id in safe_ids:
                count += 1
                safe_id = f"kb_{count:04d}"
            safe_ids.add(safe_id)
            ingest_document(
                content=content,
                title=concept,
                source="curated_knowledge_bank",
                doc_id=safe_id,
            )
            count += 1
        except Exception as e:
            logger.debug("Skip %s: %s", concept, e)

    logger.info("Ingested %d knowledge documents", count)

    # Step 2: Load exercise bank
    logger.info("=== Loading exercise bank ===")
    ex_path = BACKEND_DIR / "app" / "scripts" / "knowledge_materials" / "exercise_bank.json"
    ex_count = load_exercise_bank(str(ex_path))
    logger.info("Exercise bank: %d exercises", ex_count)

    # Step 3: Build knowledge graph from ChromaDB
    logger.info("=== Building knowledge graph ===")
    from app.services.knowledge_graph import get_graph
    from app.core.chroma_client import get_collection

    kg = get_graph()
    col = get_collection("knowledge_base")
    results = col.get()
    documents = results.get("documents", [])

    if documents:
        # Group by title
        books = {}
        for doc, meta in zip(documents, results.get("metadatas", [{}]) or [{}]):
            title = (meta or {}).get("title", "unknown")
            books.setdefault(title, "")
            books[title] += doc + "\n\n"

        texts = [{"title": t, "content": c} for t, c in books.items()]
        kg.build_from_texts(texts)
        logger.info("KG: %d nodes, %d edges", len(kg.nodes), sum(len(e) for e in kg.edges.values()))

        # Topological sort
        phases = kg.topological_sort()
        logger.info("Learning path: %d phases", len(phases))
        for i, p in enumerate(phases[:5]):
            logger.info("  Phase %d: %s", i + 1, ", ".join(p[:5]))

    # Final verification
    logger.info("=== Verification ===")
    kb_count = get_knowledge_count()
    logger.info("knowledge_base: %d documents", kb_count)

    from app.services.rag_service import search_knowledge
    for q in ["Python基础", "数据结构", "排序算法", "链表", "动态规划"]:
        results = search_knowledge(q, n=2)
        if results:
            logger.info("  '%s': score=%.3f, source=%s", q, results[0].get("score", 0), results[0].get("metadata", {}).get("title", "?"))
        else:
            logger.warning("  '%s': no results", q)

    from app.services.rag_service import search_exercises
    ex = search_exercises("Python", n=3)
    logger.info("Exercise search 'Python': %d results", len(ex))

    print(f"\n{'='*50}")
    print(f"KB: {kb_count} docs | Exercises: {ex_count} | KG: {len(kg.nodes)} nodes")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
