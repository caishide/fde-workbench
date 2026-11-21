"""AE2-WP4：编排审计留痕（54 号 v0.2-ACTIVE §3 WP4；负向设计 S-AE-09 C6/C7/C9/C10）。

- **C6/C7（节点审批腿，依赖路由/编排面）**：节点 risk≥3 真执行缺 approval_id →
  节点 failed（``approval_required``）＋上游已成功节点被补偿＋该节点零外呼；
  审批单不存在/跨租户 → 节点 failed（``approval_not_found``）零副作用；
- **C9（哨兵零命中·四处）**：哨兵值以**合法键名**进入参数 → 响应体／运行级
  留痕（``action_task_runs`` JSON 列）／节点审计行（``action_execution_logs``）／
  应用日志（caplog）四处全文 0 命中（AE1 三处＋运行级一处＝AE2 增量）；
- **C10（运行级零产物复制）**：上游 output 含哨兵 → 运行行 JSON 列 0 命中；
  节点 output 仅随该节点结果返回（响应体 nodes[].output 合法在场）；
- **运行级留痕齐备**（九必填口径的编排投影：零明文字段集闭集钉）；
- **append-only**：编排面无 PATCH/DELETE（路由钉见 test_ae_task_routes.py）；
  审计写入只在终态（沿 AE1 口径）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Any
from uuid import uuid4

import pytest
from flask import Flask
from sqlalchemy import select

from fde_api.action_execution.models import ActionExecutionLog, ActionTaskRun
from multi_tenant_harness import make_enterprise_org, make_user

SENTINEL = "AE-SENTINEL-SECRET-0001"
SENSITIVE_KEYS = ("access_token", "refresh_token", "client_secret", "api_key", "password", "bearer", "authorization")

# 运行级 audit_json 零明文字段集（闭集——多一个键即钉红；C10 结构保证）
RUN_AUDIT_ALLOWED_KEYS = frozenset(
    {
        "org_id",
        "requester_id",
        "actor_user_id",
        "definition_sha256",
        "node_count",
        "started_at",
        "finished_at",
        "duration_ms",
        "node_order",
        "orchestration",
        "failed_node",
    }
)


class AllowAllWhitelist:
    def check(self, connector_id: str, method: str) -> None:
        return None


class TaskDispatch:
    def __init__(self, *, fail_action_ids: set[str] | None = None, outputs: dict[str, dict[str, Any]] | None = None) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.seen: list[dict[str, Any]] = []
        self.fail_action_ids = fail_action_ids or set()
        self.outputs = outputs or {}

    def call(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.calls += 1
            self.seen.append(dict(request))
        if request["action_id"] in self.fail_action_ids:
            raise RuntimeError("dispatch exploded")
        return dict(self.outputs.get(request["action_id"], {"available": 3, "quantity": 1}))


class TaskCompensator:
    def compensate(self, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "compensation_id": "c-1",
            "kind": record["kind"],
            "target": record["target"],
            "status": "succeeded",
            "detail": {},
        }


@pytest.fixture
def audit_env(db_session):
    org = make_enterprise_org(db_session)
    actor = make_user(db_session, "project_lead", org_id=org.id)
    db_session.commit()
    return {"org": org, "actor": actor}


@pytest.fixture
def wired_orchestrator(monkeypatch):
    from fde_api.action_execution import routes as ae_routes

    state: dict[str, Any] = {"dispatch": TaskDispatch(), "compensator": None}

    def _factory() -> dict[str, Any]:
        return {
            "whitelist_gate": AllowAllWhitelist(),
            "dispatch": state["dispatch"],
            "compensator": state["compensator"],
        }

    monkeypatch.setattr(ae_routes, "_wired_orchestrator", _factory)
    return state


def _node(key: str, depends: tuple[str, ...] = (), **act_over: Any) -> dict[str, Any]:
    action: dict[str, Any] = {
        "action_id": f"mock.erp.{key}",
        "connector_id": "mock.erp",
        "method": "query_inventory",
        "params": {"sku": {"kind": "literal", "value": f"SKU-{key}"}},
        "dry_run": False,
        "risk_level": 1,
        "timeout_seconds": 30,
    }
    action.update(act_over)
    return {"node_key": key, "depends_on": list(depends), "action": action, "rollback_supported": True}


def _payload(org_id: str, requester_id: str, nodes: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "org_id": org_id,
        "requester_id": requester_id,
        "idempotency_key": "ae2-audit-" + uuid4().hex[:10],
        "definition": {"nodes": nodes},
    }


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---- C6/C7 · 节点审批腿（编排侧断言） ------------------------------------------


class TestNodeApprovalLegs:
    def test_c6_risk3_missing_approval_fails_node_and_compensates_upstream(
        self, db_session, audit_env, wired_orchestrator
    ) -> None:
        """C6：risk≥3 且 dry_run=false 且缺 approval_id → 节点侧 403
        ``approval_required``；该节点 failed；上游已成功节点被补偿。"""
        from fde_api.action_execution import task_orchestrator as orch

        payload = _payload(
            audit_env["org"].id,
            audit_env["actor"].id,
            [_node("n1"), _node("n2", ("n1",), risk_level=3)],  # 真执行缺审批
        )
        dispatch = TaskDispatch()
        result = orch.submit_task(
            actor=audit_env["actor"],
            payload=payload,
            whitelist_gate=AllowAllWhitelist(),
            dispatch=dispatch,
            compensator=TaskCompensator(),
        )
        by_key = {n["node_key"]: n for n in result["nodes"]}
        assert by_key["n1"]["status"] == "succeeded"  # 上游照常执行（1 次外呼）
        n2 = by_key["n2"]
        assert n2["status"] == "failed"
        assert n2["error"] is not None and n2["error"]["code"] == "approval_required"
        assert n2["action_execution_id"] is None  # 该节点零落库（L4 拒绝在锁前）
        assert dispatch.calls == 1  # 零副作用于该节点（下游未派发）
        assert result["status"] == "rolled_back"
        assert by_key["n1"]["compensation_status"] == "rolled_back"

    def test_c7_nonexistent_approval_fails_node_zero_side_effect(
        self, db_session, audit_env, wired_orchestrator
    ) -> None:
        """C7：审批单不存在 → 节点 failed（``approval_not_found``）零副作用。"""
        from fde_api.action_execution import task_orchestrator as orch

        payload = _payload(
            audit_env["org"].id,
            audit_env["actor"].id,
            [_node("n1", risk_level=3, approval_id="missing-approval-id")],
        )
        dispatch = TaskDispatch()
        result = orch.submit_task(
            actor=audit_env["actor"],
            payload=payload,
            whitelist_gate=AllowAllWhitelist(),
            dispatch=dispatch,
            compensator=TaskCompensator(),
        )
        n1 = result["nodes"][0]
        assert n1["status"] == "failed"
        assert n1["error"]["code"] == "approval_not_found"
        assert dispatch.calls == 0  # 零外呼
        assert result["status"] == "failed"  # 零可补偿节点 → failed 终态
        assert result["error"]["details"]["skipped_nodes"] == []


# ---- C9 · 哨兵零命中（响应体／运行级／节点审计行／应用日志 四处） ----------------


class TestSentinelZeroHit:
    def test_c9_sentinel_absent_in_four_surfaces(
        self, app: Flask, db_session, audit_env, wired_orchestrator, caplog
    ) -> None:
        """C9：哨兵值（合法键名 note 承载）在响应体/运行级留痕/节点审计行/
        应用日志四处全文 0 命中；运行级只留指纹。"""
        from fde_api.action_execution import task_orchestrator as orch

        payload = _payload(
            audit_env["org"].id,
            audit_env["actor"].id,
            [_node("n1", params={"note": {"kind": "literal", "value": SENTINEL}})],
        )
        with caplog.at_level(logging.INFO, logger="fde_api"):
            result = orch.submit_task(
                actor=audit_env["actor"],
                payload=payload,
                whitelist_gate=AllowAllWhitelist(),
                dispatch=TaskDispatch(),
            )
        assert result["status"] == "succeeded"
        run_id = result["execution_id"]

        # ① 响应体（TaskRunResult 全量序列化）
        response_text = json.dumps(result, ensure_ascii=False)
        # ② 运行级留痕（运行行全部 JSON 列）
        run = db_session.scalar(select(ActionTaskRun).where(ActionTaskRun.id == run_id))
        assert run is not None
        run_text = json.dumps(
            {"audit": run.audit_json, "cost": run.cost_json, "rollback": run.rollback_json,
             "error": run.error_json},
            ensure_ascii=False, default=str,
        )
        # ③ 节点审计行（AE1 action_execution_logs 全列）
        log_rows = db_session.scalars(select(ActionExecutionLog)).all()
        assert len(log_rows) == 1
        log_text = json.dumps([row.snapshot() for row in log_rows], ensure_ascii=False, default=str)
        # ④ 应用日志
        log_records = caplog.text

        for surface_name, surface_text in (
            ("response", response_text),
            ("run-row", run_text),
            ("audit-row", log_text),
            ("app-log", log_records),
        ):
            assert SENTINEL not in surface_text, f"哨兵命中 {surface_name}"
            assert "SKU-n1" not in surface_text, f"参数明文命中 {surface_name}"  # params 明文同样零落痕
        # 七敏感键名同样零命中（AE2 增运行级一处）
        for surface_name, surface_text in (("run-row", run_text), ("audit-row", log_text), ("response", response_text)):
            for key in SENSITIVE_KEYS:
                assert key not in surface_text, f"敏感键名 {key} 命中 {surface_name}"
        # 指纹在场（运行级只留 definition_sha256 与 params_sha256 锚）
        assert run.definition_sha256 == _sha(json.dumps(payload["definition"], ensure_ascii=False, sort_keys=True,
                                                       separators=(",", ":")))
        assert len(log_rows[0].params_sha256) == 64

    def test_run_audit_json_key_set_is_closed(self, db_session, audit_env, wired_orchestrator) -> None:
        """运行级 audit_json 键集闭集钉（多一个键即红——零明文结构保证）。"""
        from fde_api.action_execution import task_orchestrator as orch

        result = orch.submit_task(
            actor=audit_env["actor"],
            payload=_payload(audit_env["org"].id, audit_env["actor"].id, [_node("n1")]),
            whitelist_gate=AllowAllWhitelist(),
            dispatch=TaskDispatch(),
        )
        run = db_session.scalar(select(ActionTaskRun).where(ActionTaskRun.id == result["execution_id"]))
        assert run is not None
        assert set(run.audit_json) <= RUN_AUDIT_ALLOWED_KEYS


# ---- C10 · 运行级零产物复制 ----------------------------------------------------


class TestRunLevelNoOutputCopy:
    def test_c10_upstream_output_not_copied_to_run_row(
        self, db_session, audit_env, wired_orchestrator
    ) -> None:
        """C10：上游 output 含哨兵 → 运行行 JSON 列 0 命中；节点 output 仅随
        该节点结果返回（result.nodes[].output 合法在场）。"""
        from fde_api.action_execution import task_orchestrator as orch

        payload = _payload(
            audit_env["org"].id,
            audit_env["actor"].id,
            [_node("n1"), _node("n2", ("n1",))],
        )
        dispatch = TaskDispatch(outputs={"mock.erp.n1": {"report": SENTINEL, "available": 3}})
        result = orch.submit_task(
            actor=audit_env["actor"],
            payload=payload,
            whitelist_gate=AllowAllWhitelist(),
            dispatch=dispatch,
        )
        assert result["status"] == "succeeded"
        n1 = next(n for n in result["nodes"] if n["node_key"] == "n1")
        assert n1["output"] == {"report": SENTINEL, "available": 3}  # 节点级合法返回

        run = db_session.scalar(select(ActionTaskRun).where(ActionTaskRun.id == result["execution_id"]))
        assert run is not None
        run_text = json.dumps(
            {"audit": run.audit_json, "cost": run.cost_json, "rollback": run.rollback_json, "error": run.error_json},
            ensure_ascii=False, default=str,
        )
        assert SENTINEL not in run_text, "上游产物泄漏进运行级留痕"
        assert "report" not in run_text  # 产物键名同样不落运行级


# ---- 留痕齐备 · 节点级审计行（复用面验证） --------------------------------------


class TestNodeAuditRowsComplete:
    def test_successful_nodes_have_audit_rows_with_nine_fields(
        self, db_session, audit_env, wired_orchestrator
    ) -> None:
        """节点成功 → ``action_execution_logs`` 一行一执行（九必填齐备）——
        编排复用 AE1 审计面即自动齐备（钉＝复用路径不被绕过）。"""
        from fde_api.action_execution import task_orchestrator as orch

        result = orch.submit_task(
            actor=audit_env["actor"],
            payload=_payload(audit_env["org"].id, audit_env["actor"].id, [_node("n1"), _node("n2", ("n1",))]),
            whitelist_gate=AllowAllWhitelist(),
            dispatch=TaskDispatch(),
        )
        assert result["status"] == "succeeded"
        rows = db_session.scalars(select(ActionExecutionLog)).all()
        assert len(rows) == 2  # 每成功节点恰一行
        required = ("connector_id", "method", "params_sha256", "actor_user_id", "org_id", "approval_id",
                    "started_at", "finished_at", "duration_ms")
        for row in rows:
            snapshot = row.snapshot()
            for field in required:
                assert field in snapshot, field  # 九必填**字段在场**（approval_id 低风险可 null——U1 审计口径）
            for field in ("connector_id", "method", "params_sha256", "actor_user_id", "org_id",
                          "started_at", "finished_at", "duration_ms"):
                assert snapshot[field] is not None, field  # 非审批面字段值必非空
            assert snapshot["org_id"] == audit_env["org"].id
            assert snapshot["actor_user_id"] == audit_env["actor"].id

    def test_failed_node_leaves_no_audit_row(self, db_session, audit_env, wired_orchestrator) -> None:
        """失败路径不落审计行（沿 AE1「无真实起止时间即不伪造」口径）。"""
        from fde_api.action_execution import task_orchestrator as orch

        result = orch.submit_task(
            actor=audit_env["actor"],
            payload=_payload(audit_env["org"].id, audit_env["actor"].id, [_node("n1")]),
            whitelist_gate=AllowAllWhitelist(),
            dispatch=TaskDispatch(fail_action_ids={"mock.erp.n1"}),
            compensator=TaskCompensator(),
        )
        assert result["status"] == "failed"
        assert db_session.scalars(select(ActionExecutionLog)).all() == []
