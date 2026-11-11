"""存储物理布局主体段与五步迁移状态机（M4 批次 D；任务书 §7-M4）。

**逻辑键不变**：DB 里存的仍是 ``projects/{project_id}/...`` 逻辑键（零键列
迁移、零回填）；物理布局在本模块翻译——写路径按状态机决定落旧键/新键/
双写，读路径按状态机决定回落顺序。

- **新键约定**：``org/{org_id}/<逻辑键>``（企业归属）；平台身份段
  ``platform/<逻辑键>``（与 ``org_id=NULL`` 平台身份语义同构）。
  ``document-templates`` 逻辑根属平台级资产 ⇒ 恒 ``platform/`` 段。
- **五步状态机**（``FDE_STORAGE_LAYOUT``，出厂默认 ``legacy``＝现状零回归）：
  ``legacy``（写旧读旧）→ ``dual_write``（写旧＋新、读旧）→ ``read_new``
  （写新、读新优先回落旧——迁移核对期）→ ``readonly``（写新、读新回落旧
  ——旧根冻结）→ ``retired``（写新读新、零回落）。
- **S2/S3**（agent 工作区／转写草稿）：短生命周期临时面**存量不搬**，
  只新写入用新段（见 agents/transcripts 两处路径组装）。
- 单一权威：状态解析、段归属、物理键翻译全部在本模块（调用方不自行拼段
  ——与 ``subject_budget_exceeded`` 同款「判定只认一处」纪律）。
"""
from __future__ import annotations

from typing import BinaryIO

from sqlalchemy.orm import Session

from fde_api.storage.base import StorageError

# 五步状态闭集（出厂默认 legacy＝现状零回归；漂移即 fail-closed）。
STORAGE_LAYOUT_STATES: tuple[str, ...] = (
    "legacy",
    "dual_write",
    "read_new",
    "readonly",
    "retired",
)

# 平台身份物理段（org_id=None ⇒ platform；与 orgs 平台身份语义同构）。
PLATFORM_SEGMENT = "platform"

# 平台级逻辑根（非项目资产，恒走 platform 段）。
_PLATFORM_LOGICAL_ROOTS = frozenset({"document-templates"})


def resolve_storage_layout(settings) -> str:
    """解析存储布局状态（闭集校验 fail-closed；缺省 legacy＝现状零回归）。"""
    raw = getattr(settings, "storage_layout", None) or "legacy"
    if raw not in STORAGE_LAYOUT_STATES:
        raise StorageError("storage_layout_invalid")
    return raw


def current_layout() -> str:
    """当前请求/作业上下文的布局状态（settings 单一来源）。"""
    from flask import current_app

    return resolve_storage_layout(current_app.config["SETTINGS"])


def org_object_prefix(org_id: str | None) -> str:
    """主体物理段：企业归属 ⇒ ``org/{org_id}``；平台身份 ⇒ ``platform``。"""
    if org_id is not None and (not isinstance(org_id, str) or not org_id):
        raise StorageError("invalid_object_key")
    return f"org/{org_id}" if org_id else PLATFORM_SEGMENT


def _project_id_of(logical_key: str) -> str | None:
    """从逻辑键解析项目段；非项目根（document-templates）⇒ None（平台级）。"""
    parts = logical_key.split("/")
    if len(parts) >= 2 and parts[0] == "projects":
        return parts[1]
    return None


def prefixed_object_key(logical_key: str, org_id: str | None) -> str:
    """新物理键＝``<主体段>/<逻辑键>``。"""
    return f"{org_object_prefix(org_id)}/{logical_key}"


def _org_for_key(session: Session, logical_key: str) -> str | None:
    """逻辑键归属解析：项目根 ⇒ 项目归属 org（批次 C helper 同语义）；
    非项目根 ⇒ 平台级。"""
    from fde_api.jobs.outbox import subject_org_of_project

    project_id = _project_id_of(logical_key)
    if project_id is None:
        return None
    return subject_org_of_project(session, project_id)


def physical_write_targets(
    session: Session, logical_key: str, *, layout: str
) -> tuple[str, ...]:
    """写路径物理键闭集：legacy ⇒ 旧键；dual_write ⇒ 旧＋新；其余 ⇒ 仅新。"""
    if layout not in STORAGE_LAYOUT_STATES:
        raise StorageError("storage_layout_invalid")
    if layout == "legacy":
        return (logical_key,)
    prefixed = prefixed_object_key(logical_key, _org_for_key(session, logical_key))
    if layout == "dual_write":
        return (logical_key, prefixed)
    return (prefixed,)


def physical_read_candidates(
    session: Session, logical_key: str, *, layout: str
) -> tuple[str, ...]:
    """读路径回落序：legacy/dual_write ⇒ 旧；read_new/readonly ⇒ 新优先回落旧；
    retired ⇒ 仅新（零回落）。"""
    if layout not in STORAGE_LAYOUT_STATES:
        raise StorageError("storage_layout_invalid")
    if layout in ("legacy", "dual_write"):
        return (logical_key,)
    prefixed = prefixed_object_key(logical_key, _org_for_key(session, logical_key))
    if layout in ("read_new", "readonly"):
        return (prefixed, logical_key)
    return (prefixed,)


def open_read_stream(
    storage, session: Session, logical_key: str, *, layout: str
) -> BinaryIO:
    """按回落序打开读流（首个命中者胜出；全落空 ⇒ object_not_found）。"""
    last: StorageError | None = None
    for candidate in physical_read_candidates(session, logical_key, layout=layout):
        try:
            return storage.open_stream(candidate)
        except StorageError as error:
            last = error
    raise last if last is not None else StorageError("object_not_found")


def existing_read_key(
    storage, session: Session, logical_key: str, *, layout: str
) -> str:
    """按回落序找到首个实际在场的物理键（供 sign_download 签物理键）；
    全落空 ⇒ object_not_found。"""
    from fde_api.storage.base import StorageNotFoundError

    last: StorageError | None = None
    for candidate in physical_read_candidates(session, logical_key, layout=layout):
        try:
            storage.head(candidate)
            return candidate
        except StorageNotFoundError as error:
            last = error
    raise last if last is not None else StorageNotFoundError("object_not_found")


__all__ = [
    "PLATFORM_SEGMENT",
    "current_layout",
    "STORAGE_LAYOUT_STATES",
    "existing_read_key",
    "open_read_stream",
    "org_object_prefix",
    "physical_read_candidates",
    "physical_write_targets",
    "prefixed_object_key",
    "resolve_storage_layout",
]
