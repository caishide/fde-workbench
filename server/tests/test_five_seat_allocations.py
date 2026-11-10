"""F 线 T1：五席位纵向分配明细回归（ADR-011 §3/§5-A 选型 A，任务书 §4 T1）。

- 算式：平台 = T×平台份额%；池 = T×(100−平台份额)%；池内按 lead 30/delivery 50/
  county 10/province 10 分；舍入尾差由平台吸收；Σ明细 = Σ旧四列 = 基数。
- ADR-011 §3.4 六种情形（12 万单）逐分对齐；空缺显式记 0 不省行；
  平台吸收额闭环；原因码闭集。
- 兼容镜像：delivery_settlements 四总额列由明细同事务派生（平台列=残差），
  绕层直写 409；缺行 payable 409；delivery_settlements 恒 20 列（结构钉）。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import (
    DeliverySettlement,
    DispatchRuleVersion,
    DispatchSettlementAllocation,
)
from fde_api.dispatch.settlements import (
    ALLOCATION_REASON_CODES,
    FIVE_SEAT_KEYS,
    allocate_five_seats,
    mark_payable,
    record_receipt_settlements,
)
from fde_api.workbench.models import OperationEvent, Payment, Project

from conftest import INITIAL_PASSWORD, SERVER_ROOT

T120000 = Decimal("120000.00")
# ADR-011 §3.2：平台份额 30% ＋ 池内 lead 30/delivery 50/county 10/province 10
FULL_FIVE_SNAPSHOT = {
    "five_seat": {
        "platform_share_percent": 30,
        "pool_shares": {"lead": 30, "delivery": 50, "county": 10, "province": 10},
    }
}


def _user(username: str) -> User:
    return User(
        username=f"{username}.{uuid4().hex[:8]}",
        display_name=username,
        role="admin",
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )


def _payees(
    lead: str | None,
    delivery: str | None,
    county: str | None,
    province: str | None,
) -> dict[str, str | None]:
    return {
        "platform": None,
        "lead": lead,
        "delivery": delivery,
        "county": county,
        "province": province,
    }


def _context(db_session, *, received: str = "120000.00", milestone: str = "G3"):
    """一包一收一结算（draft，旧四列口径先落，随后由分配层覆写镜像）。"""
    import test_dispatch_p1_r5 as r5

    admin, package = r5._onsite_package(db_session)
    r5.publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    payee_lead = _user("f1.lead")
    payee_delivery = _user("f1.delivery")
    payee_county = _user("f1.county")
    payee_province = _user("f1.province")
    db_session.add_all([payee_lead, payee_delivery, payee_county, payee_province])
    db_session.flush()
    project = db_session.get(Project, package.project_id)
    payment = Payment(
        project_id=package.project_id,
        milestone_key=milestone,
        sow_type="a",
        collects="F 线 T1 里程碑",
        timing="按合同",
        amount=Decimal(received),
        received_amount=Decimal(received),
        received_at=date(2026, 11, 10),
        source_uri=f"fdeops://f-line-t1/{package.package_code}/{milestone}",
        content_hash="c" * 64,
    )
    db_session.add(payment)
    db_session.flush()
    record_receipt_settlements(db_session, actor=admin, project=project, payment=payment)
    db_session.flush()
    settlement = db_session.scalar(
        select(DeliverySettlement).where(
            DeliverySettlement.package_id == package.id,
            DeliverySettlement.settlement_key == milestone,
        )
    )
    assert settlement is not None
    return admin, package, settlement, payment, {
        "lead": payee_lead.id,
        "delivery": payee_delivery.id,
        "county": payee_county.id,
        "province": payee_province.id,
    }


def _allocate(db_session, context, *, vacant: dict[str, str] | None = None):
    admin, package, settlement, payment, payees = context
    seat_payees = _payees(
        None if vacant and "lead" in vacant else payees["lead"],
        payees["delivery"],
        None if vacant and "county" in vacant else payees["county"],
        None if vacant and "province" in vacant else payees["province"],
    )
    return allocate_five_seats(
        db_session,
        payment,
        package,
        actor=admin,
        rule_snapshot=FULL_FIVE_SNAPSHOT,
        seat_payees=seat_payees,
        vacant_reasons=vacant,
    )


def _rows(db_session, settlement_id: str) -> dict[str, DispatchSettlementAllocation]:
    return {
        row.seat_key: row
        for row in db_session.scalars(
            select(DispatchSettlementAllocation).where(
                DispatchSettlementAllocation.settlement_id == settlement_id
            )
        )
    }


def _assert_mirror_sum(settlement: DeliverySettlement, base: Decimal) -> None:
    assert (
        settlement.platform_amount
        + settlement.region_amount
        + settlement.city_amount
        + settlement.delivery_amount
    ) == base


# ---------------------------------------------------------------------------
# 六种情形（ADR-011 §3.4，12 万单逐分）
# ---------------------------------------------------------------------------


def test_scenario_1_full_roster_120k(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees))
    rows = _rows(db_session, settlement.id)
    assert set(rows) == set(FIVE_SEAT_KEYS)
    expected = {
        "platform": Decimal("36000.00"),
        "lead": Decimal("25200.00"),
        "delivery": Decimal("42000.00"),
        "county": Decimal("8400.00"),
        "province": Decimal("8400.00"),
    }
    for seat, amount in expected.items():
        assert rows[seat].amount == amount, seat
        assert rows[seat].status == "paid"
        assert rows[seat].reason_code is None
    assert rows["platform"].payee_user_id is None
    assert rows["platform"].shares_in_pool is None
    assert rows["lead"].shares_in_pool == 30
    assert rows["delivery"].shares_in_pool == 50
    assert rows["lead"].payee_user_id == payees["lead"]
    # 兼容镜像：平台列 = 残差（平台份额＋拉单席位），三列 1:1 镜像
    assert settlement.platform_amount == Decimal("61200.00")
    assert settlement.region_amount == Decimal("8400.00")
    assert settlement.city_amount == Decimal("8400.00")
    assert settlement.delivery_amount == Decimal("42000.00")
    assert sum((row.amount for row in rows.values()), Decimal(0)) == T120000
    _assert_mirror_sum(settlement, T120000)


def test_scenario_2_no_province_partner(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees),
              vacant={"province": "no_province_partner"})
    rows = _rows(db_session, settlement.id)
    assert rows["province"].amount == Decimal("0")
    assert rows["province"].status == "vacant"
    assert rows["province"].reason_code == "no_province_partner"
    assert rows["province"].payee_user_id is None
    assert rows["province"].shares_in_pool == 10  # 沉淀份额依据保留
    assert rows["platform"].amount == Decimal("44400.00")  # 平台吸收 7% T
    assert settlement.delivery_amount == Decimal("42000.00")
    assert sum((row.amount for row in rows.values()), Decimal(0)) == T120000
    _assert_mirror_sum(settlement, T120000)


def test_scenario_3_county_self_sourced_self_delivered(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees),
              vacant={"county": "self_sourced_self_delivered"})
    rows = _rows(db_session, settlement.id)
    assert rows["county"].amount == Decimal("0")
    assert rows["county"].reason_code == "self_sourced_self_delivered"
    assert rows["platform"].amount == Decimal("44400.00")
    assert rows["province"].amount == Decimal("8400.00")
    assert sum((row.amount for row in rows.values()), Decimal(0)) == T120000


def test_scenario_4_province_self_sourced_symmetric(db_session):
    """两级对称（补充拍板）：省级自拉自交同样不拿本级 10 份。"""
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees),
              vacant={"province": "self_sourced_self_delivered"})
    rows = _rows(db_session, settlement.id)
    assert rows["province"].amount == Decimal("0")
    assert rows["province"].reason_code == "self_sourced_self_delivered"
    assert rows["county"].amount == Decimal("8400.00")
    assert rows["platform"].amount == Decimal("44400.00")
    assert sum((row.amount for row in rows.values()), Decimal(0)) == T120000


def test_scenario_5_both_vacant(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees),
              vacant={
                  "county": "self_sourced_self_delivered",
                  "province": "no_province_partner",
              })
    rows = _rows(db_session, settlement.id)
    assert rows["platform"].amount == Decimal("52800.00")
    assert rows["county"].amount == Decimal("0")
    assert rows["province"].amount == Decimal("0")
    assert sum((row.amount for row in rows.values()), Decimal(0)) == T120000


def test_scenario_6_no_sourcer_enterprise_self_sourcing(db_session):
    """企业自来：拉单 30 份沉淀平台，平台实得 51% T。"""
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees),
              vacant={"lead": "no_sourcer"})
    rows = _rows(db_session, settlement.id)
    assert rows["lead"].amount == Decimal("0")
    assert rows["lead"].reason_code == "no_sourcer"
    assert rows["platform"].amount == Decimal("61200.00")
    assert settlement.platform_amount == Decimal("61200.00")  # 镜像平台列含吸收
    assert sum((row.amount for row in rows.values()), Decimal(0)) == T120000
    _assert_mirror_sum(settlement, T120000)


def test_sum_invariant_holds_across_all_vacancy_combos(db_session):
    combos: list[dict[str, str] | None] = [
        None,
        {"province": "no_province_partner"},
        {"county": "self_sourced_self_delivered"},
        {"province": "self_sourced_self_delivered"},
        {"county": "self_sourced_self_delivered", "province": "no_province_partner"},
        {"lead": "no_sourcer"},
    ]
    for vacant in combos:
        admin, package, settlement, payment, payees = _context(db_session)
        _allocate(db_session, (admin, package, settlement, payment, payees), vacant=vacant)
        rows = _rows(db_session, settlement.id)
        assert len(rows) == 5, vacant  # 空缺也不省行
        five_sum = sum((row.amount for row in rows.values()), Decimal(0))
        assert five_sum == settlement.base_amount, vacant
        _assert_mirror_sum(settlement, settlement.base_amount)
        for seat, row in rows.items():
            if row.status == "vacant":
                assert row.amount == Decimal("0")
                assert row.reason_code in ALLOCATION_REASON_CODES


# ---------------------------------------------------------------------------
# 算式与状态闸
# ---------------------------------------------------------------------------


def test_rounding_remainder_absorbed_by_platform(db_session):
    """T=100.01：残差构造下平台行吸收全部舍入尾差，Σ 恒等。"""
    admin, package, settlement, payment, payees = _context(db_session, received="100.01")
    _allocate(db_session, (admin, package, settlement, payment, payees))
    rows = _rows(db_session, settlement.id)
    assert rows["lead"].amount == Decimal("21.00")
    assert rows["delivery"].amount == Decimal("35.00")
    assert rows["county"].amount == Decimal("7.00")
    assert rows["province"].amount == Decimal("7.00")
    assert rows["platform"].amount == Decimal("30.01")  # 非直接 30%（30.00）
    assert sum((row.amount for row in rows.values()), Decimal(0)) == Decimal("100.01")


def test_allocate_requires_draft_state(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    settlement.status = "accrued"
    db_session.flush()
    with pytest.raises(DispatchServiceError) as excinfo:
        _allocate(db_session, (admin, package, settlement, payment, payees))
    assert excinfo.value.code == "allocation_settlement_state"
    assert excinfo.value.status == 409


def test_allocate_without_five_seat_block_fail_closed(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(DispatchServiceError) as excinfo:
        allocate_five_seats(
            db_session,
            payment,
            package,
            actor=admin,
            rule_snapshot={"seat_shares": {"platform": 35}},
            seat_payees=_payees(
                payees["lead"], payees["delivery"], payees["county"], payees["province"]
            ),
        )
    assert excinfo.value.code == "five_seat_snapshot_required"
    assert excinfo.value.status == 422


def test_invalid_pool_shares_rejected(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    bad_sum = {
        "five_seat": {
            "platform_share_percent": 30,
            "pool_shares": {"lead": 40, "delivery": 50, "county": 10, "province": 10},
        }
    }  # Σ=110 ≠ 100
    with pytest.raises(DispatchServiceError) as excinfo:
        allocate_five_seats(
            db_session, payment, package, actor=admin, rule_snapshot=bad_sum,
            seat_payees=_payees(
                payees["lead"], payees["delivery"], payees["county"], payees["province"]
            ),
        )
    assert excinfo.value.code == "invalid_five_seat_snapshot"
    bad_keys = {
        "five_seat": {
            "platform_share_percent": 30,
            "pool_shares": {"lead": 30, "delivery": 50, "county": 10, "region": 10},
        }
    }
    with pytest.raises(DispatchServiceError) as excinfo:
        allocate_five_seats(
            db_session, payment, package, actor=admin, rule_snapshot=bad_keys,
            seat_payees=_payees(
                payees["lead"], payees["delivery"], payees["county"], payees["province"]
            ),
        )
    assert excinfo.value.code == "invalid_five_seat_snapshot"


def test_invalid_reason_code_rejected(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(DispatchServiceError) as excinfo:
        _allocate(db_session, (admin, package, settlement, payment, payees),
                  vacant={"province": "someone_slacked"})
    assert excinfo.value.code == "invalid_vacancy_reason"
    assert excinfo.value.status == 422


def test_platform_cannot_be_vacant(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(DispatchServiceError) as excinfo:
        allocate_five_seats(
            db_session, payment, package, actor=admin, rule_snapshot=FULL_FIVE_SNAPSHOT,
            seat_payees=_payees(
                payees["lead"], payees["delivery"], payees["county"], payees["province"]
            ),
            vacant_reasons={"platform": "no_sourcer"},
        )
    assert excinfo.value.code == "invalid_vacancy_spec"


def test_payee_spec_validation(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    full = _payees(
        payees["lead"], payees["delivery"], payees["county"], payees["province"]
    )
    # 缺键
    with pytest.raises(DispatchServiceError) as excinfo:
        allocate_five_seats(
            db_session, payment, package, actor=admin, rule_snapshot=FULL_FIVE_SNAPSHOT,
            seat_payees={k: v for k, v in full.items() if k != "county"},
        )
    assert excinfo.value.code == "invalid_payee_spec"
    # 平台席位给了 payee
    with pytest.raises(DispatchServiceError) as excinfo:
        allocate_five_seats(
            db_session, payment, package, actor=admin, rule_snapshot=FULL_FIVE_SNAPSHOT,
            seat_payees={**full, "platform": payees["delivery"]},
        )
    assert excinfo.value.code == "invalid_payee_spec"
    # 非空缺席位缺收款人
    with pytest.raises(DispatchServiceError) as excinfo:
        allocate_five_seats(
            db_session, payment, package, actor=admin, rule_snapshot=FULL_FIVE_SNAPSHOT,
            seat_payees={**full, "lead": None},
        )
    assert excinfo.value.code == "invalid_payee_spec"


def test_reallocation_replaces_rows_idempotently(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    ctx = (admin, package, settlement, payment, payees)
    _allocate(db_session, ctx, vacant={"province": "no_province_partner"})
    _allocate(db_session, ctx, vacant={"lead": "no_sourcer"})  # 换一组占用重分配
    rows = _rows(db_session, settlement.id)
    assert len(rows) == 5
    assert rows["lead"].status == "vacant"
    assert rows["province"].status == "paid"
    assert rows["platform"].amount == Decimal("61200.00")
    _assert_mirror_sum(settlement, T120000)


def test_manual_direct_write_to_mirror_409(db_session):
    """绕开分配层直写四总额列 ⇒ 409（任何一侧手工写入一律 409）。"""
    admin, package, settlement, payment, payees = _context(db_session)
    ctx = (admin, package, settlement, payment, payees)
    _allocate(db_session, ctx)
    with pytest.raises(DispatchServiceError) as excinfo:
        record_receipt_settlements(
            db_session, actor=admin, project=db_session.get(Project, package.project_id),
            payment=payment,
        )
    assert excinfo.value.code == "allocation_mirror_protected"
    assert excinfo.value.status == 409


def test_missing_row_blocks_payable_409(db_session):
    """缺一席位行 ⇒ payable 409 allocation_incomplete（空缺也不得省行）。"""
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees))
    province_row = _rows(db_session, settlement.id)["province"]
    db_session.delete(province_row)
    db_session.flush()
    settlement.status = "accrued"
    settlement.acceptance_passed_at = datetime.now(timezone.utc)
    payment.invoice_no = "INV-F1-001"
    db_session.flush()
    with pytest.raises(DispatchServiceError) as excinfo:
        mark_payable(db_session, actor=admin, settlement_id=settlement.id)
    assert excinfo.value.code == "allocation_incomplete"
    assert excinfo.value.status == 409


def test_complete_allocations_allow_payable(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees))
    settlement.status = "accrued"
    settlement.acceptance_passed_at = datetime.now(timezone.utc)
    payment.invoice_no = "INV-F1-002"
    db_session.flush()
    result = mark_payable(db_session, actor=admin, settlement_id=settlement.id)
    assert result["status"] == "payable"


def test_rule_version_provenance_recorded(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    version = DispatchRuleVersion(
        version_no=77,
        status="active",
        rule_snapshot=FULL_FIVE_SNAPSHOT,
        effective_at=datetime.now(timezone.utc),
    )
    db_session.add(version)
    db_session.flush()
    allocate_five_seats(
        db_session,
        payment,
        package,
        actor=admin,
        rule_snapshot=FULL_FIVE_SNAPSHOT,
        seat_payees=_payees(
            payees["lead"], payees["delivery"], payees["county"], payees["province"]
        ),
        rule_version_id=version.id,
    )
    rows = _rows(db_session, settlement.id)
    assert all(row.rule_version_id == version.id for row in rows.values())


def test_operation_events_recorded_for_allocation_and_absorption(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees),
              vacant={"province": "no_province_partner"})
    db_session.flush()
    events = db_session.scalars(
        select(OperationEvent).where(OperationEvent.target_id == package.id)
    ).all()
    types = {event.event_type for event in events}
    assert "five_seat_allocations_recorded" in types
    assert "allocation_absorbed" in types
    absorbed = next(e for e in events if e.event_type == "allocation_absorbed")
    assert absorbed.changes["seat_key"] == "province"
    assert absorbed.changes["reason_code"] == "no_province_partner"
    assert absorbed.changes["absorbed_amount"] == 8400.0


# ---------------------------------------------------------------------------
# 库层形状（CHECK / 唯一索引——直接插行走 IntegrityError）
# ---------------------------------------------------------------------------


def _insert_raw(db_session, settlement_id: str, **overrides) -> None:
    row = DispatchSettlementAllocation(
        settlement_id=settlement_id,
        seat_key=overrides.pop("seat_key", "lead"),
        payee_user_id=overrides.pop("payee_user_id", None),
        shares_in_pool=overrides.pop("shares_in_pool", 30),
        amount=overrides.pop("amount", Decimal("0")),
        status=overrides.pop("status", "vacant"),
        reason_code=overrides.pop("reason_code", "no_sourcer"),
        **overrides,
    )
    db_session.add(row)
    db_session.flush()


def test_check_vacant_amount_nonzero_red(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(IntegrityError):
        _insert_raw(
            db_session, settlement.id, seat_key="province", shares_in_pool=10,
            amount=Decimal("100"), status="vacant", reason_code="no_province_partner",
        )
    db_session.rollback()


def test_check_vacant_without_reason_red(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(IntegrityError):
        _insert_raw(
            db_session, settlement.id, seat_key="province", shares_in_pool=10,
            amount=Decimal("0"), status="vacant", reason_code=None,
        )
    db_session.rollback()


def test_check_paid_with_reason_red(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(IntegrityError):
        _insert_raw(
            db_session, settlement.id, seat_key="lead", payee_user_id=payees["lead"],
            shares_in_pool=30, amount=Decimal("1"), status="paid",
            reason_code="no_sourcer",
        )
    db_session.rollback()


def test_check_vacant_with_payee_red(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(IntegrityError):
        _insert_raw(
            db_session, settlement.id, seat_key="lead", payee_user_id=payees["lead"],
            shares_in_pool=30, amount=Decimal("0"), status="vacant",
            reason_code="no_sourcer",
        )
    db_session.rollback()


def test_check_paid_nonplatform_without_payee_red(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(IntegrityError):
        _insert_raw(
            db_session, settlement.id, seat_key="delivery", payee_user_id=None,
            shares_in_pool=50, amount=Decimal("1"), status="paid", reason_code=None,
        )
    db_session.rollback()


def test_check_platform_row_with_payee_red(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(IntegrityError):
        _insert_raw(
            db_session, settlement.id, seat_key="platform", payee_user_id=payees["lead"],
            shares_in_pool=None, amount=Decimal("1"), status="paid", reason_code=None,
        )
    db_session.rollback()


def test_check_platform_row_with_pool_shares_red(db_session):
    context_platform_shares = {
        "seat_key": "platform",
        "payee_user_id": None,
        "shares_in_pool": 30,
        "amount": Decimal("1"),
        "status": "paid",
        "reason_code": None,
    }
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(IntegrityError):
        _insert_raw(db_session, settlement.id, **context_platform_shares)
    db_session.rollback()


def test_check_seat_key_outside_closure_red(db_session):
    admin, package, settlement, payment, payees = _context(db_session)
    with pytest.raises(IntegrityError):
        _insert_raw(
            db_session, settlement.id, seat_key="region_agent", payee_user_id=None,
            shares_in_pool=10, amount=Decimal("0"), status="vacant",
            reason_code="no_province_partner",
        )
    db_session.rollback()


def test_unique_settlement_seat_prevents_duplicate_accrual(db_session):
    """同席位重复计提 ⇒ 唯一索引红（变异 M4 的判别用例）。"""
    admin, package, settlement, payment, payees = _context(db_session)
    _allocate(db_session, (admin, package, settlement, payment, payees))
    duplicate = DispatchSettlementAllocation(
        settlement_id=settlement.id,
        seat_key="lead",
        payee_user_id=payees["lead"],
        shares_in_pool=30,
        amount=Decimal("1"),
        status="paid",
        reason_code=None,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


# ---------------------------------------------------------------------------
# 结构钉与迁移往返
# ---------------------------------------------------------------------------


def test_delivery_settlements_keeps_20_columns_and_new_layer_shape(db_session):
    """delivery_settlements 恒 20 列（ADR-003 结构钉）；新层列集合逐位钉死。"""
    from sqlalchemy import inspect as sql_inspect

    inspector = sql_inspect(db_session.get_bind())
    settlement_columns = {
        c["name"] for c in inspector.get_columns("delivery_settlements")
    }
    assert len(settlement_columns) == 20
    assert "lead_amount" not in settlement_columns  # 零加列
    allocation_columns = {
        c["name"] for c in inspector.get_columns("dispatch_settlement_allocations")
    }
    assert allocation_columns == {
        "id",
        "settlement_id",
        "seat_key",
        "payee_user_id",
        "shares_in_pool",
        "amount",
        "status",
        "reason_code",
        "rule_version_id",
        "created_at",
        "updated_at",
    }


def test_allocation_table_roundtrip(alembic_config, engine):
    """T1 迁移往返：downgrade 一步即消失、upgrade 回 head 即重建（additive 单表）。"""
    from sqlalchemy import inspect as sql_inspect
    from sqlalchemy import text

    command.downgrade(alembic_config, "f3a9c7e1d5b2")
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = current_schema()"
                )
            )
        }
    assert "dispatch_settlement_allocations" not in names
    assert "delivery_settlements" in names  # 父表不受影响（child-first）

    command.upgrade(alembic_config, "head")
    with engine.connect() as conn:
        names = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables"
                    " WHERE table_schema = current_schema()"
                )
            )
        }
    assert "dispatch_settlement_allocations" in names
