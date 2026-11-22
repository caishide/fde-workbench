"""AE2-WP5 评测 runner：冻结复合任务集公开 2 任务 × 3 次独立运行 → 落盘 → 评分。

纪律对齐（54 号 §3 WP5 / 05 号 AE1 行口径沿用）：
- **3 次独立运行**：运行间重置执行台账（AE2 两表＋AE1 三表，FK 子先父后）＋
  Mock 桩（收件箱/计数器清零）——同一冻结输入逐字重放；运行独立性＝状态隔离，
  不是复放链（任务内 replay2/replay3 与运行间独立在报告分列）；
- **分母不许改**：runs 次运行全部入记录入报告——S 层拒绝折叠为**契约形态**
  的诚实 failed TaskRunResult（error.code 保留；基础设施失败入 note 归因）；
- **字面 ID 世界**：沿 AE1 先例（占位串＝真实主键）——复用
  ``ae_eval.runner.provision_pinned_world``（AE1 模块只读复用零改动）；
- **审批运行时绑定**：``<runtime-binding>`` 占位节点每轮经审批面预签
  （四眼闸复核人≠发起人沿 AE1 P15；params 全字面量故指纹可预计算——ref 节点
  不涉审批）；
- **评分器只消费落盘记录**：runner 只产记录；判定一律由调用方落盘后经
  ``ae2_scorer.score_records`` 消费；
- **生产等价装配**：白名单门＋真 HTTP dispatch（沿 AE1 ``_live_gates`` 装置级
  快照端口注入语义）；编排器经 ``task_orchestrator.submit_task`` 生产函数提交。
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text

import _ae_mock_stack as _mock_stack_module
from ae_eval.records import RunRecord
from ae_eval.runner import (
    ORG_ID,
    PROJECT_ID,
    USER_ID,
    _live_gates,
    _make_email_approval,
    provision_pinned_world,
)
from fde_api.action_execution.errors import ActionExecutionError
from fde_api.action_execution.task_orchestrator import submit_task

__all__ = [
    "AE2_RUNS",
    "load_public_tasks",
    "reset_ae2_ledger",
    "run_public_eval",
]

SERVER_ROOT = Path(__file__).resolve().parents[2]
AE2_TASKSET_PATH = Path(__file__).resolve().parent / "taskset_ae2_v1.json"

#: 3 次独立运行（54 号 §5.1：每任务 3 次独立运行）。
AE2_RUNS = 3

RUNTIME_BINDING_PREFIX = "<runtime-binding"


def load_public_tasks() -> list[dict[str, Any]]:
    """公开集 2 复合任务（冻结任务集 byte 一致副本；run_input 逐字即场景输入）。"""
    payload = json.loads(AE2_TASKSET_PATH.read_text(encoding="utf-8"))
    tasks = [task for task in payload["tasks"] if str(task["id"]).startswith("T5-0")]
    if [str(task["id"]) for task in tasks] != ["T5-001", "T5-002"]:
        raise ValueError("AE2 公开集任务清单漂移（冻结件 v1 应恰为 T5-001/T5-002）")
    return tasks


def reset_ae2_ledger(db_session: Any) -> None:
    """运行隔离装置（不触生产 append-only 语义——沿 AE1 同款口径）。

    FK 子先父后：action_task_nodes → action_task_runs → action_execution_logs
    → action_compensations → action_executions。"""
    db_session.execute(text("DELETE FROM action_task_nodes"))
    db_session.execute(text("DELETE FROM action_task_runs"))
    db_session.execute(text("DELETE FROM action_execution_logs"))
    db_session.execute(text("DELETE FROM action_compensations"))
    db_session.execute(text("DELETE FROM action_executions"))
    db_session.commit()


def _resolve_literal_params(params: dict[str, Any]) -> dict[str, Any]:
    """审批预签指纹用的 params 解析（占位节点 params 全字面量——设计备注 §7.4）。"""
    return {
        str(name): (value.get("value") if isinstance(value, dict) and value.get("kind") == "literal" else None)
        for name, value in params.items()
    }


def _bind_runtime_approvals(db_session: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """把定义里 ``<runtime-binding>`` 占位的 approval_id 每轮经审批面预签。

    指纹＝该节点解析后 params 的 canonical sha256（占位节点 params 全字面量
    ——空 outputs 解析即实材）；审批单绑定面沿 U1（capability=action_
    execution.invoke／tool_name=action_execution.execute／复核人≠发起人）。
    definition 对象深拷贝后逐字替换（冻结输入本体不被改写）。"""
    import copy

    request = copy.deepcopy(payload)
    for node in request["definition"]["nodes"]:
        action = node["action"]
        approval_id = action.get("approval_id")
        if not (isinstance(approval_id, str) and approval_id.startswith(RUNTIME_BINDING_PREFIX)):
            continue
        resolved = _resolve_literal_params(action["params"])
        action["approval_id"] = _make_email_approval(
            db_session, resolved, int(action["risk_level"])
        )
    return request


def _snapshot_state(stack: _mock_stack_module.MockStack) -> dict[str, Any]:
    """外部状态快照（mailbox 条数／工作流草稿数——相对锚跨轮成立）。"""
    from sqlalchemy import func, select

    from fde_api.extensions import db as _db
    from fde_api.workflows.models import WorkflowDefinition

    items = _mailbox_items(stack)
    session = _db.session()  # db.session() 非 scoped——同一变量＋用完 close（WP2 教训）
    try:
        wf_count = int(session.scalar(select(func.count()).select_from(WorkflowDefinition)) or 0)
    finally:
        session.close()
    return {"mailbox_count": len(items), "wf_count": wf_count}


def _mailbox_items(stack: _mock_stack_module.MockStack) -> list[dict[str, Any]]:
    import urllib.request

    with urllib.request.urlopen(_mailbox_url(stack), timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return list(payload.get("items") or [])


def _mailbox_url(stack: _mock_stack_module.MockStack) -> str:
    return f"http://127.0.0.1:{stack.email_port}/mock-email/inbox"


def _submit_task_attempt(actor: Any, payload: dict[str, Any], gate: Any, dispatch: Any) -> dict[str, Any]:
    """单次整图提交——S 层拒绝折叠为**契约形态**的诚实 failed TaskRunResult
    （沿 AE1 ``_submit_attempt`` 同款纪律：分母保留、归因入 note、审计零伪造）。
    运行期节点失败不冒泡（编排器诚实收口终态）——此处只防提交期拒绝。"""
    try:
        return submit_task(
            actor=actor, payload=payload, whitelist_gate=gate, dispatch=dispatch, compensator=None
        )
    except ActionExecutionError as exc:
        return {
            "execution_id": f"not-issued-{uuid.uuid4().hex[:8]}",
            "idempotency_key": str(payload.get("idempotency_key")),
            "status": "failed",
            "nodes": [],
            "error": {
                "code": exc.code,
                "message": exc.message,
                "retryable": False,
                **({"details": dict(exc.details or {})} if exc.details else {}),
            },
            "rollback": None,
        }
    except Exception as exc:  # 防御：基础设施异常（契约形态兜底；Q8 映射闭集内码）
        return {
            "execution_id": f"not-issued-{uuid.uuid4().hex[:8]}",
            "idempotency_key": str(payload.get("idempotency_key")),
            "status": "failed",
            "nodes": [],
            "error": {
                "code": "tool_not_allowed",
                "message": "基础设施失败（闭集映射；details.reason 归因）。",
                "retryable": True,
                "details": {"reason": type(exc).__name__},
            },
            "rollback": None,
        }


def _run_task_once(
    db_session: Any,
    actor: Any,
    gate: Any,
    dispatch: Any,
    stack: _mock_stack_module.MockStack,
    task: dict[str, Any],
    run_index: int,
) -> RunRecord:
    task_id = str(task["id"])
    payload = _bind_runtime_approvals(db_session, dict(task["run_input"]))
    stack.reset()  # 任务间亦重置桩——零重复副作用锚按任务独立判定（任务集 run_discipline）
    before = _snapshot_state(stack)
    attempts: dict[str, dict[str, Any]] = {"first": _submit_task_attempt(actor, payload, gate, dispatch)}
    for slot in ("replay2", "replay3"):
        attempts[slot] = _submit_task_attempt(actor, payload, gate, dispatch)
    # run_cost＝harness 只读投影运行行 cost_json（TaskRunResult 契约不含 cost
    # 字段——运行级成本登记于库，x-audit-and-cost 口径）；各槽同一运行行 → 同值。
    run_cost = _read_run_cost(db_session, str(attempts["first"].get("execution_id") or ""))
    for slot in ("first", "replay2", "replay3"):
        if attempts[slot].get("execution_id") and not attempts[slot].get("execution_id", "").startswith("not-issued"):
            attempts[slot]["run_cost"] = dict(run_cost)
            # 评审 F5：同步写 cost 键——AE1 records 派生面读 attempts.*.cost
            # （观测包络登记 task.total_cost_usd＝Σ attempts.*.run_cost.estimated_usd
            # 的实际派生链经 cost 键；run_cost 为装置自读投影双登记）。
            attempts[slot]["cost"] = {"estimated_usd": float(run_cost.get("estimated_usd") or 0.0)}
    after = _snapshot_state(stack)
    note = ""
    for slot_name in ("first", "replay2", "replay3"):
        slot_error = (attempts.get(slot_name) or {}).get("error") or {}
        if isinstance(slot_error, dict) and slot_error.get("retryable") is True:
            reason = (slot_error.get("details") or {}).get("reason")
            tag = f"infrastructure_error: {reason}" if reason else "infrastructure_error"
            note = f"{note} {slot_name}:{tag}".strip()  # 评审：逐槽归因（此前只看 first 槽）
    return RunRecord(
        task_id=task_id,
        run_index=run_index,
        attempts=attempts,
        external_state={
            "mailbox_count": after["mailbox_count"],
            "workflow_definitions_added": after["wf_count"] - before["wf_count"],
        },
        note=note,
    )


def _read_run_cost(db_session: Any, run_id: str) -> dict[str, Any]:
    """按运行 id 只读查询运行行成本聚合（零明文聚合值）。"""
    from sqlalchemy import select

    from fde_api.action_execution.models import ActionTaskRun

    row = db_session.scalar(select(ActionTaskRun).where(ActionTaskRun.id == run_id))
    return dict(row.cost_json or {}) if row is not None else {}


def run_public_eval(
    *,
    db_session: Any,
    actor: Any,
    test_settings: Any,
    stack: _mock_stack_module.MockStack,
    wb_port: int,
    runs: int = AE2_RUNS,
) -> list[RunRecord]:
    """公开集 2 复合任务 × runs 次独立运行 → RunRecord 列表（调用方落盘后交评分器）。

    每轮运行前：清执行台账（AE2 两表＋AE1 三表）＋重置 Mock 桩（收件箱清零）。
    ORG_ID/PROJECT_ID/USER_ID 自 AE1 runner 复用（字面 ID 世界单一事实源）。"""
    tasks = load_public_tasks()
    token = _issue_token(actor, test_settings)
    gate, dispatch = _live_gates(
        token,
        wb_port=wb_port,
        erp_port=stack.erp_port,
        email_port=stack.email_port,
    )
    records: list[RunRecord] = []
    for run_index in range(1, runs + 1):
        reset_ae2_ledger(db_session)
        stack.reset()
        for task in tasks:
            records.append(_run_task_once(db_session, actor, gate, dispatch, stack, task, run_index))
    return records


def _issue_token(actor: Any, test_settings: Any) -> str:
    from fde_api.auth.tokens import issue_access_token

    return issue_access_token(actor, test_settings)


# 复用面显式登记（审计锚：本模块对 AE1 评测面为零改动只读复用）
_ = (ORG_ID, PROJECT_ID, USER_ID)
