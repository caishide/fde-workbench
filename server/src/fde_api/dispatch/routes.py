"""dispatch 蓝图：交付包读/发布/撤回/接单（设计 §8.6/§9.2，P0-1/P0-2）。

§9.2 纪律③：每个读入口先过 require_package_access（无授权 404，不泄露
包存在性）；管理动作（建/发/撤）限平台侧。响应体只走白名单 schema
（access.serialize_package_whitelist），金额字段唯一例外=交付方席位份额。
"""

from __future__ import annotations

from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from fde_api.auth.decorators import require_auth
from fde_api.dispatch.access import (
    has_package_access,
    list_accessible_package_ids,
    require_package_access,
    serialize_package_whitelist,
)
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import DeliveryPackage
from fde_api.dispatch.offer_service import (
    accept_offer_and_handover,
    claim_package,
    create_assign_offers,
    decline_offer,
)
from fde_api.dispatch.packages import (
    accept_package,
    create_package,
    publish_package,
    transition_package,
)
from fde_api.errors import error_response
from fde_api.extensions import db
from fde_api.solutions.models import ProjectSolution
from fde_api.workbench.models import Project

blueprint = Blueprint("dispatch", __name__, url_prefix="/api/v1/dispatch")

_PLATFORM_ROLES = ("admin", "project_lead")


def _dispatch_error(error: DispatchServiceError):
    return error_response(error.code, error.message, error.status)


def _json_body() -> dict | None:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _whitelist_payload(session, package: DeliveryPackage) -> dict:
    solution = session.get(ProjectSolution, package.solution_id)
    project = session.get(Project, package.project_id)
    return serialize_package_whitelist(package, solution=solution, project=project)


@blueprint.get("/packages")
@require_auth
def list_packages_route():
    with db.session() as session:
        ids = list_accessible_package_ids(session, user=g.current_user)
        packages = (
            session.scalars(
                select(DeliveryPackage).where(DeliveryPackage.id.in_(ids))
            ).all()
            if ids
            else []
        )
        return jsonify(
            {
                "data": [_whitelist_payload(session, package) for package in packages],
                "error": None,
            }
        )


@blueprint.get("/packages/<package_id>")
@require_auth
def get_package_route(package_id: str):
    with db.session() as session:
        try:
            package = require_package_access(
                session, user=g.current_user, package_id=package_id
            )
        except DispatchServiceError as error:
            return _dispatch_error(error)
        return jsonify({"data": _whitelist_payload(session, package), "error": None})


@blueprint.post("/packages")
@require_auth
def create_package_route():
    payload = _json_body()
    if not payload or not {"solution_id", "quote_id"} <= set(payload):
        return error_response("invalid_request", "solution_id 与 quote_id 必填。", 400)
    onsite_visits = payload.get("onsite_visits")
    if onsite_visits is not None and (
        type(onsite_visits) is not int or onsite_visits < 0
    ):
        return error_response("invalid_request", "onsite_visits 必须是非负整数。", 400)
    session = db.session()
    try:
        with session.begin():
            package = create_package(
                session,
                actor=g.current_user,
                solution_id=str(payload["solution_id"]),
                quote_id=str(payload["quote_id"]),
                dispatch_mode=str(payload.get("dispatch_mode") or "assign"),
                onsite_visits=onsite_visits,
            )
            result = _whitelist_payload(session, package)
        return jsonify({"data": result, "error": None}), 201
    except DispatchServiceError as error:
        return _dispatch_error(error)
    finally:
        session.close()


@blueprint.post("/packages/<package_id>/publish")
@require_auth
def publish_package_route(package_id: str):
    payload = _json_body() or {}
    candidates_raw = payload.get("candidate_user_ids") or []
    if not isinstance(candidates_raw, list) or not all(
        isinstance(item, str) for item in candidates_raw
    ):
        return error_response(
            "invalid_request", "candidate_user_ids 必须是字符串数组。", 400
        )
    session = db.session()
    try:
        with session.begin():
            package = publish_package(
                session,
                actor=g.current_user,
                package_id=package_id,
                candidate_user_ids=tuple(candidates_raw),
            )
            result = _whitelist_payload(session, package)
        return jsonify({"data": result, "error": None})
    except DispatchServiceError as error:
        return _dispatch_error(error)
    finally:
        session.close()


@blueprint.post("/packages/<package_id>/withdraw")
@require_auth
def withdraw_package_route(package_id: str):
    if g.current_user.role not in _PLATFORM_ROLES:
        return error_response("forbidden", "只有平台侧可撤回交付包。", 403)
    session = db.session()
    try:
        with session.begin():
            package = transition_package(
                session, actor=g.current_user, package_id=package_id, action="withdraw"
            )
            result = _whitelist_payload(session, package)
        return jsonify({"data": result, "error": None})
    except DispatchServiceError as error:
        return _dispatch_error(error)
    finally:
        session.close()


@blueprint.post("/packages/<package_id>/accept")
@require_auth
def accept_package_route(package_id: str):
    payload = _json_body()
    delivery_user_id = payload.get("delivery_user_id") if payload else None
    if not isinstance(delivery_user_id, str) or not delivery_user_id:
        return error_response("invalid_request", "delivery_user_id 必填。", 400)
    actor = g.current_user
    if actor.role not in _PLATFORM_ROLES:
        # 交付方本人接单：须是被指派人且持该包未撤销 delivery 授权（§9.2）
        if actor.id != delivery_user_id:
            return error_response(
                "forbidden", "只有平台侧或被指派的交付方本人可接单。", 403
            )
        with db.session() as session:
            if not has_package_access(
                session, user=actor, package_id=package_id, roles=("delivery",)
            ):
                return error_response(
                    "package_not_found", "交付包不存在或无权访问。", 404
                )
    try:
        result = accept_package(
            actor=actor, package_id=package_id, delivery_user_id=delivery_user_id
        )
    except DispatchServiceError as error:
        return _dispatch_error(error)
    return jsonify({"data": result, "error": None})


@blueprint.post("/packages/<package_id>/offers")
@require_auth
def create_offers_route(package_id: str):
    payload = _json_body() or {}
    if g.current_user.role not in _PLATFORM_ROLES:
        return error_response("forbidden", "只有平台侧可指派。", 403)
    candidates_raw = payload.get("candidate_user_ids") or []
    if not isinstance(candidates_raw, list) or not candidates_raw or not all(
        isinstance(item, str) for item in candidates_raw
    ):
        return error_response(
            "invalid_request", "candidate_user_ids 必须是非空字符串数组。", 400
        )
    session = db.session()
    try:
        with session.begin():
            offers = create_assign_offers(
                session,
                actor=g.current_user,
                package_id=package_id,
                candidate_user_ids=tuple(candidates_raw),
            )
            data = [
                {
                    "offer_id": offer.id,
                    "candidate_user_id": offer.candidate_user_id,
                    "dispatch_round": offer.dispatch_round,
                    "status": offer.status,
                    "version": offer.version,
                }
                for offer in offers
            ]
        return jsonify({"data": data, "error": None}), 201
    except DispatchServiceError as error:
        return _dispatch_error(error)
    finally:
        session.close()


@blueprint.post("/offers/<offer_id>/accept")
@require_auth
def accept_offer_route(offer_id: str):
    payload = _json_body() or {}
    expected_version = payload.get("version")
    if type(expected_version) is not int:
        return error_response("invalid_request", "version（乐观锁）必填。", 400)
    try:
        result = accept_offer_and_handover(
            actor=g.current_user, offer_id=offer_id, expected_version=expected_version
        )
    except DispatchServiceError as error:
        return _dispatch_error(error)
    return jsonify({"data": result, "error": None})


@blueprint.post("/offers/<offer_id>/decline")
@require_auth
def decline_offer_route(offer_id: str):
    payload = _json_body() or {}
    expected_version = payload.get("version")
    if type(expected_version) is not int:
        return error_response("invalid_request", "version（乐观锁）必填。", 400)
    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        return error_response("invalid_request", "reason 必须是字符串。", 400)
    session = db.session()
    try:
        with session.begin():
            offer = decline_offer(
                session,
                actor=g.current_user,
                offer_id=offer_id,
                expected_version=expected_version,
                reason=reason,
            )
            data = {
                "offer_id": offer.id,
                "status": offer.status,
                "version": offer.version,
            }
        return jsonify({"data": data, "error": None})
    except DispatchServiceError as error:
        return _dispatch_error(error)
    finally:
        session.close()


@blueprint.post("/packages/<package_id>/claim")
@require_auth
def claim_package_route(package_id: str):
    session = db.session()
    try:
        with session.begin():
            offer = claim_package(session, actor=g.current_user, package_id=package_id)
            data = {
                "offer_id": offer.id,
                "candidate_user_id": offer.candidate_user_id,
                "dispatch_round": offer.dispatch_round,
                "status": offer.status,
                "version": offer.version,
            }
        return jsonify({"data": data, "error": None}), 201
    except DispatchServiceError as error:
        return _dispatch_error(error)
    finally:
        session.close()
