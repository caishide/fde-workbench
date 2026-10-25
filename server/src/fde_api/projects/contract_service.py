"""contract_service：P4 合同台账（设计 §6）——只存指针与关键条款摘要。

PDF 本体在 fdeops 文件系统（A4：workbench 不存内容，source_uri 为
fdeops:// 指针 + content_hash）；DB 只记签约日/账期/验收窗口/终止条款摘要。
每 (project, sow_type) 一行 upsert（A/B/C/D 四类 SOW）。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Mapping

from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.extensions import db
from fde_api.projects.events import record_event
from fde_api.projects.permissions import project_access
from fde_api.workbench.models import Contract, Project

SOW_TYPES = ("a", "b", "c", "d")
SOW_LABELS = {"a": "SOW-A 诊断", "b": "SOW-B 试点", "c": "SOW-C 集成", "d": "SOW-D 陪跑"}

_HEX64_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
_POINTER_PREFIXES = ("fdeops://", "openfde://")


class ContractServiceError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def list_contracts(*, actor: User, project_id: str) -> dict[str, Any]:
    session = db.session()
    try:
        with session.begin():
            project = _load_project(session, actor, project_id)
            rows = list(
                session.scalars(
                    select(Contract)
                    .where(Contract.project_id == project.id)
                    .order_by(Contract.sow_type)
                )
            )
            # 台账视图按四类补位，未建档显示空位
            by_sow = {row.sow_type: _serialize_contract(row) for row in rows}
            return {
                "contracts": [
                    by_sow.get(sow_type) or {"sow_type": sow_type, "recorded": False}
                    for sow_type in SOW_TYPES
                ]
            }
    finally:
        session.close()


def record_contract(
    *, actor: User, project_id: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    """登记/更新一份 SOW 台账（upsert by sow_type）。"""
    sow_type = payload.get("sow_type")
    if sow_type not in SOW_TYPES:
        raise ContractServiceError("invalid_request", "sow_type 必须是 a/b/c/d。", 400)
    session = db.session()
    try:
        with session.begin():
            project = _load_project(session, actor, project_id, manage=True)
            row = session.scalar(
                select(Contract).where(
                    Contract.project_id == project.id, Contract.sow_type == sow_type
                )
            )
            created = row is None
            if row is None:
                row = Contract(project_id=project.id, sow_type=sow_type)

            changes: dict[str, Any] = {}
            if "signed_at" in payload:
                row.signed_at = _parse_date(payload.get("signed_at"))
                changes["signed_at"] = row.signed_at.isoformat() if row.signed_at else None
            if "payment_terms" in payload:
                row.payment_terms = _text(payload.get("payment_terms"))
                changes["payment_terms"] = row.payment_terms
            if "acceptance_window_days" in payload:
                window = payload.get("acceptance_window_days")
                if isinstance(window, bool) or not isinstance(window, int) or window < 1:
                    raise ContractServiceError(
                        "invalid_request", "acceptance_window_days 必须是 ≥1 的整数（默认 15）。", 400
                    )
                row.acceptance_window_days = window
                changes["acceptance_window_days"] = window
            if "termination_terms" in payload:
                row.termination_terms = _text(payload.get("termination_terms"))
                changes["termination_terms"] = row.termination_terms
            if "source_uri" in payload:
                source_uri = payload.get("source_uri")
                if source_uri is not None:
                    if not isinstance(source_uri, str) or not source_uri.startswith(
                        _POINTER_PREFIXES
                    ):
                        raise ContractServiceError(
                            "invalid_source_uri",
                            "source_uri 必须是 fdeops:// 或 openfde:// 指针（A4：只存指针）。",
                            400,
                        )
                    if len(source_uri) > 500:
                        raise ContractServiceError("invalid_request", "source_uri 过长（≤500）。", 400)
                row.source_uri = source_uri
                changes["source_uri"] = source_uri
            if "content_hash" in payload:
                content_hash = payload.get("content_hash")
                if content_hash is not None and (
                    not isinstance(content_hash, str)
                    or not _HEX64_PATTERN.fullmatch(content_hash)
                ):
                    raise ContractServiceError(
                        "invalid_request", "content_hash 必须是 64 位十六进制 sha256。", 400
                    )
                row.content_hash = content_hash
                changes["content_hash"] = content_hash
            if "note" in payload:
                row.note = _text(payload.get("note"))
                changes["note"] = row.note

            if created:
                session.add(row)
            session.flush()
            record_event(
                session,
                actor,
                "contract_recorded" if created else "contract_updated",
                row,
                {"sow_type": sow_type, **changes},
            )
            return _serialize_contract(row)
    finally:
        session.close()


def _serialize_contract(row: Contract) -> dict[str, Any]:
    return {
        "id": row.id,
        "sow_type": row.sow_type,
        "sow_label": SOW_LABELS[row.sow_type],
        "recorded": True,
        "signed_at": row.signed_at.isoformat() if row.signed_at else None,
        "payment_terms": row.payment_terms,
        "acceptance_window_days": row.acceptance_window_days,
        "termination_terms": row.termination_terms,
        "source_uri": row.source_uri,
        "content_hash": row.content_hash,
        "note": row.note,
    }


def _text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ContractServiceError("invalid_request", "文本字段格式不正确。", 400)
    return value.strip()


def _parse_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ContractServiceError("invalid_request", "日期必须是 YYYY-MM-DD。", 400)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ContractServiceError("invalid_request", "日期必须是 YYYY-MM-DD。", 400) from None


def _load_project(session, actor: User, project_id: str, *, manage: bool = False) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise ContractServiceError("project_not_found", "项目不存在或已被删除。", 404)
    access = project_access(actor, project)
    if not (access.can_manage if manage else access.can_view):
        raise ContractServiceError("forbidden", "你没有该项目合同台账的操作权限。", 403)
    return project
