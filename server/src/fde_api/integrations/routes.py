"""项目本体绑定路由（V3.3 WP4 段 1；任务书 §5.2 API 路径）。

挂载由 FDE_ONTOLOGY_ENABLED 控制（app.py）：关闭时蓝图不注册——
原系统路由表与行为完全不变（§13 验收 8）。
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, g, jsonify, request

from fde_api.auth.decorators import require_auth
from fde_api.errors import error_response
from fde_api.integrations.service import (
    BindingError,
    approve_upgrade,
    create_binding,
    list_bindings,
    propose_upgrade,
)

ontology_bindings_blueprint = Blueprint(
    "ontology_bindings", __name__, url_prefix="/api/v1/projects"
)


def _binding_error(exc: BindingError):
    return error_response(exc.code, exc.message, exc.status)


@ontology_bindings_blueprint.get("/<project_id>/ontology-bindings")
@require_auth
def list_bindings_route(project_id: str):
    try:
        bindings = list_bindings(actor=g.current_user, project_id=project_id)
    except BindingError as exc:
        return _binding_error(exc)
    return jsonify({"data": bindings, "error": None})


@ontology_bindings_blueprint.post("/<project_id>/ontology-bindings")
@require_auth
def create_binding_route(project_id: str):
    payload: dict[str, Any] = request.get_json(silent=True) or {}
    try:
        binding = create_binding(actor=g.current_user, project_id=project_id, input=payload)
    except BindingError as exc:
        return _binding_error(exc)
    return jsonify({"data": binding, "error": None}), 201


@ontology_bindings_blueprint.post(
    "/<project_id>/ontology-bindings/<binding_id>/upgrade-proposal"
)
@require_auth
def propose_upgrade_route(project_id: str, binding_id: str):
    payload: dict[str, Any] = request.get_json(silent=True) or {}
    try:
        upgrade = propose_upgrade(
            actor=g.current_user, project_id=project_id, binding_id=binding_id, input=payload
        )
    except BindingError as exc:
        return _binding_error(exc)
    return jsonify({"data": upgrade, "error": None}), 201


@ontology_bindings_blueprint.post(
    "/<project_id>/ontology-bindings/<binding_id>/approve-upgrade/<upgrade_id>"
)
@require_auth
def approve_upgrade_route(project_id: str, binding_id: str, upgrade_id: str):
    payload: dict[str, Any] = request.get_json(silent=True) or {}
    decision = str(payload.get("decision", ""))
    try:
        result = approve_upgrade(
            actor=g.current_user,
            project_id=project_id,
            binding_id=binding_id,
            upgrade_id=upgrade_id,
            decision=decision,
        )
    except BindingError as exc:
        return _binding_error(exc)
    return jsonify({"data": result, "error": None})
