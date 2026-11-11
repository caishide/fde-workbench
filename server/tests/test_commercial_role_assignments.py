"""F 线 T4：兼任承载回归（ADR-011 §3.8；任务书 §4 T4）。

- ``commercial_role_assignments`` 一人多角色（一人多行并存），每行附生效
  区间与来源（指针＋sha256）；同角色区间重叠 409；窗口倒挂 400。
- **主角色兼容读面**：``commercial_entitlements.commercial_role`` 单值列
  **不删列、不被兼任覆盖**（G1 既有事实）；``users.role`` **零改动**
  （ADR-001 保护清单）。
- 分配＝关键流转：admin＋密码双闸（限流同款）；事件零密码。
- 治理面不进 api_catalog。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.commercial.models import (
    CommercialEntitlement,
    CommercialRoleAssignment,
)
from fde_api.commercial.role_assignment_service import (
    assign_commercial_role,
    list_role_assignments,
)
from fde_api.commercial.service import CommercialServiceError

from conftest import INITIAL_PASSWORD

_NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def _user(username: str, *, role: str = "fde_engineer") -> User:
    return User(
        username=f"{username}.{uuid4().hex[:8]}",
        display_name=username,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )


def _assign(
    db_session,
    admin,
    target_id,
    *,
    role="R3",
    start=_NOW,
    until=None,
    uri="fdeops://f-line-t4/roles/x.md",
    digest=None,
    password=INITIAL_PASSWORD,
):
    if digest is None:
        digest = "a" * 64
    return assign_commercial_role(
        db_session,
        actor=admin,
        user_id=target_id,
        commercial_role=role,
        valid_from=start,
        valid_until=until,
        source_uri=uri,
        content_hash=digest,
        confirm_password=password,
    )


# ---------------------------------------------------------------------------
# 一人多角色（兼任承载）
# ---------------------------------------------------------------------------


def test_one_user_many_roles_coexist(db_session):
    """兼任承载：同人 R2＋R3 两行并存（区间错开），互不覆盖。"""
    admin = _user("t4.admin", role="admin")
    target = _user("t4.multi")
    db_session.add_all([admin, target])
    db_session.flush()
    _assign(db_session, admin, target.id, role="R2", start=_NOW)
    _assign(
        db_session, admin, target.id, role="R3", start=_NOW + timedelta(days=1)
    )
    rows = db_session.scalars(
        select(CommercialRoleAssignment).where(
            CommercialRoleAssignment.user_id == target.id
        )
    ).all()
    assert {row.commercial_role for row in rows} == {"R2", "R3"}


def test_same_role_window_overlap_409(db_session):
    """同角色生效区间重叠 ⇒ 409 role_assignment_overlap。"""
    admin = _user("t4.admin2", role="admin")
    target = _user("t4.overlap")
    db_session.add_all([admin, target])
    db_session.flush()
    _assign(db_session, admin, target.id, role="R3", start=_NOW, until=_NOW + timedelta(days=30))
    with pytest.raises(CommercialServiceError) as excinfo:
        _assign(
            db_session,
            admin,
            target.id,
            role="R3",
            start=_NOW + timedelta(days=10),
        )
    assert excinfo.value.code == "role_assignment_overlap"
    assert excinfo.value.status == 409


def test_same_role_sequential_windows_ok(db_session):
    """同角色先后不重叠（前段有界）⇒ 放行。"""
    admin = _user("t4.admin3", role="admin")
    target = _user("t4.seq")
    db_session.add_all([admin, target])
    db_session.flush()
    _assign(db_session, admin, target.id, role="R4", start=_NOW, until=_NOW + timedelta(days=30))
    data = _assign(
        db_session, admin, target.id, role="R4", start=_NOW + timedelta(days=30)
    )
    assert data["commercial_role"] == "R4"


def test_role_closed_set_and_window_shape(db_session):
    """闭集外角色 400；窗口倒挂 400。"""
    admin = _user("t4.admin4", role="admin")
    target = _user("t4.shape")
    db_session.add_all([admin, target])
    db_session.flush()
    with pytest.raises(CommercialServiceError) as excinfo:
        _assign(db_session, admin, target.id, role="R5")
    assert excinfo.value.code == "invalid_commercial_role"
    with pytest.raises(CommercialServiceError) as excinfo:
        _assign(db_session, admin, target.id, until=_NOW)  # until <= from
    assert excinfo.value.code == "invalid_request"
    # DB CHECK 同形兜底：绕过服务直插倒挂行撞 ck_commercial_role_assignments_window
    db_session.add(
        CommercialRoleAssignment(
            user_id=target.id,
            commercial_role="R1",
            valid_from=_NOW,
            valid_until=_NOW - timedelta(days=1),
            source_uri="fdeops://f-line-t4/bad.md",
            content_hash="b" * 64,
            assigned_by_user_id=admin.id,
        )
    )
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_assignment_requires_admin_and_password(db_session):
    """双闸三负例：非 admin 403；admin 无密码 400；admin 错密码 403。"""
    admin = _user("t4.admin5", role="admin")
    target = _user("t4.gate")
    other = _user("t4.notadmin")
    db_session.add_all([admin, target, other])
    db_session.flush()
    with pytest.raises(CommercialServiceError) as excinfo:
        _assign(db_session, other, target.id)
    assert excinfo.value.code == "commercial_admin_required"
    assert excinfo.value.status == 403
    with pytest.raises(CommercialServiceError) as excinfo:
        _assign(db_session, admin, target.id, password=None)
    assert excinfo.value.code == "invalid_request"
    assert excinfo.value.status == 400
    with pytest.raises(CommercialServiceError) as excinfo:
        _assign(db_session, admin, target.id, password="wrong-password")
    assert excinfo.value.code == "invalid_password"
    assert excinfo.value.status == 403


def test_assignment_requires_source_pointer_and_digest(db_session):
    """书面依据：指针或指纹缺失 ⇒ 400（同有同无——证据红线）。"""
    admin = _user("t4.admin6", role="admin")
    target = _user("t4.evidence")
    db_session.add_all([admin, target])
    db_session.flush()
    with pytest.raises(CommercialServiceError):
        _assign(db_session, admin, target.id, uri="")
    with pytest.raises(CommercialServiceError):
        _assign(db_session, admin, target.id, digest="short")


def test_assignment_event_has_no_password(db_session):
    """事件留痕零密码（ADR-007 纪律）。"""
    from fde_api.workbench.models import OperationEvent

    admin = _user("t4.admin7", role="admin")
    target = _user("t4.event")
    db_session.add_all([admin, target])
    db_session.flush()
    _assign(db_session, admin, target.id)
    db_session.flush()
    event = db_session.scalar(
        select(OperationEvent).where(
            OperationEvent.event_type == "commercial_role_assigned",
            OperationEvent.actor_user_id == admin.id,
        )
    )
    assert event is not None
    assert INITIAL_PASSWORD + "-x" not in str(event.changes)
    assert "confirm_password" not in str(event.changes)


# ---------------------------------------------------------------------------
# 主角色兼容读面 ＋ users.role 零改动
# ---------------------------------------------------------------------------


def test_main_role_compat_read_not_overwritten(db_session):
    """兼任**不覆盖**主角色：entitlements.commercial_role 保持 G1 单值事实，
    读面并列透出（``main_commercial_role``＋assignments）。"""
    admin = _user("t4.admin8", role="admin")
    target = _user("t4.mainrole")
    db_session.add_all([admin, target])
    db_session.flush()
    db_session.add(
        CommercialEntitlement(user_id=target.id, commercial_role="R2")
    )
    db_session.flush()
    _assign(db_session, admin, target.id, role="R3", start=_NOW)
    db_session.flush()
    entitlement = db_session.get(CommercialEntitlement, target.id)
    assert entitlement.commercial_role == "R2"  # 主角色列原样
    view = list_role_assignments(db_session, actor=admin, user_id=target.id)
    assert view["main_commercial_role"] == "R2"
    assert [row["commercial_role"] for row in view["assignments"]] == ["R3"]


def test_users_role_untouched_by_assignment(db_session):
    """``users.role`` 权限角色零改动（ADR-001 保护清单——兼任正交于权限）。"""
    admin = _user("t4.admin9", role="admin")
    target = _user("t4.usersrole")
    db_session.add_all([admin, target])
    db_session.flush()
    before = target.role
    _assign(db_session, admin, target.id, role="R2", start=_NOW)
    db_session.flush()
    db_session.expire(target)
    assert target.role == before == "fde_engineer"


def test_read_permission_self_or_admin(db_session):
    """读面权限三态：本人可读；他人 403；admin 全量可读。"""
    admin = _user("t4.admin10", role="admin")
    target = _user("t4.reader")
    other = _user("t4.other.reader")
    db_session.add_all([admin, target, other])
    db_session.flush()
    _assign(db_session, admin, target.id, role="R3", start=_NOW)
    mine = list_role_assignments(db_session, actor=target, user_id=target.id)
    assert mine["user_id"] == target.id
    admins = list_role_assignments(db_session, actor=admin, user_id=target.id)
    assert len(admins["assignments"]) == 1
    with pytest.raises(CommercialServiceError) as excinfo:
        list_role_assignments(db_session, actor=other, user_id=target.id)
    assert excinfo.value.status == 403


def test_governance_face_not_in_api_catalog() -> None:
    """治理面不进 api_catalog（AI 不可调用；G1–G4 同款边界）。"""
    from fde_api.control.api_catalog import CATALOG

    catalog_names = {row[0] for row in CATALOG}
    for path in (
        "commercial.role-assignment.assign",
        "commercial.role-assignment.list",
    ):
        assert path not in catalog_names


# ---------------------------------------------------------------------------
# 结构与迁移
# ---------------------------------------------------------------------------


def test_migration_roundtrip_and_shape(engine, alembic_config) -> None:
    """迁移 additive 往返：head 上表与 CHECK 齐备；downgrade 至**父版本
    c8d2f6a4e9b1** 后表消失；回 head 恢复（``-1`` 会被后续迁移顶掉）。"""
    from sqlalchemy import inspect as sql_inspect
    from alembic.command import downgrade, upgrade

    inspector = sql_inspect(engine)
    assert "commercial_role_assignments" in set(inspector.get_table_names())
    checks = {
        c["name"]
        for c in inspector.get_check_constraints("commercial_role_assignments")
    }
    assert {
        "ck_commercial_role_assignments_role",
        "ck_commercial_role_assignments_window",
    } <= checks

    downgrade(alembic_config, "c8d2f6a4e9b1")
    inspector = sql_inspect(engine)
    assert "commercial_role_assignments" not in set(inspector.get_table_names())
    upgrade(alembic_config, "head")
    inspector = sql_inspect(engine)
    assert "commercial_role_assignments" in set(inspector.get_table_names())
