"""action_execution 路由（AE1-WP1）：提交执行 + 执行详情。

POST /api/v1/action-executions             提交单步动作（幂等键必填；契约 U1
     ``ActionExecutionRequest`` 形态；默认门＝白名单 fail-closed ＋ 未接线
     派发 fail-closed——WP3 接白名单加载器与连接器适配）
POST /api/v1/action-executions/<id>/rollback   回滚（契约 U1 ``x-rollback``：
     四态诚实失败——``rolled_back|not_supported|failed|noop`` 均以 HTTP 200
     ＋ ``data.error`` 对象返回〔exceptions_note：诚实失败态不冒充成功〕；
     幂等——同 execution_id 重复调用复用既有批次，零重复补偿副作用）
GET  /api/v1/action-executions/<id>        执行详情（同租户；跨租户 404 不泄露）

AE2 编排路由（WP4，additive——既有三路由语义零改动，禁改清单第 10 项）：
POST /api/v1/action-tasks                   提交多步任务（TaskRequest → TaskRunResult；
     复放同载荷同状态码）；白名单提交期预检（A5/A6 静态拒）
GET  /api/v1/action-tasks/<run_id>          运行详情（TaskRunResult 全量重建；跨租户 404）
GET  /api/v1/action-tasks/<run_id>/nodes    节点清单（节点行＝节点序列权威载体；跨租户 404）
POST /api/v1/action-tasks/<run_id>/compensation  触发补偿（B11 幂等；失败运行；成功运行 422）

错误信封沿 Workbench ``{data:null,error:{code,message,details}}``（契约
x-error-codes.http_status_note：AE 以 Workbench 侧为准）。
"""
from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, g, jsonify, request

from fde_api.action_execution import service, task_orchestrator
from fde_api.action_execution.connectors import ConnectorWhitelist, HttpDispatch, load_whitelist
from fde_api.action_execution.errors import ActionExecutionError
from fde_api.auth.decorators import require_auth
from fde_api.auth.tokens import issue_access_token
from fde_api.errors import error_response

action_execution_blueprint = Blueprint("action_execution", __name__, url_prefix="/api/v1")

# WP3 生产装配：白名单门＝仓内快照只读加载（加载期固化，运行时不可变——
# 禁改清单第 5/7 项：缺失/损坏 fail-closed；惰性构造＝首次请求时加载并
# 缓存，快照缺失时在请求面 403 而非蓝本导入崩溃）。
# 评审 P10：快照同源缓存——门与 SSRF 预检共用同一份深拷贝快照，杜绝
# 「门缓存 vs 磁盘现读」双源 TOCTOU 与每请求重读盘。
_WHITELIST_GATE: ConnectorWhitelist | None = None
_WHITELIST_SNAPSHOT: dict | None = None


def _whitelist_snapshot() -> dict:
    global _WHITELIST_SNAPSHOT
    if _WHITELIST_SNAPSHOT is None:
        _WHITELIST_SNAPSHOT = load_whitelist()
    return _WHITELIST_SNAPSHOT


def _whitelist_gate() -> ConnectorWhitelist:
    global _WHITELIST_GATE
    if _WHITELIST_GATE is None:
        _WHITELIST_GATE = ConnectorWhitelist(_whitelist_snapshot())
    return _WHITELIST_GATE


@action_execution_blueprint.errorhandler(ActionExecutionError)
def service_error(error: ActionExecutionError):
    return error_response(error.code, error.message, error.status, error.details or None)


@action_execution_blueprint.post("/action-executions")
@require_auth
def submit_action():
    """提交单步动作执行：契约 U1 ``ActionExecutionRequest`` → ``ActionExecutionResult``。

    成功（含复放 ``replayed``）→ 201 ``{data: result, error: null}``（复放返回
    首次执行的载荷与状态码——U1 x-idempotency.same_key_same_body「HTTP 状态码
    与响应体逐字一致」读法；域内 status=replayed 语义见契约 $defs if/then）。
    """
    payload = request.get_json(silent=True)
    gate = _whitelist_gate()
    dispatch = HttpDispatch(
        whitelist=gate,
        token=issue_access_token(g.current_user, current_app.config["SETTINGS"]),
        whitelist_snapshot=_whitelist_snapshot(),
        timeout_seconds=300.0,  # 评审 P8：服务端超时上限＝契约 timeout_seconds 域上界
    )
    result = service.submit_action(actor=g.current_user, payload=payload, whitelist_gate=gate, dispatch=dispatch)
    return jsonify({"data": result, "error": None}), 201


@action_execution_blueprint.post("/action-executions/<execution_id>/rollback")
@require_auth
def rollback_execution(execution_id: str):
    """回滚（U1 ``x-rollback``）：body ``{reason?}`` → ``RollbackResult``。

    四态均 HTTP 200（诚实失败态以 ``data.error`` 对象承载，不冒充成功；
    ``not_found`` 404 仍走信封）。幂等：同 execution_id 重复调用复用既有批次。
    补偿器生产装配＝``NO_COMPENSATOR``（fail-closed → ``not_supported``）；
    真实补偿器随 WP3 连接器适配按 kind 注册。
    """
    payload = request.get_json(silent=True) or {}
    reason = payload.get("reason")
    if isinstance(reason, str) and len(reason) > 500:
        # U1 x-rollback.exceptions：reason 超长 → 422 validation_failed（评审 P17，
        # 不让超长串直达 varchar(500) 列炸 DataError）
        raise ActionExecutionError("validation_failed", "回滚原因超长（≤500 字符）。")
    result = service.rollback_action(
        actor=g.current_user, execution_id=execution_id, reason=reason if isinstance(reason, str) else None
    )
    return jsonify({"data": result, "error": None}), 200


@action_execution_blueprint.get("/action-executions/<execution_id>")
@require_auth
def get_execution(execution_id: str):
    payload = service.get_execution(actor=g.current_user, execution_id=execution_id)
    return jsonify({"data": payload, "error": None}), 200


# ---- AE2 编排路由（WP4；additive——新路由不改既有三路由语义） ------------------


def _wired_orchestrator() -> dict[str, Any]:
    """编排面生产装配（每请求构建；测试经 monkeypatch 本函数注入桩——
    路由本体与生产装配路径同构验证，不另开旁路）。

    - 白名单门＝单例缓存（与单步面同源快照——P10 双源 TOCTOU 口径沿用）；
    - 派发＝带本请求令牌的 HttpDispatch（同单步提交面装配）；
    - 补偿器＝缺省 None（→ ``NO_COMPENSATOR`` fail-closed，沿 U1 回滚面）；
      真实补偿器注册随 AE3 连接器适配。"""
    gate = _whitelist_gate()
    dispatch = HttpDispatch(
        whitelist=gate,
        token=issue_access_token(g.current_user, current_app.config["SETTINGS"]),
        whitelist_snapshot=_whitelist_snapshot(),
        timeout_seconds=300.0,  # P8：服务端超时上限＝契约 timeout_seconds 域上界
    )
    return {"whitelist_gate": gate, "dispatch": dispatch, "compensator": None}


@action_execution_blueprint.post("/action-tasks")
@require_auth
def submit_task():
    """提交多步任务：编排契约 ``TaskRequest`` → ``TaskRunResult``。

    成功（含复放）→ 201 ``{data, error: null}``——复放沿单步提交面口径
    （同载荷同状态码同响应体逐字，B7）。提交期静态拒（图结构/白名单预检/
    租户/档位/幂等）以 ``ActionExecutionError`` 冒泡至蓝本 errorhandler 转
    ``{data:null,error:{...}}``；拒绝零副作用（零外呼零落库）。"""
    payload = request.get_json(silent=True)
    wiring = _wired_orchestrator()
    result = task_orchestrator.submit_task(
        actor=g.current_user,
        payload=payload,
        whitelist_gate=wiring["whitelist_gate"],
        dispatch=wiring["dispatch"],
        compensator=wiring["compensator"],
    )
    return jsonify({"data": result, "error": None}), 201


@action_execution_blueprint.get("/action-tasks/<run_id>")
@require_auth
def get_task(run_id: str):
    """运行详情：TaskRunResult 全量重建（跨租户 404 不泄露）。"""
    result = task_orchestrator.get_task_result(actor=g.current_user, run_id=run_id)
    return jsonify({"data": result, "error": None}), 200


@action_execution_blueprint.get("/action-tasks/<run_id>/nodes")
@require_auth
def get_task_nodes(run_id: str):
    """节点清单（WP2 ``list_task_nodes`` 服务面出口；节点行＝节点序列权威载体）。"""
    nodes = service.list_task_nodes(actor=g.current_user, execution_id=run_id)
    return jsonify({"data": nodes, "error": None}), 200


@action_execution_blueprint.post("/action-tasks/<run_id>/compensation")
@require_auth
def compensate_task_route(run_id: str):
    """触发补偿（B11 幂等）：终态运行快照短路重建零新副作用；失败运行补跑
    未登记补偿节点；成功运行 422（状态机不含 succeeded→compensating 边）。"""
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        raise ActionExecutionError("validation_failed", "请求体须为 JSON 对象。")
    reason = payload.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason) > 500):
        raise ActionExecutionError("validation_failed", "补偿原因超长（≤500 字符）。")
    wiring = _wired_orchestrator()
    result = task_orchestrator.compensate_task(
        actor=g.current_user,
        execution_id=run_id,
        compensator=wiring["compensator"],
        reason=reason if isinstance(reason, str) else None,
    )
    return jsonify({"data": result, "error": None}), 200
