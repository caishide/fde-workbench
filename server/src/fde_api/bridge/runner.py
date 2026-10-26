"""runner：入站快照的令牌校验 + 白名单形状校验（P2 版「命令白名单」的服务端半边）。

宿主采集器（scripts/bridge-poll.mjs）持静态令牌 POST 原始快照；本模块只放行
已知形状、丢弃未知键（与 P1 routes 的字段白名单同一纪律）。令牌未配置 = 桥关闭。
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from flask import current_app, request

from fde_api.config import Settings
from fde_api.errors import error_response

ViewFunction = TypeVar("ViewFunction", bound=Callable[..., Any])

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
MAX_ENGAGEMENTS = 200
MAX_FILES_PER_DIR = 50


class BridgeValidationError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def require_bridge_token(view: ViewFunction) -> ViewFunction:
    """静态令牌门（hmac 常时比较）；FDE_BRIDGE_TOKEN 未配置 → 503 桥关闭。"""

    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any):
        settings: Settings = current_app.config["SETTINGS"]
        secret = settings.bridge_token.get_secret_value() if settings.bridge_token else None
        if not secret:
            return error_response("bridge_disabled", "FDE_BRIDGE_TOKEN is not configured.", 503)
        provided = request.headers.get("Authorization", "")
        # 编码成 bytes 再比较：compare_digest 对含非 ASCII 的 str 直接抛 TypeError（500）
        if not hmac.compare_digest(
            provided.encode("utf-8", "ignore"), f"Bearer {secret}".encode("utf-8")
        ):
            return error_response("invalid_bridge_token", "Bridge token is invalid.", 401)
        return view(*args, **kwargs)

    return cast(ViewFunction, wrapped)


def _text(value: object, maximum: int, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BridgeValidationError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise BridgeValidationError(f"{field} exceeds {maximum} chars")
    return value


def _slug(value: object, field: str) -> str:
    text = _text(value, 80, field)
    if not SLUG_PATTERN.fullmatch(text):
        raise BridgeValidationError(f"{field} is not a valid slug: {text!r}")
    return text


def _sha256(value: object, field: str, required: bool) -> str | None:
    if value is None:
        if required:
            raise BridgeValidationError(f"{field} is required")
        return None
    text = _text(value, 64, field)
    if not SHA256_PATTERN.fullmatch(text):
        raise BridgeValidationError(f"{field} is not a sha256 hex digest")
    return text.lower()


def _validate_openfde_entry(entry: object) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise BridgeValidationError("openfde.engagements[] entries must be objects")
    slug = _slug(entry.get("slug"), "openfde entry slug")
    ok = entry.get("ok")
    if not isinstance(ok, bool):
        raise BridgeValidationError(f"openfde entry {slug}: ok must be boolean")
    cleaned: dict[str, Any] = {"slug": slug, "ok": ok}
    status = entry.get("status")
    if status is not None:
        if not isinstance(status, dict):
            raise BridgeValidationError(f"openfde entry {slug}: status must be an object")
        cleaned["status"] = {k: v for k, v in list(status.items())[:20]}
    if entry.get("error") is not None:
        cleaned["error"] = _text(entry["error"], 500, f"openfde entry {slug} error")
    cleaned["stdout_sha256"] = _sha256(
        entry.get("stdout_sha256"), f"openfde entry {slug} stdout_sha256", required=False
    )
    if entry.get("source_uri") is not None:
        cleaned["source_uri"] = _text(entry["source_uri"], 500, f"openfde entry {slug} source_uri")
    return cleaned


def _validate_fdeops_dir(entry: object) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise BridgeValidationError("fdeops.dirs[] entries must be objects")
    slug = _slug(entry.get("slug"), "fdeops dir slug")
    exists = entry.get("exists")
    if not isinstance(exists, bool):
        raise BridgeValidationError(f"fdeops dir {slug}: exists must be boolean")
    cleaned: dict[str, Any] = {"slug": slug, "exists": exists}
    if entry.get("fde_initialized") is not None:
        if not isinstance(entry["fde_initialized"], bool):
            raise BridgeValidationError(f"fdeops dir {slug}: fde_initialized must be boolean")
        cleaned["fde_initialized"] = entry["fde_initialized"]
    if entry.get("bound_path") is not None:
        cleaned["bound_path"] = _text(entry["bound_path"], 260, f"fdeops dir {slug} bound_path")
    files = entry.get("files")
    if files is not None:
        if not isinstance(files, list):
            raise BridgeValidationError(f"fdeops dir {slug}: files must be a list")
        cleaned["files"] = [
            _text(f, 200, f"fdeops dir {slug} file name") for f in files[:MAX_FILES_PER_DIR]
        ]
    return cleaned


def validate_bundle(body: object) -> dict[str, Any]:
    """入站快照 → 白名单化 payload；任何形状违规直接拒（不落库）。"""
    if not isinstance(body, dict):
        raise BridgeValidationError("request body must be a JSON object")
    captured_at = _text(body.get("captured_at"), 40, "captured_at")

    payload: dict[str, Any] = {"captured_at": captured_at}

    openfde = body.get("openfde")
    if openfde is not None:
        if not isinstance(openfde, dict):
            raise BridgeValidationError("openfde must be an object")
        cleaned_openfde: dict[str, Any] = {}
        current = openfde.get("current")
        if current is not None:
            cleaned_openfde["current"] = _slug(current, "openfde.current")
        engagements = openfde.get("engagements")
        if engagements is not None:
            if not isinstance(engagements, list) or len(engagements) > MAX_ENGAGEMENTS:
                raise BridgeValidationError(f"openfde.engagements must be a list of <= {MAX_ENGAGEMENTS}")
            cleaned_openfde["engagements"] = [_validate_openfde_entry(e) for e in engagements]
        payload["openfde"] = cleaned_openfde

    fdeops = body.get("fdeops")
    if fdeops is not None:
        if not isinstance(fdeops, dict):
            raise BridgeValidationError("fdeops must be an object")
        cleaned_fdeops: dict[str, Any] = {}
        cleaned_fdeops["registry_sha256"] = _sha256(
            fdeops.get("registry_sha256"), "fdeops.registry_sha256", required=False
        )
        if fdeops.get("source_uri") is not None:
            cleaned_fdeops["source_uri"] = _text(fdeops["source_uri"], 500, "fdeops.source_uri")
        bindings = fdeops.get("bindings")
        if bindings is not None:
            if not isinstance(bindings, list) or len(bindings) > MAX_ENGAGEMENTS:
                raise BridgeValidationError(f"fdeops.bindings must be a list of <= {MAX_ENGAGEMENTS}")
            cleaned = []
            for binding in bindings:
                if not isinstance(binding, dict):
                    raise BridgeValidationError("fdeops.bindings[] entries must be objects")
                cleaned.append({
                    "slug": _slug(binding.get("slug"), "fdeops binding slug"),
                    "path": _text(binding.get("path"), 260, "fdeops binding path"),
                })
            cleaned_fdeops["bindings"] = cleaned
        dirs = fdeops.get("dirs")
        if dirs is not None:
            if not isinstance(dirs, list) or len(dirs) > MAX_ENGAGEMENTS:
                raise BridgeValidationError(f"fdeops.dirs must be a list of <= {MAX_ENGAGEMENTS}")
            cleaned_fdeops["dirs"] = [_validate_fdeops_dir(d) for d in dirs]
        payload["fdeops"] = cleaned_fdeops

    return payload
