"""B3-1（FDU 对照分析 D-1 拍板）：产能/单均工时核验证据链。

真实档案 ``fde_profiles.monthly_capacity_hours`` / ``avg_delivery_hours``
是撮合 A4 产能上限的算法输入，但此前零合法写路径（唯一写入方＝派单仿真
器）。本套件钉住唯一写入口 ``POST /admin/dispatch/profiles/<id>/
capacity-evidence``：admin+密码双闸、正整数闭集、指针+sha256 指纹（不存
本体）、审计事件、A4 上限联动。
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from conftest import INITIAL_PASSWORD
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.commercial.models import CommercialEntitlement
from fde_api.dispatch.models import FdeProfile
from fde_api.orgs.models import Org
from fde_api.workbench.models import OperationEvent


ADMIN_PROFILES_URL = "/api/v1/admin/dispatch/profiles"
PROFILES_URL = "/api/v1/dispatch/profiles"
CAPACITY_URL_TEMPLATE = ADMIN_PROFILES_URL + "/{user_id}/capacity-evidence"
SHA = "a" * 64
SHA_UPPER = "A" * 64


def _make_user(session, role, *, org_id=None):
    user = User(
        username=f"capacity-evidence-{uuid4().hex}",
        role=role,
        org_id=org_id,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
    )
    session.add(user)
    return user


def _headers(user, settings):
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _events(session, target_id):
    return list(
        session.scalars(select(OperationEvent).where(OperationEvent.target_id == target_id))
    )


def _payload(**overrides):
    payload = {
        "monthly_capacity_hours": 160,
        "avg_delivery_hours": 80,
        "source_uri": "fdeops://goal-fdu/capacity/case-001",
        "source_sha256": SHA,
        "confirm_password": INITIAL_PASSWORD,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def capacity_case(db_session):
    admin = _make_user(db_session, "admin")
    engineer = _make_user(db_session, "fde_engineer")
    lead = _make_user(db_session, "project_lead")
    db_session.flush()
    db_session.add_all(
        [
            FdeProfile(user_id=engineer.id, status="active"),
            CommercialEntitlement(user_id=engineer.id, delivery_eligibility="eligible"),
        ]
    )
    db_session.commit()
    return admin, engineer, lead


def test_capacity_evidence_happy_path_and_audit_event(client, db_session, settings, capacity_case):
    """核验写入 → 字段+证据链落库 → 审计事件（before/after）→ A4 上限联动。"""
    admin, engineer, _lead = capacity_case
    url = CAPACITY_URL_TEMPLATE.format(user_id=engineer.id)
    headers = _headers(admin, settings)

    first = client.post(url, headers=headers, json=_payload())
    assert first.status_code == 200, first.json
    body = first.json["data"]
    assert body["user_id"] == engineer.id
    assert body["monthly_capacity_hours"] == 160
    assert body["avg_delivery_hours"] == 80
    assert body["changed"] is True
    assert datetime.fromisoformat(body["capacity_verified_at"]) <= datetime.now(timezone.utc)

    # 同值重核：changed=False，但 verified_at 前移、事件照记（重核即审计事实）
    second = client.post(url, headers=headers, json=_payload())
    assert second.status_code == 200
    assert second.json["data"]["changed"] is False
    assert second.json["data"]["capacity_verified_at"] >= body["capacity_verified_at"]

    db_session.expire_all()
    profile = db_session.get(FdeProfile, engineer.id)
    assert (profile.monthly_capacity_hours, profile.avg_delivery_hours) == (160, 80)
    assert profile.capacity_evidence_uri == "fdeops://goal-fdu/capacity/case-001"
    assert profile.capacity_evidence_sha256 == SHA
    assert profile.capacity_verified_by_user_id == admin.id
    assert profile.capacity_verified_at is not None

    events = [e for e in _events(db_session, engineer.id)
              if e.event_type == "fde_capacity_evidence_recorded"]
    assert len(events) == 2
    event = events[0]
    assert event.target_type == "user"
    assert event.actor_user_id == admin.id
    assert event.changes["before"] == {
        "monthly_capacity_hours": None,
        "avg_delivery_hours": None,
    }
    assert event.changes["after"] == {
        "monthly_capacity_hours": 160,
        "avg_delivery_hours": 80,
        "source_uri": "fdeops://goal-fdu/capacity/case-001",
        "source_sha256": SHA,
    }

    # A4 产能上限联动：admin 档案列表行暴露核验态且 cap = 160 // 80 = 2
    listed = client.get(PROFILES_URL, headers=headers)
    assert listed.status_code == 200
    row = next(r for r in listed.json["data"] if r["user_id"] == engineer.id)
    assert row["capacity_verified_at"] is not None
    assert row["capacity_evidence_uri"] == "fdeops://goal-fdu/capacity/case-001"
    assert row["capacity_evidence_sha256"] == SHA
    assert row["capacity_cap"] == 2


def test_capacity_evidence_normalizes_uppercase_sha256(client, db_session, settings, capacity_case):
    """大写指纹按 promote_user 同款校验语义放行并归一为小写存储。"""
    admin, engineer, _lead = capacity_case
    url = CAPACITY_URL_TEMPLATE.format(user_id=engineer.id)
    response = client.post(url, headers=_headers(admin, settings), json=_payload(source_sha256=SHA_UPPER))
    assert response.status_code == 200, response.json
    db_session.expire_all()
    assert db_session.get(FdeProfile, engineer.id).capacity_evidence_sha256 == SHA


def test_capacity_evidence_route_gates(client, db_session, settings, capacity_case):
    """admin+平台身份+密码三重闸；project_lead 与平台外 admin 一律 403。"""
    admin, engineer, lead = capacity_case
    url = CAPACITY_URL_TEMPLATE.format(user_id=engineer.id)

    denied = client.post(url, headers=_headers(lead, settings), json=_payload())
    assert (denied.status_code, denied.json["error"]["code"]) == (403, "forbidden")
    assert _events(db_session, engineer.id) == []

    # 平台身份闸：挂到 org 下的 admin 不是平台管理员（M3b 批次①-a）
    org = Org(name=f"capacity-evidence-{uuid4().hex}", org_type="enterprise")
    db_session.add(org)
    db_session.flush()
    org_admin = _make_user(db_session, "admin", org_id=org.id)
    db_session.commit()
    org_denied = client.post(url, headers=_headers(org_admin, settings), json=_payload())
    assert (org_denied.status_code, org_denied.json["error"]["code"]) == (403, "forbidden")

    wrong_password = client.post(
        url, headers=_headers(admin, settings), json=_payload(confirm_password="wrong-password")
    )
    assert (wrong_password.status_code, wrong_password.json["error"]["code"]) == (403, "invalid_password")
    assert _events(db_session, engineer.id) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"monthly_capacity_hours": 0},
        {"monthly_capacity_hours": -5},
        {"monthly_capacity_hours": "160"},
        {"monthly_capacity_hours": True},
        {"avg_delivery_hours": 0},
        {"avg_delivery_hours": None},
        {"source_uri": ""},
        {"source_uri": "x" * 501},
        {"source_sha256": "a" * 63},
        {"source_sha256": "z" * 64},
        {"source_sha256": None},
        {"extra_key": 1},
    ],
)
def test_capacity_evidence_rejects_invalid_payloads(client, db_session, settings, capacity_case, overrides):
    """载荷闭集与值域校验：非法一律 400 且零落库零事件。"""
    admin, engineer, _lead = capacity_case
    url = CAPACITY_URL_TEMPLATE.format(user_id=engineer.id)
    payload = _payload()
    payload.update(overrides)
    response = client.post(url, headers=_headers(admin, settings), json=payload)
    assert (response.status_code, response.json["error"]["code"]) == (400, "invalid_request")
    db_session.expire_all()
    profile = db_session.get(FdeProfile, engineer.id)
    assert profile.monthly_capacity_hours is None
    assert profile.capacity_evidence_sha256 is None
    assert _events(db_session, engineer.id) == []


def test_capacity_evidence_missing_payload_key(client, db_session, settings, capacity_case):
    admin, engineer, _lead = capacity_case
    url = CAPACITY_URL_TEMPLATE.format(user_id=engineer.id)
    incomplete = _payload()
    incomplete.pop("source_uri")
    response = client.post(url, headers=_headers(admin, settings), json=incomplete)
    assert (response.status_code, response.json["error"]["code"]) == (400, "invalid_request")


def test_capacity_evidence_requires_profile(client, db_session, settings):
    """交付者在、档案不在 → 404 profile_not_found（不在派单域补建）。"""
    admin = _make_user(db_session, "admin")
    engineer = _make_user(db_session, "fde_engineer")
    db_session.flush()
    db_session.add(CommercialEntitlement(user_id=engineer.id, delivery_eligibility="eligible"))
    db_session.commit()
    url = CAPACITY_URL_TEMPLATE.format(user_id=engineer.id)
    response = client.post(url, headers=_headers(admin, settings), json=_payload())
    assert (response.status_code, response.json["error"]["code"]) == (404, "profile_not_found")


def test_capacity_evidence_requires_dispatch_deliverer(client, db_session, settings):
    """非交付者身份（即使误建档案）→ 409 delivery_identity_required。"""
    admin = _make_user(db_session, "admin")
    viewer = _make_user(db_session, "viewer")
    db_session.flush()
    db_session.add(FdeProfile(user_id=viewer.id, status="active"))
    db_session.commit()
    url = CAPACITY_URL_TEMPLATE.format(user_id=viewer.id)
    response = client.post(url, headers=_headers(admin, settings), json=_payload())
    assert (response.status_code, response.json["error"]["code"]) == (409, "delivery_identity_required")
    assert _events(db_session, viewer.id) == []


def test_capacity_evidence_future_seat_not_required(client, db_session, settings, capacity_case):
    """产能核验不依赖席位状态（与 register/enable 的权益耦合解耦）：
    seat none 也可核验——核验的是能力事实，不是接单资格。"""
    admin, engineer, _lead = capacity_case
    url = CAPACITY_URL_TEMPLATE.format(user_id=engineer.id)
    response = client.post(url, headers=_headers(admin, settings), json=_payload())
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.get(CommercialEntitlement, engineer.id).seat_status == "none"
