"""M3b 批次 ①-b（模板·任务中心·内部面 15 端点）越权与收拢套件。

依据：《M3a-隔离入口与装饰器扩展规格-v1》§3 ＋ 2026-11-11 拍板（留痕触发面
＝企业 org 之间；read-only 核验＝域级代表性用例）。

本轮核心＝**待 M0 补充 #6 销号**：``control/service.py::_project_scope`` 是
可见性的**第三套规则**（leader-OR-成员、无 org 谓词、leader 分支无角色尺）
——批次 ①-b 把它收拢进统一入口 ``visible_project_filter``（M3a 单一权威），
消费点 ``list_task_center``／``list_automation_approvals`` 两处。关键场景
仍是**跨企业成员关系**：企业乙账号被加进企业甲项目后，控制台面不得经
``_project_scope`` 旧路径漏出（幽灵行防线对控制台域补齐）。

核验销号（零代码改动面，盘点表处置建议逐条人工复核）：
- industry-templates 6 条写面 ＋ templates research-forms 3 条写面：
  ``@require_role("admin")`` 角色闸在位（R2 目录写 admin-only 保持）；
- internal 3 条：**服务间认证**（DSH 服务令牌／ClawBot 网关令牌，非 JWT
  用户面，org 维度不适用——M4 令牌租户化的输入，维度 5 已登记）；
- task-center 3 条写面：服务层经 ``authorize_ai_capability → project_access``
  （统一入口含 org 谓词）✓。
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from fde_api.auth.tokens import issue_access_token
from fde_api.control.models import AutomationApproval

from multi_tenant_harness import (
    add_member,
    make_enterprise_org,
    make_project,
    make_user,
)


def _auth(user, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _seed_approval(db_session, project, requester) -> AutomationApproval:
    row = AutomationApproval(
        run_id=None,
        workflow_node_run_id=None,
        project_id=project.id,
        requested_by_user_id=requester.id,
        request_key=f"rk-{uuid4().hex[:8]}",
        capability="task.batch_assign",
        tool_name="project_tasks.batch_assign",
        arguments_json={"task_ids": ["t-1"]},
        arguments_sha256="a" * 64,
        risk_level=3,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture
def cross_org_fixture(db_session):
    """企业甲项目（平台身份 leader）＋待审批＋企业乙账号的跨企业成员关系。"""
    from datetime import date

    from fde_api.workbench.models import ModuleCatalog, ProjectModule, ProjectTask

    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    leader = make_user(db_session, "project_lead")
    user_b = make_user(db_session, "viewer", org_id=org_b.id)
    project = make_project(
        db_session, leader, code=f"m3b1b{uuid4().hex[:6]}", org_id=org_a.id
    )
    # 关键场景：企业乙账号被（平台身份）加进企业甲项目＝跨企业成员关系
    add_member(db_session, project, user_b, role="viewer")
    approval = _seed_approval(db_session, project, leader)
    # 任务清单面夹具（list_task_center 的 project_tasks 消费点）
    catalog = ModuleCatalog(module_key=f"m3b1b_{uuid4().hex[:8]}", name=f"越权套件模块{uuid4().hex[:6]}")
    db_session.add(catalog)
    db_session.flush()
    module = ProjectModule(
        project_id=project.id,
        module_catalog_id=catalog.id,
        name=catalog.name,
    )
    db_session.add(module)
    db_session.flush()
    task = ProjectTask(
        project_module_id=module.id,
        task_key=f"m3b1b-{uuid4().hex[:6]}",
        name="越权套件任务",
        planned_start_date=date(2026, 11, 11),
        planned_end_date=date(2026, 11, 12),
        duration_days=1,
    )
    db_session.add(task)
    db_session.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "leader": leader,
        "user_b": user_b,
        "project": project,
        "approval": approval,
        "task": task,
    }


# ---------------------------------------------------------------------------
# 核心销号项：_project_scope 收拢（待 M0 补充 #6）
# ---------------------------------------------------------------------------


def test_cross_enterprise_member_cannot_see_control_plane_approvals(
    client, db_session, settings, cross_org_fixture
):
    """企业乙成员打企业甲项目 ⇒ 控制台审批清单不含（幽灵行防线·控制台域）。"""
    user_b = cross_org_fixture["user_b"]
    approval = cross_org_fixture["approval"]
    leader = cross_org_fixture["leader"]

    listed = client.get(
        "/api/v1/task-center/approvals", headers=_auth(user_b, settings)
    ).get_json()
    listed_ids = {item["id"] for item in listed["data"]["items"]}
    assert approval.id not in listed_ids, "跨企业成员关系经旧 _project_scope 路径漏出"

    # 平台身份 leader（同域）照常可见——收拢不伤存量主路径
    leader_listed = client.get(
        "/api/v1/task-center/approvals", headers=_auth(leader, settings)
    ).get_json()
    assert approval.id in {item["id"] for item in leader_listed["data"]["items"]}


def test_cross_enterprise_member_cannot_see_task_center_tasks(
    client, db_session, settings, cross_org_fixture
):
    """企业乙成员 ⇒ 任务中心主清单（project_tasks）不含跨企业项目任务。"""
    user_b = cross_org_fixture["user_b"]
    task = cross_org_fixture["task"]
    leader = cross_org_fixture["leader"]

    listed = client.get("/api/v1/task-center", headers=_auth(user_b, settings)).get_json()
    listed_ids = {item["id"] for item in listed["data"]["items"]}
    assert task.id not in listed_ids, "跨企业项目任务经旧 _project_scope 路径漏出（主清单）"

    leader_listed = client.get(
        "/api/v1/task-center", headers=_auth(leader, settings)
    ).get_json()
    assert task.id in {item["id"] for item in leader_listed["data"]["items"]}


def test_cross_enterprise_member_cannot_decide_approval(
    client, db_session, settings, cross_org_fixture
):
    """企业乙成员审批企业甲项目的请求 ⇒ 403（统一入口 org 谓词收敛）。"""
    user_b = cross_org_fixture["user_b"]
    approval = cross_org_fixture["approval"]

    response = client.post(
        f"/api/v1/task-center/approvals/{approval.id}/decision",
        json={"decision": "approve", "password": "whatever", "reason": "probe"},
        headers=_auth(user_b, settings),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# R2 目录写：admin 角色闸核验（企业 viewer 全 403）
# ---------------------------------------------------------------------------


def test_industry_template_writes_admin_gated(client, db_session, settings):
    """行业模板目录 6 条写面＝admin 角色闸（企业 viewer 全 403）。"""
    org_a = make_enterprise_org(db_session)
    viewer = make_user(db_session, "viewer", org_id=org_a.id)
    headers = _auth(viewer, settings)

    assert (
        client.post(
            "/api/v1/industry-templates",
            json={"name": "probe", "industry_name": "制造"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/industry-templates/{uuid4()}/versions", headers=headers
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/industry-templates/versions/{uuid4()}",
            json={"version": 1},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.delete(
            f"/api/v1/industry-templates/versions/{uuid4()}", headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/industry-templates/versions/{uuid4()}/publish",
            json={"password": "x"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/industry-templates/versions/{uuid4()}/deactivate",
            json={"password": "x"},
            headers=headers,
        ).status_code
        == 403
    )


def test_research_forms_writes_admin_gated(client, db_session, settings):
    """调研表单目录 3 条写面＝admin 角色闸（企业 viewer 全 403）。"""
    org_a = make_enterprise_org(db_session)
    viewer = make_user(db_session, "viewer", org_id=org_a.id)
    headers = _auth(viewer, settings)
    base = f"/api/v1/templates/{uuid4()}/versions/{uuid4()}/research-forms"

    assert client.post(base, json={}, headers=headers).status_code == 403
    assert client.put(base, json={}, headers=headers).status_code == 403
    assert client.delete(base, headers=headers).status_code == 403


# ---------------------------------------------------------------------------
# internal 服务间面：非 JWT 认证核验（M4 令牌租户化输入）
# ---------------------------------------------------------------------------


def test_internal_service_faces_reject_bad_tokens(client, db_session, settings):
    """DSH／ClawBot 服务间面坏令牌 ⇒ 401（服务间认证在位，无用户面越权路径）。"""
    bad = {"Authorization": "Bearer not-a-real-token"}
    assert (
        client.post(
            f"/api/v1/internal/dsh/executions/{uuid4()}/approvals",
            json={},
            headers=bad,
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"/api/v1/internal/dsh/approvals/{uuid4()}/execute", headers=bad
        ).status_code
        == 401
    )
    assert (
        client.post("/api/v1/internal/clawbot/events", json={}, headers=bad).status_code
        == 401
    )
