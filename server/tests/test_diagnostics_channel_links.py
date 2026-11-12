"""获客诊断 T-15：渠道链接注册表（R4 专属链接 ＝ 归因凭证）。

这一组用例守的是**归因机械可判**：

- ``source_type='partner'``（A 档〔收费档〕的种子）**不接受客户端声明**——
  只能由有效渠道链接服务端推导（P-2 零手工记账的防伪面）；
- 明文 token **只此一次**（创建响应）；库里只有 sha256（沿匿名令牌同尺）；
- 过期/停用/伪造 token ⇒ **fail-closed 降档 direct**（stale 链接不拦真实
  线索，但没有有效证据就不给 A 档）；
- 停用是软撤：历史归因不改写，新会话不再解析；
- 渠道链接面是 admin 专属（平台发链接），闸门先于鉴权（404 不是 403）；
- **零外键指向 projects**（线索 ≠ 项目，域内自持）。

这些用例不联网、不调模型——渠道链接是纯规则层。
"""
from __future__ import annotations

import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.diagnostics.models import (
    LeadDiagnosticChannelLink,
    LeadDiagnosticSession,
)

from conftest import INITIAL_PASSWORD
from test_diagnostics_mvp import _FakeRedis  # noqa: F401  （假 Redis：配额闸可测）

LINKS_PREFIX = "/api/v1/diagnostics/leads/channel-links"
SESSIONS_PREFIX = "/api/v1/diagnostics/sessions"
STAFF_IP = "198.51.100.42"


@pytest.fixture
def diag_app(app):
    """打开诊断面（部署闸开）+ 假 Redis。"""
    app.config["SETTINGS"] = app.config["SETTINGS"].model_copy(
        update={"diagnostics_enabled": True, "diagnostics_rate_fail_closed": True}
    )
    app.extensions["fde_api_redis"] = _FakeRedis()
    return app


@pytest.fixture
def diag_client(diag_app):
    return diag_app.test_client()


def _make_user(db_session, settings, *, role: str):
    user = User(
        username=f"diag.cl.{role}.{uuid4().hex[:8]}",
        display_name=role,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        email=None,
        registration_state="active",
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    headers = {"Authorization": f"Bearer {issue_access_token(user, settings)}"}
    return user, headers


def _create_link(client, headers, payload=None):
    return client.post(
        LINKS_PREFIX,
        json=payload if payload is not None else {"region_name": "浙江省", "note": "r4-01"},
        headers=headers,
        environ_base={"REMOTE_ADDR": STAFF_IP},
    )


# ── 权限与闸门 ─────────────────────────────────────────────────────────


def test_channel_link_admin_only(diag_client, db_session, settings):
    """渠道链接面 admin 专属：非 admin 403、匿名 401。"""
    _, admin_headers = _make_user(db_session, settings, role="admin")
    _, member_headers = _make_user(db_session, settings, role="fde_engineer")
    assert diag_client.get(LINKS_PREFIX).status_code == 401
    assert diag_client.get(LINKS_PREFIX, headers=member_headers).status_code == 403
    assert diag_client.post(LINKS_PREFIX, json={}, headers=member_headers).status_code == 403
    ok = diag_client.get(LINKS_PREFIX, headers=admin_headers)
    assert ok.status_code == 200


def test_disabled_gate_hides_channel_links_before_auth(client):
    """**闸门先于鉴权**：诊断面未启用 ⇒ 404（不确认面存在），不是 401/403。"""
    response = client.get(LINKS_PREFIX)
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


# ── 创建：明文只此一次 ─────────────────────────────────────────────────


def test_create_link_returns_token_once_and_stores_only_hash(
    diag_client, db_session, settings
):
    """创建响应带明文 token；库/清单里只有 sha256——明文不再出现。"""
    _, admin_headers = _make_user(db_session, settings, role="admin")
    created = _create_link(diag_client, admin_headers)
    assert created.status_code == 201, created.get_json()
    body = created.get_json()["data"]
    token = body["token"]
    assert isinstance(token, str) and len(token) >= 24

    row = db_session.scalars(select(LeadDiagnosticChannelLink)).one()
    assert row.token_sha256 != token
    assert len(row.token_sha256) == 64
    assert row.region_name == "浙江省"
    assert row.note == "r4-01"
    assert row.is_active is True

    listing = diag_client.get(LINKS_PREFIX, headers=admin_headers).get_json()["data"]
    text = json.dumps(listing, ensure_ascii=False)
    assert token not in text
    assert row.token_sha256 not in text
    assert listing[0]["is_active"] is True
    assert listing[0]["lead_count"] == 0


def test_create_link_payload_validation(diag_client, db_session, settings):
    """区域/备注超长 ⇒ 400；region/note 可省略。"""
    _, admin_headers = _make_user(db_session, settings, role="admin")
    long_region = _create_link(diag_client, admin_headers, {"region_name": "浙" * 81})
    assert long_region.status_code == 400
    long_note = _create_link(diag_client, admin_headers, {"note": "x" * 201})
    assert long_note.status_code == 400
    bare = _create_link(diag_client, admin_headers, {})
    assert bare.status_code == 201
    assert bare.get_json()["data"]["region_name"] is None


# ── 归因接线（机械落 partner / fail-closed 降档） ──────────────────────


def test_session_via_valid_link_is_mechanically_partner(
    diag_client, db_session, settings
):
    """有效链接 token ⇒ 服务端机械落 partner；channel_ref 写回链接行 UUID。"""
    _, admin_headers = _make_user(db_session, settings, role="admin")
    token = _create_link(diag_client, admin_headers).get_json()["data"]["token"]
    link_id = diag_client.get(LINKS_PREFIX, headers=admin_headers).get_json()["data"][0]["id"]

    created = diag_client.post(
        SESSIONS_PREFIX,
        json={"channel_ref": token},  # 客户端只递 token，不声明来源
        environ_base={"REMOTE_ADDR": "203.0.113.7"},
    )
    assert created.status_code == 200, created.get_json()
    body = created.get_json()["data"]
    assert body["source_type"] == "partner"

    row = db_session.scalars(select(LeadDiagnosticSession)).one()
    assert row.source_type == "partner"
    assert row.channel_ref == link_id  # 归因写回链接行 UUID（松耦合）
    assert row.attribution_tier is None  # 档位留给认领裁定（只落结构不落数）


def test_session_with_stale_link_fails_closed_to_direct(
    diag_client, db_session, settings
):
    """过期/未知 token ⇒ 会话照常建（不拦真实线索）但落 direct——无证据不给 A 档。"""
    _, admin_headers = _make_user(db_session, settings, role="admin")
    _create_link(diag_client, admin_headers)
    created = diag_client.post(
        SESSIONS_PREFIX,
        json={"channel_ref": "not-a-real-link-token"},
        environ_base={"REMOTE_ADDR": "203.0.113.8"},
    )
    assert created.status_code == 200
    body = created.get_json()["data"]
    assert body["source_type"] == "direct"

    row = db_session.scalars(select(LeadDiagnosticSession)).one()
    assert row.source_type == "direct"
    assert row.channel_ref == "not-a-real-link-token"  # 原样留痕（诚实审计线索）


def test_client_declared_partner_is_rejected(diag_client):
    """``source_type='partner'`` 客户端声明 ⇒ 400（A 档不可伪造）。"""
    response = diag_client.post(
        SESSIONS_PREFIX,
        json={"source_type": "partner", "channel_ref": "x"},
        environ_base={"REMOTE_ADDR": "203.0.113.9"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "partner_source_forbidden"


def test_channel_free_text_semantics_unchanged(diag_client, db_session):
    """``channel``（协会活动等免费名目）保持客户端声明 ＋ 自由文本 ref。"""
    created = diag_client.post(
        SESSIONS_PREFIX,
        json={"source_type": "channel", "channel_ref": "协会活动-2026Q4"},
        environ_base={"REMOTE_ADDR": "203.0.113.10"},
    )
    assert created.status_code == 200
    row = db_session.scalars(select(LeadDiagnosticSession)).one()
    assert row.source_type == "channel"
    assert row.channel_ref == "协会活动-2026Q4"


# ── 停用：软撤（历史归因定格） ─────────────────────────────────────────


def test_deactivated_link_no_longer_resolves_and_history_stays(
    diag_client, db_session, settings
):
    """停用 ⇒ 新会话落 direct；**历史 partner 行不改写**（归因创建时刻定格）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin")
    link = _create_link(diag_client, admin_headers).get_json()["data"]
    first = diag_client.post(
        SESSIONS_PREFIX, json={"channel_ref": link["token"]},
        environ_base={"REMOTE_ADDR": "203.0.113.11"},
    )
    assert first.get_json()["data"]["source_type"] == "partner"

    deactivated = diag_client.post(
        f"{LINKS_PREFIX}/{link['id']}/deactivate", json={}, headers=admin_headers
    )
    assert deactivated.status_code == 200
    assert deactivated.get_json()["data"]["is_active"] is False
    assert deactivated.get_json()["data"]["deactivated_at"]

    after = diag_client.post(
        SESSIONS_PREFIX, json={"channel_ref": link["token"]},
        environ_base={"REMOTE_ADDR": "203.0.113.12"},
    )
    assert after.get_json()["data"]["source_type"] == "direct"  # 新会话不再解析

    rows = list(db_session.scalars(select(LeadDiagnosticSession)))
    assert [r.source_type for r in rows] == ["partner", "direct"]  # 历史定格
    # 重复停用幂等
    again = diag_client.post(
        f"{LINKS_PREFIX}/{link['id']}/deactivate", json={}, headers=admin_headers
    )
    assert again.status_code == 200


def test_deactivate_unknown_link_is_404(diag_client, db_session, settings):
    _, admin_headers = _make_user(db_session, settings, role="admin")
    response = diag_client.post(
        f"{LINKS_PREFIX}/no-such-id/deactivate", json={}, headers=admin_headers
    )
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "channel_link_not_found"


def test_link_lead_count_grows(diag_client, db_session, settings):
    """清单的 lead_count 随归因会话增长（渠道方对账可见）。"""
    _, admin_headers = _make_user(db_session, settings, role="admin")
    link = _create_link(diag_client, admin_headers).get_json()["data"]
    for i in range(2):
        created = diag_client.post(
            SESSIONS_PREFIX, json={"channel_ref": link["token"]},
            environ_base={"REMOTE_ADDR": f"203.0.113.{20 + i}"},
        )
        assert created.status_code == 200
    listing = diag_client.get(LINKS_PREFIX, headers=admin_headers).get_json()["data"]
    assert listing[0]["lead_count"] == 2


# ── 结构纪律 ───────────────────────────────────────────────────────────


def test_channel_link_table_has_no_foreign_key_to_projects():
    """线索 ≠ 项目：渠道链接表**零外键指向 projects**（唯一 FK = users SET NULL）。"""
    refs = [fk.target_fullname for fk in LeadDiagnosticChannelLink.__table__.foreign_keys]
    assert refs, "渠道链接应保留 created_by 审计外键"
    assert all(target == "users.id" for target in refs)


def test_channel_link_model_exposes_no_ratio_field():
    """比例不落数（P-2）：链接模型零比例/金额字段。"""
    forbidden = ("rate", "ratio", "percent", "commission", "amount", "fee")
    names = {column.name for column in LeadDiagnosticChannelLink.__table__.columns}
    assert not any(name in forbidden or f"_{name}" in name for name in names), names
