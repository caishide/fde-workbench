"""按评测质量路由模型（N6/G-13 DoD② 的 fail-safe 薄缝）。

数据源＝N4 CI eval 产出的**按 purpose 模型质量摘要**（``FDE_AI_QUALITY_ROUTE_SUMMARY_URI``
指向的本地 JSON 指针，门禁证据同款纪律：摘要原件留本地、不入仓）。摘要形状::

    {"<purpose>": {"provider": "...", "model": "...", "score": <float>}, ...}

fail-safe 四道闸（任一不满足即 ``None``＝沿用既有模型解析链，**绝不切换**）：
① 出厂闸 ``FDE_AI_QUALITY_ROUTE_ENABLED`` 默认 False；
② 摘要指针为空 / 文件不可读 / JSON 不可解析；
③ 摘要无该 purpose 行（或行形状不合法）；
④ 质量分低于 ``FDE_AI_QUALITY_ROUTE_MIN_SCORE``（缺省 0.8＝协议 v0 PASS 截断）。

任务书 N6「明确不做」：不在无评测数据时自动切模型——本模块在任何缺数据/
未开闸情形下都必须零行为（``test_prompt_registry.py`` 的出厂默认安全钉＋
fail-safe 矩阵钉住）。
"""

from __future__ import annotations

import json
from typing import Any

from flask import current_app


def resolve_quality_route(purpose: str) -> dict[str, str] | None:
    """按评测摘要为该 purpose 选模型；任何缺数据/未开闸情形恒 ``None``。"""
    settings = current_app.config["SETTINGS"]
    if not getattr(settings, "ai_quality_route_enabled", False):
        return None
    summary = _load_summary(getattr(settings, "ai_quality_route_summary_uri", ""))
    if summary is None:
        return None
    entry = summary.get(purpose)
    if not isinstance(entry, dict):
        return None
    floor = getattr(settings, "ai_quality_route_min_score", 0.8)
    score = entry.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or score < floor:
        return None
    provider = entry.get("provider")
    model = entry.get("model")
    if not isinstance(provider, str) or not provider:
        return None
    if not isinstance(model, str) or not model:
        return None
    return {"provider": provider, "model": model}


def _load_summary(uri: str) -> dict[str, Any] | None:
    if not uri:
        return None
    try:
        with open(uri, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
