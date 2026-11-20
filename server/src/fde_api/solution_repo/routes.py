"""solution_repo 路由（AF3-WP1）：绑定 CRUD ＋ 读文件 ＋ 状态 ＋ 分支面。

POST   /api/v1/solution-repo/bindings                              绑定（四元组校验链→落行）
GET    /api/v1/solution-repo/bindings                              列表（同租户）
GET    /api/v1/solution-repo/bindings/<id>                         详情（同租户；跨租户 404 不泄露）
POST   /api/v1/solution-repo/bindings/<id>/revoke                  撤销（撤权即时生效）
GET    /api/v1/solution-repo/bindings/<id>/files?path=...          读文件（四拒＋symlink 实探＋大小上限）
GET    /api/v1/solution-repo/bindings/<id>/status                  状态（porcelain 如实回报）
POST   /api/v1/solution-repo/bindings/<id>/branches                建分支（agent_allowed branch_create）

错误信封沿 Workbench ``{data,error:{code,message,details}}``；结构保证：
**本蓝图中不存在 push/merge/远端配置端点**（D2 human_only 面永不入 agent 面；
test_af3_solution_repo::TestRouteSurface 钉路由闭集）。patch_apply 端点随
WP2 类型化 Patch adapter 落位（当前无此端点＝结构级 fail-closed）。
"""
from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request

from fde_api.auth.decorators import require_auth
from fde_api.errors import error_response
from fde_api.solution_repo import service
from fde_api.solution_repo.errors import SolutionRepoError

solution_repo_blueprint = Blueprint("solution_repo", __name__, url_prefix="/api/v1")


@solution_repo_blueprint.errorhandler(SolutionRepoError)
def service_error(error: SolutionRepoError):
    return error_response(error.code, error.message, error.status, error.details or None)


@solution_repo_blueprint.post("/solution-repo/bindings")
@require_auth
def bind_repo():
    # 评审 G1：受控基目录由服务端配置传入（绑定请求不得指定服务端围栏）。
    repo_base = current_app.config["SETTINGS"].solution_repo_base
    result = service.bind_repo(actor=g.current_user, payload=request.get_json(silent=True), repo_base=repo_base)
    return jsonify({"data": result, "error": None}), 201


@solution_repo_blueprint.get("/solution-repo/bindings")
@require_auth
def list_bindings():
    return jsonify({"data": service.list_bindings(actor=g.current_user), "error": None}), 200


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>")
@require_auth
def get_binding(binding_id: str):
    return jsonify({"data": service.get_binding(actor=g.current_user, binding_id=binding_id), "error": None}), 200


@solution_repo_blueprint.post("/solution-repo/bindings/<binding_id>/revoke")
@require_auth
def revoke_binding(binding_id: str):
    return jsonify({"data": service.revoke_binding(actor=g.current_user, binding_id=binding_id), "error": None}), 200


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/files")
@require_auth
def read_file(binding_id: str):
    rel_path = request.args.get("path", "")
    return jsonify(
        {"data": service.read_file(actor=g.current_user, binding_id=binding_id, rel_path=rel_path), "error": None}
    ), 200


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/status")
@require_auth
def get_status(binding_id: str):
    return jsonify({"data": service.get_status(actor=g.current_user, binding_id=binding_id), "error": None}), 200


@solution_repo_blueprint.post("/solution-repo/bindings/<binding_id>/branches")
@require_auth
def create_branch(binding_id: str):
    payload = request.get_json(silent=True) or {}
    return jsonify(
        {
            "data": service.create_branch(
                actor=g.current_user, binding_id=binding_id, name=payload.get("name")
            ),
            "error": None,
        }
    ), 201
