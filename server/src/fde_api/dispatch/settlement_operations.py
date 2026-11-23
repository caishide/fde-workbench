"""Admin orchestration for project-scoped dispatch settlement bookkeeping."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from decimal import Decimal
from hashlib import sha256
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from fde_api.auth.confirm_throttle import confirm_attempts_blocked, record_confirm_failure
from fde_api.auth.limits import PASSWORD_MAX_LENGTH
from fde_api.auth.models import ROLE_ADMIN, User
from fde_api.auth.passwords import verify_password
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import (
    DeliveryPackage,
    DeliverySettlement,
    DispatchRuleVersion,
    DispatchSettlementAllocation,
)
from fde_api.dispatch.settlements import (
    FIVE_SEAT_KEYS,
    _five_seat_shares,
    accrue_settlements_for_project,
    allocate_five_seats_with_lead_attribution,
    mark_paid,
    mark_payable,
    province_input_invoice_entries,
    province_input_invoice_payee,
)
from fde_api.orgs.isolation import is_cross_org_action
from fde_api.projects.events import record_event
from fde_api.workbench.models import Contract, Payment, Project, Quote

SettlementAction = Literal["allocate", "payable", "paid", "input-invoice"]
_REGIONAL_SEATS = {"county", "province"}
_VACANCIES = {"county": "self_sourced_self_delivered", "province": "no_province_partner"}


def require_platform_settlement_admin(actor: User | None) -> User:
    if actor is None or not actor.is_active or actor.role != ROLE_ADMIN or actor.org_id is not None:
        raise DispatchServiceError("forbidden", "仅平台系统运维员可操作结算。", 403)
    return actor


def _require_password(session: Session, actor: User, value: object) -> tuple[User, str]:
    current = require_platform_settlement_admin(session.get(User, actor.id))
    if not isinstance(value, str) or not 1 <= len(value) <= PASSWORD_MAX_LENGTH:
        raise DispatchServiceError("invalid_request", "请输入当前账号密码。")
    if confirm_attempts_blocked(actor.id):
        raise DispatchServiceError("too_many_attempts", "密码错误次数过多，请 15 分钟后重试。", 429)
    if not verify_password(current.password_hash, value):
        record_confirm_failure(actor.id)
        raise DispatchServiceError("invalid_password", "当前账号密码不正确。", 403)
    return current, value


def _complete_versioned_allocation(
    row: DeliverySettlement,
    allocations: list[DispatchSettlementAllocation],
    versions: dict[str, DispatchRuleVersion],
) -> DispatchRuleVersion | None:
    version_ids = {item.rule_version_id for item in allocations}
    if {item.seat_key for item in allocations} != set(FIVE_SEAT_KEYS) or len(version_ids) != 1:
        return None
    version_id = next(iter(version_ids))
    version = versions.get(version_id) if version_id is not None else None
    if version is None:
        return None
    try:
        _, shares = _five_seat_shares(version.rule_snapshot)
    except DispatchServiceError:
        return None
    if any(item.shares_in_pool != shares.get(item.seat_key) for item in allocations):
        return None
    if sum((item.amount for item in allocations), Decimal(0)) != row.base_amount:
        return None
    return version


def _versions_for(
    session: Session, allocations: list[DispatchSettlementAllocation]
) -> dict[str, DispatchRuleVersion]:
    ids = {item.rule_version_id for item in allocations if item.rule_version_id is not None}
    if not ids:
        return {}
    return {row.id: row for row in session.scalars(select(DispatchRuleVersion).where(DispatchRuleVersion.id.in_(ids)))}


def _existing_input_invoice_ids(session: Session, settlement_ids: list[str]) -> set[str]:
    from fde_api.commercial.models import CommercialRevenueLedger as Ledger

    if not settlement_ids:
        return set()
    return {entry.delivery_settlement_id for entry in session.scalars(
        province_input_invoice_entries().where(Ledger.delivery_settlement_id.in_(settlement_ids))
    ) if entry.delivery_settlement_id is not None}


def _settlements_for_project(project_id: str):
    return (
        select(DeliverySettlement, DeliveryPackage)
        .join(DeliveryPackage, DeliveryPackage.id == DeliverySettlement.package_id)
        .where(DeliveryPackage.project_id == project_id)
    )


def list_project_settlements(session: Session, project_id: str) -> dict[str, Any]:
    if session.get(Project, project_id) is None:
        raise DispatchServiceError("project_not_found", "项目不存在。", 404)
    rows = session.execute(
        _settlements_for_project(project_id).order_by(DeliveryPackage.package_code, DeliverySettlement.settlement_key)
    ).all()
    allocations = list(session.scalars(
        select(DispatchSettlementAllocation).where(
            DispatchSettlementAllocation.settlement_id.in_([row.id for row, _ in rows])
        )
    )) if rows else []
    grouped: dict[str, list[DispatchSettlementAllocation]] = defaultdict(list)
    for item in allocations:
        grouped[item.settlement_id].append(item)
    versions = _versions_for(session, allocations)
    invoice_ids = _existing_input_invoice_ids(session, [row.id for row, _ in rows])
    return {
        "settlements": [
            _serialize(row, package, grouped[row.id], versions, row.id in invoice_ids)
            for row, package in rows
        ],
    }


def _allocation_snapshot(row: DeliverySettlement, package: DeliveryPackage) -> str:
    # 包哈希只绑定发布内容，不能识别同一包的实收基数或交付席变更。
    values = (
        row.id, row.settlement_key, row.status, str(row.base_amount), row.updated_at.isoformat(),
        row.snapshot_hash, package.id, package.snapshot_hash, package.sow_type, package.seat_delivery,
    )
    return sha256(json.dumps(values, separators=(",", ":")).encode("utf-8")).hexdigest()


def _require_allocation_snapshot(row: DeliverySettlement, package: DeliveryPackage, payload: dict[str, Any]) -> None:
    if "expected_allocation_snapshot" not in payload:
        raise DispatchServiceError("allocation_snapshot_required", "请重新读取结算并确认实收基数。", 428)
    expected = payload["expected_allocation_snapshot"]
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise DispatchServiceError("invalid_allocation_snapshot", "结算确认快照无效，请重新读取。", 400)
    if expected != _allocation_snapshot(row, package):
        raise DispatchServiceError("allocation_snapshot_conflict", "结算已变更，请重新读取并核对后再确认五席分配。", 409)


def _serialize(
    row: DeliverySettlement,
    package: DeliveryPackage,
    allocations: list[DispatchSettlementAllocation],
    versions: dict[str, DispatchRuleVersion],
    input_invoice_recorded: bool,
) -> dict[str, Any]:
    version = _complete_versioned_allocation(row, allocations, versions)
    return {
        "id": row.id,
        "package_id": package.id,
        "package_code": package.package_code,
        "delivery_user_id": package.seat_delivery,
        "settlement_key": row.settlement_key,
        "status": row.status,
        "base_amount": str(row.base_amount),
        "allocation_snapshot": _allocation_snapshot(row, package) if row.status == "draft" else None,
        "version_no": version.version_no if version else None,
        "requires_versioned_allocation": _is_pilot_milestone(row),
        "paid_at": row.paid_at.isoformat() if row.paid_at is not None else None,
        "input_invoice_required": any(item.seat_key == "province" and item.status == "paid" for item in allocations),
        "input_invoice_recorded": input_invoice_recorded,
        "allocations": [
            {
                "seat_key": item.seat_key,
                "payee_user_id": item.payee_user_id,
                "amount": str(item.amount),
                "status": item.status,
                "reason_code": item.reason_code,
            }
            for item in sorted(allocations, key=lambda item: FIVE_SEAT_KEYS.index(item.seat_key))
        ],
    }


def _is_pilot_milestone(row: DeliverySettlement) -> bool:
    # G4/G8 收款里程碑在收款计划中专属于 B 试点。
    return row.settlement_key in {"G4", "G8"}


def _linked_receipt(session: Session, row: DeliverySettlement, package: DeliveryPackage) -> Payment:
    payment = session.scalar(select(Payment).where(
        Payment.project_id == package.project_id,
        Payment.milestone_key == row.settlement_key,
    ))
    if (
        payment is None
        or payment.received_at is None
        or payment.received_amount != row.base_amount
        or (package.sow_type is not None and payment.sow_type != package.sow_type)
        or row.snapshot_hash != package.snapshot_hash
    ):
        raise DispatchServiceError(
            "settlement_receipt_conflict", "该交付包的快照或对应里程碑实收与结算不一致，请先核对。", 409
        )
    return payment


def _allocate(
    session: Session, actor: User, package: DeliveryPackage, payment: Payment,
    payload: dict[str, Any], password: str,
) -> None:
    if not package.seat_delivery:
        raise DispatchServiceError("settlement_delivery_required", "请先确认交付包的交付人。", 409)
    payees = payload.get("seat_payees", {})
    vacant = payload.get("vacant_reasons", {})
    if not isinstance(payees, dict) or not isinstance(vacant, dict) or (
        set(payees) | set(vacant)
    ) != _REGIONAL_SEATS or set(payees) & set(vacant):
        raise DispatchServiceError(
            "invalid_payee_spec", "市县席和省级席各需指定一个收款人或一项空缺原因。", 422
        )
    if "province" in payees:
        raise DispatchServiceError("regional_agent_not_enabled", "本期省级席位须登记为无省级服务商。", 409)
    for seat, reason in vacant.items():
        if reason != _VACANCIES[seat]:
            raise DispatchServiceError("invalid_vacancy_reason", "该席位不适用所选空缺原因。", 422)
    if "county" in payees:
        from fde_api.commercial.models import RegionalPartner

        payee = payees["county"]
        active_service = (
            session.scalar(select(RegionalPartner.id).join(User, User.id == RegionalPartner.applicant_user_id).where(
                User.id == payee, User.is_active.is_(True), RegionalPartner.stage == "city_service",
            ).limit(1)) if isinstance(payee, str) and 1 <= len(payee) <= 36 else None
        )
        if active_service is None:
            raise DispatchServiceError("city_service_required", "市县席收款人须为启用的城市服务伙伴。", 422)
    allocate_five_seats_with_lead_attribution(
        session,
        payment,
        package,
        actor=actor,
        seat_payees={"delivery": package.seat_delivery, **payees, **dict.fromkeys(vacant)},
        vacant_reasons=vacant,
        confirm_password=password,
    )


def _evidence_pointer(value: object) -> str:
    if not isinstance(value, str) or len(value.strip()) > 500:
        raise DispatchServiceError("invalid_request", "凭证指针须在 500 字以内。")
    pointer = value.strip()
    scheme, separator, path = pointer.partition("://")
    if not separator or scheme not in {"fdeops", "openfde"} or not path.strip() or any(c in value for c in "\r\n\x00"):
        raise DispatchServiceError("invalid_request", "请输入 fdeops:// 或 openfde:// 凭证指针。")
    return pointer


def _record_input_invoice(
    session: Session, actor: User, row: DeliverySettlement, package: DeliveryPackage,
    payment: Payment, payload: dict[str, Any], password: str,
) -> dict[str, Any]:
    from fde_api.commercial.ledger_service import record_revenue_entry
    from fde_api.commercial.models import CommercialRevenueLedger as Ledger
    from fde_api.commercial.service import CommercialServiceError

    source_uri = _evidence_pointer(payload.get("source_uri"))
    raw_hash = payload.get("content_hash")
    if not isinstance(raw_hash, str) or re.fullmatch(r"[0-9a-fA-F]{64}", raw_hash.strip()) is None:
        raise DispatchServiceError("invalid_request", "进项票须提供 64 位 SHA-256 指纹。")
    content_hash = raw_hash.strip().lower()
    existing = list(session.scalars(
        province_input_invoice_entries().where(Ledger.delivery_settlement_id == row.id)
    ))
    for entry in existing:
        if entry.source_uri == source_uri and (entry.content_hash or "").lower() == content_hash:
            return {"entry_id": entry.id, "changed": False}
    if existing:
        raise DispatchServiceError("input_invoice_already_recorded", "已登记进项票，请人工复核已有科目。", 409)
    if row.status != "accrued":
        raise DispatchServiceError("invalid_settlement_state", "只有已计提的结算可登记进项票。", 409)
    payee = province_input_invoice_payee(session, row.id)
    if payee is None:
        raise DispatchServiceError("input_invoice_not_applicable", "本结算没有已分配的省级席位。", 409)
    quote_id = session.scalar(select(Quote.id).where(
        Quote.id == package.quote_id, Quote.project_id == package.project_id,
    )) if package.quote_id is not None else None
    contract_id = session.scalar(select(Contract.id).where(
        Contract.project_id == package.project_id, Contract.sow_type == payment.sow_type,
    ))
    try:
        data = record_revenue_entry(
            session, actor=actor, subject_type="project_share", line_item="project_fee",
            payee_user_id=payee, subject_user_id=payee, quote_id=quote_id,
            payment_id=payment.id, contract_id=contract_id, delivery_settlement_id=row.id,
            delivery_package_id=package.id, source_uri=source_uri,
            content_hash=content_hash, confirm_password=password,
        )
    except CommercialServiceError as error:
        raise DispatchServiceError(error.code, error.message, error.status) from error
    return {"entry_id": data["entry"]["id"], "changed": True}


def operate_project_settlement(
    session: Session, *, actor: User, project_id: str, settlement_id: str,
    action: SettlementAction, payload: dict[str, Any],
) -> dict[str, Any]:
    actor, password = _require_password(session, actor, payload.get("confirm_password"))
    # 收款、发包与验收并发时保持项目 → 交付包 → 结算锁序。项目的 NO KEY UPDATE 允许外键引用。
    project = session.scalar(
        select(Project).where(Project.id == project_id).with_for_update(key_share=True)
        .execution_options(populate_existing=True)
    )
    if project is None:
        raise DispatchServiceError("project_not_found", "项目不存在。", 404)
    settlement_package_id = select(DeliverySettlement.package_id).where(DeliverySettlement.id == settlement_id)
    package = session.scalar(
        select(DeliveryPackage)
        .where(DeliveryPackage.project_id == project.id, DeliveryPackage.id == settlement_package_id.scalar_subquery())
        .with_for_update(key_share=True).execution_options(populate_existing=True)
    )
    if package is None:
        raise DispatchServiceError("settlement_not_found", "项目内没有该结算行。", 404)
    row = session.scalar(
        select(DeliverySettlement).where(DeliverySettlement.id == settlement_id, DeliverySettlement.package_id == package.id)
        .with_for_update().execution_options(populate_existing=True)
    )
    if row is None:
        raise DispatchServiceError("settlement_not_found", "项目内没有该结算行。", 404)
    if action == "allocate":
        _require_allocation_snapshot(row, package, payload)
    payment = _linked_receipt(session, row, package)
    result: dict[str, Any] | None = None
    if action == "allocate":
        _allocate(session, actor, package, payment, payload, password)
        if payment.acceptance_passed_at is not None:
            accrue_settlements_for_project(session, actor=actor, project_id=project.id, settlement_id=row.id)
    elif action == "payable":
        if row.status == "accrued" and _is_pilot_milestone(row):
            allocations = list(session.scalars(select(DispatchSettlementAllocation).where(
                DispatchSettlementAllocation.settlement_id == row.id
            )))
            if _complete_versioned_allocation(row, allocations, _versions_for(session, allocations)) is None:
                raise DispatchServiceError(
                    "versioned_allocation_required", "B 试点转应付前必须具备同一规则版本的完整五席明细。", 409
                )
        mark_payable(session, actor=actor, settlement_id=row.id)
    elif action == "paid":
        proof = _evidence_pointer(payload.get("paid_proof_source_uri"))
        mark_paid(session, actor=actor, settlement_id=row.id, paid_proof_source_uri=proof)
    else:
        result = _record_input_invoice(session, actor, row, package, payment, payload, password)
        if not result["changed"]:
            return result
    if is_cross_org_action(actor.org_id, project.org_id):
        event = record_event(session, actor, "cross_org_dispatch_settlement_bookkeeping", package, {
            "settlement_id": row.id, "settlement_key": row.settlement_key, "action": action,
        })
        event.org_id = project.org_id
    return {"id": row.id, "status": row.status, "settlement_key": row.settlement_key, **(result or {})}
