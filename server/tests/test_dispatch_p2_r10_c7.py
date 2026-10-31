"""C7 混合模式自动转换 job（goal-r10，设计 §6.1：先 assign 24h 无人接 → 转 claim）。

验收口径：
- 指派死亡（expired/rejected）的 assign 包 × 城市 claim 开闸（§6.4）→
  就地转 claim + §2.3 重发（round+1 新码新哈希）+ 留痕；
- 未开闸/无城市归属 → §11 降级态安全空转（包保持原状）；
- 幂等（mode 翻转后不再命中）；单包失败不炸整批（SAVEPOINT）；
- 24h 响应窗由 expire_stale_offers 按 §6.2 response_window_hours 执行，
  本模块零新增时间常数。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.dispatch import cities as cities_mod
from fde_api.dispatch.maintenance import convert_stale_assign_to_claim, run_maintenance
from fde_api.dispatch.models import (
    DeliveryPackage,
    DispatchOffer,
    DispatchRuleVersion,
    FdeProfile,
)
from fde_api.dispatch.offer_service import (
    claim_package,
    create_assign_offers,
    decline_offer,
    expire_stale_offers,
)
from fde_api.dispatch.packages import create_package, publish_package
from fde_api.solutions.models import ProjectSolution
from fde_api.workbench.models import (
    IndustryTemplate,
    IndustryTemplateVersion,
    ModuleCatalog,
    OperationEvent,
    Project,
    ProjectModule,
    Quote,
)

from conftest import SERVER_ROOT


@pytest.fixture
def module_catalog(db_session):
    """每用例清表会连带清 module_catalog——建包前重灌引用种子（同 conftest）。"""
    import sys

    if str(SERVER_ROOT) not in sys.path:
        sys.path.insert(0, str(SERVER_ROOT))
    from load_seeds import _upsert_module_catalog

    _upsert_module_catalog(db_session)
    db_session.commit()
    return db_session.scalar(select(ModuleCatalog).limit(1))

# ---------------------------------------------------------------- 基础件


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


def _quote(project_id: str, quote_key: str) -> Quote:
    return Quote(
        project_id=project_id,
        quote_key=quote_key,
        status="finalized",
        tier="standard",
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


def _assign_package(
    db_session,
    module_catalog,
    *,
    city: str = "苏州",
    enterprise_code: str | None = None,
):
    """assign 包到 offered 态：派单线项目 + 方案 + 报价 + 发布 + 指派 Top1。"""
    from fde_api.workbench.models import ProjectModule

    admin = _user("r10.admin")
    template = IndustryTemplate(
        template_key=f"r10-tpl-{uuid4().hex[:8]}",
        name="r10 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="r10 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    code = enterprise_code or f"r10 客户·制造业·{city}"
    project = Project(
        project_code=f"R10-{uuid4().hex[:6].upper()}-{uuid4().hex[:4]}",
        name="r10 混合模式项目",
        enterprise_code=code,
        business_line="FDE_DISPATCH",  # P2-4 H3：交付包只建在派单线项目
        planned_start_date=datetime(2026, 11, 3).date(),
        leader_user_id=admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([admin, project])
    db_session.flush()
    db_session.add(
        ProjectModule(
            project_id=project.id,
            module_catalog_id=module_catalog.id,
            name="初步诊断",
            status="active",
        )
    )
    solution = ProjectSolution(
        project_id=project.id, name="r10 方案", owner_user_id=admin.id, status="active"
    )
    db_session.add(solution)
    db_session.flush()
    quote = _quote(project.id, f"Q-{uuid4().hex[:8]}")
    db_session.add(quote)
    db_session.flush()
    package = create_package(
        db_session, actor=admin, solution_id=solution.id, quote_id=quote.id
    )
    publish_package(
        db_session, actor=admin, package_id=package.id, candidate_user_ids=()
    )
    db_session.flush()
    return admin, project, package


def _candidate(db_session, username: str, city: str | None = None) -> User:
    candidate = _user(username, role="fde_engineer")
    db_session.add(candidate)
    if city:
        db_session.add(
            FdeProfile(
                user_id=candidate.id,
                home_city=city,
                status="active",
                is_active=True,
                monthly_capacity_hours=160,
                avg_delivery_hours=80,
            )
        )
    db_session.flush()
    return candidate


_OPEN_SUZHOU_SEED = (
    {
        "city": "苏州",
        "province": "江苏",
        "metro_group": "苏锡常都市圈",
        "city_tier": "T1",
        "claim_enabled": True,
        "subsidy_scheme": None,
    },
)


def _open_gate(db_session, monkeypatch, *, city: str = "苏州", peers: int = 2) -> None:
    """§6.4 三条件 + 城市开关：开闸（供给=同城 active 档案 > 需求、零拒单、
    active 规则版本=权重公示代理）。"""
    for i in range(peers):
        _candidate(db_session, f"r10.gate.{city}.{i}", city=city)
    db_session.add(
        DispatchRuleVersion(
            version_no=1,
            status="active",
            rule_snapshot={
                "stage_b_weights": {"level": 40, "industry": 30, "sla": 20, "geo_remote": 10},
                "level_score_map": {"L1": 40, "L2": 60, "L3": 80, "L4": 100},
                "seat_shares": {"platform": 35, "region": 5, "city": 20, "delivery": 40},
            },
            effective_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    db_session.flush()
    monkeypatch.setattr(cities_mod, "_city_seed", lambda: _OPEN_SUZHOU_SEED)


def _assign_to_candidate(db_session, admin: User, package: DeliveryPackage, user: User):
    create_assign_offers(
        db_session, actor=admin, package_id=package.id, candidate_user_ids=(user.id,)
    )
    db_session.flush()


# ---------------------------------------------------------------- 验收用例


def test_c7_converts_expired_assign_and_becomes_claimable(db_session, module_catalog, monkeypatch):
    """assign 超时死亡（24h 响应窗）→ 开闸城转 claim 重发 → 交付方可抢。"""
    admin, _project, package = _assign_package(db_session, module_catalog)
    candidate = _candidate(db_session, "r10.c1", city="苏州")
    _assign_to_candidate(db_session, admin, package, candidate)
    assert package.dispatch_status == "offered"
    # 24h 响应窗判死（§6.2 response_window_hours，上游 expire 执行）
    expire_stale_offers(
        db_session, now=datetime.now(timezone.utc) + timedelta(hours=25)
    )
    db_session.flush()
    db_session.refresh(package)
    assert package.dispatch_status == "expired"

    _open_gate(db_session, monkeypatch)
    report = convert_stale_assign_to_claim(db_session)
    db_session.flush()
    db_session.refresh(package)
    assert len(report["converted"]) == 1
    assert report["converted"][0]["city"] == "苏州"
    assert package.dispatch_mode == "claim"
    assert package.dispatch_status == "published"
    assert package.dispatch_round == 2  # §2.3 非 draft 重发 round+1

    event = db_session.scalar(
        select(OperationEvent)
        .where(OperationEvent.event_type == "dispatch_c7_converted")
        .order_by(OperationEvent.id.desc())
    )
    assert event is not None
    assert event.changes["city"] == "苏州"

    # 转换后的包可被交付方抢（claim_package 走 §6.4 闸门）
    offer = claim_package(db_session, actor=candidate, package_id=package.id)
    db_session.flush()
    assert offer.match_breakdown["mode"] == "claim"


def test_c7_skips_when_gate_closed(db_session, module_catalog):
    """城市未开闸（种子默认全关）→ §11 降级态安全空转：包保持原状。"""
    admin, _project, package = _assign_package(db_session, module_catalog)
    candidate = _candidate(db_session, "r10.c2", city="苏州")
    _assign_to_candidate(db_session, admin, package, candidate)
    expire_stale_offers(
        db_session, now=datetime.now(timezone.utc) + timedelta(hours=25)
    )
    db_session.flush()

    report = convert_stale_assign_to_claim(db_session)
    db_session.refresh(package)
    assert report["converted"] == []
    assert report["skipped"][0]["reason"] == "claim_gate_closed"
    assert package.dispatch_mode == "assign"  # 原状（人工重派路径不变）
    assert package.dispatch_status == "expired"


def test_c7_idempotent_second_run_noop(db_session, module_catalog, monkeypatch):
    """mode 翻转后不再命中扫描——同一包只转一次。"""
    admin, _project, package = _assign_package(db_session, module_catalog)
    candidate = _candidate(db_session, "r10.c3", city="苏州")
    _assign_to_candidate(db_session, admin, package, candidate)
    expire_stale_offers(
        db_session, now=datetime.now(timezone.utc) + timedelta(hours=25)
    )
    _open_gate(db_session, monkeypatch)

    first = convert_stale_assign_to_claim(db_session)
    assert len(first["converted"]) == 1
    second = convert_stale_assign_to_claim(db_session)
    assert second["converted"] == []
    assert second["skipped"] == []


def test_c7_converts_all_declined_assign(db_session, module_catalog, monkeypatch):
    """全拒（rejected）同属「响应窗内无人接」→ 开闸城同样转 claim。"""
    admin, _project, package = _assign_package(db_session, module_catalog)
    c1 = _candidate(db_session, "r10.c4a", city="苏州")
    c2 = _candidate(db_session, "r10.c4b", city="合肥")
    _assign_to_candidate(db_session, admin, package, c1)
    _assign_to_candidate(db_session, admin, package, c2)
    for candidate in (c1, c2):
        offer = db_session.scalar(
            select(DispatchOffer).where(
                DispatchOffer.package_id == package.id,
                DispatchOffer.candidate_user_id == candidate.id,
            )
        )
        decline_offer(
            db_session,
            actor=candidate,
            offer_id=offer.id,
            expected_version=offer.version,
            reason="档期冲突",
        )
    db_session.flush()
    db_session.refresh(package)
    assert package.dispatch_status == "rejected"

    # 拒单率稀释（§6.4 条件②）：4 条同窗 accepted 历史 offer → 2/6≈33% <40%
    voters = [_user(f"r10.c4.hist{i}", role="fde_engineer") for i in range(4)]
    db_session.add_all(voters)
    db_session.flush()
    db_session.add_all(
        [
            DispatchOffer(
                package_id=package.id,
                dispatch_round=package.dispatch_round,
                candidate_user_id=voter.id,
                status="accepted",
                match_breakdown={"mode": "assign"},
                offered_at=datetime.now(timezone.utc),
            )
            for voter in voters
        ]
    )
    db_session.flush()

    _open_gate(db_session, monkeypatch)
    report = convert_stale_assign_to_claim(db_session)
    db_session.refresh(package)
    assert len(report["converted"]) == 1
    assert package.dispatch_mode == "claim"
    assert package.dispatch_status == "published"
    assert package.dispatch_round == 2


def test_c7_skips_unknown_city(db_session, module_catalog):
    """企业代号缺城市段 → 跳过（city_unknown），包保持原状。"""
    admin, _project, package = _assign_package(
        db_session, module_catalog, enterprise_code=f"r10 两段·{uuid4().hex[:6]}"
    )
    candidate = _candidate(db_session, "r10.c5")
    _assign_to_candidate(db_session, admin, package, candidate)
    expire_stale_offers(
        db_session, now=datetime.now(timezone.utc) + timedelta(hours=25)
    )
    db_session.flush()

    report = convert_stale_assign_to_claim(db_session)
    assert report["converted"] == []
    assert report["skipped"][0]["reason"] == "city_unknown"


def test_c7_ignores_live_offers(db_session, module_catalog, monkeypatch):
    """响应窗内的在途指派（offered 未超时）不转换——24h 只由上游判死。"""
    admin, _project, package = _assign_package(db_session, module_catalog)
    candidate = _candidate(db_session, "r10.c6", city="苏州")
    _assign_to_candidate(db_session, admin, package, candidate)
    _open_gate(db_session, monkeypatch)

    report = convert_stale_assign_to_claim(db_session)
    db_session.refresh(package)
    assert report["converted"] == []
    assert package.dispatch_status == "offered"
    assert package.dispatch_mode == "assign"


def test_c7_single_failure_does_not_crash_batch(db_session, module_catalog, monkeypatch):
    """单包前置缺失（报价被改非 finalized）→ SAVEPOINT 回滚跳过，健康包照转。"""
    admin, project, package = _assign_package(db_session, module_catalog)
    broken_admin, _p2, broken = _assign_package(db_session, module_catalog)
    candidate = _candidate(db_session, "r10.c7", city="苏州")
    _assign_to_candidate(db_session, admin, package, candidate)
    _assign_to_candidate(db_session, broken_admin, broken, candidate)
    expire_stale_offers(
        db_session, now=datetime.now(timezone.utc) + timedelta(hours=25)
    )
    # 破坏健康前置：报价改回 draft（发布前置=finalized）
    quote = db_session.scalar(select(Quote).where(Quote.project_id == project.id))
    assert quote.id != broken.quote_id
    tampered = db_session.get(Quote, broken.quote_id)
    tampered.status = "draft"
    db_session.flush()
    _open_gate(db_session, monkeypatch)

    report = convert_stale_assign_to_claim(db_session)
    db_session.flush()
    db_session.refresh(package)
    db_session.refresh(broken)
    assert len(report["converted"]) == 1
    assert report["converted"][0]["package_code"] == package.package_code
    failed = [s for s in report["skipped"] if s["reason"].startswith("convert_failed")]
    assert failed and failed[0]["package_code"] == broken.package_code
    assert package.dispatch_mode == "claim" and package.dispatch_status == "published"
    assert broken.dispatch_mode == "assign" and broken.dispatch_status == "expired"


def test_c7_rides_run_maintenance_same_tick(db_session, module_catalog, monkeypatch):
    """转换挂 run_maintenance（dispatch.maintenance job 体）：判死与转换同节拍。"""
    admin, _project, package = _assign_package(db_session, module_catalog)
    candidate = _candidate(db_session, "r10.c8", city="苏州")
    _assign_to_candidate(db_session, admin, package, candidate)
    _open_gate(db_session, monkeypatch)
    assert package.dispatch_status == "offered"

    result = run_maintenance(
        db_session, now=datetime.now(timezone.utc) + timedelta(hours=25)
    )
    db_session.flush()
    db_session.refresh(package)
    assert result["expired_offers"] >= 1
    assert result["c7_conversion"]["converted"], result["c7_conversion"]
    assert package.dispatch_mode == "claim"
    assert package.dispatch_status == "published"
    assert package.dispatch_round == 2
