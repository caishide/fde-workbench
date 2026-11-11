"""M3b 批次 ①-a（AI 与扩展控制面 24 端点）越权与留痕套件。

依据：《M3a-隔离入口与装饰器扩展规格-v1》§3（服务层校验／fail-closed／
跨 org 留痕／失败码闭集）＋ 2026-11-11 拍板（留痕触发面＝**企业 org 之间**，
平台内部桶不算）。

覆盖面（盘点表维度 2 批次 ① 的 ai／extensions／modules／document-templates／
users ai-access 五个蓝图域）：

- **R1/R2 平台管理面**（模型供应商、模型目录、插件目录同步、公共 Skill
  治理、公共模型配置、插件审批）：只认**平台身份**——企业身份即使被授予
  ``system_operator`` AI 档也一律 403（``is_platform_operator`` 单一判定）；
- **R3 主体归属**（lcsc 执行记录、个人 Skill、个人模型配置）：owner 之外
  一律 404/403（不确认资源存在）；
- **跨 org 留痕**（规格 §3.4）：admin 代改**别家企业**账号的 AI 授权／
  代审批**别家企业**账号的插件变更 ⇒ 事件带 ``cross_org_`` 前缀且 org
  维度取被作用账号归属；平台身份目标保持原事件名（存量零回归）。
"""
from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import select

from fde_api.auth.tokens import issue_access_token
from fde_api.control.access import CAPABILITY_REQUIREMENTS
from fde_api.control.lcsc_skills import LcscSkillRun
from fde_api.control.model_preferences import ModelPreference
from fde_api.control.models import PluginChangeRequest, PluginPackage, SkillDefinition
from fde_api.workbench.models import OperationEvent

from conftest import INITIAL_PASSWORD
from multi_tenant_harness import make_enterprise_org, make_user


def _auth(user, settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------


def _grant_system_operator(db_session, user, admin) -> None:
    """给账号授 system_operator AI 档——证明 org 维度独立于 AI 档生效。"""
    from fde_api.control.models import UserAIAccessGrant

    db_session.add(
        UserAIAccessGrant(
            user_id=user.id,
            access_level="system_operator",
            granted_by_user_id=admin.id,
            reason="越权套件：企业身份持最高 AI 档",
        )
    )
    db_session.commit()


def _public_skill(db_session, admin) -> SkillDefinition:
    skill = SkillDefinition(
        scope="public",
        namespace_key="public",
        skill_key=f"m3b.public.{uuid4().hex[:8]}",
        name="越权套件公共技能",
        status="published",
        created_by_user_id=admin.id,
    )
    db_session.add(skill)
    db_session.commit()
    return skill


def _personal_skill(db_session, owner) -> SkillDefinition:
    skill = SkillDefinition(
        scope="personal",
        namespace_key=owner.id,
        skill_key=f"m3b.personal.{uuid4().hex[:8]}",
        name="越权套件个人技能",
        status="published",
        owner_user_id=owner.id,
        created_by_user_id=owner.id,
    )
    db_session.add(skill)
    db_session.commit()
    return skill


def _public_preference(db_session) -> ModelPreference:
    pref = ModelPreference(
        scope="public",
        owner_user_id=None,
        name="越权套件公共模型",
        provider="openai",
        base_url="https://api.example.com/v1",
        model="gpt-x",
    )
    db_session.add(pref)
    db_session.commit()
    return pref


def _lcsc_run(db_session, user, *, skill_key: str) -> LcscSkillRun:
    run = LcscSkillRun(
        user_id=user.id,
        execution_id=str(uuid4()),
        request_sha256=sha256(uuid4().hex.encode()).hexdigest(),
        skill_key=skill_key,
        query="越权套件查询",
        status="completed",
        started_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.commit()
    return run


# ---------------------------------------------------------------------------
# R1/R2：平台管理面对企业身份 fail-closed（即使持 system_operator AI 档）
# ---------------------------------------------------------------------------


def test_enterprise_operator_blocked_from_platform_private_writes(
    client, db_session, settings
):
    """企业身份＋system_operator AI 档 ⇒ 模型供应商／模型目录／目录同步全 403。"""
    admin = make_user(db_session, "admin")
    org_a = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    _grant_system_operator(db_session, user_a, admin)
    headers = _auth(user_a, settings)

    provider_payload = {
        "key": f"m3bprov{uuid4().hex[:8]}",
        "name": "越权套件供应商",
        "base_url": "https://api.example.com",
        "credential_ref": "env:PROBE_KEY",
        "credential_hint": "probe",
        "status": "active",
    }
    assert client.post(
        "/api/v1/extensions/providers", json=provider_payload, headers=headers
    ).status_code == 403
    assert client.post(
        "/api/v1/extensions/models",
        json={
            "provider_key": provider_payload["key"],
            "key": "m3b-model",
            "name": "越权套件模型",
            "context_window": 8192,
            "supports_tools": True,
            "supports_json": True,
            "status": "active",
        },
        headers=headers,
    ).status_code == 403
    assert (
        client.post("/api/v1/extensions/marketplace/sync", json={}, headers=headers).status_code
        == 403
    )


def test_enterprise_operator_blocked_from_public_skill_governance(
    client, db_session, settings
):
    """企业身份＋system_operator AI 档 ⇒ 公共 Skill 全治理动作与开关全 403。"""
    admin = make_user(db_session, "admin")
    org_a = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    _grant_system_operator(db_session, user_a, admin)
    skill = _public_skill(db_session, admin)
    headers = _auth(user_a, settings)

    save_payload = {
        "key": f"m3b.public.{uuid4().hex[:8]}",
        "name": "越权套件公共技能二",
        "description": "",
        "instructions": "step",
        "manifest": {},
        "required_capabilities": [next(iter(CAPABILITY_REQUIREMENTS))],
    }
    assert client.post(
        "/api/v1/extensions/skills/public", json=save_payload, headers=headers
    ).status_code == 403
    for action in ("submit-review", "publish", "rollback", "deprecate"):
        response = client.post(
            f"/api/v1/extensions/skills/{skill.id}/{action}",
            json={"password": INITIAL_PASSWORD, "reason": "probe"},
            headers=headers,
        )
        assert response.status_code == 403, action
    # PATCH 开关不得旁路治理（can_edit 对企业身份恒 False）
    assert (
        client.patch(
            f"/api/v1/extensions/skills/{skill.id}",
            json={"status": "deprecated"},
            headers=headers,
        ).status_code
        == 403
    )


def test_enterprise_operator_blocked_from_public_model_preferences(
    client, db_session, settings
):
    """企业身份＋system_operator AI 档 ⇒ 公共模型配置写／删全 403。"""
    admin = make_user(db_session, "admin")
    org_a = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    _grant_system_operator(db_session, user_a, admin)
    pref = _public_preference(db_session)
    headers = _auth(user_a, settings)

    assert client.post(
        "/api/v1/extensions/model-preferences",
        json={
            "scope": "public",
            "name": "越权套件公共模型二",
            "provider": "openai",
            "base_url": "https://api.example.com/v1",
            "model": "gpt-y",
            "api_key": "",
            "is_default": False,
            "supports_tools": True,
        },
        headers=headers,
    ).status_code == 403
    assert (
        client.delete(
            f"/api/v1/extensions/model-preferences/{pref.id}",
            json={"password": INITIAL_PASSWORD},
            headers=headers,
        ).status_code
        == 403
    )


def test_enterprise_operator_blocked_from_plugin_change_decision(
    client, db_session, settings
):
    """企业身份＋system_operator AI 档 ⇒ 插件变更审批 403（门禁先于存在性）。"""
    admin = make_user(db_session, "admin")
    org_a = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    _grant_system_operator(db_session, user_a, admin)
    response = client.post(
        f"/api/v1/extensions/plugin-requests/{uuid4()}/decision",
        json={"decision": "reject", "reason": "probe"},
        headers=_auth(user_a, settings),
    )
    assert response.status_code == 403


def test_enterprise_viewer_blocked_from_user_admin_surfaces(
    client, db_session, settings
):
    """企业身份 ⇒ 用户管理读／写面 403（_require_admin 既有闸复核）。"""
    org_a = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    user_b = make_user(db_session, "viewer")
    headers = _auth(user_a, settings)
    assert (
        client.get(f"/api/v1/users/{user_b.id}/ai-access", headers=headers).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/users/{user_b.id}/ai-access",
            json={"level": "assistant_read"},
            headers=headers,
        ).status_code
        == 403
    )


# ---------------------------------------------------------------------------
# 跨 org 留痕（规格 §3.4；触发面＝企业 org 之间，拍板 2026-11-11）
# ---------------------------------------------------------------------------


def test_admin_cross_org_ai_access_leaves_cross_org_event(
    client, db_session, settings
):
    """admin 代改**别家企业**账号 AI 授权 ⇒ ``cross_org_`` 前缀事件＋org 维度。"""
    admin = make_user(db_session, "admin")
    org_b = make_enterprise_org(db_session)
    user_b = make_user(db_session, "viewer", org_id=org_b.id)

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
        event.event_type == "cross_org_ai_access.updated" for event in events
    ), "跨 org 写动作未留痕（缺 cross_org_ 前缀事件）"
    event = next(e for e in events if e.event_type == "cross_org_ai_access.updated")
    assert event.org_id == org_b.id, "跨 org 事件的 org 维度须取被作用账号归属"


def test_admin_platform_target_ai_access_event_unchanged(
    client, db_session, settings
):
    """admin 改**平台身份**账号 ⇒ 事件名保持 ``ai_access.updated``（存量零回归）。"""
    admin = make_user(db_session, "admin")
    user_p = make_user(db_session, "viewer")

    response = client.patch(
        f"/api/v1/users/{user_p.id}/ai-access",
        json={"level": "assistant_read"},
        headers=_auth(admin, settings),
    )
    assert response.status_code == 200
    events = db_session.scalars(
        select(OperationEvent).where(OperationEvent.target_id == user_p.id)
    ).all()
    assert [e.event_type for e in events] == ["ai_access.updated"]
    assert all(e.org_id is None for e in events)


def _pending_plugin_request(db_session, admin, target_user) -> PluginChangeRequest:
    plugin = PluginPackage(
        plugin_key=f"m3b.plugin.{uuid4().hex[:8]}",
        name="越权套件插件",
        current_version="1.0.0",
        package_sha256=sha256(uuid4().hex.encode()).hexdigest(),
        status="active",
        created_by_user_id=admin.id,
    )
    db_session.add(plugin)
    db_session.flush()
    request = PluginChangeRequest(
        plugin_id=plugin.id,
        target_user_id=target_user.id,
        requested_by_user_id=target_user.id,
        action="install",
        target_version="1.0.0",
        requested_capabilities=[],
        status="pending",
        request_reason="probe",
    )
    db_session.add(request)
    db_session.commit()
    return request


def test_admin_cross_org_plugin_decision_leaves_cross_org_event(
    client, db_session, settings
):
    """admin 代审批**别家企业**账号的插件变更 ⇒ ``cross_org_`` 前缀事件。"""
    admin = make_user(db_session, "admin")
    org_b = make_enterprise_org(db_session)
    user_b = make_user(db_session, "viewer", org_id=org_b.id)
    request_b = _pending_plugin_request(db_session, admin, user_b)

    response = client.post(
        f"/api/v1/extensions/plugin-requests/{request_b.id}/decision",
        json={"decision": "reject", "reason": "越权套件驳回"},
        headers=_auth(admin, settings),
    )
    assert response.status_code == 200

    events = db_session.scalars(
        select(OperationEvent).where(
            OperationEvent.event_type == "cross_org_plugin_change.decided"
        )
    ).all()
    assert len(events) == 1
    assert events[0].org_id == org_b.id
    assert events[0].target_id == request_b.id
    assert events[0].changes["decision"] == "reject"


def test_admin_platform_target_plugin_decision_leaves_no_cross_org_event(
    client, db_session, settings
):
    """admin 审批**平台身份**账号的插件变更 ⇒ 不产生跨 org 事件（零噪声钉）。"""
    admin = make_user(db_session, "admin")
    user_p = make_user(db_session, "viewer")
    request_p = _pending_plugin_request(db_session, admin, user_p)

    response = client.post(
        f"/api/v1/extensions/plugin-requests/{request_p.id}/decision",
        json={"decision": "reject", "reason": "越权套件驳回"},
        headers=_auth(admin, settings),
    )
    assert response.status_code == 200
    events = db_session.scalars(
        select(OperationEvent).where(
            OperationEvent.event_type == "cross_org_plugin_change.decided"
        )
    ).all()
    assert events == []


# ---------------------------------------------------------------------------
# R3：主体归属（owner 之外一律 404/403，不确认资源存在）
# ---------------------------------------------------------------------------


def test_lcsc_runs_owner_scope_blocks_cross_tenant(client, db_session, settings):
    """企业 A 令牌打企业 B 的执行记录 ⇒ 对比 404＋列表只见自己的行。"""
    admin = make_user(db_session, "admin")
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    user_b = make_user(db_session, "viewer", org_id=org_b.id)
    _grant_system_operator(db_session, user_a, admin)
    run_b1 = _lcsc_run(db_session, user_b, skill_key="lcsc-browser-baseline")
    run_b2 = _lcsc_run(db_session, user_b, skill_key="lcsc-browser-jev")
    run_a = _lcsc_run(db_session, user_a, skill_key="lcsc-browser-baseline")
    headers = _auth(user_a, settings)

    response = client.post(
        "/api/v1/ai/lcsc-runs/compare",
        json={"baseline_id": run_b1.id, "jev_id": run_b2.id},
        headers=headers,
    )
    assert response.status_code == 404

    listed = client.get("/api/v1/ai/lcsc-runs", headers=headers).get_json()
    listed_ids = {item["id"] for item in listed["data"]["items"]}
    assert run_a.id in listed_ids
    assert run_b1.id not in listed_ids and run_b2.id not in listed_ids


def test_lcsc_desktop_run_ownership_blocks_cross_tenant(
    client, db_session, settings
):
    """企业 A 令牌对 B 的桌面执行记录续写 ⇒ 404（own_run 不确认存在）。"""
    admin = make_user(db_session, "admin")
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    user_b = make_user(db_session, "viewer", org_id=org_b.id)
    _grant_system_operator(db_session, user_a, admin)
    run_b = _lcsc_run(db_session, user_b, skill_key="lcsc-browser-baseline")

    response = client.post(
        f"/api/v1/ai/lcsc-runs/desktop/{run_b.id}/complete",
        json={"steps": [], "duration_ms": 1000},
        headers=_auth(user_a, settings),
    )
    assert response.status_code == 404


def test_personal_skill_owner_scope_blocks_cross_tenant(
    client, db_session, settings
):
    """企业 A 对 B 的个人 Skill 下架 ⇒ 403（can_edit 只认 owner）。"""
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    user_b = make_user(db_session, "viewer", org_id=org_b.id)
    skill_b = _personal_skill(db_session, user_b)

    response = client.patch(
        f"/api/v1/extensions/skills/{skill_b.id}",
        json={"status": "deprecated"},
        headers=_auth(user_a, settings),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# 读面收敛核验（域级代表——拍板 2026-11-11：域级代表性用例进 CI）
# ---------------------------------------------------------------------------


def test_model_preferences_list_self_scoped(client, db_session, settings):
    """extensions 域：个人模型配置列表只见自己的（别人的 personal 行不外泄）。"""
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    user_b = make_user(db_session, "viewer", org_id=org_b.id)
    pref_a = ModelPreference(
        scope="personal",
        owner_user_id=user_a.id,
        name="甲的私有模型",
        provider="openai",
        base_url="https://api.example.com/v1",
        model="gpt-a",
    )
    pref_b = ModelPreference(
        scope="personal",
        owner_user_id=user_b.id,
        name="乙的私有模型",
        provider="openai",
        base_url="https://api.example.com/v1",
        model="gpt-b",
    )
    db_session.add_all([pref_a, pref_b])
    db_session.commit()

    listed = client.get(
        "/api/v1/extensions/model-preferences", headers=_auth(user_a, settings)
    ).get_json()
    listed_ids = {item["id"] for item in listed["data"]["items"]}
    assert pref_a.id in listed_ids
    assert pref_b.id not in listed_ids


def test_role_gated_catalog_writes_block_enterprise_viewer(
    client, db_session, settings
):
    """modules／document-templates 域：企业 viewer 写目录 ⇒ 403（角色闸复核）。"""
    org_a = make_enterprise_org(db_session)
    user_a = make_user(db_session, "viewer", org_id=org_a.id)
    headers = _auth(user_a, settings)

    assert (
        client.post(
            "/api/v1/modules",
            json={"name": "越权套件模块", "key": f"m3b_module_{uuid4().hex[:8]}"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/modules/{uuid4()}", json={"version": 1}, headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/v1/document-templates/{uuid4()}/versions", headers=headers
        ).status_code
        == 403
    )
