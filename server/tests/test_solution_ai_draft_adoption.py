"""GAP-15：AI 草稿采纳率埋点（方案确认流——系统派生，零申报零新表）。

钉住六件事（gap-register GAP-15 / ADR-007 §2.5 复审触发器的数据承载）：
1. AI 草稿方案（``generated_by='agent'``）首次被修改即在 ``source_json`` 落
   ``ai_draft_modified`` 戳——首改即定、幂等不翻回（二改时间戳不变）；
2. 人工方案（``generated_by='human'``/缺省）永不落戳、永不带 ai_draft 块
   ——既有事件形状向后兼容（不塞 None 键）；
3. ``solution_signoff_resolved`` 事件在拍板对象为 AI 草稿方案时携带
   ``ai_draft`` 派生块（generated_by/agent_run_id/modified_after_generation）
   ——approved+未修改=接受原稿、approved+已修改=修改后接受、rejected=拒绝；
4. 弃用 AI 草稿方案（``project_solution_archived``）＝拒绝/放弃信号，事件
   携带同款块；
5. 采纳率在既有 operation_events 事件序上可查——不建第二套事件体系；
6. 变异面：摘掉事件块派生或摘掉首改戳，上述断言逐一转红。
"""
from __future__ import annotations

from uuid import uuid4

from test_agents_d4_harness import (  # noqa: F401  (pytest fixture)
    api_client,
    d4_app,
    d4_client,
    d4_settings,
)
from test_document_drafts_api import _persist_project
from test_solution_signoff import _checkpoint  # 复用终审夹具助手

from conftest import INITIAL_PASSWORD
from fde_api.solutions.models import ProjectSolution
from fde_api.workbench.models import OperationEvent


def _solution(db_session, project, owner, *, generated_by: str | None = None) -> ProjectSolution:
    # agent_run_id 指向 agent_runs 真 FK——本文件只钉采纳留痕派生逻辑，
    # 不跑 run 接线链，故置 None（可空列；派生块如实携带 None）。
    solution = ProjectSolution(
        project_id=project.id,
        name="采纳留痕方案",
        owner_user_id=owner.id,
        generated_by=generated_by,
    )
    db_session.add(solution)
    db_session.commit()
    return solution


def _patch(client_wrapper, project, solution, **fields):
    payload = {"version": solution.version, **fields}
    return client_wrapper.patch(
        f"/api/v1/projects/{project.id}/solutions/{solution.id}", json=payload
    )


def _signoff(client_wrapper, project, solution, decision: str):
    return client_wrapper.post(
        f"/api/v1/projects/{project.id}/solutions/{solution.id}/signoff",
        json={"decision": decision},
    )


def _archive(client_wrapper, project, solution):
    return client_wrapper.post(
        f"/api/v1/projects/{project.id}/solutions/{solution.id}/archive",
        json={"version": solution.version, "password": INITIAL_PASSWORD},
    )


def _event(db_session, project, event_type: str) -> OperationEvent:
    return (
        db_session.query(OperationEvent)
        .filter(
            OperationEvent.event_type == event_type,
            OperationEvent.project_id == project.id,
        )
        .one()
    )


# ---------------------------------------------------------------------------
# 1. 首改落戳（AI 草稿方案）与人工方案零触碰
# ---------------------------------------------------------------------------


def test_ai_draft_solution_update_stamps_modified_once(d4_client, db_session, d4_settings) -> None:
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code=f"AD{uuid4().hex[:4]}")
    solution = _solution(db_session, project, leader.user, generated_by="agent")

    first = _patch(leader, project, solution, design_markdown="人工修改稿 v1")
    assert first.status_code == 200, first.json
    db_session.expire(solution)
    assert solution.source_json is not None
    assert solution.source_json["ai_draft_modified"] is True
    assert solution.source_json["ai_draft_modified_by_user_id"] == leader.user.id
    first_stamp = solution.source_json["ai_draft_modified_at"]

    # 首改即定：第二次修改不翻写时间戳（幂等不回填）
    second = _patch(leader, project, solution, design_markdown="人工修改稿 v2")
    assert second.status_code == 200, second.json
    db_session.expire(solution)
    assert solution.source_json["ai_draft_modified_at"] == first_stamp


def test_human_solution_update_never_stamps(d4_client, db_session, d4_settings) -> None:
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code=f"AD{uuid4().hex[:4]}")
    solution = _solution(db_session, project, leader.user, generated_by="human")

    body = _patch(leader, project, solution, design_markdown="纯人工撰写")
    assert body.status_code == 200, body.json
    db_session.expire(solution)
    assert solution.source_json is None


# ---------------------------------------------------------------------------
# 2. 拍板事件携带 ai_draft 派生块
# ---------------------------------------------------------------------------


def test_signoff_event_carries_unmodified_ai_draft_block(d4_client, db_session, d4_settings) -> None:
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code=f"AD{uuid4().hex[:4]}")
    solution = _solution(db_session, project, leader.user, generated_by="agent")
    _checkpoint(db_session, solution)

    body = _signoff(leader, project, solution, "approved")
    assert body.status_code == 200, body.json
    event = _event(db_session, project, "solution_signoff_resolved")
    assert event.changes["decision"] == "approved"
    assert event.changes["ai_draft"] == {
        "generated_by": "agent",
        "agent_run_id": None,
        "modified_after_generation": False,
    }


def test_signoff_event_flags_modified_after_generation(d4_client, db_session, d4_settings) -> None:
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code=f"AD{uuid4().hex[:4]}")
    solution = _solution(db_session, project, leader.user, generated_by="agent")
    _checkpoint(db_session, solution)
    assert _patch(leader, project, solution, design_markdown="改过再拍板").status_code == 200

    body = _signoff(leader, project, solution, "approved")
    assert body.status_code == 200, body.json
    event = _event(db_session, project, "solution_signoff_resolved")
    assert event.changes["ai_draft"]["modified_after_generation"] is True


def test_signoff_reject_on_ai_draft_still_carries_block(d4_client, db_session, d4_settings) -> None:
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code=f"AD{uuid4().hex[:4]}")
    solution = _solution(db_session, project, leader.user, generated_by="agent")
    _checkpoint(db_session, solution)

    body = _signoff(leader, project, solution, "rejected")
    assert body.status_code == 200, body.json
    event = _event(db_session, project, "solution_signoff_resolved")
    assert event.changes["decision"] == "rejected"
    assert event.changes["ai_draft"]["generated_by"] == "agent"


def test_signoff_event_omits_ai_draft_for_human_solution(d4_client, db_session, d4_settings) -> None:
    """向后兼容钉：人工方案拍板事件不得出现 ai_draft 键（旧行形状零漂移）。"""
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code=f"AD{uuid4().hex[:4]}")
    solution = _solution(db_session, project, leader.user, generated_by="human")
    _checkpoint(db_session, solution)

    body = _signoff(leader, project, solution, "approved")
    assert body.status_code == 200, body.json
    event = _event(db_session, project, "solution_signoff_resolved")
    assert "ai_draft" not in event.changes


# ---------------------------------------------------------------------------
# 3. 弃用（archive）事件携带同款块
# ---------------------------------------------------------------------------


def test_archive_event_carries_ai_draft_block(d4_client, db_session, d4_settings) -> None:
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code=f"AD{uuid4().hex[:4]}")
    solution = _solution(db_session, project, leader.user, generated_by="agent")
    assert _patch(leader, project, solution, design_markdown="改后弃用").status_code == 200
    db_session.expire(solution)

    body = _archive(leader, project, solution)
    assert body.status_code == 200, body.json
    event = _event(db_session, project, "project_solution_archived")
    assert event.changes["ai_draft"] == {
        "generated_by": "agent",
        "agent_run_id": None,
        "modified_after_generation": True,
    }


def test_archive_event_omits_ai_draft_for_human_solution(d4_client, db_session, d4_settings) -> None:
    leader = api_client(d4_client, db_session, d4_settings, "project_lead")
    project = _persist_project(db_session, leader.user, code=f"AD{uuid4().hex[:4]}")
    solution = _solution(db_session, project, leader.user)

    body = _archive(leader, project, solution)
    assert body.status_code == 200, body.json
    event = _event(db_session, project, "project_solution_archived")
    assert "ai_draft" not in event.changes
