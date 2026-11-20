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
    """加载白名单快照（缺失抛 ``FileNotFoundError``、损坏抛 ``ValueError``——fail-closed）。

    深校验（评审 G14）：内层必需键与类型逐项验——缺键/类型错/两闭集相交
    一律 ``ValueError``（防「快照 dict 合法但结构残缺 → 消费面 KeyError 500」
    与「agent_allowed∩human_only 交集静默放行」两形态）。
    """
    target = Path(path) if path is not None else SNAPSHOT_PATH
    if not target.is_file():
        raise FileNotFoundError(f"solution_repo 白名单快照缺失（fail-closed）：{target}")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"solution_repo 白名单快照损坏（fail-closed）：{exc}") from exc
    if not isinstance(data, dict) or "path_rules" not in data or "git_ops" not in data:
        raise ValueError("solution_repo 白名单快照缺 path_rules/git_ops 段（fail-closed）")

    rules = data["path_rules"]
    if not isinstance(rules, dict):
        raise ValueError("path_rules 段须为对象（fail-closed）")
    for key in ("allow_roots", "max_patch_bytes", "max_patch_files", "max_patch_changed_lines", "max_file_read_bytes"):
        if key not in rules:
            raise ValueError(f"path_rules 缺必需键 {key}（fail-closed）")
    if not isinstance(rules["allow_roots"], list):
        raise ValueError("path_rules.allow_roots 须为数组（fail-closed）")

    git_ops = data["git_ops"]
    if not isinstance(git_ops, dict):
        raise ValueError("git_ops 段须为对象（fail-closed）")
    allowed = git_ops.get("agent_allowed")
    human = git_ops.get("human_only")
    if not isinstance(allowed, list) or not isinstance(human, list):
        raise ValueError("git_ops.agent_allowed/human_only 须为数组（fail-closed）")
    overlap = sorted(set(allowed) & set(human))
    if overlap:
        raise ValueError(f"agent_allowed 与 human_only 相交（fail-closed）：{overlap}")
    return data
