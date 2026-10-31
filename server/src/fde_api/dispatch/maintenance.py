"""dispatch 维护任务（P1-7 留存策略 + 超时释放调度，goal-r6）。

- 超时释放（§2.5/§6.2）：expire_stale_offers（r4 已实现）挂进调度。
- 留存扫描（规则表 B11 / §6.2）：撮合流水与评分留痕 3 年、涉税资料 10 年
  ——本任务只**报告**超期对象（OperationEvent 留痕，含 bounded 样本清单），
  实际删档/转冷存储是运营人工动作（留存是「至少保留」下限，删除另有合规
  审批；goal-r6 留注⑰）。
- 调度：cli.scheduler 主循环每轮调用 `maintenance_due()`（24h 节流，经
  BackgroundJob 天然去重）→ 到期 enqueue `dispatch.maintenance` → worker
  跑 handler（jobs/handlers 注册，模式同 research.export）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fde_api.dispatch.disputes import run_l0_reconciliation
from fde_api.dispatch.models import DeliverySettlement, Dispute, DispatchOffer
from fde_api.dispatch.offer_service import expire_stale_offers
from fde_api.projects.events import record_event
from fde_api.workbench.models import Payment

RETENTION_MATCHING_YEARS = 3   # 撮合流水与评分留痕（§6.2 / 规则表 B11）
RETENTION_TAX_YEARS = 10       # 涉税资料（§7.4 / B11）
_MAINTENANCE_JOB_TYPE = "dispatch.maintenance"
_SAMPLE_LIMIT = 50


def retention_scan(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """超期对象盘点（只读 + 事件留痕，不删数据——留注⑰）。"""
    now = now or datetime.now(timezone.utc)
    matching_cutoff = now - timedelta(days=365 * RETENTION_MATCHING_YEARS)
    tax_cutoff = now - timedelta(days=365 * RETENTION_TAX_YEARS)

    stale_offers = session.scalars(
        select(DispatchOffer.id).where(DispatchOffer.created_at < matching_cutoff).limit(_SAMPLE_LIMIT)
    ).all()
    stale_settlements = session.scalars(
        select(DeliverySettlement.id).where(DeliverySettlement.created_at < tax_cutoff).limit(_SAMPLE_LIMIT)
    ).all()
    stale_payments = session.scalars(
        select(Payment.id).where(Payment.created_at < tax_cutoff).limit(_SAMPLE_LIMIT)
    ).all()
    resolved_disputes = session.scalars(
        select(Dispute.id).where(
            Dispute.status.in_(("resolved", "closed")),
            Dispute.resolved_at.is_not(None),
            Dispute.resolved_at < matching_cutoff,
        ).limit(_SAMPLE_LIMIT)
    ).all()

    report = {
        "matching_over_3y_sample": stale_offers,
        "tax_over_10y_settlements_sample": stale_settlements,
        "tax_over_10y_payments_sample": stale_payments,
        "disputes_past_3y_sample": resolved_disputes,
        "note": "report-only：删档/转冷存储须人工合规审批（留注⑰）",
    }
    admin = session.scalar(select_admin())
    target = session_get_any_package(session)
    if admin is not None and target is not None:
        record_event(
            session,
            admin,
            "dispatch_retention_scanned",
            target,
            report,
        )
    return report


def select_admin():
    from fde_api.auth.models import User

    from sqlalchemy import select as _select

    return _select(User).where(User.role == "admin").limit(1)


def session_get_any_package(session: Session):
    from sqlalchemy import select as _select

    from fde_api.dispatch.models import DeliveryPackage

    return session.scalar(_select(DeliveryPackage).limit(1))


def run_maintenance(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """维护任务体（worker handler 调用）：超时释放 + 留存扫描 + T+30 对账。"""
    expired = expire_stale_offers(session, now=now)
    retention = retention_scan(session, now=now)
    reconciliation = run_l0_reconciliation(session, now=now)
    return {
        "expired_offers": expired,
        "retention": retention,
        "t30_reconciliation": reconciliation,
    }


def maintenance_due(session: Session, *, now: datetime | None = None) -> bool:
    """24h 节流：还有 pending/queued/running 维护作业 → 不到期；最近一次成功
    完成距今 ≥24h 才再投（DB 侧 max(updated_at)，不受 ORM server_default
    回填时点影响）。"""
    from sqlalchemy import func

    from fde_api.jobs.models import BackgroundJob

    now = now or datetime.now(timezone.utc)
    running = session.scalar(
        select(BackgroundJob.id).where(
            BackgroundJob.job_type == _MAINTENANCE_JOB_TYPE,
            BackgroundJob.status.in_(("pending", "queued", "running")),
        )
    )
    if running is not None:
        return False
    last_finished_at = session.scalar(
        select(func.max(BackgroundJob.updated_at)).where(
            BackgroundJob.job_type == _MAINTENANCE_JOB_TYPE,
            BackgroundJob.status.in_(("succeeded", "failed")),
        )
    )
    if last_finished_at is None:
        return True
    return now - last_finished_at >= timedelta(hours=24)


def register_dispatch_maintenance_handler() -> None:
    from fde_api.jobs.handlers import register_handler

    register_handler(_MAINTENANCE_JOB_TYPE, _run_maintenance_job)


def _run_maintenance_job(job) -> None:
    """worker handler：单事务跑超时释放 + 留存扫描 + T+30 对账。"""
    from fde_api.extensions import db

    session = db.session()
    try:
        with session.begin():
            run_maintenance(session)
    finally:
        session.close()
