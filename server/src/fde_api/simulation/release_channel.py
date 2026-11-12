"""改进提案受控发布通道（AI 原生化 N4，G-11）——全仓唯一的发布/回滚/工单写入点。

**语义收口（N4：静态钉由「零写入」改为「只许经发布通道写」）**：
- 状态机扩展 ``approved → published``（发布）与 ``published → approved``
  （回滚），两态迁移**只许**经本模块；
- **发布 ≠ 自动落地**（任务书 N4 边界）：本通道是**受控、审计、可回滚的
  记账面**——生产提示词 / Skill / 本体**正文零触碰**（N6 纪律：提示词正文
  不入库、不自动改），正文改动仍由人工在治理面实施；
- 发布闸四件：admin ＋ 当前账号密码确认 ＋ 提案须 ``approved`` ＋ 回归计划
  在案（``regression_plan_json`` 非空——没回归计划不给发布，风险③防后门）；
  note 必填留痕；
- 回滚闸：admin ＋ 密码 ＋ note；``published → approved``，``release_json``
  累积 ``rollback`` 子对象（原发布字段保留——审计链不断，可回滚路径有钉）；
- 复审工单（G-14 消费方）：``create_review_ticket`` 生成 draft 提案
  （target=prompt 文本指针），指纹含 UTC 日（每规则每日至多一张），零生产写。

静态钉（``tests/test_simulation_improvement.py``）：全仓 ``ImprovementProposal``
引用面 ⊆ {models, improvement_service, release_channel}；发布/回滚函数只许
住在本模块且必须带密码闸。
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.auth.passwords import verify_password
from fde_api.extensions import db
from fde_api.simulation.improvement_service import _serialize_proposal
from fde_api.simulation.models import ImprovementProposal
from fde_api.simulation.service import ScenarioServiceError, _require_level
from fde_api.workbench.models import OperationEvent

# 模拟域事件类型（直接落 operation_events，project_id 恒 None——模拟对象不属于
# 任何真实项目，service.py 同口径）。
EVENT_RELEASED = "simulation.proposal_released"
EVENT_ROLLED_BACK = "simulation.proposal_release_rolled_back"
EVENT_TICKET_CREATED = "simulation.review_ticket_created"

# 复审工单指纹的来源标识（含 UTC 日 ⇒ 每规则每日至多一张，重复评估幂等）。
_TICKET_SOURCE = "metrics_v31_ticket"


def _require_admin(actor: User) -> None:
    _require_level(actor)
    if actor.role != "admin":
        raise ScenarioServiceError(
            "forbidden", "提案发布/回滚需平台管理员。", 403
        )


def _require_confirmation(
    payload: dict[str, Any], *, actor: User
) -> str:
    """密码＋note 双必填（比照 decide_proposal：密码确认范式，note 必须留理由）。"""
    password = payload.get("password")
    if not isinstance(password, str) or not password or len(password) > 1024:
        raise ScenarioServiceError(
            "invalid_request", "password 必填（当前账号密码确认）。"
        )
    note = payload.get("note")
    if not isinstance(note, str) or not note.strip():
        raise ScenarioServiceError("invalid_request", "note 必填（发布必须留理由）。")
    if not verify_password(actor.password_hash, password):
        raise ScenarioServiceError("invalid_password", "当前账号密码不正确。", 403)
    return note.strip()


def _release_event(
    session, actor: User, row: ImprovementProposal, event_type: str, changes: dict[str, Any]
) -> None:
    session.add(
        OperationEvent(
            actor_user_id=actor.id,
            project_id=None,
            target_type="improvement_proposal",
            target_id=row.id,
            event_type=event_type,
            changes=changes,
        )
    )


def release_proposal(*, actor: User, proposal_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """发布已批准提案（G-11 受控发布通道；admin＋密码＋回归计划在案）。"""
    _require_admin(actor)
    note = _require_confirmation(payload, actor=actor)
    with db.session() as session:
        row = session.get(ImprovementProposal, proposal_id)
        if row is None:
            raise ScenarioServiceError("not_found", "改进提案不存在。", 404)
        if row.status == "published":
            raise ScenarioServiceError(
                "conflict", "该提案已发布。", 409, {"status": row.status}
            )
        if row.status != "approved":
            raise ScenarioServiceError(
                "conflict", "只有已批准（approved）的提案可发布。", 409, {"status": row.status}
            )
        if not (row.regression_plan_json or {}):
            raise ScenarioServiceError(
                "conflict",
                "发布闸：提案须附回归计划（regression_plan 非空）方可发布。",
                409,
                {"required": "regression_plan"},
            )
        release = {
            "released_at": datetime.now(UTC).isoformat(),
            "released_by_user_id": actor.id,
            "released_version": row.proposed_version,
            "release_note": note,
            "rollback": None,
        }
        row.status = "published"
        row.release_json = release
        _release_event(
            session,
            actor,
            row,
            EVENT_RELEASED,
            {
                "proposal_key": row.proposal_key,
                "target": dict(row.target_json or {}),
                "fingerprint": row.fingerprint,
                "released_version": release["released_version"],
                "release_note": note,
            },
        )
        session.flush()
        session.commit()
        return _serialize_proposal(row)


def rollback_release(*, actor: User, proposal_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """回滚已发布提案（published → approved；原发布字段保留，审计链不断）。"""
    _require_admin(actor)
    note = _require_confirmation(payload, actor=actor)
    with db.session() as session:
        row = session.get(ImprovementProposal, proposal_id)
        if row is None:
            raise ScenarioServiceError("not_found", "改进提案不存在。", 404)
        if row.status != "published":
            raise ScenarioServiceError(
                "conflict", "只有已发布（published）的提案可回滚。", 409, {"status": row.status}
            )
        release = dict(row.release_json or {})
        if release.get("rollback"):
            raise ScenarioServiceError(
                "conflict", "该提案已回滚，不可重复回滚。", 409
            )
        release["rollback"] = {
            "rolled_back_at": datetime.now(UTC).isoformat(),
            "rolled_back_by_user_id": actor.id,
            "rollback_note": note,
        }
        row.status = "approved"
        row.release_json = release
        _release_event(
            session,
            actor,
            row,
            EVENT_ROLLED_BACK,
            {
                "proposal_key": row.proposal_key,
                "target": dict(row.target_json or {}),
                "fingerprint": row.fingerprint,
                "rollback_note": note,
            },
        )
        session.flush()
        session.commit()
        return _serialize_proposal(row)


def create_review_ticket(
    *, rule: dict[str, Any], evidence: dict[str, Any]
) -> tuple[dict[str, Any] | None, str]:
    """按越限规则生成提示词复审工单（draft 提案；G-14 的唯一写入执行点）。

    指纹 = sha256(规则本体 + UTC 日)——同一规则同日重复评估幂等（已存在 ⇒
    返回 ``(None, "exists")`` 不重复建单）；次日仍越限则生成新工单（自然节
    奔）。工单是 draft 提案：**不触发任何生产写**，人工复核后才走既有审批/
    发布链。
    """
    canonical = json.dumps(
        {"source": _TICKET_SOURCE, "rule": rule, "date": evidence["utc_date"]},
        sort_keys=True,
        ensure_ascii=False,
    )
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    with db.session() as session:
        clash = session.scalar(
            select(ImprovementProposal).where(
                ImprovementProposal.fingerprint == fingerprint
            )
        )
        if clash is not None:
            return None, "exists"
        metric = str(rule["metric"])
        row = ImprovementProposal(
            proposal_key=f"TICKET-{fingerprint[:8].upper()}",
            title=f"指标复审工单：{metric} {rule['op']} {rule['threshold']}"[:160],
            problem=(
                f"v31 指标 {metric} 实测 {evidence['value']}"
                f"（样本 {evidence['sample_size']}）越限"
                f"（规则：{rule['op']} {rule['threshold']}，报告 {evidence['report_generated_at']}）"
                "——按复审规则自动生成，请人工复核对应提示词面。"
            )[:2000],
            finding_ids_json=[],
            finding_codes_json=["metrics_v31_breach"],
            fingerprint=fingerprint,
            target_json={"kind": "prompt", "ref": str(rule["prompt_ref"])},
            current_version="v1",
            proposed_version="v2",
            change_summary=json.dumps(evidence, sort_keys=True, ensure_ascii=False),
            expected_effect_json={},
            impact_scope_json=["metrics_v31"],
            regression_plan_json={},
            override_json={},
            status="draft",
            created_by_user_id=None,
        )
        session.add(row)
        session.flush()
        session.commit()
        return _serialize_proposal(row), "created"
