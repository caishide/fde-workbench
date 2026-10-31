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
from fde_api.dispatch.matching import match_package, override_required_level
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


@blueprint.post("/packages/<package_id>/match")
@require_auth
def match_package_route(package_id: str):
    """撮合 Top3（§4.1–§4.8；平台侧；无公示规则版本 422=降级态人工排序）。"""
    if g.current_user.role not in _PLATFORM_ROLES:
        return error_response("forbidden", "只有平台侧可执行撮合。", 403)
    session = db.session()
    try:
        with session.begin():
            result = match_package(session, actor=g.current_user, package_id=package_id)
        return jsonify({"data": result, "error": None})
    except DispatchServiceError as error:
        return _dispatch_error(error)
    finally:
        session.close()


@blueprint.post("/packages/<package_id>/required-level")
@require_auth
def override_required_level_route(package_id: str):
    """发布前人工覆盖 required_level（§4.5；必填 reason，留痕）。"""
    payload = _json_body() or {}
    if g.current_user.role not in _PLATFORM_ROLES:
        return error_response("forbidden", "只有平台侧可覆盖等级门槛。", 403)
    level, reason = payload.get("level"), payload.get("reason")
    if not isinstance(level, str) or not isinstance(reason, str) or not reason.strip():
        return error_response("invalid_request", "level 与非空 reason 必填。", 400)
    session = db.session()
    try:
        with session.begin():
            package = override_required_level(
                session,
                actor=g.current_user,
                package_id=package_id,
                level=level,
                reason=reason,
            )
            data = {
                "package_id": package.id,
                "required_level": package.required_level,
                "dispatch_status": package.dispatch_status,
            }
        return jsonify({"data": data, "error": None})
    except DispatchServiceError as error:
        return _dispatch_error(error)
    finally:
        session.close()


@blueprint.get("/profiles")
@require_auth
def list_profiles_route():
    """能力档案 + 产能看板数据（P2-1/§3.2/§6.5；平台侧——档案含他人在途计数）。"""
    if g.current_user.role not in _PLATFORM_ROLES:
        return error_response("forbidden", "只有平台侧可查看供给池档案。", 403)
    from fde_api.dispatch.models import DispatchOffer, FdeProfile
    from fde_api.workbench.models import User as UserModel
    from sqlalchemy import func

    with db.session() as session:
        in_hand = dict(
            session.execute(
                select(
                    DispatchOffer.candidate_user_id,
                    func.count(DispatchOffer.id),
                )
                .where(
                    DispatchOffer.status.in_(("offered", "accepted")),
                )
                .group_by(DispatchOffer.candidate_user_id)
            ).all()
        )
        rows = session.execute(
            select(FdeProfile, UserModel.username, UserModel.display_name)
            .join(UserModel, UserModel.id == FdeProfile.user_id)
            .order_by(FdeProfile.user_id)
        ).all()
        data = []
        for profile, username, display_name in rows:
            cap = (
                (profile.monthly_capacity_hours or 0)
                // max(profile.avg_delivery_hours or 0, 1)
                if profile.monthly_capacity_hours
                else 0
            )
            data.append(
                {
                    "user_id": profile.user_id,
                    "username": username,
                    "display_name": display_name,
                    "level": profile.level,
                    "status": profile.status,
                    "scores": {
                        "biz_cognition": profile.biz_cognition_score,
                        "scenario_eng": profile.scenario_eng_score,
                        "ai_tech": profile.ai_tech_score,
                        "delivery_assure": profile.delivery_assure_score,
                    },
                    "industry_tags": profile.industry_tags or [],
                    "module_tags": profile.module_tags or [],
                    "home_city": profile.home_city,
                    "geo_fence_km": profile.geo_fence_km,
                    "monthly_capacity_hours": profile.monthly_capacity_hours,
                    "avg_delivery_hours": profile.avg_delivery_hours,
                    "in_hand": in_hand.get(profile.user_id, 0),
                    "capacity_cap": cap,
                }
            )
        return jsonify({"data": data, "error": None})


@blueprint.get("/rules")
@require_auth
def list_rules_route():
    """规则版本与只读常数（P2-1 权重配置页；平台侧）。"""
    if g.current_user.role not in _PLATFORM_ROLES:
        return error_response("forbidden", "只有平台侧可查看规则版本。", 403)
    from fde_api.dispatch.models import DispatchRuleVersion
    from fde_api.system_configuration import DISPATCH_CONSTANTS

    with db.session() as session:
        versions = session.scalars(
            select(DispatchRuleVersion).order_by(DispatchRuleVersion.version_no)
        ).all()
        return jsonify(
            {
                "data": {
                    "versions": [
                        {
                            "id": row.id,
                            "version_no": row.version_no,
                            "status": row.status,
                            "rule_snapshot": row.rule_snapshot,
                            "published_at": row.published_at.isoformat()
                            if row.published_at
                            else None,
                            "effective_at": row.effective_at.isoformat()
                            if row.effective_at
                            else None,
                            "retired_at": row.retired_at.isoformat()
                            if row.retired_at
                            else None,
                        }
                        for row in versions
                    ],
                    "constants": dict(DISPATCH_CONSTANTS),
                },
                "error": None,
            }
        )
