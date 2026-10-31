"""goal-r6 P1 收官回归（派单设计 §8.4 P1-6/P1-7 + §6.6/§7.5 disputes）。

- P1-6：Quote.owner_user_id 归属（创建即落 owner + 归属过滤）。
- §6.6：disputes L1 打开（48h SLA）/ L1 金额上限 422 / 人工裁决 /
  处罚动作 100% 人工（自动侧只产 L0 草稿）。
- §7.5 E5：T+30 对账——应计 vs 实收差异 >±¥1 自动 L0 草稿（幂等）。
- P1-7：留存扫描（3 年/10 年报告只读）+ 维护作业 24h 节流 + handler 注册。
- 超时释放调度挂载：maintenance handler 内含 expire_stale_offers。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.dispatch import maintenance as maintenance_mod
from fde_api.dispatch.disputes import (
    open_dispute,
    resolve_dispute,
    run_l0_reconciliation,
)
from fde_api.dispatch.models import (
    DeliveryPackage,
    DeliverySettlement,
    Dispute,
    DispatchOffer,
)
from fde_api.workbench.models import OperationEvent, Project, Quote

from conftest import SERVER_ROOT


def _user(username: str, role: str = "admin") -> User:
    from fde_api.auth.passwords import hash_password

    from conftest import INITIAL_PASSWORD

    return User(
        username=f"{username}.{uuid4().hex[:8]}",
        display_name=username,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )


def _package_with_settlements(
    db_session,
    *,
    accrued_total: str,
    received_total: str | None,
    milestone_key: str = "G3",
    rule_version: int = 1,
):
    """含一条 accrued 结算与（可选）实收 Payment 的包（复用 r5 helper 族）。"""
    import test_dispatch_p1_r5 as r5

    admin, package = r5._onsite_package(db_session)
    r5._active_rule(db_session, version_no=rule_version)
    r5.publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    settlement = DeliverySettlement(
        package_id=package.id,
        settlement_key=milestone_key,
        base_amount=Decimal(accrued_total),
        platform_amount=Decimal(accrued_total) * Decimal("0.35"),
        region_amount=Decimal(accrued_total) * Decimal("0.05"),
        city_amount=Decimal(accrued_total) * Decimal("0.20"),
        delivery_amount=Decimal(accrued_total) * Decimal("0.40"),
        status="accrued",
        acceptance_passed_at=datetime.now(timezone.utc),
    )
    db_session.add(settlement)
    from fde_api.workbench.models import Payment

    payment = Payment(
        project_id=package.project_id,
        milestone_key=milestone_key,
        sow_type="a",
        collects="r6 里程碑",
        timing="按合同",
        amount=Decimal(received_total or accrued_total),
        received_amount=Decimal(received_total) if received_total else None,
        received_at=datetime(2026, 10, 31).date() if received_total else None,
        source_uri=f"fdeops://goal-r6/{package.package_code}/{milestone_key}",
        content_hash="a" * 64,
    )
    db_session.add(payment)
    db_session.flush()
    return admin, package, settlement, payment


# ---------------------------------------------------------------------------
# P1-6：报价归属
# ---------------------------------------------------------------------------


def test_quote_owner_set_on_create_and_filtered(db_session, client, settings):
    from fde_api.auth.tokens import issue_access_token
    from fde_api.projects.quote_service import create_quote

    seed_admin = _user("r6.owner.admin")
    other = _user("r6.owner.other", role="project_lead")
    db_session.add_all([seed_admin, other])
    from fde_api.workbench.models import IndustryTemplate, IndustryTemplateVersion

    template = IndustryTemplate(
        template_key=f"r6-tpl-{uuid4().hex[:8]}",
        name="r6 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="r6 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    project = Project(
        project_code=f"R6-{uuid4().hex[:6].upper()}",
        name="r6 归属项目",
        enterprise_code=f"r6 企业·制造·{uuid4().hex[:4]}",
        planned_start_date=datetime(2026, 10, 31).date(),
        leader_user_id=seed_admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add(project)
    db_session.commit()  # create_quote 自管独立 session，需先落库可见

    data = create_quote(
        actor=seed_admin,
        project_id=project.id,
        payload={
            "tier": "light",
            "ideal_hours": "25",
            "hourly_rate": 150,
            "cash_cost": 1500,
            "anchor_mode": "steady",
        },
    )
    db_session.expire_all()
    quote = db_session.get(Quote, data["id"])
    assert quote.owner_user_id == seed_admin.id

    # 归属过滤
    from fde_api.dispatch.matching import _in_hand_count  # noqa: F401  (导入健康)

    mine = db_session.scalars(
        select(Quote).where(Quote.owner_user_id == seed_admin.id)
    ).all()
    assert [q.id for q in mine] == [quote.id]
    theirs = db_session.scalars(
        select(Quote).where(Quote.owner_user_id == other.id)
    ).all()
    assert theirs == []


# ---------------------------------------------------------------------------
# §6.6：disputes 打开 / 裁决 / 金额上限
# ---------------------------------------------------------------------------


def test_dispute_open_l1_sla_and_cap(db_session):
    admin, package, _s, _p = _package_with_settlements(
        db_session, accrued_total="10000", received_total="10000"
    )
    dispute = open_dispute(
        db_session,
        actor=admin,
        package_id=package.id,
        layer="L1",
        reason="席位金额有异议",
        settlement_key="G3",
        amount=Decimal("500"),
    )
    db_session.flush()
    assert dispute.status == "open" and dispute.layer == "L1"
    assert dispute.snapshot_hash == package.snapshot_hash  # §2.3 规则 2
    assert dispute.sla_due_at is not None
    due_in = dispute.sla_due_at - datetime.now(timezone.utc)
    assert timedelta(hours=47) < due_in <= timedelta(hours=48)  # 48h SLA

    # L1 金额上限（>¥50,000 → 422 走 L2）
    with pytest.raises(Exception) as excinfo:
        open_dispute(
            db_session, actor=admin, package_id=package.id, layer="L1",
            reason="超额", amount=Decimal("60000"),
        )
    assert getattr(excinfo.value, "code", "") == "amount_above_l1"

    # L0 不能人工打开
    with pytest.raises(Exception) as excinfo:
        open_dispute(
            db_session, actor=admin, package_id=package.id, layer="L0", reason="x"
        )
    assert getattr(excinfo.value, "code", "") == "invalid_request"


def test_dispute_resolve_human_only(db_session):
    admin, package, _s, _p = _package_with_settlements(
        db_session, accrued_total="10000", received_total="10000"
    )
    engineer = _user("r6.eng", role="fde_engineer")
    db_session.add(engineer)
    db_session.flush()
    dispute = open_dispute(
        db_session, actor=admin, package_id=package.id, layer="L1", reason="对账差异"
    )
    db_session.flush()

    # 非平台侧不能裁决（处罚类动作 100% 人工）
    with pytest.raises(Exception) as excinfo:
        resolve_dispute(
            db_session, actor=engineer, dispute_id=dispute.id, resolution="算了"
        )
    assert getattr(excinfo.value, "code", "") == "forbidden"

    resolved = resolve_dispute(
        db_session, actor=admin, dispute_id=dispute.id, resolution="补差额 500 元，人工复核通过"
    )
    db_session.flush()
    assert resolved.status == "resolved" and resolved.handled_by_user_id == admin.id
    assert resolved.resolved_at is not None
    event = db_session.scalar(
        select(OperationEvent).where(
            OperationEvent.event_type == "dispute_resolved",
            OperationEvent.changes["dispute_id"].as_string() == dispute.id,
        )
    )
    assert event is not None


# ---------------------------------------------------------------------------
# §7.5 E5：T+30 对账
# ---------------------------------------------------------------------------


def test_t30_reconciliation_creates_l0_draft(db_session):
    """应计 10000 vs 实收 9500（差 500 > ±1）→ L0 草稿；幂等重跑不再建。"""
    admin, package, _s, _p = _package_with_settlements(
        db_session, accrued_total="10000", received_total="9500"
    )
    result = run_l0_reconciliation(db_session)
    db_session.flush()
    assert result["created"] == 1
    dispute = db_session.scalar(
        select(Dispute).where(Dispute.package_id == package.id)
    )
    assert dispute is not None
    assert dispute.layer == "L0" and dispute.status == "draft"
    assert abs(dispute.amount) == Decimal("500")  # 少收 500 → 实收−应计 = −500

    # 幂等：重跑不重复建
    again = run_l0_reconciliation(db_session)
    assert again["created"] == 0

    # 差异 ≤±1 不建
    admin2, package2, _s2, _p2 = _package_with_settlements(
        db_session, accrued_total="10000", received_total="10000.5",
        milestone_key="G4", rule_version=2,
    )
    run_l0_reconciliation(db_session)
    assert (
        db_session.scalar(select(Dispute.id).where(Dispute.package_id == package2.id))
        is None
    )


# ---------------------------------------------------------------------------
# P1-7：留存扫描 + 维护作业
# ---------------------------------------------------------------------------


def test_retention_scan_report_only(db_session):
    """留存扫描：3 年/10 年超期盘点只读（事件留痕），不删数据。"""
    admin, package, settlement, payment = _package_with_settlements(
        db_session, accrued_total="10000", received_total="10000"
    )
    # 造一条「3 年前」的 offer 与「10 年前」的结算
    db_session.add(
        DispatchOffer(
            package_id=package.id, dispatch_round=90,
            candidate_user_id=admin.id, status="expired",
            offered_at=datetime.now(timezone.utc) - timedelta(days=4 * 365),
            created_at=datetime.now(timezone.utc) - timedelta(days=4 * 365),
        )
    )
    settlement.created_at = datetime.now(timezone.utc) - timedelta(days=11 * 365)
    db_session.flush()

    report = maintenance_mod.retention_scan(db_session)
    assert len(report["matching_over_3y_sample"]) == 1
    assert settlement.id in report["tax_over_10y_settlements_sample"]
    # 只读：数据仍在
    assert db_session.get(DispatchOffer, report["matching_over_3y_sample"][0]) is not None
    event = db_session.scalar(
        select(OperationEvent).where(
            OperationEvent.event_type == "dispatch_retention_scanned"
        )
    )
    assert event is not None and "report-only" in str(event.changes["note"])


def test_maintenance_due_throttle_and_handler(db_session):
    """维护作业：无完成记录 → 到期；completed 后 24h 内不再投；handler 注册可用。"""
    from fde_api.jobs.handlers import get_handler
    from fde_api.jobs.models import BackgroundJob

    maintenance_mod.register_dispatch_maintenance_handler()
    assert get_handler("dispatch.maintenance") is not None

    assert maintenance_mod.maintenance_due(db_session) is True
    db_session.add(
        BackgroundJob(
            job_type="dispatch.maintenance", target_id="daily-x", status="succeeded"
        )
    )
    db_session.flush()
    assert maintenance_mod.maintenance_due(db_session) is False


def test_maintenance_handler_runs_end_to_end(db_session):
    """handler 端到端：超时释放 + 留存 + 对账一体；过期 offer 被释放。"""
    admin, package, _s, _p = _package_with_settlements(
        db_session, accrued_total="10000", received_total="10000"
    )
    offer = DispatchOffer(
        package_id=package.id,
        dispatch_round=package.dispatch_round,
        candidate_user_id=admin.id,
        status="offered",
        match_breakdown={"mode": "assign"},
        offered_at=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    db_session.add(offer)
    db_session.commit()  # handler 用独立 session，先落库可见

    maintenance_mod.register_dispatch_maintenance_handler()
    handler = __import__("fde_api.jobs.handlers", fromlist=["get_handler"]).get_handler(
        "dispatch.maintenance"
    )
    handler(None)  # worker 约定 handler 返回 None；断言副作用
    db_session.expire_all()
    assert db_session.get(DispatchOffer, offer.id).status == "expired"


# ---------------------------------------------------------------------------
# 迁移契约
# ---------------------------------------------------------------------------


def test_head_revision_pinned():
    """HEAD 常量与迁移文件互证（通用断言——head 随轮次前进，不做硬编码）。"""
    import re

    source = (SERVER_ROOT / "tests" / "test_migrations.py").read_text(encoding="utf-8")
    match = re.search(r'HEAD_REVISION = "([0-9a-f]{12})"', source)
    assert match, "HEAD_REVISION 常量缺失"
    head = match.group(1)
    assert any(
        head in p.name for p in (SERVER_ROOT / "migrations" / "versions").iterdir()
    ), f"head {head} 无对应迁移文件"
