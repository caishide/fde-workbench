"""AI 原生化 N3c（T-A10 合批）：产物内容读取面——sha256 自证＋防穿越＋容器态显式降级。

验收面（backlog T-A10 登记 + N3c 轮拍板）：
- 「看到什么就复核什么」桌面内闭环：content 逐字节 sha256 对库行指纹自证
  （不符 ⇒ 503 fail-closed——内容与被复核行不同源绝不能给复核人看）；
- 进程空间裁决（推荐项拍板）：宿主裸跑态全量可用；容器态原件不在场 ⇒
  **显式 404 artifact_content_unavailable（不静默、不伪造空内容）**；
- 路径防穿越（绝对路径/``..``/符号链接逃逸 ⇒ 404 path_unsafe）；超限 413
  不截断；只读零写零事件（预览不新增外发通道）；
- 权限与复核动作同尺（can_manage）；不进 api_catalog（复核面纪律）。
"""
from __future__ import annotations

import base64
import hashlib
from datetime import date
from uuid import uuid4

import pytest

from fde_api.agents import artifact_content
from fde_api.agents.artifact_content import read_artifact_content  # noqa: F401  (模块在场钉)
from fde_api.agents.models import AgentArtifact, AgentRun
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
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


def _seed_bundle(db_session, settings, tmp_path, *, content: bytes = "# 报告\n正文".encode("utf-8")):
    """admin + 项目 + completed run + 产物行 + 工作区原件（指纹一致）。"""
    admin = _user("n3c.ac.admin")
    viewer = _user("n3c.ac.viewer", role="viewer")
    project = Project(
        project_code=f"AC-{uuid4().hex[:6].upper()}",
        name="产物内容项目",
        enterprise_code="ac 客户·制造·苏州",
        business_line="FDE_DISPATCH",
        planned_start_date=date(2026, 10, 31),
        leader_user_id=admin.id,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([admin, viewer, project])
    db_session.flush()
    db_session.add(ProjectMember(project_id=project.id, user_id=viewer.id, role="viewer"))
    agent = seed_agent(db_session, settings, name="n3c 内容智能体", credential_ref=f"zcode-{uuid4().hex[:8]}")
    run = AgentRun(
        project_id=project.id,
        agent_id=agent.id,
        initiated_by_user_id=admin.id,
        capability_used="agent.plan.generate",
        status="completed",
        context_ref="ctx",
        idempotency_key=f"{uuid4().hex}:fp",
    )
    db_session.add(run)
    db_session.flush()
    artifact = AgentArtifact(
        run_id=run.id,
        kind="doc",
        storage_ref=f"{run.id}/output/report.md",
        sha256=hashlib.sha256(content).hexdigest(),
        reviewed=False,
    )
    db_session.add(artifact)
    db_session.commit()
    # 宿主工作区原件（平台身份 org 段=platform；storage_ref 含 {run_id}/output/ 前缀）
    target = tmp_path / "platform" / artifact.storage_ref
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return admin, viewer, project, run, artifact, content


@pytest.fixture()
def content_env(app, client, db_session, settings, tmp_path, monkeypatch):
    """把应用的 agent_workspace_root 指到本测 tmp_path（其余零变化）。"""
    monkeypatch.setitem(
        app.config,
        "SETTINGS",
        app.config["SETTINGS"].model_copy(update={"agent_workspace_root": str(tmp_path)}),
    )
    return {"app": app, "client": client, "db_session": db_session, "settings": settings, "tmp_path": tmp_path}


def _get(env, user: User, run, artifact):
    return env["client"].get(
        f"/api/v1/agents/runs/{run.id}/artifacts/{artifact.id}/content",
        headers=_headers(env["settings"], user),
    )


def test_content_happy_path_sha256_self_proof(content_env, db_session) -> None:
    admin, _viewer, _project, run, artifact, content = _seed_bundle(
        content_env["db_session"], content_env["settings"], content_env["tmp_path"]
    )
    response = _get(content_env, admin, run, artifact)
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert base64.b64decode(data["content_base64"]) == content
    assert data["sha256"] == artifact.sha256 and data["size"] == len(content)
    assert data["kind"] == "doc" and data["mime"] == "text/markdown"
    assert data["reviewed"] is False and data["run_id"] == run.id
    # 只读零事件：预览不落 operation_events
    assert (
        db_session.query(OperationEvent)
        .filter(OperationEvent.target_id == run.id)
        .count()
        == 0
    )


def test_content_missing_file_degrades_explicitly(content_env, db_session) -> None:
    """容器态降级语义：原件不在服务端可见工作区 ⇒ 404 显式码（不静默不伪造）。"""
    admin, _viewer, _project, run, artifact, _content = _seed_bundle(
        content_env["db_session"], content_env["settings"], content_env["tmp_path"]
    )
    (content_env["tmp_path"] / "platform" / artifact.storage_ref).unlink()
    response = _get(content_env, admin, run, artifact)
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "artifact_content_unavailable"


def test_content_path_traversal_rejected(content_env, db_session) -> None:
    admin, _viewer, _project, run, artifact, _content = _seed_bundle(
        content_env["db_session"], content_env["settings"], content_env["tmp_path"]
    )
    session = content_env["db_session"]
    # ①.. 上跳逃逸 output/
    artifact.storage_ref = f"{run.id}/output/../../secret.md"
    session.commit()
    response = _get(content_env, admin, run, artifact)
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "artifact_content_path_unsafe"
    # ②绝对路径
    artifact.storage_ref = "/etc/passwd"
    session.commit()
    response = _get(content_env, admin, run, artifact)
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "artifact_content_path_unsafe"


def test_content_fingerprint_mismatch_fail_closed(content_env, db_session) -> None:
    admin, _viewer, _project, run, artifact, _content = _seed_bundle(
        content_env["db_session"], content_env["settings"], content_env["tmp_path"]
    )
    target = content_env["tmp_path"] / "platform" / artifact.storage_ref
    target.write_bytes("# 被人改过的原件".encode("utf-8"))
    response = _get(content_env, admin, run, artifact)
    assert response.status_code == 503
    assert response.get_json()["error"]["code"] == "artifact_content_fingerprint_mismatch"


def test_content_oversize_rejected_not_truncated(content_env, db_session, monkeypatch) -> None:
    monkeypatch.setattr(artifact_content, "MAX_ARTIFACT_CONTENT_BYTES", 8)
    admin, _viewer, _project, run, artifact, _content = _seed_bundle(
        content_env["db_session"], content_env["settings"], content_env["tmp_path"]
    )
    response = _get(content_env, admin, run, artifact)
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "artifact_content_too_large"


def test_content_permission_same_ruler_as_review(content_env, db_session) -> None:
    """权限与复核动作同尺：can_manage 才可读；不可见项目 404 不泄露存在性。"""
    admin, viewer, _project, run, artifact, _content = _seed_bundle(
        content_env["db_session"], content_env["settings"], content_env["tmp_path"]
    )
    viewer_response = _get(content_env, viewer, run, artifact)
    assert viewer_response.status_code == 403
    assert viewer_response.get_json()["error"]["code"] == "project_forbidden"

    outsider = _user("n3c.ac.outsider", role="fde_engineer")
    content_env["db_session"].add(outsider)
    content_env["db_session"].commit()
    # 平台身份可见「平台内部 org 桶」项目（M3a 语义）⇒ 可见不可管＝403；
    # 「404 不泄露」面属企业受限归属，由跨企业隔离套件承载。
    outsider_response = _get(content_env, outsider, run, artifact)
    assert outsider_response.status_code == 403
    assert outsider_response.get_json()["error"]["code"] == "project_forbidden"

    missing = content_env["client"].get(
        f"/api/v1/agents/runs/no-such-run/artifacts/{artifact.id}/content",
        headers=_headers(content_env["settings"], admin),
    )
    assert missing.status_code == 404


def test_content_artifact_must_belong_to_run(content_env, db_session) -> None:
    admin, _viewer, _project, run, artifact, _content = _seed_bundle(
        content_env["db_session"], content_env["settings"], content_env["tmp_path"]
    )
    session = content_env["db_session"]
    other_run = AgentRun(
        project_id=run.project_id,
        agent_id=run.agent_id,
        initiated_by_user_id=admin.id,
        capability_used="agent.plan.generate",
        status="completed",
        context_ref="ctx",
        idempotency_key=f"{uuid4().hex}:fp",
    )
    session.add(other_run)
    session.commit()
    response = _get(content_env, admin, other_run, artifact)
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "artifact_not_found"


def test_content_route_not_in_catalog() -> None:
    """复核面纪律：内容读取路由不进 api_catalog（与 PATCH 复核写面同尺）。"""
    from fde_api.control.api_catalog import CATALOG

    assert not any("content" in key for key in CATALOG)
