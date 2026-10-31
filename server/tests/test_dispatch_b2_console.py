"""调度台操作面（B2）：GET /packages/<id>/offers 平台侧包留痕。

- 平台侧（admin/project_lead）看一包全量 offer 留痕：谁被派、接/拒状态、
  §6.2 窗口 deadline 现算（assign=包响应窗 / claim=15 分钟确认窗）；
- rank/explanation 取自 match_breakdown（§4.8 释明平台侧同可见）；
- 非平台侧 403（候选人已有 /offers/mine 自助视图，包侧聚合不开放）；
- 未知包 404；排序=轮次倒序 → offered_at 倒序（最新轮置顶）。

零迁移（读路由）；服务端全部为既有模型。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from conftest import INITIAL_PASSWORD
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.dispatch.models import DispatchOffer
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


def _published_package(db_session: Session, *, mode: str = "assign"):
    """admin + 派单线项目 + finalized 报价 + published 交付包（r3 三件套口径）。"""
    admin = _user("b2.admin")
    fde = _user("b2.fde", role="fde_engineer")
    stranger = _user("b2.stranger", role="fde_engineer")
    template = IndustryTemplate(
        template_key=f"b2-tpl-{uuid4().hex[:8]}",
        name="b2 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="b2 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    project = Project(
        project_code=f"B2-{uuid4().hex[:6].upper()}",
        name="b2 调度台项目",
        enterprise_code="b2 企业·制造·苏州",
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
        name="b2 交付方案",
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
        db_session,
        actor=admin,
        solution_id=solution.id,
        quote_id=quote.id,
        dispatch_mode=mode,
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
    rank: int | None = None,
    explanation: str | None = None,
    mode: str | None = None,
    offered_at: datetime | None = None,
) -> DispatchOffer:
    breakdown: dict = {}
    if rank is not None:
        breakdown["rank"] = rank
    if explanation is not None:
        breakdown["explanation"] = explanation
    if mode is not None:
        breakdown["mode"] = mode
    offer = DispatchOffer(
        package_id=package.id,
        dispatch_round=1,
        candidate_user_id=candidate.id,
        status=status,
        match_breakdown=breakdown or None,
        offered_at=offered_at or datetime(2026, 10, 31, 12, 0, tzinfo=UTC),
    )
    db_session.add(offer)
    db_session.flush()
    return offer


# ---------------------------------------------------------------------------
# GET /packages/<id>/offers：平台侧包留痕
# ---------------------------------------------------------------------------


def test_package_offers_full_trail_with_rank_and_deadline(console_context, db_session):
    ctx = console_context
    offer = _offer(
        db_session,
        package=ctx["package"],
        candidate=ctx["fde"],
        rank=1,
        explanation="L2 · 行业匹配 · 地理 T1",
    )
    _offer(
        db_session,
        package=ctx["package"],
        candidate=ctx["stranger"],
        status="declined",
        rank=2,
        offered_at=datetime(2026, 10, 31, 9, 0, tzinfo=UTC),
    )
    db_session.commit()

    response = ctx["admin_client"].get(
        f"/api/v1/dispatch/packages/{ctx['package'].id}/offers"
    )
    assert response.status_code == 200
    rows = response.json["data"]
    assert len(rows) == 2
    # 排序：offered_at 倒序（后派的置顶）
    assert rows[0]["offer_id"] == offer.id
    assert rows[0]["candidate_user_id"] == ctx["fde"].id
    assert rows[0]["candidate_username"] == ctx["fde"].username
    assert rows[0]["candidate_display_name"] == ctx["fde"].display_name
    assert rows[0]["status"] == "offered"
    assert rows[0]["rank"] == 1
    assert rows[0]["explanation"] == "L2 · 行业匹配 · 地理 T1"
    assert rows[0]["mode"] == "assign"
    # assign 窗口 = offered_at + 包 response_window_hours（默认 24h，§6.2）
    assert rows[0]["deadline"] == "2026-11-01T12:00:00+00:00"
    # 全量留痕：他方 declined 行同样可见（调度台据此决定重派）
    assert rows[1]["status"] == "declined"
    assert rows[1]["responded_at"] is None  # 测试数据未回填响应时刻


def test_package_offers_empty_trail(console_context, db_session):
    ctx = console_context
    admin, fde, stranger, project, claim_pkg = _published_package(
        db_session, mode="claim"
    )
    db_session.commit()

    response = ctx["admin_client"].get(
        f"/api/v1/dispatch/packages/{claim_pkg.id}/offers"
    )
    assert response.status_code == 200
    assert response.json["data"] == []


def test_package_offers_claim_deadline(console_context, db_session):
    ctx = console_context
    _offer(db_session, package=ctx["package"], candidate=ctx["fde"])
    # claim 模式包：另建一包并放 claim offer
    admin, fde, stranger, project, claim_pkg = _published_package(
        db_session, mode="claim"
    )
    _offer(db_session, package=claim_pkg, candidate=fde, mode="claim")
    db_session.commit()

    rows = ctx["admin_client"].get(
        f"/api/v1/dispatch/packages/{claim_pkg.id}/offers"
    ).json["data"]
    # claim 确认窗 = offered_at + 15 分钟（§6.2 claim_confirm_window_minutes）
    assert rows[0]["deadline"] == "2026-10-31T12:15:00+00:00"
    assert rows[0]["mode"] == "claim"


def test_package_offers_forbidden_for_non_platform(console_context, db_session):
    ctx = console_context
    _offer(db_session, package=ctx["package"], candidate=ctx["fde"])
    db_session.commit()

    for who in ("fde_client", "stranger_client"):
        response = ctx[who].get(
            f"/api/v1/dispatch/packages/{ctx['package'].id}/offers"
        )
        assert response.status_code == 403
        assert response.json["error"]["code"] == "forbidden"


def test_package_offers_404_unknown_package(console_context):
    response = console_context["admin_client"].get(
        f"/api/v1/dispatch/packages/{uuid4()}/offers"
    )
    assert response.status_code == 404
    assert response.json["error"]["code"] == "package_not_found"


def test_package_offers_round_desc_first(console_context, db_session):
    ctx = console_context
    first = _offer(db_session, package=ctx["package"], candidate=ctx["fde"], rank=1)
    second = DispatchOffer(
        package_id=ctx["package"].id,
        dispatch_round=2,
        candidate_user_id=ctx["stranger"].id,
        status="offered",
        offered_at=datetime(2026, 10, 31, 13, 0, tzinfo=UTC),
    )
    db_session.add(second)
    db_session.commit()

    rows = ctx["admin_client"].get(
        f"/api/v1/dispatch/packages/{ctx['package'].id}/offers"
    ).json["data"]
    # 轮次倒序优先：第 2 轮置顶（重派后最新轮是运营焦点）
    assert rows[0]["dispatch_round"] == 2
    assert rows[0]["offer_id"] == second.id
    assert rows[1]["offer_id"] == first.id
