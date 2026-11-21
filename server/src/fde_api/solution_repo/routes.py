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


# ---- AF3-WP2：类型化 Patch 应用＋diff/log 读面 ----------------------------------


@solution_repo_blueprint.post("/solution-repo/bindings/<binding_id>/patches")
@require_auth
def apply_patch(binding_id: str):
    """patch_apply（白名单 v2 agent_allowed）：PatchPlan 键集精确→原子应用＋
    受控 commit；幂等同键重放＝复放首次结果（200 replayed）。"""
    result = service.apply_patch(
        actor=g.current_user, binding_id=binding_id, payload=request.get_json(silent=True)
    )
    # applied（新应用）＝201；replayed/failed 复放＝200（AE1 同键同态口径——
    # failed 复放按原失败快照返回，不冒充新成功）。
    status = 201 if result.get("status") == "applied" else 200
    return jsonify({"data": result, "error": None}), status


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/patches/<patch_id>")
@require_auth
def get_patch(binding_id: str, patch_id: str):
    return jsonify(
        {"data": service.get_patch(actor=g.current_user, binding_id=binding_id, patch_id=patch_id), "error": None}
    ), 200


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/changes")
@require_auth
def get_changes(binding_id: str):
    return jsonify({"data": service.get_changes(actor=g.current_user, binding_id=binding_id), "error": None}), 200


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/commits")
@require_auth
def get_commit_log(binding_id: str):
    return jsonify({"data": service.get_commit_log(actor=g.current_user, binding_id=binding_id), "error": None}), 200


# ---- AF3-WP3：固定受信任 CI bundle -----------------------------------------------


@solution_repo_blueprint.post("/solution-repo/bindings/<binding_id>/ci/runs")
@require_auth
def run_ci(binding_id: str):
    """run_ci（白名单 v3 agent_allowed）：受信任 bundle 执行＋RepoCIRun 落行。"""
    result = service.run_ci(
        actor=g.current_user, binding_id=binding_id, payload=request.get_json(silent=True)
    )
    return jsonify({"data": result, "error": None}), 201


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/ci/runs")
@require_auth
def get_ci_runs(binding_id: str):
    return jsonify({"data": service.get_ci_runs(actor=g.current_user, binding_id=binding_id), "error": None}), 200


# ---- AF3-WP4：修复闭环（correction_loop） ----------------------------------------


@solution_repo_blueprint.post("/solution-repo/bindings/<binding_id>/corrections")
@require_auth
def start_correction(binding_id: str):
    """修复闭环（AF1① 预算内收敛）：失败 run 锚→修复 patch→同 bundle 复测。"""
    result = service.start_correction(
        actor=g.current_user, binding_id=binding_id, payload=request.get_json(silent=True)
    )
    return jsonify({"data": result, "error": None}), 201


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/corrections")
@require_auth
def get_corrections(binding_id: str):
    return jsonify({"data": service.get_corrections(actor=g.current_user, binding_id=binding_id), "error": None}), 200


# ---- AF3-WP5：证据绑定与审计台账聚合 -----------------------------------------------


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/evidence")
@require_auth
def get_evidence(binding_id: str):
    return jsonify({"data": service.get_evidence(actor=g.current_user, binding_id=binding_id), "error": None}), 200


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/evidence/file")
@require_auth
def get_evidence_file(binding_id: str):
    return jsonify(
        {
            "data": service.get_evidence_file(
                actor=g.current_user,
                binding_id=binding_id,
                rel_path=request.args.get("path", ""),
                commit=request.args.get("commit", ""),
            ),
            "error": None,
        }
    ), 200


@solution_repo_blueprint.get("/solution-repo/bindings/<binding_id>/audit")
@require_auth
def get_audit_ledger(binding_id: str):
    return jsonify({"data": service.get_audit_ledger(actor=g.current_user, binding_id=binding_id), "error": None}), 200
