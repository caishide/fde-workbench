"""G8 重评机械闸回归（E-4③，2026-11-28）。

seeds/gates.json G8 fail_exit 原文「证据不足→延长时间盒（书面）或 stop；
不允许无限『再跑跑看』」的代码强制（gate_service._require_g8_reeval_discipline）：
- 仅域 G8——其余门 fail_exit 有「可随时重启」等出处，闸之即违背方法论层；
- 超时间盒（Settings.gate_g8_reeval_window_days）或累计 fail 拍板达上限
  （Settings.gate_g8_reeval_max_fails）后，重评须随附书面说明（note）——
  放行即事件留痕 timebox_extended；无 note 则 409 两分码拒绝；
- 窗内且未触线的重评零变化（基线回归钉），fail 计数只认 result=fail 且
  只认本门禁行的事件。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from fde_api.workbench.models import Gate, OperationEvent

from test_gates_api import (  # noqa: F401 — 复用夹具与读面助手
    _gate_snapshot,
    _submit_all_evidence,
    admin_client,
    gate_project,
)


def _fail_g8(admin_client, gates_url: str, leader_client) -> None:
    """提交全部 G8 证据并由 leader 拍 fail（admin 执行、leader 拍板＝P0-5 分离）。"""
    revision = _submit_all_evidence(admin_client, gates_url, "G8")
    response = leader_client.post(
        f"{gates_url}/G8/decision",
        json={"expected_revision": revision, "result": "fail"},
    )
    assert response.status_code == 200, response.get_data(as_text=True)


def _submit_g8_evidence(admin_client, gates_url: str, *, note: str | None = None):
    gate = _gate_snapshot(admin_client, gates_url, "G8")
    payload = {
        "expected_revision": gate["revision"],
        "items": [
            {
                "label": item["label"],
                "source_uri": f"fdeops://g8-reeval/{gate['revision']}/{index}",
                "content_hash": hashlib.sha256(
                    f"{item['label']}@{gate['revision']}".encode()
                ).hexdigest(),
            }
            for index, item in enumerate(gate["checklist"])
        ],
    }
    if note is not None:
        payload["note"] = note
    return admin_client.post(f"{gates_url}/G8/evidence", json=payload)


def _age_decided_at(db_session, project_id: str, gate_key: str, days: int) -> None:
    """把门禁行 decided_at 回拨 N 天（窗口边界测试的时钟退移）。"""
    db_session.execute(
        update(Gate)
        .where(Gate.project_id == project_id, Gate.gate_key == gate_key)
        .values(decided_at=datetime.now(timezone.utc) - timedelta(days=days))
    )
    db_session.commit()


def _submitted_changes(db_session) -> list[dict]:
    rows = db_session.scalars(
        select(OperationEvent).where(
            OperationEvent.event_type == "gate_evidence_submitted"
        )
    ).all()
    return [row.changes for row in rows if isinstance(row.changes, dict)]


def _flagged_events(db_session) -> list[OperationEvent]:
    rows = db_session.scalars(
        select(OperationEvent).where(
            OperationEvent.event_type == "gate_evidence_submitted"
        )
    ).all()
    return [
        row
        for row in rows
        if isinstance(row.changes, dict) and row.changes.get("timebox_extended")
    ]


def _add_noise_event(
    db_session,
    *,
    actor_user_id: str,
    project_id: str,
    target_gate_id: str,
    gate_key: str,
    result: str,
) -> None:
    """直插一条合成 gate_decided 事件（fail 计数域钉的干扰源，沿
    test_extract_case_from_project.py 的直插先例；不计入真实状态机）。"""
    db_session.add(
        OperationEvent(
            actor_user_id=actor_user_id,
            project_id=project_id,
            target_type="gate",
            target_id=target_gate_id,
            event_type="gate_decided",
            changes={"gate_key": gate_key, "from_status": "evidence", "result": result},
        )
    )
    db_session.commit()


def test_g8_first_submission_before_any_fail_unaffected(
    admin_client, gate_project, db_session
):
    """G8 首提（无 fail 历史）不受机械闸影响：pending 态不在闸域。"""
    _project, gates_url, _leader = gate_project
    response = _submit_g8_evidence(admin_client, gates_url)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert not any(row.get("timebox_extended") for row in _submitted_changes(db_session))


def test_g8_reeval_within_window_baseline_allowed(admin_client, gate_project, db_session):
    """fail 后窗内重评（fail_count=1 < 上限）零变化放行，不留痕 timebox_extended。"""
    _project, gates_url, leader_client = gate_project
    _fail_g8(admin_client, gates_url, leader_client)
    response = _submit_g8_evidence(admin_client, gates_url)
    assert response.status_code == 200, response.get_data(as_text=True)
    assert not any(row.get("timebox_extended") for row in _submitted_changes(db_session))


def test_g8_reeval_window_expired_requires_written_note(
    admin_client, gate_project, db_session
):
    """超时间盒（14 天窗，回拨 15 天）无书面说明 → 409 gate_reeval_window_expired。"""
    _project, gates_url, leader_client = gate_project
    _fail_g8(admin_client, gates_url, leader_client)
    _age_decided_at(db_session, _project["id"], "G8", days=15)
    response = _submit_g8_evidence(admin_client, gates_url)
    assert response.status_code == 409, response.get_data(as_text=True)
    assert response.json["error"]["code"] == "gate_reeval_window_expired"
    assert "延长时间盒" in response.json["error"]["message"]


def test_g8_reeval_window_expired_with_note_passes_and_audits(
    admin_client, gate_project, db_session
):
    """超窗后随附书面说明（note）放行：事件恰一旗标、note 与 from_status 留痕。"""
    _project, gates_url, leader_client = gate_project
    _fail_g8(admin_client, gates_url, leader_client)
    _age_decided_at(db_session, _project["id"], "G8", days=15)
    note = "客户书面同意延长时间盒两周（邮件指针 fdeops://p8/extension-01）"
    response = _submit_g8_evidence(admin_client, gates_url, note=note)
    assert response.status_code == 200, response.get_data(as_text=True)
    flagged = _flagged_events(db_session)
    assert len(flagged) == 1
    assert flagged[0].changes["note"] == note
    assert flagged[0].changes["from_status"] == "failed"
    assert flagged[0].changes["to_status"] == "evidence"


def test_g8_reeval_cap_reached_requires_written_note(admin_client, gate_project):
    """三次 fail 后（上限 3）窗内重评仍须书面说明：无 note → 409 cap_reached。"""
    _project, gates_url, leader_client = gate_project
    for _ in range(3):
        _fail_g8(admin_client, gates_url, leader_client)
    response = _submit_g8_evidence(admin_client, gates_url)
    assert response.status_code == 409, response.get_data(as_text=True)
    assert response.json["error"]["code"] == "gate_reeval_cap_reached"
    assert "3 次" in response.json["error"]["message"]


def test_g8_reeval_cap_with_note_passes(admin_client, gate_project, db_session):
    """超次后随附书面说明放行：留痕 timebox_extended（「不允许无限」＝不许无记录再评）。"""
    _project, gates_url, leader_client = gate_project
    for _ in range(3):
        _fail_g8(admin_client, gates_url, leader_client)
    response = _submit_g8_evidence(
        admin_client, gates_url, note="第 4 轮再评：客户书面延长（decisions.md 行 42）"
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    assert len(_flagged_events(db_session)) == 1


def test_g8_reeval_scope_excludes_other_gates(admin_client, gate_project, db_session):
    """域钉：G4 fail_exit 原文「可随时重启」——超窗重评不闸（仅域 G8）。"""
    _project, gates_url, leader_client = gate_project
    revision = _submit_all_evidence(admin_client, gates_url, "G4")
    response = leader_client.post(
        f"{gates_url}/G4/decision", json={"expected_revision": revision, "result": "fail"}
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    _age_decided_at(db_session, _project["id"], "G4", days=15)
    gate = _gate_snapshot(admin_client, gates_url, "G4")
    resubmit = admin_client.post(
        f"{gates_url}/G4/evidence",
        json={
            "expected_revision": gate["revision"],
            "items": [
                {
                    "label": item["label"],
                    "source_uri": f"fdeops://g4-restart/{gate['revision']}/{index}",
                    "content_hash": hashlib.sha256(item["label"].encode()).hexdigest(),
                }
                for index, item in enumerate(gate["checklist"])
            ],
        },
    )
    assert resubmit.status_code == 200, resubmit.get_data(as_text=True)
    assert not any(row.get("timebox_extended") for row in _submitted_changes(db_session))


def test_g8_reeval_then_pass_full_chain_still_reachable(
    admin_client, gate_project, db_session
):
    """机械闸不挡合法过门：超窗书面重评 → 三态拍板 pass/proceed → 终态闸原样。"""
    _project, gates_url, leader_client = gate_project
    _fail_g8(admin_client, gates_url, leader_client)
    _age_decided_at(db_session, _project["id"], "G8", days=15)
    response = _submit_g8_evidence(
        admin_client, gates_url, note="补齐 POC 验收表第五项后书面延长提交"
    )
    assert response.status_code == 200, response.get_data(as_text=True)
    revision = response.json["data"]["revision"]
    decided = leader_client.post(
        f"{gates_url}/G8/decision",
        json={"expected_revision": revision, "result": "pass", "decision": "proceed"},
    )
    assert decided.status_code == 200, decided.get_data(as_text=True)
    again = _submit_g8_evidence(admin_client, gates_url)
    assert again.status_code == 409
    assert again.json["error"]["code"] == "gate_already_decided"


def test_g8_fail_count_ignores_non_fail_and_foreign_gate_events(
    admin_client, gate_project, db_session
):
    """fail 计数只认本门禁行的 result=fail：同门 pass 噪声与他门 fail 噪声不入计数。"""
    _project, gates_url, leader_client = gate_project
    _fail_g8(admin_client, gates_url, leader_client)
    g8 = db_session.scalar(
        select(Gate).where(
            Gate.project_id == _project["id"], Gate.gate_key == "G8"
        )
    )
    g9 = db_session.scalar(
        select(Gate).where(
            Gate.project_id == _project["id"], Gate.gate_key == "G9"
        )
    )
    # 两条同门 pass 噪声＋两条他门 fail 噪声：计数若漏任一过滤都会把
    # fail_count 抬到 ≥3 触发 409——正确语义 1 < 3 放行。
    for _ in range(2):
        _add_noise_event(
            db_session,
            actor_user_id=admin_client.user.id,
            project_id=_project["id"],
            target_gate_id=g8.id,
            gate_key="G8",
            result="pass",
        )
    for _ in range(2):
        _add_noise_event(
            db_session,
            actor_user_id=admin_client.user.id,
            project_id=_project["id"],
            target_gate_id=g9.id,
            gate_key="G9",
            result="fail",
        )
    response = _submit_g8_evidence(admin_client, gates_url)
    assert response.status_code == 200, response.get_data(as_text=True)


def test_g8_reeval_window_days_config_override(
    admin_client, gate_project, db_session, app, monkeypatch
):
    """配置面生效钉：窗口覆写为 1 天后，回拨 2 天即触超窗（默认 14 天不触）。"""
    _project, gates_url, leader_client = gate_project
    monkeypatch.setattr(app.config["SETTINGS"], "gate_g8_reeval_window_days", 1)
    _fail_g8(admin_client, gates_url, leader_client)
    _age_decided_at(db_session, _project["id"], "G8", days=2)
    response = _submit_g8_evidence(admin_client, gates_url)
    assert response.status_code == 409, response.get_data(as_text=True)
    assert response.json["error"]["code"] == "gate_reeval_window_expired"


@pytest.mark.parametrize("note", ["   ", ""])
def test_g8_reeval_blank_note_does_not_count_as_written(
    admin_client, gate_project, db_session, note
):
    """空白 note 不算书面说明：_optional_note 归一层直接 400，进不了机械闸。"""
    _project, gates_url, leader_client = gate_project
    _fail_g8(admin_client, gates_url, leader_client)
    _age_decided_at(db_session, _project["id"], "G8", days=15)
    response = _submit_g8_evidence(admin_client, gates_url, note=note)
    assert response.status_code == 400
    assert response.json["error"]["code"] == "invalid_request"
