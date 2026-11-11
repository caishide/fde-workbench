"""多客户 M4 批次 C：队列 job 主体标签（任务书 §7-M4「job 携带主体标签用于计量」）。

钉面：
- **全链钉**：入队调用点显式声明（``enqueue_outbox`` keyword-only 必填＝机械
  闸）→ ``outbox_events.subject_org`` → dispatch 单点复制 →
  ``background_jobs.org_id``。企业身份发起 ⇒ 企业 org；平台身份 ⇒ ``None``
  （平台级，与 org 平台身份语义同构）。
- **计量读面**：``GET /admin/jobs/metering``（admin 只读；非 admin 403）——
  按 org 分组 active/terminal 计数＋平台级单列。
- **静态钉**：全仓 ``enqueue_outbox(`` 调用点必须显式携带 ``subject_org=``；
  dispatch 必须传 ``event.subject_org``（防新调用点绕过主体声明）。
- **迁移**：``e9b4f7c2a8d3`` additive（两列＋一索引）；存量行 NULL=平台级
  （零回填——推断不伪装成事实）。
变异验收：M1 dispatch 摘复制（传 None）⇒ 全链钉红；M2 摘计量分组 ⇒ 读面红。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import inspect, select

from conftest import INITIAL_PASSWORD
from fde_api.ai.executions import start_execution
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.jobs.models import BackgroundJob, OutboxEvent
from fde_api.jobs.outbox import dispatch_pending, subject_org_of_project
from multi_tenant_harness import make_enterprise_org, make_user


def _dispatch(app):
    from fde_api.extensions import db as app_db

    class _Queue:
        def __init__(self):
            self.ids = []

        def enqueue(self, job_id):
            self.ids.append(job_id)

    queue = _Queue()
    with app.app_context():
        session = app_db.session()
        try:
            dispatch_pending(session, queue, limit=10)
        finally:
            session.close()
    return queue


def test_full_chain_enterprise_actor_labels_job(db_session, app):
    """企业身份发起 ai.execute ⇒ outbox.subject_org ＝ job.org_id ＝ 企业 org。"""
    org = make_enterprise_org(db_session)
    actor = make_user(db_session, role="admin", org_id=org.id)
    with app.app_context():
        started = start_execution(
            actor=actor,
            operation="project_ai_opportunities_discover",
            payload={"project_id": str(uuid4())},
        )
    event = db_session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.topic == "ai.execute",
            OutboxEvent.aggregate_id == started["id"],
        )
    )
    assert event is not None
    assert event.subject_org == org.id
    queue = _dispatch(app)
    assert queue.ids, "outbox event must create a background job"
    job = db_session.scalar(
        select(BackgroundJob).where(
            BackgroundJob.job_type == "ai.execute",
            BackgroundJob.target_id == started["id"],
        )
    )
    assert job is not None
    assert job.org_id == org.id  # dispatch 单点复制（M1 变异打这里）


def test_full_chain_platform_actor_is_platform_level(db_session, app):
    """平台身份（org_id=NULL）⇒ 标签 None＝平台级（不编造归属）。"""
    actor = make_user(db_session, role="admin", org_id=None)
    with app.app_context():
        started = start_execution(
            actor=actor,
            operation="project_ai_opportunities_discover",
            payload={"project_id": str(uuid4())},
        )
    event = db_session.scalar(
        select(OutboxEvent).where(OutboxEvent.aggregate_id == started["id"])
    )
    assert event.subject_org is None
    _dispatch(app)
    job = db_session.scalar(
        select(BackgroundJob).where(BackgroundJob.target_id == started["id"])
    )
    assert job.org_id is None


def test_subject_org_of_project_resolves_and_falls_back(db_session):
    """helper：项目归属解析；项目不存在/无归属 ⇒ None（平台级兜底）。"""
    org = make_enterprise_org(db_session)
    leader = make_user(db_session, role="admin", org_id=org.id)
    from test_ai_server_chat_mcp import make_project

    project = make_project(db_session, leader)
    project.org_id = org.id
    db_session.commit()
    assert subject_org_of_project(db_session, project.id) == org.id
    assert subject_org_of_project(db_session, "no-such-project") is None
    assert subject_org_of_project(db_session, None) is None


def test_metering_face_admin_gate_and_groups(client, db_session, app):
    """计量读面：非 admin 403；admin 读到平台级组＋企业组＋queue_depth。"""
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)

    # 直接落三行 job：企业甲 active、企业甲 terminal、平台级 active。
    db_session.add_all(
        [
            BackgroundJob(
                job_type="file.preview", target_id=str(uuid4()), status="pending", org_id=org_a.id
            ),
            BackgroundJob(
                job_type="file.preview", target_id=str(uuid4()), status="succeeded", org_id=org_a.id
            ),
            BackgroundJob(
                job_type="dispatch.maintenance", target_id=f"daily-{uuid4().hex[:8]}", status="pending", org_id=None
            ),
        ]
    )
    db_session.commit()

    from datetime import UTC, datetime

    from fde_api.auth.service import issue_access_token

    admin = User(
        username=f"m4c-admin-{uuid4().hex[:8]}",
        display_name="M4C admin",
        role="admin",
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    viewer = User(
        username=f"m4c-viewer-{uuid4().hex[:8]}",
        display_name="M4C viewer",
        role="viewer",
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    db_session.add_all([admin, viewer])
    db_session.commit()

    with app.app_context():
        settings = app.config["SETTINGS"]
        admin_headers = {"Authorization": "Bearer " + issue_access_token(admin, settings)}
        viewer_headers = {"Authorization": "Bearer " + issue_access_token(viewer, settings)}

        denied = client.get("/api/v1/admin/jobs/metering", headers=viewer_headers)
        assert denied.status_code == 403
        assert denied.get_json()["error"]["code"] == "job_metering_forbidden"

        ok = client.get("/api/v1/admin/jobs/metering", headers=admin_headers)
        assert ok.status_code == 200
        data = ok.get_json()["data"]

    groups = {g["org_id"]: g for g in data["groups"]}
    assert groups[org_a.id] == {"org_id": org_a.id, "active": 1, "terminal": 1}
    assert groups[None] == {"org_id": None, "active": 1, "terminal": 0}
    assert org_b.id not in groups  # 无 job 的 org 不出现（零编造）
    assert isinstance(data["queue_depth"], int)


def test_enqueue_call_sites_all_declare_subject_org():
    """静态钉：全仓 ``enqueue_outbox(`` 调用点必须显式携带 ``subject_org=``；
    dispatch 必须传 ``event.subject_org``。"""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "fde_api"
    offenders: list[str] = []
    for path in src.rglob("*.py"):
        rel = path.relative_to(src).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel == "jobs/outbox.py":
            # 权威模块：dispatch 必须复制事件主体
            assert "subject_org=event.subject_org" in text, "dispatch 必须传 event.subject_org"
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            if "enqueue_outbox(" not in line or line.strip().startswith("#"):
                continue
            # 调用点（含跨行调用）：从该行向后找到闭括号，窗口内必须显式声明
            window = "\n".join(lines[idx : idx + 12])
            if "subject_org=" not in window:
                offenders.append(f"{rel}:{idx + 1}")
    assert offenders == [], "enqueue_outbox 调用点未显式声明 subject_org：\n" + "\n".join(offenders)


def test_queue_subject_migration_columns(db_session):
    """``e9b4f7c2a8d3`` additive：两列＋一索引在场。"""
    engine = db_session.get_bind()
    inspector = inspect(engine)
    outbox_cols = {c["name"] for c in inspector.get_columns("outbox_events")}
    job_cols = {c["name"] for c in inspector.get_columns("background_jobs")}
    assert "subject_org" in outbox_cols
    assert "org_id" in job_cols
    job_indexes = {ix["name"] for ix in inspector.get_indexes("background_jobs")}
    assert "ix_background_jobs_org_id" in job_indexes
