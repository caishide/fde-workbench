"""payment_service：P4 收款与催款（设计 §6；工具包 §10 记录表单电子化）。

口径铁律（映射表 v1.3 + SOP v2.4.6；工程层不得发明方法论层没有的状态）：
- 里程碑定义 = seeds/payment_milestones.json（7 条，各带 source_uri + sha256 溯源）：
    G3 A 诊断款（按小时预付 ¥500/h 锚点或半天打包）/ G4 B 预付 50% /
    G8 B 尾款 50%（毕业拍板 proceed 时）/ SOW-C M1 40% 签约即付 /
    M2 40% 灰度第 2 段达标 / M3 20% G9 验收全签 / D 陪跑月付（逾期 15 天暂停）。
- 状态不落库（读时现算）：received_at 有值 = 已收；否则 invoice_no 有值 = 已开票；
    否则 = 计划。dunning_level 同理现算：到期未收按 D+7/15/30/60 四级提醒。
- G8 stop 也按合同结算（SOP §S8 拍板三态）：门禁引擎 decide stop 时联动给
  G8 尾款行打 settlement_reason='g8_stop'——B 尾款照收，不因 stop 免除。
- 金额真相在台账（人回填），本表是计划与提醒的执行看板。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from fde_api.auth.models import User
from fde_api.extensions import db
from fde_api.projects.events import record_event
from fde_api.projects.permissions import project_access
from fde_api.workbench.models import Gate, OperationEvent, Payment, Project

_SEEDS_DIR = Path(__file__).resolve().parents[3] / "seeds"

# 计划生成用的 SOW → 里程碑映射（payment_milestones.json 的投影；ratio 原样）
PLAN_MILESTONES: dict[str, tuple[str, ...]] = {
    "a": ("G3",),
    "b": ("G4", "G8"),
    "c": ("SOW-C M1", "SOW-C M2", "SOW-C M3"),
    "d": ("D",),
}

SOW_LABELS = {"a": "A 诊断", "b": "B 试点", "c": "C 集成", "d": "D 陪跑"}

# D+7/15/30/60 四级催款（设计 §6；读时现算）
DUNNING_LEVELS = (
    (60, "d60"),
    (30, "d30"),
    (15, "d15"),
    (7, "d7"),
)
DUNNING_LABELS = {
    None: "未到期",
    "d7": "D+7 提醒",
    "d15": "D+15 催收",
    "d30": "D+30 严肃催收",
    "d60": "D+60 高管对话/暂停",
}

TWO_PLACES = Decimal("0.01")


class PaymentServiceError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@lru_cache(maxsize=1)
def _milestone_templates() -> dict[str, dict[str, Any]]:
    """读 payment_milestones.json（镜像内只读，进程级缓存）。"""
    path = _SEEDS_DIR / "payment_milestones.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as error:
        raise RuntimeError("payment_milestones.json unavailable") from error
    rows = payload.get("payment_milestones")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("payment_milestones.json empty")
    return {row["milestone_key"]: row for row in rows}


def _milestone_template(key: str) -> dict[str, Any]:
    """取单条里程碑模板；种子缺失转服务错误（不裸 500/KeyError）。"""
    try:
        templates = _milestone_templates()
    except RuntimeError as error:
        raise PaymentServiceError(
            "payment_seed_unavailable",
            "收款里程碑种子不可用，请检查服务端 seeds/payment_milestones.json。",
            500,
        ) from error
    template = templates.get(key)
    if template is None:
        raise PaymentServiceError(
            "payment_milestone_missing",
            f"收款里程碑种子缺少 {key}。",
            500,
        )
    return template


def _positive_amount(value: object, field: str) -> Decimal:
    """金额入参：有限、正数、有上限（拦 NaN/Infinity——float 比较对 NaN 恒假）。"""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise PaymentServiceError("invalid_request", f"{field} 必须是正数金额。", 400)
    try:
        parsed = Decimal(str(value))
    except ArithmeticError:
        raise PaymentServiceError("invalid_request", f"{field} 必须是正数金额。", 400) from None
    if not parsed.is_finite() or not Decimal("0") < parsed <= Decimal("10000000"):
        raise PaymentServiceError("invalid_request", f"{field} 必须是正数金额。", 400)
    return parsed


def _parse_ratio(amount_structure: str) -> Decimal | None:
    if "50%" in amount_structure:
        return Decimal("0.50")
    if "40%" in amount_structure:
        return Decimal("0.40")
    if "20%" in amount_structure:
        return Decimal("0.20")
    return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def generate_payment_plan(
    *, actor: User, project_id: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    """按 SOW 生成收款计划（B 50/50、C 40/40/20、A 预付、D 月付）。

    金额基数 = base_amount（成交价或合同额）；A/D 按输入金额整行。
    幂等：该 SOW 里程碑已有行则 409，除非 replace=true（先删后建）。
    """
    sow_type = payload.get("sow_type")
    if sow_type not in PLAN_MILESTONES:
        raise PaymentServiceError("invalid_request", "sow_type 必须是 a/b/c/d。", 400)
    base = _positive_amount(payload.get("base_amount"), "base_amount")
    replace = bool(payload.get("replace"))
    session = db.session()
    try:
        with session.begin():
            project = _load_project(session, actor, project_id, manage=True)
            # 串行化同项目的计划创建/重建（防并发双插撞唯一约束）
            session.execute(
                select(Project.id).where(Project.id == project.id).with_for_update()
            )
            keys = PLAN_MILESTONES[sow_type]
            existing = list(
                session.scalars(
                    select(Payment).where(
                        Payment.project_id == project.id, Payment.milestone_key.in_(keys)
                    )
                )
            )
            if existing and not replace:
                raise PaymentServiceError(
                    "plan_exists",
                    f"{SOW_LABELS[sow_type]}收款计划已存在（replace=true 可重建）。",
                    409,
                )
            if existing and replace:
                # 金额真相在台账（人回填）：已到账/已开票/G8 结算标记的行不许删
                locked = [
                    row.milestone_key
                    for row in existing
                    if row.received_at is not None
                    or row.invoice_no
                    or row.settlement_reason
                ]
                if locked:
                    raise PaymentServiceError(
                        "ledger_truth_present",
                        f"{'、'.join(locked)} 已有收款事实（到账/开票/G8 结算标记），"
                        "不许 replace 重建，请逐行修正。",
                        409,
                    )
            for row in existing:
                session.delete(row)
            session.flush()
            created = []
            for key in keys:
                template = _milestone_template(key)
                ratio = _parse_ratio(template.get("amount_structure") or "")
                if sow_type in ("a", "d"):
                    amount = _money(base)
                elif ratio is None:
                    raise PaymentServiceError(
                        "invalid_request", f"里程碑 {key} 缺少比例定义。", 400
                    )
                else:
                    amount = _money(base * ratio)
                row = Payment(
                    project_id=project.id,
                    milestone_key=key,
                    sow_type=sow_type,
                    collects=template["collects"],
                    timing=template["timing"],
                    ratio=ratio,
                    amount=amount,
                    note=template.get("amount_structure") or "",
                    source_uri=template["source_uri"],
                    content_hash=template["source_sha256"],
                )
                session.add(row)
                created.append(row)
            session.flush()
            record_event(
                session,
                actor,
                "payment_plan_generated",
                project,
                {
                    "sow_type": sow_type,
                    "base_amount": float(base),
                    "milestones": keys,
                    "replaced": bool(existing),
                },
            )
            rows = [_serialize_payment(row, today=None) for row in created]
        return {"payments": rows, "sow_type": sow_type}
    finally:
        session.close()


def update_payment(
    *,
    actor: User,
    project_id: str,
    milestone_key: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """收款回填（received_amount/received_at/invoice_no）与到期日设置。"""
    session = db.session()
    try:
        with session.begin():
            project = _load_project(session, actor, project_id, manage=True)
            row = _load_payment(session, project.id, milestone_key)
            changes: dict[str, Any] = {}
            if "due_date" in payload:
                row.due_date = _parse_date(payload.get("due_date"), "due_date")
                changes["due_date"] = row.due_date.isoformat() if row.due_date else None
            if "invoice_no" in payload:
                invoice_no = payload.get("invoice_no")
                if invoice_no is not None and (
                    not isinstance(invoice_no, str) or not invoice_no.strip()
                ):
                    raise PaymentServiceError("invalid_request", "invoice_no 必须是非空字符串。", 400)
                row.invoice_no = invoice_no.strip() if isinstance(invoice_no, str) else None
                changes["invoice_no"] = row.invoice_no
            received_touched = False
            if "received_amount" in payload or "received_at" in payload:
                amount = payload.get("received_amount")
                if amount is not None:
                    amount = _positive_amount(amount, "received_amount")
                received_at = payload.get("received_at")
                if received_at is None and amount is not None:
                    received_at = date.today().isoformat()
                if amount is not None:
                    row.received_amount = _money(Decimal(str(amount)))
                    row.received_at = _parse_date(received_at, "received_at")
                    changes["received_amount"] = float(row.received_amount)
                    changes["received_at"] = row.received_at.isoformat()
                elif received_at is not None:
                    # 只补到账日（金额沿用计划额）
                    row.received_at = _parse_date(received_at, "received_at")
                    row.received_amount = row.amount
                    changes["received_at"] = row.received_at.isoformat()
                received_touched = True
            if not changes:
                raise PaymentServiceError("invalid_request", "没有可更新的字段。", 400)
            session.flush()
            if received_touched:
                # P0-4（派单设计 §7.2/§7.3）：实收回填联动结算草稿——基数=实收。
                # 无交付包的项目纯 no-op（存量 A 组路径零感知，催款逻辑不动）。
                from fde_api.dispatch.settlements import record_receipt_settlements

                record_receipt_settlements(
                    session, actor=actor, project=project, payment=row
                )
                # 补口：G8 已过门但尾款晚到——收款时补打验收时刻并推进计提
                # （mark_acceptance_passed 幂等：只动 acceptance 仍为空的实收行）。
                g8_passed = session.scalar(
                    select(Gate.id).where(
                        Gate.project_id == project.id,
                        Gate.gate_key == "G8",
                        Gate.status == "passed",
                    )
                )
                if g8_passed is not None:
                    mark_acceptance_passed(session, actor, project.id)
            record_event(
                session,
                actor,
                "payment_updated",
                row,
                {"milestone_key": milestone_key, **changes},
            )
            return _serialize_payment(row, today=None)
    finally:
        session.close()


def mark_acceptance_passed(session: Session, actor: User, project_id: str) -> dict[str, Any]:
    """G8 过门联动（gate_service decide 事务内调用，P0-4）：验收通过时刻打标。

    只处理已实收行（received_at 非空）：acceptance_passed_at 是
    delivery_settlements 从 draft → accrued 的起算条件之一（实收 + 验收），
    打标后顺手推进该项目已满足双条件的结算计提。无包项目零感知。
    """
    project = session.get(Project, project_id)
    if project is None:
        # 调用方（gate/收款钩子）都在项目事务内，防御分支只为类型收窄
        return {"payments_marked": 0, "settlements_accrued": 0}
    rows = session.scalars(
        select(Payment)
        .where(
            Payment.project_id == project_id,
            Payment.received_at.is_not(None),
            Payment.acceptance_passed_at.is_(None),
        )
        .with_for_update()
    ).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.acceptance_passed_at = now
    from fde_api.dispatch.settlements import accrue_settlements_for_project

    accrued = accrue_settlements_for_project(session, actor=actor, project_id=project_id)
    if rows or accrued:
        record_event(
            session,
            actor,
            "payment_acceptance_marked",
            project,
            {"payments_marked": len(rows), "settlements_accrued": accrued},
        )
    return {"payments_marked": len(rows), "settlements_accrued": accrued}


def flag_g8_stop_settlement(session: Session, actor: User, project_id: str) -> dict[str, Any]:
    """G8 stop 联动（由 gate_service 在 decide 事务内调用）：stop 也按合同结算。

    有 G8 尾款行 → 打 settlement_reason='g8_stop'（B 尾款照收，不因 stop 免除）；
    无行（计划未建）→ 仅留事件，建计划时人工确认。
    """
    row = session.scalar(
        select(Payment)
        .where(Payment.project_id == project_id, Payment.milestone_key == "G8")
        .with_for_update()
    )
    flagged = False
    if row is not None:
        row.settlement_reason = "g8_stop"
        if not row.note.endswith("G8 stop：按合同结算尾款"):
            row.note = (row.note + "；G8 stop：按合同结算尾款").lstrip("；")
        flagged = True
    # 事件目标优先收款行；无行时挂项目（都在则非空——调用方来自项目事务）。
    event_target = row if row is not None else session.get(Project, project_id)
    if event_target is not None:
        record_event(
            session,
            actor,
            "payment_settlement_flagged",
            event_target,
            {"milestone_key": "G8", "flagged": flagged, "reason": "g8_stop"},
        )
    return {"flagged": flagged, "milestone_key": "G8"}


def payment_board(*, actor: User, project_id: str) -> dict[str, Any]:
    """收款看板：行 + 现算状态/催款级 + 汇总（应收/已收/逾期）。"""
    session = db.session()
    try:
        with session.begin():
            project = _load_project(session, actor, project_id, manage=False)
            rows = list(
                session.scalars(
                    select(Payment)
                    .where(Payment.project_id == project.id)
                    .order_by(Payment.created_at, Payment.milestone_key)
                )
            )
            today = date.today()
            serialized = [_serialize_payment(row, today=today) for row in rows]
            # 汇总在 Decimal 域求和再转 float（避免 0.1+0.2 类显示毛刺）
            receivable = sum((row.amount for row in rows), Decimal("0"))
            received = sum(
                (row.received_amount or Decimal("0") for row in rows), Decimal("0")
            )
            overdue = sum(
                (
                    row.amount
                    for row in rows
                    if row.due_date is not None
                    and row.due_date < today
                    and row.received_at is None
                ),
                Decimal("0"),
            )
            events = _recent_payment_events(session, project.id)
        return {
            "payments": serialized,
            "summary": {
                "receivable": float(receivable),
                "received": float(received),
                "outstanding": float(receivable - received),
                "overdue": float(overdue),
                "dunning_counts": {
                    level: sum(1 for row in serialized if row["dunning_level"] == level)
                    for level in ("d7", "d15", "d30", "d60")
                },
            },
            "events": events,
        }
    finally:
        session.close()


def _dunning(row: Payment, today: date) -> str | None:
    if row.received_at is not None or row.due_date is None:
        return None
    days = (today - row.due_date).days
    if days < 7:
        return None
    for threshold, level in DUNNING_LEVELS:
        if days >= threshold:
            return level
    return None


def _serialize_payment(row: Payment, *, today: date | None) -> dict[str, Any]:
    if row.received_at is not None:
        status = "received"
    elif row.invoice_no:
        status = "invoiced"
    else:
        status = "planned"
    level = _dunning(row, today) if today is not None else None
    overdue = bool(
        today is not None
        and row.due_date is not None
        and row.due_date < today
        and row.received_at is None
    )
    return {
        "id": row.id,
        "milestone_key": row.milestone_key,
        "sow_type": row.sow_type,
        "sow_label": SOW_LABELS[row.sow_type],
        "collects": row.collects,
        "timing": row.timing,
        "ratio": float(row.ratio) if row.ratio is not None else None,
        "amount": float(row.amount),
        "received_amount": float(row.received_amount) if row.received_amount is not None else None,
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "received_at": row.received_at.isoformat() if row.received_at else None,
        "invoice_no": row.invoice_no,
        "status": status,
        "status_label": {"planned": "计划", "invoiced": "已开票", "received": "已到账"}[status],
        "settlement_reason": row.settlement_reason,
        "note": row.note,
        "dunning_level": level,
        "dunning_label": DUNNING_LABELS.get(level, "未到期"),
        # 已过到期日未收（D+7 才进催款级；0–6 天只标记不计催款，口径见 DUNNING_LEVELS）
        "overdue": overdue,
        "source_uri": row.source_uri,
    }


PAYMENT_EVENT_TYPES = (
    "payment_plan_generated",
    "payment_updated",
    "payment_settlement_flagged",
)


def _recent_payment_events(session: Session, project_id: str) -> list[dict[str, Any]]:
    rows = session.execute(
        select(OperationEvent)
        .options(joinedload(OperationEvent.actor))
        .where(
            OperationEvent.project_id == project_id,
            OperationEvent.event_type.in_(PAYMENT_EVENT_TYPES),
        )
        .order_by(OperationEvent.occurred_at.desc())
        .limit(20)
    ).scalars()
    return [
        {
            "event_type": row.event_type,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "actor_display_name": row.actor.display_name if row.actor else None,
            "changes": row.changes,
        }
        for row in rows
    ]


def _parse_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PaymentServiceError("invalid_request", f"{field} 必须是 YYYY-MM-DD。", 400)
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise PaymentServiceError("invalid_request", f"{field} 必须是 YYYY-MM-DD。", 400) from None


def _load_project(session: Session, actor: User, project_id: str, *, manage: bool) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise PaymentServiceError("project_not_found", "项目不存在或已被删除。", 404)
    access = project_access(actor, project)
    if not (access.can_manage if manage else access.can_view):
        raise PaymentServiceError("forbidden", "你没有该项目收款的操作权限。", 403)
    return project


def _load_payment(session: Session, project_id: str, milestone_key: str) -> Payment:
    row = session.scalar(
        select(Payment)
        .where(Payment.project_id == project_id, Payment.milestone_key == milestone_key)
        .with_for_update()
    )
    if row is None:
        raise PaymentServiceError("payment_not_found", f"收款里程碑 {milestone_key} 不存在。", 404)
    return row
