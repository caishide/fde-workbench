"""F 线 T5：就近硬闸加固（**不提权**）——回归与验收用例。

ADR-011 §5-D ＋ 任务书 §4-T5／§12：

- **动作 ①**：`onsite_required` 由「schedule 四关键词派生」改为
  「**FDE 交付项目默认 True，仅显式标记纯远程才 False**」；关键词派生
  降级为「字段为空（未设置）时的兜底」。
- **动作 ②**：`radius_expand_wait_minutes=15` 接进 `expire_stale_offers`
  ⇒ 同城无人时按 15 分钟逐级自动扩圈（同城→同省→邻接都市圈→全国）；
  全国档仍需「旗舰档＋客户书面确认」。
- **动作 ③（保持不动）**：`stage_b_weights` 维持 40/30/20/10；
  `geo_remote`／`sort_key_onsite`／`sort_key_remote` 一字不动。

既有断言保护：`test_dispatch_p1_r5.py` 的「同城 L1 胜深圳 L4」（:376）与
「远程型加权序」（:448）**不得推翻**——本文件用「显式 False 仍走远程加权
序」「显式 True／未设置仍走到场型硬闸」两条反向钉守住它们。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from fde_api.auth.models import User
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.matching import allowed_geo_tier, match_package
from fde_api.dispatch.models import (
    DeliveryPackage,
    DispatchOffer,
    DispatchRuleVersion,
    FdeProfile,
    resolve_onsite_required,
)
from fde_api.dispatch.offer_service import (
    expand_stale_offers,
    expire_stale_offers,
)
from fde_api.dispatch.packages import create_package, publish_package
from fde_api.solutions.models import ProjectSolution
from fde_api.system_configuration import DISPATCH_CONSTANTS
from fde_api.workbench.models import OperationEvent, Project, ProjectModule, Quote


# ---------------------------------------------------------------------------
# 夹具（沿用 test_dispatch_p1_r5.py 的既有范式）
# ---------------------------------------------------------------------------


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


def _profile(
    db_session,
    user: User,
    *,
    level: str = "L1",
    module_tags: list[str] | None = None,
    industry_tags: list[str] | None = None,
    home_city: str | None = None,
    capacity: int = 100,
    avg_hours: int = 10,
    status: str = "active",
) -> FdeProfile:
    db_session.add(user)
    row = FdeProfile(
        user_id=user.id,
        level=level,
        module_tags=module_tags or ["pre_diagnosis"],
        industry_tags=industry_tags or ["制造业"],
        home_city=home_city,
        monthly_capacity_hours=capacity,
        avg_delivery_hours=avg_hours,
        status=status,
        is_active=status == "active",
    )
    db_session.add(row)
    return row


def _retire_active_rules(db_session) -> None:
    db_session.execute(
        update(DispatchRuleVersion)
        .where(DispatchRuleVersion.status == "active")
        .values(status="retired")
    )
    db_session.flush()


def _active_rule(db_session, **overrides) -> DispatchRuleVersion:
    _retire_active_rules(db_session)
    row = DispatchRuleVersion(
        version_no=overrides.pop("version_no", 1),
        status=overrides.pop("status", "active"),
        rule_snapshot=overrides.pop(
            "rule_snapshot",
            {
                "stage_b_weights": {"level": 40, "industry": 30, "sla": 20, "geo_remote": 10},
                "level_score_map": {"L1": 40, "L2": 60, "L3": 80, "L4": 100},
                "seat_shares": {"platform": 35, "region": 5, "city": 20, "delivery": 40},
            },
        ),
        effective_at=datetime.now(timezone.utc) - timedelta(days=1),
        **overrides,
    )
    db_session.add(row)
    db_session.flush()
    return row


def _package(
    db_session,
    *,
    schedule: str = "",
    tier: str = "standard",
    onsite_required: bool | None = None,
    round_no: int = 1,
    client_city: str = "广州",
):
    """建一个 FDE 交付包（方案文本可空 ⇒ 关键词派生无从命中）。"""
    admin = _user("t5.admin")
    db_session.add(admin)
    db_session.flush()
    from fde_api.workbench.models import ModuleCatalog

    module = db_session.scalar(
        select(ModuleCatalog).where(ModuleCatalog.module_key == "pre_diagnosis")
    )
    if module is None:
        module = ModuleCatalog(
            module_key="pre_diagnosis",
            name="售前诊断",
            description="T5 测试自建",
            is_active=True,
        )
        db_session.add(module)
        db_session.flush()
    from fde_api.workbench.models import IndustryTemplate, IndustryTemplateVersion

    template = IndustryTemplate(
        template_key=f"t5-tpl-{uuid4().hex[:8]}",
        name="t5 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="t5 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    project = Project(
        project_code=f"T5-{uuid4().hex[:6].upper()}",
        name="t5 撮合项目",
        enterprise_code=f"t5 企业·制造·{client_city}",
        business_line="FDE_DISPATCH",
        planned_start_date=datetime(2026, 10, 31).date(),
        leader_user_id=admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([project, module])
    db_session.flush()
    db_session.add(
        ProjectModule(
            project_id=project.id,
            module_catalog_id=module.id,
            name=module.name,
            status="active",
        )
    )
    db_session.flush()
    solution = ProjectSolution(
        project_id=project.id,
        name="t5 方案",
        schedule=schedule,
        owner_user_id=admin.id,
    )
    db_session.add(solution)
    db_session.flush()
    quote = Quote(
        project_id=project.id,
        quote_key=f"Q-{uuid4().hex[:8]}",
        status="finalized",
        tier=tier,
        ideal_hours=Decimal("100"),
        realistic_hours=Decimal("100"),
        integration_factor=Decimal("1.00"),
        data_factor=Decimal("1.00"),
        compliance_factor=Decimal("1.00"),
        buffer_factor=Decimal("1.00"),
        hourly_rate=150,
        cash_cost=100000,
        margin_factor=Decimal("1.40"),
        b_layer_score=5,
        b_layer_factor=Decimal("1.00"),
        anchor_mode="steady",
        labor_cost=Decimal("100000"),
        total_cost=Decimal("100000"),
        formula_price=Decimal("200000"),
        anchor_low=200000,
        anchor_high=300000,
        branch="A",
        final_amount=Decimal("20000"),
        field_claims={"final_amount": "measured"},
    )
    db_session.add(quote)
    db_session.flush()
    package = create_package(
        db_session,
        actor=admin,
        solution_id=solution.id,
        quote_id=quote.id,
        onsite_required=onsite_required,
    )
    package.required_level = "L1"
    package.dispatch_round = round_no
    db_session.flush()
    return admin, package, quote


# ---------------------------------------------------------------------------
# 动作 ①：onsite_required 默认 True（漏关键词不再让硬闸失效）
# ---------------------------------------------------------------------------


def test_onsite_defaults_true_when_schedule_has_no_keyword(db_session):
    """方案文本为空/无关键词 ⇒ 仍走到场型（硬闸不再整体失效）。"""
    _admin, package, _quote = _package(db_session, schedule="")
    # 新建包落 NULL（未设置）
    assert package.onsite_required is None
    # 读侧兜底 ⇒ 默认到场型
    assert resolve_onsite_required(package) is True
    # 关键词派生已降级为兜底：即使文本命中关键词，默认仍是 True
    assert resolve_onsite_required(package, schedule="需到场实施") is True
    # **关键**：未命中关键词**不得**据此判为纯远程（否则硬闸又整体失效）
    assert resolve_onsite_required(package, schedule="") is True


def test_onsite_explicit_remote_is_respected(db_session):
    """显式标记纯远程（False）⇒ 原样采用，不被派生或默认值改写。"""
    _admin, package, _quote = _package(
        db_session, schedule="需到场实施", onsite_required=False
    )
    assert package.onsite_required is False
    assert resolve_onsite_required(package) is False
    # 关键：显式 False **不得**被「四关键词命中」推回 True
    assert resolve_onsite_required(package, schedule="需到场实施") is False


def test_onsite_explicit_true_is_respected(db_session):
    """显式到场型（True）⇒ 原样采用。"""
    _admin, package, _quote = _package(
        db_session, schedule="", onsite_required=True
    )
    assert package.onsite_required is True
    assert resolve_onsite_required(package) is True


def test_publish_freezes_onsite_into_snapshot(db_session):
    """发布时把到场型语义**冻结进快照**（显式 False 不得被静默改写成 True）。

    旧写法 ``package.onsite_required or _derive(...)`` 正是这个 bug 的来源：
    显式纯远程在发布时被静默改回到场型。
    """
    admin, package, _quote = _package(
        db_session, schedule="需到场实施", onsite_required=False
    )
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    assert package.onsite_required is False
    assert resolve_onsite_required(package) is False
    assert package.snapshot_hash


def test_publish_resolves_null_to_onsite_default(db_session):
    """未设置（NULL）⇒ 发布时落库为具体值（默认到场型），快照可复现。"""
    admin, package, _quote = _package(db_session, schedule="")
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    assert package.onsite_required is True


def test_cross_province_candidate_rejected_in_onsite_package(db_session):
    """**M12 守面**：到场包（未设置⇒默认到场型）中跨省候选不得中签。

    这是任务书验收「同城候选可用时跨省候选不中签」的机械钉——若
    ``onsite_required`` 被恒置 False，本用例转红。
    """
    admin, package, _quote = _package(db_session, schedule="")
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    remote = _user("t5.remote", role="fde_engineer")
    _profile(db_session, remote, level="L4", home_city="深圳")
    result = match_package(db_session, actor=admin, package_id=package.id)
    # 无同城候选 ⇒ 场景 C（不自动派）；跨省候选被围栏淘汰
    assert result["scenario"] == "C"
    assert result["offers"] == []


def test_same_city_candidate_wins_over_cross_province(db_session):
    """同城候选可用时跨省候选不中签（到场型硬闸 + 字典序一级键）。"""
    admin, package, _quote = _package(db_session, schedule="")
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    near = _user("t5.near", role="fde_engineer")
    _profile(db_session, near, level="L1", home_city="广州")
    far = _user("t5.far", role="fde_engineer")
    _profile(db_session, far, level="L4", home_city="深圳")
    result = match_package(db_session, actor=admin, package_id=package.id)
    assert result["scenario"] == "A"
    assert [o["candidate_user_id"] for o in result["offers"]] == [near.id]


def test_explicit_remote_keeps_weighted_path(db_session):
    """显式标记纯远程 ⇒ 走远程型加权序（**保护既有远程型断言**）。

    `test_dispatch_p1_r5.py:448` 的远程型加权序语义在此被反向钉住：
    显式 False 仍生效 ⇒ 远程型不因「默认 True」改造而回归成到场型。
    """
    admin, package, _quote = _package(
        db_session, schedule="", onsite_required=False
    )
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    # 跨省候选需先脱离 §6.5 新人保护期（前 N 单只推同城）——既有语义。
    far = _retire_newcomer_protection(db_session, package, "深圳")
    result = match_package(db_session, actor=admin, package_id=package.id)
    assert result["scenario"] == "B"
    assert [o["candidate_user_id"] for o in result["offers"]] == [far.id]


def test_create_rejects_non_bool_onsite(db_session):
    """非布尔 onsite_required ⇒ 400（服务层显式拒绝，不静默纠正）。"""
    admin = _user("t5.admin.reject")
    db_session.add(admin)
    db_session.flush()
    _admin, package, _quote = _package(db_session, schedule="")
    with pytest.raises(DispatchServiceError) as error:
        create_package(
            db_session,
            actor=admin,
            solution_id=package.solution_id,
            quote_id=package.quote_id,
            onsite_required="yes",  # type: ignore[arg-type]
        )
    assert error.value.code == "invalid_request"


# ---------------------------------------------------------------------------
# 动作 ②：15 分钟逐级自动扩圈
# ---------------------------------------------------------------------------


def _expire_all_offers(db_session, package: DeliveryPackage, now: datetime) -> None:
    """把本轮 offer 全部终结（超时），使包进入可扩圈态。"""
    offers = db_session.scalars(
        select(DispatchOffer).where(
            DispatchOffer.package_id == package.id,
            DispatchOffer.dispatch_round == package.dispatch_round,
        )
    ).all()
    for offer in offers:
        offer.status = "expired"
        offer.responded_at = now
        offer.version += 1
    db_session.flush()


def _retire_newcomer_protection(db_session, package, city: str) -> User:
    """脱离 §6.5 新人保护期（前 N 单只推同城）。

    手法与既有 ``test_dispatch_p1_r5.py`` 远程型用例一致：预置 N 单已接
    记录使候选计数越过保护阈值。**这是既有保护期语义的复刻，不是绕过**——
    新人保护本身零改动。
    """
    veteran = _user("t5.veteran", role="fde_engineer")
    _profile(db_session, veteran, level="L4", home_city=city)
    for round_no in range(91, 96):
        db_session.add(
            DeliveryPackage(
                id=uuid4().hex,
                solution_id=package.solution_id,
                project_id=package.project_id,
                package_code=f"PKG-T5-OLD-{uuid4().hex[:8].upper()}",
                dispatch_round=round_no,
                dispatch_status="accepted",
                seat_delivery=veteran.id,
                accepted_at=datetime.now(timezone.utc),
            )
        )
    db_session.flush()
    return veteran


def test_expand_waits_full_15_minutes(db_session):
    """**M12b 守面**：未满 15 分钟 **不** 推进（扩圈闸生效）。"""
    admin, package, _quote = _package(db_session, schedule="")
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    base = datetime.now(timezone.utc)
    _expire_all_offers(db_session, package, base)
    package.dispatch_status = "expired"
    db_session.flush()

    # 14 分钟：不动。**经调度入口 expire_stale_offers 调用**——
    # 扩圈接线就在其内部（变异 M12b 摘除点），直接调原语测不出接线。
    expire_stale_offers(db_session, now=base + timedelta(minutes=14))
    db_session.flush()
    assert package.dispatch_round == 1
    assert package.dispatch_status == "expired"


def test_expand_advances_one_tier_after_15_minutes(db_session):
    """过 15 分钟 ⇒ 自动重发（round+1 ＝ 扩圈一档）。"""
    admin, package, _quote = _package(db_session, schedule="")
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    base = datetime.now(timezone.utc)
    _expire_all_offers(db_session, package, base)
    package.dispatch_status = "expired"
    db_session.flush()

    # **经调度入口**（变异 M12b 的摘除点）⇒ 接线缺失时本用例转红。
    expire_stale_offers(db_session, now=base + timedelta(minutes=16))
    db_session.flush()
    assert package.dispatch_round == 2
    assert package.dispatch_status == "published"
    # 半径随轮次推进（§4.7 序列 25→50→100→0）
    assert package.redispatch_radius_km == 50
    # 留痕事件
    event = db_session.scalar(
        select(OperationEvent).where(
            OperationEvent.event_type == "dispatch_offer_expanded"
        )
    )
    assert event is not None
    assert "radius_expand_wait_elapsed" in str(event.changes)


def test_expand_progresses_city_to_province_to_metro(db_session):
    """逐级链：同城(round1) → 同省(round2) → 邻接都市圈(round3)。"""
    admin, package, _quote = _package(db_session, schedule="")
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    base = datetime.now(timezone.utc)

    tiers = []
    for _ in range(3):
        _expire_all_offers(db_session, package, base)
        package.dispatch_status = "expired"
        db_session.flush()
        expire_stale_offers(db_session, now=base + timedelta(minutes=16))
        db_session.flush()
        # 首轮已是 round1（发布时），第一次扩圈 ⇒ round2。
        assert package.dispatch_round == len(tiers) + 2
        tiers.append(allowed_geo_tier(package, _quote))
        base = base + timedelta(minutes=16)
    # 非旗舰档在 tier2 封顶（全国档 tier3 需 flagship＋客户书面确认）
    # ⇒ 可达档位 [1, 2, 2]；全国档由下一用例单独守。
    assert tiers == [1, 2, 2]


def test_expand_stops_before_national_for_non_flagship(db_session):
    """非旗舰档 **不** 扩到全国（客户书面确认门槛保持不动）。

    `allowed_geo_tier` 在 round≥4 且 quote.tier != 'flagship' 时封顶 tier2
    ⇒ 本函数不得绕过该门槛。
    """
    admin, package, quote = _package(db_session, schedule="", tier="standard")
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    base = datetime.now(timezone.utc)
    for _ in range(5):
        _expire_all_offers(db_session, package, base)
        package.dispatch_status = "expired"
        db_session.flush()
        round_before = package.dispatch_round
        expire_stale_offers(db_session, now=base + timedelta(minutes=16))
        db_session.flush()
        base = base + timedelta(minutes=16)
        if package.dispatch_round == round_before:
            break
    assert package.dispatch_round == 4
    # 非旗舰 ⇒ 全国档封顶 tier2（不扩到 tier3＝全国）
    assert allowed_geo_tier(package, quote) == 2


def test_expand_skips_remote_package(db_session):
    """远程型不参与就近扩圈（远程本就不设地理围栏，扩圈无意义）。"""
    admin, package, _quote = _package(
        db_session, schedule="", onsite_required=False
    )
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    base = datetime.now(timezone.utc)
    _expire_all_offers(db_session, package, base)
    package.dispatch_status = "expired"
    db_session.flush()
    expire_stale_offers(db_session, now=base + timedelta(minutes=60))
    db_session.flush()
    assert package.dispatch_round == 1


def test_expand_is_idempotent(db_session):
    """同一节拍重复调用不重复推进（幂等）。"""
    admin, package, _quote = _package(db_session, schedule="")
    _active_rule(db_session)
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    base = datetime.now(timezone.utc)
    _expire_all_offers(db_session, package, base)
    package.dispatch_status = "expired"
    db_session.flush()
    now = base + timedelta(minutes=16)
    expire_stale_offers(db_session, now=now)
    db_session.flush()
    assert package.dispatch_round == 2
    # 同节拍重复调用：不得二次推进（幂等）
    expire_stale_offers(db_session, now=now)
    db_session.flush()
    assert package.dispatch_round == 2


# ---------------------------------------------------------------------------
# 动作 ③：权重未变（不提权）
# ---------------------------------------------------------------------------


def test_stage_b_weights_unchanged():
    """**权重未变钉**：stage_b_weights 维持 40/30/20/10（任务书 §12 动作 3）。

    本轮只修派生判定与扩圈调度，**不提权**——geo_remote 仍为 10。
    """
    weights = DISPATCH_CONSTANTS["stage_b_weights"]
    assert weights == {"level": 40, "industry": 30, "sla": 20, "geo_remote": 10}


def test_radius_expand_wait_constant_unchanged():
    """扩圈等待常量仍是 15 分钟（§6.2 唯一权威表，本轮只加消费方）。"""
    assert DISPATCH_CONSTANTS["radius_expand_wait_minutes"] == 15
