"""M8 重放防护专项：API-action 幂等键、确认窗口、陈旧令牌归属变更。

leader §9 R1（:228 跨企业数据泄露＝最高级事故）与 R6（:233 密钥/口令
不入日志）关联的运行时面。现有机制的权威实现是
``fde_api/control/api_actions.py``：``execute_api`` 以
``sha256([user.id, execution_id, data])`` 作幂等键（:140-145），
``pending_actions`` / ``action_status`` / ``decide_action`` 三路径均按
``actor_user_id`` 收敛（:213-282），确认窗口由 ``CONFIRMATION_WINDOW``
单点推导（:37），finished replay 不受窗口影响（:107-115）。

本文件只钉**既有机制的回归行为**，不新增生产代码、不构造生产缺陷：

- 同 ``execution_id`` 重放不得新增 ``OperationEvent``（幂等）。
- ``execution_id``／幂等键按 actor 派生：B 企业账号拿 A 的 execution_id
  不得命中 A 的结果（跨 org 不命中）；三条消费路径均拒绝外来 identifier。
- 迟到决策零副作用（pending 筛除 / status expired / 不落 started·finished /
  目标不变）。
- 陈旧令牌：令牌 claim 的 ``org_id`` 只是快照，授权判定读库
  （``test_org_scope_entry.py:263``）；账号迁出 B 企业后旧令牌不得再读 B 资源。

覆盖面＝「测试判别力面」＋「运行时重放面」，不得跨面支撑 git 泄漏面。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy import update as sa_update

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.control.access import capabilities_for_level
from fde_api.control.api_actions import (
    CONFIRMATION_WINDOW,
    action_status,
    decide_action,
    execute_api,
    pending_actions,
)
from fde_api.control.service import ControlServiceError
from fde_api.workbench.models import OperationEvent
from multi_tenant_harness import (
    make_enterprise_org,
    make_project as make_org_project,
    make_user,
)
from test_ai_server_chat_mcp import make_project

_WINDOW_PASSWORD = "m8-window-pw"


def invoke(user, operation, parameters=None, body=None, *, execution=None, scope=None, level="system_operator"):
    """同 test_ai_api_actions.py:14 的调用形态，直接驱动 execute_api。"""
    return execute_api(
        user=user,
        claims={"execution_id": execution or str(uuid4()), "project_id": scope},
        allowed=set(capabilities_for_level(level)),
        operation=operation,
        parameters=parameters,
        body=body,
    )


def _make_admin(db_session, label, org_id):
    user = User(
        username=f"m8-replay-{label}-{uuid4().hex}",
        display_name=label,
        role="admin",
        password_hash=hash_password(_WINDOW_PASSWORD),
        must_change_password=False,
        is_active=True,
        org_id=org_id,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _events_of(db_session, identifier):
    return db_session.scalars(
        select(OperationEvent).where(OperationEvent.target_id == identifier)
    ).all()


def _awaiting_action(user, db_session):
    """发起敏感写操作，落 awaiting_confirmation（projects.update 通道）。"""
    user.password_hash = hash_password(_WINDOW_PASSWORD)
    db_session.commit()
    project = make_project(db_session, user)
    result = invoke(
        user,
        "projects.update",
        {"project_id": project.id},
        {"version": project.version, "status": "cancelled"},
    )
    assert result["status"] == "awaiting_confirmation", result
    return project, result["action_id"]


@pytest.fixture
def m8_replay_ctx(app, db_session):
    """两个不同企业 org 的各一名 admin；``app.app_context()`` 供 execute_api
    使用（``current_app``／内部 test_client 转发）。"""
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user_a = _make_admin(db_session, "a", org_a.id)
    user_b = _make_admin(db_session, "b", org_b.id)
    with app.app_context():
        yield {
            "org_a": org_a,
            "org_b": org_b,
            "user_a": user_a,
            "user_b": user_b,
        }


def test_m8_window_constant_is_fifteen_minutes():
    """窗口常量单一权威值（漂移即红，同 test_api_confirmation_expiry.py:58）。"""
    assert CONFIRMATION_WINDOW == timedelta(minutes=15)


def test_m8_same_execution_id_replay_does_not_add_operation_events(m8_replay_ctx, db_session):
    """同键重放返回既有结果，且不得新增任何 OperationEvent。"""
    user = m8_replay_ctx["user_a"]
    project = make_project(db_session, user)
    execution = str(uuid4())
    args = {"project_id": project.id}
    body = {"version": project.version, "name": "M8 replay guard"}
    result = invoke(user, "projects.update", args, body, execution=execution)
    assert result["status"] == "completed", result
    identifier = result["action_id"]

    before = _events_of(db_session, identifier)
    assert {e.event_type for e in before} == {
        "ai.api.requested",
        "ai.api.started",
        "ai.api.finished",
    }
    replay = invoke(user, "projects.update", args, body, execution=execution)
    assert replay == result

    db_session.rollback()  # 结束本连接可重复读快照（同 test_api_confirmation_expiry 纪律）
    after = _events_of(db_session, identifier)
    assert len(after) == len(before) == 3
    assert {e.event_type for e in after} == {
        "ai.api.requested",
        "ai.api.started",
        "ai.api.finished",
    }


def test_m8_finished_action_replay_is_not_shadowed_by_expiry(m8_replay_ctx, db_session):
    """已完成操作的同键 replay 不受确认窗口到期遮蔽，且不追加事件。"""
    user = m8_replay_ctx["user_a"]
    project = make_project(db_session, user)
    execution = str(uuid4())
    args = {"project_id": project.id}
    body = {"version": project.version, "name": "M8 finished replay"}
    first = invoke(user, "projects.update", args, body, execution=execution)
    assert first["status"] == "completed", first

    db_session.execute(
        sa_update(OperationEvent)
        .where(OperationEvent.target_id == first["action_id"])
        .values(created_at=datetime.now(UTC) - timedelta(hours=1))
    )
    db_session.commit()
    replay = invoke(user, "projects.update", args, body, execution=execution)
    assert replay == first
    db_session.rollback()
    assert len(_events_of(db_session, first["action_id"])) == 3


def test_m8_execution_id_is_actor_scoped_not_globally_replayable(
    m8_replay_ctx, db_session, monkeypatch
):
    """跨 org 不命中：B 企业账号拿 A 的 execution_id + 同一入参，不得命中
    A 的结果（幂等键含 user.id，见 api_actions.py:144）。"""
    monkeypatch.setattr(
        "fde_api.control.model_preferences._validate_url", lambda value: value
    )
    user_a = m8_replay_ctx["user_a"]
    user_b = m8_replay_ctx["user_b"]
    execution = str(uuid4())
    # models.save 无路径参数，可让两个 actor 用**完全相同**的 data 调用，
    # 从而把差异隔离到 user.id 一维。
    body = {
        "scope": "personal",
        "name": "M8 cross-org replay model",
        "provider": "openai-compatible",
        "base_url": "https://api.example.com/v1",
        "model": "m8-replay-model-id",
        "is_default": False,
        "supports_tools": True,
    }
    first = invoke(user_a, "models.save", body=body, execution=execution)
    assert first["status"] == "completed", first
    second = invoke(user_b, "models.save", body=body, execution=execution)
    assert second["status"] == "completed", second
    assert second["action_id"] != first["action_id"], (
        "同一 execution_id 跨 actor 命中了同一幂等键——跨主体重放面"
    )
    with pytest.raises(ControlServiceError):
        action_status(user_b, first["action_id"])


def test_m8_pending_actions_is_owner_scoped(m8_replay_ctx, db_session):
    """待确认清单按 actor 收敛：B 企业账号看不到 A 的待确认操作。"""
    user_a = m8_replay_ctx["user_a"]
    user_b = m8_replay_ctx["user_b"]
    _project, identifier = _awaiting_action(user_a, db_session)
    assert [row["id"] for row in pending_actions(user_a)] == [identifier]
    assert pending_actions(user_b) == []


def test_m8_action_status_rejects_foreign_identifier(m8_replay_ctx, db_session):
    """action_status 对外来 identifier 报 not_found（不得跨主体读状态）。"""
    user_a = m8_replay_ctx["user_a"]
    user_b = m8_replay_ctx["user_b"]
    _project, identifier = _awaiting_action(user_a, db_session)
    with pytest.raises(ControlServiceError) as caught:
        action_status(user_b, identifier)
    assert caught.value.code == "not_found"


def test_m8_decide_action_rejects_foreign_identifier(m8_replay_ctx, db_session):
    """decide_action 对外来 identifier 拒绝，且不落任何 started/finished 事件。"""
    user_a = m8_replay_ctx["user_a"]
    user_b = m8_replay_ctx["user_b"]
    _project, identifier = _awaiting_action(user_a, db_session)
    user_b.password_hash = hash_password(_WINDOW_PASSWORD)
    db_session.commit()
    with pytest.raises(ControlServiceError):
        decide_action(user_b, identifier, _WINDOW_PASSWORD)
    db_session.rollback()
    assert _events_of(db_session, identifier) and all(
        e.event_type == "ai.api.requested" for e in _events_of(db_session, identifier)
    )


def test_m8_late_decision_after_expiry_has_zero_side_effects(m8_replay_ctx, db_session):
    """迟到决策：pending 筛除 / status expired / 拒绝 / 不落 started·finished /
    目标零副作用（B#13-C append-only 纪律）。"""
    user = m8_replay_ctx["user_a"]
    project, identifier = _awaiting_action(user, db_session)
    db_session.execute(
        sa_update(OperationEvent)
        .where(
            OperationEvent.target_id == identifier,
            OperationEvent.event_type == "ai.api.requested",
        )
        .values(created_at=datetime.now(UTC) - timedelta(minutes=16))
    )
    db_session.commit()

    assert pending_actions(user) == []
    assert action_status(user, identifier)["status"] == "expired"
    with pytest.raises(ControlServiceError) as caught:
        decide_action(user, identifier, _WINDOW_PASSWORD)
    assert caught.value.code == "action_expired"

    db_session.rollback()
    assert {e.event_type for e in _events_of(db_session, identifier)} == {
        "ai.api.requested"
    }
    db_session.refresh(project)
    assert project.status == "active"


def test_m8_stale_token_after_org_change_cannot_read_b_resource(
    client, db_session, settings
):
    """陈旧令牌：claim 的 org_id 只是快照，授权读库；账号迁出 B 企业后，
    旧令牌不得再读 B 企业项目（test_org_scope_entry.py:263 的回归钉）。"""
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_org_project(
        db_session, user, code=f"M8{uuid4().hex[:8]}", org_id=org_b.id
    )
    db_session.commit()
    headers = {"Authorization": f"Bearer {issue_access_token(user, settings)}"}

    # 阳性对照：归属仍为 org_b 时属主可读，防「全 404」假绿。
    before = client.get(f"/api/v1/projects/{project_b.id}", headers=headers)
    assert before.status_code == 200, (
        before.status_code,
        before.get_data(as_text=True)[:200],
    )

    user.org_id = org_a.id
    db_session.commit()
    after = client.get(f"/api/v1/projects/{project_b.id}", headers=headers)
    assert after.status_code in (401, 403, 404), (
        after.status_code,
        after.get_data(as_text=True)[:200],
    )
    assert str(project_b.id) not in after.get_data(as_text=True)
