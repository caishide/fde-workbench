import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/deploy/recovery_manifest.py"
FILES = {
    "api": "api-image.tar",
    "worker": "worker-image.tar",
    "scheduler": "scheduler-image.tar",
    "migrations": "migrations.tar",
    "postgres": "postgres.dump",
    "storage": "storage.tar",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class RecoveryManifestTests(unittest.TestCase):
    def setUp(self):
        temp = self.enterContext(tempfile.TemporaryDirectory())
        self.bundle = Path(temp) / "bundle"
        self.bundle.mkdir()
        self.manifest = self.bundle / "manifest.json"
        self.document = {
            "schema_version": 1,
            "commit": "a" * 40,
            "release_input_fingerprint": "b" * 64,
            "migration_head": "a8786f78abcd",
            "capture_id": "c" * 32,
            "artifacts": {},
        }
        for role, filename in FILES.items():
            payload = f"synthetic artifact: {role}".encode()
            (self.bundle / filename).write_bytes(payload)
            item = {"size_bytes": len(payload), "sha256": sha256(payload)}
            if role in {"api", "worker", "scheduler"}:
                item.update(image_id="sha256:" + sha256(role.encode()), platform="linux/amd64")
            self.document["artifacts"][role] = item
        self.approved_digest = self.write_manifest()

    def write_manifest(self, raw=None):
        if raw is None:
            raw = json.dumps(self.document).encode()
        self.manifest.write_bytes(raw)
        return sha256(raw)

    def run_cli(self, expected=None, *, bundle=None, cwd=None):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "verify", "--bundle", str(self.bundle) if bundle is None else bundle,
             "--expected-manifest-sha256", expected or self.approved_digest],
            capture_output=True, text=True, timeout=15, check=False, cwd=cwd,
        )
        self.assertEqual(result.stderr, "", result.stderr)
        return result.returncode, json.loads(result.stdout)

    def reject(self, code, role=None, *, expected=None, exit_code=1, bundle=None, cwd=None):
        status, report = self.run_cli(expected, bundle=bundle, cwd=cwd)
        self.assertEqual(status, exit_code, report)
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["restore_status"], "not_checked")
        self.assertEqual(report["error"], {"code": code, **({"role": role} if role else {})})
        self.assertNotIn(str(self.bundle), json.dumps(report))

    def test_approved_manifest_and_six_artifacts_verify(self):
        status, report = self.run_cli()
        self.assertEqual(status, 0, report)
        self.assertEqual(report["status"], "bundle_verified")
        self.assertEqual(report["restore_status"], "not_checked")
        self.assertEqual(report["manifest_sha256"], self.approved_digest)

    def test_replaced_payload_and_matching_manifest_do_not_replace_approval(self):
        data = b"new synthetic backup"
        (self.bundle / FILES["storage"]).write_bytes(data)
        self.document["artifacts"]["storage"] = {"sha256": sha256(data), "size_bytes": len(data)}
        self.write_manifest()
        self.reject("manifest_digest_mismatch")

    def test_same_size_change_has_wrong_digest(self):
        path = self.bundle / FILES["storage"]
        path.write_bytes(b"x" * path.stat().st_size)
        self.reject("artifact_digest_mismatch", "storage")

    def test_incomplete_file_has_wrong_size(self):
        (self.bundle / FILES["postgres"]).write_bytes(b"cut")
        self.reject("artifact_size_mismatch", "postgres")

    def test_missing_role_file_is_rejected(self):
        (self.bundle / FILES["migrations"]).unlink()
        self.reject("input_unavailable", "migrations", exit_code=2)

    def test_nonregular_input_is_rejected(self):
        path = self.bundle / FILES["postgres"]
        path.unlink()
        path.mkdir()
        self.reject("unsafe_input", "postgres")

    def test_hardlink_is_rejected_even_if_bytes_match(self):
        os.link(self.bundle / FILES["api"], self.bundle.parent / "archive-copy")
        self.reject("unsafe_input", "api")

    def test_duplicate_json_fields_are_rejected(self):
        raw = self.manifest.read_bytes().replace(b"{", b'{"schema_version": 1,', 1)
        self.reject("invalid_manifest", expected=self.write_manifest(raw))

    def test_limits_and_schema_are_checked(self):
        self.reject("manifest_too_large", expected=self.write_manifest(b" " * (64 * 1024 + 1)))
        self.document["schema_version"] = True
        self.reject("invalid_manifest", expected=self.write_manifest())
        self.document["schema_version"] = 1
        self.document["artifacts"]["storage"]["path"] = "untrusted-relative-path"
        self.reject("invalid_manifest", expected=self.write_manifest())

    def test_missing_role_and_image_metadata_are_rejected(self):
        self.document["artifacts"]["api"]["image_id"] = "mutable:latest"
        self.reject("invalid_manifest", expected=self.write_manifest())
        del self.document["artifacts"]["api"]
        self.reject("invalid_manifest", expected=self.write_manifest())

    def test_malformed_approval_digest_is_rejected(self):
        self.reject("invalid_expected_digest", expected="invalid", exit_code=2)

    def test_empty_bundle_is_rejected_even_in_approved_directory(self):
        self.reject("invalid_bundle_path", exit_code=2, bundle="", cwd=self.bundle)

    def test_parent_path_components_are_rejected_before_normalization(self):
        child = self.bundle / "child"
        child.mkdir()
        self.reject("invalid_bundle_path", exit_code=2, bundle=str(child / ".."))
