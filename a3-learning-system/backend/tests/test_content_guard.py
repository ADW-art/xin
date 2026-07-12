"""
ContentGuard 内容安全守卫 — anti-learning-plan 检测单元测试

测试覆盖:
- is_learning_plan_output — 学习计划/课程表检测
- 正常教学内容不误判
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.utils.content_guard import ContentGuard


def test_detect_weekly_plan():
    """检测多周课程表"""
    guard = ContentGuard()
    text = """## 学习计划
第1周：Python基础语法
第2周：面向对象编程
第3周：Web开发入门"""
    assert guard.is_learning_plan_output(text) is True


def test_detect_numbered_stages():
    """检测"第X阶段"结构"""
    guard = ContentGuard()
    text = """第1阶段：基础概念讲解
第2阶段：代码实战练习
第3阶段：项目综合应用"""
    assert guard.is_learning_plan_output(text) is True


def test_detect_daily_schedule():
    """检测多天课程"""
    guard = ContentGuard()
    text = """第1天：安装Python
第2天：变量和数据类型
第3天：控制流"""
    assert guard.is_learning_plan_output(text) is True


def test_detect_curriculum_title():
    """检测独立的学习计划标题"""
    guard = ContentGuard()
    text = """# Python 学习计划

## 课程大纲
这是为期四周的Python学习计划..."""
    assert guard.is_learning_plan_output(text) is True


def test_no_false_positive_on_focused_content():
    """聚焦单知识点内容不误判为计划"""
    guard = ContentGuard()
    text = """## Python 装饰器

### 概念讲解
装饰器是一种高阶函数...

### 代码示例
```python
def my_decorator(func):
    def wrapper():
        print("before")
        func()
        print("after")
    return wrapper
```

### 常见误区
新手常犯的错误是忘记使用 @wraps..."""
    assert guard.is_learning_plan_output(text) is False


def test_no_false_positive_short_text():
    """短文本(单知识点的标题)不误判"""
    guard = ContentGuard()
    assert guard.is_learning_plan_output("什么是Python装饰器") is False
    assert guard.is_learning_plan_output("学习一下闭包的概念") is False


def test_detect_single_plan_keyword():
    """仅含'学习计划'四个字也检测"""
    guard = ContentGuard()
    text = "# Python 学习计划\n\n先学基础语法，再学面向对象，最后做项目实战"
    assert guard.is_learning_plan_output(text) is True


def test_detect_multi_module_structure():
    """检测"第X模块"结构"""
    guard = ContentGuard()
    text = """第一模块：入门基础
第二模块：核心语法
第三模块：高级特性"""
    assert guard.is_learning_plan_output(text) is True


def test_empty_short_text():
    """空文本和极短文本返回 False"""
    guard = ContentGuard()
    assert guard.is_learning_plan_output("") is False
    assert guard.is_learning_plan_output("Python") is False
    assert guard.is_learning_plan_output("学习") is False
