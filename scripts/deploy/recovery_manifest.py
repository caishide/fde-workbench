"""Verify an approved, sealed rehearsal bundle without interpreting its archives."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

FILES = {
    "api": "api-image.tar",
    "worker": "worker-image.tar",
    "scheduler": "scheduler-image.tar",
    "migrations": "migrations.tar",
    "postgres": "postgres.dump",
    "storage": "storage.tar",
}
IMAGE_ROLES = {"api", "worker", "scheduler"}
MANIFEST_LIMIT = 64 * 1024
CHUNK_SIZE = 1024 * 1024


class Rejected(Exception):
    def __init__(self, code: str, role: str | None = None, *, exit_code: int = 1):
        super().__init__(code)
        self.code = code
        self.role = role
        self.exit_code = exit_code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Rejected("invalid_arguments", exit_code=2)


def matches(value, pattern: str) -> bool:
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def validate_manifest(raw: bytes) -> dict:
    try:
        manifest = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)
    except (ValueError, RecursionError):
        raise Rejected("invalid_manifest") from None
    if not isinstance(manifest, dict) or manifest.keys() != {
        "schema_version", "commit", "release_input_fingerprint", "migration_head", "capture_id", "artifacts"
    }:
        raise Rejected("invalid_manifest")
    version = manifest["schema_version"]
    if type(version) is not int or version != 1:
        raise Rejected("invalid_manifest")
    for key, pattern in (
        ("commit", r"[0-9a-f]{40}"),
        ("release_input_fingerprint", r"[0-9a-f]{64}"),
        ("migration_head", r"[0-9A-Za-z_]{1,32}"),
        ("capture_id", r"[0-9a-f]{32}"),
    ):
        if not matches(manifest[key], pattern):
            raise Rejected("invalid_manifest")
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, dict) or artifacts.keys() != FILES.keys():
        raise Rejected("invalid_manifest")
    for role, item in artifacts.items():
        keys = {"size_bytes", "sha256"}
        if role in IMAGE_ROLES:
            keys |= {"image_id", "platform"}
        if not isinstance(item, dict) or item.keys() != keys:
            raise Rejected("invalid_manifest")
        if type(item["size_bytes"]) is not int or item["size_bytes"] <= 0:
            raise Rejected("invalid_manifest")
        if not matches(item["sha256"], r"[0-9a-f]{64}"):
            raise Rejected("invalid_manifest")
        if role in IMAGE_ROLES and (
            not matches(item["image_id"], r"sha256:[0-9a-f]{64}")
            or item["platform"] not in ("linux/amd64", "linux/arm64")
        ):
            raise Rejected("invalid_manifest")
    return manifest


def linked(info: os.stat_result) -> bool:
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def stamp(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns)


def read_file(path: Path, role: str | None, size: int | None) -> bytes | str:
    try:
        before = path.lstat()
        if linked(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise Rejected("unsafe_input", role)
        with path.open("rb") as handle:
            # Windows can report different ctime values for a path and its open handle.
            if stamp(os.fstat(handle.fileno())) != stamp(before):
                raise Rejected("input_changed", role)
            result: bytes | str
            if size is None:
                result = handle.read(MANIFEST_LIMIT + 1)
                if len(result) > MANIFEST_LIMIT:
                    raise Rejected("manifest_too_large")
            else:
                if before.st_size != size:
                    raise Rejected("artifact_size_mismatch", role)
                digest = hashlib.sha256()
                remaining = size
                while remaining:
                    chunk = handle.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        raise Rejected("artifact_size_mismatch", role)
                    digest.update(chunk)
                    remaining -= len(chunk)
                if handle.read(1):
                    raise Rejected("artifact_size_mismatch", role)
                result = digest.hexdigest()
            if stamp(os.fstat(handle.fileno())) != stamp(before) or stamp(path.lstat()) != stamp(before):
                raise Rejected("input_changed", role)
            return result
    except (OSError, ValueError):
        raise Rejected("input_unavailable", role, exit_code=2) from None


def verify(bundle: str, expected: str) -> dict:
    if not matches(expected, r"[0-9a-f]{64}"):
        raise Rejected("invalid_expected_digest", exit_code=2)
    if not bundle.strip():
        raise Rejected("invalid_bundle_path", exit_code=2)
    root = Path(bundle)
    if ".." in root.parts:
        raise Rejected("invalid_bundle_path", exit_code=2)
    root = Path(os.path.abspath(root))
    for path in reversed((root, *root.parents)):
        info = path.lstat()
        if linked(info) or not stat.S_ISDIR(info.st_mode):
            raise Rejected("unsafe_input")
    raw = read_file(root / "manifest.json", None, None)
    assert isinstance(raw, bytes)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise Rejected("manifest_digest_mismatch")
    manifest = validate_manifest(raw)
    for role, filename in FILES.items():
        item = manifest["artifacts"][role]
        if read_file(root / filename, role, item["size_bytes"]) != item["sha256"]:
            raise Rejected("artifact_digest_mismatch", role)
    return manifest


def main(argv=None) -> int:
    report: dict[str, Any] = {"schema_version": 1, "status": "rejected", "restore_status": "not_checked"}
    try:
        parser = Parser(description=__doc__, allow_abbrev=False)
        parser.add_argument("command", choices=("verify",))
        parser.add_argument("--bundle", required=True)
        parser.add_argument("--expected-manifest-sha256", required=True)
        args = parser.parse_args(argv)
        verify(args.bundle, args.expected_manifest_sha256)
    except (OSError, ValueError):
        report["error"] = {"code": "input_unavailable"}
        code = 2
    except Rejected as error:
        report["error"] = {"code": error.code}
        if error.role is not None:
            report["error"]["role"] = error.role
        code = error.exit_code
    else:
        report.update(status="bundle_verified", manifest_sha256=args.expected_manifest_sha256)
        code = 0
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
