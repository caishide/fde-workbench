"""goal-d4：V8 幂等（I-1）+ 重试链 ≤2 次指数退避。

幂等语义在服务层收敛（d3 迁移注释的落地点）：completed 复用、失败后
必须走显式 retry；retry 共享幂等键（家族大小 = 尝试次数），退避
base*2^(已重试-1) 秒。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from test_agents_d4_harness import (
    RecordingBackend,
    ScriptedEvents,
    api_client,
    prime_run,
    seed_agent,
)
from test_document_drafts_api import _persist_project

from fde_api.agents.models import AgentRun
from test_agents_d4_harness import d4_app, d4_client, d4_settings  # noqa: F401  (pytest fixture)


def _setup(db_session, d4_client, d4_settings):
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code=f"D4I{uuid4().hex[:6]}")
    agent = seed_agent(db_session, d4_settings)
    return leader, project, agent


def _post(leader, agent, project, key):
    return leader.post(
        f"/api/v1/agents/{agent.id}/run",
        json={"project_id": project.id, "idempotency_key": key},
    )


def _family_count(db_session, key: str) -> int:
    return len(list(db_session.scalars(select(AgentRun).where(AgentRun.idempotency_key == key))))


def test_completed_run_reused_without_rerun(db_session, d4_client, d4_app, d4_settings) -> None:
    """I-1：同幂等键连续两次请求 → 第二次复用首次结果（200），不重复计费。"""
    leader, project, agent = _setup(db_session, d4_client, d4_settings)
    prime_run(d4_app, events=ScriptedEvents([[{"type": "tool_call", "tool": "read_file"}], [{"type": "done", "exit_code": 0}]]))
    key = f"i1:{uuid4().hex}"

    first = _post(leader, agent, project, key)
    assert first.status_code == 201
    second = _post(leader, agent, project, key)
    assert second.status_code == 200
    assert second.json["data"]["id"] == first.json["data"]["id"]
    assert second.json["data"]["token_cost"] == first.json["data"]["token_cost"]
    assert _family_count(db_session, key) == 1


def test_failed_run_requires_explicit_retry(db_session, d4_client, d4_app, d4_settings) -> None:
    """终态失败：同键 start 不悄悄重跑 → 409 agent_run_retry_required。"""
    leader, project, agent = _setup(db_session, d4_client, d4_settings)
    prime_run(d4_app, events=ScriptedEvents([[{"type": "done", "exit_code": 1}]]))
    key = f"fail:{uuid4().hex}"
    assert _post(leader, agent, project, key).status_code == 201
    blocked = _post(leader, agent, project, key)
    assert blocked.status_code == 409
    assert blocked.json["error"]["code"] == "agent_run_retry_required"
    assert _family_count(db_session, key) == 1


def test_retry_creates_linked_attempt_sharing_key(db_session, d4_client, d4_app, d4_settings) -> None:
    """retry：新 run 挂 retry_of、共享幂等键；原 run 终态不变。"""
    leader, project, agent = _setup(db_session, d4_client, d4_settings)
    d4_app.extensions["fde_agent_sandbox_backend"] = RecordingBackend()
    d4_app.extensions["fde_agent_event_provider_factory"] = lambda run_id, workspace: ScriptedEvents(
        [[{"type": "done", "exit_code": 1}]]
    )
    key = f"retry:{uuid4().hex}"
    original_id = _post(leader, agent, project, key).json["data"]["id"]

    retried = leader.post(f"/api/v1/agents/runs/{original_id}/retry", json=None)
    assert retried.status_code == 201, retried.json
    data = retried.json["data"]
    assert data["id"] != original_id
    assert data["retry_of"] == original_id
    assert data["idempotency_key"] == key
    assert _family_count(db_session, key) == 2
    assert db_session.get(AgentRun, original_id).status == "failed"


def test_retry_cap_two_attempts_then_refuse(db_session, d4_client, d4_app, d4_settings) -> None:
    """重试上限 2 次（家族 = 3 个 run）；第 3 次 retry 409。"""
    leader, project, agent = _setup(db_session, d4_client, d4_settings)
    d4_app.extensions["fde_agent_sandbox_backend"] = RecordingBackend()
    d4_app.extensions["fde_agent_event_provider_factory"] = lambda run_id, workspace: ScriptedEvents(
        [[{"type": "done", "exit_code": 1}]]
    )
    key = f"cap:{uuid4().hex}"
    original_id = _post(leader, agent, project, key).json["data"]["id"]
    first = leader.post(f"/api/v1/agents/runs/{original_id}/retry", json=None)
    second = leader.post(f"/api/v1/agents/runs/{original_id}/retry", json=None)
    assert (first.status_code, second.status_code) == (201, 201)
    third = leader.post(f"/api/v1/agents/runs/{original_id}/retry", json=None)
    assert third.status_code == 409
    assert third.json["error"]["code"] == "agent_retry_limit_exceeded"
    assert _family_count(db_session, key) == 3


def test_retry_backoff_window_blocks_then_elapses(db_session, d4_client, d4_app, d4_settings) -> None:
    """指数退避：base=30 时第 1 次重试需等 30s；窗口未到 409 + retry_after。"""
    leader, project, agent = _setup(db_session, d4_client, d4_settings)
    d4_app.extensions["fde_agent_sandbox_backend"] = RecordingBackend()
    d4_app.extensions["fde_agent_event_provider_factory"] = lambda run_id, workspace: ScriptedEvents(
        [[{"type": "done", "exit_code": 1}]]
    )
    d4_app.config["SETTINGS"] = d4_app.config["SETTINGS"].model_copy(update={"agent_retry_backoff_base_seconds": 30})
    key = f"backoff:{uuid4().hex}"
    original_id = _post(leader, agent, project, key).json["data"]["id"]

    blocked = leader.post(f"/api/v1/agents/runs/{original_id}/retry", json=None)
    assert blocked.status_code == 409
    assert blocked.json["error"]["code"] == "retry_backoff_not_elapsed"
    assert blocked.json["error"]["details"]["retry_after_ms"] > 0

    # 退避归零（等价窗口已过）→ 放行
    d4_app.config["SETTINGS"] = d4_app.config["SETTINGS"].model_copy(update={"agent_retry_backoff_base_seconds": 0})
    assert leader.post(f"/api/v1/agents/runs/{original_id}/retry", json=None).status_code == 201


def test_retry_rejects_completed_runs_and_unauthorized_users(db_session, d4_client, d4_app, d4_settings) -> None:
    """completed 不可 retry；档位不足的工程师 retry 被实时鉴权拦截。"""
    leader, project, agent = _setup(db_session, d4_client, d4_settings)
    prime_run(d4_app, events=ScriptedEvents([[{"type": "done", "exit_code": 0}]]))
    completed_id = _post(leader, agent, project, f"ok:{uuid4().hex}").json["data"]["id"]
    denied = leader.post(f"/api/v1/agents/runs/{completed_id}/retry", json=None)
    assert denied.status_code == 409
    assert denied.json["error"]["code"] == "agent_retry_not_allowed"

    prime_run(d4_app, events=ScriptedEvents([[{"type": "done", "exit_code": 1}]]))
    failed_id = _post(leader, agent, project, f"no:{uuid4().hex}").json["data"]["id"]
    engineer = api_client(d4_client, db_session, d4_settings, "fde_engineer")
    assert engineer.post(f"/api/v1/agents/runs/{failed_id}/retry", json=None).status_code == 403
