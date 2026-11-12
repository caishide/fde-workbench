"""M8 红队爬扫：企业 A 账号全 API 爬扫企业 B 资源（GET 读面参数化）。

leader 任务书 :106-107 与 ADR-M3 §6 :44 定的最终兜底：用企业 A 账号逐条
爬扫企业 B 的读面，暴露盘点表外的疑似全局面。**本轮零生产代码改动**——
若某条读面坐实真实跨 org 越权，按 ADR-M3 :44 登记「待 M0 补充」＋
`xfail(strict=True)` 待销号，另开轮修，不得顺手改生产代码、不得据此申报
「安全专项零高危」。

设计要点（对齐 team-lead 实施规格）：

- ``ROUTES`` 30 条 GET 读面，从 ``multi_tenant_harness`` 4 工厂造的 B 企业
  资源 ID 逐条拼出具体路径；企业 A token 打过去须 ``403/404``（或 200 但
  载荷不含 B 标识）。
- **双阳性对照**：B 属主 token 同路径须 ``200``（防「全 404」假绿）；
  A 企业内与 B 属主**同角色**的账号仍须 ``403/404``（排除「403 其实由
  角色差异产生」的假绿）。两条都过才算 org 维度真收敛。
- **完整性钉**：候选面由 ``create_app().url_map`` 动态派生（支持 GET＋
  路径含模板变量），``candidate - accounted == set()`` 保证「未登记即红」、
  ``accounted - candidate == set()`` 保证登记不陈旧；**绝不写死 480**、
  **绝不引用 ``docs/audit/v3-route-inventory.csv`` 作集合**（在途 PR 会
  改清单，且清单列是 AST 富化产物，CI 只钉 (method,path)）。
- 排除面逐条登记理由：阳性对照不可行／admin-only 平台面／公开匿名面／
  内部服务间面／角色面／本轮抽样上限。

覆盖面＝「测试判别力面」：本文件只证明用例在检验跨企业性，不跨面支撑
git 泄漏面或运行时日志·事件·审计面结论。
"""
from __future__ import annotations

from uuid import uuid4

import pytest

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


def _auth(user, settings):
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _actual_routes(app):
    """(method, path) 集合——口径同 test_route_inventory_sync.py:25。"""
    actual = set()
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        methods = sorted(m for m in (rule.methods or []) if m not in {"HEAD", "OPTIONS"})
        actual.add(("|".join(methods), rule.rule))
    return actual


def _candidate_get_var_routes(app):
    """候选面＝url_map 里「支持 GET 且路径含模板变量」的全部路由（动态现测）。"""
    return {
        (method, path)
        for (method, path) in _actual_routes(app)
        if "GET" in method.split("|") and "<" in path
    }


# 本轮实际爬扫的 30 条高风险企业资源读面：key 为 (method, Flask rule)，
# value 为「用 B 企业资源 ID 拼出具体路径」的构造器。
ROUTES = {
    ("GET", "/api/v1/agents/runs/<run_id>"): lambda w: f"/api/v1/agents/runs/{w['run'].id}",
    ("GET", "/api/v1/agents/runs/<run_id>/tool-calls"): lambda w: f"/api/v1/agents/runs/{w['run'].id}/tool-calls",
    ("GET", "/api/v1/ai/chat/conversations/<conversation_id>"): lambda w: f"/api/v1/ai/chat/conversations/{w['conversation'].id}",
    ("GET", "/api/v1/commercial/certification-records/<user_id>"): lambda w: f"/api/v1/commercial/certification-records/{w['user_b'].id}",
    ("GET", "/api/v1/commercial/entitlements/<user_id>"): lambda w: f"/api/v1/commercial/entitlements/{w['user_b'].id}",
    ("GET", "/api/v1/commercial/orgs/<org_id>/invitations"): lambda w: f"/api/v1/commercial/orgs/{w['org_b'].id}/invitations",
    ("GET", "/api/v1/commercial/role-assignments/<user_id>"): lambda w: f"/api/v1/commercial/role-assignments/{w['user_b'].id}",
    ("GET", "/api/v1/projects/<project_id>"): lambda w: f"/api/v1/projects/{w['project_b'].id}",
    ("GET", "/api/v1/projects/<project_id>/business-facts"): lambda w: f"/api/v1/projects/{w['project_b'].id}/business-facts",
    ("GET", "/api/v1/projects/<project_id>/contracts"): lambda w: f"/api/v1/projects/{w['project_b'].id}/contracts",
    ("GET", "/api/v1/projects/<project_id>/delivery-plans"): lambda w: f"/api/v1/projects/{w['project_b'].id}/delivery-plans",
    ("GET", "/api/v1/projects/<project_id>/discovery/extractions"): lambda w: f"/api/v1/projects/{w['project_b'].id}/discovery/extractions",
    ("GET", "/api/v1/projects/<project_id>/documents"): lambda w: f"/api/v1/projects/{w['project_b'].id}/documents",
    ("GET", "/api/v1/projects/<project_id>/documents/delivery-records"): lambda w: f"/api/v1/projects/{w['project_b'].id}/documents/delivery-records",
    ("GET", "/api/v1/projects/<project_id>/evidence"): lambda w: f"/api/v1/projects/{w['project_b'].id}/evidence",
    ("GET", "/api/v1/projects/<project_id>/execution-facts"): lambda w: f"/api/v1/projects/{w['project_b'].id}/execution-facts",
    ("GET", "/api/v1/projects/<project_id>/files"): lambda w: f"/api/v1/projects/{w['project_b'].id}/files",
    ("GET", "/api/v1/projects/<project_id>/gantt"): lambda w: f"/api/v1/projects/{w['project_b'].id}/gantt",
    ("GET", "/api/v1/projects/<project_id>/gates"): lambda w: f"/api/v1/projects/{w['project_b'].id}/gates",
    ("GET", "/api/v1/projects/<project_id>/guidance"): lambda w: f"/api/v1/projects/{w['project_b'].id}/guidance",
    ("GET", "/api/v1/projects/<project_id>/guidance-analyses"): lambda w: f"/api/v1/projects/{w['project_b'].id}/guidance-analyses",
    ("GET", "/api/v1/projects/<project_id>/members"): lambda w: f"/api/v1/projects/{w['project_b'].id}/members",
    ("GET", "/api/v1/projects/<project_id>/ontology/candidates"): lambda w: f"/api/v1/projects/{w['project_b'].id}/ontology/candidates",
    ("GET", "/api/v1/projects/<project_id>/ontology/change-sets"): lambda w: f"/api/v1/projects/{w['project_b'].id}/ontology/change-sets",
    ("GET", "/api/v1/projects/<project_id>/ontology/relation-types"): lambda w: f"/api/v1/projects/{w['project_b'].id}/ontology/relation-types",
    ("GET", "/api/v1/projects/<project_id>/ontology/terms"): lambda w: f"/api/v1/projects/{w['project_b'].id}/ontology/terms",
    ("GET", "/api/v1/projects/<project_id>/payments"): lambda w: f"/api/v1/projects/{w['project_b'].id}/payments",
    ("GET", "/api/v1/projects/<project_id>/quotes"): lambda w: f"/api/v1/projects/{w['project_b'].id}/quotes",
    ("GET", "/api/v1/projects/<project_id>/requirements"): lambda w: f"/api/v1/projects/{w['project_b'].id}/requirements",
    ("GET", "/api/v1/projects/<project_id>/research/exports/<export_id>"): lambda w: f"/api/v1/projects/{w['project_b'].id}/research/exports/{w['export'].id}",
}

# 候选面中未纳入本轮爬扫的 71 条，逐条登记理由（「未登记即红」的另一半）。
# 理由分类均来自 D:/test/fde-wt-m8 基线 d092c2e 的 A/B/同角色 A 三状态码实测。
_EXCLUDED_WITH_REASON = {
    ("GET", "/api/v1/admin/commercial/orgs/<org_id>/ai-budget"): "admin-only 平台面（B 属主亦 403）：M6 已证 admin 全量可见是平台能力非漏洞",
    ("GET", "/api/v1/ai/chat/messages/<turn_id>/progress"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/ai/executions/<execution_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/ai/lcsc-runs/<run_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/commercial/enterprise-quota/<subject_key>"): "阳性对照不可行：B 属主亦 400（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/commercial/enterprise-spaces/<subject_key>"): "阳性对照不可行：B 属主亦 400（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/commercial/opportunities/<opportunity_id>"): "阳性对照不可行：B 属主亦 404（商机需企业确认前置状态，全 404 假绿风险）",
    ("GET", "/api/v1/commercial/regional-partners/<partner_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/commercial/revenue-ledger/<entry_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/delivery-plans/<plan_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/diagnostics/leads/claims/<claim_id>"): "公开获客诊断匿名认领面，非企业资源读面；B 属主亦 404",
    ("GET", "/api/v1/diagnostics/share/<share_token>"): "公开分享只读面，非企业资源读面；B 属主亦 404",
    ("GET", "/api/v1/discovery/extractions/<extraction_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/dispatch/packages/<package_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/dispatch/packages/<package_id>/offers"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/document-templates/<version_id>/download-url"): "admin-only 平台面（A/B 均 403），非企业资源读面",
    ("GET", "/api/v1/extensions/plugins/<plugin_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/extensions/skills/<skill_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/extensions/skills/<skill_id>/versions"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/handover-packages/<package_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/industry-templates/<template_id>/versions"): "角色面而非 org 隔离面：同角色 A 账号即 200（403 由角色差异产生，非跨企业收敛）",
    ("GET", "/api/v1/industry-templates/versions/<version_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/internal/dsh/approvals/<approval_id>"): "内部 DSH 服务间面（A/B 均 401，静态令牌服务间面），非企业 token 读面",
    ("GET", "/api/v1/internal/dsh/executions/<run_id>/knowledge"): "内部 DSH 服务间面（A/B 均 401，静态令牌服务间面），非企业 token 读面",
    ("GET", "/api/v1/interview-minutes/<minutes_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/meeting-templates/<template_id>/checklist"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/meetings/<meeting_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/meetings/<meeting_id>/cost"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/meetings/<meeting_id>/minutes"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/projects/<project_id>/documents/<document_id>"): "阳性对照不可行：B 属主亦 404（需先建文档），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/documents/<document_id>/versions"): "阳性对照不可行：B 属主亦 404（需先建文档），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/documents/<version_id>/download-url"): "阳性对照不可行：B 属主亦 404（需先建文档版本），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/documents/<version_id>/preview-url"): "阳性对照不可行：B 属主亦 404（需先建文档版本），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/files/<version_id>/download-url"): "阳性对照不可行：B 属主亦 404（需先建文件版本），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/files/<version_id>/preview-url"): "阳性对照不可行：B 属主亦 404（需先建文件版本），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/files/items/<file_id>/versions"): "阳性对照不可行：B 属主亦 404（需先建文件），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/guidance-analyses/<analysis_id>"): "阳性对照不可行：B 属主亦 404（需先建分析记录），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/ontology/change-sets/<change_set_id>"): "阳性对照不可行：B 属主亦 404（需先建变更集），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/ontology/terms/<term_id>/impact"): "阳性对照不可行：B 属主亦 404（需先建术语），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/presurvey-intake"): "本轮抽样面上限 30 条；已实测 A/同角色 A ∈ {403,404} 且 B=200，留待后续轮扩面",
    ("GET", "/api/v1/projects/<project_id>/quotes/<quote_key>/draft"): "阳性对照不可行：B 属主亦 404（需先建报价草稿），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/research/forms"): "阳性对照不可行：B 属主亦 409（需模板绑定前置状态），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/research/forms/<form_id>"): "阳性对照不可行：B 属主亦 409（需模板绑定前置状态），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/research/subjects"): "本轮抽样面上限 30 条；已实测 A/同角色 A ∈ {403,404} 且 B=200，留待后续轮扩面",
    ("GET", "/api/v1/projects/<project_id>/research/subjects/<subject_id>/memo"): "阳性对照不可行：B 属主亦 400（需 memo 前置状态），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/research/subjects/<subject_id>/personal-memos"): "阳性对照不可行：B 属主亦 400（需 memo 前置状态），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/solutions"): "本轮抽样面上限 30 条；已实测 A/同角色 A ∈ {403,404} 且 B=200，留待后续轮扩面",
    ("GET", "/api/v1/projects/<project_id>/solutions/<solution_id>"): "阳性对照不可行：B 属主亦 404（需先建方案），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/solutions/<solution_id>/health"): "阳性对照不可行：B 属主亦 404（需先建方案），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/solutions/<solution_id>/review-trail"): "阳性对照不可行：B 属主亦 404（需先建方案），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/tasks"): "本轮抽样面上限 30 条；已实测 A/同角色 A ∈ {403,404} 且 B=200，留待后续轮扩面",
    ("GET", "/api/v1/projects/<project_id>/tasks/<task_id>"): "阳性对照不可行：B 属主亦 404（需先建任务），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/test-plans"): "本轮抽样面上限 30 条；已实测 A/同角色 A ∈ {403,404} 且 B=200，留待后续轮扩面",
    ("GET", "/api/v1/projects/<project_id>/workflow-runs"): "本轮抽样面上限 30 条；已实测 A/同角色 A ∈ {403,404} 且 B=200，留待后续轮扩面",
    ("GET", "/api/v1/projects/<project_id>/workflow-runs/<run_id>"): "阳性对照不可行：B 属主亦 404（需先建工作流运行），全 404 假绿风险",
    ("GET", "/api/v1/projects/<project_id>/workflows"): "本轮抽样面上限 30 条；已实测 A/同角色 A ∈ {403,404} 且 B=200，留待后续轮扩面",
    ("GET", "/api/v1/simulation/proposals/<proposal_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/simulation/regression/results/<result_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/simulation/regression/suites/<suite_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/simulation/runs/<run_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/simulation/runs/<run_id>/evaluation"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/simulation/runs/<run_id>/trace"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/simulation/scenarios/<scenario_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/simulation/scenarios/<scenario_id>/versions"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/skills/<skill_id>/document"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/templates/<template_id>/versions/<version_id>/research-forms"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/test-executions/<execution_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/test-plans/<plan_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/transcript-drafts/<draft_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/translator/translations/<translation_id>"): "阳性对照不可行：B 属主亦 404（全 404 假绿风险），本轮夹具无该资源前置状态",
    ("GET", "/api/v1/users/<user_id>/ai-access"): "admin-only 平台面（A/B 均 403，用户 AI 授权查询），非企业资源读面",
}


def _b_markers(world):
    """B 企业标识（用于「200 但不得泄漏」的兜底断言）。"""
    return [
        str(world["project_b"].id),
        str(world["project_b"].project_code),
        str(world["org_b"].id),
        str(world["user_b"].id),
    ]


@pytest.fixture
def m8_world(db_session):
    """跨企业世界：两个企业 org、A 企业两账号（含与 B 属主同角色者）、
    B 企业属主与项目，以及挂在该项目上的 B 企业资源（导出/AI run/对话/
    待确认 API-action）。所有工厂均自带 ``db_session.commit()``——HTTP
    路由面测试若漏 commit，请求侧连接看不到数据，会退化成「列表空集」假绿。
    """
    org_a = make_enterprise_org(db_session)
    org_b = make_enterprise_org(db_session)
    user_a = make_user(db_session, "fde_engineer", org_id=org_a.id)
    user_a_lead = make_user(db_session, "project_lead", org_id=org_a.id)
    user_b = make_user(db_session, "project_lead", org_id=org_b.id)
    project_b = make_project(
        db_session, user_b, code=f"M8{uuid4().hex[:8]}", org_id=org_b.id
    )
    # 跨企业成员关系＝判别力关键场景：成员关系本身挡不住 org 维度。
    add_member(db_session, project_b, user_a)
    add_member(db_session, project_b, user_a_lead)

    subject = ProjectResearchSubject(
        project_id=project_b.id,
        subject_type="company",
        subject_key=f"subject-{uuid4().hex[:8]}",
        name="M8 隔离用例调研对象",
    )
    db_session.add(subject)
    db_session.flush()
    form = ProjectResearchForm(
        project_id=project_b.id,
        subject_id=subject.id,
        form_key=f"form-{uuid4().hex[:8]}",
        name="M8 隔离用例调研表",
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
        name="M8 隔离用例智能体",
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
        context_ref="masked://m8-isolation-case",
        idempotency_key=f"m8-{uuid4().hex}",
    )
    db_session.add(run)

    conversation = AIConversation(
        user_id=user_b.id,
        title="M8 隔离用例会话",
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
                "description": "M8 隔离用例待确认操作",
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
        "user_a_lead": user_a_lead,
        "user_b": user_b,
        "project_b": project_b,
        "export": export,
        "run": run,
        "conversation": conversation,
        "action_id": action_id,
    }


@pytest.mark.parametrize("route", sorted(ROUTES), ids=lambda r: r[1])
def test_m8_cross_enterprise_a_token_cannot_read_b_resource(
    client, db_session, settings, m8_world, route
):
    """企业 A token 打企业 B 资源 ⇒ 403/404（或 200 但载荷不含 B 标识）。"""
    path = ROUTES[route](m8_world)

    blocked = client.get(path, headers=_auth(m8_world["user_a"], settings))
    assert blocked.status_code in (403, 404), (
        path,
        blocked.status_code,
        blocked.get_data(as_text=True)[:200],
    )
    # 「或载荷不含 B 标识」这一形态由下列两个 200 列表面用例承载；参数化爬扫面
    # 用严格 403/404，使身份/夹具取值的摘除式变异能确定性地转红（判别力自证）。
    assert all(
        marker not in blocked.get_data(as_text=True) for marker in _b_markers(m8_world)
    ), (path, "拒绝响应体泄漏 B 企业标识")

    # 同角色控制：A 企业账号即使与 B 属主同为 project_lead，仍须被 org 收敛，
    # 排除「403 其实由角色差异产生」的假绿。
    same_role = client.get(path, headers=_auth(m8_world["user_a_lead"], settings))
    assert same_role.status_code in (403, 404), (path, same_role.status_code)

    # 阳性对照：B 属主 token 同路径须 200，防「全 404」假绿
    #（先例 test_m3b_batch3_project_service.py:262-288）。
    allowed = client.get(path, headers=_auth(m8_world["user_b"], settings))
    assert allowed.status_code == 200, (
        path,
        allowed.status_code,
        allowed.get_data(as_text=True)[:200],
    )


def test_m8_sweep_surface_covers_every_candidate_get_read_face(app):
    """完整性钉：候选面 ≡ ROUTES ∪ 排除登记；未登记即红、陈旧登记即红。"""
    candidate = _candidate_get_var_routes(app)
    accounted = set(ROUTES) | set(_EXCLUDED_WITH_REASON)
    assert candidate - accounted == set(), (
        "发现未登记的 GET 读面（须纳入 ROUTES 或补排除理由）：",
        sorted(candidate - accounted),
    )
    assert accounted - candidate == set(), (
        "登记面已陈旧（url_map 中不再存在）：",
        sorted(accounted - candidate),
    )
    assert all(reason.strip() for reason in _EXCLUDED_WITH_REASON.values()), (
        "排除登记必须逐条给出非空理由"
    )


def test_m8_swept_routes_are_real_get_rules(app):
    """ROUTES 必须是 create_app().url_map 里真实存在的 GET 规则（防 stale）。"""
    actual = _actual_routes(app)
    assert set(ROUTES) <= actual, (
        "ROUTES 含不存在的路由：",
        sorted(set(ROUTES) - actual),
    )
    assert all(method == "GET" for method, _ in ROUTES)


def test_m8_route_builders_fully_substitute_template_variables(m8_world):
    """每条 ROUTES 的构造器必须把模板变量全部换成真实 B 资源 ID。"""
    for route, build in ROUTES.items():
        path = build(m8_world)
        assert "<" not in path and ">" not in path, (route, path)
        assert path.startswith("/api/v1/"), (route, path)


def test_m8_routes_and_exclusions_are_disjoint():
    """同一条路由不得既被爬扫又被排除（防止悄悄撤掉一条读面）。"""
    assert set(ROUTES).isdisjoint(_EXCLUDED_WITH_REASON)


def test_m8_a_project_list_never_contains_b_project_id(client, db_session, settings, m8_world):
    """200 列表面：A 企业账号的项目列表不得出现 B 企业项目标识。"""
    owner = client.get("/api/v1/projects", headers=_auth(m8_world["user_b"], settings))
    assert owner.status_code == 200
    assert m8_world["project_b"].id in {
        row["id"] for row in owner.get_json()["data"]["items"]
    }

    response = client.get("/api/v1/projects", headers=_auth(m8_world["user_a"], settings))
    assert response.status_code == 200
    items = response.get_json()["data"]["items"]
    assert m8_world["project_b"].id not in {row["id"] for row in items}


def test_m8_a_pending_actions_never_contains_b_action(client, db_session, settings, m8_world):
    """200 列表面：A 企业账号的待确认 API-action 清单不得出现 B 企业操作。"""
    owner = client.get("/api/v1/ai/actions", headers=_auth(m8_world["user_b"], settings))
    assert owner.status_code == 200
    assert m8_world["action_id"] in {
        row["id"] for row in owner.get_json()["data"]["items"]
    }

    response = client.get("/api/v1/ai/actions", headers=_auth(m8_world["user_a"], settings))
    assert response.status_code == 200
    identifiers = {row["id"] for row in response.get_json()["data"]["items"]}
    assert m8_world["action_id"] not in identifiers
