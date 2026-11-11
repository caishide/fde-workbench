"""F 线 T6：结算／税／票／对账回归（任务书 §4 T6）。

- 累计预扣扩到多收款主体：同一收款人跨席位（lead/delivery/county）年收入
  进同一累计基数；机构席位（province＝区域服务商）走进项票路径，**不进**
  劳务报酬基数（分流不得混算，ADR-011 §4）。
- 发票前置扩展：paid 的 province 席位 payable 前必须按项目登记进项票
  （G3 ``project_share`` 科目行附 source_uri＋content_hash 凭证指针＋指纹）；
  个人席位不受此闸（走预扣路径）。
- 科目层 ``project_share`` 改引用**五席位明细聚合**（引用不重算语义不变）：
  明细在场 ⇒ 金额＝该收款主体已分配份额合计；无明细存量行回退旧镜像列
  （数据兼容）。
- 区域结算与 county 席位对齐：明细在场 ⇒ 科目行收款人必须＝county 席位
  收款人（张冠李戴 409 保持并细化到席位）。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.commercial.ledger_service import record_revenue_entry
from fde_api.commercial.models import RegionalPartner
from fde_api.commercial.regional_service import record_service_settlement
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import (
    DeliverySettlement,
    DispatchSettlementAllocation,
)
from fde_api.dispatch.settlements import (
    _INSTITUTIONAL_SEAT_KEYS,
    _PERSONAL_SEAT_KEYS,
    allocate_five_seats,
    mark_payable,
    record_receipt_settlements,
)
from fde_api.projects.payment_service import mark_acceptance_passed
from fde_api.workbench.models import Payment

import test_five_seat_allocations as f1
from conftest import INITIAL_PASSWORD

SNAPSHOT = f1.FULL_FIVE_SNAPSHOT


# ---------------------------------------------------------------------------
# 夹具助手（复用 T1 的项目/包/收款链，不建第二套）
# ---------------------------------------------------------------------------


def _ctx(db_session, *, received, milestone):
    """T1 链＋交付席位落位（seat_delivery 未设 ⇒ 计提跳过预扣——T4 同款补位）。"""
    context = f1._context(db_session, received=received, milestone=milestone)
    # record_receipt_settlements 建行时把当时的 package.seat_delivery 拷进
    # 结算行 ⇒ 包与结算行都要补位，计提才会算预扣。
    context[1].seat_delivery = context[4]["delivery"]
    context[2].seat_delivery_user_id = context[4]["delivery"]
    db_session.flush()
    return context


def _payees_map(
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


def _allocate(
    db_session, context, payees: dict[str, str | None], vacant: dict[str, str] | None = None
):
    """按给定收款人分配五席位（platform 恒 None；空缺走 T4 双闸豁免键）。"""
    admin, package, settlement, payment, _ctx_payees = context
    return allocate_five_seats(
        db_session,
        payment,
        package,
        actor=admin,
        rule_snapshot=SNAPSHOT,
        seat_payees=payees,
        vacant_reasons=vacant or {},
        rule_version_id=None,
        confirm_password=INITIAL_PASSWORD,
    )


def _add_milestone(db_session, context, milestone: str, received: str):
    """同一包上补第二个里程碑收款＋结算 draft 行（预扣跨结算累计用）。"""
    admin, package, _settlement, _payment, _payees = context
    project = db_session.get(f1.Project, package.project_id)
    payment = Payment(
        project_id=package.project_id,
        milestone_key=milestone,
        sow_type="a",
        collects="F 线 T6 里程碑",
        timing="按合同",
        amount=Decimal(received),
        received_amount=Decimal(received),
        received_at=date(2026, 11, 10),
        source_uri=f"fdeops://f-line-t6/{package.package_code}/{milestone}",
        content_hash="c" * 64,
    )
    db_session.add(payment)
    db_session.flush()
    record_receipt_settlements(
        db_session, actor=admin, project=project, payment=payment
    )
    db_session.flush()
    row = db_session.scalar(
        select(DeliverySettlement).where(
            DeliverySettlement.package_id == package.id,
            DeliverySettlement.settlement_key == milestone,
        )
    )
    assert row is not None
    return payment, row


def _settlement_rows(db_session, settlement_id: str) -> dict[str, Decimal]:
    return {
        row.seat_key: row.amount
        for row in db_session.scalars(
            select(DispatchSettlementAllocation).where(
                DispatchSettlementAllocation.settlement_id == settlement_id
            )
        )
    }


def _accrue(db_session, context) -> None:
    """验收打标＋计提（走唯一写咽喉，预扣在计提时逐结算计算）。"""
    admin, package, _settlement, _payment, _payees = context
    mark_acceptance_passed(db_session, actor=admin, project_id=package.project_id)


def _get_settlement(db_session, context, milestone: str) -> DeliverySettlement:
    _admin, package, _settlement, _payment, _payees = context
    row = db_session.scalar(
        select(DeliverySettlement).where(
            DeliverySettlement.package_id == package.id,
            DeliverySettlement.settlement_key == milestone,
        )
    )
    db_session.refresh(row)
    return row


def _province_ledger_entry(db_session, context, *, with_evidence: bool = True):
    """按动作③口径为 province 席位登记分成科目行（进项票凭证载体）。"""
    admin, package, settlement, _payment, payees = context
    province_amount = _settlement_rows(db_session, settlement.id)["province"]
    return record_revenue_entry(
        db_session,
        actor=admin,
        subject_type="project_share",
        line_item="platform_share",
        payee_user_id=payees["province"],
        delivery_settlement_id=settlement.id,
        delivery_package_id=package.id,
        amount=float(province_amount),
        source_uri="fdeops://f-line-t6/input-invoice/province" if with_evidence else None,
        content_hash="a" * 64 if with_evidence else None,
        confirm_password=INITIAL_PASSWORD,
    )


def _city_service_partner(db_session, code: str, applicant_user_id: str) -> RegionalPartner:
    """直接落一行 city_service 伙伴（本文件聚焦结算对齐，不测伙伴生命周期）。"""
    row = RegionalPartner(
        id=uuid4().hex,
        partner_code=code,
        region_name="杭州",
        stage="city_service",
        applicant_user_id=applicant_user_id,
        stage_changed_at=datetime.now(timezone.utc),
        exclusive_territory=False,
    )
    db_session.add(row)
    db_session.flush()
    return row


# ---------------------------------------------------------------------------
# 动作①：累计预扣多收款主体
# ---------------------------------------------------------------------------


def test_withholding_accumulates_across_seats_of_same_payee(db_session):
    """同一收款人跨席位年收入进同一累计基数：X 先拿 S1 拉单分成（无预扣行），
    再在 S2 交付——S2 预扣按 X 的全部个人席位收入计算（M13 判据）。"""
    context = _ctx(db_session, received="100000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    lead_x, delivery_y, county_z, province_v = (
        payees["lead"], payees["delivery"], payees["county"], payees["province"]
    )
    _allocate(
        db_session,
        context,
        _payees_map(lead_x, delivery_y, county_z, province_v),
    )
    payment2, settlement2 = _add_milestone(db_session, context, "G8", "100000.00")
    # S2 的交付席位＝X：结算行 delivery 用户也要落 X（record_receipt 拷的是
    # 包上的 seat_delivery＝Y——计提按结算行 delivery 用户算预扣）。
    settlement2.seat_delivery_user_id = lead_x
    _allocate(
        db_session,
        (admin, package, settlement2, payment2, payees),
        _payees_map(delivery_y, lead_x, county_z, province_v),
    )
    _accrue(db_session, context)

    s1 = _get_settlement(db_session, context, "G3")
    s2 = _get_settlement(db_session, context, "G8")
    # S1（Y 交付）：基数＝Y 本结算交付席位 35000 → (35000×0.8−5000)×3% = 690
    assert s1.withholding_tax == Decimal("690.00")
    # S2（X 交付）：基数＝X 的 S2 交付 35000 ＋ S1 拉单 21000（跨席位累计）
    # → 累计应纳税所得 39800 跳 10% 档：3980−2520−0 = 1460 ＞ 690；若无 S1
    # 拉单收入则只有 23000 → 3% 档 690（跨席位累计可辨）。
    assert s2.withholding_tax == Decimal("1460.00")
    assert s2.withholding_tax > s1.withholding_tax


def test_same_settlement_multi_seat_counts_into_base(db_session):
    """同一结算内兼任（lead＋delivery 同人）一并进当期基数（:func:`_payee_settlement_base`）。"""
    context = _ctx(db_session, received="90000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    same = payees["delivery"]  # 让 lead 与 delivery 同收款人（结算行 delivery 用户一致）
    _allocate(
        db_session,
        context,
        _payees_map(same, same, payees["county"], payees["province"]),
    )
    _accrue(db_session, context)

    row = _get_settlement(db_session, context, "G3")
    # 基数＝18900（lead）＋31500（delivery）＝50400 → 应纳税所得 35320 仍在
    # 3% 档（≤36000）：1059.60；若只按 delivery 列＝31500 → 20200×3%＝606（可辨）
    assert row.withholding_tax == Decimal("1059.60")


def test_institutional_seat_excluded_from_withholding_base(db_session):
    """机构席位（province）金额**不进**个人劳务报酬基数（分流不得混算）。"""
    context = _ctx(db_session, received="120000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    same = payees["delivery"]  # 同人持有 delivery＋province 两席位
    _allocate(
        db_session,
        context,
        _payees_map(payees["lead"], same, payees["county"], same),
    )
    _accrue(db_session, context)

    row = _get_settlement(db_session, context, "G3")
    # 基数＝个人席位 42000（delivery）→ (42000×0.8−5000)×3% = 858；若把
    # province 8400 混入基数 → 32320×3% = 969.60（可辨）
    assert row.withholding_tax == Decimal("858.00")


def test_seat_split_constants_shape():
    """分流判据常量钉：个人席位三键、机构席位 province 一键（闭集形状）。"""
    assert _PERSONAL_SEAT_KEYS == ("lead", "delivery", "county")
    assert _INSTITUTIONAL_SEAT_KEYS == ("province",)


# ---------------------------------------------------------------------------
# 动作②：mark_payable 进项票前置（机构席位）
# ---------------------------------------------------------------------------


def test_payable_requires_province_input_invoice(db_session):
    """paid 的 province 席位 payable 前必须登记进项票（无登记 422；
    附凭证指针＋指纹的 G3 科目行在场方可过闸——M14 判据）。"""
    context = _ctx(db_session, received="120000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    _allocate(
        db_session,
        context,
        _payees_map(
            payees["lead"], payees["delivery"], payees["county"], payees["province"]
        ),
    )
    settlement.status = "accrued"
    settlement.acceptance_passed_at = datetime.now(timezone.utc)
    payment.invoice_no = "INV-T6-001"
    db_session.flush()

    with pytest.raises(DispatchServiceError) as exc_info:
        mark_payable(db_session, actor=admin, settlement_id=settlement.id)
    assert exc_info.value.code == "input_invoice_required"
    assert exc_info.value.status == 422

    # 无凭证的科目行（缺 source_uri/content_hash）不满足进项票闸
    _province_ledger_entry(db_session, context, with_evidence=False)
    with pytest.raises(DispatchServiceError) as exc_info:
        mark_payable(db_session, actor=admin, settlement_id=settlement.id)
    assert exc_info.value.code == "input_invoice_required"

    # 附凭证指针＋指纹 ⇒ 过闸
    _province_ledger_entry(db_session, context, with_evidence=True)
    result = mark_payable(db_session, actor=admin, settlement_id=settlement.id)
    assert result["status"] == "payable"


def test_payable_personal_seats_not_blocked_by_invoice_gate(db_session):
    """个人席位（lead/delivery/county）走预扣路径：无任何科目行也可 payable
    （province 空缺——闸不咬个人席位，分流不得反向混算）。"""
    context = _ctx(db_session, received="120000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    _allocate(
        db_session,
        context,
        _payees_map(payees["lead"], payees["delivery"], payees["county"], None),
        vacant={"province": "no_province_partner"},
    )
    settlement.status = "accrued"
    settlement.acceptance_passed_at = datetime.now(timezone.utc)
    payment.invoice_no = "INV-T6-002"
    db_session.flush()
    result = mark_payable(db_session, actor=admin, settlement_id=settlement.id)
    assert result["status"] == "payable"


# ---------------------------------------------------------------------------
# 动作③：科目层 project_share 引用五席位明细聚合
# ---------------------------------------------------------------------------


def test_project_share_amount_references_allocation_aggregation(db_session):
    """明细在场 ⇒ 金额＝该收款主体已分配份额合计；按旧四席位镜像列取数
    一律 409（M15 判据：lead 科目按 delivery 镜像额必被拒）。"""
    context = _ctx(db_session, received="120000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    _allocate(
        db_session,
        context,
        _payees_map(payees["lead"], payees["delivery"], payees["county"], None),
        vacant={"province": "no_province_partner"},
    )
    amounts = _settlement_rows(db_session, settlement.id)
    assert amounts["lead"] == Decimal("25200.00")
    assert settlement.delivery_amount == Decimal("42000.00")

    # lead 收款主体按旧镜像列（delivery 42000）记账 ⇒ 409
    with pytest.raises(Exception) as exc_info:
        record_revenue_entry(
            db_session,
            actor=admin,
            subject_type="project_share",
            line_item="platform_share",
            subject_user_id=payees["lead"],
            delivery_settlement_id=settlement.id,
            amount=42000,
            confirm_password=INITIAL_PASSWORD,
        )
    assert getattr(exc_info.value, "code", None) == "amount_mismatch_settlement"

    # 按 lead 席位聚合额 25200 ⇒ 200，落账金额＝明细聚合
    entry = record_revenue_entry(
        db_session,
        actor=admin,
        subject_type="project_share",
        line_item="platform_share",
        subject_user_id=payees["lead"],
        delivery_settlement_id=settlement.id,
        amount=25200,
        confirm_password=INITIAL_PASSWORD,
    )
    assert Decimal(str(entry["entry"]["amount"])) == Decimal("25200.00")
    assert entry["entry"]["basis"]["allocation_source"] == "dispatch_settlement_allocations"

    # 差一笔也 409（引用不重算语义不变）
    with pytest.raises(Exception) as exc_info:
        record_revenue_entry(
            db_session,
            actor=admin,
            subject_type="project_share",
            line_item="platform_share",
            subject_user_id=payees["county"],
            delivery_settlement_id=settlement.id,
            amount=8401,
            confirm_password=INITIAL_PASSWORD,
        )
    assert getattr(exc_info.value, "code", None) == "amount_mismatch_settlement"


def test_project_share_payee_not_allocated_rejected(db_session):
    """明细在场但收款主体没有已分配份额（含空缺席位）⇒ 409（空缺沉淀不
    产生分成科目）。"""
    context = _ctx(db_session, received="120000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    outsider = User(
        username=f"t6.outsider.{uuid4().hex[:8]}",
        display_name="t6.outsider",
        role="fde_engineer",
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(outsider)
    db_session.flush()
    _allocate(
        db_session,
        context,
        _payees_map(payees["lead"], payees["delivery"], payees["county"], None),
        vacant={"province": "no_province_partner"},
    )
    for subject in (outsider.id, payees["province"]):
        with pytest.raises(Exception) as exc_info:
            record_revenue_entry(
                db_session,
                actor=admin,
                subject_type="project_share",
                line_item="platform_share",
                subject_user_id=subject,
                delivery_settlement_id=settlement.id,
                confirm_password=INITIAL_PASSWORD,
            )
        assert getattr(exc_info.value, "code", None) == "project_share_payee_not_allocated"


def test_project_share_requires_subject_when_allocated(db_session):
    """明细在场 ⇒ 分成科目必须指明收款主体（缺 subject/payee 400）。"""
    context = _ctx(db_session, received="120000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    _allocate(
        db_session,
        context,
        _payees_map(payees["lead"], payees["delivery"], payees["county"], None),
        vacant={"province": "no_province_partner"},
    )
    with pytest.raises(Exception) as exc_info:
        record_revenue_entry(
            db_session,
            actor=admin,
            subject_type="project_share",
            line_item="platform_share",
            delivery_settlement_id=settlement.id,
            confirm_password=INITIAL_PASSWORD,
        )
    assert getattr(exc_info.value, "code", None) == "project_share_payee_required"


def test_project_share_legacy_settlement_keeps_old_behavior(db_session):
    """无明细存量行按旧口径：金额＝delivery 席位镜像额（数据兼容，任务书 §7）。"""
    context = _ctx(db_session, received="120000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    # 不分配（旧四列口径 draft 行）
    legacy_amount = settlement.delivery_amount
    assert legacy_amount > 0
    entry = record_revenue_entry(
        db_session,
        actor=admin,
        subject_type="project_share",
        line_item="platform_share",
        subject_user_id=payees["delivery"],
        delivery_settlement_id=settlement.id,
        amount=float(legacy_amount),
        confirm_password=INITIAL_PASSWORD,
    )
    assert Decimal(str(entry["entry"]["amount"])) == legacy_amount
    assert "allocation_source" not in (entry["entry"]["basis"] or {})


# ---------------------------------------------------------------------------
# 动作④：区域结算与 county 席位对齐
# ---------------------------------------------------------------------------


def test_regional_settlement_aligns_county_payee(db_session):
    """明细在场 ⇒ 科目行收款人必须＝county 席位收款人；delivery 收款人的
    科目行张冠李戴 ⇒ 409 county_payee_mismatch。"""
    context = _ctx(db_session, received="120000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    _allocate(
        db_session,
        context,
        _payees_map(payees["lead"], payees["delivery"], payees["county"], None),
        vacant={"province": "no_province_partner"},
    )
    amounts = _settlement_rows(db_session, settlement.id)

    county_entry = record_revenue_entry(
        db_session,
        actor=admin,
        subject_type="project_share",
        line_item="platform_share",
        subject_user_id=payees["county"],
        delivery_settlement_id=settlement.id,
        delivery_package_id=package.id,
        amount=float(amounts["county"]),
        confirm_password=INITIAL_PASSWORD,
    )
    partner = _city_service_partner(db_session, f"t6.county.{uuid4().hex[:6]}", admin.id)
    result = record_service_settlement(
        db_session,
        actor=admin,
        partner_id=partner.id,
        project_id=package.project_id,
        ledger_entry_id=county_entry["entry"]["id"],
        confirm_password=INITIAL_PASSWORD,
    )
    assert result["changed"] is True

    delivery_entry = record_revenue_entry(
        db_session,
        actor=admin,
        subject_type="project_share",
        line_item="platform_share",
        subject_user_id=payees["delivery"],
        delivery_settlement_id=settlement.id,
        delivery_package_id=package.id,
        amount=float(amounts["delivery"]),
        confirm_password=INITIAL_PASSWORD,
    )
    with pytest.raises(Exception) as exc_info:
        record_service_settlement(
            db_session,
            actor=admin,
            partner_id=partner.id,
            project_id=package.project_id,
            ledger_entry_id=delivery_entry["entry"]["id"],
            confirm_password=INITIAL_PASSWORD,
        )
    assert getattr(exc_info.value, "code", None) == "county_payee_mismatch"


def test_regional_settlement_legacy_without_allocations_unchanged(db_session):
    """无明细存量行按旧口径：项目归属校验照旧、不做席位对齐（数据兼容）。"""
    context = _ctx(db_session, received="120000.00", milestone="G3")
    admin, package, settlement, payment, payees = context
    entry = record_revenue_entry(
        db_session,
        actor=admin,
        subject_type="project_share",
        line_item="platform_share",
        subject_user_id=payees["delivery"],
        delivery_settlement_id=settlement.id,
        delivery_package_id=package.id,
        amount=float(settlement.delivery_amount),
        confirm_password=INITIAL_PASSWORD,
    )
    partner = _city_service_partner(db_session, f"t6.legacy.{uuid4().hex[:6]}", admin.id)
    result = record_service_settlement(
        db_session,
        actor=admin,
        partner_id=partner.id,
        project_id=package.project_id,
        ledger_entry_id=entry["entry"]["id"],
        confirm_password=INITIAL_PASSWORD,
    )
    assert result["changed"] is True
