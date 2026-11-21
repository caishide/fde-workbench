"""Validate and orchestrate an offline rehearsal through caller-supplied steps."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from itertools import combinations
import os
from pathlib import Path
import re
import stat
import time
from types import MappingProxyType
from urllib.parse import SplitResult, urlsplit

from recovery_manifest import IMAGE_ROLES, Rejected, linked, verify


SCHEMA_VERSION = 1
IMAGE_ID_RE = re.compile(r"sha256:[0-9a-f]{64}")
DIGEST_RE = re.compile(r"[0-9a-f]{64}")
CAPTURE_RE = re.compile(r"[0-9a-f]{32}")
HEAD_RE = re.compile(r"[A-Za-z0-9_]{1,32}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
STAGES = (
    "preflight",
    "restore_database",
    "restore_storage",
    "apply_migrations",
    "verify_crypto",
    "verify_images",
    "verify_mounts",
    "probe_readiness",
)


class RehearsalPlanError(ValueError):
    pass


class RecoveryStepError(Exception):
    def __init__(self, code: str, message: object | None = None):
        super().__init__(code, message)
        self.code = code


@dataclass(frozen=True)
class RehearsalPlan:
    rehearsal_root: str | os.PathLike[str] = field(repr=False)
    bundle: str | os.PathLike[str] = field(repr=False)
    expected_manifest_sha256: str
    capture_id: str
    commit: str
    migration_head: str
    project: str
    network: str
    postgres_volume: str
    redis_volume: str
    storage_volume: str
    database_url: str = field(repr=False)
    redis_url: str
    storage_root: str | os.PathLike[str] = field(repr=False)
    migrations_mount: str | os.PathLike[str] = field(repr=False)
    readiness_url: str
    secret_fingerprint: str = field(repr=False)
    image_ids: Mapping[str, str]
    expected_storage_sha256: str
    expected_object_count: int
    expected_marker_sha256: str


def _hex(value: object, pattern: re.Pattern[str], field: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise RehearsalPlanError(field)
    return value


def _path(value: object, field: str, *, root: Path | None = None, must_exist: bool = False) -> Path:
    try:
        raw = os.fspath(value) if isinstance(value, os.PathLike) else value
    except (OSError, TypeError, ValueError):
        raise RehearsalPlanError(field) from None
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise RehearsalPlanError(field)
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts:
        raise RehearsalPlanError(field)
    path = Path(os.path.abspath(path))
    for entry in (*reversed(path.parents), path):
        try:
            info = entry.lstat()
        except FileNotFoundError:
            if must_exist:
                raise RehearsalPlanError(field) from None
            break
        except OSError:
            raise RehearsalPlanError(field) from None
        if linked(info) or not stat.S_ISDIR(info.st_mode):
            raise RehearsalPlanError(field)
    # On Windows this also expands existing 8.3 aliases, including parents of future paths.
    try:
        canonical = path.resolve(strict=must_exist)
    except (OSError, ValueError, RuntimeError):
        raise RehearsalPlanError(field) from None
    if root is not None and (canonical == root or not canonical.is_relative_to(root)):
        raise RehearsalPlanError(field)
    return canonical


def _resource(value: object, capture: str, suffix: str, field: str) -> str:
    expected = f"fde-r1c-{capture}-{suffix}"
    if value != expected:
        raise RehearsalPlanError(field)
    return expected


def _port(value: int | None, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 20000 <= value <= 29999:
        raise RehearsalPlanError(field)
    return value


def _loopback(
    raw: object, scheme: str, path: str, field: str, *, require_credentials: bool = False,
) -> int:
    if not isinstance(raw, str) or not raw.isascii() or any(ord(char) <= 32 for char in raw):
        raise RehearsalPlanError(field)
    try:
        parts: SplitResult = urlsplit(raw)
        port = _port(parts.port, field)
    except ValueError:
        raise RehearsalPlanError(field) from None
    if (
        parts.scheme != scheme or parts.hostname != "127.0.0.1" or parts.path != path
        or "?" in raw or "#" in raw
    ):
        raise RehearsalPlanError(field)
    if require_credentials:
        if not parts.username or not parts.password or parts.netloc.count("@") != 1:
            raise RehearsalPlanError(field)
    elif "@" in parts.netloc:
        raise RehearsalPlanError(field)
    return port


def _validate_plan(plan: object) -> tuple[RehearsalPlan, Path]:
    if not isinstance(plan, RehearsalPlan):
        raise RehearsalPlanError("plan_type")
    _hex(plan.capture_id, CAPTURE_RE, "capture_id")
    _hex(plan.commit, COMMIT_RE, "commit")
    _hex(plan.migration_head, HEAD_RE, "migration_head")
    _hex(plan.expected_manifest_sha256, DIGEST_RE, "expected_manifest_sha256")
    _hex(plan.secret_fingerprint, DIGEST_RE, "secret_fingerprint")
    _hex(plan.expected_storage_sha256, DIGEST_RE, "expected_storage_sha256")
    _hex(plan.expected_marker_sha256, DIGEST_RE, "expected_marker_sha256")
    if type(plan.expected_object_count) is not int or plan.expected_object_count <= 0:
        raise RehearsalPlanError("expected_object_count")

    root = _path(plan.rehearsal_root, "rehearsal_root", must_exist=True)
    bundle = _path(plan.bundle, "bundle", root=root, must_exist=True)
    storage = _path(plan.storage_root, "storage_root", root=root)
    migrations = _path(plan.migrations_mount, "migrations_mount", root=root)
    targets = (bundle, storage, migrations)
    if any(left.is_relative_to(right) or right.is_relative_to(left) for left, right in combinations(targets, 2)):
        raise RehearsalPlanError("path_overlap")

    _resource(plan.project, plan.capture_id, "rehearsal", "project")
    _resource(plan.network, plan.capture_id, "internal", "network")
    _resource(plan.postgres_volume, plan.capture_id, "postgres", "postgres_volume")
    _resource(plan.redis_volume, plan.capture_id, "redis", "redis_volume")
    _resource(plan.storage_volume, plan.capture_id, "storage", "storage_volume")

    expected_db = f"fde_r1c_{plan.capture_id}_rehearsal"
    database_port = _loopback(
        plan.database_url, "postgresql+psycopg", f"/{expected_db}", "database_url", require_credentials=True,
    )
    redis_port = _loopback(plan.redis_url, "redis", "/9", "redis_url")
    readiness_port = _loopback(plan.readiness_url, "http", "/api/v1/health/ready", "readiness_url")
    if len({database_port, redis_port, readiness_port}) != 3:
        raise RehearsalPlanError("port_overlap")

    if not isinstance(plan.image_ids, Mapping) or set(plan.image_ids) != IMAGE_ROLES:
        raise RehearsalPlanError("image_ids")
    for role, image_id in plan.image_ids.items():
        _hex(image_id, IMAGE_ID_RE, f"image_ids.{role}")

    fixed = replace(
        plan, rehearsal_root=str(root), bundle=str(bundle), storage_root=str(storage),
        migrations_mount=str(migrations), image_ids=MappingProxyType(dict(plan.image_ids)),
    )
    return fixed, bundle


def _report(capture: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "capture_id": capture,
        "status": "rejected",
        "restore_status": "not_run",
        "bundle_verified": False,
        "timings_ms": {},
        "evidence": {},
    }


def _finish(report: dict, stage: str, code: str) -> dict:
    report["status"] = "restore_failed"
    report["restore_status"] = "blocked"
    report["error"] = {"stage": stage, "code": code}
    return report


def _run_stage(
    stage: str, step: Callable[[RehearsalPlan], object], plan: RehearsalPlan, report: dict,
) -> tuple[bool, object]:
    started = time.perf_counter_ns()
    try:
        return True, step(plan)
    except RecoveryStepError as error:
        code = "restore_rejected" if error.code == "restore_rejected" else "stage_failed"
        return False, _finish(report, stage, code)
    except (Exception, SystemExit):
        return False, _finish(report, stage, "stage_failed")
    finally:
        report["timings_ms"][stage] = (time.perf_counter_ns() - started) // 1_000_000


def _check_database(evidence: object, plan: RehearsalPlan) -> bool:
    if not isinstance(evidence, dict) or set(evidence) != {"object_count", "capture_id", "watermark"}:
        return False
    if evidence["capture_id"] != plan.capture_id:
        return False
    if type(evidence["object_count"]) is not int or evidence["object_count"] != plan.expected_object_count:
        return False
    return type(evidence["watermark"]) is int and evidence["watermark"] > 0


def _check_storage(evidence: object, plan: RehearsalPlan) -> bool:
    if not isinstance(evidence, dict) or set(evidence) != {"object_count", "sha256", "byte_identical"}:
        return False
    if evidence["sha256"] != plan.expected_storage_sha256 or evidence["byte_identical"] is not True:
        return False
    return type(evidence["object_count"]) is int and evidence["object_count"] == plan.expected_object_count


def _check_crypto(evidence: object, plan: RehearsalPlan) -> bool:
    if not isinstance(evidence, dict) or set(evidence) != {"decrypt_ok", "secret_fingerprint", "marker_sha256"}:
        return False
    if evidence["decrypt_ok"] is not True:
        return False
    if evidence["secret_fingerprint"] != plan.secret_fingerprint:
        return False
    return evidence["marker_sha256"] == plan.expected_marker_sha256


def _check_images(evidence: object, plan: RehearsalPlan) -> bool:
    return evidence == plan.image_ids


def _check_migrations(evidence: object, plan: RehearsalPlan) -> bool:
    return evidence == {"head": plan.migration_head}


def _check_readiness(evidence: object, plan: RehearsalPlan) -> bool:
    if not isinstance(evidence, dict) or set(evidence) != {"endpoint", "http_status", "code"}:
        return False
    if evidence["endpoint"] != plan.readiness_url or type(evidence["http_status"]) is not int:
        return False
    if evidence["http_status"] != 200:
        return False
    return evidence["code"] == "ok"


def _check_preflight(evidence: dict, _plan: RehearsalPlan) -> bool:
    return (
        evidence.keys() == {"isolated", "public_ports", "external_channels"}
        and evidence["isolated"] is True
        and evidence["public_ports"] is False
        and evidence["external_channels"] is False
    )


def _check_mounts(evidence: dict, _plan: RehearsalPlan) -> bool:
    return (
        evidence.keys() == {"migrations_in_rehearsal", "storage_in_rehearsal"}
        and evidence["migrations_in_rehearsal"] is True
        and evidence["storage_in_rehearsal"] is True
    )


CHECKS = {
    "preflight": _check_preflight,
    "restore_database": _check_database,
    "restore_storage": _check_storage,
    "apply_migrations": _check_migrations,
    "verify_crypto": _check_crypto,
    "verify_images": _check_images,
    "verify_mounts": _check_mounts,
    "probe_readiness": _check_readiness,
}
FAIL_CODES = {
    "preflight": "unsafe_rehearsal_target",
    "restore_database": "database_evidence_mismatch",
    "restore_storage": "storage_evidence_mismatch",
    "apply_migrations": "migration_head_mismatch",
    "verify_crypto": "crypto_evidence_mismatch",
    "verify_images": "image_id_mismatch",
    "verify_mounts": "mount_evidence_mismatch",
    "probe_readiness": "readiness_evidence_mismatch",
}


# Report fields are independent of callback return objects and omit input secrets and URLs.
EVIDENCE_FIELDS = {
    "preflight": ("preflight", ("isolated", "public_ports", "external_channels")),
    "restore_database": ("database", ("object_count", "capture_id", "watermark")),
    "restore_storage": ("storage", ("object_count", "sha256", "byte_identical")),
    "apply_migrations": ("migrations", ("head",)),
    "verify_crypto": ("crypto", ("decrypt_ok",)),
    "verify_images": ("images", tuple(sorted(IMAGE_ROLES))),
    "verify_mounts": ("mounts", ("migrations_in_rehearsal", "storage_in_rehearsal")),
    "probe_readiness": ("readiness", ("http_status", "code")),
}


def _verified_manifest(bundle: Path, expected: str) -> dict:
    try:
        return verify(str(bundle), expected)
    except Rejected as error:
        code = "bundle_mismatch" if error.code == "manifest_digest_mismatch" else "bundle_invalid"
        raise RehearsalPlanError(code) from None
    except (OSError, ValueError):
        raise RehearsalPlanError("bundle_invalid") from None


def execute_rehearsal(plan: object, steps: Mapping[str, Callable[[RehearsalPlan], object]]) -> dict:
    try:
        fixed, bundle = _validate_plan(plan)
    except RehearsalPlanError as error:
        capture = plan.capture_id if isinstance(plan, RehearsalPlan) else None
        report = _report(capture if isinstance(capture, str) and CAPTURE_RE.fullmatch(capture) else "")
        report["error"] = {"code": "unsafe_rehearsal_plan", "field": error.args[0] if error.args else "plan"}
        return report

    report = _report(fixed.capture_id)
    if not isinstance(steps, Mapping) or set(steps) != set(STAGES) or not all(callable(step) for step in steps.values()):
        report["error"] = {"code": "invalid_rehearsal_steps"}
        return report
    try:
        manifest = _verified_manifest(bundle, fixed.expected_manifest_sha256)
    except RehearsalPlanError as error:
        report["error"] = {"code": error.args[0]}
        return report
    report["bundle_verified"] = True
    approved_images = {role: manifest["artifacts"][role]["image_id"] for role in IMAGE_ROLES}
    if (
        manifest["capture_id"] != fixed.capture_id or manifest["migration_head"] != fixed.migration_head
        or manifest["commit"] != fixed.commit or approved_images != fixed.image_ids
    ):
        report["error"] = {"code": "plan_manifest_mismatch"}
        return report

    callbacks = dict(steps)
    for stage in STAGES:
        ok, value = _run_stage(stage, callbacks[stage], fixed, report)
        if not ok:
            return report
        if (
            type(value) is not dict
            or any(type(item) not in (str, int, bool) for item in value.values())
            or not CHECKS[stage](value, fixed)
        ):
            return _finish(report, stage, FAIL_CODES[stage])
        key, fields = EVIDENCE_FIELDS[stage]
        report["evidence"][key] = {field: value[field] for field in fields}
    report["status"] = "restore_verified"
    report["restore_status"] = "passed"
    return report
