"""adapters：宿主采集快照（原始 CLI/文件输出）→ 规范化结构。

只做形状规整（camelCase→snake_case、缺键容错、类型收敛），不做业务判断；
openfde status 的字段集以 CLI `status -e <slug> --json` 实测输出为准
（2026-10-25：engagement/episodes/pending/entities/activeFacts/expiredFacts/openTasks）。
"""

from __future__ import annotations

from typing import Any


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def normalize_openfde_status(raw: object) -> dict[str, Any]:
    """`openfde status -e <slug> --json` 输出 → snake_case 计数字典。"""
    if not isinstance(raw, dict):
        return {}
    return {
        "engagement": raw.get("engagement") if isinstance(raw.get("engagement"), str) else None,
        "episodes": _int_or_none(raw.get("episodes")),
        "pending": _int_or_none(raw.get("pending")),
        "entities": _int_or_none(raw.get("entities")),
        "active_facts": _int_or_none(raw.get("activeFacts")),
        "expired_facts": _int_or_none(raw.get("expiredFacts")),
        "open_tasks": _int_or_none(raw.get("openTasks")),
    }


def normalize_fdeops_dir(raw: object) -> dict[str, Any]:
    """宿主侧 fdeops 目录探针 → 规范化（CLI 未装机，探针见 bridge-poll.mjs）。"""
    if not isinstance(raw, dict):
        return {}
    files = raw.get("files")
    return {
        "exists": raw.get("exists") is True,
        "fde_initialized": raw.get("fde_initialized") is True,
        "bound_path": raw.get("bound_path") if isinstance(raw.get("bound_path"), str) else None,
        "files": [f for f in files if isinstance(f, str)][:50] if isinstance(files, list) else [],
    }
