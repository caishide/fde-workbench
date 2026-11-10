"""夜审修复 r5 迁移窗口：幂等唯一窗口＋单点现行唯一＋run_id FK 索引。

CR-045/048/053/059（拍板 2026-11-10：授权迁移窗口一次做，留痕可推翻）。
结构面＝迁移 ``a9c5e2d7b3f1`` 五索引；本文件钉：

- 五索引在 head 库真实存在且部分谓词形状正确（pg_indexes 现测）；
- CR-045 并发同键 start：预检查后的竞态窗口由部分唯一索引兜底——
  败者重读在途行按幂等语义 200 返回（CR-052 同款真实竞态复现法）；
- CR-048 产物 (run, storage_ref) 唯一＋回执写事务行锁重校验（TOCTOU 收口）；
- CR-053 单项目现行 published/approved 至多一份（违反即 IntegrityError）。
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from fde_api.agents import service as svc
from fde_api.agents.models import AgentArtifact, AgentRun
from fde_api.plans.models import DeliveryPlan
from fde_api.quality.models import TestPlan

from test_agents_d4_harness import (  # noqa: F401  (pytest fixtures)
    d4_app,
    d4_client,
    d4_settings,
)
from test_agents_d4_harness import api_client, seed_agent
from test_document_drafts_api import _persist_project
from test_host_poll import TOKEN, _receipt_payload, _seed_host_run  # noqa: F401
from test_host_poll import poll_settings  # noqa: F401  (pytest fixture)

WINDOW_INDEXES = (
    "uq_agent_runs_idempotency_active",
    "uq_agent_artifacts_run_storage_ref",
    "uq_delivery_plans_project_published",
    "uq_test_plans_project_approved",
    "ix_agent_tool_calls_run",
)


# ---------------------------------------------------------------------------
# 结构面：head 库五索引形状（pg_indexes 现测，含部分谓词）
# ---------------------------------------------------------------------------


def test_uniqueness_window_indexes_exist_with_predicates(db_session) -> None:
    rows = db_session.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE indexname = ANY(CAST(:names AS text[]))"
        ),
        {"names": list(WINDOW_INDEXES)},
    ).all()
    defs = dict(rows)
    missing = [n for n in WINDOW_INDEXES if n not in defs]
    assert not missing, f"r5 窗口索引缺失于 head 库：{missing}"
    # 部分谓词形状（唯一窗口只锁现行态，不封重试链/历史行）
    assert "queued" in defs["uq_agent_runs_idempotency_active"]
    assert "host_running" in defs["uq_agent_runs_idempotency_active"]
    assert "WHERE" in defs["uq_agent_runs_idempotency_active"]
    assert "WHERE" in defs["uq_delivery_plans_project_published"]
    assert "published" in defs["uq_delivery_plans_project_published"]
    assert "WHERE" in defs["uq_test_plans_project_approved"]
    assert "approved" in defs["uq_test_plans_project_approved"]
    # 产物唯一为复合 (run_id, storage_ref)——前导 run_id 兼作详情页查询
    assert "(run_id, storage_ref)" in defs["uq_agent_artifacts_run_storage_ref"]
    # 工具调用 FK 索引为普通非唯一
    assert "UNIQUE" not in defs["ix_agent_tool_calls_run"].upper() or "CREATE INDEX" in defs[
        "ix_agent_tool_calls_run"
    ].upper()


def test_idempotency_violation_classifier() -> None:
    """非目标约束的 IntegrityError 原样上抛（不吞）——分类器两态。"""
    from fde_api.agents.service import _is_idempotency_active_violation

    class _Diag:
        constraint_name = "uq_agent_runs_idempotency_active"

    class _Orig(BaseException):
        diag = _Diag()

    assert _is_idempotency_active_violation(IntegrityError("s", {}, _Orig())) is True

    class _OtherDiag:
        constraint_name = "some_other_constraint"

    class _OtherOrig(BaseException):
        diag = _OtherDiag()

    assert _is_idempotency_active_violation(IntegrityError("s", {}, _OtherOrig())) is False
    # 无 diag 形态（SQLite 垫等）：退回文本匹配
    assert (
        _is_idempotency_active_violation(
            IntegrityError("uq_agent_runs_idempotency_active ...", {}, Exception())
        )
        is True
    )
    assert _is_idempotency_active_violation(IntegrityError("nope", {}, Exception())) is False


# ---------------------------------------------------------------------------
# CR-045：并发同键 start 的竞态窗口兜底（真实唯一约束复现）
# ---------------------------------------------------------------------------


def test_concurrent_same_key_start_returns_existing_run(
    db_session, d4_client, d4_settings, monkeypatch
) -> None:
    """预检查通过后、flush 前，独立连接抢插同键 in-flight run（模拟 READ
    COMMITTED 下先行提交的并发事务）→ 真实 INSERT 撞部分唯一索引 → 兜底
    重读在途行按幂等语义 200 返回（双执行双计费结构不可能）。"""
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code="R45A")
    agent = seed_agent(db_session, d4_settings)
    key = "r45:race-key"

    rival_id = "r45-rival-" + "0" * 12
    original_flush = OrmSession.flush
    raced = {"done": False}

    def racing_flush(self, *args, **kwargs):
        if not raced["done"] and self.new and any(isinstance(o, AgentRun) for o in self.new):
            raced["done"] = True
            OrmSession.flush = original_flush  # 只劫持一次
            with db_session.get_bind().begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO agent_runs (id, project_id, agent_id, initiated_by_user_id, "
                        "capability_used, status, context_ref, idempotency_key, cost_owner_type, "
                        "created_at, updated_at) VALUES ("
                        ":id, :pid, :aid, :uid, :cap, 'queued', :ref, :key, 'project', now(), now())"
                    ),
                    {
                        "id": rival_id,
                        "pid": project.id,
                        "aid": agent.id,
                        "uid": leader.user.id,
                        "cap": agent.capability_tier,
                        "ref": "agent-workspaces/r45-rival/task.md",
                        "key": key,
                    },
                )
        return original_flush(self, *args, **kwargs)

    monkeypatch.setattr(OrmSession, "flush", racing_flush)
    body = leader.post(
        f"/api/v1/agents/{agent.id}/run",
        json={"project_id": project.id, "idempotency_key": key},
    )
    assert body.status_code == 200, body.get_data(as_text=True)
    data = body.get_json()["data"]
    assert data["id"] == rival_id, "败者必须幂等复用先行提交的在途 run"
    # 同键 in-flight 行恰一条（败者未落第二行）
    inflight = db_session.scalars(
        select(AgentRun).where(
            AgentRun.idempotency_key == key,
            AgentRun.status.in_(("queued", "running", "host_running")),
        )
    ).all()
    assert len(inflight) == 1 and inflight[0].id == rival_id


# ---------------------------------------------------------------------------
# CR-048：产物唯一 ＋ 回执写事务行锁重校验
# ---------------------------------------------------------------------------


def test_agent_artifact_run_storage_ref_unique(db_session, d4_settings) -> None:
    run = _seed_host_run(db_session, d4_settings, claimed=datetime.now(UTC))
    db_session.add(
        AgentArtifact(
            run_id=run.id, kind="doc", storage_ref=f"host:{run.id}/output/report.md", sha256="a" * 64
        )
    )
    db_session.commit()
    db_session.add(
        AgentArtifact(
            run_id=run.id, kind="doc", storage_ref=f"host:{run.id}/output/report.md", sha256="b" * 64
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_receipt_write_txn_recheck_returns_duplicate(
    db_session, poll_settings, monkeypatch
) -> None:
    """CR-048 TOCTOU 收口：读闸通过后、写事务取行前，并发回执先行落终态
    ⇒ 写事务行锁重读后如实 duplicate=True，不再二次落产物。"""
    run = _seed_host_run(db_session, poll_settings, claimed=datetime.now(UTC))
    svc.claim_host_run(presented_token=TOKEN)

    original_get = OrmSession.get
    gets = {"n": 0}

    def racing_get(self, entity, ident, *args, **kwargs):
        if entity is AgentRun and ident == run.id:
            gets["n"] += 1
            if gets["n"] == 2:
                # 第二次取行＝写事务行锁重读；此刻并发胜者已先行提交终态。
                with db_session.get_bind().begin() as conn:
                    conn.execute(
                        text(
                            "UPDATE agent_runs SET status = 'completed', host_receipt_at = now() "
                            "WHERE id = :rid"
                        ),
                        {"rid": run.id},
                    )
        return original_get(self, entity, ident, *args, **kwargs)

    monkeypatch.setattr(OrmSession, "get", racing_get)
    out = svc.submit_host_receipt(
        presented_token=TOKEN,
        run_id=run.id,
        payload=_receipt_payload(artifacts=[
            {"path": "report.md", "kind": "doc", "source_refs": ["t-1"], "sha256": "a" * 64},
        ]),
    )
    assert out["duplicate"] is True, "写事务重校验必须识别先行终态（败者如实 duplicate）"
    db_session.expire_all()
    rows = db_session.scalars(select(AgentArtifact).where(AgentArtifact.run_id == run.id)).all()
    assert len(rows) == 0, "重校验命中后败者不得再落产物行"


def test_receipt_write_get_takes_row_lock(db_session, poll_settings, monkeypatch) -> None:
    """CR-048：写事务取行必须 with_for_update=True（读闸一次、写事务行锁重读
    一次——锁缺失时并发回执窗口重新敞开）。"""
    run = _seed_host_run(db_session, poll_settings, claimed=datetime.now(UTC))
    svc.claim_host_run(presented_token=TOKEN)
    original_get = OrmSession.get
    seen: list[bool] = []

    def spy_get(self, entity, ident, *args, **kwargs):
        if entity is AgentRun and ident == run.id:
            seen.append(bool(kwargs.get("with_for_update")))
        return original_get(self, entity, ident, *args, **kwargs)

    monkeypatch.setattr(OrmSession, "get", spy_get)
    out = svc.submit_host_receipt(presented_token=TOKEN, run_id=run.id, payload=_receipt_payload())
    assert out["status"] == "completed"
    assert seen == [False, True], f"回执取行形态必须为 读闸无锁/写事务行锁，实测 {seen}"


# ---------------------------------------------------------------------------
# CR-053：单项目现行 published/approved 至多一份
# ---------------------------------------------------------------------------


def test_delivery_plan_second_published_rejected(db_session, d4_settings) -> None:
    user = api_client(d4_client, db_session, d4_settings, "project_lead").user
    project = _persist_project(db_session, user, code="R53A")
    now = datetime.now(UTC)
    db_session.add(
        DeliveryPlan(
            project_id=project.id, created_by_user_id=user.id, title="方案一",
            status="published", version=1,
            reviewed_by_user_id=user.id, reviewed_at=now,
            published_by_user_id=user.id, published_at=now,
        )
    )
    db_session.commit()
    db_session.add(
        DeliveryPlan(
            project_id=project.id, created_by_user_id=user.id, title="方案二",
            status="published", version=1,
            reviewed_by_user_id=user.id, reviewed_at=now,
            published_by_user_id=user.id, published_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_test_plan_second_approved_rejected(db_session, d4_settings) -> None:
    user = api_client(d4_client, db_session, d4_settings, "project_lead").user
    project = _persist_project(db_session, user, code="R53B")
    now = datetime.now(UTC)
    db_session.add(
        TestPlan(
            project_id=project.id, created_by_user_id=user.id, title="计划一",
            status="approved", version=1,
            reviewed_by_user_id=user.id, reviewed_at=now,
        )
    )
    db_session.commit()
    db_session.add(
        TestPlan(
            project_id=project.id, created_by_user_id=user.id, title="计划二",
            status="approved", version=1,
            reviewed_by_user_id=user.id, reviewed_at=now,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
