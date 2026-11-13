"""P2′① 宿主轮询领取：服务层三函数 + 三路由（§11.3 六条约束）。

覆盖：fail-closed 闸 / 领取 FIFO+幂等+token 绑定 / 回执终态对齐+产物指纹直录 /
H4 失联只标记 / 状态机迁移（queued→host_running→终态）。
集成层免 app 直调 service（claim/receipt/status 都是纯 session 面）；
HTTP 面跑 1 例烟测（路由→service 接线 + 错误投影）。
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from fde_api.agents import service as svc
from fde_api.agents.models import AgentArtifact, AgentRegistry, AgentRun
from sqlalchemy import select, text

from pydantic import SecretStr

from test_agents_d4_harness import d4_settings  # noqa: F401  (pytest fixture)
from test_document_drafts_api import _persist_project

TOKEN = "host-proxy-token-0123456789abcdef"
_TOKEN_SECRET = SecretStr(TOKEN)
SUMMARY = {
    "sessionId": "sess_p2",
    "usage": {"inputTokens": 10, "outputTokens": 20},
    "projection": {"status": "done", "totalTokenCount": 30},
}


@pytest.fixture
def poll_settings(d4_settings, monkeypatch):
    """settings 快照 + 服务层 _settings 注入（service 直调不经 app context）。"""
    settings = d4_settings.model_copy(
        update={
            "agent_host_poll_enabled": True,
            "agent_host_poll_token": _TOKEN_SECRET,
            "agent_host_lost_mark_minutes": 30,
        }
    )
    monkeypatch.setattr(svc, "_settings", lambda: settings)
    return settings


def _seed_host_run(db_session, settings, *, status="queued", claimed=None, provider="host_poll"):
    """直接落一条 host_poll run（绕过 start_run 全闸——闸面已有既有测试覆盖）。"""
    from test_agents_d4_harness import make_user, seed_agent

    import uuid as _uuid

    user = make_user(db_session, "project_lead")
    project = _persist_project(db_session, user, code=f"HP{_uuid.uuid4().hex[:6].upper()}")
    agent = seed_agent(db_session, settings)
    run = AgentRun(
        project_id=project.id,
        agent_id=agent.id,
        initiated_by_user_id=user.id,
        capability_used=agent.capability_tier,
        status=status,
        context_ref="agent-workspaces/r-host/task.md",
        idempotency_key=f"host-{status}-{claimed}-{datetime.now(timezone.utc).timestamp()}",
        execution_provider=provider,
        host_claimed_at=claimed,
        host_token_hash=svc._host_poll_token_hash(TOKEN) if claimed else None,
    )
    db_session.add(run)
    db_session.commit()
    return run


# ---------------------------------------------------------------------------
# fail-closed 闸（约束：生产启用闸不放宽）
# ---------------------------------------------------------------------------


def test_disabled_by_default_403(db_session, d4_settings):
    """默认关闭：三条面全部 403 host_poll_disabled。"""
    for fn, kwargs in (
        (svc.host_poll_status, {"presented_token": TOKEN}),
        (svc.claim_host_run, {"presented_token": TOKEN}),
        (svc.submit_host_receipt, {"presented_token": TOKEN, "run_id": "x", "payload": {"summary": {}}}),
    ):
        with pytest.raises(svc.AgentsServiceError) as ei:
            fn(**kwargs)
        assert ei.value.code == "host_poll_disabled" and ei.value.status == 403


def test_enabled_without_token_403(db_session, poll_settings, monkeypatch):
    """开关开但令牌为空 ⇒ 仍 403（半配置不裸奔）。"""
    import unittest.mock as mock

    broken = poll_settings.model_copy(update={"agent_host_poll_token": None})
    monkeypatch.setattr(svc, "_settings", lambda: broken)
    with pytest.raises(svc.AgentsServiceError) as ei:
        svc.claim_host_run(presented_token=TOKEN)
    assert ei.value.code == "host_poll_disabled"


def test_wrong_token_403(db_session, poll_settings):
    with pytest.raises(svc.AgentsServiceError) as ei:
        svc.claim_host_run(presented_token="wrong-token")
    assert ei.value.code == "host_poll_forbidden"


# ---------------------------------------------------------------------------
# 领取：FIFO / 状态迁移 / 幂等重领 / token 绑定
# ---------------------------------------------------------------------------


def test_claim_fifo_and_status_transition(db_session, poll_settings):
    r1 = _seed_host_run(db_session, poll_settings)
    r2 = _seed_host_run(db_session, poll_settings)
    out = svc.claim_host_run(presented_token=TOKEN)
    assert out["run_id"] in (r1.id, r2.id)
    assert "claimed_at" in out and "context_ref" in out
    assert out["claimed_at"] is not None
    db_session.expire_all()  # claim 在另一 session 提交
    row = db_session.get(AgentRun, out["run_id"])
    assert row.status == "host_running"
    assert row.execution_provider == "host_poll"
    assert row.host_token_hash == svc._host_poll_token_hash(TOKEN)
    # FIFO：早创建的先领
    assert out["run_id"] == r1.id


def test_claim_idempotent_same_token(db_session, poll_settings):
    run = _seed_host_run(db_session, poll_settings)
    first = svc.claim_host_run(presented_token=TOKEN)
    second = svc.claim_host_run(presented_token=TOKEN)
    assert first["run_id"] == second["run_id"] == run.id
    db_session.expire_all()  # claim 在另一 session 提交
    row = db_session.get(AgentRun, run.id)
    assert row.host_claimed_at is not None


def test_claim_conflict_after_token_rotation(db_session, poll_settings, monkeypatch):
    """服务端令牌轮换后，旧 hash 的 run 被新令牌续领 ⇒ host_claim_conflict。

    （真实冲突面：config 只有一个 token，异 token 在 _verify 就 403；hash 不
    匹配分支覆盖「token 轮换后旧代理续领」场景。）
    """
    from pydantic import SecretStr

    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)  # 旧 token 领取 → host_running + 旧 hash
    rotated = poll_settings.model_copy(update={"agent_host_poll_token": SecretStr("rotated-token")})
    monkeypatch.setattr(svc, "_settings", lambda: rotated)
    with pytest.raises(svc.AgentsServiceError) as ei:
        svc.claim_host_run(presented_token="rotated-token", run_id=run.id)
    assert ei.value.code == "host_claim_conflict"


def test_claim_empty_queue_404(db_session, poll_settings):
    with pytest.raises(svc.AgentsServiceError) as ei:
        svc.claim_host_run(presented_token=TOKEN)
    assert ei.value.status == 404


def test_claim_skips_sandbox_runs(db_session, poll_settings):
    """execution_provider=sandbox 的 run 不进宿主领取面（通道隔离）。"""
    _seed_host_run(db_session, poll_settings, provider="sandbox")
    with pytest.raises(svc.AgentsServiceError) as ei:
        svc.claim_host_run(presented_token=TOKEN)
    assert ei.value.status == 404


# ---------------------------------------------------------------------------
# 回执：终态对齐 / 产物指纹直录 / 幂等 / 令牌绑定
# ---------------------------------------------------------------------------


def _receipt_payload(*, exit_code=0, artifacts=None, status=None):
    payload = {
        "exit_code": exit_code,
        "summary": SUMMARY,
        "artifacts": artifacts or [],
    }
    if status:
        payload["status"] = status
    return payload


def test_receipt_completed_with_artifacts(db_session, poll_settings):
    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    arts = [
        {"path": "report.md", "kind": "doc", "source_refs": ["task-1"], "sha256": "a" * 64},
        {"path": "patch.diff", "kind": "diff", "source_refs": ["task-1"], "sha256": "b" * 64},
    ]
    out = svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload=_receipt_payload(artifacts=arts))
    assert out["status"] == "completed" and out["duplicate"] is False and out["failures"] == []
    db_session.expire_all()  # receipt 在另一 session 提交
    row = db_session.get(AgentRun, run.id)
    assert row.status == "completed"
    assert row.host_receipt_at is not None
    assert row.token_cost == 30  # billable_units：投影 totalTokenCount 优先
    arts_rows = db_session.scalars(select(AgentArtifact).where(AgentArtifact.run_id == run.id)).all()
    assert len(arts_rows) == 2
    assert all(a.storage_ref.startswith(f"host:{run.id}/") for a in arts_rows)
    assert all(a.sha256 in ("a" * 64, "b" * 64) for a in arts_rows)
    assert all(a.reviewed is False and a.linked_solution_id is None for a in arts_rows)
    assert all(a.derived_summary is None for a in arts_rows)  # 服务端无原件：诚实置空


def test_receipt_nonzero_exit_failed(db_session, poll_settings):
    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    out = svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload=_receipt_payload(exit_code=2))
    assert out["status"] == "failed"
    db_session.expire_all()
    assert db_session.get(AgentRun, run.id).status == "failed"


def test_receipt_host_timeout_kept(db_session, poll_settings):
    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    out = svc.submit_host_receipt(
        presented_token=TOKEN, run_id=run.id, payload=_receipt_payload(exit_code=0, status="timeout")
    )
    assert out["status"] == "timeout"
    db_session.expire_all()
    assert db_session.get(AgentRun, run.id).status == "timeout"


def test_receipt_idempotent_duplicate(db_session, poll_settings):
    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    first = svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload=_receipt_payload())
    second = svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload=_receipt_payload())
    assert first["duplicate"] is False and second["duplicate"] is True
    assert second["status"] == "completed"


def test_receipt_rejects_after_token_rotation(db_session, poll_settings, monkeypatch):
    """token 轮换后旧代理回执 ⇒ host_poll_forbidden（hash 分支可辨）。"""
    from pydantic import SecretStr

    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    rotated = poll_settings.model_copy(update={"agent_host_poll_token": SecretStr("rotated-token")})
    monkeypatch.setattr(svc, "_settings", lambda: rotated)
    with pytest.raises(svc.AgentsServiceError) as ei:
        svc.submit_host_receipt(presented_token="rotated-token", run_id=run.id, payload=_receipt_payload())
    assert ei.value.code == "host_poll_forbidden"


def test_receipt_rejects_wrong_token(db_session, poll_settings):
    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    with pytest.raises(svc.AgentsServiceError) as ei:
        svc.submit_host_receipt(presented_token="other", run_id=run.id, payload=_receipt_payload())
    assert ei.value.code == "host_poll_forbidden"


def test_receipt_rejects_unclaimed_run(db_session, poll_settings):
    """queued（未领取）run 的回执 ⇒ invalid_state（鉴权通过后状态闸）。"""
    run = _seed_host_run(db_session, poll_settings)  # 仍 queued，host_token_hash=None
    with pytest.raises(svc.AgentsServiceError) as ei:
        svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload=_receipt_payload())
    assert ei.value.code == "host_receipt_invalid_state"


def test_receipt_failure_details_not_fatal(db_session, poll_settings):
    """产物校验失败只记 failures 不改终态（H4：人工按明细处置）。"""
    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    arts = [
        {"path": "../evil.md", "kind": "doc", "source_refs": ["t"], "sha256": "a" * 64},  # unsafe_path
        {"path": "x.md", "kind": "doc", "source_refs": [], "sha256": "a" * 64},  # missing refs
        {"path": "y.md", "kind": "doc", "source_refs": ["t"], "sha256": "short"},  # sha256 缺失
    ]
    out = svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload=_receipt_payload(artifacts=arts))
    assert out["status"] == "completed"  # 终态不被校验失败劫持
    reasons = {r for item in out["failures"] for r in item["reasons"]}
    assert "unsafe_path" in reasons and "missing_source_refs" in reasons and "sha256_missing_in_receipt" in reasons


# ---------------------------------------------------------------------------
# goal-sprint r2 吸收钉（goal-crv QR-088 / QR-089 / QR-073）
# ---------------------------------------------------------------------------


def test_claim_run_id_revalidates_after_rival_commit(db_session, poll_settings):
    """QR-088：带 run_id 领取取行锁——rival 代理已提交领取（host_running+异
    token）时，后来者等锁后**重读最新状态**判 403 host_claim_conflict，绝不
    覆写劫持（无锁实现：快照停在 queued ⇒ 无条件赋值覆写 rival 的 token ⇒
    双代理同时执行同一 run）。"""
    rival_hash = svc._host_poll_token_hash("rival-proxy-token")
    run = _seed_host_run(db_session, poll_settings)
    holder = db_session.get_bind().connect()
    tx = holder.begin()
    # rival 领取（未提交）：模拟与后来者并发的另一代理
    holder.execute(
        text(
            "UPDATE agent_runs SET status = 'host_running', host_token_hash = :h,"
            " host_claimed_at = now() WHERE id = :id"
        ),
        {"h": rival_hash, "id": run.id},
    )
    outcome: dict = {}

    def claimer():
        # Flask-SQLAlchemy 的 scoped session 按线程取上下文——领取线程须自带
        # app context（主线程 fixture 的上下文不跨线程）。
        from fde_api.app import create_app

        with create_app(poll_settings).app_context():
            try:
                outcome["payload"] = svc.claim_host_run(presented_token=TOKEN, run_id=run.id)
            except Exception as error:  # noqa: BLE001 - 线程边界收集
                outcome["error"] = error

    worker = threading.Thread(target=claimer)
    worker.start()
    time.sleep(0.5)  # 让后来者先落到锁等待点（无锁实现则已拿到 queued 快照）
    tx.commit()  # rival 领取生效
    holder.close()
    worker.join(timeout=15)
    assert isinstance(outcome.get("error"), svc.AgentsServiceError), outcome
    assert outcome["error"].code == "host_claim_conflict"
    db_session.expire_all()
    row = db_session.get(AgentRun, run.id)
    assert row.status == "host_running"
    assert row.host_token_hash == rival_hash  # rival 所有权未被覆写


def test_claim_run_id_conflict_after_other_token_claim(db_session, poll_settings, monkeypatch):
    """QR-088 邻面：run_id 路径同样走「已领取 + 异 token ⇒ 403」判定
    （行锁等锁后按最新状态判定——不同时代理不抢别人手里的活）。"""
    from pydantic import SecretStr

    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)  # FIFO 领取（同 token）
    other = poll_settings.model_copy(update={"agent_host_poll_token": SecretStr("other-proxy-token")})
    monkeypatch.setattr(svc, "_settings", lambda: other)
    with pytest.raises(svc.AgentsServiceError) as ei:
        svc.claim_host_run(presented_token="other-proxy-token", run_id=run.id)
    assert ei.value.code == "host_claim_conflict"


def test_claim_payload_uses_frozen_tools_snapshot(db_session, poll_settings):
    """QR-089：领取载荷读发起时刻快照——发起后 registry 名单变更不进领取面。"""
    run = _seed_host_run(db_session, poll_settings)
    run.frozen_tools = ["fs_read", "code_search"]  # 模拟 start_run 发起时刻快照
    agent = db_session.get(AgentRegistry, run.agent_id)
    agent.allowed_tools = ["fs_read", "code_search", "http_post"]
    db_session.commit()
    payload = svc.claim_host_run(presented_token=TOKEN, run_id=run.id)
    assert payload["allowed_tools"] == ["fs_read", "code_search"]


def test_claim_payload_falls_back_to_registry_without_snapshot(db_session, poll_settings):
    """旧行兼容：frozen_tools NULL（迁移 c8e2a6f0b9d4 前落库）⇒ 回落 registry 读。"""
    run = _seed_host_run(db_session, poll_settings)
    assert run.frozen_tools is None
    payload = svc.claim_host_run(presented_token=TOKEN, run_id=run.id)
    agent = db_session.get(AgentRegistry, run.agent_id)
    assert payload["allowed_tools"] == list(agent.allowed_tools)


@pytest.mark.parametrize(
    "bad",
    ["D:\\abs\\secret.md", "C:/abs/x.md", "\\rooted.md", "a\\b.md", "D:\\test\\FDE\\truth.md"],
)
def test_receipt_windows_form_paths_never_register_rows(db_session, poll_settings, bad):
    """QR-073：盘符/反斜杠/根锚三形态 = unsafe_path——failures 留痕且零产物行
    （宿主自报 path 是不可信面，防任意宿主文件伪装产物污染证据链）。"""
    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    arts = [{"path": bad, "kind": "doc", "source_refs": ["t"], "sha256": "a" * 64}]
    out = svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload=_receipt_payload(artifacts=arts))
    assert out["status"] == "completed"
    assert any("unsafe_path" in item["reasons"] for item in out["failures"])
    db_session.expire_all()
    assert db_session.scalars(select(AgentArtifact).where(AgentArtifact.run_id == run.id)).all() == []


def test_start_run_persists_frozen_tools_snapshot(db_session, poll_settings):
    """QR-089 上游半边：host_poll 受理（202）时发起时刻三重交集快照落 run 行。"""
    import uuid as _uuid

    from fde_api.app import create_app
    from test_agents_d4_harness import ApiClient, issue_access_token, make_user, seed_agent
    from test_document_drafts_api import _persist_project

    app = create_app(poll_settings)
    app.config.update(TESTING=True)
    user = make_user(db_session, "project_lead")
    token = issue_access_token(user, poll_settings)
    client = ApiClient(app.test_client(), user, {"Authorization": f"Bearer {token}"})
    project = _persist_project(db_session, user, code=f"FT{_uuid.uuid4().hex[:6].upper()}")
    agent = seed_agent(db_session, poll_settings)
    body = client.post(
        f"/api/v1/agents/{agent.id}/run",
        json={"project_id": project.id, "idempotency_key": f"ft-{_uuid.uuid4().hex[:8]}"},
    )
    assert body.status_code == 202, body.json
    assert body.json["data"]["execution_provider"] == "host_poll"
    db_session.expire_all()
    row = db_session.scalar(select(AgentRun).where(AgentRun.project_id == project.id))
    assert row is not None and row.status == "queued"
    assert row.frozen_tools is not None and len(row.frozen_tools) >= 1


# ---------------------------------------------------------------------------
# H4：失联只标记
# ---------------------------------------------------------------------------


def test_mark_host_lost_only_marks(db_session, poll_settings):
    old = datetime.now(timezone.utc) - timedelta(minutes=45)
    run = _seed_host_run(db_session, poll_settings, status="host_running", claimed=old)
    out = svc.mark_host_lost()
    assert out["count"] == 1 and out["marked"] == [run.id]
    db_session.expire_all()  # mark 在另一 session 提交——过期本 session 旧快照
    row = db_session.get(AgentRun, run.id)
    assert row.host_lost_at is not None
    assert row.status == "host_running"  # 不迁移状态（H4）
    # 幂等：再扫不重打
    assert svc.mark_host_lost()["count"] == 0


def test_mark_host_lost_young_run_skipped(db_session, poll_settings):
    fresh = datetime.now(timezone.utc) - timedelta(minutes=5)
    _seed_host_run(db_session, poll_settings, status="host_running", claimed=fresh)
    assert svc.mark_host_lost()["count"] == 0


# ---------------------------------------------------------------------------
# HTTP 面烟测（路由→service 接线 + 错误投影）
# ---------------------------------------------------------------------------


def test_host_routes_http_smoke(db_session, poll_settings, d4_settings, monkeypatch):
    from fde_api.app import create_app

    app = create_app(poll_settings)
    app.config.update(TESTING=True)
    client = app.test_client()
    headers = {"X-Host-Poll-Token": TOKEN}

    # 关闭态 → 403（注意：poll_settings fixture 的 svc._settings monkeypatch
    # 在本测试内仍生效——off_app 的路由面走真实 create_app settings，但其
    # service 内部 _settings 被 patch ⇒ 先还原再测关闭态）
    monkeypatch.setattr(svc, "_settings", lambda: d4_settings)
    off_app = create_app(d4_settings)
    off_app.config.update(TESTING=True)
    assert off_app.test_client().get("/api/v1/agents/host/status", headers=headers).status_code == 403
    assert off_app.test_client().get("/api/v1/agents/host/status").status_code == 403  # 无头

    # 开启态：status→claim→receipt 全链（恢复 poll settings 注入）
    monkeypatch.setattr(svc, "_settings", lambda: poll_settings)
    run = _seed_host_run(db_session, poll_settings)
    body = client.get("/api/v1/agents/host/status", headers=headers)
    assert body.status_code == 200 and body.json["data"]["pending"] == 1
    body = client.post("/api/v1/agents/host/claim", headers=headers, json={})
    assert body.status_code == 200 and body.json["data"]["run_id"] == run.id
    body = client.post(
        f"/api/v1/agents/host/runs/{run.id}/receipt",
        headers=headers,
        json=_receipt_payload(artifacts=[{"path": "o.md", "kind": "doc", "source_refs": ["t"], "sha256": "a" * 64}]),
    )
    assert body.status_code == 200 and body.json["data"]["status"] == "completed"
    # 错误投影：坏令牌
    body = client.get("/api/v1/agents/host/status", headers={"X-Host-Poll-Token": "bad"})
    assert body.status_code == 403 and body.json["error"]["code"] == "host_poll_forbidden"


# ---------------------------------------------------------------------------
# QR-095（goal-crv r5 发现，goal-sprint r3 吸收）：exit_code 缺省不再
# 「缺省即成功」——completed 必须 int 0 支撑，缺失/非零一律 fail-closed。
# ---------------------------------------------------------------------------


def test_receipt_missing_exit_code_lands_failed(db_session, poll_settings):
    """缺 exit_code 缺 status ⇒ failed（原缺省按 0＝缺省即成功，QR-095 收口）。"""
    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    out = svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload={"summary": SUMMARY, "artifacts": []})
    assert out["status"] == "failed"
    db_session.expire_all()
    assert db_session.get(AgentRun, run.id).status == "failed"


def test_receipt_completed_without_zero_exit_downgraded(db_session, poll_settings):
    """显式 completed 但无 int 0 支撑 ⇒ 降 failed（宿主自报载荷不可信面）。"""
    run = _seed_host_run(db_session, poll_settings)
    svc.claim_host_run(presented_token=TOKEN)
    out = svc.submit_host_receipt(
        presented_token=TOKEN, run_id=run.id, payload=_receipt_payload(exit_code=2, status="completed")
    )
    assert out["status"] == "failed"
    db_session.expire_all()
    assert db_session.get(AgentRun, run.id).status == "failed"


# ---------------------------------------------------------------------------
# 任务书面料读取面（goal-sprint r3：host_context——宿主代理 spawn 前取
# 服务端已渲染的三件；渲染一次、消费两侧）
# ---------------------------------------------------------------------------


def _write_server_workspace(db_session, settings, run, *, with_files=True):
    """服务端侧工作区落盘（模拟 _write_workspace 渲染产物）＋指针对齐。"""
    root = Path(settings.agent_workspace_root)
    run_dir = root / "org-x" / run.id
    (run_dir / "output").mkdir(parents=True, exist_ok=True)
    if with_files:
        (run_dir / "context.md").write_text("CTX-BODY", encoding="utf-8")
        (run_dir / "task.md").write_text("TASK-BODY", encoding="utf-8")
        (run_dir / "AGENTS.md").write_text("AGENTS-BODY", encoding="utf-8")
    prefix = f"{Path(settings.agent_workspace_root).as_posix().strip('/')}/"
    run.context_ref = f"{prefix}org-x/{run.id}/context.md"
    db_session.commit()
    return run_dir


def test_context_returns_rendered_files(db_session, poll_settings):
    from fde_api.agents.host_context import fetch_host_run_context

    run = _seed_host_run(db_session, poll_settings)
    _write_server_workspace(db_session, poll_settings, run)
    svc.claim_host_run(presented_token=TOKEN)
    out = fetch_host_run_context(presented_token=TOKEN, run_id=run.id)
    assert out["files"] == {"context.md": "CTX-BODY", "task.md": "TASK-BODY", "AGENTS.md": "AGENTS-BODY"}


def test_context_missing_files_return_empty_strings(db_session, poll_settings):
    """面料缺席返回空串（形状恒定，宿主侧不猜、不 spawn 缺任务书的 run）。"""
    from fde_api.agents.host_context import fetch_host_run_context

    run = _seed_host_run(db_session, poll_settings)
    _write_server_workspace(db_session, poll_settings, run, with_files=False)
    svc.claim_host_run(presented_token=TOKEN)
    out = fetch_host_run_context(presented_token=TOKEN, run_id=run.id)
    assert out["files"] == {"context.md": "", "task.md": "", "AGENTS.md": ""}


def test_context_gates_on_claim_and_token(db_session, poll_settings):
    """状态闸族：未领取 409／他 token 403／已回执 409（信息最小暴露同回执面）。"""
    from fde_api.agents.host_context import fetch_host_run_context

    run = _seed_host_run(db_session, poll_settings)
    _write_server_workspace(db_session, poll_settings, run)
    with pytest.raises(svc.AgentsServiceError) as ei:
        fetch_host_run_context(presented_token=TOKEN, run_id=run.id)
    assert ei.value.status == 409
    svc.claim_host_run(presented_token=TOKEN)
    with pytest.raises(svc.AgentsServiceError) as ei:
        fetch_host_run_context(presented_token="other-token", run_id=run.id)
    assert ei.value.status == 403
    svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload=_receipt_payload())
    with pytest.raises(svc.AgentsServiceError) as ei:
        fetch_host_run_context(presented_token=TOKEN, run_id=run.id)
    assert ei.value.status == 409


def test_context_gates_on_claim_binding_after_token_rotation(db_session, poll_settings, monkeypatch):
    """领取绑定闸（轮换可判）：配置侧令牌轮换后，新令牌合法但非领取者 ⇒ 403。

    单令牌常态下该绑定检查与入口校验重合；轮换场景才可判别——旧领取者
    持有的 run，新令牌（对当前配置合法）读面料必须按领取绑定拒绝。
    """
    from fde_api.agents.host_context import fetch_host_run_context

    run = _seed_host_run(db_session, poll_settings)
    _write_server_workspace(db_session, poll_settings, run)
    svc.claim_host_run(presented_token=TOKEN)
    rotated = poll_settings.model_copy(
        update={"agent_host_poll_token": SecretStr("rotated-token-0123456789abc")}
    )
    monkeypatch.setattr(svc, "_settings", lambda: rotated)
    with pytest.raises(svc.AgentsServiceError) as ei:
        fetch_host_run_context(presented_token="rotated-token-0123456789abc", run_id=run.id)
    assert ei.value.status == 403 and ei.value.code == "host_poll_forbidden"


def test_context_rejects_non_host_poll_run(db_session, poll_settings):
    from fde_api.agents.host_context import fetch_host_run_context

    run = _seed_host_run(db_session, poll_settings, provider="sandbox")
    _write_server_workspace(db_session, poll_settings, run)
    with pytest.raises(svc.AgentsServiceError) as ei:
        fetch_host_run_context(presented_token=TOKEN, run_id=run.id)
    assert ei.value.code == "host_context_rejected"


def test_context_route_http_wiring(db_session, poll_settings):
    """路由→模块接线烟测（第四条宿主面路由；200 投影形状）。"""
    from fde_api.app import create_app

    app = create_app(poll_settings)
    app.config.update(TESTING=True)
    client = app.test_client()
    headers = {"X-Host-Poll-Token": TOKEN}
    run = _seed_host_run(db_session, poll_settings)
    _write_server_workspace(db_session, poll_settings, run)
    svc.claim_host_run(presented_token=TOKEN)
    body = client.get(f"/api/v1/agents/host/runs/{run.id}/context", headers=headers)
    assert body.status_code == 200
    assert body.json["data"]["files"]["task.md"] == "TASK-BODY"
    # 无头 403
    assert client.get(f"/api/v1/agents/host/runs/{run.id}/context").status_code == 403
