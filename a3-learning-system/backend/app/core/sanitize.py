"""
输入消毒模块
防 XSS / SQL 注入 / 命令注入 / 路径穿越
"""

import re
import unicodedata

from fastapi import HTTPException, status

# SQL 注入检测模式（关键字 + 拼接手法）
SQL_INJECTION_PATTERNS = [
    r"(?:'|\")\s*(?:OR|AND)\s+(?:\d+=\d+|'[^']*'='[^']*'|\"[^\"]*\"=\"[^\"]*\")\s*(?:--|#)?",
    r"\b(?:UNION|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|TRUNCATE)\b\s+(?:\bFROM\b|\bINTO\b|\bTABLE\b|\bPROCEDURE\b)",
    r"(?:--|#)\s*$",                    # 行末注释注入
    r"'\s*;\s*(?:DROP|DELETE|INSERT)\s+",  # 语句串联
]

# XSS 检测模式
XSS_PATTERNS = [
    r"<script[^>]*>.*?</script>",
    r"javascript\s*:",
    r"on\w+\s*=\s*[\"'][^\"']*[\"']",
    r"<iframe[^>]*>",
    r"<embed[^>]*>",
    r"<object[^>]*>",
    r"data:text/html",
    r"base64[,\s]*",
    r"document\.(?:cookie|write|location)\b",
    r"eval\s*\(.*\)",
    r"expression\s*\(.*\)",
    r"vbscript\s*:",
]

# 路径穿越 / 命令注入
PATH_CMD_PATTERNS = [
    r"(?:\.\./|\.\.\\){2,}",              # 路径穿越 ../../../
    r"\b(?:/etc/passwd|/etc/shadow)\b",     # 敏感文件
    r"[;&|`$]\s*(?:cat|ls|rm|wget|curl|nc|bash|sh|python|perl|php)\b",  # 命令注入
    r"\\x[0-9a-fA-F]{2}",                   # 十六进制编码绕过
]

ALL_PATTERNS = SQL_INJECTION_PATTERNS + XSS_PATTERNS + PATH_CMD_PATTERNS


def _contains_unsafe_unicode(text: str) -> bool:
    """检测混淆 Unicode（同形字攻击、RTL覆盖等）"""
    for ch in text:
        cat = unicodedata.category(ch)
        # 检测 RTL 覆盖字符 (‮) 和零宽字符
        if ch in ("‮", "​", "‌", "‍", "﻿", "­"):
            return True
        # 控制字符（除了常见空白）
        if cat == "Cc" and ch not in ("\n", "\r", "\t"):
            return True
    return False


def sanitize_input(value: str) -> str:
    """对用户输入进行安全检查

    Args:
        value: 用户输入字符串

    Returns:
        清洗后的字符串（当前为空操作，仅做检测拦截）

    Raises:
        HTTPException(400): 输入包含不安全内容时
    """
    if not value:
        return value

    # 1. Unicode 混淆检测
    if _contains_unsafe_unicode(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="输入包含不安全字符",
        )

    # 2. 正则模式匹配
    for pattern in ALL_PATTERNS:
        if re.search(pattern, value, re.IGNORECASE):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="输入包含不安全内容",
            )

    return value
