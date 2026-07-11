"""
LLM 通用工具（Token 管理 / 重试 / 智能降级）

功能：
  1. Token 计数与截断（防止 prompt 超出模型上限）
  2. 带重试的 LLM 调用包装器
  3. 智能错误分类 + 语义化兜底回复

使用方式：
    from app.utils.llm_helper import safe_chat_sync, truncate_messages, count_tokens

    messages = truncate_messages(messages, max_tokens=3000)
    result = safe_chat_sync(spark, messages, retries=2)
"""

import logging
import re
import time

logger = logging.getLogger(__name__)

# ── Token 估算（粗略：中文 ~1.5 tokens/字，英文 ~0.25 tokens/词） ──

def estimate_tokens(text: str) -> int:
    """估算文本的 token 数量

    策略：中文字符 ~1.5 token，英文单词 ~0.25 token，标点/空格 ~0.3 token
    这是近似值，用于防止超限，不要求精确。
    """
    if not text:
        return 0
    chinese = len(re.findall(r'[\u4e00-\u9fff]', text))
    english = len(re.findall(r'[a-zA-Z]+', text))
    other = len(text) - chinese - english
    return int(chinese * 1.5 + english * 0.25 + other * 0.3)


def count_messages_tokens(messages: list[dict]) -> int:
    """估算消息列表的总 token 数"""
    total = 0
    for msg in messages:
        # role + content 的结构开销
        total += 4
        total += estimate_tokens(msg.get("content", ""))
    return total


def truncate_messages(
    messages: list[dict],
    max_tokens: int = 3500,
    keep_system: bool = True,
    max_single_message_tokens: int = 1500,
) -> list[dict]:
    """截断消息列表以控制 token 数量

    策略（P2-FIX 2026-07-11, 修复 13→1 激进截断问题）:
      0. 先截断过长的单条消息 (RAG 检索结果/代码块常 > 3000 tokens)
      1. 始终保留 system prompt
      2. 从最旧的消息开始截断（保留最近的上下文）
      3. 单条消息截断到合理长度

    Args:
        messages: 原始消息列表
        max_tokens: 最大允许 token 数（默认 3500，留空间给输出）
        keep_system: 是否保留 system 消息
        max_single_message_tokens: 单条消息最大 token (默认 1500, 防止 RAG 大 content 撑爆)

    Returns:
        截断后的消息列表
    """
    if count_messages_tokens(messages) <= max_tokens:
        return messages

    # ── 步骤 0: 截短过长的单条消息（防止 RAG/代码块撑爆总 token）──
    # 之前: 1 条 RAG 检索结果 4000 tokens + 12 条历史对话各 200 tokens = 6400 tokens
    #       会被激进 pop 到只剩 1 条, 12 条历史对话全丢
    # 现在: 先把 4000 tokens 的 RAG 截到 1500, 总变成 3900, 保留 12 条历史
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and estimate_tokens(content) > max_single_message_tokens:
            # 保留前 N 字符 (粗略, 因为 estimate_tokens 是估算)
            # 假设 1.5 token/字 (中文), 反推 1500 token ≈ 1000 字
            char_limit = int(max_single_message_tokens / 1.5)  # 保守按中文最密
            if len(content) > char_limit:
                # P2-C 2026-07-11: 保留头尾 (sliding window), 比纯头部保留更多信息
                head_chars = int(char_limit * 0.7)
                tail_chars = char_limit - head_chars
                msg["content"] = (
                    content[:head_chars]
                    + "\n\n...（中间内容已省略）...\n\n"
                    + content[-tail_chars:] if len(content) > char_limit else content
                )
                logger.debug("LLM Helper: 单条消息 sliding 截断 %d → %d 字符 (head=%d, tail=%d)",
                             len(content), head_chars + tail_chars + 20, head_chars, tail_chars)

    if count_messages_tokens(messages) <= max_tokens:
        return messages

    result = []
    system_msg = None

    # 分离 system 消息
    for msg in messages:
        if msg.get("role") == "system" and keep_system:
            system_msg = msg
        else:
            result.append(msg)

    # 从旧到新逐步丢弃历史，直到 token 数满足要求
    system_tokens = estimate_tokens(system_msg.get("content", "")) if system_msg else 0
    threshold = max_tokens - system_tokens
    # 防御: 如果 system 比 max_tokens 还大, 至少给 result 留一条空间
    threshold = max(threshold, 100)
    while result and count_messages_tokens(result) > threshold:
        result.pop(0)

    # 如果还是太长，截断最后一条用户/AI 消息的内容
    if result and count_messages_tokens(result) > max_tokens * 0.8:
        last = result[-1]
        content = last.get("content", "")
        # 保留前 80% 的内容
        cutoff = int(len(content) * 0.8)
        last["content"] = content[:cutoff] + "\n...（内容已截断）"

    if system_msg:
        result.insert(0, system_msg)

    logger.warning("LLM Helper: 消息已截断 %d → %d 条 (tokens ≈ %d)",
                   len(messages), len(result), count_messages_tokens(result))
    return result


# ── 带重试的 LLM 调用 ──

def safe_chat_sync(
    spark,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    retries: int = 2,
    fallback: str = "",
) -> str:
    """带重试 + Token 控制的同步 LLM 调用（非流式，用于简短提取类调用）

    注意：对话生成类调用请使用 safe_chat_stream() 以获得流式体验。

    Args:
        spark: SparkClient 实例
        messages: 消息列表（会自动截断）
        temperature: 温度参数
        max_tokens: 最大输出 token 数
        retries: 重试次数
        fallback: 全部失败后的兜底回复

    Returns:
        LLM 回复文本，或兜底文本
    """
    # 先做 token 截断
    messages = truncate_messages(messages, max_tokens=6000)

    last_error = None
    for attempt in range(retries + 1):
        try:
            result = spark.chat_sync(messages, temperature=temperature, max_tokens=max_tokens)
            if result and result.strip():
                return result.strip()
            logger.warning("LLM Helper: 返回为空 (attempt %d/%d)", attempt + 1, retries + 1)
        except RuntimeError as e:
            last_error = e
            err_msg = str(e)
            # 可重试的错误：网络超时、服务繁忙
            is_retryable = any(kw in err_msg for kw in [
                "timeout", "超时", "连接", "connection", "busy", "繁忙",
                "rate limit", "429", "503", "502",
            ])
            if not is_retryable or attempt >= retries:
                break
            wait = (attempt + 1) * 1.5
            logger.warning("LLM Helper: 调用失败 (%s)，%.1fs 后重试 %d/%d ...",
                          err_msg[:80], wait, attempt + 1, retries)
            time.sleep(wait)
        except Exception as e:
            last_error = e
            logger.error("LLM Helper: 未知错误 (attempt %d/%d): %s", attempt + 1, retries + 1, e)
            break

    # 兜底回复
    if fallback:
        return fallback

    return _classify_and_fallback(last_error)


def _classify_and_fallback(error: Exception | None) -> str:
    """根据错误类型返回有意义的兜底回复"""
    if error is None:
        return "抱歉，我暂时没有获取到有效回复。请换个方式提问试试？"

    err_str = str(error).lower()

    if any(kw in err_str for kw in ["timeout", "超时"]):
        return "响应超时了喵~ 网络可能有点拥堵，请稍后再试一次。"
    if any(kw in err_str for kw in ["rate", "429", "配额", "限额"]):
        return "当前调用频率较高，请稍等片刻再问我哦。"
    if any(kw in err_str for kw in ["auth", "401", "403", "认证", "鉴权"]):
        return "服务认证出现问题，请联系管理员检查配置。"
    if any(kw in err_str for kw in ["token", "max_tokens", "length"]):
        return "问题内容有点长呢~ 能不能简化一下再问我？"

    return "抱歉，处理过程中遇到了一点小问题。请换个方式再试，或者稍后重试。"


# ── 带重试的流式 LLM 调用 ──

def safe_chat_stream(
    spark,
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    retries: int = 2,
    fallback: str = "",
) -> "Generator[str, None, None]":
    """带重试 + Token 控制的流式 LLM 调用

    自动截断过长消息，重试可恢复错误，全部失败后 yield 兜底回复。

    Yields:
        逐 token 的 LLM 回复片段
    """
    messages = truncate_messages(messages, max_tokens=6000)

    for attempt in range(retries + 1):
        try:
            yielded_any = False
            for chunk in spark.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
                if chunk:
                    yielded_any = True
                    yield chunk
            if yielded_any:
                return  # 成功返回
            # 空响应 → 重试
            logger.warning("LLM Helper: 流式返回为空 (attempt %d/%d)", attempt + 1, retries + 1)
        except RuntimeError as e:
            err_msg = str(e)
            is_retryable = any(kw in err_msg for kw in [
                "timeout", "超时", "连接", "connection", "busy", "繁忙",
                "rate limit", "429", "503", "502",
            ])
            if not is_retryable or attempt >= retries:
                break
            wait = (attempt + 1) * 1.5
            logger.warning("LLM Helper: 流式失败 (%s)，%.1fs 后重试 %d/%d ...",
                          err_msg[:80], wait, attempt + 1, retries)
            time.sleep(wait)
        except Exception as e:
            logger.error("LLM Helper: 流式未知错误 (attempt %d/%d): %s", attempt + 1, retries + 1, e)
            break

    # 兜底
    if fallback:
        yield fallback
    else:
        yield _classify_and_fallback(None)



# ── Prompt 长度预警 ──

def check_prompt_length(messages: list[dict], limit: int = 3500, agent_name: str = "") -> bool:
    """检查 prompt 是否超长，超长则记录警告日志

    Returns:
        True 安全, False 超长需截断
    """
    tokens = count_messages_tokens(messages)
    if tokens > limit:
        logger.warning("[%s] Prompt 过长: ≈%d tokens (限制 %d)，建议调用 truncate_messages()",
                      agent_name, tokens, limit)
        return False
    return True
