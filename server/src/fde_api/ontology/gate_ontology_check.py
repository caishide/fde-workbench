"""M5-WP2③④：Gate 本体辅助校验回执 + S-16/S-12 依赖闸（独立新模块）。

职责切分（D29）：Gate Service 是唯一结论入口——本模块只做**只读**本体辅助
校验并固化不可变 ``GateEvaluationReceipt``，不直接改写 Gate 状态；Agent 与
ontology-service 无任何 Gate 写通道（S-16，探针钉死于
``tests/test_m5_wp2_gate_receipt_service.py``）。

- D31 项目 Gate 口径：只考核低置信度(<0.8)/冲突候选 **100% 人工处置闭环**
  （免改/精修/驳回均绿灯）；``≥80%`` 免改率是后台编译器遥测，与本闸无关。
- S-16 双层枚举：全局 ``FDE_ONTOLOGY_GATE_DEPENDENCY = strong|weak|per_gate``
  （空值/缺省 = 契约默认 ``per_gate``）；仅 ``per_gate`` 读单门禁
  ``required|optional|none``（``gates.ontology_dependency``，NULL=模板默认）。
- S-12 防降级旁路锁：下调依赖等级须项目 Owner（``leader_user_id``，admin 恒
  可）**异人**审批，提案只留痕不落值；本体不可达（熔断）窗口期内禁生效。
- 诚实缺省：项目无活跃本体绑定 = 未使用本体面 → 闸静默放行（与 workflow_runs
  NULL 快照同款语义）；``ontology_enabled=False``（存量默认）→ 整闸关闭。

异常沿 ``GateServiceError``（函数内延迟 import，避免与 gate_service 循环依赖），
路由层 ``_gate_error`` 零改动接线。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.integrations.models import ACTIVE_MARKER, ProjectOntologyBinding
from fde_api.workbench.models import (
    Gate,
    GateEvaluationReceipt,
    OperationEvent,
    Project,
)

# 处置闭环判定键（D31；与 runtime governance.scan_candidate_disposition 同形，
# 缺键 fail-closed）
_DISPOSITION_ALL_DISPOSED_KEY = "all_disposed"


def _snapshot_sha256(summary: Mapping[str, Any]) -> str:
    """治理摘要 canonical JSON 的 sha256（回执验真锚点；与 mock 同款规范化）。"""
    return hashlib.sha256(
        json.dumps(summary, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _active_binding(session: Session, project_id: str) -> ProjectOntologyBinding | None:
    return session.scalars(
        select(ProjectOntologyBinding).where(
            ProjectOntologyBinding.project_id == project_id,
            ProjectOntologyBinding.status == "active",
            ProjectOntologyBinding.active_marker == ACTIVE_MARKER,
        )
    ).first()


def _breaker_state(client: Any) -> str:
    """读 client 熔断态只读视图；mock/旧适配器无此视图时兜底 closed。"""
    return str(getattr(client, "breaker_state", "closed"))


def _is_owner(user: User, project: Project) -> bool:
    """项目 Owner 判定（沿 permissions.project_access 同款惯例；admin 恒可）。"""
    if user.role == "admin":
        return True
    return user.id == project.leader_user_id and user.role in (
        "admin",
        "project_lead",
        "fde_engineer",
    )


def _record_event(
    session: Session,
    actor: User,
    event_type: str,
    project: Project,
    changes: Mapping[str, Any],
) -> None:
    from fde_api.projects.events import record_event

    record_event(session, actor, event_type, project, dict(changes))


def _load_summary(client: Any, binding: ProjectOntologyBinding, actor: User) -> dict[str, Any]:
    """拉取钉版治理摘要（只读；异常向调用方上抛由 _enforce_level 统一分流）。"""
    return client.get_version_governance_summary(
        actor_id=actor.id,
        org_id=binding.org_id,
        project_id=binding.project_id,
        ontology_id=binding.ontology_id,
        version_id=binding.pinned_version_id,
    )


def _fix_receipt(
    session: Session,
    *,
    actor: User,
    project: Project,
    gate: Gate,
    binding: ProjectOntologyBinding,
    summary: Mapping[str, Any],
    client: Any,
    level: str,
) -> GateEvaluationReceipt:
    """求值瞬间固化不可变回执（INSERT-only；D29 快照 + 降级态一并冻结）。

    ``summary`` 传空 Mapping 即降级回执（本体不可达 optional 放行场景）：
    快照只含 ``receipt_annotation``，透明标注「本体校验在线/降级态」（工作令
    §1 条 4）；快照哈希对注入标注后的**最终 JSON** 计算——验真重放口径一致。
    """
    breaker = _breaker_state(client)
    degradation = "degraded" if not summary else "online"
    annotated: dict[str, Any] = {
        **dict(summary),
        "receipt_annotation": {
            "degradation": degradation,
            "effective_dependency": level,
            "breaker_state": breaker,
        },
    }
    disposition = annotated.get("candidate_disposition")
    all_closed = (
        isinstance(disposition, Mapping)
        and disposition.get(_DISPOSITION_ALL_DISPOSED_KEY) is True
    )
    receipt = GateEvaluationReceipt(
        project_id=project.id,
        gate_key=gate.gate_key,
        ontology_id=binding.ontology_id,
        pinned_version_id=binding.pinned_version_id,
        snapshot_sha256=_snapshot_sha256(annotated),
        domain_schema_sha256=_opt_digest(annotated.get("domain_schema_sha256")),
        site_binding_sha256=_opt_digest(annotated.get("site_binding_sha256")),
        breaker_state=breaker,
        disposition_closed=bool(all_closed) if summary else True,
        summary_json=annotated,
        gate_ready=bool(annotated.get("gate_ready")),
        evaluated_at=datetime.now(UTC),
        created_by_user_id=actor.id,
    )
    session.add(receipt)
    session.flush()
    return receipt


def verify_receipt(receipt: GateEvaluationReceipt) -> bool:
    """回执验真（离线重放入口）：重算快照哈希与固化值比对。

    summary_json 是回执唯一大体积载荷——其 canonical JSON sha256 必须与
    ``snapshot_sha256`` 逐位一致；任一篡改（改处置结论/改标注）即失配。
    """
    return receipt.snapshot_sha256 == _snapshot_sha256(receipt.summary_json)


def _opt_digest(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def enforce_dependency_before_decision(
    session: Session,
    *,
    project: Project,
    gate: Gate,
    template: Mapping[str, Any],
    settings: Any,
    actor: User,
    client: Any = None,
) -> dict[str, Any]:
    """门禁拍板放行前的本体依赖闸（S-16/S-12/D31 唯一执行点）。

    返回 ``{"enforced": bool, "level": str|None, "degraded": bool,
    "receipt_id": str|None}``；阻断直接抛 ``GateServiceError``（409）。
    """
    from fde_api.ontology.dependency_gate import resolve_ontology_dependency

    if not getattr(settings, "ontology_enabled", False):
        # 存量默认（本体面关闭）：整闸静默，零行为变化（D12/D13 门控语义）
        return {"enforced": False, "level": None, "degraded": False, "receipt_id": None}

    level = resolve_ontology_dependency(
        getattr(settings, "ontology_gate_dependency", ""),
        template.get("ontology_dependency"),
        gate.ontology_dependency,
    )
    if level == "none":
        return {"enforced": False, "level": level, "degraded": False, "receipt_id": None}

    binding = _active_binding(session, project.id)
    if binding is None:
        # 诚实缺省：项目未使用本体面，无本体依赖可言（不伪造校验记录）
        return {"enforced": False, "level": level, "degraded": False, "receipt_id": None}

    if level == "weak":
        # S-16 §3：weak = 原规则运行 + 标注「未校验」（审计留痕，不阻断）
        _record_event(
            session,
            actor,
            "gate_ontology_skipped_weak",
            project,
            {"gate_key": gate.gate_key, "level": level},
        )
        return {"enforced": False, "level": level, "degraded": False, "receipt_id": None}

    if client is None:
        from fde_api.integrations.service import client_from_settings

        client = client_from_settings()

    summary: dict[str, Any] | None
    degraded = False
    try:
        summary = _load_summary(client, binding, actor)
    except Exception:
        # 本体不可达 / 熔断（mock 故障注入与真实网络故障同路）
        summary = None
        degraded = True
    breaker = _breaker_state(client)
    if breaker in ("open", "half_open"):
        degraded = True

    if degraded:
        if level == "optional":
            # optional：原规则运行 + 降级留痕（放行）；降级态同样固化进回执
            # （工作令 §1 条 4：回执透明标注「本体校验在线/降级态」）
            receipt = _fix_receipt(
                session, actor=actor, project=project, gate=gate,
                binding=binding, summary={}, client=client, level=level,
            )
            _record_event(
                session,
                actor,
                "gate_ontology_degraded",
                project,
                {
                    "gate_key": gate.gate_key,
                    "level": level,
                    "breaker_state": breaker,
                    "receipt_id": receipt.id,
                },
            )
            return {
                "enforced": True,
                "level": level,
                "degraded": True,
                "receipt_id": receipt.id,
            }
        # required/strong：挂起（禁带病放行；S-12 熔断窗口内也不得追溯放行）
        from fde_api.projects.gate_service import GateServiceError

        raise GateServiceError(
            "gate_ontology_suspended",
            "本体校验不可用（依赖等级 required）：门禁拍板挂起，恢复后重试。",
            409,
        )

    receipt = _fix_receipt(
        session, actor=actor, project=project, gate=gate, binding=binding,
        summary=summary or {}, client=client, level=level,
    )
    if not receipt.disposition_closed:
        if level == "optional":
            _record_event(
                session,
                actor,
                "gate_ontology_disposition_open",
                project,
                {"gate_key": gate.gate_key, "level": level, "receipt_id": receipt.id},
            )
            return {
                "enforced": True,
                "level": level,
                "degraded": False,
                "receipt_id": receipt.id,
            }
        from fde_api.projects.gate_service import GateServiceError

        raise GateServiceError(
            "gate_ontology_disposition_open",
            "本体治理未闭环（低置信度/冲突候选未 100% 人工处置）：门禁拍板阻断。",
            409,
        )
    return {
        "enforced": True,
        "level": level,
        "degraded": False,
        "receipt_id": receipt.id,
    }


def propose_gate_dependency_change(
    session: Session,
    *,
    actor: User,
    project: Project,
    gate: Gate,
    proposed_level: str,
) -> dict[str, Any]:
    """S-12 依赖等级变更提案。

    - 非法等级 422；**下调**（放松方向）→ 只留提案事件不落值（异人审批锁）；
    - 同值/升级（收紧方向）无风险 → 直接落值 + 留痕（无需审批）。
    """
    from fde_api.ontology.dependency_gate import GATE_DEPENDENCY_LEVELS, is_downgrade
    from fde_api.projects.gate_service import GateServiceError

    level = (proposed_level or "").strip()
    if level not in GATE_DEPENDENCY_LEVELS:
        raise GateServiceError(
            "invalid_request",
            f"ontology_dependency must be one of {GATE_DEPENDENCY_LEVELS}",
            400,
        )
    current = gate.ontology_dependency or ""
    if not _is_owner(actor, project):
        raise GateServiceError(
            "gate_dependency_owner_required",
            "依赖等级变更须项目 Owner 或平台 admin 提案。",
            403,
        )
    if not current or not is_downgrade(current, level):
        # 升级/同值/首次显式声明：直接生效
        gate.ontology_dependency = level
        _record_event(
            session,
            actor,
            "gate_dependency_changed",
            project,
            {
                "gate_key": gate.gate_key,
                "from_level": current or "(template default)",
                "to_level": level,
            },
        )
        return {"status": "activated", "level": level}
    _record_event(
        session,
        actor,
        "gate_dependency_downgrade_proposed",
        project,
        {
            "gate_key": gate.gate_key,
            "from_level": current,
            "to_level": level,
            "proposed_by": actor.id,
        },
    )
    return {"status": "proposed", "level": level}


def approve_gate_dependency_change(
    session: Session,
    *,
    actor: User,
    project: Project,
    gate: Gate,
    proposed_level: str,
    settings: Any,
    client: Any = None,
) -> dict[str, Any]:
    """S-12 下调审批生效闸：Owner 异人批准 + 非本体降级窗口 → 落值 + 留痕。"""
    from fde_api.ontology.dependency_gate import can_activate_downgrade, is_downgrade
    from fde_api.projects.gate_service import GateServiceError

    level = (proposed_level or "").strip()
    current = gate.ontology_dependency or ""
    if not current or not is_downgrade(current, level):
        raise GateServiceError(
            "invalid_request",
            "该变更不是待审批的下调（无提案或方向非下调）。",
            400,
        )
    proposal = session.scalars(
        select(OperationEvent)
        .where(
            OperationEvent.project_id == project.id,
            OperationEvent.event_type == "gate_dependency_downgrade_proposed",
        )
        .order_by(OperationEvent.id.desc())
    ).first()
    if proposal is None or proposal.changes.get("gate_key") != gate.gate_key:
        raise GateServiceError(
            "gate_dependency_no_proposal", "没有待生效的下调提案。", 409
        )
    if not _is_owner(actor, project):
        raise GateServiceError(
            "gate_dependency_owner_required",
            "依赖等级下调审批须项目 Owner 或平台 admin。",
            403,
        )

    degraded = False
    if getattr(settings, "ontology_enabled", False):
        if client is None:
            from fde_api.integrations.service import client_from_settings

            client = client_from_settings()
        if _breaker_state(client) in ("open", "half_open"):
            degraded = True
    proposed_by = str(proposal.changes.get("proposed_by", ""))
    if not can_activate_downgrade(
        proposer=proposed_by, approver=actor.id, degraded=degraded
    ):
        raise GateServiceError(
            "gate_dependency_approver_conflict",
            "异人审批锁：审批人须异于提案人，且本体降级窗口期内禁生效。",
            403,
        )
    gate.ontology_dependency = level
    _record_event(
        session,
        actor,
        "gate_dependency_downgrade_activated",
        project,
        {
            "gate_key": gate.gate_key,
            "from_level": current,
            "to_level": level,
            "proposed_by": proposed_by,
            "approved_by": actor.id,
        },
    )
    return {"status": "activated", "level": level}
