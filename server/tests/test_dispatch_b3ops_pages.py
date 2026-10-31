"""运维页簇（B3/B5/B6）五路由：disputes 列表/打开/裁决 + simulator/replay +
claim-gates 看板。

- 争议：L0 禁人工打开（400）、L1 金额上限 422 amount_above_l1、未知包 404、
  非平台侧 403；裁决结论必填、已决 409、快照锚=打开时的包快照（§2.3 规则 2）；
- 回放：只读（无 offer 落库），无公示规则版本=逐包 skipped 降级行（§11.1）；
- 开闸：种子 6 城逐城可解释明细；开关在种子文件（只读展示，HTTP 不翻转）。

零迁移（薄路由包装既有服务层函数）。
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
from fde_api.dispatch.models import DeliveryPackage, Dispute, DispatchRuleVersion
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


def _published_package(db_session: Session) -> DeliveryPackage:
    """admin + 派单线项目 + finalized 报价 + published 交付包（r3 三件套口径）。"""
    admin = _user("bops.admin")
    fde = _user("bops.fde", role="fde_engineer")
    template = IndustryTemplate(
        template_key=f"bops-tpl-{uuid4().hex[:8]}",
        name="bops 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="bops 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    project = Project(
        project_code=f"BOPS-{uuid4().hex[:6].upper()}",
        name="bops 运维页项目",
        enterprise_code="bops 企业·制造·苏州",
        business_line="FDE_DISPATCH",
        planned_start_date=date(2026, 11, 1),
        planned_end_date=date(2026, 12, 31),
        leader_user_id=admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([admin, fde, project])
    db_session.flush()
    solution = ProjectSolution(
        project_id=project.id,
        name="bops 交付方案",
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
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    return package


@pytest.fixture()
def console_context(client, db_session, settings):
    package = _published_package(db_session)
    db_session.commit()
    admin = (
        db_session.query(User)
        .filter(User.username.startswith("bops.admin."))
        .one()
    )
    fde = db_session.query(User).filter(User.username.startswith("bops.fde.")).one()
    return {
        "package": package,
        "admin": admin,
        "fde": fde,
        "admin_client": _authorized(client, settings, admin),
        "fde_client": _authorized(client, settings, fde),
    }


# ---------------------------------------------------------------------------
# GET /disputes + POST /disputes + POST /disputes/<id>/resolve
# ---------------------------------------------------------------------------


def test_disputes_list_full_trail_with_pointer(console_context, db_session):
    ctx = console_context
    db_session.add_all(
        [
            Dispute(
                package_id=ctx["package"].id,
                settlement_key="MAB01",
                layer="L0",
                status="draft",
                amount=Decimal("-12.50"),
                reason="对账差异 实收−应计=−12.50",
                l0_report_source_uri="file:///D:/test/FDE/engagements/recon/t+30.csv",
                snapshot_hash=ctx["package"].snapshot_hash,
                created_at=datetime(2026, 11, 1, 8, 0, tzinfo=UTC),
            ),
            Dispute(
                package_id=ctx["package"].id,
                layer="L1",
                status="open",
                amount=Decimal("3000"),
                reason="交付方对席位金额有异议",
                opened_by_user_id=ctx["admin"].id,
                created_at=datetime(2026, 11, 1, 9, 0, tzinfo=UTC),
            ),
        ]
    )
    db_session.commit()

    response = ctx["admin_client"].get("/api/v1/dispatch/disputes")
    assert response.status_code == 200
    rows = response.json["data"]
    assert len(rows) == 2
    # created_at 倒序：后开的 L1 置顶
    assert rows[0]["layer"] == "L1"
    assert rows[0]["package_code"] == ctx["package"].package_code
    assert rows[0]["opened_by"] == ctx["admin"].display_name
    # L0 行：指针红线字段原样透出（指针本身，非对账单本体）
    assert rows[1]["l0_report_source_uri"].startswith("file:///")
    assert rows[1]["status"] == "draft"
    assert rows[1]["amount"] == -12.5

    forbidden = ctx["fde_client"].get("/api/v1/dispatch/disputes")
    assert forbidden.status_code == 403


def test_open_dispute_l1_anchors_snapshot_and_rejects_l0(console_context):
    ctx = console_context
    response = ctx["admin_client"].post(
        "/api/v1/dispatch/disputes",
        json={
            "package_id": ctx["package"].id,
            "layer": "L1",
            "reason": "交付方对席位金额有异议",
            "amount": 3000,
        },
    )
    assert response.status_code == 201
    data = response.json["data"]
    assert data["status"] == "open"
    assert data["layer"] == "L1"
    # §2.3 规则 2：争议锚定打开时那一版包快照
    assert data["snapshot_hash"] == ctx["package"].snapshot_hash

    l0 = ctx["admin_client"].post(
        "/api/v1/dispatch/disputes",
        json={"package_id": ctx["package"].id, "layer": "L0", "reason": "试试人工开 L0"},
    )
    assert l0.status_code == 400
    assert l0.json["error"]["code"] == "invalid_request"

    forbidden = ctx["fde_client"].post(
        "/api/v1/dispatch/disputes",
        json={"package_id": ctx["package"].id, "layer": "L1", "reason": "x"},
    )
    assert forbidden.status_code == 403


def test_open_dispute_l1_amount_ceiling_422(console_context):
    ctx = console_context
    response = ctx["admin_client"].post(
        "/api/v1/dispatch/disputes",
        json={
            "package_id": ctx["package"].id,
            "layer": "L1",
            "reason": "超 L1 上限",
            "amount": 60000,
        },
    )
    assert response.status_code == 422
    assert response.json["error"]["code"] == "amount_above_l1"


def test_open_dispute_unknown_package_404(console_context):
    response = console_context["admin_client"].post(
        "/api/v1/dispatch/disputes",
        json={"package_id": str(uuid4()), "layer": "L1", "reason": "x"},
    )
    assert response.status_code == 404
    assert response.json["error"]["code"] == "package_not_found"


def test_resolve_dispute_then_409_on_second_resolve(console_context):
    ctx = console_context
    opened = ctx["admin_client"].post(
        "/api/v1/dispatch/disputes",
        json={
            "package_id": ctx["package"].id,
            "layer": "L2",
            "reason": "跨区争议需双人复核",
        },
    ).json["data"]
    dispute_id = opened["dispute_id"]

    resolved = ctx["admin_client"].post(
        f"/api/v1/dispatch/disputes/{dispute_id}/resolve",
        json={"resolution": "补足席位差额 ¥500，由区域份额分摊"},
    )
    assert resolved.status_code == 200
    assert resolved.json["data"]["status"] == "resolved"

    again = ctx["admin_client"].post(
        f"/api/v1/dispatch/disputes/{dispute_id}/resolve",
        json={"resolution": "再裁一次"},
    )
    assert again.status_code == 409
    assert again.json["error"]["code"] == "invalid_dispute_state"

    empty = ctx["admin_client"].post(
        f"/api/v1/dispatch/disputes/{dispute_id}/resolve",
        json={"resolution": "  "},
    )
    assert empty.status_code == 400

    missing = ctx["admin_client"].post(
        f"/api/v1/dispatch/disputes/{uuid4()}/resolve",
        json={"resolution": "x"},
    )
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# POST /simulator/replay：只读回放
# ---------------------------------------------------------------------------


def test_replay_without_rule_version_marks_skipped(console_context):
    ctx = console_context
    response = ctx["admin_client"].post("/api/v1/dispatch/simulator/replay")
    assert response.status_code == 200
    data = response.json["data"]
    assert data["mode"] == "replay"
    assert data["rule_version"] is None
    assert data["summary"]["replayed"] == 1
    assert data["packages"][0]["skipped"] == "no_active_rule_version"


def test_replay_with_active_rule_version_scenarios(console_context, db_session):
    ctx = console_context
    db_session.add(
        DispatchRuleVersion(
            version_no=1,
            status="active",
            rule_snapshot={},
            published_at=datetime(2026, 11, 1, tzinfo=UTC),
            published_by_user_id=ctx["admin"].id,
        )
    )
    db_session.commit()

    response = ctx["admin_client"].post("/api/v1/dispatch/simulator/replay")
    assert response.status_code == 200
    data = response.json["data"]
    assert data["rule_version"] == 1
    row = data["packages"][0]
    # 空供给池：Stage A 全拒 → 场景 C（不自动派，人工兜底口径）
    assert row["scenario"] == "C"
    assert row["stage_a_pass"] is False
    # 只读纪律：回放不落 offer
    from fde_api.dispatch.models import DispatchOffer

    assert db_session.query(DispatchOffer).count() == 0

    forbidden = console_context["fde_client"].post("/api/v1/dispatch/simulator/replay")
    assert forbidden.status_code == 403


# ---------------------------------------------------------------------------
# GET /claim-gates：开闸看板
# ---------------------------------------------------------------------------


def test_claim_gates_lists_seed_cities_with_explainers(console_context):
    import json as _json
    from pathlib import Path

    seed = _json.loads(
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath("seeds/dispatch_cities.json")
        .read_text(encoding="utf-8")
    )
    expected = [row["city"] for row in seed["cities"]]

    response = console_context["admin_client"].get("/api/v1/dispatch/claim-gates")
    assert response.status_code == 200
    rows = response.json["data"]
    assert [row["city"] for row in rows] == expected
    first = rows[0]
    # 可解释明细：白名单 + 种子开关 + 三条件 + 终判
    assert first["whitelisted"] is True
    # §11.1 降级态：备案未完成，种子默认 false
    assert first["city_switch"] is False
    assert set(first["conditions"]) == {
        "supply_gt_demand",
        "reject_rate_ok",
        "rule_publicized",
    }
    assert first["claim_open"] is False
    assert "reject_rate" in first

    forbidden = console_context["fde_client"].get("/api/v1/dispatch/claim-gates")
    assert forbidden.status_code == 403
