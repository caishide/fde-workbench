"""solution_repo 白名单快照只读加载（AF3-WP1；沿 ``action_execution.connectors.load_whitelist``
fail-closed 先例）。

快照＝``whitelist.json``（FROZEN v1.0.0，2026-11-20 P1 D-C 拍板冻结）：
- 缺失/损坏一律抛错（调用方 fail-closed 全拒）——禁改清单第 5/7 项同款纪律；
- 运行时不可变：变更只能走白名单 v2＋评审（20 号 §2 D2）。
"""
from __future__ import annotations

import json
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent
SNAPSHOT_PATH = SERVER_ROOT / "whitelist.json"


def load_whitelist(path: str | Path | None = None) -> dict:
    """加载白名单快照（缺失抛 ``FileNotFoundError``、损坏抛 ``ValueError``——fail-closed）。"""
    target = Path(path) if path is not None else SNAPSHOT_PATH
    if not target.is_file():
        raise FileNotFoundError(f"solution_repo 白名单快照缺失（fail-closed）：{target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"solution_repo 白名单快照损坏（fail-closed）：{exc}") from exc
    if not isinstance(data, dict) or "path_rules" not in data or "git_ops" not in data:
        raise ValueError("solution_repo 白名单快照缺 path_rules/git_ops 段（fail-closed）")
    return data
