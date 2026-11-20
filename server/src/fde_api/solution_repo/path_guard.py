"""仓工具面路径白名单判定（AF3-WP1；04 §3.3 A1 四拒＋D2「落机器可检」）。

三层判定，全部纯函数优先（fs 实探独立成 ``check_path_fs``，服务面读文件前调用）：

1. ``check_path``（字符串形状面）：规范化→穿越四形态→四拒部件级判定→
   allow_roots 前缀匹配；
2. ``check_path_fs``（文件系统面）：形状面通过后逐级 symlink 实探——叶子与
   中间目录都查，解析后逃出 workspace_root 即拒（侦察：workbench 无 symlink
   先例，AF3 自建；S-AF3-05）；
3. ``check_patch``（Patch 汇总面）：逐条目形状面＋三上限（字节/文件数/变更行，
   D-C 已批 512KB/100 文件/2 万行）。

四拒语义（部件级，比 glob 引擎更可预测）：任一路径部件 == ``.git`` 或
``hooks`` 即拒；连续部件 ``.github``+``workflows`` 即拒（任意深度）。宽拒绝
``hooks`` 目录是受控仓 fail-closed 姿态（设计件 §3 声明）；``core.hooksPath``
配置变更面由 ``git_boundary`` human_only 闭集拒（S-AF3-11）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

# 拒绝码闭集（与 errors.py 对齐；判定层不抛异常——verdict 让调用方决定信封）
CODE_PROTECTED = "protected_path"        # S-AF3-01/02/03：.git/**、hooks、.github/workflows/**
CODE_ESCAPE = "path_escape"              # S-AF3-04：穿越/绝对路径/盘符/反斜杠/空部件
CODE_OUTSIDE = "outside_allow_roots"     # S-AF3-07：allow_roots 外
CODE_SYMLINK = "symlink_escape"          # S-AF3-05：symlink 逃逸
CODE_OVERSIZE = "oversize_patch"         # S-AF3-06：三上限

_DENIED_PARTS = frozenset({".git", "hooks"})

# verdict.code → 域错误码/用户消息（errors.py 闭集映射；403 面＝保护路径，
# 422 面＝形状/越界）——判定层单一映射（service/patch_plan 共用，WP2 自
# patch_plan/service 本地副本上收至此防循环依赖）。
VERDICT_ERRORS: dict[str, str] = {
    "protected_path": "protected_path_rejected",
    "path_escape": "path_escape_rejected",
    "outside_allow_roots": "outside_allow_roots",
    "symlink_escape": "symlink_escape_rejected",
    "oversize_patch": "oversize_patch",
}

VERDICT_MESSAGES: dict[str, str] = {
    "protected_path_rejected": "保护路径拒绝（.git/**、hooks、.github/workflows/**）。",
    "path_escape_rejected": "路径穿越形态拒绝（..、绝对路径、盘符、反斜杠）。",
    "outside_allow_roots": "越界路径（不在绑定 allow_roots 内）。",
    "symlink_escape_rejected": "符号链接逃逸拒绝。",
    "oversize_patch": "Patch 超出上限（bytes/files/lines）。",
}


class VerdictErrorPayload(NamedTuple):
    code: str
    message: str


def verdict_error(verdict: "Verdict") -> VerdictErrorPayload:
    return VerdictErrorPayload(VERDICT_ERRORS[verdict.code], VERDICT_MESSAGES[VERDICT_ERRORS[verdict.code]])


@dataclass(frozen=True)
class Verdict:
    ok: bool
    code: str  # 通过时为 ""
    reason: str


_OK = Verdict(ok=True, code="", reason="")


def check_path(raw: str, *, allow_roots: tuple[str, ...]) -> Verdict:
    """字符串形状面判定（不触盘）：穿越→四拒→allow_roots。

    大小写口径（评审 G17 声明）：四拒部件判定**大小写不敏感**（`.GIT`/`Hooks`
    同拒）；allow_roots 首部件匹配**大小写敏感**（`Ontology/` 视为越界）——
    不一致方向为 fail-closed（误拒不泄露），Windows 不敏感盘上以快照登记
    的规范小写目录名为准。
    """
    if not raw or raw.strip() == "":
        return Verdict(False, CODE_ESCAPE, "空路径")
    if raw.startswith("/") or raw.startswith("\\"):
        return Verdict(False, CODE_ESCAPE, "绝对路径拒绝")
    if len(raw) >= 2 and raw[1] == ":":
        return Verdict(False, CODE_ESCAPE, "盘符路径拒绝")
    if ":" in raw:
        # 中段冒号＝NTFS ADS 流形态（如 ontology/x.yaml:ads）——WP2 写面前
        # 的泄露/写入旁路面，读取面同拒（评审 G16）。
        return Verdict(False, CODE_ESCAPE, "冒号路径拒绝（NTFS ADS 形态）")
    if "\\" in raw:
        return Verdict(False, CODE_ESCAPE, "反斜杠分隔拒绝")
    if any(ord(c) < 32 for c in raw):
        return Verdict(False, CODE_ESCAPE, "控制字符拒绝")
    parts = [p for p in raw.split("/")]
    if any(p == "" for p in parts):
        return Verdict(False, CODE_ESCAPE, "空路径部件拒绝")
    if any(p == ".." or p == "." for p in parts):
        return Verdict(False, CODE_ESCAPE, "相对穿越部件拒绝")

    # 四拒（部件级，任意深度）：.git / hooks / .github/workflows。
    # Win32 别名防绕（评审 G7）：剥尾点/尾空格后判定——`.git.`/`hooks `
    # 在 Windows 上打开的就是 `.git`/`hooks` 本体。
    for i, part in enumerate(parts):
        stripped = part.rstrip(". ")
        if stripped.lower() in _DENIED_PARTS:
            return Verdict(False, CODE_PROTECTED, f"保护路径部件拒绝：{part}")
        if stripped.lower() == ".github" and i + 1 < len(parts) and parts[i + 1].rstrip(". ").lower() == "workflows":
            return Verdict(False, CODE_PROTECTED, "保护路径拒绝：.github/workflows")

    # allow_roots 前缀（第一部件须命中白名单根集；大小写敏感——见 docstring 口径声明）
    roots = {r.rstrip("/") for r in allow_roots if r.rstrip("/")}
    if parts[0] not in roots:
        return Verdict(False, CODE_OUTSIDE, f"越界路径（allow_roots={sorted(roots)}）")
    return _OK


def check_path_fs(
    raw: str | Path,
    *,
    workspace_root: Path,
    allow_roots: tuple[str, ...],
) -> Verdict:
    """fs 实探面：形状面通过后，从 workspace_root 逐级到目标做 symlink 检查。

    任一级为 symlink 且解析后不在 workspace_root 内 → ``symlink_escape``；
    workspace_root 自身先归一（真实绝对路径），防伪根。
    """
    raw_text = str(raw)
    shape = check_path(raw_text, allow_roots=allow_roots)
    if not shape.ok:
        return shape

    root = workspace_root.resolve()
    current = root
    for part in Path(raw_text).parts:
        current = current / part
        if current.is_symlink():
            resolved = current.resolve()
            if not resolved.is_relative_to(root):
                return Verdict(False, CODE_SYMLINK, f"符号链接逃逸：{current} → {resolved}")
    if current.exists() and not current.resolve().is_relative_to(root):
        return Verdict(False, CODE_SYMLINK, f"解析后越出工作区：{current} → {current.resolve()}")
    return _OK


def verify_resolved(real_path: str | Path, root: Path, rel_path: str, allow_roots: tuple[str, ...]) -> Verdict:
    """评审 D1/H2 复核 helper（读面打开后／写面写入前共用）：
    **解析真实路径**须 (a) 仍在工作区内（逃逸拒）且 (b) 相对工作区的路径过
    check_path 四拒＋allow_roots 全判（仓内链接 ontology/x.yaml→.git/config
    或 →server/ 这类「解析不逃逸但落入保护/越界区」同拒——probe 面 check_path_fs
    只判逃逸不判落点，本 helper 补落点维度）。"""
    real = Path(real_path)
    if not real.is_relative_to(root):
        return Verdict(False, CODE_SYMLINK, f"符号链接逃逸（复核）：解析后越出工作区 {real}")
    rel = real.relative_to(root).as_posix()
    return check_path(rel, allow_roots=allow_roots)


@dataclass(frozen=True)
class PatchEntry:
    """类型化 Patch 条目最小形状（WP2 升格为完整 PatchPlan 契约；本件只承载
    path_guard 所需三量：目标路径＋字节数＋变更行数）。"""

    path: str
    new_bytes: int
    changed_lines: int


def check_patch(
    entries: tuple[PatchEntry, ...],
    *,
    allow_roots: tuple[str, ...],
    max_bytes: int = 524288,
    max_files: int = 100,
    max_lines: int = 20000,
) -> Verdict:
    """Patch 汇总面：逐条目形状面（首个失败即返回）＋三上限逐项判定。

    上限判定用 ``>=`` 恰达语义（等于上限通过、超出拒绝）；reason 携带
    维度名（bytes/files/lines）供结构化拒绝信息消费（AF2④ 携带）。
    """
    for entry in entries:
        shape = check_path(entry.path, allow_roots=allow_roots)
        if not shape.ok:
            return shape
        if entry.new_bytes < 0 or entry.changed_lines < 0:
            # 评审 G16：负值会拉低合计绕过三上限——非负守卫。
            return Verdict(False, CODE_OVERSIZE, "负值拒绝（new_bytes/changed_lines 须非负）")

    total_bytes = sum(e.new_bytes for e in entries)
    if total_bytes > max_bytes:
        return Verdict(False, CODE_OVERSIZE, f"bytes 超限：{total_bytes} > {max_bytes}")
    if len(entries) > max_files:
        return Verdict(False, CODE_OVERSIZE, f"files 超限：{len(entries)} > {max_files}")
    total_lines = sum(e.changed_lines for e in entries)
    if total_lines > max_lines:
        return Verdict(False, CODE_OVERSIZE, f"lines 超限：{total_lines} > {max_lines}")
    return _OK
