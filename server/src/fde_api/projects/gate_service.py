"""gate_service：P3 门禁引擎（设计 §5，Gate 状态机驱动）。

口径铁律（照搬 SOP v2.4.6 + 映射表 v1.3；工程层不得发明方法论层没有的东西）：
- 状态机：pending →(提交证据) evidence →(人工核验) passed | conditional_pass | failed。
  conditional_pass 仅 G9（SOP 原文「有条件通过」）；G8 passed 必带 decision ∈
  {proceed, pivot, stop}（三者都算过门，stop 的结算由 P4 Payment 承接）；
  v0.2 已删无出处的 waived，此处不存在。
- claimed ≠ accepted（SOP 铁律，设计 §5.3）：清单每项 claim_status，
  提交出处 = claimed（UI 黄标），人工核验接受 = accepted。
  pass 要求全部项 accepted，conditional_pass 要求全部项至少 claimed——门禁不能是
  「点鼠标过场」。
- 证据只存出处指针（A4）：项级 source_uri + content_hash，内容本体在
  fdeops .fde/ 或 openfde assets/。
- failed 允许重新提交证据（G4 fail_exit「可随时重启」有出处）；
  passed / conditional_pass 为终态（SOP 无「撤销过门」语义）。
- 失败出口可触发（§5 验收）：decide fail 的响应与事件均带模板 fail_exit 原文，
  出口动作本身在 SOP 里由人执行，引擎只负责显式呈现与留痕。
- 模板：seeds/gates.json（烘进镜像）按项目幂等实例化 9 行（首次访问时懒初始化，
  兼容 P1/P2 期已激活的存量项目）；evidence_checklist 即模板快照（P1 口径，
  模板定义不另建 DB 表）。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from fde_api.auth.models import User
from fde_api.extensions import db
from fde_api.projects.events import record_event
from fde_api.projects.permissions import project_access
from fde_api.workbench.models import Gate, OperationEvent, Project, SopNode

GATE_STATUSES = ("pending", "evidence", "passed", "conditional_pass", "failed")
GATE_RESULTS = ("pass", "conditional_pass", "fail")
G8_DECISIONS = ("proceed", "pivot", "stop")
# 模板 checklist 项的合法 claim_status；null = 未提交（§5.3：accepted 之外一律黄标）
CLAIM_STATUSES = ("claimed", "accepted")

_GATE_KEY_PATTERN = re.compile(r"G[1-9]")
_HEX64_PATTERN = re.compile(r"[0-9a-fA-F]{64}")

_SEEDS_DIR = Path(__file__).resolve().parents[3] / "seeds"


class GateServiceError(Exception):
    def __init__(self, code: str, message: str, status: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@lru_cache(maxsize=1)
def _gate_templates() -> tuple[dict[str, Any], ...]:
    """读取 gates.json 模板（镜像内只读，进程级缓存足够）。"""
    path = _SEEDS_DIR / "gates.json"
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as error:
        raise RuntimeError("gates.json template unavailable") from error
    rows = payload.get("gates") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("gates.json template empty")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("gate_key"), str):
            raise RuntimeError("gates.json template row invalid")
    return tuple(rows)


def _template_index() -> dict[str, dict[str, Any]]:
    return {row["gate_key"]: row for row in _gate_templates()}


def ensure_project_gates(session: Session, project: Project) -> int:
    """按模板幂等实例化 9 行 Gate（已存在则不动），返回新建行数。

    先锁项目行再计数：两个并发首访不会双份 9 行（撞唯一约束 500）。
    """
    session.execute(
        select(Project.id).where(Project.id == project.id).with_for_update()
    )
    existing = session.scalar(
        select(func.count()).select_from(Gate).where(Gate.project_id == project.id)
    )
    if existing:
        return 0
    for template in _gate_templates():
        session.add(
            Gate(
                project_id=project.id,
                gate_key=template["gate_key"],
                status="pending",
                evidence_checklist=[
                    {
                        "label": label,
                        "claim_status": None,
                        "source_uri": None,
                        "content_hash": None,
                    }
                    for label in template.get("evidence_checklist") or []
                ],
                signer_role=template.get("signer_role"),
            )
        )
    return len(_gate_templates())


def _ensure_gates_logged(session: Session, actor: User, project: Project) -> None:
    """懒初始化（docstring 承诺「首次访问」）：list/submit/decide 入口统一走这里。"""
    created = ensure_project_gates(session, project)
    if created:
        record_event(
            session,
            actor,
            "gates_instantiated",
            project,
            {"gate_count": created, "source": "seeds/gates.json"},
        )


def list_project_gates(*, actor: User, project_id: str) -> dict[str, Any]:
    session = db.session()
    try:
        with session.begin():
            project = _load_project_for_gates(session, actor, project_id, manage=False)
            _ensure_gates_logged(session, actor, project)
            gates = list(
                session.scalars(select(Gate).where(Gate.project_id == project.id))
            )
            templates = _template_index()
            sop_nodes = _sop_nodes_for_templates(session, templates)
            order = {row["gate_key"]: index for index, row in enumerate(_gate_templates())}
            gates.sort(key=lambda gate: order.get(gate.gate_key, 99))
            items = [
                _serialize_gate(gate, templates.get(gate.gate_key), sop_nodes)
                for gate in gates
            ]
            events = _recent_gate_events(session, project.id)
        return {
            "project_id": project.id,
            "sop_phase": project.sop_phase,
            "gates": items,
            "events": events,
        }
    except GateServiceError:
        raise
    except RuntimeError as error:
        if str(error).startswith("gates.json"):
            raise GateServiceError(
                "gate_template_unavailable",
                "门禁模板不可用，请检查服务端 seeds/gates.json。",
                500,
            ) from None
        raise
    finally:
        session.close()


def submit_gate_evidence(
    *,
    actor: User,
    project_id: str,
    gate_key: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    items = _normalize_submission_items(payload)
    note = _optional_note(payload)
    session = db.session()
    try:
        with session.begin():
            project = _load_project_for_gates(session, actor, project_id, manage=True)
            _ensure_gates_logged(session, actor, project)
            gate = _load_gate(session, project.id, gate_key)
            if gate.status in ("passed", "conditional_pass"):
                raise GateServiceError(
                    "gate_already_decided", "该门禁已过门，不能再提交证据。", 409
                )
            checklist = {
                item["label"]: dict(item) for item in gate.evidence_checklist
            }
            unknown = [item["label"] for item in items if item["label"] not in checklist]
            if unknown:
                raise GateServiceError(
                    "invalid_gate_evidence",
                    f"清单项不存在：{'、'.join(unknown)}。",
                    400,
                )
            for item in items:
                checklist[item["label"]].update(
                    claim_status="claimed",
                    source_uri=item["source_uri"],
                    content_hash=item["content_hash"],
                )
            previous_status = gate.status
            gate.evidence_checklist = list(checklist.values())
            gate.status = "evidence"
            gate.submitted_at = datetime.now(timezone.utc)
            gate.evidence_uri = items[0]["source_uri"]
            gate.evidence_hash = items[0]["content_hash"]
            record_event(
                session,
                actor,
                "gate_evidence_submitted",
                gate,
                {
                    "gate_key": gate.gate_key,
                    "from_status": previous_status,
                    "to_status": gate.status,
                    "items": [
                        {
                            "label": item["label"],
                            "source_uri": item["source_uri"],
                            "content_hash": item["content_hash"],
                        }
                        for item in items
                    ],
                    "note": note,
                },
            )
            session.flush()
            templates = _template_index()
            sop_nodes = _sop_nodes_for_templates(session, templates)
            return _serialize_gate(gate, templates.get(gate.gate_key), sop_nodes)
    except GateServiceError:
        raise
    except RuntimeError as error:
        if str(error).startswith("gates.json"):
            raise GateServiceError(
                "gate_template_unavailable",
                "门禁模板不可用，请检查服务端 seeds/gates.json。",
                500,
            ) from None
        raise
    finally:
        session.close()


def decide_gate(
    *,
    actor: User,
    project_id: str,
    gate_key: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    result = payload.get("result")
    if result not in GATE_RESULTS:
        raise GateServiceError(
            "invalid_request", "result 必须是 pass / conditional_pass / fail。", 400
        )
    decision = payload.get("decision")
    if decision is not None and decision not in G8_DECISIONS:
        raise GateServiceError(
            "invalid_request", "decision 必须是 proceed / pivot / stop。", 400
        )
    accepted_labels_raw = payload.get("accepted_labels")
    if accepted_labels_raw is not None and (
        not isinstance(accepted_labels_raw, list)
        or not all(isinstance(label, str) for label in accepted_labels_raw)
    ):
        raise GateServiceError(
            "invalid_request", "accepted_labels 必须是字符串数组。", 400
        )
    note = _optional_note(payload)

    session = db.session()
    try:
        with session.begin():
            project = _load_project_for_gates(session, actor, project_id, manage=True)
            _ensure_gates_logged(session, actor, project)
            gate = _load_gate(session, project.id, gate_key)
            if gate.status != "evidence":
                raise GateServiceError(
                    "invalid_gate_state", "该门禁尚无待核验证据，先提交证据再核验。", 409
                )
            templates = _template_index()
            template = templates.get(gate.gate_key)
            if template is None:
                raise GateServiceError(
                    "gate_template_unavailable",
                    f"门禁 {gate.gate_key} 的模板定义缺失，请检查服务端 seeds/gates.json。",
                    500,
                )
            if gate.gate_key == "G8":
                if result != "pass" and decision is not None:
                    raise GateServiceError(
                        "gate_decision_not_allowed",
                        "decision 只随 G8 过门（pass）提交。",
                        400,
                    )
                if result == "pass" and decision is None:
                    raise GateServiceError(
                        "gate_decision_required",
                        "G8 过门必须书面拍板：proceed / pivot / stop 三选一。",
                        400,
                    )
            else:
                if result == "conditional_pass" and gate.gate_key != "G9":
                    raise GateServiceError(
                        "gate_result_not_allowed",
                        "conditional_pass（有条件通过）仅限 G9 上线门。",
                        400,
                    )
                if decision is not None:
                    raise GateServiceError(
                        "gate_decision_not_allowed",
                        "decision 三态拍板仅限 G8 试点毕业门。",
                        400,
                    )

            checklist = [dict(item) for item in gate.evidence_checklist]
            previous_status = gate.status
            changes: dict[str, Any] = {
                "gate_key": gate.gate_key,
                "from_status": previous_status,
                "result": result,
            }
            if result == "pass":
                # claimed ≠ accepted（SOP 铁律）：核验只能「接受已提交证据的项」，
                # 不许把从未提交的清单项直接追认 accepted 空证据过门。
                claimed = {
                    item["label"]
                    for item in checklist
                    if item["claim_status"] == "claimed"
                }
                accepted = (
                    set(accepted_labels_raw)
                    if accepted_labels_raw is not None
                    else claimed
                )
                not_claimed = sorted(accepted - claimed)
                if not_claimed:
                    raise GateServiceError(
                        "accepted_labels_not_claimed",
                        "accepted_labels 只能核验已提交证据的清单项："
                        f"{'、'.join(not_claimed)} 尚未提交。",
                        400,
                    )
                for item in checklist:
                    if item["label"] in accepted:
                        item["claim_status"] = "accepted"
                gate.evidence_checklist = checklist
                incomplete = [
                    item["label"]
                    for item in checklist
                    if item["claim_status"] != "accepted"
                ]
                if incomplete:
                    raise GateServiceError(
                        "gate_evidence_incomplete",
                        f"仍有清单项未接受核验，不能过门：{'、'.join(incomplete)}。",
                        400,
                    )
                gate.status = "passed"
                if decision is not None:
                    gate.decision = decision
                    changes["decision"] = decision
            elif result == "conditional_pass":
                unclaimed = [
                    item["label"]
                    for item in checklist
                    if item["claim_status"] not in CLAIM_STATUSES
                ]
                if unclaimed:
                    raise GateServiceError(
                        "gate_evidence_incomplete",
                        f"有条件通过也要求全部证据先提交：{'、'.join(unclaimed)}。",
                        400,
                    )
                gate.evidence_checklist = checklist
                gate.status = "conditional_pass"
            else:
                gate.evidence_checklist = checklist
                gate.status = "failed"
                changes["fail_exit"] = template.get("fail_exit") or ""
            gate.decided_at = datetime.now(timezone.utc)
            if note:
                changes["note"] = note
            # P4 承接（设计 §6）：G8 stop 也按合同结算（SOP §S8 三态）——
            # 联动给 G8 尾款收款行打 settlement_reason，B 尾款照收。
            settlement: dict[str, Any] | None = None
            if gate.gate_key == "G8" and result == "pass" and decision == "stop":
                from fde_api.projects.payment_service import flag_g8_stop_settlement

                settlement = flag_g8_stop_settlement(session, actor, project.id)
                changes["g8_stop_settlement"] = settlement
            record_event(session, actor, "gate_decided", gate, changes)
            session.flush()
            sop_nodes = _sop_nodes_for_templates(session, templates)
            result_payload = _serialize_gate(gate, template, sop_nodes)
            if settlement is not None:
                result_payload["g8_stop_settlement"] = settlement
            return result_payload
    except GateServiceError:
        raise
    except RuntimeError as error:
        if str(error).startswith("gates.json"):
            raise GateServiceError(
                "gate_template_unavailable",
                "门禁模板不可用，请检查服务端 seeds/gates.json。",
                500,
            ) from None
        raise
    finally:
        session.close()


def _load_project_for_gates(
    session: Session, actor: User, project_id: str, *, manage: bool
) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise GateServiceError("project_not_found", "项目不存在或已被删除。", 404)
    access = project_access(actor, project)
    if not (access.can_manage if manage else access.can_view):
        raise GateServiceError("forbidden", "你没有该项目门禁的操作权限。", 403)
    return project


def _load_gate(session: Session, project_id: str, gate_key: str) -> Gate:
    if not isinstance(gate_key, str) or not _GATE_KEY_PATTERN.fullmatch(gate_key):
        raise GateServiceError("invalid_request", "门禁编号格式不正确。", 400)
    gate = session.scalar(
        select(Gate)
        .where(Gate.project_id == project_id, Gate.gate_key == gate_key)
        .with_for_update()
    )
    if gate is None:
        raise GateServiceError("gate_not_found", "该门禁不存在。", 404)
    return gate


def _sop_nodes_for_templates(
    session: Session, templates: Mapping[str, dict[str, Any]]
) -> dict[str, SopNode]:
    """只取模板引用到的节点（避免每次请求全表扫 SopNode）。"""
    node_keys = {
        template.get("node_key")
        for template in templates.values()
        if template.get("node_key")
    }
    if not node_keys:
        return {}
    return {
        node.node_key: node
        for node in session.scalars(
            select(SopNode).where(SopNode.node_key.in_(node_keys))
        )
    }


def _normalize_submission_items(
    payload: Mapping[str, Any]
) -> list[dict[str, str]]:
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise GateServiceError(
            "invalid_request", "items 必须是非空数组（label + source_uri + content_hash）。", 400
        )
    normalized: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            raise GateServiceError("invalid_request", "items 元素必须是对象。", 400)
        label = item.get("label")
        source_uri = item.get("source_uri")
        content_hash = item.get("content_hash")
        if not isinstance(label, str) or not label.strip():
            raise GateServiceError("invalid_request", "label 不能为空。", 400)
        if not isinstance(source_uri, str) or not 0 < len(source_uri.strip()) <= 500:
            raise GateServiceError(
                "invalid_request", "source_uri 必须是 1–500 字符的出处指针。", 400
            )
        if not isinstance(content_hash, str) or not _HEX64_PATTERN.fullmatch(
            content_hash
        ):
            raise GateServiceError(
                "invalid_request", "content_hash 必须是 64 位十六进制 sha256。", 400
            )
        normalized.append(
            {
                "label": label.strip(),
                "source_uri": source_uri.strip(),
                "content_hash": content_hash.strip().lower(),
            }
        )
    return normalized


def _optional_note(payload: Mapping[str, Any]) -> str | None:
    note = payload.get("note")
    if note is None:
        return None
    if not isinstance(note, str) or not note.strip() or len(note) > 500:
        raise GateServiceError(
            "invalid_request", "note 必须是 1–500 字符的说明。", 400
        )
    return note.strip()


def _serialize_gate(
    gate: Gate,
    template: dict[str, Any] | None,
    sop_nodes: Mapping[str, SopNode],
) -> dict[str, Any]:
    node = sop_nodes.get(template.get("node_key")) if template else None
    return {
        "gate_key": gate.gate_key,
        "status": gate.status,
        "decision": gate.decision,
        "submitted_at": gate.submitted_at.isoformat() if gate.submitted_at else None,
        "decided_at": gate.decided_at.isoformat() if gate.decided_at else None,
        "evidence_uri": gate.evidence_uri,
        "evidence_hash": gate.evidence_hash,
        "checklist": [
            {
                "label": item.get("label"),
                "claim_status": item.get("claim_status"),
                "source_uri": item.get("source_uri"),
                "content_hash": item.get("content_hash"),
            }
            for item in gate.evidence_checklist
        ],
        # 模板快照（gates.json，A4 出处指针在模板 source_uri/source_sha256）
        "gate_name": template.get("gate_name") if template else None,
        "node_key": template.get("node_key") if template else None,
        "exit_condition": template.get("exit_condition") if template else None,
        "evidence_location": template.get("evidence_location") if template else None,
        "contract_payment": template.get("contract_payment") if template else None,
        "signer_role": template.get("signer_role") if template else gate.signer_role,
        "fail_exit": template.get("fail_exit") if template else None,
        "decision_semantics": template.get("decision_semantics") if template else None,
        "template_source_uri": template.get("source_uri") if template else None,
        "next_node_keys": node.next_node_keys if node else [],
    }


GATE_EVENT_TYPES = ("gates_instantiated", "gate_evidence_submitted", "gate_decided")


def _recent_gate_events(session: Session, project_id: str) -> list[dict[str, Any]]:
    # gates_instantiated 挂在 project 目标上，另两类挂在 gate 行上——按事件类型过滤
    events = list(
        session.scalars(
            select(OperationEvent)
            .options(joinedload(OperationEvent.actor))
            .where(
                OperationEvent.project_id == project_id,
                OperationEvent.event_type.in_(GATE_EVENT_TYPES),
            )
            .order_by(OperationEvent.occurred_at.desc())
            .limit(30)
        )
    )
    return [
        {
            "event_type": event.event_type,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "actor_display_name": event.actor.display_name if event.actor else None,
            "changes": event.changes,
        }
        for event in events
    ]
