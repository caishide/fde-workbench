"""接单工作台（B1）三读路由：/offers/mine、/settlements/mine、/profiles/me。

- 收件箱只含本人 offer（全量留痕语义）；deadline=§6.2 窗口现算
  （assign=包响应窗 24h / claim=15 分钟确认窗）；
- 结算只回本人席位角色与金额——他席存在与金额零出现（§9.5 同源隔离）；
- 档案自助视图无档案 404；在途计数口径与平台侧 list_profiles 一致。

零迁移（读路由 + 白名单 id 支撑列）；服务端全部为既有模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest
from conftest import INITIAL_PASSWORD
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.dispatch.models import DeliverySettlement, DispatchOffer, FdeProfile
from fde_api.dispatch.packages import create_package, publish_package
from fde_api.solutions.models import ProjectSolution
from fde_api.workbench.models import (
    IndustryTemplate,
    IndustryTemplateVersion,
    Project,
    Quote,
)
from sqlalchemy.orm import Session

UTC = timezone.utc


@dataclass
class _Client:
    client: object
    user: User
    headers: dict[str, str]

    def get(self, *args, **kwargs):
        return self.client.get(*args, headers=self.headers, **kwargs)

    def post(self, *args, **kwargs):
        return self.client.post(*args, headers=self.headers, **kwargs)


def _authorized(client, settings, user: User) -> _Client:
    return _Client(
        client, user, {"Authorization": f"Bearer {issue_access_token(user, settings)}"}
    )


def _user(username: str, role: str = "admin") -> User:
    return User(
        username=f"{username}.{uuid4().hex[:8]}",
        display_name=username,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )


def _published_package(db_session: Session, *, project_city: str = "苏州"):
    """admin + 派单线项目 + finalized 报价 + published 交付包（r3 三件套口径）。"""
    admin = _user("b1.admin")
    fde = _user("b1.fde", role="fde_engineer")
    stranger = _user("b1.stranger", role="fde_engineer")
    template = IndustryTemplate(
        template_key=f"b1-tpl-{uuid4().hex[:8]}",
        name="b1 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="b1 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    project = Project(
        project_code=f"B1-{uuid4().hex[:6].upper()}",
        name="b1 接单工作台项目",
        enterprise_code=f"b1 企业·制造·{project_city}",
        business_line="FDE_DISPATCH",  # P2-4 H3：交付包只建在派单线项目
        planned_start_date=date(2026, 10, 31),
        planned_end_date=date(2026, 12, 31),
        leader_user_id=admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([admin, fde, stranger, project])
    db_session.flush()
    solution = ProjectSolution(
        project_id=project.id,
        name="b1 交付方案",
        design_markdown="# 设计",
        deliverables="交付物 A/B",
        acceptance_criteria="验收口径",
        data_systems="ERP",
        schedule="远程交付",
        risks_dependencies="无",
        owner_user_id=admin.id,
    )
    db_session.add(solution)
    db_session.flush()
    quote = Quote(
        project_id=project.id,
        quote_key=f"Q-{uuid4().hex[:8]}",
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
    db_session.add(quote)
    db_session.flush()
    package = create_package(
        db_session, actor=admin, solution_id=solution.id, quote_id=quote.id
    )
    publish_package(
        db_session, actor=admin, package_id=package.id, candidate_user_ids=(fde.id,)
    )
    db_session.flush()
    return admin, fde, stranger, project, package


@pytest.fixture()
def console_context(client, db_session, settings):
    admin, fde, stranger, project, package = _published_package(db_session)
    db_session.commit()
    return {
        "admin": admin,
        "fde": fde,
        "stranger": stranger,
        "project": project,
        "package": package,
        "admin_client": _authorized(client, settings, admin),
        "fde_client": _authorized(client, settings, fde),
        "stranger_client": _authorized(client, settings, stranger),
    }


def _offer(
    db_session,
    *,
    package,
    candidate: User,
    status: str = "offered",
    mode: str | None = None,
    offered_at: datetime | None = None,
) -> DispatchOffer:
    offer = DispatchOffer(
        package_id=package.id,
        dispatch_round=1,
        candidate_user_id=candidate.id,
        status=status,
        match_breakdown={"mode": mode} if mode else None,
        offered_at=offered_at or datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
    )
    db_session.add(offer)
    db_session.flush()
    return offer


def _settlement(
    db_session,
    *,
    package,
    platform: User | None = None,
    region: User | None = None,
    city: User | None = None,
    delivery: User | None = None,
) -> DeliverySettlement:
    row = DeliverySettlement(
        package_id=package.id,
        settlement_key=f"M{uuid4().hex[:4].upper()}",
        base_amount=Decimal("10000.00"),
        seat_platform_user_id=platform.id if platform else None,
        seat_region_agent_user_id=region.id if region else None,
        seat_city_partner_user_id=city.id if city else None,
        seat_delivery_user_id=delivery.id if delivery else None,
        platform_amount=Decimal("3500.00"),
        region_amount=Decimal("500.00"),
        city_amount=Decimal("2000.00"),
        delivery_amount=Decimal("4000.00"),
        withholding_tax=Decimal("120.00"),
        status="accrued",
    )
    db_session.add(row)
    db_session.flush()
    return row


# ---------------------------------------------------------------------------
# /offers/mine：我的 offer 收件箱
# ---------------------------------------------------------------------------


def test_offers_mine_only_own_offers_with_deadline(console_context, db_session):
    ctx = console_context
    mine = _offer(db_session, package=ctx["package"], candidate=ctx["fde"])
    _offer(
        db_session,
        package=ctx["package"],
        candidate=ctx["stranger"],
        offered_at=datetime(2026, 10, 31, 9, 0, tzinfo=UTC),
    )
    db_session.commit()

    response = ctx["fde_client"].get("/api/v1/dispatch/offers/mine")
    assert response.status_code == 200
    rows = response.json["data"]
    assert len(rows) == 1
    row = rows[0]
    assert row["offer_id"] == mine.id
    assert row["status"] == "offered"
    assert row["version"] == mine.version
    # assign 窗口 = offered_at + 包 response_window_hours（默认 24h，§6.2）
    assert row["deadline"] == "2026-11-01T12:00:00+00:00"
    assert row["mode"] == ctx["package"].dispatch_mode
    # 包侧走白名单 payload（含 id 支撑列；报价明细零出现）
    assert row["package"]["id"] == ctx["package"].id
    assert row["package"]["package_code"] == ctx["package"].package_code
    assert "final_amount" not in row["package"]


def test_offers_mine_claim_confirm_window_15m(console_context, db_session):
    ctx = console_context
    _offer(db_session, package=ctx["package"], candidate=ctx["fde"], mode="claim")
    db_session.commit()

    rows = ctx["fde_client"].get("/api/v1/dispatch/offers/mine").json["data"]
    # claim 确认窗 = offered_at + 15 分钟（§6.2 claim_confirm_window_minutes）
    assert rows[0]["deadline"] == "2026-10-31T12:15:00+00:00"
    assert rows[0]["mode"] == "claim"


def test_offers_mine_excludes_other_candidates(console_context, db_session):
    ctx = console_context
    _offer(db_session, package=ctx["package"], candidate=ctx["fde"])
    db_session.commit()

    rows = ctx["stranger_client"].get("/api/v1/dispatch/offers/mine").json["data"]
    assert rows == []


# ---------------------------------------------------------------------------
# /settlements/mine：我的席位结算（他席金额零出现）
# ---------------------------------------------------------------------------


def test_settlements_mine_only_own_seat_amount(console_context, db_session):
    ctx = console_context
    row = _settlement(
        db_session,
        package=ctx["package"],
        platform=ctx["fde"],
        delivery=ctx["stranger"],
    )
    db_session.commit()

    data = ctx["fde_client"].get("/api/v1/dispatch/settlements/mine").json["data"]
    assert len(data) == 1
    entry = data[0]
    assert entry["settlement_id"] == row.id
    assert entry["my_roles"] == ["platform"]
    assert entry["my_amount"] == 3500.0
    # 隔离由显式 schema 保证：响应键集里没有任何他席金额字段，
    # 金额值只允许 base_amount / my_amount / withholding_tax 三个
    assert set(entry) == {
        "settlement_id",
        "package_code",
        "settlement_key",
        "status",
        "base_amount",
        "my_roles",
        "my_amount",
        "withholding_tax",
        "acceptance_passed_at",
        "paid_at",
    }
    assert {k for k in entry if k.endswith("_amount")} == {
        "base_amount",
        "my_amount",
    }

    other = ctx["stranger_client"].get("/api/v1/dispatch/settlements/mine").json["data"]
    assert len(other) == 1
    assert other[0]["my_roles"] == ["delivery"]
    assert other[0]["my_amount"] == 4000.0

    admin_rows = ctx["admin_client"].get("/api/v1/dispatch/settlements/mine").json["data"]
    assert admin_rows == []


def test_settlements_mine_multi_seat_sums(console_context, db_session):
    ctx = console_context
    _settlement(db_session, package=ctx["package"], region=ctx["fde"], city=ctx["fde"])
    db_session.commit()

    data = ctx["fde_client"].get("/api/v1/dispatch/settlements/mine").json["data"]
    assert data[0]["my_roles"] == ["region", "city"]
    assert data[0]["my_amount"] == 2500.0


# ---------------------------------------------------------------------------
# /profiles/me：我的能力档案自助视图
# ---------------------------------------------------------------------------


def test_profiles_me_returns_own_profile_and_in_hand(console_context, db_session):
    ctx = console_context
    db_session.add(
        FdeProfile(
            user_id=ctx["fde"].id,
            level="L2",
            status="active",
            biz_cognition_score=3,
            scenario_eng_score=3,
            ai_tech_score=4,
            delivery_assure_score=3,
            home_city="苏州",
            monthly_capacity_hours=160,
            avg_delivery_hours=40,
        )
    )
    _offer(
        db_session,
        package=ctx["package"],
        candidate=ctx["fde"],
        status="accepted",
    )
    db_session.commit()

    response = ctx["fde_client"].get("/api/v1/dispatch/profiles/me")
    assert response.status_code == 200
    data = response.json["data"]
    assert data["level"] == "L2"
    assert data["home_city"] == "苏州"
    assert data["scores"]["ai_tech"] == 4
    # 在途计数 = offered + accepted（口径与平台侧 list_profiles 一致）
    assert data["in_hand"] == 1
    assert data["capacity_cap"] == 4


def test_profiles_me_404_without_profile(console_context, db_session):
    response = console_context["fde_client"].get("/api/v1/dispatch/profiles/me")
    assert response.status_code == 404
    assert response.json["error"]["code"] == "profile_not_found"
