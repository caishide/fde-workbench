"""M8 敏感日志专项：口令/令牌/密钥明文不得进响应体、caplog、OperationEvent.changes。

leader §9 R6（:233「密钥/口令不入 VCS、不入日志；含 @ 的连接串输出一律
打码」）。既有机制：``fde_api/control/api_actions.py`` 的 ``SECRET_KEYS``
＋ ``_safe(..., incoming=True)`` 递归拒绝密钥字段（:30、:51-78），
``_run`` 把确认口令仅留在内存、不写事件（:194-210）；唯一明确 caplog
明文钉是 ``test_auth_api.py:481-499``（坏登录口令／坏 refresh token）。

本轮把「不进日志·事件·审计」从单点扩展到**三面同钉**（响应体 /
``caplog.text`` / ``OperationEvent.changes``），并加一条 ``SECRET_KEYS``
静态闸（漂移即红）。全部为**只读回归钉**：零生产代码改动、不在生产代码
构造泄漏，也不把「主动构造泄漏以验证」写成「已修复」。

覆盖面＝「运行时日志·事件·审计面」，不得跨面支撑 git 泄漏面
（``check-secret-scan.sh``／gitleaks）或「测试判别力面」。
"""
from __future__ import annotations

import logging
from uuid import uuid4

import pytest
from sqlalchemy import select

from conftest import INITIAL_PASSWORD
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.control.api_actions import SECRET_KEYS
from fde_api.control.service import ControlServiceError
from fde_api.workbench.models import OperationEvent
from test_ai_api_actions import invoke
from test_ai_server_chat_mcp import make_project


@pytest.fixture
def m8_secret_ctx(app, db_session):
    """平台身份 admin；``app.app_context()`` 供 execute_api 的 current_app
    与内部 test_client 转发使用（HTTP 面测试的数据已 commit）。"""
    user = User(
        username=f"m8-secret-{uuid4().hex}",
        display_name="M8 敏感日志用例",
        role="admin",
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with app.app_context():
        yield user


def _all_changes(db_session):
    db_session.rollback()  # 结束本连接可重复读快照，读取别的 session 落的事件
    return str(
        [e.changes for e in db_session.scalars(select(OperationEvent)).all()]
    )


def test_m8_bad_login_password_not_in_response_or_caplog(
    client, db_session, caplog, m8_secret_ctx
):
    """坏登录口令不得进响应体或 caplog（先例 test_auth_api.py:481-499）。"""
    caplog.set_level(logging.DEBUG)
    secret = "M8-NeverLogLogin!9a2b"
    response = client.post(
        "/api/v1/auth/login",
        json={"username": m8_secret_ctx.username, "password": secret, "device_label": "M8"},
    )
    assert response.status_code in (400, 401), response.status_code
    assert secret not in response.get_data(as_text=True)
    assert secret not in caplog.text


def test_m8_bad_refresh_token_not_in_response_or_caplog(client, db_session, caplog):
    """坏 refresh token 不得进响应体或 caplog。"""
    caplog.set_level(logging.DEBUG)
    secret = "M8-NeverLogRefreshToken!9a2b"
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": secret})
    assert response.status_code in (400, 401), response.status_code
    assert secret not in response.get_data(as_text=True)
    assert secret not in caplog.text


def test_m8_issued_tokens_not_in_caplog(client, db_session, caplog, m8_secret_ctx):
    """签发的 access/refresh token 在响应体里是合法的，但不得进日志。"""
    caplog.set_level(logging.DEBUG)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": m8_secret_ctx.username,
            "password": INITIAL_PASSWORD,
            "device_label": "M8",
        },
    )
    assert login.status_code == 200, login.get_data(as_text=True)
    data = login.get_json()["data"]
    assert data["access_token"] and data["refresh_token"]
    assert data["access_token"] not in caplog.text
    assert data["refresh_token"] not in caplog.text


def test_m8_changed_password_not_in_response_caplog_or_audit_events(
    client, db_session, caplog, m8_secret_ctx
):
    """改密新口令：响应体 / caplog / OperationEvent.changes 三面同钉。"""
    caplog.set_level(logging.DEBUG)
    secret = "M8-NeverLogNewPass!9a2b"
    login = client.post(
        "/api/v1/auth/login",
        json={
            "username": m8_secret_ctx.username,
            "password": INITIAL_PASSWORD,
            "device_label": "M8",
        },
    )
    assert login.status_code == 200, login.get_data(as_text=True)
    headers = {"Authorization": f"Bearer {login.get_json()['data']['access_token']}"}
    response = client.post(
        "/api/v1/auth/change-password",
        headers=headers,
        json={"current_password": INITIAL_PASSWORD, "new_password": secret},
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    assert secret not in response.get_data(as_text=True)
    assert secret not in caplog.text
    assert secret not in _all_changes(db_session)


def test_m8_confirmation_password_not_in_response_caplog_or_audit_events(
    client, db_session, settings, caplog, m8_secret_ctx
):
    """确认口令只在专用安全界面内存使用：响应体 / caplog / 事件三面不得出现，
    且以「决策确已完成」作阳性对照（避免断言因请求失败而空转）。"""
    caplog.set_level(logging.DEBUG)
    secret = "M8-NeverLogConfirm!9a2b"
    user = m8_secret_ctx
    user.password_hash = hash_password(secret)
    db_session.commit()
    project = make_project(db_session, user)
    result = invoke(
        user,
        "projects.update",
        {"project_id": project.id},
        {"version": project.version, "status": "cancelled"},
    )
    assert result["status"] == "awaiting_confirmation", result
    identifier = result["action_id"]

    headers = {"Authorization": f"Bearer {issue_access_token(user, settings)}"}
    response = client.post(
        f"/api/v1/ai/actions/{identifier}/decision",
        json={"password": secret},
        headers=headers,
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    # 阳性对照：密码确被消费、操作确已完成（否则「不出现」是空转）。
    assert response.get_json()["data"]["status"] == "completed"
    assert secret not in response.get_data(as_text=True)
    assert secret not in caplog.text
    db_session.rollback()
    events = db_session.scalars(
        select(OperationEvent).where(OperationEvent.target_id == identifier)
    ).all()
    assert secret not in str([e.changes for e in events])


@pytest.mark.parametrize("secret_key", ["password", "api_key", "access_token"])
def test_m8_secret_body_keys_rejected_and_never_recorded_in_audit_events(
    client, db_session, caplog, m8_secret_ctx, secret_key
):
    """密钥字段作为 AI 操作参数被递归拒绝（secret_not_allowed），且不得进
    caplog 或 OperationEvent.changes（拒绝发生在落任何事件之前）。"""
    caplog.set_level(logging.DEBUG)
    secret = f"M8-NeverLog-{secret_key}-9a2b"
    with pytest.raises(ControlServiceError) as caught:
        invoke(m8_secret_ctx, "projects.create", body={secret_key: secret})
    assert caught.value.code == "secret_not_allowed"
    assert secret not in caplog.text
    assert secret not in _all_changes(db_session)


def test_m8_nested_secret_rejected_and_not_recorded(
    client, db_session, caplog, m8_secret_ctx
):
    """嵌套结构里的密钥字段同样被拒绝，且不留痕（_safe 递归）。"""
    caplog.set_level(logging.DEBUG)
    secret = "M8-NeverLog-Nested-9a2b"
    with pytest.raises(ControlServiceError) as caught:
        invoke(m8_secret_ctx, "projects.create", body={"notes": {"api_key": secret}})
    assert caught.value.code == "secret_not_allowed"
    assert secret not in caplog.text
    assert secret not in _all_changes(db_session)


def test_m8_secret_keys_static_gate_covers_required_names():
    """静态闸：SECRET_KEYS 覆盖 leader §9 R6 的密钥/口令名（漂移即红）。"""
    assert {
        "password",
        "api_key",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "credential",
        "credential_ciphertext",
        "secret",
    } <= SECRET_KEYS
