"""WP-E SES 发信策略：纯逻辑层（goal-r3 G3 先行钉住，G9 落地客户端与回调端点）。

设计约束（docs/验收场景矩阵-G3.md 链 3）：
- 总开关 FDE_SES_ENABLED 未显式开启时模块整体禁用（默认关闭，不影响现有行为；
  SES 生产批复下来只需改配置启用）。
- 四态反馈：sent（送达）/ bounce（退信）/ complaint（投诉）/ throttle（限流）。
  bounce 与 complaint 不可重试且地址进抑制名单；throttle 可重试（指数退避、上限固定）。
- 幂等：同 message_id 只发一次，重复决策为 drop_duplicate（重试=同 id 新 attempt）。
- 每日限额：当日已发数达到上限即拒绝（沙盒口径默认 10 封/天，可配）。
- 发信域约束：只用配置的子域发信（如 mail.somwyn.com），主域 somwyn.com 不发信。

本模块不 import 任何 AWS/网络依赖——可测性与 G9 接线解耦。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable, Literal

FeedbackEvent = Literal["sent", "bounce", "complaint", "throttle"]

SANDBOX_DAILY_LIMIT = 10
MAX_RETRY_ATTEMPTS = 3
RETRY_BASE_DELAY = timedelta(minutes=1)
RETRY_MAX_DELAY = timedelta(minutes=15)

SEND = "send"
DROP_DISABLED = "drop_disabled"
DROP_DUPLICATE = "drop_duplicate"
DROP_SUPPRESSED = "drop_suppressed"
DROP_OVER_QUOTA = "drop_over_quota"
DROP_DOMAIN = "drop_sender_domain_forbidden"


@dataclass(frozen=True, slots=True)
class SendDecision:
    """一次发送请求的裁决：action 说明去留，attempt 供退避计算。"""

    action: str
    retryable: bool = False
    attempt: int = 0


def feedback_is_retryable(event: FeedbackEvent) -> bool:
    """四态分类：只有 throttle 值得重试；bounce/complaint 是地址级死刑。"""
    if event == "throttle":
        return True
    if event in ("sent", "bounce", "complaint"):
        return False
    raise ValueError(f"unknown feedback event: {event}")


def should_suppress(event: FeedbackEvent) -> bool:
    """bounce/complaint 把地址拉进抑制名单；sent/throttle 不影响地址。"""
    return event in ("bounce", "complaint")


def next_retry_delay(attempt: int) -> timedelta:
    """指数退避 1m→2m→4m，封顶 15m；attempt 从 1 起算。"""
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
    return min(delay, RETRY_MAX_DELAY)


def retry_allows(attempt: int) -> bool:
    """attempt 超过上限即放弃（含首发，attempt=0 表示尚未重试过）。"""
    return attempt < MAX_RETRY_ATTEMPTS


def is_allowed_sender_domain(domain: str, allowed_subdomain_root: str) -> bool:
    """发信域必须是允许子域根（如 mail.somwyn.com）本身或其子域。

    主域（如 somwyn.com）明确拒绝——项目口径主域不发信，避免 SPF/DKIM 面
    扩大到主域全部邮件。大小写与尾部点归一后比较。
    """
    normalized = domain.strip().rstrip(".").lower()
    root = allowed_subdomain_root.strip().rstrip(".").lower()
    if not normalized or not root:
        return False
    return normalized == root or normalized.endswith("." + root)


def decide_send(
    *,
    enabled: bool,
    message_id: str,
    seen_message_ids: Iterable[str],
    recipient_suppressed: bool,
    today_sent_count: int,
    daily_limit: int = SANDBOX_DAILY_LIMIT,
    attempt: int = 0,
) -> SendDecision:
    """发送闸门（纯函数）：开关 → 幂等 → 抑制 → 限额，全过才 send。

    判定顺序固定：任何一步拒绝都不看后面的条件，保证决策可复现、可测。
    """
    if not enabled:
        return SendDecision(DROP_DISABLED)
    if message_id in set(seen_message_ids):
        return SendDecision(DROP_DUPLICATE, attempt=attempt)
    if recipient_suppressed:
        return SendDecision(DROP_SUPPRESSED, attempt=attempt)
    if today_sent_count >= daily_limit:
        return SendDecision(DROP_OVER_QUOTA, attempt=attempt)
    return SendDecision(SEND, attempt=attempt)
