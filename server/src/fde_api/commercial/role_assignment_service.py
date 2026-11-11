"""兼任承载服务（F 线 T4：ADR-011 §3.8；任务书 §4 T4）。

- ``commercial_role_assignments`` 一人多角色：一人可有多行（多角色并存），
  每行附**生效区间**（``valid_from``／``valid_until``，后者空＝长期有效）
  与**来源**（书面依据指针＋sha256 指纹——证据红线同款，不内嵌正文）。
- ``commercial_entitlements.commercial_role`` 单值列保留为「主角色」兼容
  读面（**不删列**）；本服务**零写** entitlements、**零写** ``users.role``
  （ADR-001 保护清单——兼任承载不得污染权限角色尺）。
- 分配/写入＝**关键流转**（ADR-007）：admin＋密码双闸＋限流（与 G4 归属
  确认同款）；逐动作 ``operation_events`` 留痕，密码不落事件。
- 同 (user, role) 生效区间**重叠** 409 ``role_assignment_overlap``（行锁
  ＋重叠判定——并发安全沿用 G2 额度行锁范式）；窗口倒挂 400。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fde_api.auth.confirm_throttle import confirm_attempts_blocked, record_confirm_failure
from fde_api.auth.models import ROLE_ADMIN, User
from fde_api.auth.passwords import verify_password
from fde_api.commercial.models import COMMERCIAL_ROLES, CommercialEntitlement, CommercialRoleAssignment
from fde_api.commercial.service import CommercialServiceError
from fde_api.projects.events import record_event

_SHA256_RE_LENGTH = 64


def _error(code: str, message: str, status: int = 400) -> CommercialServiceError:
    return CommercialServiceError(code, message, status)


def _require_admin(actor: User) -> None:
    if actor.role != ROLE_ADMIN:
        raise _error("commercial_admin_required", "兼任承载治理仅系统运维员可用。", 403)


def _confirm_password(session: Session, actor: User, password: object) -> None:
    """单次显式授权：admin 写原语须携带当前账号密码（高风险写人工确认）。"""
    if not isinstance(password, str) or not password:
        raise _error("invalid_request", "confirm_password 必填（高风险写人工确认）。")
    # CR-047：密码确认尝试限流——与 auth verify-password / ai 确认闸同 key 同阈值同窗口。
    if confirm_attempts_blocked(actor.id):
        raise _error("too_many_attempts", "密码错误次数过多，请 15 分钟后重试。", 429)
    current = session.get(User, actor.id)
    if current is None or not verify_password(current.password_hash, password):
        record_confirm_failure(actor.id)
        raise _error("invalid_password", "当前账号密码不正确。", 403)


def _require_sha256(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value.strip()) != _SHA256_RE_LENGTH
        or not all(ch in "0123456789abcdef" for ch in value.strip().lower())
    ):
        raise _error("invalid_request", f"{field} 必须是 64 位 sha256 十六进制指纹。")
    return value.strip().lower()


def _require_uri(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 500:
        raise _error("invalid_request", f"{field} 必须是 ≤500 字符指针字符串。")
    return value.strip()


def _parse_dt(value: object, field: str) -> datetime:
    """生效时刻解析：接受 datetime 或 ISO 8601 字符串（路由层 JSON 形态）。"""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip())
        except ValueError:
            raise _error(
                "invalid_request", f"{field} 必须是 ISO 8601 datetime。"
            ) from None
    else:
        raise _error("invalid_request", f"{field} 必须是 ISO 8601 datetime。")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _require_user(session: Session, user_id: object) -> User:
    if not isinstance(user_id, str) or not user_id:
        raise _error("invalid_request", "user_id 必填。")
    user = session.get(User, user_id)
    if user is None:
        raise _error("user_not_found", "用户不存在。", 404)
    return user


def _serialize(row: CommercialRoleAssignment, main_role: str | None) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "commercial_role": row.commercial_role,
        "valid_from": row.valid_from.isoformat(),
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "source_uri": row.source_uri,
        "content_hash": row.content_hash,
        "assigned_by_user_id": row.assigned_by_user_id,
        "main_commercial_role": main_role,
    }


# ══════════════════════════════════════════════════════════════════════════
# 写原语（关键流转：admin＋密码双闸）
# ══════════════════════════════════════════════════════════════════════════


def assign_commercial_role(
    session: Session,
    *,
    actor: User,
    user_id: object,
    commercial_role: object,
    valid_from: object,
    valid_until: object = None,
    source_uri: object,
    content_hash: object,
    confirm_password: object,
) -> dict[str, Any]:
    """分配商业角色（兼任承载写原语；admin＋密码双闸）。

    - ``commercial_role`` ∈ R1–R4 闭集（``COMMERCIAL_ROLES``）；
    - 生效区间：``valid_from`` 必填，``valid_until`` 可空＝长期有效；
      倒挂（``valid_until <= valid_from``）400（DB CHECK 同形兜底）；
    - 同 ``(user_id, commercial_role)`` 现行区间**重叠** ⇒ 409
      ``role_assignment_overlap``（先锁存量行再判重叠——并发安全）；
    - **零写** ``users.role``／``commercial_entitlements``——主角色兼容
      读面由读面层拼装，兼任不覆盖主角色。
    """
    _require_admin(actor)
    _confirm_password(session, actor, confirm_password)
    target = _require_user(session, user_id)
    if commercial_role not in COMMERCIAL_ROLES:
        raise _error(
            "invalid_commercial_role",
            f"commercial_role 必须在 {COMMERCIAL_ROLES} 闭集内。",
        )
    start = _parse_dt(valid_from, "valid_from")
    end = None if valid_until is None else _parse_dt(valid_until, "valid_until")
    if end is not None and end <= start:
        raise _error(
            "invalid_request", "生效区间倒挂：valid_until 必须晚于 valid_from。"
        )
    uri = _require_uri(source_uri, "source_uri")
    digest = _require_sha256(content_hash, "content_hash")

    # 行锁存量区间再判重叠（G2 额度并发范式：锁在手读必为已提交真值）
    existing = list(
        session.scalars(
            select(CommercialRoleAssignment)
            .where(
                CommercialRoleAssignment.user_id == target.id,
                CommercialRoleAssignment.commercial_role == commercial_role,
            )
            .with_for_update()
        ).all()
    )
    for row in existing:
        row_end = row.valid_until
        overlaps = (row_end is None or row_end > start) and (
            end is None or end > row.valid_from
        )
        if overlaps:
            raise _error(
                "role_assignment_overlap",
                f"同角色 {commercial_role} 生效区间重叠："
                f"既有 {row.valid_from.isoformat()}～"
                f"{row_end.isoformat() if row_end else '长期'}。",
                409,
            )

    assignment = CommercialRoleAssignment(
        user_id=target.id,
        commercial_role=commercial_role,
        valid_from=start,
        valid_until=end,
        source_uri=uri,
        content_hash=digest,
        assigned_by_user_id=actor.id,
    )
    session.add(assignment)
    session.flush()
    # 事件零密码（ADR-007 纪律）
    record_event(
        session,
        actor,
        "commercial_role_assigned",
        target,
        {
            "assignment_id": assignment.id,
            "commercial_role": commercial_role,
            "valid_from": start.isoformat(),
            "valid_until": end.isoformat() if end else None,
            "source_uri": uri,
            "content_hash": digest,
        },
    )
    main_role = _main_role(session, target.id)
    return _serialize(assignment, main_role)


# ══════════════════════════════════════════════════════════════════════════
# 读面（兼任明细 ＋ 主角色兼容读面）
# ══════════════════════════════════════════════════════════════════════════


def _main_role(session: Session, user_id: str) -> str | None:
    """主角色兼容读面：``commercial_entitlements.commercial_role`` 原样透出。

    兼任行**永不回写**主角色列——单值列是 G1 既有事实，兼任是 T4 增量事实。
    """
    entitlement = session.get(CommercialEntitlement, user_id)
    return entitlement.commercial_role if entitlement else None


def list_role_assignments(
    session: Session, *, actor: User, user_id: object
) -> dict[str, Any]:
    """读兼任明细（admin 全量可读；本人只读自己；其余 403）。

    返回兼实行集＋``main_commercial_role``（entitlements 单值列兼容读面，
    不删列语义的承载面）。
    """
    if not isinstance(user_id, str) or not user_id:
        raise _error("invalid_request", "user_id 必填。")
    if actor.role != ROLE_ADMIN and actor.id != user_id:
        raise _error("forbidden", "兼任明细仅本人或系统运维员可读。", 403)
    target = _require_user(session, user_id)
    rows = list(
        session.scalars(
            select(CommercialRoleAssignment)
            .where(CommercialRoleAssignment.user_id == target.id)
            .order_by(CommercialRoleAssignment.valid_from)
        ).all()
    )
    main_role = _main_role(session, target.id)
    return {
        "user_id": target.id,
        "main_commercial_role": main_role,
        "assignments": [_serialize(row, main_role) for row in rows],
    }
