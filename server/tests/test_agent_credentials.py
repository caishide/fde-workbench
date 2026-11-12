"""E11：智能体凭据管理面（`agents/credentials.py` ＋ 三个路由）。

覆盖：
1. **只存密文、绝不回显**——落库是 Fernet 密文，响应与列表**无明文无密文**；
2. **平台管理面闸**——非平台身份 403（企业身份被授予 system_operator 也不行，
   沿 M3b 批次 ①-a 单一判定）；
3. **凭据名校验**——只允许字母数字下划线（会进 env 名），空名/超长/非法字符 400；
4. **同名即更新**（幂等写入）；
5. **删除**；
6. **种子一致性**——zcode 型种子 agent 的 `credential_ref` 非空（否则 run 发起
   409 credential_missing），persona 型保持 null（不可执行，不需要凭据）。
"""
from __future__ import annotations

from unittest.mock import patch

from fde_api.agents.models import AgentCredential, AgentRegistry
from fde_api.agents.seeds import _agent_seeds

from uuid import uuid4

import pytest

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token

PASSWORD = "Passw0rd!demo"


class _Client:
    def __init__(self, client, user, headers) -> None:
        self.client = client
        self.user = user
        self.headers = headers

    def get(self, *args, **kwargs):
        return self.client.get(*args, headers=self.headers, **kwargs)

    def post(self, *args, **kwargs):
        return self.client.post(*args, headers=self.headers, **kwargs)

    def patch(self, *args, **kwargs):
        return self.client.patch(*args, headers=self.headers, **kwargs)

    def delete(self, *args, **kwargs):
        return self.client.delete(*args, headers=self.headers, **kwargs)


@pytest.fixture
def make_account(client, db_session, settings):
    """造账号的工厂（**fixture 名与测试参数名不同**，避免同名遮蔽）。"""

    def create(role: str) -> _Client:
        user = User(
            username=f"{role}.{uuid4().hex}",
            display_name=role,
            role=role,
            password_hash=hash_password(PASSWORD),
            must_change_password=False,
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()
        headers = {"Authorization": f"Bearer {issue_access_token(user, settings)}"}
        return _Client(client, user, headers)

    return create


def _platform_admin(make_account):
    """平台身份 ＋ system_operator AI 档（admin 默认档位）。"""
    return make_account("admin")


# --- 只存密文、绝不回显 ------------------------------------------------


def test_credential_is_stored_encrypted_and_never_echoed(make_account, db_session):
    admin = _platform_admin(make_account)
    secret = "sk-super-secret-value"

    response = admin.post(
        "/api/v1/agents/credentials",
        json={"name": "default", "credential": secret},
    )

    assert response.status_code == 200, response.get_data(as_text=True)
    body = response.get_data(as_text=True)
    assert secret not in body
    assert "credential_ciphertext" not in body

    db_session.expire_all()
    row = db_session.query(AgentCredential).filter_by(name="default").one()
    assert row.credential_ciphertext
    assert secret not in row.credential_ciphertext


def test_credential_list_exposes_no_ciphertext(make_account, db_session):
    admin = _platform_admin(make_account)
    admin.post("/api/v1/agents/credentials", json={"name": "default", "credential": "s3cret"})

    response = admin.get("/api/v1/agents/credentials")

    assert response.status_code == 200
    payload = response.get_data(as_text=True)
    assert "s3cret" not in payload
    assert "credential_ciphertext" not in payload
    names = {item["name"] for item in response.json["data"]}
    assert "default" in names
    entry = next(item for item in response.json["data"] if item["name"] == "default")
    assert entry["credential_configured"] is True


# --- 平台管理面闸 ------------------------------------------------------


def test_non_platform_identity_cannot_write_credentials(make_account, db_session):
    """企业身份（即便被授予 system_operator AI 档）也不得写凭据。"""
    engineer = make_account("fde_engineer")

    response = engineer.post(
        "/api/v1/agents/credentials",
        json={"name": "default", "credential": "s3cret"},
    )

    assert response.status_code == 403
    assert response.json["error"]["code"] == "forbidden"


def test_platform_identity_with_ai_access_disabled_cannot_write_credentials(
    make_account, db_session
):
    """平台身份但 AI 权限被关 ⇒ 仍不得写凭据（单一判定的两个轴都要过）。"""
    admin = _platform_admin(make_account)

    with patch(
        "fde_api.agents.credentials.is_platform_operator", return_value=False
    ):
        response = admin.post(
            "/api/v1/agents/credentials",
            json={"name": "default", "credential": "s3cret"},
        )

    assert response.status_code == 403


def test_listing_credentials_requires_platform_operator(make_account, db_session):
    viewer = make_account("viewer")
    response = viewer.get("/api/v1/agents/credentials")
    assert response.status_code == 403


# --- 凭据名校验 -------------------------------------------------------


@pytest.mark.parametrize(
    "bad_name",
    ["", "  ", "has space", "has-dash", "has.dot", "a" * 121, "env$inject"],
)
def test_invalid_credential_names_are_rejected(make_account, db_session, bad_name):
    admin = _platform_admin(make_account)
    response = admin.post(
        "/api/v1/agents/credentials",
        json={"name": bad_name, "credential": "s3cret"},
    )
    assert response.status_code == 400, bad_name
    assert response.json["error"]["code"] == "invalid_credential"


def test_empty_credential_is_rejected(make_account, db_session):
    admin = _platform_admin(make_account)
    response = admin.post(
        "/api/v1/agents/credentials",
        json={"name": "default", "credential": "   "},
    )
    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_credential"


def test_unknown_payload_fields_are_rejected(make_account, db_session):
    admin = _platform_admin(make_account)
    response = admin.post(
        "/api/v1/agents/credentials",
        json={"name": "default", "credential": "s3cret", "evil": "x"},
    )
    assert response.status_code == 400


# --- 同名更新与删除 ----------------------------------------------------


def test_same_name_updates_in_place(make_account, db_session):
    admin = _platform_admin(make_account)
    admin.post("/api/v1/agents/credentials", json={"name": "default", "credential": "first"})
    admin.post("/api/v1/agents/credentials", json={"name": "default", "credential": "second"})

    db_session.expire_all()
    rows = db_session.query(AgentCredential).filter_by(name="default").all()
    assert len(rows) == 1
    assert "first" not in rows[0].credential_ciphertext
    assert "second" not in rows[0].credential_ciphertext


def test_delete_credential_removes_row(make_account, db_session):
    admin = _platform_admin(make_account)
    admin.post("/api/v1/agents/credentials", json={"name": "default", "credential": "s3cret"})

    response = admin.delete("/api/v1/agents/credentials/default")

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(AgentCredential).filter_by(name="default").count() == 0


def test_delete_missing_credential_returns_404(make_account, db_session):
    admin = _platform_admin(make_account)
    response = admin.delete("/api/v1/agents/credentials/nope")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "credential_not_found"


# --- 种子一致性 -------------------------------------------------------


def test_zcode_seeds_carry_credential_ref():
    """zcode 型种子 agent 必须带 `credential_ref`——否则 run 发起 409 credential_missing。"""
    zcode_rows = [row for row in _agent_seeds() if row.get("kind") == "zcode"]
    assert zcode_rows, "种子应有 zcode 型 agent"
    for row in zcode_rows:
        assert row.get("credential_ref"), row.get("name")


def test_persona_seeds_keep_null_credential_ref():
    """persona 型不可执行（start_run 直接拒），凭据位保持 null。"""
    persona_rows = [row for row in _agent_seeds() if row.get("kind") == "persona"]
    for row in persona_rows:
        assert row.get("credential_ref") is None, row.get("name")


def test_registry_credential_ref_matches_seed(make_account, db_session):
    """注册表行的 credential_ref 与种子一致（装载后不得漂移）。"""
    db_session.expire_all()
    registry = db_session.query(AgentRegistry).all()
    seeded = {
        (row.get("kind"), row.get("capability_tier")): row.get("credential_ref")
        for row in _agent_seeds()
    }
    for item in registry:
        expected = seeded.get((item.kind, item.capability_tier))
        if expected is None:
            continue
        assert item.credential_ref == expected, item.name
