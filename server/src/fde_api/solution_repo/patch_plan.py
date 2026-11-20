"""类型化 PatchPlan 契约（AF3-WP2；沿 AF2 WP2 TransformPlan 键集精确纪律）。

顶层键闭集 ``{patch_id, base_commit, entries}``；entry 键闭集
``{path, operation, content}``；operation 闭集 ``{create, update, delete}``；
delete 无 content、create/update 必有 content（str）。未知键/缺键/越值一律
``SolutionRepoError("validation_failed")`` 且 message 携带未知键名（AF2④
结构化拒绝信息消费）。path 走 ``check_path``（四拒/越界/穿越形状面）、content
体量走 ``check_patch`` 三上限（bytes/files/lines，负值守卫）。

零自由表达式槽：没有 shell 命令、没有文件名模式、没有「附加载荷」——Patch
夹带的任意脚本/装饰载荷（D3 红线）在这里就没有表达位。
"""
from __future__ import annotations

import re
from typing import Any

from fde_api.solution_repo.errors import SolutionRepoError
from fde_api.solution_repo.path_guard import PatchEntry, VERDICT_ERRORS, check_patch, check_path

TOP_LEVEL_KEYS = frozenset({"patch_id", "base_commit", "entries"})
ENTRY_KEYS = frozenset({"path", "operation", "content"})
OPERATIONS = frozenset({"create", "update", "delete"})

_PATCH_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")


def _reject(message: str, details: dict | None = None) -> SolutionRepoError:
    return SolutionRepoError("validation_failed", message, details=details)


def validate_patch_plan(payload: Any, *, allow_roots: tuple[str, ...]) -> dict[str, Any]:
    """键集精确校验＋规范化。返回 ``{patch_id, base_commit, entries}``
    （entries 为 ``{path, operation, content|None}`` 列表）；非法即抛域错误。"""
    if not isinstance(payload, dict):
        raise _reject("PatchPlan 须为 JSON 对象。")
    unknown_top = sorted(set(payload) - TOP_LEVEL_KEYS)
    if unknown_top:
        raise _reject(f"PatchPlan 含未登记键（键集精确）：{unknown_top}", details={"unknown_keys": unknown_top})
    missing_top = sorted(TOP_LEVEL_KEYS - set(payload))
    if missing_top:
        raise _reject(f"PatchPlan 缺必需键：{missing_top}", details={"missing_keys": missing_top})

    patch_id = payload["patch_id"]
    if not isinstance(patch_id, str) or not _PATCH_ID_RE.match(patch_id):
        raise _reject("patch_id 须为 1..128 字符且匹配 [A-Za-z0-9][A-Za-z0-9._-]*。", details={"patch_id": patch_id})
    base_commit = payload["base_commit"]
    if not isinstance(base_commit, str) or not _HEX40_RE.match(base_commit):
        raise _reject("base_commit 须为 40 位十六进制 commit hash。", details={"base_commit": base_commit})
    entries_raw = payload["entries"]
    if not isinstance(entries_raw, list) or not entries_raw:
        raise _reject("entries 须为非空数组。")

    whitelist = _limits_from_caller(allow_roots)
    entries: list[dict[str, Any]] = []
    for raw in entries_raw:
        if not isinstance(raw, dict):
            raise _reject("entry 须为 JSON 对象。")
        unknown_entry = sorted(set(raw) - ENTRY_KEYS)
        if unknown_entry:
            raise _reject(
                f"entry 含未登记键（键集精确）：{unknown_entry}",
                details={"unknown_keys": unknown_entry, "path": raw.get("path")},
            )
        missing_entry = sorted(ENTRY_KEYS - set(raw) - {"content"})
        if missing_entry:
            raise _reject(
                f"entry 缺必需键：{missing_entry}",
                details={"missing_keys": missing_entry, "path": raw.get("path")},
            )
        path = raw["path"]
        operation = raw["operation"]
        content = raw.get("content")
        if operation not in OPERATIONS:
            raise _reject(
                f"operation 须为 {sorted(OPERATIONS)} 闭集内值。",
                details={"operation": operation, "path": path},
            )
        if operation == "delete":
            if "content" in raw:
                raise _reject("delete 条目不得携带 content。", details={"path": path})
            entry_content = None
        else:
            if not isinstance(content, str):
                raise _reject(f"{operation} 条目 content 须为字符串。", details={"path": path})
            entry_content = content
        entries.append({"path": path, "operation": operation, "content": entry_content})

    # 路径形状面＋三上限（bytes/files/lines；负值守卫在 check_patch）——
    # 与 check_path_fs 的 fs 实探在 apply 执行面分层衔接。
    for entry in entries:
        shape = check_path(entry["path"], allow_roots=allow_roots)
        if not shape.ok:
            raise SolutionRepoError(
                VERDICT_ERRORS[shape.code],
                f"entry 路径被路径白名单拒绝：{shape.reason}",
                details={"path": entry["path"], "reason": shape.reason},
            )
    patch_entries = tuple(
        PatchEntry(
            path=e["path"],
            new_bytes=len((e["content"] or "").encode("utf-8")),
            changed_lines=(e["content"] or "").count("\n") + (1 if e["content"] else 0),
        )
        if e["operation"] != "delete"
        else PatchEntry(path=e["path"], new_bytes=0, changed_lines=0)
        for e in entries
    )
    verdict = check_patch(patch_entries, **whitelist)
    if not verdict.ok:
        raise SolutionRepoError(
            VERDICT_ERRORS[verdict.code],
            f"Patch 汇总被拒：{verdict.reason}",
            details={"reason": verdict.reason},
        )
    return {"patch_id": patch_id, "base_commit": base_commit, "entries": entries}


def _limits_from_caller(allow_roots: tuple[str, ...]) -> dict[str, Any]:
    """三上限从冻结快照取（调用方不得放宽——G14 深校验保证键存在）。"""
    from fde_api.solution_repo.snapshot import load_whitelist

    rules = load_whitelist()["path_rules"]
    return {
        "allow_roots": allow_roots,
        "max_bytes": rules["max_patch_bytes"],
        "max_files": rules["max_patch_files"],
        "max_lines": rules["max_patch_changed_lines"],
    }
