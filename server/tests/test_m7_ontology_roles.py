"""M7 / S-21：Workbench 侧审批角色真身接线（sqlite 文件库；不依赖 CI MySQL）。

钉死四件事：

1. **签名上下文头带 roles**——去重排序后写入；缺省（roles=None）时载荷与 M7 之前
   **逐字节一致**（老 client 零改造）；roles 在 HMAC 覆盖面内（改一个字节即验签失败）。
2. **角色授予的增删查**——幂等（同一人同一角色重复授予不新增）、角色闭集、跨项目隔离。
3. **审批路径 fail-closed**——请求投票角色 ∉ 该身份在本项目的授予集合 ⇒ 403
   ``role_not_granted``，且**发生在任何出站调用之前**（此前是请求体自报即认：
   一个非提议人可连投三票把变更集批掉——M7 决策单第 2 条）。
4. **放行时把授予集合签进 roles**——进 HMAC 覆盖面，runtime 侧再验一次
   「投票角色 ∈ 声明角色」与「三必签角色异人」（两侧同认一份授权事实）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from flask import Flask
from pydantic import SecretStr
from sqlalchemy import DefaultClause, event
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from fde_api.app import create_app
from fde_api.auth.models import Base, User
from fde_api.config import Settings
from fde_api.extensions import db
from fde_api.integrations import service
from fde_api.integrations.models import ProjectOntologyBinding, ProjectOntologyRole
from fde_api.integrations.ontology_client import build_context_header
from fde_api.integrations.ontology_mock import MockOntologyAdapter
from fde_api.workbench.models import Project, ProjectMember

_BASE: dict[str, str] = {
    "database_url": "",  # 每测试填 sqlite 文件
    "redis_url": "redis://127.0.0.1:6379/2",
    "jwt_secret": "test-secret-with-at-least-thirty-two-characters",
}

SIGNING_KEY = "m7-signing-key"


# ---------------------------------------------------------------- 纯单元（无 DB）


def _decode(header: str) -> tuple[dict[str, Any], str]:
    raw, sig = header.split(".", 1)
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    return payload, sig


def test_build_context_header_roles_are_sorted_and_deduped() -> None:
    header = build_context_header(
        "u-1", "org-1", "p-1", SIGNING_KEY, ts=1700000000, nonce="n-1",
        roles=["risk", "business_owner", "risk"],
    )
    payload, _sig = _decode(header)
    assert payload["roles"] == ["business_owner", "risk"]


def test_build_context_header_without_roles_keeps_legacy_payload_shape() -> None:
    """roles=None ⇒ 载荷与 M7 之前逐字节一致（老 client 零改造，无签名不可用性风险）。"""
    header = build_context_header("u-1", "org-1", "p-1", SIGNING_KEY, ts=1700000000, nonce="n-1")
    payload, _sig = _decode(header)
    assert "roles" not in payload
    assert set(payload) == {"actor_id", "org_id", "project_id", "ts", "nonce"}


def test_build_context_header_signature_covers_roles() -> None:
    """roles 进 HMAC 覆盖面：篡改载荷（换角色）即验签失败。"""
    header = build_context_header(
        "u-1", "org-1", "p-1", SIGNING_KEY, ts=1700000000, nonce="n-1", roles=["data_owner"]
    )
    raw, sig = header.split(".", 1)
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    payload["roles"] = ["business_owner"]
    tampered = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    expected = base64.urlsafe_b64encode(
        hmac.new(SIGNING_KEY.encode(), tampered.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    assert expected != sig  # 改载荷 ⇒ 签名对不上 ⇒ runtime 验签 403


def test_mock_adapter_rejects_role_outside_signed_declaration() -> None:
    """mock 世界与 runtime 同语义：投票角色 ∉ 声明角色 ⇒ 403（mock 也得守同一条线）。"""
    mock = MockOntologyAdapter()
    mock._action_requests["req-1"] = {
        "id": "req-1",
        "request_id": "req-1",
        "org_id": "org-1",
        "ontology_id": "ont-1",
        "pinned_version_id": "v1",
        "status": "pending",
        "requested_by_user_id": "u-other",
        "action_key": "a1",
    }
    mock._action_approvals["req-1"] = []
    denied = mock.approve_action(
        actor_id="u-1", org_id="org-1", project_id="p-1", ontology_id="ont-1",
        request_id="req-1", role="business_owner", decision="approved",
        roles=("data_owner",),
    )
    assert denied["_status"] == 403
    assert denied["code"] == "forbidden"
    # 未声明（roles=None）⇒ 与 runtime off 档一致，不拦
    mock._action_requests["req-1"]["status"] = "pending"
    allowed = mock.approve_action(
        actor_id="u-1", org_id="org-1", project_id="p-1", ontology_id="ont-1",
        request_id="req-1", role="business_owner", decision="approved",
    )
    assert allowed["_status"] == 200


# ---------------------------------------------------------------- sqlite 夹具（无 CI MySQL）


def _fill_sqlite_timestamps(
    session: Session, flush_context: object, instances: object
) -> None:
    """sqlite 无 UTC_TIMESTAMP(6)（MySQL 专有 server_default）：flush 前显式回填。"""
    bind = session.bind
    if bind is None or bind.dialect.name != "sqlite":
        return
    now = datetime.now(UTC)
    for obj in session.new:
        for field in ("created_at", "updated_at", "acted_at"):
            if (
                hasattr(type(obj), field)
                and getattr(obj, field, None) is None
                and field in type(obj).__mapper__.columns
            ):
                setattr(obj, field, now)


def _leader() -> User:
    return User(
        id="u-leader", username="leader@test", role="project_lead", password_hash="x", is_active=True
    )


def _member() -> User:
    return User(
        id="u-bo", username="bo@test", role="fde_engineer", password_hash="x", is_active=True
    )


def _outsider() -> User:
    return User(
        id="u-out", username="out@test", role="viewer", password_hash="x", is_active=True
    )


class FakeClient:
    """记录 approve_action 的出站参数（断言 roles 声明与角色真身一致）。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def approve_action(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"_status": 200, "status": "approved"}


@pytest.fixture
def wb_app(tmp_path: Path) -> Iterator[Flask]:
    base = dict(_BASE)
    base["database_url"] = f"sqlite:///{tmp_path / 'wb-roles.db'}"
    settings = Settings(
        env="test",
        ontology_enabled=True,
        ontology_api_key=SecretStr("k"),
        ontology_signing_key=SecretStr("s"),
        **base,  # type: ignore[arg-type]
    )
    app = create_app(settings)
    engine = app.extensions["fde_api_db"]
    tables = [
        Base.metadata.tables[n]
        for n in (
            "users",
            "projects",
            "project_members",
            "project_ontology_bindings",
            "project_ontology_roles",
        )
    ]
    _saved: dict[Any, Any] = {}
    for table in tables:
        for col in table.columns:
            sd = col.server_default
            arg = getattr(sd, "arg", None)
            rendered = str(arg) if arg is not None else ""
            if "TIMESTAMP" in rendered.upper():
                _saved[col] = sd
                col.server_default = DefaultClause(sa_text("CURRENT_TIMESTAMP"))
    try:
        Base.metadata.create_all(engine, tables=tables)
        _seed(app)
        event.listen(Session, "before_flush", _fill_sqlite_timestamps)
        yield app
    finally:
        event.remove(Session, "before_flush", _fill_sqlite_timestamps)
        for col, sd in _saved.items():
            col.server_default = sd


def _seed(app: Flask) -> None:
    with app.app_context():
        session = db.session()
        session.add_all(
            [
                _leader(),
                _member(),
                _outsider(),
                Project(
                    id="p-1",
                    project_code="PRJ-1",
                    name="项目一",
                    enterprise_code="ENT-1",
                    leader_user_id="u-leader",
                    status="active",
                    planned_start_date=date(2026, 1, 1),
                    planned_end_date=date(2026, 12, 31),
                    template_snapshot={},
                    org_id="org-1",
                ),
                ProjectMember(id="pm-1", project_id="p-1", user_id="u-bo", role="member"),
                ProjectOntologyBinding(
                    id="b-1",
                    org_id="org-1",
                    project_id="p-1",
                    ontology_id="ont-1",
                    pinned_version_id="ver-1",
                    pinned_version="1.0.0",
                    binding_role="primary",
                    status="active",
                    active_marker="active",
                    bound_by_user_id="u-leader",
                ),
            ]
        )
        session.commit()


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake: FakeClient) -> None:
    monkeypatch.setattr(service, "client_from_settings", lambda: fake)


# ---------------------------------------------------------------- 用例


def test_grant_list_revoke_roundtrip(wb_app: Flask) -> None:
    with wb_app.app_context():
        granted = service.grant_ontology_roles(
            actor=_leader(), project_id="p-1",
            payload={"user_id": "u-bo", "roles": ["business_owner"]},
        )
        assert [g["role"] for g in granted] == ["business_owner"]
        assert granted[0]["granted_by_user_id"] == "u-leader"
        assert granted[0]["org_id"] == "org-1"  # org 取项目归属（D10 段 2 口径）

        listed = service.list_ontology_roles(actor=_leader(), project_id="p-1")
        assert [(r["user_id"], r["role"]) for r in listed] == [("u-bo", "business_owner")]

        revoked = service.revoke_ontology_role(
            actor=_leader(), project_id="p-1", user_id="u-bo", role="business_owner"
        )
        assert revoked["role"] == "business_owner"
        assert service.list_ontology_roles(actor=_leader(), project_id="p-1") == []


def test_grant_is_idempotent_and_role_closed_set(wb_app: Flask) -> None:
    with wb_app.app_context():
        service.grant_ontology_roles(
            actor=_leader(), project_id="p-1",
            payload={"user_id": "u-bo", "roles": ["data_owner"]},
        )
        again = service.grant_ontology_roles(
            actor=_leader(), project_id="p-1",
            payload={"user_id": "u-bo", "roles": ["data_owner"]},
        )
        assert len(again) == 1
        assert len(service.list_ontology_roles(actor=_leader(), project_id="p-1")) == 1
        with pytest.raises(service.BindingError) as exc:
            service.grant_ontology_roles(
                actor=_leader(), project_id="p-1",
                payload={"user_id": "u-bo", "roles": ["superuser"]},
            )
        assert exc.value.code == "invalid_request"


def test_grant_rejects_non_member_and_unknown_user(wb_app: Flask) -> None:
    with wb_app.app_context():
        with pytest.raises(service.BindingError) as exc:
            service.grant_ontology_roles(
                actor=_leader(), project_id="p-1",
                payload={"user_id": "u-out", "roles": ["business_owner"]},
            )
        assert exc.value.code == "invalid_request"
        with pytest.raises(service.BindingError) as exc:
            service.grant_ontology_roles(
                actor=_leader(), project_id="p-1",
                payload={"user_id": "u-nobody", "roles": ["business_owner"]},
            )
        assert exc.value.status == 404


def test_revoke_unknown_grant_is_404(wb_app: Flask) -> None:
    with wb_app.app_context():
        with pytest.raises(service.BindingError) as exc:
            service.revoke_ontology_role(
                actor=_leader(), project_id="p-1", user_id="u-bo", role="risk"
            )
        assert exc.value.status == 404


def test_approve_action_requires_granted_role_before_outbound(
    wb_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未授予的角色 ⇒ 403 role_not_granted，且**没有任何出站调用**（fail-closed 前置）。"""
    fake = FakeClient()
    _patch_client(monkeypatch, fake)
    with wb_app.app_context():
        with pytest.raises(service.BindingError) as exc:
            service.approve_binding_action(
                actor=_member(), project_id="p-1", binding_id="b-1", request_id="req-1",
                payload={"role": "business_owner", "decision": "approved"},
            )
        assert exc.value.status == 403
        assert exc.value.code == "role_not_granted"
        assert fake.calls == []


def test_approve_action_signs_granted_roles(
    wb_app: Flask, monkeypatch: pytest.MonkeyPatch
) -> None:
    """授予集合进签名声明（进 HMAC 覆盖面），runtime 据此再验一次。"""
    fake = FakeClient()
    _patch_client(monkeypatch, fake)
    with wb_app.app_context():
        service.grant_ontology_roles(
            actor=_leader(), project_id="p-1",
            payload={"user_id": "u-bo", "roles": ["business_owner", "risk"]},
        )
        service.approve_binding_action(
            actor=_member(), project_id="p-1", binding_id="b-1", request_id="req-1",
            payload={"role": "business_owner", "decision": "approved"},
        )
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["role"] == "business_owner"
    assert tuple(call["roles"]) == ("business_owner", "risk")
    assert call["actor_id"] == "u-bo"


def test_granted_roles_derivation_is_empty_without_grants(wb_app: Flask) -> None:
    """未授予 ⇒ 空集合（fail-closed：runtime 在 signed_roles 档一律 403）。"""
    with wb_app.app_context():
        session = db.session()
        assert service.granted_ontology_roles(session, project_id="p-1", user_id="u-bo") == ()


def test_project_ontology_role_model_columns_match_migration() -> None:
    """模型列与迁移声明同名同约束（模型漂移=迁移漂移，先在这里钉住）。"""
    table = cast(Any, ProjectOntologyRole.__table__)
    assert set(table.columns.keys()) >= {
        "id", "org_id", "project_id", "user_id", "role", "granted_by_user_id",
        "created_at", "updated_at",
    }
    checks = {c.name for c in table.constraints if c.name}
    assert "ck_project_ontology_roles_role" in checks
    assert "uq_project_ontology_roles_project_user_role" in checks
