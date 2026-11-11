"""Transactional outbox: enqueue change events in the business transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from fde_api.jobs.models import OutboxEvent


def utcnow() -> datetime:
    return datetime.now(UTC)


# MySQL DATETIME stores second precision and rounds fractional seconds up, so a
# freshly created event can carry an available_at one second in the future.
# Allow that rounding window so events are dispatchable immediately.
AVAILABLE_AT_GRACE = timedelta(seconds=1)


@dataclass(frozen=True, slots=True)
class DispatchResult:
    dispatched: int


def enqueue_outbox(
    session: Session,
    topic: str,
    aggregate_id: str,
    payload: dict,
    *,
    subject_org: str | None,
) -> OutboxEvent:
    """Insert an outbox event in the caller's transaction.

    The event is flushed but never committed here, so it shares the
    business write's fate: a business rollback removes it too.

    M4 批次 C（任务书 §7-M4「队列 job 携带主体标签用于计量」）：``subject_org``
    **keyword-only 必填**＝机械闸——每个入队调用点必须显式声明主体：能解析
    的传目标主体 org（通常＝项目的 ``org_id`` 或发起人 ``users.org_id``）；
    平台面/匿名面/解析不出的**显式传 ``None``**（平台级，不静默）。计量面
    非授权面：标签不影响任何调度/权限行为。
    """
    event = OutboxEvent(
        topic=topic,
        aggregate_id=aggregate_id,
        payload_json=payload,
        status="pending",
        attempts=0,
        available_at=utcnow(),
        subject_org=subject_org,
    )
    session.add(event)
    session.flush()
    return event


def subject_org_of_project(session: Session, project_id: str | None) -> str | None:
    """项目主体 org（M4 批次 C 计量标签）；项目不存在/无归属 ⇒ None（平台级）。"""
    if not project_id:
        return None
    from fde_api.workbench.models import Project

    project = session.get(Project, project_id)
    return project.org_id if project is not None else None


def subject_org_of_user(session: Session, user_id: str | None) -> str | None:
    """账号主体 org（M4 批次 C 计量标签）；账号不存在/平台身份 ⇒ None。"""
    if not user_id:
        return None
    from fde_api.auth.models import User

    user = session.get(User, user_id)
    return user.org_id if user is not None else None


def subject_org_of_automation_task(session: Session, task: object) -> str | None:
    """自动化任务主体 org：项目归属优先，无项目回创建者归属；都无 ⇒ None。"""
    project_id = getattr(task, "project_id", None)
    if project_id:
        org = subject_org_of_project(session, project_id)
        if org:
            return org
    return subject_org_of_user(session, getattr(task, "created_by_user_id", None))


def dispatch_pending(
    session: Session, queue: object, limit: int = 100
) -> DispatchResult:
    """Claim the oldest due events and enqueue one job per target.

    A leading read forces a fresh consistent snapshot so the caller's already
    committed events are always visible under MySQL REPEATABLE READ, then a
    conditional UPDATE claims each event so concurrent workers cannot
    double-dispatch it. If any enqueue fails the batch rolls back and events
    stay pending.
    """
    from fde_api.jobs.queue import ensure_background_job

    session.execute(select(OutboxEvent.id).limit(1))
    events = session.scalars(
        select(OutboxEvent)
        .where(
            OutboxEvent.status == "pending",
            OutboxEvent.available_at <= utcnow() + AVAILABLE_AT_GRACE,
        )
        .order_by(OutboxEvent.available_at, OutboxEvent.id)
        .limit(limit)
    ).all()

    dispatched = 0
    try:
        for event in events:
            claimed = session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == event.id, OutboxEvent.status == "pending")
                .values(status="dispatched")
            )
            if claimed.rowcount != 1:
                continue
            job = ensure_background_job(
                session, event.topic, event.aggregate_id, subject_org=event.subject_org
            )
            queue.enqueue(job.id)  # type: ignore[attr-defined]
            dispatched += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    return DispatchResult(dispatched=dispatched)


# outbox last_error 与业务行同宽纪律：只留截断后的失败摘要（Text 列，
# 2000 字上限与后台 job 诊断口径一致）。
_OUTBOX_ERROR_MAX = 2000


def mark_completed(session: Session, job_type: str, target_id: str) -> int:
    """Settle the dispatched events for a succeeded job (V3 T-J1 / WB-DEF-9).

    Outbox events had no completed/failed write point: dispatched was a
    terminal leak. The linkage key is (topic, aggregate_id) == (job_type,
    target_id) — the same pair ``dispatch_pending`` deduped on, so all events
    coalesced into this job settle together. Events still pending (not yet
    claimed) are untouched: they belong to a future dispatch.
    """
    return _settle_for_job(session, job_type, target_id, "completed", "")


def mark_failed(
    session: Session, job_type: str, target_id: str, last_error: str = ""
) -> int:
    """Settle the dispatched events for a failed job, keeping the error digest."""
    return _settle_for_job(session, job_type, target_id, "failed", last_error[:_OUTBOX_ERROR_MAX])


def _settle_for_job(
    session: Session, job_type: str, target_id: str, status: str, last_error: str
) -> int:
    result = session.execute(
        update(OutboxEvent)
        .where(
            OutboxEvent.topic == job_type,
            OutboxEvent.aggregate_id == target_id,
            OutboxEvent.status == "dispatched",
        )
        .values(status=status, last_error=last_error)
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]  # 与 dispatch_pending 同口径


def cancel_for_job(
    session: Session, job_type: str, target_id: str, reason: str = ""
) -> int:
    """Close every unsettled event for a cancelled job (V3 T-J2，域 14).

    与 mark_failed（只收 dispatched）的刻意差异：取消还收掉仍处 pending 的
    事件——运营者杀的是整个工作单元；留着 pending 行，下一轮 dispatch
    会为同键新建 job，已取消的工作被复活。取消之后**新**提交的事件则照常
    走新建 job（终态已释放槽位），属合法新工作。
    """
    result = session.execute(
        update(OutboxEvent)
        .where(
            OutboxEvent.topic == job_type,
            OutboxEvent.aggregate_id == target_id,
            OutboxEvent.status.in_(("pending", "dispatched")),
        )
        .values(status="failed", last_error=reason[:_OUTBOX_ERROR_MAX])
    )
    return int(result.rowcount or 0)  # type: ignore[attr-defined]  # 与 dispatch_pending 同口径
