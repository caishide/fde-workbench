"""V3.3 M5-WP2③④：Gate 本体辅助校验回执 + S-16/S-12 依赖闸 + Agent 禁改探针（TDD）。

D29/D31：Gate 求值瞬间固化不可变 ``GateEvaluationReceipt``（输入快照哈希 +
当时熔断降级态）；项目 Gate 只考核低置信度(<0.8)/冲突候选 100% 人工处置闭环。
S-16：``strong|weak|per_gate`` 双层枚举；S-12：下调依赖等级须项目 Owner 异人
审批（``leader_user_id`` 判定）且本体降级窗口期内禁生效。S-16 写通道不开放：
Agent（MCP 工具面）无任何 Gate 写工具（探针钉死）。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.control.ontology_gateway import call_ontology_tool
from fde_api.control.service import ControlServiceError
from fde_api.integrations.models import ACTIVE_MARKER, ProjectOntologyBinding
from fde_api.orgs.models import Org
from fde_api.integrations.ontology_mock import MockOntologyAdapter
from fde_api.ontology.gate_ontology_check import (
    approve_gate_dependency_change,
    enforce_dependency_before_decision,
    propose_gate_dependency_change,
)
from fde_api.workbench.models import (
    AcceptanceContract,
    Gate,
    GateEvaluationReceipt,
    OperationEvent,
    User,
)
from test_document_drafts_api import _persist_project

from conftest import INITIAL_PASSWORD


def _mk_user(db_session, username: str, role: str) -> User:
    user = User(
        username=username,
        display_name=username,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def m5_leader(db_session):
    return _mk_user(db_session, "m5.leader", "project_lead")


@pytest.fixture
def m5_admin(db_session):
    return _mk_user(db_session, "m5.admin", "admin")


@pytest.fixture
def ontology_project(db_session, m5_leader):
    """带 active 本体绑定的项目（绑定 seed 制造业本体 1.0.0；Owner = leader）。"""
    org = Org(org_type="enterprise", name="M5 依赖闸企业")
    db_session.add(org)
    db_session.commit()
    m5_leader.org_id = org.id
    db_session.commit()
    project = _persist_project(db_session, m5_leader, code="M5DEP")
    if project.org_id is None:  # helper 不显式传 org 时补齐归属（D10：归属=项目组织）
        project.org_id = org.id
        db_session.commit()
    db_session.add(
        ProjectOntologyBinding(
            org_id=org.id,
            project_id=project.id,
            ontology_id="ont-seed-mfg",
            pinned_version_id="ver-seed-1-0-0",
            pinned_version="1.0.0",
            bound_by_user_id=m5_leader.id,
            status="active",
            active_marker=ACTIVE_MARKER,
        )
    )
    db_session.commit()
    return project


@pytest.fixture
def gate_row(db_session, ontology_project):
    """项目门禁懒初始化后取 G5 行（模板无 ontology_dependency → resolve 兜底 required）。"""
    from fde_api.projects.gate_service import ensure_project_gates

    ensure_project_gates(db_session, ontology_project)
    db_session.commit()
    return db_session.scalars(
        select(Gate).where(
            Gate.project_id == ontology_project.id, Gate.gate_key == "G5"
        )
    ).one()


def _gate_template() -> dict[str, Any]:
    from fde_api.projects.gate_service import _template_index

    return _template_index()["G5"]


class _ClosedClient:
    """熔断闭合态 stub（S-12 审批流只读 breaker 态，不打真实请求）。"""

    breaker_state = "closed"


def test_enforce_no_binding_passes_honestly(
    db_session, ontology_project, gate_row, m5_admin, settings, monkeypatch
):
    """无活跃绑定的项目 = 未使用本体面（诚实缺省，workflow_runs NULL 同款）→ 放行。"""
    binding = db_session.scalars(
        select(ProjectOntologyBinding).where(
            ProjectOntologyBinding.project_id == ontology_project.id
        )
    ).one()
    db_session.delete(binding)
    db_session.commit()
    monkeypatch.setattr(settings, "ontology_enabled", True, raising=False)
    result = enforce_dependency_before_decision(
        db_session,
        project=ontology_project,
        gate=gate_row,
        template=_gate_template(),
        settings=settings,
        actor=m5_admin,
        client=MockOntologyAdapter(),
    )
    assert result["enforced"] is False


def test_enforce_disabled_flag_is_silent(
    db_session, ontology_project, gate_row, m5_admin, settings, monkeypatch
):
    """ontology_enabled=False（存量默认）→ 依赖闸完全静默，零行为变化。"""
    monkeypatch.setattr(settings, "ontology_enabled", False, raising=False)
    result = enforce_dependency_before_decision(
        db_session,
        project=ontology_project,
        gate=gate_row,
        template=_gate_template(),
        settings=settings,
        actor=m5_admin,
        client=MockOntologyAdapter(),
    )
    assert result["enforced"] is False


def test_enforce_required_unavailable_suspends(
    db_session, ontology_project, gate_row, m5_admin, settings, monkeypatch
):
    """required + 本体不可达 → 409 挂起（禁带病放行，S-16 strong 语义）。"""
    monkeypatch.setattr(settings, "ontology_enabled", True, raising=False)
    gate_row.ontology_dependency = "required"  # 显式建档（硬钳制不走全缺省兜底）
    adapter = MockOntologyAdapter()
    adapter.inject_fault("unavailable")
    from fde_api.projects.gate_service import GateServiceError

    with pytest.raises(GateServiceError) as excinfo:
        enforce_dependency_before_decision(
            db_session,
            project=ontology_project,
            gate=gate_row,
            template=_gate_template(),
            settings=settings,
            actor=m5_admin,
            client=adapter,
        )
    assert excinfo.value.status == 409
    assert excinfo.value.code == "gate_ontology_suspended"


def test_enforce_required_fixes_receipt_and_passes(
    db_session, ontology_project, gate_row, m5_admin, settings, monkeypatch
):
    """本体可达 + D31 处置闭环 → 固化不可变回执后放行（回执字段逐项断言）。"""
    monkeypatch.setattr(settings, "ontology_enabled", True, raising=False)
    result = enforce_dependency_before_decision(
        db_session,
        project=ontology_project,
        gate=gate_row,
        template=_gate_template(),
        settings=settings,
        actor=m5_admin,
        client=MockOntologyAdapter(),
    )
    db_session.commit()
    assert result["enforced"] is True
    assert result["degraded"] is False
    receipt = db_session.scalars(
        select(GateEvaluationReceipt).where(
            GateEvaluationReceipt.project_id == ontology_project.id,
            GateEvaluationReceipt.gate_key == "G5",
        )
    ).one()
    assert receipt.ontology_id == "ont-seed-mfg"
    assert receipt.pinned_version_id == "ver-seed-1-0-0"
    assert receipt.breaker_state == "closed"
    assert receipt.disposition_closed is True  # D31：种子候选 100% 处置闭环
    assert len(receipt.snapshot_sha256) == 64
    assert receipt.summary_json["ontology_version_id"] == "ver-seed-1-0-0"


def test_enforce_optional_degraded_passes_with_event(
    db_session, ontology_project, gate_row, m5_admin, settings, monkeypatch
):
    """optional + 本体不可达 → 放行但落「未校验」事件留痕（S-16 optional 语义）。"""
    monkeypatch.setattr(settings, "ontology_enabled", True, raising=False)
    gate_row.ontology_dependency = "optional"
    db_session.commit()
    adapter = MockOntologyAdapter()
    adapter.inject_fault("unavailable")
    result = enforce_dependency_before_decision(
        db_session,
        project=ontology_project,
        gate=gate_row,
        template=_gate_template(),
        settings=settings,
        actor=m5_admin,
        client=adapter,
    )
    db_session.commit()
    assert result["enforced"] is True
    assert result["degraded"] is True
    event = db_session.scalars(
        select(OperationEvent)
        .where(
            OperationEvent.project_id == ontology_project.id,
            OperationEvent.event_type == "gate_ontology_degraded",
        )
        .order_by(OperationEvent.id.desc())
    ).first()
    assert event is not None
    assert event.changes["gate_key"] == "G5"


def test_s12_downgrade_requires_distinct_owner_approval(
    db_session, ontology_project, gate_row, m5_admin, m5_leader, settings, monkeypatch
):
    """下调 optional→none：提案不落值；同人自批 403；Owner 异人批准才落值+双事件。"""
    monkeypatch.setattr(settings, "ontology_enabled", True, raising=False)
    gate_row.ontology_dependency = "optional"  # 先落基线再测下调
    db_session.commit()

    result = propose_gate_dependency_change(
        db_session,
        actor=m5_leader,  # 项目 Owner（leader_user_id）
        project=ontology_project,
        gate=gate_row,
        proposed_level="none",
    )
    db_session.commit()
    assert result["status"] == "proposed"
    assert gate_row.ontology_dependency == "optional"  # 提案不落值（S-12 锁）

    from fde_api.projects.gate_service import GateServiceError

    with pytest.raises(GateServiceError) as excinfo:
        approve_gate_dependency_change(
            db_session,
            actor=m5_leader,  # 同人自批 → 403
            project=ontology_project,
            gate=gate_row,
            proposed_level="none",
            client=_ClosedClient(),
            settings=settings,
        )
    assert excinfo.value.status == 403

    approved = approve_gate_dependency_change(
        db_session,
        actor=m5_admin,  # Owner/admin 异人批准
        project=ontology_project,
        gate=gate_row,
        proposed_level="none",
        client=_ClosedClient(),
        settings=settings,
    )
    db_session.commit()
    assert approved["status"] == "activated"
    assert gate_row.ontology_dependency == "none"
    kinds = {
        e.event_type
        for e in db_session.scalars(
            select(OperationEvent).where(OperationEvent.project_id == ontology_project.id)
        ).all()
    }
    assert "gate_dependency_downgrade_proposed" in kinds
    assert "gate_dependency_downgrade_activated" in kinds


def test_s12_non_owner_cannot_propose_downgrade(
    db_session, ontology_project, gate_row, m5_admin, settings
):
    """非 Owner（admin 之外且非 leader）提案下调 → 403。"""
    from fde_api.auth.passwords import hash_password as _hp
    from fde_api.projects.gate_service import GateServiceError

    outsider = User(
        username="m5.outsider",
        display_name="m5.outsider",
        role="fde_engineer",
        password_hash=_hp(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )
    db_session.add(outsider)
    db_session.commit()
    with pytest.raises(GateServiceError) as excinfo:
        propose_gate_dependency_change(
            db_session,
            actor=outsider,
            project=ontology_project,
            gate=gate_row,
            proposed_level="none",
        )
    assert excinfo.value.status == 403
    assert excinfo.value.code == "gate_dependency_owner_required"


def test_agent_cannot_write_gate_via_mcp(db_session, m5_admin):
    """MCP 工具面（D26 三工具）无任何 Gate 写操作 → gate 类工具名一律 invalid_tool。"""
    for tool_name in (
        "gate_decide",
        "gate_submit_evidence",
        "ontology_gate_decide",
        "gate_dependency_downgrade",
    ):
        with pytest.raises(ControlServiceError) as excinfo:
            call_ontology_tool(
                db_session,
                user=m5_admin,
                name=tool_name,
                arguments={"project_id": "p", "binding_id": "b"},
                execution_id="exec-1",
            )
        assert excinfo.value.status == 400


def test_acceptance_contract_persists(db_session, ontology_project, m5_admin):
    """契约项：输入清单/量化规则引用 + 异人 acceptor + SLA 默认 72h（D29）。"""
    contract = AcceptanceContract(
        project_id=ontology_project.id,
        gate_key="G5",
        title="批次追溯证据契约",
        items_json=[
            {"ref_kind": "input", "ref_key": "ev-batch-001", "note": "原始质检单"},
            {"ref_kind": "rule", "ref_key": "logic:batch_ttl", "note": "量化规则引用"},
        ],
        acceptor_user_id=m5_admin.id,
    )
    db_session.add(contract)
    db_session.commit()
    assert contract.sla_hours == 72  # D29 默认 72h
    assert contract.status == "active"


# ---- route 级烟测：decide_gate 拍板被本体依赖闸阻断（S-16 唯一结论入口接线）----


def test_decide_gate_route_blocked_by_ontology_gate(
    client, db_session, ontology_project, gate_row, m5_admin, m5_leader, settings, monkeypatch
):
    """required + 本体不可达 → POST decision 返回 409 gate_ontology_suspended。"""
    from fde_api.auth.tokens import issue_access_token

    gate_row.status = "evidence"
    gate_row.submitted_by_user_id = m5_admin.id  # P0-5：拍板人（leader）≠ 执行人
    gate_row.ontology_dependency = "required"  # 显式建档（硬钳制不走全缺省兜底）
    db_session.commit()
    monkeypatch.setattr(settings, "ontology_enabled", True, raising=False)
    adapter = MockOntologyAdapter()
    adapter.inject_fault("unavailable")
    monkeypatch.setattr(
        "fde_api.integrations.service.client_from_settings", lambda: adapter
    )
    headers = {
        "Authorization": f"Bearer {issue_access_token(m5_leader, settings)}"
    }
    resp = client.post(
        f"/api/v1/projects/{ontology_project.id}/gates/G5/decision",
        json={"result": "pass"},
        headers=headers,
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body["error"]["code"] == "gate_ontology_suspended"
