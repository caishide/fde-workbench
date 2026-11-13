"""产物采纳为方案（goal-crj 采纳流反向入口；人工动作语义）。

验收面（与族内 adopt/confirm 先例同尺）：
- **人工触发**：无自动采纳路径（本模块只被显式 POST 路由调用）；
- **幂等**：同产物重复采纳 ⇒ 返回既有方案（duplicate=True），不重复建方案/
  不重复落事件；
- **一 run 一方案**：同 run 已有产物被采纳 ⇒ 409（先归档既有方案）；
- **终态闸**：run 未到终态 ⇒ 409（半成品不进方案台账）；
- **权限同尺**：can_manage 才可采纳（与产物复核动作同尺）；
- **溯源列族**：新建方案 generated_by='agent' ＋ agent_run_id ＋
  source_json.kind='adopted_artifact'；产物回写 linked_solution_id；
- **红线 §6.6**：方案只存**指针**（storage_ref＋sha256），原件永不进库。
"""
from __future__ import annotations

import hashlib
from datetime import date
from uuid import uuid4

import pytest

from fde_api.agents.models import AgentArtifact, AgentRun
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.solutions.models import ProjectSolution
from fde_api.workbench.models import OperationEvent, Project, ProjectMember

from conftest import INITIAL_PASSWORD
from test_agents_d4_harness import seed_agent


def _user(username: str, role: str = "admin") -> User:
    return User(
        username=f"{username}.{uuid4().hex[:8]}",
        display_name=username,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )


def _headers(settings, user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user, settings)}"}


def _seed_bundle(db_session, settings, *, status: str = "completed", run_status: str = "completed"):
    """admin + viewer + 项目 + run（终态可配） + 产物行（未采纳）。"""
    admin = _user("crj.adopt.admin")
    viewer = _user("crj.adopt.viewer", role="viewer")
    project = Project(
        project_code=f"CRJ-{uuid4().hex[:6].upper()}",
        name="采纳流项目",
        enterprise_code="crj 客户·制造·苏州",
        business_line="FDE_DISPATCH",
        planned_start_date=date(2026, 10, 31),
        leader_user_id=admin.id,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([admin, viewer, project])
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=viewer.id, role="viewer"))
    agent = seed_agent(db_session, settings, name="crj 采纳智能体", credential_ref=f"zcode-{uuid4().hex[:8]}")
    run = AgentRun(
        project_id=project.id,
        agent_id=agent.id,
        initiated_by_user_id=admin.id,
        capability_used="agent.plan.generate",
        status=run_status,
        context_ref="ctx",
        idempotency_key=f"{uuid4().hex}:fp",
    )
    db_session.add(run)
    db_session.flush()
    artifact = AgentArtifact(
        run_id=run.id,
        kind="doc",
        storage_ref=f"host:{run.id}/output/report.md",
        sha256=hashlib.sha256("# 报告".encode("utf-8")).hexdigest(),
        reviewed=False,
        linked_solution_id=None,
    )
    db_session.add(artifact)
    db_session.commit()
    return admin, viewer, project, run, artifact


def _post(env, user, run, artifact, body=None):
    return env["client"].post(
        f"/api/v1/agents/runs/{run.id}/artifacts/{artifact.id}/adopt-solution",
        headers=_headers(env["settings"], user),
        json=body if body is not None else {},
    )


def test_adopt_creates_solution_with_provenance(client, db_session, settings):
    """主路径：产物采纳 ⇒ 新建 draft 方案＋溯源列族＋产物回链＋事件。"""
    admin, _viewer, project, run, artifact = _seed_bundle(db_session, settings)
    response = _post({"client": client, "settings": settings}, admin, run, artifact)
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["adopted"] is True and data["duplicate"] is False
    solution_id = data["solution_id"]
    solution = db_session.get(ProjectSolution, solution_id)
    assert solution is not None
    # 溯源列族（E3/V9/V11）
    assert solution.generated_by == "agent"
    assert solution.agent_run_id == run.id
    assert solution.status == "active"          # 终审进度由 review checkpoint 承载
    assert solution.source_json["kind"] == "adopted_artifact"
    assert solution.source_json["sha256"] == artifact.sha256
    # 红线 §6.6：只存指针，原件不进库
    assert solution.source_json["storage_ref"] == artifact.storage_ref
    assert "# 报告" not in (solution.design_markdown or "")
    # 产物回链
    db_session.refresh(artifact)
    assert artifact.linked_solution_id == solution_id
    # 事件留痕
    events = db_session.query(OperationEvent).filter(
        OperationEvent.event_type == "agent_artifact_adopted_as_solution"
    ).count()
    assert events == 1


def test_adopt_is_idempotent(client, db_session, settings):
    """幂等：同产物重复采纳 ⇒ 返回既有方案，不重复建、不重复落事件。"""
    admin, _viewer, _project, run, artifact = _seed_bundle(db_session, settings)
    env = {"client": client, "settings": settings}
    first = _post(env, admin, run, artifact)
    assert first.status_code == 200
    second = _post(env, admin, run, artifact)
    assert second.status_code == 200, second.get_json()
    data = second.get_json()["data"]
    assert data["duplicate"] is True and data["adopted"] is False
    assert data["solution_id"] == first.get_json()["data"]["solution_id"]
    assert db_session.query(ProjectSolution).filter(
        ProjectSolution.agent_run_id == run.id
    ).count() == 1
    assert db_session.query(OperationEvent).filter(
        OperationEvent.event_type == "agent_artifact_adopted_as_solution"
    ).count() == 1


def test_adopt_link_existing_solution(client, db_session, settings):
    """归入既有方案：人工已建方案时把产物挂上去（不新建方案）。"""
    admin, _viewer, project, run, artifact = _seed_bundle(db_session, settings)
    existing = ProjectSolution(
        project_id=project.id,
        owner_user_id=admin.id,
        name="人工已建方案",
        design_markdown="# 人工正文",
        deliverables="",
        acceptance_criteria="",
        data_systems="",
        schedule="",
        risks_dependencies="",
        status="active",
        generated_by="human",
    )
    db_session.add(existing)
    db_session.commit()
    response = _post({"client": client, "settings": settings}, admin, run, artifact,
                     {"target_solution_id": existing.id})
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["solution_id"] == existing.id and data["adopted"] is True
    db_session.refresh(existing)
    assert existing.agent_run_id == run.id and existing.generated_by == "agent"
    assert db_session.query(ProjectSolution).filter(
        ProjectSolution.agent_run_id == run.id
    ).count() == 1


def test_adopt_rejects_non_terminal_run(client, db_session, settings):
    """终态闸：run 未到终态 ⇒ 409（半成品不进方案台账）。"""
    admin, _viewer, _project, run, artifact = _seed_bundle(db_session, settings, run_status="host_running")
    response = _post({"client": client, "settings": settings}, admin, run, artifact)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "agent_run_not_terminal"


def test_adopt_rejects_second_artifact_same_run(client, db_session, settings):
    """一 run 一方案：同 run 已有产物被采纳 ⇒ 409（先归档既有方案）。"""
    admin, _viewer, _project, run, artifact = _seed_bundle(db_session, settings)
    env = {"client": client, "settings": settings}
    assert _post(env, admin, run, artifact).status_code == 200
    second = AgentArtifact(
        run_id=run.id,
        kind="doc",
        storage_ref=f"host:{run.id}/output/other.md",
        sha256=hashlib.sha256("# 另一份".encode("utf-8")).hexdigest(),
        reviewed=False,
    )
    db_session.add(second)
    db_session.commit()
    response = _post(env, admin, run, second)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "artifact_already_adopted"


def test_adopt_permission_same_ruler_as_review(client, db_session, settings):
    """权限同尺：viewer（不可管）⇒ 403；产物不属该 run ⇒ 404。"""
    admin, viewer, _project, run, artifact = _seed_bundle(db_session, settings)
    env = {"client": client, "settings": settings}
    response = _post(env, viewer, run, artifact)
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "project_forbidden"

    missing = client.post(
        f"/api/v1/agents/runs/{run.id}/artifacts/no-such-artifact/adopt-solution",
        headers=_headers(settings, admin),
        json={},
    )
    assert missing.status_code == 404
    assert missing.get_json()["error"]["code"] == "agent_artifact_not_found"


def test_adopt_route_not_in_catalog():
    """复核面纪律：产物采纳路由不进 api_catalog（终审动作沿业务对象纪律）。

    注：族内 ``translator.adopt`` **在** catalog（创作类写路径）；
    本路由属 agents 域终审/复核面——按 agents 域既有纪律（复核/终审写面
    不进目录）排除，故断言精确到本路径而非全量关键词。
    """
    from fde_api.control.api_catalog import CATALOG

    paths = [row["path"] for row in CATALOG.values()]
    assert not any("adopt-solution" in path for path in paths)
    assert not any("adopt-solution" in key for key in CATALOG)
