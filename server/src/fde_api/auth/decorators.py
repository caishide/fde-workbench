from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

import jwt
from flask import current_app, g, request

from fde_api.auth.models import InvalidRoleError, User, VALID_ROLES
from fde_api.auth.permissions import role_at_least
from fde_api.config import Settings
from fde_api.errors import error_response
from fde_api.extensions import db


ViewFunction = TypeVar("ViewFunction", bound=Callable[..., Any])
FORCED_CHANGE_ALLOWED_ROUTES = frozenset(
    {
        ("GET", "/api/v1/auth/me"),
        ("POST", "/api/v1/auth/change-password"),
        ("POST", "/api/v1/auth/verify-password"),
    }
)


def require_auth(view: ViewFunction) -> ViewFunction:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        user, claims, failure = _current_request_identity()
        if failure is not None:
            return failure
        assert user is not None
        assert claims is not None

        if (
            claims.get("pwd") is not True or user.must_change_password
        ) and (request.method, request.path) not in FORCED_CHANGE_ALLOWED_ROUTES:
            return error_response(
                "password_change_required",
                "Password change is required before accessing this resource.",
                403,
            )

        g.current_user = user
        g.access_token_claims = claims
        # M3a：org 上下文注入（**读库值**，非令牌 claim——令牌是 15 分钟快照，
        # 授权判定一律以 users.org_id 为准，规格 §4）。
        g.current_user_org_id = user.org_id
        return view(*args, **kwargs)

    return cast(ViewFunction, wrapped)


def require_role(*roles: str) -> Callable[[ViewFunction], ViewFunction]:
    invalid_roles = set(roles) - VALID_ROLES
    if invalid_roles:
        invalid_role = sorted(invalid_roles)[0]
        raise InvalidRoleError(f"unsupported role: {invalid_role}")

    def decorator(view: ViewFunction) -> ViewFunction:
        @require_auth
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            if g.current_user.role not in roles:
                return error_response(
                    "forbidden", "You do not have permission to access this resource.", 403
                )
            return view(*args, **kwargs)

        return cast(ViewFunction, wrapped)

    return decorator


def require_minimum_role(required: str) -> Callable[[ViewFunction], ViewFunction]:
    if required not in VALID_ROLES:
        raise InvalidRoleError(f"unsupported role: {required}")

    def decorator(view: ViewFunction) -> ViewFunction:
        @require_auth
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any):
            if not role_at_least(g.current_user.role, required):
                return error_response(
                    "forbidden", "You do not have permission to access this resource.", 403
                )
            return view(*args, **kwargs)

        return cast(ViewFunction, wrapped)

    return decorator


def _current_request_identity():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, raw_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not raw_token.strip():
        return None, None, _invalid_access_response()

    settings: Settings = current_app.config["SETTINGS"]
    try:
        claims = jwt.decode(
            raw_token.strip(),
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer="fde-workbench",
            # M3a：7 个既有 claim 必填；org_id 走**在场性**显式校验（见下）——
            # PyJWT 的 require 判定是「payload.get(claim) is None ⇒ 缺 claim」，
            # 而平台身份的 org_id 合法值就是 null ⇒ 不能进 require 列表。
            options={"require": ["sub", "role", "pwd", "ver", "iat", "exp", "iss"]},
        )
    except jwt.PyJWTError:
        return None, None, _invalid_access_response()

    if (
        not isinstance(claims.get("sub"), str)
        or not isinstance(claims.get("pwd"), bool)
        or type(claims.get("ver")) is not int
    ):
        return None, None, _invalid_access_response()

    # M3a：org_id claim 必须**在场**——缺该 claim 的是隔离改造前的旧令牌，
    # 一律 401（fail-closed：「缺 claim」若按平台身份放行＝陈旧令牌越权）；
    # 在场且为 null ＝平台身份（§11-8 拍板语义），合法。
    if "org_id" not in claims:
        return None, None, _invalid_access_response()
    if claims["org_id"] is not None and not isinstance(claims["org_id"], str):
        return None, None, _invalid_access_response()

    session = db.session()
    try:
        user = session.get(User, claims["sub"])
    finally:
        session.close()
    if user is None:
        return None, None, _invalid_access_response()
    if claims["ver"] != user.auth_version:
        return None, None, _invalid_access_response()
    if not user.is_active:
        return (
            None,
            None,
            error_response("account_inactive", "This account is inactive.", 403),
        )
    return user, claims, None


def _invalid_access_response():
    return error_response(
        "access_token_invalid", "Access token is invalid or expired.", 401
    )
