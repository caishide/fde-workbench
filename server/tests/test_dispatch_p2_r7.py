"""goal-r7 P2 批次回归（派单设计 §8.5：P2-3 business_line + P2-6 cities 扩字段
+ P2-1 服务端支撑路由 profiles/rules）。P2-2（Project.status 扩展）无目标枚举值
——设计/规则表/BP 均未给出新状态集，发明即违规（台账第十九节留注待拍板）。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from fde_api.auth.models import User
from fde_api.dispatch.models import DispatchOffer, FdeProfile
from fde_api.workbench.models import Project

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


# ---------------------------------------------------------------------------
# P2-3：business_line 'FDE_DISPATCH' 放行
# ---------------------------------------------------------------------------


def test_business_line_allows_dispatch_value(db_session):
    """CHECK 扩展：'FDE_DISPATCH' 可入库；既有 'FDE' 不受影响。"""
    admin = _user("r7.bl.admin")
    template = None
    from fde_api.workbench.models import IndustryTemplate, IndustryTemplateVersion

    template = IndustryTemplate(
        template_key=f"r7-tpl-{uuid4().hex[:8]}",
        name="r7 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="r7 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    db_session.add_all([admin, version])
    db_session.flush()
    dispatched = Project(
        project_code=f"R7-{uuid4().hex[:6].upper()}",
        name="派单池立项项目",
        enterprise_code=f"r7 企业·制造·{uuid4().hex[:4]}",
        planned_start_date=datetime(2026, 10, 31).date(),
        leader_user_id=admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
        business_line="FDE_DISPATCH",
    )
    db_session.add(dispatched)
    db_session.flush()
    assert dispatched.business_line == "FDE_DISPATCH"
    # 既有值仍可用
    legacy = Project(
        project_code=f"R7-{uuid4().hex[:6].upper()}",
        name="常规项目",
        enterprise_code=f"r7 企业·零售·{uuid4().hex[:4]}",
        planned_start_date=datetime(2026, 10, 31).date(),
        leader_user_id=admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add(legacy)
    db_session.flush()
    assert legacy.business_line == "FDE"
    # 非法值仍被 CHECK 拒绝
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db_session.add(
            Project(
                project_code=f"R7-{uuid4().hex[:6].upper()}",
                name="非法业务线",
                enterprise_code=f"r7 企业·x·{uuid4().hex[:4]}",
                planned_start_date=datetime(2026, 10, 31).date(),
                leader_user_id=admin.id,
                source_template_version=version,
                template_snapshot={"industry_name": "制造业", "modules": []},
                business_line="LOGISTICS",
            )
        )
        db_session.flush()
    db_session.rollback()


# ---------------------------------------------------------------------------
# P2-6：dispatch_cities 扩字段（subsidy_scheme 选填 + metro_group）
# ---------------------------------------------------------------------------


def test_dispatch_cities_extended_fields():
    payload = json.loads(
        (Path(SERVER_ROOT) / "seeds" / "dispatch_cities.json").read_text(encoding="utf-8")
    )
    assert payload["cities"], "六城种子"
    for row in payload["cities"]:
        # P2-6 扩字段进 schema：subsidy_scheme 选填（null 允许）、metro_group 必备
        assert "subsidy_scheme" in row
        assert "metro_group" in row and row["metro_group"]
        assert row["subsidy_scheme"] is None  # 种子默认未配置补贴


# ---------------------------------------------------------------------------
# P2-1 服务端支撑：profiles / rules 只读路由
# ---------------------------------------------------------------------------


@pytest.fixture
def api_user(db_session):
    admin = _user("r7.api.admin")
    engineer = _user("r7.api.eng", role="fde_engineer")
    db_session.add_all([admin, engineer])
    db_session.commit()
    return admin, engineer


def test_profiles_route_admin_only_and_shape(client, db_session, settings, api_user):
    from fde_api.auth.tokens import issue_access_token

    admin, engineer = api_user
    profile_user = _user("r7.prof.fde", role="fde_engineer")
    db_session.add(profile_user)
    db_session.add(
        FdeProfile(
            user_id=profile_user.id,
            level="L2",
            module_tags=["pre_diagnosis"],
            industry_tags=["制造业"],
            home_city="苏州",
            monthly_capacity_hours=100,
            avg_delivery_hours=10,
            status="active",
            is_active=True,
        )
    )
    db_session.add(
        DispatchOffer(
            package_id=_any_package_id(db_session),
            dispatch_round=1,
            candidate_user_id=profile_user.id,
            status="offered",
        )
    )
    db_session.commit()

    headers = {"Authorization": f"Bearer {issue_access_token(admin, settings)}"}
    response = client.get("/api/v1/dispatch/profiles", headers=headers)
    assert response.status_code == 200, response.get_data(as_text=True)
    rows = response.json["data"]
    target = next(row for row in rows if row["user_id"] == profile_user.id)
    assert target["level"] == "L2"
    assert target["scores"]["scenario_eng"] == 0  # 默认 0 起评
    assert target["capacity_cap"] == 10  # 100 // 10
    assert target["in_hand"] == 1  # 在途计数（跨包聚合）

    # 非平台侧 403
    eng_headers = {"Authorization": f"Bearer {issue_access_token(engineer, settings)}"}
    denied = client.get("/api/v1/dispatch/profiles", headers=eng_headers)
    assert denied.status_code == 403


def _any_package_id(db_session):
    from fde_api.dispatch.models import DeliveryPackage

    package_id = db_session.scalar(select(DeliveryPackage.id).limit(1))
    if package_id is None:
        # 造一个最小包（复用 r5 helper）
        import test_dispatch_p1_r5 as r5

        _admin, package = r5._onsite_package(db_session)
        return package.id
    return package_id


def test_rules_route_lists_versions_and_constants(client, db_session, settings, api_user):
    from fde_api.auth.tokens import issue_access_token
    from fde_api.dispatch.models import DispatchRuleVersion

    admin, _engineer = api_user
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
    db_session.commit()
    headers = {"Authorization": f"Bearer {issue_access_token(admin, settings)}"}
    response = client.get("/api/v1/dispatch/rules", headers=headers)
    assert response.status_code == 200
    payload = response.json["data"]
    versions = {row["version_no"]: row for row in payload["versions"]}
    assert 1 in versions and versions[1]["status"] == "active"
    assert versions[1]["rule_snapshot"]["seat_shares"]["delivery"] == 40
    # 只读常数节（§6.2）
    assert payload["constants"]["response_window_hours"] == 24
    assert payload["constants"]["top_n"] == 3
