"""goal-d1（交付工作台升级 S0-1/S0-1b）：售前轻量录入卡 + G3 前置闸。

- PRD F1 / 决议 D16：presurvey_intakes 1:1 录入卡（S1–S2 可填，无敏感字段）；
  set_presurvey_source 与 create_analysis 需 G3 诊断开工门 passed
  （G3 证据清单=SOW-A+A 款+授权书四项，status 语义仅 pass/fail）。
- 判据：PRD §4 F1 + 技术实施方案 §3 goal-d1 表。
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from fde_api.auth.models import User
from fde_api.auth.tokens import issue_access_token
from fde_api.guidance.models import PresurveyIntake
from fde_api.workbench.models import Gate, IndustryTemplate, IndustryTemplateVersion, OperationEvent, Project


def _make_user(db_session, role: str) -> User:
    user = User(
        username=f"{role}.{uuid4().hex}",
        display_name=role,
        role=role,
        password_hash="x",
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _persisted_project(db_session, *, code: str | None = None):
    leader = _make_user(db_session, "project_lead")
    template = IndustryTemplate(name="录入卡模板", industry_name="制造")
    template_version = IndustryTemplateVersion(
        template=template,
        name=template.name,
        industry_name=template.industry_name,
        description="",
        version_number=1,
        status="published",
        published_by=leader,
    )
    project = Project(
        project_code=code or f"FDE-INTAKE-{uuid4().hex[:8]}",
        name="录入卡项目",
        enterprise_code="星河制造·制造·苏州",
        leader=leader,
        source_template_version=template_version,
        template_snapshot={},
        planned_start_date=date(2026, 11, 1),
    )
    db_session.add(project)
    db_session.commit()
    return project, leader


class AuthorizedClient:
    def __init__(self, client, user, headers):
        self.client = client
        self.user = user
        self.headers = headers

    def get(self, *args, **kwargs):
        return self.client.get(*args, headers=self.headers, **kwargs)

    def post(self, *args, **kwargs):
        return self.client.post(*args, headers=self.headers, **kwargs)

    def put(self, *args, **kwargs):
        return self.client.put(*args, headers=self.headers, **kwargs)


def _authed_client(client, user, settings) -> AuthorizedClient:
    return AuthorizedClient(
        client, user, {"Authorization": f"Bearer {issue_access_token(user, settings)}"}
    )


def _intake_base(project_id: str) -> str:
    return f"/api/v1/projects/{project_id}/presurvey-intake"


def _pass_g3(db_session, project) -> None:
    db_session.add(Gate(project_id=project.id, gate_key="G3", status="passed"))
    db_session.commit()


# ---- 录入卡（S0-1） ----


def test_intake_get_returns_default_card_when_absent(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    response = _authed_client(client, leader, settings).get(_intake_base(project.id))
    assert response.status_code == 200, response.get_data(as_text=True)
    card = response.json["data"]
    assert card["industry"] == "" and card["interview_mode"] == "onsite"
    assert card["interviewee_roles"] == [] and card["updated_at"] is None


def test_intake_put_and_get_roundtrip(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    api = _authed_client(client, leader, settings)
    payload = {
        "industry": "汽车零部件", "scale": "500-1000 人", "region": "苏州",
        "interview_mode": "remote", "interviewee_roles": ["生产部长", "IT 经理"],
        "customer_vision": "打通生产数据链路", "phase_objective": "完成诊断",
        "notes": "由城市合伙人转介",
    }
    put = api.put(_intake_base(project.id), json=payload)
    assert put.status_code == 200, put.get_data(as_text=True)
    card = put.json["data"]
    assert card["industry"] == "汽车零部件" and card["interview_mode"] == "remote"
    assert card["interviewee_roles"] == ["生产部长", "IT 经理"]
    assert card["updated_by_user_id"] == leader.id and card["updated_at"] is not None

    got = api.get(_intake_base(project.id))
    assert got.json["data"]["customer_vision"] == "打通生产数据链路"
    row = db_session.get(PresurveyIntake, project.id)
    assert row is not None and row.phase_objective == "完成诊断"


def test_intake_upsert_preserves_unmentioned_fields(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    api = _authed_client(client, leader, settings)
    first = api.put(_intake_base(project.id), json={"industry": "机械加工"})
    assert first.status_code == 200
    second = api.put(_intake_base(project.id), json={"region": "南通"})
    assert second.status_code == 200
    card = second.json["data"]
    assert card["industry"] == "机械加工" and card["region"] == "南通"


def test_intake_requires_manager(db_session, client, settings):
    from fde_api.workbench.models import ProjectMember

    project, leader = _persisted_project(db_session)
    viewer = _make_user(db_session, "viewer")
    outsider = _make_user(db_session, "fde_engineer")
    db_session.add(ProjectMember(project=project, user=viewer, role="viewer"))
    db_session.commit()
    assert _authed_client(client, viewer, settings).put(
        _intake_base(project.id), json={"industry": "x"}
    ).status_code == 403
    # 非成员按 house style 拿 404 掩护（_project 的 project_not_found），
    # 不泄露项目存在性——写与读一致。
    assert _authed_client(client, outsider, settings).put(
        _intake_base(project.id), json={"industry": "x"}
    ).status_code == 404
    assert _authed_client(client, outsider, settings).get(_intake_base(project.id)).status_code == 404


def test_intake_requires_auth(client):
    response = client.get("/api/v1/projects/whatever/presurvey-intake")
    assert response.status_code == 401


def test_intake_rejects_unknown_field(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    response = _authed_client(client, leader, settings).put(
        _intake_base(project.id), json={"contact_phone": "13800000000"}
    )
    assert response.status_code == 400
    assert response.json["error"]["code"] == "unknown_field"


def test_intake_rejects_bad_interview_mode(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    response = _authed_client(client, leader, settings).put(
        _intake_base(project.id), json={"interview_mode": "电话"}
    )
    assert response.status_code == 400


def test_intake_rejects_overlong_text(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    response = _authed_client(client, leader, settings).put(
        _intake_base(project.id), json={"industry": "行" * 81}
    )
    assert response.status_code == 400


def test_intake_rejects_bad_roles(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    api = _authed_client(client, leader, settings)
    assert api.put(_intake_base(project.id), json={"interviewee_roles": "生产部长"}).status_code == 400
    assert api.put(_intake_base(project.id), json={"interviewee_roles": ["角" * 81]}).status_code == 400


def test_intake_rejects_empty_payload(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    response = _authed_client(client, leader, settings).put(_intake_base(project.id), json={})
    assert response.status_code == 400


def test_intake_save_records_operation_event(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    put = _authed_client(client, leader, settings).put(
        _intake_base(project.id), json={"industry": "电子"}
    )
    assert put.status_code == 200
    event = (
        db_session.query(OperationEvent)
        .filter(OperationEvent.project_id == project.id)
        .filter(OperationEvent.event_type == "presurvey_intake_saved")
        .one()
    )
    assert event.changes == {"fields": ["industry"]}


# ---- G3 前置闸（S0-1b，行为变更：既有链路新增状态前置） ----


def _guidance_post(api: AuthorizedClient, project_id: str, payload: dict):
    return api.post(f"/api/v1/projects/{project_id}/guidance-analyses", json=payload)


def test_create_analysis_blocked_without_g3(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    response = _guidance_post(_authed_client(client, leader, settings), project.id, {})
    assert response.status_code == 409, response.get_data(as_text=True)
    assert response.json["error"]["code"] == "presurvey_s3_gate_open"


def test_set_presurvey_source_blocked_without_g3(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    response = _authed_client(client, leader, settings).post(
        f"/api/v1/projects/{project.id}/presurvey-source", json={"file_version_id": "nope"}
    )
    # 闸先于文件存在性校验：未过 G3 时连 404 文件错误都不应泄露。
    assert response.status_code == 409
    assert response.json["error"]["code"] == "presurvey_s3_gate_open"


def test_create_analysis_gate_passes_with_g3_passed(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    _pass_g3(db_session, project)
    response = _guidance_post(_authed_client(client, leader, settings), project.id, {})
    # 过闸后走到既有链路：无预调研源 → 400 presurvey_source_required。
    assert response.status_code == 400
    assert response.json["error"]["code"] == "presurvey_source_required"


def test_create_analysis_blocked_when_g3_only_evidence(db_session, client, settings):
    project, leader = _persisted_project(db_session)
    db_session.add(Gate(project_id=project.id, gate_key="G3", status="evidence"))
    db_session.commit()
    response = _guidance_post(_authed_client(client, leader, settings), project.id, {})
    assert response.status_code == 409
    assert response.json["error"]["code"] == "presurvey_s3_gate_open"
