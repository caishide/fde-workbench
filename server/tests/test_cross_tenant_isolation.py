"""M3c：跨企业越权套件骨架（企业 A 令牌打企业 B 资源）。

《M3a-隔离入口与装饰器扩展规格-v1》§3.6 与 ADR-M3 §3 定的施工顺序：
**套件先于端点改造入库**——本文件是 M3b 逐批销号的载体：

- 本轮（M3a）已覆盖的域：用例**直接绿**（项目／调研／文件／导出／AI 执行
  状态／API-action／对话），它们的作用是把「企业只见本企业」钉成 CI 事实；
- **尚未销号**的域：用例挂 ``xfail(strict=True)``——改造完成即 XPASS ⇒
  严格模式判失败 ⇒ **强制摘标记**。这把「销号」从人工纪律变成机械闸。

**关键场景＝跨企业成员关系**：企业甲的账号被（平台身份）加进企业乙的项目
——按 org 归属维度收敛后不可见。只测「素不相识的账号」不构成判别力
（成员关系本来就会挡住），跨企业成员关系才是 org 维度真正要挡的场景。

覆盖面（任务书 §7-M3c）：项目／调研表／文件／导出／AI 执行状态／
API-action 确认／对话。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.agents.models import AgentRegistry, AgentRun
from fde_api.auth.tokens import issue_access_token
from fde_api.control.chat import AIConversation
from fde_api.research.models import (
    ProjectResearchExport,
    ProjectResearchForm,
    ProjectResearchSubject,
)
from fde_api.workbench.models import OperationEvent

from multi_tenant_harness import (
    add_member,
    make_enterprise_org,
    make_project,
    make_user,
)


def _code() -> str:
    return f"M3{uuid4().hex[:8]}"


def _auth(user, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


@pytest.fixture
def two_enterprises(db_session):
    """两个企业 org（甲／乙）——代号化名，无客户真实信息。"""
    return (
        make_enterprise_org(db_session),
        make_enterprise_org(db_session),
    )


@pytest.fixture
def cross_org_world(db_session, two_enterprises):
    """跨企业世界：企业甲的账号在企业乙的项目里**有成员关系**。

    返回的 ``world`` 字典含：两个 org、两个账号、乙方项目，以及挂在乙方
    项目上的各域资源（调研对象／调研表／导出任务／AI 执行 run／对话会话／
    待确认 API-action）。
    """
    org_a, org_b = two_enterprises
    user_a = make_user(db_session, "fde_engineer", org_id=org_a.id)
    user_b = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_project(db_session, user_b, code=_code(), org_id=org_b.id)
    # 跨企业成员关系：平台身份授予的「越界成员」——org 维度必须把它收回来
    add_member(db_session, project_b, user_a)

    subject = ProjectResearchSubject(
        project_id=project_b.id,
        subject_type="company",
        subject_key=f"subject-{uuid4().hex[:8]}",
        name="隔离用例调研对象",
    )
    db_session.add(subject)
    db_session.flush()
    form = ProjectResearchForm(
        project_id=project_b.id,
        subject_id=subject.id,
        form_key=f"form-{uuid4().hex[:8]}",
        name="隔离用例调研表",
    )
    db_session.add(form)
    db_session.flush()
    export = ProjectResearchExport(
        project_id=project_b.id,
        form_id=form.id,
        requested_by_user_id=user_b.id,
        status="queued",
    )
    db_session.add(export)

    registry = AgentRegistry(
        kind="zcode",
        name="隔离用例智能体",
        enabled=True,
        capability_tier="agent.code.write",
        sandbox_profile="default",
        credential_ref=None,
        allowed_tools=["read_file"],
        max_cost_units=0,
        max_duration_ms=0,
    )
    db_session.add(registry)
    db_session.flush()
    run = AgentRun(
        project_id=project_b.id,
        agent_id=registry.id,
        initiated_by_user_id=user_b.id,
        capability_used="agent.code.write",
        context_ref="masked://isolation-case",
        idempotency_key=f"m3-{uuid4().hex}",
    )
    db_session.add(run)

    conversation = AIConversation(
        user_id=user_b.id,
        title="隔离用例会话",
        project_id=project_b.id,
        source="desktop",
    )
    db_session.add(conversation)

    action_id = uuid4().hex + uuid4().hex
    db_session.add(
        OperationEvent(
            actor_user_id=user_b.id,
            project_id=project_b.id,
            target_type="ai_api_action",
            target_id=action_id,
            event_type="ai.api.requested",
            changes={
                "description": "隔离用例待确认操作",
                "operation": "projects.get",
                "parameters": {},
                "body": {},
                "query": {},
                "confirmation_required": True,
            },
        )
    )
    db_session.commit()

    return {
        "org_a": org_a,
        "org_b": org_b,
        "user_a": user_a,
        "user_b": user_b,
        "project_b": project_b,
        "export": export,
        "run": run,
        "conversation": conversation,
        "action_id": action_id,
    }


# ---------------------------------------------------------------------------
# 覆盖面一：项目
# ---------------------------------------------------------------------------


def test_cross_tenant_project_detail_denied(client, db_session, settings, cross_org_world):
    """企业甲账号读企业乙的项目详情 ⇒ 403/404（不确认面存在）。"""
    response = client.get(
        f"/api/v1/projects/{cross_org_world['project_b'].id}",
        headers=_auth(cross_org_world["user_a"], settings),
    )
    assert response.status_code in (403, 404)


def test_cross_tenant_project_list_excludes_other_org(client, db_session, settings, cross_org_world):
    """企业甲账号的项目列表里**不得出现**企业乙的项目。"""
    response = client.get(
        "/api/v1/projects",
        headers=_auth(cross_org_world["user_a"], settings),
    )
    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert cross_org_world["project_b"].id not in {row["id"] for row in items}


# ---------------------------------------------------------------------------
# 覆盖面二：调研表
# ---------------------------------------------------------------------------


def test_cross_tenant_research_subjects_denied(client, db_session, settings, cross_org_world):
    """企业甲账号读企业乙项目的调研对象 ⇒ 403/404。"""
    response = client.get(
        f"/api/v1/projects/{cross_org_world['project_b'].id}/research/subjects",
        headers=_auth(cross_org_world["user_a"], settings),
    )
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 覆盖面三：文件
# ---------------------------------------------------------------------------


def test_cross_tenant_project_files_denied(client, db_session, settings, cross_org_world):
    """企业甲账号读企业乙项目的文件清单 ⇒ 403/404。"""
    response = client.get(
        f"/api/v1/projects/{cross_org_world['project_b'].id}/files",
        headers=_auth(cross_org_world["user_a"], settings),
    )
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 覆盖面四：导出
# ---------------------------------------------------------------------------


def test_cross_tenant_research_export_denied(client, db_session, settings, cross_org_world):
    """企业甲账号读企业乙项目的调研导出任务 ⇒ 403/404。"""
    response = client.get(
        f"/api/v1/projects/{cross_org_world['project_b'].id}"
        f"/research/exports/{cross_org_world['export'].id}",
        headers=_auth(cross_org_world["user_a"], settings),
    )
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 覆盖面五：AI 执行状态
# ---------------------------------------------------------------------------


def test_cross_tenant_agent_run_status_denied(client, db_session, settings, cross_org_world):
    """企业甲账号读企业乙项目的 AI 执行状态 ⇒ 403/404。"""
    response = client.get(
        f"/api/v1/agents/runs/{cross_org_world['run'].id}",
        headers=_auth(cross_org_world["user_a"], settings),
    )
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 覆盖面六：API-action 确认
# ---------------------------------------------------------------------------


def test_cross_tenant_api_action_not_listed(client, db_session, settings, cross_org_world):
    """企业甲账号的待确认操作清单里**不得出现**企业乙账号的操作。"""
    response = client.get(
        "/api/v1/ai/actions",
        headers=_auth(cross_org_world["user_a"], settings),
    )
    assert response.status_code == 200
    identifiers = {row["id"] for row in response.get_json()["data"]["items"]}
    assert cross_org_world["action_id"] not in identifiers


# ---------------------------------------------------------------------------
# 覆盖面七：对话
# ---------------------------------------------------------------------------


def test_cross_tenant_chat_conversation_denied(client, db_session, settings, cross_org_world):
    """企业甲账号读企业乙账号的对话会话 ⇒ 404（会话属主隔离）。"""
    response = client.get(
        f"/api/v1/ai/chat/conversations/{cross_org_world['conversation'].id}",
        headers=_auth(cross_org_world["user_a"], settings),
    )
    assert response.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 待销号域：跨 org 写动作留痕（M3b 批次 ① 平台控制面）
# ---------------------------------------------------------------------------


@pytest.mark.xfail(
    strict=True,
    reason="M3b 待销号：平台身份对**别家企业**账号的写动作必须落 cross_org_ 留痕"
    "（《M3a 规格》§3.4）——改造完成即 XPASS，严格模式强制摘标记",
)
def test_cross_org_write_action_leaves_audit_event(
    client, db_session, settings, cross_org_world
):
    """平台身份改**别家企业**账号的 AI 授权 ⇒ 必须留痕（``cross_org_`` 前缀事件）。

    现状：admin 代改他人授权只落 ``ai_access.updated`` 事件（无跨 org 语义）
    ⇒ 本用例红——M3b 批次 ① 改造后转绿，届时摘掉 ``xfail`` 标记。
    """
    admin = make_user(db_session, "admin")
    user_b = cross_org_world["user_b"]

    response = client.patch(
        f"/api/v1/users/{user_b.id}/ai-access",
        json={"level": "assistant_read"},
        headers=_auth(admin, settings),
    )
    assert response.status_code == 200

    events = db_session.scalars(
        select(OperationEvent).where(
            OperationEvent.actor_user_id == admin.id,
            OperationEvent.target_type == "user_ai_access",
            OperationEvent.target_id == user_b.id,
        )
    ).all()
    assert any(
        event.event_type.startswith("cross_org_") for event in events
    ), "跨 org 写动作未留痕（缺 cross_org_ 前缀事件）"
