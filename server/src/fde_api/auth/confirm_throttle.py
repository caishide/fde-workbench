"""密码确认尝试限流（单一权威，CR-047）。

verify-password 与各域高风险写密码确认闸共用：同 key、同阈值、同窗口，
与 control/api_actions.decide_action 的失败计数同源（计数原语自此收口单点）。
键前缀沿用 decide_action 既有值（兼容已在线计数），按用户 id 维度累计。
"""

from __future__ import annotations

from flask import current_app

CONFIRM_FAILURE_LIMIT = 5
CONFIRM_FAILURE_WINDOW_SECONDS = 900
CONFIRM_FAILURE_KEY_PREFIX = "fde:ai:confirmation-failures:"

TOO_MANY_ATTEMPTS_CODE = "too_many_attempts"
TOO_MANY_ATTEMPTS_MESSAGE = "密码错误次数过多，请 15 分钟后重试。"


def _client():
    return current_app.extensions["fde_api_redis"]


def confirm_attempts_key(user_id: str) -> str:
    return CONFIRM_FAILURE_KEY_PREFIX + user_id


def confirm_attempts_blocked(user_id: str) -> bool:
    """该用户密码确认失败次数是否已达上限（达到即拒绝本次尝试）。"""
    return int(_client().get(confirm_attempts_key(user_id)) or 0) >= CONFIRM_FAILURE_LIMIT


def record_confirm_failure(user_id: str) -> None:
    """记一次失败：窗口内累计到上限后拒绝后续尝试。"""
    client = _client()
    key = confirm_attempts_key(user_id)
    client.incr(key)
    client.expire(key, CONFIRM_FAILURE_WINDOW_SECONDS)
