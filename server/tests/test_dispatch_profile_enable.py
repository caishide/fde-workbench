"""派单档案启用是独立的管理员授权动作。"""

from datetime import datetime, timedelta, timezone
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


PROFILES_URL = "/api/v1/dispatch/profiles"
ADMIN_PROFILES_URL = "/api/v1/admin/dispatch/profiles"


def _make_user(session, role, *, org_id=None):
    user = User(
        username=f"profile-enable-{uuid4().hex}",
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


@pytest.fixture
def profile_case(db_session):
    admin = _make_user(db_session, "admin")
    engineer = _make_user(db_session, "fde_engineer")
    db_session.flush()
    db_session.add_all(
        [
            FdeProfile(user_id=engineer.id, status="active"),
            CommercialEntitlement(user_id=engineer.id, delivery_eligibility="eligible"),
        ]
    )
    db_session.commit()
    return admin, engineer


def test_admin_enables_profile_once_without_changing_commercial_seat(
    client, db_session, settings, profile_case
):
    admin, engineer = profile_case
    headers = _headers(admin, settings)
    url = f"{ADMIN_PROFILES_URL}/{engineer.id}/enable"

    def list_row():
        response = client.get(PROFILES_URL, headers=headers)
        assert response.status_code == 200
        return next(row for row in response.json["data"] if row["user_id"] == engineer.id)

    assert list_row()["is_active"] is False
    assert list_row()["can_enable"] is True
    for changed in (True, False):
        response = client.post(url, headers=headers, json={"confirm_password": INITIAL_PASSWORD})
        assert response.status_code == 200, response.json
        assert response.json["data"] == {
            "user_id": engineer.id,
            "is_active": True,
            "changed": changed,
        }

    assert list_row()["is_active"] is True
    assert list_row()["can_enable"] is False
    mine = client.get(f"{PROFILES_URL}/me", headers=_headers(engineer, settings))
    assert mine.status_code == 200
    assert mine.json["data"]["is_active"] is True
    db_session.expire_all()
    assert db_session.get(FdeProfile, engineer.id).status == "active"
    entitlement = db_session.get(CommercialEntitlement, engineer.id)
    assert entitlement.seat_status == "none"
    assert entitlement.seat_source is None
    assert entitlement.delivery_eligibility == "eligible"
    (event,) = _events(db_session, engineer.id)
    assert (event.event_type, event.actor_user_id, event.target_type) == (
        "fde_profile_enabled",
        admin.id,
        "user",
    )
    assert event.changes["before"] == {"is_active": False}
    assert event.changes["after"] == {"is_active": True}
    assert event.changes["source"] == "dispatch_profiles"
    assert event.changes["request_id"]
    assert "confirm_password" not in event.changes


@pytest.mark.parametrize("role", ["project_lead", "fde_engineer", "viewer", "enterprise_admin"])
def test_only_platform_admin_can_enable_profile(client, db_session, settings, profile_case, role):
    _, engineer = profile_case
    if role == "enterprise_admin":
        org = Org(name=f"profile-enable-{uuid4().hex}", org_type="enterprise")
        db_session.add(org)
        db_session.flush()
        caller = _make_user(db_session, "admin", org_id=org.id)
    elif role == "fde_engineer":
        caller = engineer  # 自助档案不能自行启用
    else:
        caller = _make_user(db_session, role)
    db_session.commit()
    headers = _headers(caller, settings)
    denied = client.post(
        f"{ADMIN_PROFILES_URL}/{engineer.id}/enable",
        headers=headers,
        json={"confirm_password": INITIAL_PASSWORD},
    )
    assert denied.status_code == 403
    assert denied.json["error"]["code"] == "forbidden"
    if role in ("project_lead", "enterprise_admin"):
        listed = client.get(PROFILES_URL, headers=headers)
        assert listed.status_code == 200
        row = next(row for row in listed.json["data"] if row["user_id"] == engineer.id)
        assert row["is_active"] is False and row["can_enable"] is False
    db_session.expire_all()
    assert db_session.get(FdeProfile, engineer.id).is_active is False
    assert _events(db_session, engineer.id) == []


@pytest.mark.parametrize(
    ("profile_status", "eligibility", "status", "code"),
    [
        ("pending", "eligible", 409, "profile_not_active"),
        ("suspended", "eligible", 409, "profile_not_active"),
        ("active", "none", 409, "delivery_eligibility_required"),
        ("active", None, 409, "delivery_eligibility_required"),
        (None, "eligible", 404, "profile_not_found"),
    ],
)
def test_enable_requires_existing_active_profile_and_eligible_commercial_record(
    client, db_session, settings, profile_case, profile_status, eligibility, status, code
):
    admin, engineer = profile_case
    profile = db_session.get(FdeProfile, engineer.id)
    entitlement = db_session.get(CommercialEntitlement, engineer.id)
    if profile_status is None:
        db_session.delete(profile)
    else:
        profile.status = profile_status
    if eligibility is None:
        db_session.delete(entitlement)
    else:
        entitlement.delivery_eligibility = eligibility
    db_session.commit()
    headers = _headers(admin, settings)
    if profile_status is not None:
        listed = client.get(PROFILES_URL, headers=headers)
        assert listed.status_code == 200
        row = next(row for row in listed.json["data"] if row["user_id"] == engineer.id)
        assert row["is_active"] is False and row["can_enable"] is False
    denied = client.post(
        f"{ADMIN_PROFILES_URL}/{engineer.id}/enable",
        headers=headers,
        json={"confirm_password": INITIAL_PASSWORD},
    )
    assert (denied.status_code, denied.json["error"]["code"]) == (status, code)
    db_session.expire_all()
    profile_after = db_session.get(FdeProfile, engineer.id)
    entitlement_after = db_session.get(CommercialEntitlement, engineer.id)
    assert (
        (profile_after.status, profile_after.is_active) == (profile_status, False)
        if profile_after
        else profile_status is None
    )
    assert (entitlement_after.delivery_eligibility if entitlement_after else None) == eligibility
    assert _events(db_session, engineer.id) == []


def test_admin_must_confirm_each_enable_and_cannot_submit_disable(
    client, db_session, settings, profile_case
):
    admin, engineer = profile_case
    url = f"{ADMIN_PROFILES_URL}/{engineer.id}/enable"
    headers = _headers(admin, settings)
    assert client.post(url, json={"confirm_password": INITIAL_PASSWORD}).status_code == 401
    for payload in (
        {},
        {"confirm_password": ""},
        {"confirm_password": True},
        {"confirm_password": INITIAL_PASSWORD, "is_active": False},
    ):
        malformed = client.post(url, headers=headers, json=payload)
        assert malformed.status_code == 400
    for _ in range(5):
        denied = client.post(url, headers=headers, json={"confirm_password": "wrong-password"})
        assert (denied.status_code, denied.json["error"]["code"]) == (403, "invalid_password")
    blocked = client.post(url, headers=headers, json={"confirm_password": INITIAL_PASSWORD})
    assert (blocked.status_code, blocked.json["error"]["code"]) == (429, "too_many_attempts")
    db_session.expire_all()
    assert db_session.get(FdeProfile, engineer.id).is_active is False
    assert _events(db_session, engineer.id) == []


def test_platform_admin_enable_for_enterprise_target_is_audited_to_enterprise(
    client, db_session, settings, profile_case
):
    admin, engineer = profile_case
    org = Org(name=f"profile-enable-{uuid4().hex}", org_type="enterprise")
    db_session.add(org)
    db_session.flush()
    engineer.org_id = org.id
    db_session.commit()
    response = client.post(
        f"{ADMIN_PROFILES_URL}/{engineer.id}/enable",
        headers=_headers(admin, settings),
        json={"confirm_password": INITIAL_PASSWORD},
    )
    assert response.status_code == 200
    (event,) = _events(db_session, engineer.id)
    assert event.org_id == org.id
    assert event.event_type == "cross_org_fde_profile_enabled"


@pytest.mark.parametrize(
    ("attribute", "value"),
    [("role", "viewer"), ("is_active", False), ("registration_state", "suspended")],
)
def test_enable_rechecks_delivery_account_identity(
    client, db_session, settings, profile_case, attribute, value
):
    admin, engineer = profile_case
    setattr(engineer, attribute, value)
    db_session.commit()
    headers = _headers(admin, settings)
    listed = client.get(PROFILES_URL, headers=headers)
    assert listed.status_code == 200
    row = next(row for row in listed.json["data"] if row["user_id"] == engineer.id)
    assert row["is_active"] is False and row["can_enable"] is False
    denied = client.post(
        f"{ADMIN_PROFILES_URL}/{engineer.id}/enable",
        headers=headers,
        json={"confirm_password": INITIAL_PASSWORD},
    )
    assert (denied.status_code, denied.json["error"]["code"]) == (409, "delivery_identity_required")
    db_session.expire_all()
    assert db_session.get(FdeProfile, engineer.id).is_active is False
    assert _events(db_session, engineer.id) == []


@pytest.mark.parametrize(
    ("attribute", "value"),
    [("is_active", False), ("role", "viewer"), ("registration_state", "suspended")],
)
def test_automatic_matching_stops_offering_after_delivery_account_loses_access(
    db_session, attribute, value
):
    from fde_api.dispatch.matching import match_package
    from fde_api.dispatch.packages import publish_package
    from test_dispatch_p1_r5 import _active_rule, _onsite_package, _profile

    engineer = _make_user(db_session, "fde_engineer")
    _profile(
        db_session,
        engineer,
        level="L2",
        module_tags=["pre_diagnosis"],
        industry_tags=["制造业"],
        home_city="广州",
    )
    _active_rule(db_session)
    admin, first = _onsite_package(db_session)
    publish_package(db_session, actor=admin, package_id=first.id)
    baseline = match_package(db_session, actor=admin, package_id=first.id)
    assert [offer["candidate_user_id"] for offer in baseline["offers"]] == [engineer.id]

    setattr(engineer, attribute, value)
    db_session.flush()
    assert db_session.get(FdeProfile, engineer.id).is_active is True
    admin, second = _onsite_package(db_session)
    publish_package(db_session, actor=admin, package_id=second.id)
    result = match_package(db_session, actor=admin, package_id=second.id)
    assert result["scenario"] == "C"
    assert result["offers"] == []


@pytest.mark.parametrize("seat", ["none", "expired", "active"])
def test_admin_registers_profile_then_enables_only_if_active(client, db_session, settings, seat):
    admin = _make_user(db_session, "admin")
    engineer = _make_user(db_session, "fde_engineer")
    db_session.flush()
    entitlement = CommercialEntitlement(user_id=engineer.id, delivery_eligibility="eligible")
    if seat != "none":
        now = datetime.now(timezone.utc)
        entitlement.seat_status = "active"
        entitlement.seat_source = "bootcamp_practical"
        entitlement.seat_activated_at = now - timedelta(days=10)
        entitlement.seat_expires_at = now + timedelta(days=10 if seat == "active" else -1)
    db_session.add(entitlement)
    db_session.commit()
    headers = _headers(admin, settings)
    profile_status = "active" if seat == "active" else "pending"
    for city, changed, expected_code in ((" 苏州 ", True, 201), ("上海", False, 200)):
        response = client.post(
            ADMIN_PROFILES_URL,
            headers=headers,
            json={"user_id": engineer.id, "home_city": city, "confirm_password": INITIAL_PASSWORD},
        )
        assert response.status_code == expected_code, response.json
        assert response.json["data"] == {
            "user_id": engineer.id,
            "home_city": "苏州",
            "status": profile_status,
            "is_active": False,
            "changed": changed,
        }
    db_session.expire_all()
    profile = db_session.get(FdeProfile, engineer.id)
    assert profile.level is None
    assert profile.monthly_capacity_hours is None
    assert profile.avg_delivery_hours is None
    assert db_session.get(CommercialEntitlement, engineer.id).seat_status == (
        "none" if seat == "none" else "active"
    )
    (event,) = _events(db_session, engineer.id)
    assert event.event_type == "fde_profile_registered"
    assert event.changes["after"] == {
        "status": profile_status,
        "is_active": False,
        "home_city": "苏州",
    }
    response = client.post(
        f"{ADMIN_PROFILES_URL}/{engineer.id}/enable",
        headers=headers,
        json={"confirm_password": INITIAL_PASSWORD},
    )
    if seat == "active":
        assert response.status_code == 200
        assert response.json["data"]["is_active"] is True
    else:
        assert (response.status_code, response.json["error"]["code"]) == (409, "profile_not_active")
    if seat == "none":
        activated = client.post(
            f"/api/v1/admin/commercial/users/{engineer.id}/seat-activation",
            headers=headers,
            json={
                "seat_source": "bootcamp_practical",
                "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
                "confirm_password": INITIAL_PASSWORD,
            },
        )
        assert activated.status_code == 200, activated.json
        db_session.expire_all()
        profile = db_session.get(FdeProfile, engineer.id)
        assert (profile.status, profile.is_active) == ("active", False)
        enabled = client.post(
            f"{ADMIN_PROFILES_URL}/{engineer.id}/enable",
            headers=headers,
            json={"confirm_password": INITIAL_PASSWORD},
        )
        assert enabled.status_code == 200, enabled.json
        assert enabled.json["data"]["changed"] is True
        assert {event.event_type for event in _events(db_session, engineer.id)} == {
            "fde_profile_registered",
            "commercial_seat_activated",
            "fde_profile_enabled",
        }


@pytest.mark.parametrize(
    ("role", "registration_state", "eligibility", "error_code"),
    [
        ("viewer", "active", "eligible", "delivery_identity_required"),
        ("fde_engineer", "suspended", "eligible", "delivery_identity_required"),
        ("fde_engineer", "active", None, "delivery_eligibility_required"),
        ("fde_engineer", "active", "none", "delivery_eligibility_required"),
    ],
)
def test_registration_requires_reviewed_deliverer_and_commercial_eligibility(
    client, db_session, settings, role, registration_state, eligibility, error_code
):
    admin = _make_user(db_session, "admin")
    target = _make_user(db_session, role)
    target.registration_state = registration_state
    db_session.flush()
    if eligibility is not None:
        db_session.add(CommercialEntitlement(user_id=target.id, delivery_eligibility=eligibility))
    db_session.commit()
    response = client.post(
        ADMIN_PROFILES_URL,
        headers=_headers(admin, settings),
        json={"user_id": target.id, "confirm_password": INITIAL_PASSWORD},
    )
    assert (response.status_code, response.json["error"]["code"]) == (409, error_code)
    assert db_session.get(FdeProfile, target.id) is None
    assert _events(db_session, target.id) == []


def test_registration_requires_platform_admin_password_and_rejects_profile_overrides(
    client, db_session, settings
):
    admin = _make_user(db_session, "admin")
    lead = _make_user(db_session, "project_lead")
    engineer = _make_user(db_session, "fde_engineer")
    db_session.flush()
    db_session.add(CommercialEntitlement(user_id=engineer.id, delivery_eligibility="eligible"))
    db_session.commit()
    payload = {"user_id": engineer.id, "confirm_password": INITIAL_PASSWORD}
    denied = client.post(ADMIN_PROFILES_URL, headers=_headers(lead, settings), json=payload)
    assert (denied.status_code, denied.json["error"]["code"]) == (403, "forbidden")
    headers = _headers(admin, settings)
    for invalid in (
        {"user_id": engineer.id},
        {**payload, "level": "L1"},
        {**payload, "monthly_capacity_hours": 160},
        {**payload, "is_active": True},
        {**payload, "home_city": "长" * 33},
    ):
        response = client.post(ADMIN_PROFILES_URL, headers=headers, json=invalid)
        assert (response.status_code, response.json["error"]["code"]) == (400, "invalid_request")
    response = client.post(
        ADMIN_PROFILES_URL,
        headers=headers,
        json={**payload, "confirm_password": "wrong-password"},
    )
    assert (response.status_code, response.json["error"]["code"]) == (403, "invalid_password")
    assert db_session.get(FdeProfile, engineer.id) is None
    assert _events(db_session, engineer.id) == []
