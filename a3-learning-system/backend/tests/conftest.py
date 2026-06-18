"""
Pytest fixtures and shared test utilities for the A3 Learning System.

Provides:
- Mock SparkClient for tests that need LLM calls
- Test database setup/teardown helpers
- Freeze-time utilities for time-dependent tests
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import sys
import os

# Ensure the backend app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# SparkClient 全局 Mock（无需真实 WS 连接）
# ============================================================

class MockSparkClient:
    """模拟讯飞星火客户端，返回预设文本，避免真实 API 调用。"""

    def __init__(self, mock_response: str = "模拟回复"):
        self.mock_response = mock_response
        self.last_messages = []
        self.app_id = "mock_app_id"
        self.api_key = "mock_api_key"
        self.api_secret = "mock_api_secret"
        self.app_password = ""

    def chat_stream(self, messages: list[dict], temperature: float = 0.7, max_tokens: int = 4096):
        """流式对话（模拟）—— 逐个 token yield。"""
        tokens = list(self.mock_response)
        for token in tokens:
            yield token

    def chat_sync(self, messages: list[dict], temperature: float = 0.7) -> str:
        """同步对话。"""
        self.last_messages = messages
        return self.mock_response


@pytest.fixture
def mock_spark() -> MockSparkClient:
    """返回一个 Mock SparkClient 实例。"""
    return MockSparkClient()


# ============================================================
# 时间冻结工具（Review Scheduler 时间相关测试用）
# ============================================================

@pytest.fixture
def freeze_time():
    """冻结时间到固定时刻（2026-06-15 12:00:00），用于 ReviewScheduler 测试。

    用法：
        def test_retention(freeze_time):
            s = ReviewSchedule("test")
            s.review()  # last_reviewed = freeze_time
            # 此时 retention_rate 基于 freeze_time 计算
    """
    frozen = datetime(2026, 6, 15, 12, 0, 0)
    with patch("app.services.review_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = frozen
        mock_dt.side_effect = datetime
        yield frozen


@pytest.fixture
def freeze_time_with_progression():
    """返回一个可推进的冻结时间上下文。

    用法：
        def test_retention_decay(freeze_time_with_progression):
            frozen, mock_dt = freeze_time_with_progression
            s = ReviewSchedule("test")
            s.review()  # frozen
            mock_dt.now.return_value = frozen + timedelta(days=5)
            # Now retention is based on 5 days later
    """
    frozen = datetime(2026, 6, 15, 12, 0, 0)
    mock_dt = MagicMock()
    mock_dt.now.return_value = frozen
    with patch("app.services.review_scheduler.datetime", mock_dt):
        yield frozen, mock_dt


# ============================================================
# 测试样本数据
# ============================================================

@pytest.fixture
def sample_texts() -> list[dict]:
    """用于知识图谱构建的示例教材文本。"""
    return [
        {
            "title": "Python 基础",
            "content": """# Python 基础语法
变量是 Python 中最基本的概念。Python 使用动态类型。
数据类型包括整数、浮点数、字符串、列表等。
列表是 Python 中最常用的数据结构之一。""",
        },
        {
            "title": "函数与模块",
            "content": """# Python 函数
函数通过 def 关键字定义。函数可以接受参数并返回值。
模块化编程允许将函数组织到不同的文件中。
装饰器是一种特殊的函数，用于修改其他函数的行为。
理解列表和函数后，可以开始学习面向对象编程。""",
        },
        {
            "title": "面向对象编程",
            "content": """# 面向对象编程
类是面向对象编程的核心概念。类定义了对象的属性和方法。
继承允许子类复用父类的代码。
多态实现了不同类的统一接口调用。
类型注解提高了代码的可读性和可维护性。""",
        },
    ]
