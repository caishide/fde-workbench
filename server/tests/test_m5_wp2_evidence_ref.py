"""M5-WP2② S-13 证据本体引用登记面（并入并行评审增量；模块域：evidence service）。

覆盖三条验收语义（工作令 §1 条 1）：
- 唯一指纹键防互踩：S-13 引用列**不进** ``(project_id, source_uri,
  content_sha256)`` 唯一键——引用是语义增强锚点，幂等语义零变化；
- 归属强验：引用必须钉住**本项目活跃绑定**版本，未钉/跨租户一律
  400 ``ontology_ref_not_pinned``（错误码不泄露本体存在性，S-01/S-13）；
- 证据不可变纪律：同指纹重复登记幂等（created=false）且首建引用不被改写。
"""

from __future__ import annotations

from sqlalchemy import UniqueConstraint, select

from fde_api.auth.models import User
from fde_api.auth.tokens import issue_access_token
from fde_api.evidence.models import ProjectEvidence
from fde_api.integrations.models import ProjectOntologyBinding
from fde_api.integrations.ontology_mock import M5_SEED_VERSION_ID, SEED_ONTOLOGY_ID
from fde_api.workbench.models import Project

from test_gates_api import AuthorizedClient
from test_gates_api import admin_client, gate_project  # noqa: F401  (pytest fixture 供给方)


# ---------------------------------------------------------------- fixtures


def _admin_client(env, db_session) -> AuthorizedClient:
    """gate_project 项目的 admin 执行人客户端（evidence 登记须 manage 位）。"""
    from fde_api.workbench.models import Project as _P  # noqa: F401  (类型引用)

    admin = db_session.scalar(select(User).where(User.username == "gate.admin"))
    assert admin is not None
    return AuthorizedClient(
        env["client"], admin, {"Authorization": f"Bearer {issue_access_token(admin, env['settings'])}"}
    )


def _m5_env(gate_project, client, db_session, settings):
    """(project, admin_client) + 活跃本体绑定（钉 ver-seed-1-1-0 演示版）。"""
    project, _gates_url, _leader = gate_project
    env = {
        "project": project,
        "client": client,
        "settings": settings,
        "org_id": db_session.get(Project, project["id"]).org_id,
    }
    admin_client = _admin_client(env, db_session)
    env["admin"] = admin_client
    project_row = db_session.get(Project, project["id"])
    binding = ProjectOntologyBinding(
        org_id=project_row.org_id,
        project_id=project["id"],
        ontology_id=SEED_ONTOLOGY_ID,
        pinned_version_id=M5_SEED_VERSION_ID,
        pinned_version="1.1.0",
        binding_role="primary",
        status="active",
        active_marker="active",
        bound_by_user_id=admin_client.user.id,
    )
    db_session.add(binding)
    db_session.commit()
    return env


# ---------------------------------------------------------------- 防互踩（ORM 层）


def test_evidence_unique_fingerprint_not_polluted_by_ref(db_session) -> None:
    """工作令防互踩：S-13 引用列不进 (project_id, source_uri, content_sha256) 唯一键。"""
    uq = next(
        c
        for c in ProjectEvidence.__table__.constraints  # type: ignore[attr-defined]
        if isinstance(c, UniqueConstraint)
    )
    assert set(uq.columns.keys()) == {"project_id", "source_uri", "content_sha256"}


# ---------------------------------------------------------------- 归属强验（API 层）


def test_evidence_ontology_ref_pinned_to_active_binding(gate_project, client, db_session, settings) -> None:
    """引用钉住活跃绑定版本 → 五列落库；引用未钉版本 → 400 防跨租户注入。"""
    env = _m5_env(gate_project, client, db_session, settings)
    pid = env["project"]["id"]
    ok = env["admin"].post(
        f"/api/v1/projects/{pid}/evidence",
        json={
            "kind": "gate",
            "source_uri": "fdeops://m5/ref-ok",
            "content_sha256": "b" * 64,
            "ontology_ref": {
                "ontology_id": SEED_ONTOLOGY_ID,
                "pinned_version_id": M5_SEED_VERSION_ID,
                "object_ref_id": "ref-obj-1",
            },
        },
    )
    assert ok.status_code == 201, ok.get_data(as_text=True)
    body = ok.json["data"]["evidence"]
    assert body["ontology_id"] == SEED_ONTOLOGY_ID
    assert body["pinned_version_id"] == M5_SEED_VERSION_ID
    assert body["object_ref_id"] == "ref-obj-1"
    assert body["action_request_id"] is None

    bad = env["admin"].post(
        f"/api/v1/projects/{pid}/evidence",
        json={
            "kind": "gate",
            "source_uri": "fdeops://m5/ref-bad",
            "content_sha256": "c" * 64,
            "ontology_ref": {
                "ontology_id": "ont-other-tenant",
                "pinned_version_id": "ver-other",
            },
        },
    )
    assert bad.status_code == 400
    assert bad.json["error"]["code"] == "ontology_ref_not_pinned"


def test_evidence_ref_idempotent_fingerprint_keeps_first_ref(gate_project, client, db_session, settings) -> None:
    """同指纹重复登记幂等（created=false）且首建引用不被改写（证据不可变纪律）。"""
    env = _m5_env(gate_project, client, db_session, settings)
    pid = env["project"]["id"]
    payload = {
        "kind": "gate",
        "source_uri": "fdeops://m5/idem",
        "content_sha256": "d" * 64,
        "ontology_ref": {
            "ontology_id": SEED_ONTOLOGY_ID,
            "pinned_version_id": M5_SEED_VERSION_ID,
        },
    }
    first = env["admin"].post(f"/api/v1/projects/{pid}/evidence", json=payload)
    assert first.status_code == 201
    second = env["admin"].post(f"/api/v1/projects/{pid}/evidence", json=payload)
    assert second.status_code == 200
    assert second.json["data"]["created"] is False
    row = db_session.scalar(
        select(ProjectEvidence).where(ProjectEvidence.source_uri == "fdeops://m5/idem")
    )
    assert row.ontology_id == SEED_ONTOLOGY_ID
