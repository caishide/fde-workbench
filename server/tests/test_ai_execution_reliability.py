"""E8 AI 执行可靠性回归钉。

- start_execution 不再启动 daemon 线程，而是落 outbox → BackgroundJob
  （进程重启任务不丢）
- worker 消费：run_job 驱动执行并把 Redis 状态推到终态
- 重复投递/重放：终态执行幂等跳过，不产生重复副作用（操作只跑一次）
"""
import json
from unittest.mock import patch

from fde_api.ai.executions import (
    OPERATIONS,
    execute_ai_execution_job,
    get_execution,
    start_execution,
)
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.jobs.handlers import ensure_default_handlers
from fde_api.jobs.models import BackgroundJob, OutboxEvent
from fde_api.jobs.outbox import dispatch_pending
from fde_api.jobs.worker import run_job
from sqlalchemy import select


def _ensure_handlers():
    """测试进程里显式注册默认 handler；失败要让断言看见而不是静默。"""
    ensure_default_handlers()


def _actor(db_session) -> User:
    user = User(
        username="ai.exec.retry",
        display_name="AI 执行",
        role="admin",
        password_hash=hash_password("InitialPass!234"),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def test_start_execution_persists_job_without_daemon_thread(
    db_session, app, client, monkeypatch
):
    """任务落 outbox/BackgroundJob；进程中不再出现执行线程。"""
    import threading

    actor = _actor(db_session)
    started = patch.dict(OPERATIONS, {})
    started.start()
    try:
        state = start_execution(
            actor=actor,
            operation="industry_template_chat",
            payload={"messages": [{"role": "user", "content": "问题"}]},
        )
    finally:
        started.stop()

    assert state["status"] == "running"

    # outbox 事件已持久化（worker 重启后仍可派发）
    events = db_session.scalars(
        select(OutboxEvent).where(OutboxEvent.topic == "ai.execute")
    ).all()
    assert len(events) == 1

    # 进程里没有以 ai-execution 命名的线程（不再依赖 daemon 线程）
    assert not [t for t in threading.enumerate() if t.name.startswith("ai-execution-")]


def test_worker_consumes_job_and_reaches_terminal_state(db_session, app, client):
    _ensure_handlers()
    actor = _actor(db_session)
    state = start_execution(
        actor=actor,
        operation="industry_template_chat",
        payload={"messages": [{"role": "user", "content": "问题"}]},
    )
    execution_id = state["id"]

    calls = {"count": 0}
    result_payload = {"reply": "回答", "version": 1}

    def fake_operation(*, actor, payload, on_event):
        calls["count"] += 1
        on_event({"type": "stage_changed", "text": "fake 阶段"})
        return result_payload

    monkeypatched = patch.dict(OPERATIONS, {"industry_template_chat": (fake_operation, OPERATIONS["industry_template_chat"][1])})
    monkeypatched.start()
    try:
        # 派发 outbox → BackgroundJob（测试内直接驱动 dispatch）
        with app.app_context():
            from fde_api.extensions import db as app_db

            session = app_db.session()
            try:
                class _Queue:
                    def __init__(self):
                        self.ids = []

                    def enqueue(self, job_id):
                        self.ids.append(job_id)

                queue = _Queue()
                dispatch_pending(session, queue, limit=10)
            finally:
                session.close()
        assert queue.ids, "outbox event must create a background job"

        job = db_session.scalar(
            select(BackgroundJob).where(
                BackgroundJob.job_type == "ai.execute",
                BackgroundJob.target_id == execution_id,
            )
        )
        assert job is not None

        outcome = run_job(job.id)
        assert outcome == "succeeded"
        db_session.refresh(job)
        assert job.status == "succeeded"

        final = get_execution(
            actor=actor, execution_id=execution_id, after=0
        )
        assert final["status"] == "completed"
        assert final["result"] == result_payload
    finally:
        monkeypatched.stop()

    # worker 级重放：终态任务再跑一次是 no-op
    assert run_job(job.id) == "already_terminal"
    assert calls["count"] == 1


def test_redelivered_execution_does_not_repeat_side_effects(
    db_session, app, client
):
    """重复投递：状态已是终态时 handler 直接跳过（操作只执行一次）。"""
    actor = _actor(db_session)
    state = start_execution(
        actor=actor,
        operation="industry_template_chat",
        payload={"messages": [{"role": "user", "content": "问题"}]},
    )
    execution_id = state["id"]

    calls = {"count": 0}

    def fake_operation(*, actor, payload, on_event):
        calls["count"] += 1
        return {"reply": "第一次"}

    saved = OPERATIONS["industry_template_chat"]
    OPERATIONS["industry_template_chat"] = (fake_operation, saved[1])
    try:
        job = BackgroundJob(
            job_type="ai.execute", target_id=execution_id, status="queued"
        )
        db_session.add(job)
        db_session.commit()

        # worker 实际由 app 上下文驱动；这里模拟其调用方式
        with app.app_context():
            execute_ai_execution_job(job)
        assert calls["count"] == 1

        # 模拟重复投递（同一 job 再消费一次）：终态 → 跳过
        with app.app_context():
            execute_ai_execution_job(job)
        assert calls["count"] == 1

        final = get_execution(actor=actor, execution_id=execution_id, after=0)
        assert final["status"] == "completed"
    finally:
        OPERATIONS["industry_template_chat"] = saved
