"""AE2 出口轮评审修复钉（bmad-code-review 四层×三组 12 层评审→P1「全部批准」修复轮）。

每钉对应评审分诊的一处修复（实现面组），钉先红后绿（修复已随本文件同 PR 落位；
变异自验：逐一回退修复→对应钉红→还原零残留）：
- R1 补偿路由非 dict 请求体 → 422（此前 AttributeError 裸 500）；
- R2 approval_id 空串提交期拒（契约 NodeAction minLength:1 此前漏过）；
- R3 compensate_task 校验序对齐 S3→S4（跨租户 404 不被 viewer 403 抢先）；
- R4 补偿段非域异常诚实收口（此前冒泡致运行行滞留 compensating 非终态）；
- R5 失败腿 rollback_supported 置位（DN-1 甲案：派发已发生的失败行按调用方
  置位，补偿通道不被恒 not_supported 堵死；成功腿为 WP3 断线修复，本钉补失败腿）。
"""
from __future__ import annotations

import threading
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from fde_api.action_execution import service as ae_service
from fde_api.action_execution import task_orchestrator as orch
from fde_api.action_execution.models import ActionExecution, ActionTaskRun
from multi_tenant_harness import make_enterprise_org, make_user


class AllowAllWhitelist:
    def check(self, connector_id: str, method: str) -> None:
        return None


class TaskDispatch:
    """可计数 dispatch 桩（同构 test_ae_task_audit.py）。"""

    def __init__(self, *, fail_action_ids: set[str] | None = None, explode: bool = False) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.fail_action_ids = fail_action_ids or set()
        self.explode = explode  # 补偿段非域异常注入位

    def call(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self.calls += 1
        if self.explode:
            raise RuntimeError("dispatch exploded (non-domain)")
        if request["action_id"] in self.fail_action_ids:
            raise RuntimeError("dispatch exploded (non-domain)")
        return {"available": 3, "quantity": 1}


class TaskCompensator:
    """可控补偿器桩：kind 命中 refuse_kinds 时抛**非域异常**（R4 注入位）。"""

    def __init__(self, refuse_kinds: set[str] | None = None) -> None:
        self.kinds: list[str] = []
        self._refuse = refuse_kinds or set()

    def compensate(self, record: dict[str, Any]) -> dict[str, Any]:
        if record["kind"] in self._refuse:
            raise RuntimeError("compensator infrastructure exploded (non-domain)")
        self.kinds.append(str(record["kind"]))
        return {
            "compensation_id": f"c-{len(self.kinds)}",
            "kind": record["kind"],
            "target": record["target"],
            "status": "succeeded",
            "detail": {},
        }


@pytest.fixture
def fx_env(db_session):
    org = make_enterprise_org(db_session)
    actor = make_user(db_session, "project_lead", org_id=org.id)
    viewer = make_user(db_session, "viewer", org_id=org.id)
    db_session.commit()
    return {"org": org, "actor": actor, "viewer": viewer}


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
        "idempotency_key": "ae2-rfix-" + uuid4().hex[:10],
        "definition": {"nodes": nodes},
    }


def _run_rows(db_session, key: str) -> list[ActionTaskRun]:
    return list(db_session.scalars(select(ActionTaskRun).where(ActionTaskRun.idempotency_key == key)).all())


# ---- R1 · 补偿路由非 dict 体 422 -------------------------------------------------


class TestCompensateRouteShape:
    def test_compensate_route_non_dict_body_is_422(self, db_session, fx_env, client, test_settings) -> None:
        """补偿路由请求体为真值非对象（如 ``[1]``）→ 422（此前 AttributeError 裸 500）。"""
        from fde_api.auth.tokens import issue_access_token

        headers = {"Authorization": f"Bearer {issue_access_token(fx_env['actor'], test_settings)}"}
        resp = client.post(
            f"/api/v1/action-tasks/{uuid4().hex}/compensation",
            json=[1, 2],
            headers=headers,
        )
        assert resp.status_code == 422
        body = resp.get_json()
        assert body["error"]["code"] == "validation_failed"


# ---- R2 · approval_id minLength（契约 NodeAction minLength:1） --------------------


class TestApprovalIdMinLength:
    def test_approval_id_empty_string_rejected_at_submit(self, db_session, fx_env) -> None:
        """approval_id=""（空串）提交期 422＋零运行行（契约 minLength:1——
        此前只查上界 ≤128，空串漏过并在运行期才以 201+failed 收口）。"""
        from fde_api.action_execution.errors import ActionExecutionError

        payload = _payload(
            fx_env["org"].id,
            fx_env["actor"].id,
            [_node("n1", risk_level=3, approval_id="")],
        )
        dispatch = TaskDispatch()
        with pytest.raises(ActionExecutionError) as exc:
            orch.submit_task(
                actor=fx_env["actor"], payload=payload, whitelist_gate=AllowAllWhitelist(), dispatch=dispatch
            )
        assert exc.value.code == "validation_failed"
        assert dispatch.calls == 0  # 提交期静态拒零外呼
        assert _run_rows(db_session, str(payload["idempotency_key"])) == []  # 零运行行


# ---- R3 · compensate_task 校验序 S3→S4 --------------------------------------------


class TestCompensateValidationOrder:
    def test_compensate_tenant_gate_precedes_capability(
        self, db_session, fx_env, monkeypatch
    ) -> None:
        """跨租户 run_id ＋ viewer 档位 → 404 not_found（S3 租户闸先于 S4 档位——
        此前 _check_capability 在租户闸前，viewer 跨租户触发补偿得 403 泄露探测面）。"""
        from fde_api.action_execution.errors import ActionExecutionError
        from fde_api.action_execution.models import ActionTaskRun

        # 他 org 的终态运行行（直落一行，租户闸命中即短路、状态不参与）
        other_org = make_enterprise_org(db_session)
        run = ActionTaskRun(
            id=uuid4().hex,
            org_id=other_org.id,
            idempotency_key="ae2-rfix-cross-" + uuid4().hex[:8],
            definition_sha256="0" * 64,
            node_count=1,
            status="failed",
            requester_id=fx_env["actor"].id,
            audit_json={},
            rollback_json={},
            cost_json={},
        )
        db_session.add(run)
        db_session.commit()
        with pytest.raises(ActionExecutionError) as exc:
            orch.compensate_task(
                actor=fx_env["viewer"], execution_id=run.id, compensator=None, reason=None
            )
        assert exc.value.code == "not_found"  # 404（非 permission_revoked 403）


# ---- R4 · 补偿段非域异常诚实收口 ---------------------------------------------------


class TestCompensatePassNonDomain:
    def test_compensate_pass_non_domain_exception_is_honest_failed(self, db_session, fx_env, monkeypatch) -> None:
        """补偿段漏出**非域异常**（rollback_action 自身基础设施故障）→ 该节点
        补偿 failed 诚实登记＋运行收口 ``compensation_failed``（残留逐条）——
        此前裸异常冒泡，运行行永久滞留 ``compensating`` 非终态、同键提交与
        补偿触发恒 409。注入位＝rollback_action 本身（compensator 桩异常在
        rollback_action 内部已被四态转写消化，到不了编排层）。"""
        from fde_api.action_execution.errors import ActionExecutionError

        payload = _payload(
            fx_env["org"].id,
            fx_env["actor"].id,
            [_node("n1"), _node("n2", ("n1",), risk_level=3)],  # n2 真执行缺审批→确定性失败
        )
        real_rollback = ae_service.rollback_action

        def _exploding_rollback(*args: Any, **kwargs: Any):
            raise RuntimeError("rollback_action infrastructure exploded (non-domain)")

        monkeypatch.setattr(ae_service, "rollback_action", _exploding_rollback)
        result = orch.submit_task(
            actor=fx_env["actor"],
            payload=payload,
            whitelist_gate=AllowAllWhitelist(),
            dispatch=TaskDispatch(),
            compensator=TaskCompensator(),
        )
        monkeypatch.setattr(ae_service, "rollback_action", real_rollback)
        assert result["status"] == "compensation_failed"  # 非 compensating 滞留
        assert result["rollback"] is not None
        assert result["rollback"]["residual"] == ["n1"]  # 该节点补偿 failed 诚实登记
        assert result.get("error") is not None
        assert ActionExecutionError is not None  # 域错误类引用保活（语义自证）
        # 收口后同键复放通道可用（非终态滞留会 409 in_flight）
        replay = orch.submit_task(
            actor=fx_env["actor"],
            payload=payload,
            whitelist_gate=AllowAllWhitelist(),
            dispatch=TaskDispatch(),
            compensator=TaskCompensator(),
        )
        assert replay["status"] == result["status"]  # 终态快照重建（B7 复放语义）


# ---- R5 · 失败腿 rollback_supported 置位（DN-1 甲案） ------------------------------


class TestFailedLegRollbackSupported:
    def test_failed_execution_rollback_supported_honored(self, db_session, fx_env) -> None:
        """单步真执行失败（dispatch 非域异常）＋ ``rollback_supported=True`` →
        失败行 ``rollback_json.supported`` 置位——派发已发生的失败行（副作用
        可能已发生）补偿通道不被恒 not_supported 堵死（WP3 断线修复只覆盖
        成功腿；本钉补失败腿＝两条 finalize 腿一致）。"""
        payload = {
            "action_id": "mock.erp.query_inventory",
            "action_type": "call_api",
            "connector_id": "mock.erp",
            "method": "query_inventory",
            "params": {"sku": "SKU-RFIX"},
            "idempotency_key": "idem-ae2-rfix-" + uuid4().hex[:8],
            "org_id": fx_env["org"].id,
            "requester_id": fx_env["actor"].id,
            "dry_run": False,
            "risk_level": 1,
            "timeout_seconds": 30,
            "approval_id": None,
        }
        exploding = TaskDispatch(explode=True)
        from fde_api.action_execution.errors import ActionExecutionError

        with pytest.raises(ActionExecutionError):
            ae_service.submit_action(
                actor=fx_env["actor"],
                payload=payload,
                whitelist_gate=AllowAllWhitelist(),
                dispatch=exploding,
                rollback_supported=True,
            )
        row = db_session.scalar(
            select(ActionExecution).where(ActionExecution.idempotency_key == payload["idempotency_key"])
        )
        assert row is not None and row.status == "failed"
        assert (row.rollback_json or {}).get("supported") is True  # 失败腿置位（修复前恒 False）
