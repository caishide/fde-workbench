"""delivery_settlements 席位级结算服务（设计 §7.2/§7.3/§7.4，P0-4）。

分工铁律（§2.4 理由三）：Payment = 客户↔平台收款，语义零改动；本模块 =
平台↔FDE 分账，两表以 package→project 关联，资金流方向相反，绝不合并。

- 基数 = 里程碑实收回款（§7.3-1），不从分成池二次扣工时（§7.3-2）。
- 四席位 35/5/20/40；冷启动该城前 3 单 40/5/15/40（上浮 5pp 自城市合伙人
  扣，§7.1 建议，需确认）。比例取值：active 规则版本快照优先，回退
  DISPATCH_CONSTANTS（§6.2：改比例 = 新版本 + 公示，禁止硬编码散落）。
- 状态机 draft → accrued → payable → paid，任一方争议 → disputed。
  accrued 双条件：对应 Payment 实收 + G8 过门（acceptance_passed_at 非空）。
- 个税按劳务报酬累计预扣法（§7.4 公式）；率表以税务总局 2025 年第 16 号
  公告原文为准（附录 C 待确认项，代码常量集中此处便于法务复核后一次替换）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping

from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.dispatch.cities import city_from_enterprise_code, package_client_city
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import (
    DeliveryPackage,
    DeliverySettlement,
    DispatchSettlementAllocation,
)
from fde_api.dispatch.rules import active_rule_snapshot
from fde_api.projects.events import record_event
from fde_api.system_configuration import DISPATCH_CONSTANTS
from fde_api.workbench.models import Payment, Project

TWO_PLACES = Decimal("0.01")
SEAT_KEYS = ("platform", "region", "city", "delivery")

# ---------------------------------------------------------------------------
# 五席位百份制（ADR-011 §3 唯一业务口径；规则唯一成文处 =
# docs/commercialization/rules/five-seat-split-rules.md，F 线 T1）。
# 比例数值**不在本模块**：来自规则版本快照的 five_seat 块（H3：比例只落快照，
# T2 迁移种入上线前初始基线版本；缺快照 fail-closed 422）。
# ---------------------------------------------------------------------------

FIVE_SEAT_KEYS = ("platform", "lead", "delivery", "county", "province")
# 空缺沉淀原因码闭集（扩展须同步改闭集＋规则文件 JSON 块＋机器闸——任务书 T4）
ALLOCATION_REASON_CODES = (
    "no_province_partner",
    "self_sourced_self_delivered",
    "no_sourcer",
)
ALLOCATION_STATUSES = ("paid", "vacant")
_POOL_SEAT_KEYS = ("lead", "delivery", "county", "province")
# 兼容镜像映射：旧四列 ← 五席位（平台列=残差吸收拉单与空缺，其余三列 1:1）
_MIRROR_COLUMNS = {"region": "province", "city": "county", "delivery": "delivery"}

# §7.4 累计预扣法：劳务报酬预扣率表（累计应纳税所得额 → 预扣率 / 速算扣除数）。
# 率表口径：税务总局 2025 年第 16 号公告（设计文档明确「率表不抄进文档，
# 实现以公告原文为准」——本常量即实现侧唯一落点，法务确认后只改这里）。
WITHHOLDING_BRACKETS: tuple[tuple[int, int | None, Decimal, Decimal], ...] = (
    (0, 36_000, Decimal("0.03"), Decimal(0)),
    (36_000, 144_000, Decimal("0.10"), Decimal(2520)),
    (144_000, 300_000, Decimal("0.20"), Decimal(16920)),
    (300_000, 420_000, Decimal("0.25"), Decimal(31920)),
    (420_000, 660_000, Decimal("0.30"), Decimal(52920)),
    (660_000, 960_000, Decimal("0.35"), Decimal(85920)),
    (960_000, None, Decimal("0.45"), Decimal(181920)),
)

# §7.4 公式常数：累计费用 = 累计收入 × 20%；累计减除费用 = 5000 元/月
_EXPENSE_RATE = Decimal("0.20")
_MONTHLY_DEDUCTION = Decimal(5000)


def _money(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def seat_shares_for(session: Session, package: DeliveryPackage) -> dict[str, int]:
    """席位份额 %：active 版本快照优先（§7.3-3），回退 DISPATCH_CONSTANTS。
    冷启动判定 = 该城（包侧客户城，留注⑤ 终版口径）已接单序号 ≤ 前 N 单（§7.1）。"""
    snapshot = active_rule_snapshot(session)
    base_shares = (snapshot or {}).get("seat_shares") or DISPATCH_CONSTANTS["seat_shares"]
    cold_shares = (snapshot or {}).get("cold_start_seat_shares") or (
        DISPATCH_CONSTANTS["cold_start_seat_shares"]
    )
    cold_orders = (snapshot or {}).get("cold_start_first_orders") or (
        DISPATCH_CONSTANTS["cold_start_first_orders"]
    )
    if _city_order_rank(session, package) <= cold_orders:
        return {key: int(cold_shares[key]) for key in SEAT_KEYS}
    return {key: int(base_shares[key]) for key in SEAT_KEYS}


def _city_order_rank(session: Session, package: DeliveryPackage) -> int:
    """该包在同城的接单序号（1 起）。城 = **包侧客户城**（企业代号第三段，
    §3.1 三段式——留注⑤ 终版切换：home_city 代理随 B-④ 城市拍板退役，
    与 cities.package_client_city 同口径）。无城可判 → 返回大数（不触发冷启动）。"""
    city = package_client_city(session, package)
    if not city:
        return 1 << 30
    earlier_rows = session.execute(
        select(DeliveryPackage.id, Project.enterprise_code)
        .join(Project, Project.id == DeliveryPackage.project_id)
        .where(
            DeliveryPackage.id != package.id,
            DeliveryPackage.dispatch_status == "accepted",
            DeliveryPackage.accepted_at.is_not(None),
            DeliveryPackage.accepted_at
            < (package.accepted_at or datetime.now(timezone.utc)),
        )
    ).all()
    earlier = sum(
        1 for _row_id, code in earlier_rows if city_from_enterprise_code(code) == city
    )
    return earlier + 1


def split_four_seats(
    base_amount: Decimal, shares: dict[str, int]
) -> dict[str, Decimal]:
    """四席位金额（分）：区域/城市/交付按比例四舍五入，平台吸收舍入尾差，
    保证 Σ四席位 = 基数（审计口径）。"""
    if base_amount < 0:
        raise DispatchServiceError("invalid_request", "计提基数不能为负数。")
    region = _money(base_amount * Decimal(shares["region"]) / 100)
    city = _money(base_amount * Decimal(shares["city"]) / 100)
    delivery = _money(base_amount * Decimal(shares["delivery"]) / 100)
    platform = _money(base_amount - region - city - delivery)
    return {"platform": platform, "region": region, "city": city, "delivery": delivery}


def _five_seat_shares(
    rule_snapshot: Mapping[str, Any] | None,
) -> tuple[int, dict[str, int]]:
    """从规则版本快照读五席位比例（``five_seat`` 块，字段名与规则文件机器
    可读块一致）。快照缺块 ⇒ fail-closed 422——比例不在代码里硬编码（H3），
    T2 由初始基线版本落库（``platform_share_percent`` ＋ ``pool_shares``）。"""
    block = (rule_snapshot or {}).get("five_seat")
    if not isinstance(block, Mapping):
        raise DispatchServiceError(
            "five_seat_snapshot_required",
            "规则快照缺 five_seat 块：五席位比例只落规则版本快照"
            "（T2 上线前初始基线版本），不在代码硬编码。",
            422,
        )
    platform_pct = block.get("platform_share_percent")
    pool = block.get("pool_shares")
    if not isinstance(platform_pct, int) or isinstance(platform_pct, bool) or not (
        0 <= platform_pct <= 100
    ):
        raise DispatchServiceError(
            "invalid_five_seat_snapshot", "platform_share_percent 须为 0–100 整数。", 422
        )
    if not isinstance(pool, Mapping) or set(pool.keys()) != set(_POOL_SEAT_KEYS):
        raise DispatchServiceError(
            "invalid_five_seat_snapshot",
            "pool_shares 须恰含 lead/delivery/county/province 四键。",
            422,
        )
    shares: dict[str, int] = {}
    for key in _POOL_SEAT_KEYS:
        value = pool[key]
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 100:
            raise DispatchServiceError(
                "invalid_five_seat_snapshot", f"pool_shares.{key} 须为 0–100 整数。", 422
            )
        shares[key] = value
    # 规则文件机器可读块口径：``pool_total_shares``=100，池内四份数是**池内**
    # 百份制（lead 30 + delivery 50 + county 10 + province 10 = 100）；池占
    # 基数比例 = 100 - platform_share_percent（30 + 70 = 100）。两个 100
    # 不是一个 100——平台份额不与池内份数相加。
    if sum(shares.values()) != 100:
        raise DispatchServiceError(
            "invalid_five_seat_snapshot",
            "Σ池内四份数必须 = 100（pool_total_shares 百份制；平台份额另计）。",
            422,
        )
    return platform_pct, shares


def allocate_five_seats(
    session: Session,
    payment: Payment,
    package: DeliveryPackage,
    *,
    actor: User,
    rule_snapshot: Mapping[str, Any] | None = None,
    seat_payees: Mapping[str, str | None],
    vacant_reasons: Mapping[str, str] | None = None,
    rule_version_id: str | None = None,
) -> list[DispatchSettlementAllocation]:
    """五席位分配原语（ADR-011 §3.2 算式，F 线 T1）。

    - 基数 = 结算行 ``base_amount``（里程碑实收，不重算不二次扣）；
      平台 = T×平台份额%；池 = T×(100−平台份额)%；池内按份数分。
    - 空缺席位**显式记 0 不省行**（``status='vacant'`` ＋原因码），吸收额进
      平台行（平台列 = 残差：平台份额＋拉单席位＋全部空缺吸收＋舍入尾差）。
    - 同一事务内把 ``delivery_settlements`` 四总额列改写为明细的兼容镜像，
      并断言 **Σ明细 = Σ旧四列 = 基数**；缺行/绕层直写分别 409。
    - ``seat_payees``：席位 → 收款人 user id（platform 恒 None——平台无
      user 行）；``vacant_reasons``：席位 → 原因码（闭集
      ``ALLOCATION_REASON_CODES``）。谁 vacant 的业务判定归 T3（拉单确权）/
      T4（空缺人工确认），本原语只按给定占用规格记账。
    """
    settlement = session.scalar(
        select(DeliverySettlement).where(
            DeliverySettlement.package_id == package.id,
            DeliverySettlement.settlement_key == payment.milestone_key,
        )
    )
    if settlement is None:
        raise DispatchServiceError(
            "settlement_not_found",
            "结算行不存在：先经收款回填（record_receipt_settlements）生成 draft 行。",
            404,
        )
    if settlement.status != "draft":
        raise DispatchServiceError(
            "allocation_settlement_state",
            "只有 draft 结算可（重）分配：accrued 起金额已进预扣与对账口径。",
            409,
        )
    base_amount = settlement.base_amount
    platform_pct, pool_shares = _five_seat_shares(rule_snapshot)

    vacant = dict(vacant_reasons or {})
    bad_vacant = set(vacant) - set(_POOL_SEAT_KEYS)
    if bad_vacant:
        raise DispatchServiceError(
            "invalid_vacancy_spec",
            f"空缺席位只能是非平台席位，非法键：{sorted(bad_vacant)}。",
            422,
        )
    for seat, code in vacant.items():
        if code not in ALLOCATION_REASON_CODES:
            raise DispatchServiceError(
                "invalid_vacancy_reason",
                f"原因码 {code!r} 不在闭集 {ALLOCATION_REASON_CODES}。",
                422,
            )
    if set(seat_payees.keys()) != set(FIVE_SEAT_KEYS):
        raise DispatchServiceError(
            "invalid_payee_spec",
            "seat_payees 必须恰含五席位键（platform/lead/delivery/county/province）。",
            422,
        )
    if seat_payees["platform"] is not None:
        raise DispatchServiceError(
            "invalid_payee_spec", "平台席位无 user 收款人（payee 恒 None）。", 422
        )
    for seat in FIVE_SEAT_KEYS:
        if seat == "platform":
            continue
        payee = seat_payees[seat]
        if seat in vacant:
            if payee is not None:
                raise DispatchServiceError(
                    "invalid_payee_spec",
                    f"空缺席位 {seat} 不得有收款人（payee 与 vacant 互斥）。",
                    422,
                )
        elif not isinstance(payee, str) or not payee.strip():
            raise DispatchServiceError(
                "invalid_payee_spec",
                f"非空缺席位 {seat} 必须有非空收款人 user id。",
                422,
            )

    if base_amount < 0:
        raise DispatchServiceError("invalid_request", "计提基数不能为负数。")
    pool_total = base_amount * Decimal(100 - platform_pct) / 100
    amounts: dict[str, Decimal] = {}
    for seat in _POOL_SEAT_KEYS:
        if seat in vacant:
            # ADR-011 §3.5-1：显式记 0，不得省行；份额由平台吸收（§3.5-2）
            amounts[seat] = Decimal("0")
        else:
            amounts[seat] = _money(pool_total * Decimal(pool_shares[seat]) / 100)
    platform_amount = _money(base_amount - sum(amounts.values(), Decimal(0)))

    five_sum = platform_amount + sum(amounts.values(), Decimal(0))
    if five_sum != base_amount:  # 审计硬断言（Σ席位=基数，残差构造下恒真）
        raise DispatchServiceError(
            "allocation_sum_invariant",
            f"Σ五席位 {five_sum} ≠ 基数 {base_amount}。",
            500,
        )

    # 重分配 = 整组替换（幂等刷新；审计走 operation_events 留痕）
    for old in session.scalars(
        select(DispatchSettlementAllocation).where(
            DispatchSettlementAllocation.settlement_id == settlement.id
        )
    ):
        session.delete(old)
    session.flush()  # 先放行 (settlement, seat) 唯一索引，再落新组
    rows = [
        DispatchSettlementAllocation(
            settlement_id=settlement.id,
            seat_key="platform",
            payee_user_id=None,
            shares_in_pool=None,
            amount=platform_amount,
            status="paid",
            rule_version_id=rule_version_id,
        )
    ]
    for seat in _POOL_SEAT_KEYS:
        rows.append(
            DispatchSettlementAllocation(
                settlement_id=settlement.id,
                seat_key=seat,
                payee_user_id=None if seat in vacant else seat_payees[seat],
                shares_in_pool=pool_shares[seat],
                amount=amounts[seat],
                status="vacant" if seat in vacant else "paid",
                reason_code=vacant.get(seat),
                rule_version_id=rule_version_id,
            )
        )
    session.add_all(rows)

    # 兼容镜像（同一事务）：平台列 = 残差（平台份额＋拉单席位＋全部空缺吸收＋
    # 舍入尾差）；region/city/delivery 三列 1:1 镜像 province/county/delivery。
    # 注意平台**行**（amounts 残差 = 基数−四池席位）与平台**镜像列**（基数−
    # 三镜像列）是两个残差——旧四列恒等式要求后者，前者只是席位行金额。
    settlement.platform_amount = _money(
        base_amount - amounts["province"] - amounts["county"] - amounts["delivery"]
    )
    settlement.region_amount = amounts["province"]
    settlement.city_amount = amounts["county"]
    settlement.delivery_amount = amounts["delivery"]
    mirror_sum = (
        settlement.platform_amount
        + settlement.region_amount
        + settlement.city_amount
        + settlement.delivery_amount
    )
    if mirror_sum != base_amount:  # 第二断言：Σ旧四列 = 基数
        raise DispatchServiceError(
            "allocation_mirror_invariant",
            f"Σ旧四列 {mirror_sum} ≠ 基数 {base_amount}（镜像派生失真）。",
            500,
        )
    session.flush()

    absorbed = {
        seat: _money(pool_total * Decimal(pool_shares[seat]) / 100)
        for seat in vacant
    }
    record_event(
        session,
        actor,
        "five_seat_allocations_recorded",
        package,
        {
            "settlement_key": settlement.settlement_key,
            "base_amount": float(base_amount),
            "platform_share_percent": platform_pct,
            "pool_shares": dict(pool_shares),
            "paid_amounts": {
                "platform": float(platform_amount),
                **{s: float(amounts[s]) for s in _POOL_SEAT_KEYS if s not in vacant},
            },
            "vacant": {seat: code for seat, code in vacant.items()},
            "absorbed_amounts": {seat: float(v) for seat, v in absorbed.items()},
            "mirror": {
                "platform_amount": float(settlement.platform_amount),
                "region_amount": float(settlement.region_amount),
                "city_amount": float(settlement.city_amount),
                "delivery_amount": float(settlement.delivery_amount),
            },
            "rule_version_id": rule_version_id,
        },
    )
    for seat, value in absorbed.items():
        # ADR-011 §3.5-2/§3.5-4：吸收闭环逐席位留痕（金额等式 = 池 × 份数/100）
        record_event(
            session,
            actor,
            "allocation_absorbed",
            package,
            {
                "settlement_key": settlement.settlement_key,
                "seat_key": seat,
                "reason_code": vacant[seat],
                "shares_in_pool": pool_shares[seat],
                "absorbed_amount": float(value),
            },
        )
    return rows


def assert_allocations_complete(session: Session, settlement_id: str) -> None:
    """五席位明细行数守卫：有明细的结算缺任何一行 ⇒ 409（空缺也不得省行，
    ADR-011 §3.5-1；无明细的存量行按旧口径放行——任务书 §7 数据兼容）。"""
    count = session.scalar(
        select(func.count())
        .select_from(DispatchSettlementAllocation)
        .where(DispatchSettlementAllocation.settlement_id == settlement_id)
    )
    if count is not None and count > 0 and count != len(FIVE_SEAT_KEYS):
        raise DispatchServiceError(
            "allocation_incomplete",
            f"五席位明细行数 {count} ≠ {len(FIVE_SEAT_KEYS)}：空缺席位也必须显式记 0。",
            409,
        )


def compute_withholding(
    session: Session,
    *,
    delivery_user_id: str,
    current_amount: Decimal,
    now: datetime | None = None,
) -> Decimal:
    """§7.4 累计预扣法：
    本期应预扣 = (累计收入 − 累计费用(收入×20%) − 累计减除(5000×月份数))
                 × 预扣率 − 速算扣除数 − 累计已预扣，下限 0。

    累计口径 = 该交付方本自然年已到 accrued/payable/paid 的席位结算 +
    本笔 current_amount；月份数 = 这些结算的验收月（含本月）去重计数。
    """
    now = now or datetime.now(timezone.utc)
    past_rows = session.execute(
        select(
            DeliverySettlement.delivery_amount,
            DeliverySettlement.withholding_tax,
            func.coalesce(
                DeliverySettlement.acceptance_passed_at, DeliverySettlement.created_at
            ),
        ).where(
            DeliverySettlement.seat_delivery_user_id == delivery_user_id,
            DeliverySettlement.status.in_(("accrued", "payable", "paid")),
            extract("year", DeliverySettlement.created_at) == now.year,
        )
    ).all()
    cumulative_income = Decimal(current_amount) + sum(
        (row[0] for row in past_rows), Decimal(0)
    )
    cumulative_withheld = sum((row[1] for row in past_rows), Decimal(0))
    months = {row[2].month for row in past_rows} | {now.month}
    taxable_base = max(
        Decimal(0),
        cumulative_income * (1 - _EXPENSE_RATE) - _MONTHLY_DEDUCTION * len(months),
    )
    for floor, ceiling, rate, quick in WITHHOLDING_BRACKETS:
        if taxable_base < floor:
            continue
        if ceiling is None or taxable_base <= ceiling:
            full_tax = _money(taxable_base * rate) - quick
            return max(Decimal(0), _money(full_tax - cumulative_withheld))
    return Decimal(0)


def record_receipt_settlements(
    session: Session, *, actor: User, project: Project, payment: Payment
) -> int:
    """收款实收回填钩子（payment_service.update_payment 事务内调用）：
    为项目下已发布/已接的交付包 upsert 结算 draft 行（基数 = 实收）。
    无交付包 → 纯 no-op（存量 A 组路径零感知，催款逻辑不动）。"""
    if payment.received_amount is None:
        return 0
    packages = session.scalars(
        select(DeliveryPackage).where(
            DeliveryPackage.project_id == project.id,
            DeliveryPackage.dispatch_status.in_(("published", "offered", "assigned", "accepted")),
        )
    ).all()
    created = 0
    for package in packages:
        shares = seat_shares_for(session, package)
        amounts = split_four_seats(payment.received_amount, shares)
        row = session.scalar(
            select(DeliverySettlement).where(
                DeliverySettlement.package_id == package.id,
                DeliverySettlement.settlement_key == payment.milestone_key,
            )
        )
        if row is None:
            row = DeliverySettlement(
                package_id=package.id,
                snapshot_hash=package.snapshot_hash,
                settlement_key=payment.milestone_key,
                base_amount=payment.received_amount,
                seat_delivery_user_id=package.seat_delivery,
                platform_amount=amounts["platform"],
                region_amount=amounts["region"],
                city_amount=amounts["city"],
                delivery_amount=amounts["delivery"],
            )
            session.add(row)
            created += 1
        else:
            # 五席位明细在场 ⇒ 四总额列是明细派生的兼容镜像，绕层直写一律 409
            # （刷新走 allocate_five_seats 重分配）。无明细的存量行按旧口径放行。
            allocation_count = session.scalar(
                select(func.count())
                .select_from(DispatchSettlementAllocation)
                .where(DispatchSettlementAllocation.settlement_id == row.id)
            )
            if allocation_count:
                raise DispatchServiceError(
                    "allocation_mirror_protected",
                    "该结算已建五席位明细：总额列为明细派生镜像，禁止直写；"
                    "请通过 allocate_five_seats 重新分配。",
                    409,
                )
            row.base_amount = payment.received_amount
            row.platform_amount = amounts["platform"]
            row.region_amount = amounts["region"]
            row.city_amount = amounts["city"]
            row.delivery_amount = amounts["delivery"]
        session.flush()
        record_event(
            session,
            actor,
            "settlement_draft_recorded",
            package,
            {
                "settlement_key": payment.milestone_key,
                "base_amount": float(payment.received_amount),
                "shares": shares,
                "delivery_amount": float(amounts["delivery"]),
                "status": row.status,
            },
        )
    return len(packages)


def accrue_settlements_for_project(
    session: Session, *, actor: User, project_id: str
) -> int:
    """G8 过门联动（gate_service decide 事务内调用）：把「实收 + 验收双满足」
    的 draft 行推进 accrued，冗余 acceptance_passed_at 并计提当期预扣。"""
    payments = {
        row.milestone_key: row
        for row in session.scalars(
            select(Payment)
            .where(
                Payment.project_id == project_id,
                Payment.received_amount.is_not(None),
                Payment.acceptance_passed_at.is_not(None),
            )
            # 累计预扣按里程碑键序推进，计提顺序可复算（§7.4 审计口径）
            .order_by(Payment.milestone_key)
        )
    }
    if not payments:
        return 0
    packages = session.scalars(
        select(DeliveryPackage).where(DeliveryPackage.project_id == project_id)
    ).all()
    accrued = 0
    for package in packages:
        for key, payment in payments.items():
            row = session.scalar(
                select(DeliverySettlement).where(
                    DeliverySettlement.package_id == package.id,
                    DeliverySettlement.settlement_key == key,
                    DeliverySettlement.status == "draft",
                )
            )
            if row is None:
                continue
            passed_at = payment.acceptance_passed_at
            if passed_at is None:
                continue
            # 先算后改：compute_withholding 内的 SELECT 会触发 autoflush，
            # 若先把本行置 accrued，本行会混进「累计已计提」口径被双计。
            withholding = Decimal(0)
            if row.seat_delivery_user_id is not None:
                withholding = compute_withholding(
                    session,
                    delivery_user_id=row.seat_delivery_user_id,
                    current_amount=row.delivery_amount,
                    now=passed_at,
                )
            row.acceptance_passed_at = passed_at
            row.status = "accrued"
            row.withholding_tax = withholding
            accrued += 1
            session.flush()
            record_event(
                session,
                actor,
                "settlement_accrued",
                package,
                {
                    "settlement_key": key,
                    "base_amount": float(row.base_amount),
                    "withholding_tax": float(row.withholding_tax),
                    "acceptance_passed_at": passed_at.isoformat(),
                },
            )
    return accrued


def _load_settlement(session: Session, settlement_id: str) -> DeliverySettlement:
    row = session.get(DeliverySettlement, settlement_id)
    if row is None:
        raise DispatchServiceError("settlement_not_found", "结算行不存在。", 404)
    return row


def _package_or_404(session: Session, row: DeliverySettlement) -> DeliveryPackage:
    package = session.get(DeliveryPackage, row.package_id)
    if package is None:
        # package_id 外键 RESTRICT，父行被删才会走到这里
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    return package


def _linked_payment(session: Session, row: DeliverySettlement) -> Payment | None:
    package = session.get(DeliveryPackage, row.package_id)
    if package is None:
        return None
    return session.scalar(
        select(Payment).where(
            Payment.project_id == package.project_id,
            Payment.milestone_key == row.settlement_key,
        )
    )


def mark_payable(session: Session, *, actor: User, settlement_id: str) -> dict[str, Any]:
    """accrued → payable：发票前置校验（§7.5——对应里程碑发票已登记）。"""
    row = _load_settlement(session, settlement_id)
    if row.status != "accrued":
        raise DispatchServiceError(
            "invalid_settlement_state", "只有 accrued 结算可转 payable。", 409
        )
    payment = _linked_payment(session, row)
    if payment is None or not payment.invoice_no:
        raise DispatchServiceError(
            "invoice_required", "发票前置校验未过：对应里程碑尚未登记发票。", 422
        )
    # 五席位明细在场 ⇒ 缺任何一行即拒绝（空缺也显式记 0，不得省行）
    assert_allocations_complete(session, row.id)
    row.status = "payable"
    session.flush()
    record_event(
        session,
        actor,
        "settlement_payable",
        _package_or_404(session, row),
        {"settlement_key": row.settlement_key},
    )
    return {"id": row.id, "status": row.status, "settlement_key": row.settlement_key}


def mark_paid(
    session: Session,
    *,
    actor: User,
    settlement_id: str,
    paid_proof_source_uri: str,
    paid_at: datetime | None = None,
) -> dict[str, Any]:
    """payable → paid：打款凭证只存指针（红线：不存本体）。"""
    row = _load_settlement(session, settlement_id)
    if row.status != "payable":
        raise DispatchServiceError(
            "invalid_settlement_state", "只有 payable 结算可转 paid。", 409
        )
    if not isinstance(paid_proof_source_uri, str) or not paid_proof_source_uri.strip():
        raise DispatchServiceError(
            "invalid_request", "paid_proof_source_uri 必须是非空指针。"
        )
    row.status = "paid"
    row.paid_proof_source_uri = paid_proof_source_uri.strip()
    row.paid_at = paid_at or datetime.now(timezone.utc)
    session.flush()
    record_event(
        session,
        actor,
        "settlement_paid",
        _package_or_404(session, row),
        {
            "settlement_key": row.settlement_key,
            "paid_proof_source_uri": row.paid_proof_source_uri,
            "paid_at": row.paid_at.isoformat(),
        },
    )
    return {"id": row.id, "status": row.status, "settlement_key": row.settlement_key}


def mark_disputed(
    session: Session, *, actor: User, settlement_id: str, reason: str
) -> dict[str, Any]:
    """任一方发起争议（§6.6 L0-L3 仲裁入口；disputes 表随后续轮落位）。"""
    row = _load_settlement(session, settlement_id)
    if row.status == "paid":
        raise DispatchServiceError(
            "invalid_settlement_state", "已打款结算不能转 disputed，走人工对账。", 409
        )
    if not isinstance(reason, str) or not reason.strip():
        raise DispatchServiceError("invalid_request", "争议原因必填。")
    row.status = "disputed"
    session.flush()
    record_event(
        session,
        actor,
        "settlement_disputed",
        _package_or_404(session, row),
        {"settlement_key": row.settlement_key, "reason": reason.strip()},
    )
    return {"id": row.id, "status": row.status, "settlement_key": row.settlement_key}
