"""P2-4 私单封堵（goal-r9，设计 §8.5 / 规则表「禁止私下接单的技术执行」）。

三钩子的可判定用例：
  H1 立项入口——派单线只能平台侧立项；直签缺省行为不变；
  H2 池内企业直签封堵——立项/报价双入口；复购走池放行；
  H3 渠道正交——直签项目不得建交付包。
封堵留痕走独立事务（主事务回滚后 OperationEvent 仍存活）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.dispatch.models import DeliveryPackage
from fde_api.dispatch.packages import create_package
from fde_api.projects.quote_service import QuoteServiceError, create_quote
from fde_api.projects.service import ProjectServiceError, create_project
from fde_api.solutions.models import ProjectSolution
from fde_api.workbench.models import (
    IndustryTemplateVersion,
    OperationEvent,
    Project,
    Quote,
)
from fde_api.workbench.seed import seed_workbench

from conftest import INITIAL_PASSWORD


# ---------------------------------------------------------------- 基础件

def _user(username: str, role: str = "admin") -> User:
    return User(
        username=f"{username}.{uuid4().hex[:8]}",
        display_name=username,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )


@pytest.fixture
def published_template(db_session):
    seed_workbench(db_session)
    db_session.commit()
    return db_session.scalar(
        select(IndustryTemplateVersion).where(
            IndustryTemplateVersion.status == "published"
        )
    )


def _create_project_via_service(
    db_session, template, *, actor: User, enterprise_code: str, business_line: str
) -> dict:
    return create_project(
        actor=actor,
        input={
            "name": f"r9 渠道项目 {business_line}",
            "enterprise_code": enterprise_code,
            "template_version_id": template.id,
            "leader_user_id": actor.id,
            "planned_start_date": "2026-11-03",
            "module_keys": ["pre_diagnosis"],
            "business_line": business_line,
        },
    )


def _pooled_enterprise_setup(db_session, *, enterprise_code: str):
    """造一个池内企业：派单线项目 + 方案 + 报价 + 交付包（H3 放行路径）。"""
    from fde_api.workbench.models import IndustryTemplate

    admin = _user("r9.pool.admin")
    template = IndustryTemplate(
        template_key=f"r9-tpl-{uuid4().hex[:8]}",
        name="r9 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="r9 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    project = Project(
        project_code=f"R9-{uuid4().hex[:6].upper()}",
        name="r9 池内项目",
        enterprise_code=enterprise_code,
        business_line="FDE_DISPATCH",
        planned_start_date=date(2026, 11, 3),
        leader_user_id=admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([admin, project])
    db_session.flush()
    solution = ProjectSolution(
        project_id=project.id, name="r9 方案", owner_user_id=admin.id
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
    db_session.commit()
    package = create_package(
        db_session,
        actor=admin,
        solution_id=solution.id,
        quote_id=quote.id,
    )
    db_session.commit()
    return admin, project, package


# ---------------------------------------------------------------- H1 立项入口

def test_dispatch_line_entry_platform_ok(db_session, client, settings):
    """平台侧以 FDE_DISPATCH 立项 → 落库 + 响应体带 business_line。"""
    from fde_api.workbench.seed import seed_workbench

    seed_workbench(db_session)
    db_session.commit()
    admin = _user("r9.entry.admin")
    db_session.add(admin)
    db_session.commit()
    template = db_session.scalar(
        select(IndustryTemplateVersion).where(
            IndustryTemplateVersion.status == "published"
        )
    )
    token = issue_access_token(admin, settings)
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "r9 派单线立项",
            "enterprise_code": f"r9 池源·制造·{uuid4().hex[:6]}",
            "template_version_id": template.id,
            "leader_user_id": admin.id,
            "planned_start_date": "2026-11-03",
            "module_keys": ["pre_diagnosis"],
            "business_line": "FDE_DISPATCH",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    assert response.json["data"]["business_line"] == "FDE_DISPATCH"


def test_dispatch_line_entry_non_platform_403(db_session, client, settings):
    """交付侧角色以派单线立项 → 403 dispatch_project_platform_only（H1 专属码）。"""
    from fde_api.workbench.seed import seed_workbench

    seed_workbench(db_session)
    db_session.commit()
    engineer = _user("r9.entry.engineer", role="fde_engineer")
    db_session.add(engineer)
    db_session.commit()
    template = db_session.scalar(
        select(IndustryTemplateVersion).where(
            IndustryTemplateVersion.status == "published"
        )
    )
    token = issue_access_token(engineer, settings)
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "r9 越权派单线立项",
            "enterprise_code": f"r9 越权·制造·{uuid4().hex[:6]}",
            "template_version_id": template.id,
            "leader_user_id": engineer.id,
            "planned_start_date": "2026-11-03",
            "module_keys": ["pre_diagnosis"],
            "business_line": "FDE_DISPATCH",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, response.get_data(as_text=True)
    # 路由 require_minimum_role("project_lead") 先于服务层——通用 forbidden；
    # H1 专属错误码在服务层直达（见下一个用例）。
    assert response.json["error"]["code"] == "forbidden"


def test_dispatch_line_entry_service_level_code(db_session, published_template):
    """服务层直达：fde_engineer 以派单线立项 → 专属码 dispatch_project_platform_only。"""
    engineer = _user("r9.svc.engineer", role="fde_engineer")
    db_session.add(engineer)
    db_session.commit()
    with pytest.raises(ProjectServiceError) as err:
        _create_project_via_service(
            db_session,
            published_template,
            actor=engineer,
            enterprise_code=f"r9 服务层·制造·{uuid4().hex[:6]}",
            business_line="FDE_DISPATCH",
        )
    assert err.value.code == "dispatch_project_platform_only"
    assert err.value.status == 403


def test_business_line_invalid_400(db_session, client, settings):
    """business_line 越界 → 400 invalid_business_line（枚举封闭）。"""
    from fde_api.workbench.seed import seed_workbench

    seed_workbench(db_session)
    db_session.commit()
    admin = _user("r9.badline.admin")
    db_session.add(admin)
    db_session.commit()
    template = db_session.scalar(
        select(IndustryTemplateVersion).where(
            IndustryTemplateVersion.status == "published"
        )
    )
    token = issue_access_token(admin, settings)
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "r9 越界渠道",
            "enterprise_code": f"r9 越界·制造·{uuid4().hex[:6]}",
            "template_version_id": template.id,
            "leader_user_id": admin.id,
            "planned_start_date": "2026-11-03",
            "module_keys": ["pre_diagnosis"],
            "business_line": "AGENCY",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400, response.get_data(as_text=True)
    assert response.json["error"]["code"] == "invalid_business_line"


def test_direct_entry_default_unchanged(db_session, client, settings):
    """不传 business_line 的存量直签立项行为不变（默认 FDE）。"""
    from fde_api.workbench.seed import seed_workbench

    seed_workbench(db_session)
    db_session.commit()
    admin = _user("r9.legacy.admin")
    db_session.add(admin)
    db_session.commit()
    template = db_session.scalar(
        select(IndustryTemplateVersion).where(
            IndustryTemplateVersion.status == "published"
        )
    )
    token = issue_access_token(admin, settings)
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "r9 存量直签",
            "enterprise_code": f"r9 直签·制造·{uuid4().hex[:6]}",
            "template_version_id": template.id,
            "leader_user_id": admin.id,
            "planned_start_date": "2026-11-03",
            "module_keys": ["pre_diagnosis"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201, response.get_data(as_text=True)
    assert response.json["data"]["business_line"] == "FDE"


# ---------------------------------------------------------------- H2 池内企业直签封堵

def test_private_deal_blocked_on_project(db_session, published_template):
    """池内企业 × 直签立项 → 422 private_deal_blocked。"""
    admin, _, _ = _pooled_enterprise_setup(
        db_session, enterprise_code=f"r9 封堵·制造·{uuid4().hex[:6]}"
    )
    # 该企业此刻已在池内（有交付包）；直签线再立项 → 封堵
    pooled_enterprise = db_session.scalar(
        select(Project.enterprise_code).where(Project.business_line == "FDE_DISPATCH")
    )
    with pytest.raises(ProjectServiceError) as err:
        _create_project_via_service(
            db_session,
            published_template,
            actor=admin,
            enterprise_code=pooled_enterprise,
            business_line="FDE",
        )
    assert err.value.code == "private_deal_blocked"
    assert err.value.status == 422


def test_repurchase_via_pool_allowed(db_session, published_template):
    """同企业复购走派单线 → 放行（§3.3 复购判据口径）。"""
    admin, _, _ = _pooled_enterprise_setup(
        db_session, enterprise_code=f"r9 复购·制造·{uuid4().hex[:6]}"
    )
    pooled_enterprise = db_session.scalar(
        select(Project.enterprise_code).where(Project.business_line == "FDE_DISPATCH")
    )
    dto = _create_project_via_service(
        db_session,
        published_template,
        actor=admin,
        enterprise_code=pooled_enterprise,
        business_line="FDE_DISPATCH",
    )
    assert dto["business_line"] == "FDE_DISPATCH"


def test_private_deal_blocked_on_quote_of_legacy_direct_project(
    db_session, published_template
):
    """存量直签项目（守门前的历史数据）× 池内企业 → 建报价同样封堵。"""
    admin, _, _ = _pooled_enterprise_setup(
        db_session, enterprise_code=f"r9 存量·制造·{uuid4().hex[:6]}"
    )
    pooled_enterprise = db_session.scalar(
        select(Project.enterprise_code).where(Project.business_line == "FDE_DISPATCH")
    )
    legacy = Project(
        project_code=f"R9L-{uuid4().hex[:6].upper()}",
        name="r9 存量直签项目",
        enterprise_code=pooled_enterprise,
        business_line="FDE",
        planned_start_date=date(2026, 11, 3),
        leader_user_id=admin.id,
        source_template_version=published_template,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add(legacy)
    db_session.commit()
    with pytest.raises(QuoteServiceError) as err:
        create_quote(
            actor=admin,
            project_id=legacy.id,
            payload={"preset": "first_order_defaults"},
        )
    assert err.value.code == "private_deal_blocked"
    assert err.value.status == 422


# ---------------------------------------------------------------- H3 渠道正交

def test_package_on_direct_project_blocked(db_session, published_template):
    """直签项目不得入池：create_package → 422 dispatch_line_required。"""
    from fde_api.workbench.models import IndustryTemplate

    admin = _user("r9.direct.admin")
    template = IndustryTemplate(
        template_key=f"r9d-tpl-{uuid4().hex[:8]}",
        name="r9d 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="r9d 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    direct = Project(
        project_code=f"R9D-{uuid4().hex[:6].upper()}",
        name="r9 直签项目",
        enterprise_code=f"r9 直签新客·制造·{uuid4().hex[:6]}",
        business_line="FDE",
        planned_start_date=date(2026, 11, 3),
        leader_user_id=admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([admin, direct])
    db_session.flush()
    solution = ProjectSolution(
        project_id=direct.id, name="r9d 方案", owner_user_id=admin.id
    )
    db_session.add(solution)
    db_session.flush()
    quote = Quote(
        project_id=direct.id,
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
    db_session.commit()
    from fde_api.dispatch.errors import DispatchServiceError

    with pytest.raises(DispatchServiceError) as err:
        create_package(
            db_session, actor=admin, solution_id=solution.id, quote_id=quote.id
        )
    assert err.value.code == "dispatch_line_required"
    assert err.value.status == 422


# ---------------------------------------------------------------- 封堵留痕（独立事务）

def test_block_writes_audit_event_surviving_rollback(
    db_session, published_template
):
    """封堵 → OperationEvent(private_deal_blocked) 独立事务存活（主事务已回滚）。"""
    admin, _, _ = _pooled_enterprise_setup(
        db_session, enterprise_code=f"r9 留痕·制造·{uuid4().hex[:6]}"
    )
    pooled_enterprise = db_session.scalar(
        select(Project.enterprise_code).where(Project.business_line == "FDE_DISPATCH")
    )
    with pytest.raises(ProjectServiceError):
        _create_project_via_service(
            db_session,
            published_template,
            actor=admin,
            enterprise_code=pooled_enterprise,
            business_line="FDE",
        )
    db_session.rollback()  # 主事务回滚后，留痕必须仍在
    event = db_session.scalar(
        select(OperationEvent)
        .where(OperationEvent.event_type == "private_deal_blocked")
        .order_by(OperationEvent.id.desc())
    )
    assert event is not None
    changes = event.changes or {}
    assert changes["hook"] == "H2_enterprise_channel"
    assert changes["enterprise_code"] == pooled_enterprise
