"""agents 蓝图：7 路由（goal-d4，技术实施方案 §3.1 agents 段）。

api_catalog 只收其中只读 GET（注册表/溯源/工具留痕/成本）；POST run /
handoff / retry 属人工授权写路径——AI 不得代发起、代接管、代重试（沿门禁
三路由不进目录的同一红线）。
"""

from flask import Blueprint, g, jsonify, request

from fde_api.agents import service
from fde_api.auth.decorators import require_auth
from fde_api.errors import error_response

agents_blueprint = Blueprint("agents", __name__, url_prefix="/api/v1/agents")


@agents_blueprint.errorhandler(service.AgentsServiceError)
def service_error(error):
    return error_response(error.code, error.message, error.status, error.detail or None)


def _payload():
    value = request.get_json(silent=True)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise service.AgentsServiceError("invalid_request", "请求内容必须为 JSON 对象。", 400)
    return value


def _data(value):
    return jsonify({"data": value, "error": None})


@agents_blueprint.get("")
@require_auth
def list_agents():
    """注册表（含不可用原因，P-1 静态半边）。"""
    return _data(service.list_agents(actor=g.current_user))


@agents_blueprint.post("/<agent_id>/run")
@require_auth
def start_run(agent_id):
    """触发 run（实时鉴权 + 幂等 + 预算闸 + 脱敏渲染 + 沙箱执行）。

    201 = 新 run；200 = 幂等复用既有 run（V8：不重复计费不重复落产物）。
    """
    data, status = service.start_run(actor=g.current_user, agent_id=agent_id, payload=_payload())
    return _data(data), status


@agents_blueprint.get("/runs/<run_id>")
@require_auth
def get_run(run_id):
    """溯源：run 状态/成本/降级链 + 产物指纹（V9 反查链的 run 段锚点）。"""
    return _data(service.get_run_detail(actor=g.current_user, run_id=run_id))


@agents_blueprint.post("/runs/<run_id>/handoff")
@require_auth
def handoff_run(run_id):
    """L3 转人工收口（E-2）：接管人落 run，挂 pending signoff 终审检查点。"""
    return _data(service.handoff_run(actor=g.current_user, run_id=run_id, payload=_payload()))


@agents_blueprint.post("/runs/<run_id>/retry")
@require_auth
def retry_run(run_id):
    """幂等重试：共享幂等键，≤2 次指数退避（V8/I-1 语义的显式入口）。"""
    data, status = service.retry_run(actor=g.current_user, run_id=run_id, payload=_payload())
    return _data(data), status


@agents_blueprint.get("/runs/<run_id>/tool-calls")
@require_auth
def list_tool_calls(run_id):
    """工具调用留痕（V3 前半）：?decision=denied 取越权明细。"""
    return _data(
        service.list_tool_calls(actor=g.current_user, run_id=run_id, decision=request.args.get("decision"))
    )


@agents_blueprint.get("/cost")
@require_auth
def get_cost():
    """成本明细（V10/M-1）：scope=project|seat|platform。"""
    return _data(
        service.get_cost(
            actor=g.current_user,
            scope=request.args.get("scope"),
            project_id=request.args.get("project_id"),
        )
    )
