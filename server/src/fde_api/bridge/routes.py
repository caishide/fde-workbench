"""bridge 路由（P2）：
  POST /api/v1/bridge/snapshots      宿主采集器推快照（桥令牌，非用户 JWT）
  POST /api/v1/bridge/reconcile      手动重投影（重放最近一次成功快照）
  GET  /api/v1/bridge/engagements    双轨状态一屏看（flags: vanished/unlinked/orphan/stale）
  DELETE /api/v1/bridge/engagements/<slug>  清投影（只删 bridge 行，不动真相文件）
  GET  /api/v1/bridge/status         最近同步运行 + 采集新鲜度
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from fde_api.auth.decorators import require_auth, require_minimum_role
from fde_api.bridge.runner import BridgeValidationError, require_bridge_token, validate_bundle
from fde_api.bridge.sync import (
    BridgeSyncError,
    delete_projection,
    engagement_view,
    recent_runs,
    reproject_last,
    apply_snapshot,
)
from fde_api.errors import error_response

bridge_blueprint = Blueprint("bridge", __name__, url_prefix="/api/v1/bridge")


@bridge_blueprint.post("/snapshots")
@require_bridge_token
def post_snapshot():
    body = request.get_json(silent=True)
    try:
        payload = validate_bundle(body)
    except BridgeValidationError as exc:
        return error_response("invalid_request", exc.message, 400)
    try:
        result = apply_snapshot(payload, trigger="poller")
    except BridgeSyncError as exc:
        return error_response("sync_failed", str(exc), 500)
    return jsonify({"data": result, "error": None}), 201


@bridge_blueprint.post("/reconcile")
@require_auth
@require_minimum_role("project_lead")
def reconcile():
    try:
        result = reproject_last()
    except BridgeSyncError as exc:
        return error_response("no_snapshot", str(exc), 409)
    return jsonify({"data": result, "error": None})


@bridge_blueprint.get("/engagements")
@require_auth
def list_engagements():
    return jsonify({"data": engagement_view(), "error": None})


@bridge_blueprint.delete("/engagements/<slug>")
@require_auth
@require_minimum_role("project_lead")
def remove_projection(slug: str):
    try:
        delete_projection(slug)
    except BridgeSyncError as exc:
        message = str(exc)
        status = 404 if "not found" in message else 409
        return error_response("projection_conflict" if status == 409 else "not_found", message, status)
    return jsonify({"data": {"slug": slug, "removed": True}, "error": None})


@bridge_blueprint.get("/status")
@require_auth
def bridge_status():
    return jsonify({"data": {"runs": recent_runs()}, "error": None})
