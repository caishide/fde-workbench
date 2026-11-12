"""改进提案受控发布通道（N4 G-11）——发布/回滚闸与审计链。

钉住：①发布闸四件（admin＋密码＋approved 态＋回归计划在案）缺一 4xx；
②发布→published＋operation_events 审计行；③回滚→approved＋release_json
累积 rollback 子对象（原发布字段保留＝审计链不断）；④重复发布/重复回滚
409；⑤序列化暴露 release 面。
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from conftest import INITIAL_PASSWORD, SERVER_ROOT
from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.extensions import db
from fde_api.simulation.models import ImprovementProposal
from fde_api.workbench.models import OperationEvent


@dataclass(frozen=True)
class _Client:
    client: object
    user: User
    headers: dict[str, str]

    def get(self, *args, **kwargs):
        return self.client.get(*args, headers=self.headers, **kwargs)

    def post(self, *args, **kwargs):
        return self.client.post(*args, headers=self.headers, **kwargs)


def _make_client(client, db_session, settings, *, role: str) -> _Client:
    user = User(
        username=f"sim.release.{role}.{uuid4().hex[:8]}",
        display_name="Release channel tester",
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return _Client(client, user, {"Authorization": f"Bearer {issue_access_token(user, settings)}"})


@pytest.fixture
def admin(client, db_session, settings):
    return _make_client(client, db_session, settings, role="admin")


@pytest.fixture
def lead(client, db_session, settings):
    return _make_client(client, db_session, settings, role="project_lead")


@pytest.fixture(autouse=True)
def _clean_release(db_session):
    yield
    db_session.rollback()
    db_session.execute(
        delete(OperationEvent).where(OperationEvent.target_type == "improvement_proposal")
    )
    db_session.execute(delete(ImprovementProposal))
    db_session.commit()


def _proposal(db_session, *, status: str, regression_plan: dict | None) -> ImprovementProposal:
    row = ImprovementProposal(
        proposal_key=f"PROP-{uuid4().hex[:8].upper()}",
        title="改进：知识采集前置",
        problem="失败分析指向知识采集滞后。",
        finding_ids_json=[],
        finding_codes_json=["missing_source_refs"],
        fingerprint=uuid4().hex[:16],
        target_json={"kind": "prompt", "ref": "quality.testcase_draft"},
        current_version="v1",
        proposed_version="v2",
        change_summary="在起草提示词中前置知识采集检查单。",
        expected_effect_json={},
        impact_scope_json=["quality"],
        regression_plan_json=regression_plan or {},
        override_json={},
        status=status,
    )
    db_session.add(row)
    db_session.commit()
    return row


def _release(client, proposal_id: str):
    return client.post(
        f"/api/v1/simulation/proposals/{proposal_id}/release",
        json={"password": INITIAL_PASSWORD, "note": "回归计划在案，发布。"},
    )


def _rollback(client, proposal_id: str):
    return client.post(
        f"/api/v1/simulation/proposals/{proposal_id}/rollback",
        json={"password": INITIAL_PASSWORD, "note": "线上表现不符预期，回滚。"},
    )


def _release_events(db_session) -> list[OperationEvent]:
    return list(
        db_session.scalars(
            select(OperationEvent).where(
                OperationEvent.target_type == "improvement_proposal"
            ).order_by(OperationEvent.created_at, OperationEvent.id)
        )
    )


def test_release_requires_admin(lead, db_session):
    row = _proposal(db_session, status="approved", regression_plan={"cases": ["r1"]})
    response = _release(lead, row.id)
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "forbidden"


def test_release_requires_password_and_note(admin, db_session):
    row = _proposal(db_session, status="approved", regression_plan={"cases": ["r1"]})
    missing_password = admin.post(
        f"/api/v1/simulation/proposals/{row.id}/release", json={"note": "缺密码"}
    )
    assert missing_password.status_code == 400
    wrong_password = admin.post(
        f"/api/v1/simulation/proposals/{row.id}/release",
        json={"password": "wrong-password", "note": "密码错"},
    )
    assert wrong_password.status_code == 403
    assert wrong_password.get_json()["error"]["code"] == "invalid_password"
    missing_note = admin.post(
        f"/api/v1/simulation/proposals/{row.id}/release",
        json={"password": INITIAL_PASSWORD},
    )
    assert missing_note.status_code == 400


def test_release_gate_requires_approved_status(admin, db_session):
    row = _proposal(db_session, status="draft", regression_plan={"cases": ["r1"]})
    response = _release(admin, row.id)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "conflict"


def test_release_gate_requires_regression_plan(admin, db_session):
    row = _proposal(db_session, status="approved", regression_plan=None)
    response = _release(admin, row.id)
    assert response.status_code == 409
    body = response.get_json()["error"]
    assert body["code"] == "conflict"
    assert body["details"] == {"required": "regression_plan"}


def test_release_publishes_and_audits(admin, db_session):
    row = _proposal(db_session, status="approved", regression_plan={"cases": ["r1"]})
    response = _release(admin, row.id)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "published"
    assert data["release"]["released_by_user_id"] == admin.user.id
    assert data["release"]["released_version"] == "v2"
    assert data["release"]["rollback"] is None
    events = _release_events(db_session)
    assert [event.event_type for event in events] == ["simulation.proposal_released"]
    assert events[0].changes["fingerprint"] == row.fingerprint
    assert events[0].changes["release_note"] == "回归计划在案，发布。"


def test_release_twice_conflicts(admin, db_session):
    row = _proposal(db_session, status="approved", regression_plan={"cases": ["r1"]})
    assert _release(admin, row.id).status_code == 200
    again = _release(admin, row.id)
    assert again.status_code == 409
    assert again.get_json()["error"]["code"] == "conflict"


def test_rollback_restores_approved_and_appends_audit(admin, db_session):
    row = _proposal(db_session, status="approved", regression_plan={"cases": ["r1"]})
    release = _release(admin, row.id).get_json()["data"]
    response = _rollback(admin, row.id)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["status"] == "approved"
    assert data["release"]["rollback"]["rolled_back_by_user_id"] == admin.user.id
    # 原发布字段保留——审计链不断（可回滚路径的回滚留痕）。
    assert data["release"]["released_at"] == release["release"]["released_at"]
    assert data["release"]["released_version"] == "v2"
    assert [event.event_type for event in _release_events(db_session)] == [
        "simulation.proposal_released",
        "simulation.proposal_release_rolled_back",
    ]
    second = _rollback(admin, row.id)
    assert second.status_code == 409


def test_rollback_requires_published(admin, db_session):
    row = _proposal(db_session, status="approved", regression_plan={"cases": ["r1"]})
    response = _rollback(admin, row.id)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "conflict"


def test_proposal_listing_exposes_release_face(admin, db_session):
    row = _proposal(db_session, status="approved", regression_plan={"cases": ["r1"]})
    before = admin.get("/api/v1/simulation/proposals").get_json()["data"]["items"]
    assert [item["release"] for item in before if item["id"] == row.id] == [None]
    _release(admin, row.id)
    after = admin.get("/api/v1/simulation/proposals").get_json()["data"]["items"]
    released = next(item for item in after if item["id"] == row.id)
    assert released["status"] == "published"
    assert released["release"]["released_version"] == "v2"


def test_release_channel_module_is_sole_write_point_outside_domain():
    """release/rollback 函数只许住 release_channel 且带闸（源级复钉——独立于
    test_simulation_improvement 的全仓扫描，防本域内绕行）。"""
    channel_path = (
        SERVER_ROOT / "src" / "fde_api" / "simulation" / "release_channel.py"
    )
    text = channel_path.read_text(encoding="utf-8")
    assert "verify_password(actor.password_hash, password)" in text
    assert 'actor.role != "admin"' in text
    # 通道不写生产正文：模块内禁止出现任何生产模块 import。
    for production_module in ("discovery", "quality", "plans", "workflows"):
        assert f"from fde_api.{production_module}" not in text, production_module
