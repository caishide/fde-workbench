"""AI 原生化 N3b 本体轮（G-03）：DAG AI 起草——返件式草稿零落库（ADR v1 §3）。

验收面（ADR §6 实施清单 + G-03 消解判据复测动作）：
- ①AI 起草入口走 ``execute_ai_prompt`` 单一入口（模块级打桩；J-1 白名单
  WORKFLOW_DAG_DRAFT_SYSTEM_PROMPT 钉见 test_prompt_entrypoint_gate 与
  test_dual_source_regression_and_j1_pin）；
- ②**返件式零落库**（ADR 拍板二）：响应只带草稿＋validate 干跑明细＋sha；
  成功路径 WorkflowDefinition/Version **零行**（事件＝审计面）；契约失败零写入；
- ③**闭集不扩展**（ADR 拍板一）：四值 type 外拒绝；节点字段白名单外拒绝；
  契约推荐项 ≥1 human_approval；
- ④**全尺同闸**：AI 预检复用 validate_dag_against_registry（未发布技能引用
  在 AI 侧即拒）；三道干跑＋两道人工闸端到端（G-03 复测动作＝完整链演示）；
- ⑤前置闸在 AI 调用前（零烧费）：方案 approved/published、技能白名单、
  capability 白名单——闸码与编译器同码；
- ⑥确定性归一：拓扑序重排＋plan_ref 服务端注入＋dag_sha256 可重算；
- ⑦双来源回归钉：compile_plan_workflow/draft-from-plan 缺省腿零改动。
"""
from __future__ import annotations

import json

from test_agents_d4_harness import ApiClient, api_client, issue_access_token, make_user
from test_agents_d4_harness import d4_app, d4_client, d4_settings  # noqa: F401  (pytest fixture)
from test_delivery_plans import _generate, _leader_project, _seed_requirements
from test_discovery_extraction import _DICT_NAME
from test_workflow_templates import _publish_seed_skills

from fde_api.workbench.models import OperationEvent, ProjectMember
from fde_api.workflows import draft_ai as workflow_draft
from fde_api.workflows.definition_service import dag_sha256
from fde_api.workflows.models import WorkflowDefinition, WorkflowDefinitionVersion


def _approved_plan(db_session, leader, project) -> dict:
    """确定性生成方案→人工 approved→published（AI 腿输入域前置态）。"""
    _seed_requirements(db_session, project, leader.user, 1)
    plan = _generate(db_session, leader, project)
    plan_id = plan["id"]
    assert leader.patch(
        f"/api/v1/delivery-plans/{plan_id}/review", json={"decision": "approved"}
    ).status_code == 200
    assert leader.post(f"/api/v1/delivery-plans/{plan_id}/publish").status_code == 200
    db_session.expire_all()
    return plan


def _ai_nodes() -> list[dict]:
    """与编译器三节点形同构的合法草稿（**故意逆拓扑序**返回——钉确定性重排）。"""
    return [
        {"key": "acceptance_review", "type": "human_approval", "depends_on": ["implement"],
         "capability": "workbench.write", "expires_minutes": 1440},
        {"key": "plan_review", "type": "human_approval", "depends_on": [],
         "capability": "workbench.write", "expires_minutes": 60},
        {"key": "implement", "type": "skill", "ref": "research-brief@1", "depends_on": ["plan_review"],
         "output": "implementation_brief", "max_retries": 1, "timeout_seconds": 3600,
         "failure_class": "retryable", "params": {"objective": "按交付方案实施部署"}},
    ]


def _patch_ai(outputs: list, calls: list):
    """把 workflows.draft.execute_ai_prompt 换成固定输出序列（N3a 同法，末项粘性）。"""
    state = {"i": 0}

    def _fake_execute(**kwargs):
        calls.append(kwargs)
        index = min(state["i"], len(outputs) - 1)
        state["i"] += 1
        item = outputs[index]
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict):
            item = json.dumps(item, ensure_ascii=False)
        return {"text": item, "model": {"provider": "test", "name": "test-model"}, "provider_usage": {}}

    original = workflow_draft.execute_ai_prompt
    workflow_draft.execute_ai_prompt = _fake_execute
    return original


def _unpatch_ai(original) -> None:
    workflow_draft.execute_ai_prompt = original


def _setup(db_session, d4_client, d4_settings, tag: str):
    """领队＋项目＋published 技能＋approved/published 方案（返回 leader/project/plan_id）。"""
    leader, project = _leader_project(db_session, d4_client, d4_settings, tag)
    _publish_seed_skills(db_session, leader.user)
    plan = _approved_plan(db_session, leader, project)
    return leader, project, plan["id"]


def _zero_definitions(db_session, project_id) -> bool:
    return (
        db_session.query(WorkflowDefinition).filter_by(project_id=project_id).count() == 0
        and db_session.query(WorkflowDefinitionVersion).count() == 0
    )


# ---------------------------------------------------------------------------
# 成功路径：返件式草稿（零落库）＋确定性归一＋溯源


def test_ai_dag_draft_happy_path_zero_db(db_session, d4_client, d4_settings) -> None:
    leader, project, plan_id = _setup(db_session, d4_client, d4_settings, "N3BW-1")
    outputs = [{"nodes": _ai_nodes()}]
    calls: list = []
    original = _patch_ai(outputs, calls)
    try:
        response = leader.post(
            f"/api/v1/projects/{project.id}/workflows/generate-ai-draft",
            json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
        )
    finally:
        _unpatch_ai(original)
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    draft = data["draft"]

    # 返件式形状（ADR §3 响应形状）
    assert set(draft) == {"dag_json", "validate", "dag_sha256", "plan_ref", "implementation_skill_ref"}
    assert draft["plan_ref"] == plan_id
    assert draft["implementation_skill_ref"] == "research-brief@1"
    assert data["prompt_version"] == workflow_draft.WORKFLOW_DAG_PROMPT_VERSION
    assert data["model"] == "test-model"

    # ⑥确定性归一：拓扑序重排＋plan_ref 服务端注入＋sha 可重算
    keys = [node["key"] for node in draft["dag_json"]["nodes"]]
    assert keys == ["plan_review", "implement", "acceptance_review"], "按 validate_dag 确定性拓扑序重排"
    assert all(node["plan_ref"] == plan_id for node in draft["dag_json"]["nodes"]), "plan_ref 服务端注入"
    assert draft["dag_sha256"] == dag_sha256(draft["dag_json"]), "dag_sha256 可重算"
    assert draft["validate"]["valid"] is True
    assert draft["validate"]["order"] == keys

    # ②返件式零落库：业务域零行（事件＝审计面照常留痕）
    assert _zero_definitions(db_session, project.id), "业务域表零写入（返件式草稿）"
    event = db_session.query(OperationEvent).filter_by(
        target_type="project", target_id=project.id, event_type="workflow_dag_ai_drafted"
    ).one()
    changes = event.changes
    assert changes["purpose"] == "workflow_dag_draft"
    assert changes["prompt_version"] == workflow_draft.WORKFLOW_DAG_PROMPT_VERSION
    assert changes["model"] == "test-model"
    assert changes["dag_sha256"] == draft["dag_sha256"]
    assert changes["node_count"] == 3
    assert changes["plan_ref"] == plan_id
    assert "dag_json" not in changes and "nodes" not in changes, "事件不带 DAG 全文"

    # ①单一入口钉证：purpose/prompt_version/execution_id/use_tools（归因三元＋零工具）
    assert len(calls) == 1
    assert calls[0]["purpose"] == "workflow_dag_draft"
    assert calls[0]["prompt_version"] == workflow_draft.WORKFLOW_DAG_PROMPT_VERSION
    assert calls[0]["execution_id"].startswith("workflow-dag:")
    assert calls[0]["use_tools"] is False


# ---------------------------------------------------------------------------
# 契约闸（ADR 拍板一：闭集不扩展＋契约推荐项；全尺同闸）


def test_ai_dag_draft_requires_human_approval_node(db_session, d4_client, d4_settings) -> None:
    """契约推荐项（ADR §2）：无 human_approval 的全自动图 ⇒ 整批拒绝（重试一次）。"""
    leader, project, plan_id = _setup(db_session, d4_client, d4_settings, "N3BW-2")
    skill_only = [{"nodes": [
        {"key": "implement", "type": "skill", "ref": "research-brief@1", "depends_on": []},
    ]}]
    calls: list = []
    original = _patch_ai(skill_only, calls)
    try:
        response = leader.post(
            f"/api/v1/projects/{project.id}/workflows/generate-ai-draft",
            json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
        )
    finally:
        _unpatch_ai(original)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ai_draft_contract_failed"
    assert len(calls) == 2, "契约失败自动重试一次"
    assert _zero_definitions(db_session, project.id)
    assert db_session.query(OperationEvent).filter_by(event_type="workflow_dag_ai_drafted").count() == 0


def test_ai_dag_draft_rejects_closed_set_and_unknown_fields(db_session, d4_client, d4_settings) -> None:
    """闭集不扩展（ADR 拍板一）：四值 type 外拒绝；白名单字段外拒绝。"""
    leader, project, plan_id = _setup(db_session, d4_client, d4_settings, "N3BW-3")

    bad_type = {"nodes": _ai_nodes()}
    bad_type["nodes"][1]["type"] = "condition"  # 四值闭集外
    calls: list = []
    original = _patch_ai([bad_type], calls)
    try:
        response = leader.post(
            f"/api/v1/projects/{project.id}/workflows/generate-ai-draft",
            json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
        )
    finally:
        _unpatch_ai(original)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ai_draft_contract_failed"
    assert len(calls) == 2

    bad_field = {"nodes": _ai_nodes()}
    bad_field["nodes"][1]["compensation"] = {"action": "rollback"}  # 白名单字段外
    calls2: list = []
    original = _patch_ai([bad_field], calls2)
    try:
        response = leader.post(
            f"/api/v1/projects/{project.id}/workflows/generate-ai-draft",
            json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
        )
    finally:
        _unpatch_ai(original)
    assert response.status_code == 409
    assert _zero_definitions(db_session, project.id)


def test_ai_dag_draft_full_scale_registry_gate(db_session, d4_client, d4_settings) -> None:
    """全尺同闸：AI 形状合法但 registry 对账不过（未发布技能引用）⇒ 契约失败。

    证明 AI 预检**复用 validate_dag_against_registry**（与 create_definition 同尺，
    零第二套校验逻辑——ADR §5）。"""
    leader, project, plan_id = _setup(db_session, d4_client, d4_settings, "N3BW-4")
    bad_ref = {"nodes": _ai_nodes()}
    bad_ref["nodes"][2]["ref"] = "nosuch-skill@1"
    calls: list = []
    original = _patch_ai([bad_ref], calls)
    try:
        response = leader.post(
            f"/api/v1/projects/{project.id}/workflows/generate-ai-draft",
            json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
        )
    finally:
        _unpatch_ai(original)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ai_draft_contract_failed"
    assert len(calls) == 2
    assert _zero_definitions(db_session, project.id)


def test_ai_dag_draft_contract_failure_zero_write(db_session, d4_client, d4_settings) -> None:
    """畸形 JSON（重试后仍畸形）⇒ 409 ai_draft_contract_failed，业务域零写入。"""
    leader, project, plan_id = _setup(db_session, d4_client, d4_settings, "N3BW-5")
    calls: list = []
    original = _patch_ai(["{not json", "{also-bad"], calls)
    try:
        response = leader.post(
            f"/api/v1/projects/{project.id}/workflows/generate-ai-draft",
            json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
        )
    finally:
        _unpatch_ai(original)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ai_draft_contract_failed"
    assert len(calls) == 2
    assert _zero_definitions(db_session, project.id)
    assert db_session.query(OperationEvent).filter_by(event_type="workflow_dag_ai_drafted").count() == 0


# ---------------------------------------------------------------------------
# 前置闸（同编译器输入域，闸码同码；全部 AI 调用前——零烧费）＋权限


def test_ai_dag_draft_pre_gates_before_ai_call(db_session, d4_client, d4_settings) -> None:
    leader, project, plan_id = _setup(db_session, d4_client, d4_settings, "N3BW-6")

    def _fail_if_called(**kwargs):
        raise AssertionError("前置闸失败时不得发起 AI 调用（零烧费纪律）")

    url = f"/api/v1/projects/{project.id}/workflows/generate-ai-draft"
    original = workflow_draft.execute_ai_prompt
    workflow_draft.execute_ai_prompt = _fail_if_called
    try:
        # 草稿方案（未审阅）→ 409 plan_not_approved
        _seed_requirements(db_session, project, leader.user, 1)
        draft_plan = _generate(db_session, leader, project)
        denied = leader.post(url, json={"plan_id": draft_plan["id"], "implementation_skill_ref": "research-brief@1"})
        assert denied.status_code == 409
        assert denied.get_json()["error"]["code"] == "plan_not_approved"

        # 技能引用非 <key>@<版本号> 形 → 409 invalid_skill_ref
        bad = leader.post(url, json={"plan_id": plan_id, "implementation_skill_ref": "research-brief"})
        assert bad.status_code == 409
        assert bad.get_json()["error"]["code"] == "invalid_skill_ref"

        # 形合法但不在 published 白名单 → 422 skill_ref_not_published
        unpublished = leader.post(url, json={"plan_id": plan_id, "implementation_skill_ref": "nosuch-skill@1"})
        assert unpublished.status_code == 422
        assert unpublished.get_json()["error"]["code"] == "skill_ref_not_published"

        # capability 白名单外（system.* 不开放）→ 409 invalid_capability
        cap = leader.post(url, json={
            "plan_id": plan_id, "implementation_skill_ref": "research-brief@1",
            "approval_capability": "system.run",
        })
        assert cap.status_code == 409
        assert cap.get_json()["error"]["code"] == "invalid_capability"

        # member（非管理）⇒ 403；未认证 ⇒ 401
        member_user = make_user(db_session, "fde_engineer")
        db_session.add(ProjectMember(project_id=project.id, user_id=member_user.id, role="member"))
        db_session.commit()
        member = ApiClient(d4_client, member_user,
                           {"Authorization": f"Bearer {issue_access_token(member_user, d4_settings)}"})
        assert member.post(url, json={
            "plan_id": plan_id, "implementation_skill_ref": "research-brief@1",
        }).status_code == 403
        assert d4_client.post(url, json={"plan_id": plan_id}).status_code == 401
    finally:
        workflow_draft.execute_ai_prompt = original
    assert _zero_definitions(db_session, project.id)


# ---------------------------------------------------------------------------
# 输出端兜底脱敏 + 凭据 fail-closed（params/when 文本字段）


def test_ai_dag_draft_redaction_and_credential_fail_closed(db_session, d4_client, d4_settings) -> None:
    leader, project, plan_id = _setup(db_session, d4_client, d4_settings, "N3BW-7")

    # 词典命中（种子合成名，零真实资料）⇒ params 替换＋事件 redaction_entries
    tainted = {"nodes": _ai_nodes()}
    tainted["nodes"][2]["params"]["objective"] = f"与{_DICT_NAME}对齐交付方案"
    calls: list = []
    original = _patch_ai([tainted], calls)
    try:
        response = leader.post(
            f"/api/v1/projects/{project.id}/workflows/generate-ai-draft",
            json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
        )
    finally:
        _unpatch_ai(original)
    assert response.status_code == 200, response.get_json()
    draft = response.get_json()["data"]["draft"]
    params = draft["dag_json"]["nodes"][1]["params"]
    assert _DICT_NAME not in params["objective"], "输出端兜底脱敏必须替换词典命中名"
    event = db_session.query(OperationEvent).filter_by(
        target_type="project", target_id=project.id, event_type="workflow_dag_ai_drafted"
    ).one()
    assert event.changes["redaction_entries"], "脱敏替换留痕进事件（审计面）"

    # 凭据串命中 ⇒ 422 整批拒绝＋零写入（fail-closed：凭据不进任何响应/事件）
    cred = {"nodes": _ai_nodes()}
    cred["nodes"][2]["params"]["objective"] = "部署时使用密钥: abcdefghijkl1234"
    original = _patch_ai([cred], [])
    try:
        denied = leader.post(
            f"/api/v1/projects/{project.id}/workflows/generate-ai-draft",
            json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
        )
    finally:
        _unpatch_ai(original)
    assert denied.status_code == 422
    assert denied.get_json()["error"]["code"] == "sensitive_credential_detected"
    assert db_session.query(OperationEvent).filter_by(
        target_type="project", target_id=project.id, event_type="workflow_dag_ai_drafted"
    ).count() == 1, "拒绝路径零新增事件"


# ---------------------------------------------------------------------------
# ⑦双来源回归钉（缺省腿零改动）＋ J-1 白名单钉


def test_dual_source_regression_and_j1_pin(db_session, d4_client, d4_settings) -> None:
    """draft-from-plan 缺省腿零回归（确定性编译器输出不变）；两个新提示词常量
    进 J-1 白名单；新路由不进 api_catalog。"""
    leader, project, plan_id = _setup(db_session, d4_client, d4_settings, "N3BW-8")

    # 缺省腿：确定性 draft-from-plan 照常 201＋三节点形（ADR 拍板三承重墙）
    created = leader.post(
        f"/api/v1/projects/{project.id}/workflows/draft-from-plan",
        json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
    )
    assert created.status_code == 201, created.get_json()
    keys = [node["key"] for node in created.get_json()["data"]["definition"]["dag_json"]["nodes"]]
    assert keys == ["plan_review", "implement", "acceptance_review"]

    # 纯函数金形钉：compile_plan_workflow 三节点形状零漂移（缺省腿语义未动）
    from fde_api.workflows.compiler import compile_plan_workflow

    compiled = compile_plan_workflow(
        {"id": plan_id, "title": "交付方案 v1", "status": "published", "version": 1, "items": []},
        implementation_skill_ref="research-brief@1",
    )
    assert [node["key"] for node in compiled["workflow_draft"]["dag_json"]["nodes"]] == [
        "plan_review", "implement", "acceptance_review",
    ]

    # J-1 白名单：两个新提示词常量已登记（外部文字禁入契约 §2 表）
    from test_prompt_entrypoint_gate import _ALLOWED_PROMPT_CONSTANTS

    assert "WORKFLOW_DAG_DRAFT_SYSTEM_PROMPT" in _ALLOWED_PROMPT_CONSTANTS
    assert "DELIVERY_PLAN_DRAFT_SYSTEM_PROMPT" in _ALLOWED_PROMPT_CONSTANTS


# ---------------------------------------------------------------------------
# G-03 复测动作：HTTP 层端到端演示完整链
# （AI 起草草稿 → validate 干跑 → 人工 create_definition → publish，发布走人工通道）


def test_g03_end_to_end_chain_ai_draft_to_human_publish(db_session, d4_client, d4_settings) -> None:
    leader, project, plan_id = _setup(db_session, d4_client, d4_settings, "N3BW-9")
    outputs = [{"nodes": _ai_nodes()}]
    original = _patch_ai(outputs, [])
    try:
        drafted = leader.post(
            f"/api/v1/projects/{project.id}/workflows/generate-ai-draft",
            json={"plan_id": plan_id, "implementation_skill_ref": "research-brief@1"},
        )
    finally:
        _unpatch_ai(original)
    assert drafted.status_code == 200, drafted.get_json()
    draft = drafted.get_json()["data"]["draft"]

    # 第二道干跑＋第一道人工闸：人工持草稿走既有 create_definition（can_manage）
    created = leader.post(
        f"/api/v1/projects/{project.id}/workflows",
        json={"name": "AI 起草采纳定义", "dag": draft["dag_json"]},
    )
    assert created.status_code == 201, created.get_json()
    definition = created.get_json()["data"]["definition"]
    assert definition["status"] == "draft"
    assert definition["content_sha256"] == draft["dag_sha256"], "人工采纳的图与 AI 草稿逐位一致"

    # validate 干跑端点（同一 API 面复验）
    validated = leader.post(f"/api/v1/projects/{project.id}/workflows/{definition['id']}/validate")
    assert validated.status_code == 200
    assert validated.get_json()["data"]["valid"] is True

    # 第三道复验＋第二道人工闸：publish admin-only（D-2 维持——AI 无旁路）
    leader_publish = leader.post(f"/api/v1/projects/{project.id}/workflows/{definition['id']}/publish")
    assert leader_publish.status_code == 403, "发布 admin-only（leader 不可发布）"
    admin_user = make_user(db_session, "admin")
    admin = ApiClient(d4_client, admin_user,
                      {"Authorization": f"Bearer {issue_access_token(admin_user, d4_settings)}"})
    published = admin.post(f"/api/v1/projects/{project.id}/workflows/{definition['id']}/publish")
    assert published.status_code == 200, published.get_json()
    assert published.get_json()["data"]["definition"]["status"] == "published"
    assert published.get_json()["data"]["content_sha256"] == draft["dag_sha256"]

    # 完整链留痕：AI 起草事件＋人工 create/publish 事件并存（谁采纳谁署名）
    assert db_session.query(OperationEvent).filter_by(
        target_type="project", target_id=project.id, event_type="workflow_dag_ai_drafted"
    ).count() == 1
    assert db_session.query(OperationEvent).filter_by(
        target_type="workflow_definition", target_id=definition["id"],
        event_type="workflow_definition_created",
    ).count() == 1
