"""disputes 争议与 T+30 对账（设计 §6.6/§7.5，goal-r6）。

L0 机器对账（每次必跑）：逐包逐里程碑比对 delivery_settlements（accrued+
payable+paid 的 base_amount 合计）vs Payment 实收——差异 > ±¥1 → 自动生成
disputes L0 草稿（幂等：同包同键已有 draft/open 争议则跳过）。对账单只存
source_uri 指针。

L1/L2 人工：打开（48h SLA 起算）/裁决（**处罚类动作 100% 人工**——本模块
自动侧只产 L0 草稿，resolution 只能由人写入；L2 双签留痕二期，留注⑯）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import DeliveryPackage, DeliverySettlement, Dispute
from fde_api.projects.events import record_event
from fde_api.system_configuration import DISPATCH_CONSTANTS
from fde_api.workbench.models import Payment

_L1_AMOUNT_CEILING = Decimal("50000")
_DIFF_TOLERANCE = Decimal("1")  # §7.5：差异 > ±¥1 生成草稿
OPEN_STATUSES = ("draft", "open", "reviewing")


def open_dispute(
    session: Session,
    *,
    actor: User,
    package_id: str,
    layer: str,
    reason: str,
    settlement_key: str | None = None,
    amount: Decimal | None = None,
    l0_report_source_uri: str | None = None,
) -> Dispute:
    """人工打开争议（L1 平台运营 / L2 双人复核入口）。L0 只由对账自动产。"""
    if actor.role not in ("admin", "project_lead"):
        raise DispatchServiceError("forbidden", "只有平台侧可打开争议。", 403)
    if layer not in ("L1", "L2"):
        raise DispatchServiceError("invalid_request", "人工打开仅限 L1/L2（L0 由对账自动产）。")
    if layer == "L1" and amount is not None and amount > _L1_AMOUNT_CEILING:
        raise DispatchServiceError(
            "amount_above_l1", f"L1 仅受理 ≤¥{_L1_AMOUNT_CEILING:,.0f}，请走 L2 双人复核。", 422
        )
    if not isinstance(reason, str) or not reason.strip():
        raise DispatchServiceError("invalid_request", "争议原因必填。")
    package = session.get(DeliveryPackage, package_id)
    if package is None:
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    now = datetime.now(timezone.utc)
    dispute = Dispute(
        package_id=package.id,
        settlement_key=settlement_key,
        layer=layer,
        status="open",
        amount=amount,
        reason=reason.strip(),
        l0_report_source_uri=l0_report_source_uri,
        snapshot_hash=package.snapshot_hash,
        opened_by_user_id=actor.id,
        sla_due_at=now
        + timedelta(hours=int(DISPATCH_CONSTANTS["appeal_sla_hours"])),
    )
    session.add(dispute)
    session.flush()
    record_event(
        session,
        actor,
        "dispute_opened",
        package,
        {
            "dispute_id": dispute.id,
            "layer": layer,
            "settlement_key": settlement_key,
            "sla_due_at": dispute.sla_due_at.isoformat() if dispute.sla_due_at else None,
        },
    )
    return dispute


def resolve_dispute(
    session: Session,
    *,
    actor: User,
    dispute_id: str,
    resolution: str,
    close: bool = False,
) -> Dispute:
    """人工裁决（§6.6：处罚类动作 100% 人工；L2 双签留痕二期留注⑯）。"""
    if actor.role not in ("admin", "project_lead"):
        raise DispatchServiceError("forbidden", "裁决是人工动作，仅平台侧可执行。", 403)
    dispute = session.get(Dispute, dispute_id)
    if dispute is None:
        raise DispatchServiceError("dispute_not_found", "争议单不存在。", 404)
    if dispute.status not in ("open", "reviewing"):
        raise DispatchServiceError(
            "invalid_dispute_state", f"状态 {dispute.status} 不能裁决。", 409
        )
    if not isinstance(resolution, str) or not resolution.strip():
        raise DispatchServiceError("invalid_request", "裁决结论必填。")
    dispute.status = "closed" if close else "resolved"
    dispute.resolution = resolution.strip()
    dispute.handled_by_user_id = actor.id
    dispute.resolved_at = datetime.now(timezone.utc)
    session.flush()
    package = session.get(DeliveryPackage, dispute.package_id)
    if package is None:
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    record_event(
        session,
        actor,
        "dispute_resolved",
        package,
        {
            "dispute_id": dispute.id,
            "layer": dispute.layer,
            "status": dispute.status,
            "resolution": dispute.resolution,
        },
    )
    return dispute


def run_l0_reconciliation(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """T+30 对账（§7.5，月度）：逐包逐键比对结算应计 vs Payment 实收，
    差异 > ±¥1 → L0 草稿（幂等）。返回差异包清单（事件留痕）。"""
    now = now or datetime.now(timezone.utc)
    rows = session.execute(
        select(
            DeliverySettlement.package_id,
            DeliverySettlement.settlement_key,
            func_settlement_total(),
        ).group_by(DeliverySettlement.package_id, DeliverySettlement.settlement_key)
    ).all()
    expected: dict[tuple[str, str], Decimal] = {
        (package_id, key): total for package_id, key, total in rows
    }
    payments = session.execute(
        select(Payment.project_id, Payment.milestone_key, Payment.received_amount)
        .where(Payment.received_amount.is_not(None))
    ).all()
    # project → 该项目下的包（一个项目通常一个包；多包取全部）
    project_packages: dict[str, list[str]] = {}
    for package in session.scalars(select(DeliveryPackage)).all():
        project_packages.setdefault(package.project_id, []).append(package.id)
    package_snapshots = {
        package.id: package.snapshot_hash for package in session.scalars(select(DeliveryPackage)).all()
    }

    created = 0
    diffs: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for project_id, milestone_key, received in payments:
        for package_id in project_packages.get(project_id, []):
            seen_key = (package_id, milestone_key)
            if seen_key in seen:
                continue
            seen.add(seen_key)
            expected_total = expected.get(seen_key, Decimal("0"))
            diff = Decimal(received) - expected_total
            if abs(diff) <= _DIFF_TOLERANCE:
                continue
            existing = session.scalar(
                select(Dispute.id).where(
                    Dispute.package_id == package_id,
                    Dispute.settlement_key == milestone_key,
                    Dispute.status.in_(OPEN_STATUSES),
                )
            )
            if existing is not None:
                continue
            dispute = Dispute(
                package_id=package_id,
                settlement_key=milestone_key,
                layer="L0",
                status="draft",
                amount=diff,
                reason=f"T+30 对账差异：实收 {received} − 应计 {expected_total} = {diff}（>±¥1）",
                snapshot_hash=package_snapshots.get(package_id),
            )
            session.add(dispute)
            created += 1
            diffs.append(
                {
                    "package_id": package_id,
                    "settlement_key": milestone_key,
                    "received": float(received),
                    "accrued": float(expected_total),
                    "diff": float(diff),
                    "dispute_id": dispute.id,
                }
            )
    if created:
        session.flush()
        system_actor = session.scalar(select(User).where(User.role == "admin").limit(1))
        if system_actor is not None:
            target = session.get(DeliveryPackage, diffs[0]["package_id"])
            if target is not None:
                record_event(
                    session,
                    system_actor,
                    "dispatch_t30_reconciled",
                    target,
                    {"diffs": diffs, "created": created},
                )
    return {"scanned_packages": len(project_packages), "diffs": diffs, "created": created}


def func_settlement_total():
    from sqlalchemy import func

    return func.sum(DeliverySettlement.base_amount)
