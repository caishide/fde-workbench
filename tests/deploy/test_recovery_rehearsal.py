"""Exercise the offline recovery orchestrator with synthetic bundles and callbacks."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts/deploy"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from recovery_manifest import FILES
from recovery_rehearsal import (
    RehearsalPlan,
    RecoveryStepError,
    execute_rehearsal,
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class RehearsalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        self.bundle = self.temp / "bundle"
        self.bundle.mkdir()
        self.storage = self.temp / "storage"
        self.storage.mkdir()
        self.migrations = self.temp / "migrations"
        self.migrations.mkdir()
        payloads = {role: f"synthetic {role}".encode() for role in FILES}
        for role, payload in payloads.items():
            (self.bundle / FILES[role]).write_bytes(payload)
        manifest = {
            "schema_version": 1,
            "commit": "a" * 40,
            "release_input_fingerprint": "b" * 64,
            "migration_head": "deadbeefcafe",
            "capture_id": "c" * 32,
            "artifacts": {},
        }
        for role, payload in payloads.items():
            item = {"size_bytes": len(payload), "sha256": digest(payload)}
            if role in {"api", "worker", "scheduler"}:
                item.update(image_id="sha256:" + digest(role.encode()), platform="linux/amd64")
            manifest["artifacts"][role] = item
        raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        (self.bundle / "manifest.json").write_bytes(raw)
        self.manifest_digest = digest(raw)
        self.capture = "c" * 32
        self.image_ids = {
            "api": "sha256:" + digest(b"api"),
            "worker": "sha256:" + digest(b"worker"),
            "scheduler": "sha256:" + digest(b"scheduler"),
        }
        self.plan = RehearsalPlan(
            rehearsal_root=self.temp,
            bundle=self.bundle,
            expected_manifest_sha256=self.manifest_digest,
            capture_id=self.capture,
            commit="a" * 40,
            migration_head="deadbeefcafe",
            project=f"fde-r1c-{self.capture}-rehearsal",
            network=f"fde-r1c-{self.capture}-internal",
            postgres_volume=f"fde-r1c-{self.capture}-postgres",
            redis_volume=f"fde-r1c-{self.capture}-redis",
            storage_volume=f"fde-r1c-{self.capture}-storage",
            database_url=f"postgresql+psycopg://rehearsal:hidden@127.0.0.1:25432/fde_r1c_{self.capture}_rehearsal",
            redis_url=f"redis://127.0.0.1:26379/9",
            storage_root=self.storage,
            migrations_mount=self.migrations,
            readiness_url="http://127.0.0.1:28100/api/v1/health/ready",
            secret_fingerprint="d" * 64,
            image_ids=self.image_ids,
            expected_storage_sha256="e" * 64,
            expected_object_count=2,
            expected_watermark=17,
            expected_marker_sha256="f" * 64,
        )
        self.calls = []

    def steps(self):
        def preflight(plan):
            self.calls.append("preflight")
            return {"isolated": True, "public_ports": False, "external_channels": False}

        def restore_database(plan):
            self.calls.append("restore_database")
            return {"object_count": 2, "capture_id": self.capture, "watermark": 17}

        def restore_storage(plan):
            self.calls.append("restore_storage")
            return {"object_count": 2, "sha256": "e" * 64, "byte_identical": True}

        def apply_migrations(plan):
            self.calls.append("apply_migrations")
            return {"head": "deadbeefcafe"}

        def verify_crypto(plan):
            self.calls.append("verify_crypto")
            return {"decrypt_ok": True, "secret_fingerprint": "d" * 64, "marker_sha256": "f" * 64}

        def verify_images(plan):
            self.calls.append("verify_images")
            return {role: value for role, value in self.image_ids.items()}

        def verify_mounts(plan):
            self.calls.append("verify_mounts")
            return {"migrations_in_rehearsal": True, "storage_in_rehearsal": True}

        def probe_readiness(plan):
            self.calls.append("probe_readiness")
            return {"endpoint": "http://127.0.0.1:28100/api/v1/health/ready", "http_status": 200, "code": "ok"}

        return {
            "preflight": preflight,
            "restore_database": restore_database,
            "restore_storage": restore_storage,
            "apply_migrations": apply_migrations,
            "verify_crypto": verify_crypto,
            "verify_images": verify_images,
            "verify_mounts": verify_mounts,
            "probe_readiness": probe_readiness,
        }

    def test_rejected_isolation_plan_runs_no_steps_and_reports_no_secret(self):
        plan = RehearsalPlan(
            **{**self.plan.__dict__, "database_url": "postgresql+psycopg://fde:hidden@127.0.0.1:15432/fde_workbench"}
        )
        report = execute_rehearsal(plan, self.steps())
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["restore_status"], "not_run")
        self.assertFalse(report["bundle_verified"])
        self.assertEqual(report["error"]["code"], "unsafe_rehearsal_plan")
        self.assertEqual(self.calls, [])
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("hidden", rendered)
        self.assertNotIn(str(self.bundle), rendered)

    def test_bundle_mismatch_stops_before_restore(self):
        plan = RehearsalPlan(
            **{**self.plan.__dict__, "expected_manifest_sha256": "0" * 64}
        )
        report = execute_rehearsal(plan, self.steps())
        self.assertEqual(report["status"], "rejected")
        self.assertEqual(report["restore_status"], "not_run")
        self.assertFalse(report["bundle_verified"])
        self.assertEqual(report["error"]["code"], "bundle_mismatch")
        self.assertEqual(self.calls, [])

    def test_successful_synthetic_restore_reports_all_evidence(self):
        report = execute_rehearsal(self.plan, self.steps())
        self.assertEqual(report["status"], "restore_verified")
        self.assertEqual(report["restore_status"], "passed")
        self.assertTrue(report["bundle_verified"])
        self.assertEqual(report["capture_id"], self.capture)
        self.assertEqual(
            self.calls,
            ["preflight", "restore_database", "restore_storage", "apply_migrations",
             "verify_crypto", "verify_images", "verify_mounts", "probe_readiness"],
        )
        self.assertEqual(report["evidence"]["database"]["capture_id"], self.capture)
        self.assertEqual(report["evidence"]["database"]["object_count"], 2)
        self.assertEqual(report["evidence"]["database"]["watermark"], 17)
        self.assertEqual(report["evidence"]["storage"]["byte_identical"], True)
        self.assertEqual(report["evidence"]["migrations"]["head"], "deadbeefcafe")
        self.assertEqual(report["evidence"]["images"], self.image_ids)
        self.assertEqual(report["evidence"]["readiness"]["http_status"], 200)
        self.assertEqual(
            set(report["timings_ms"]),
            {"preflight", "restore_database", "restore_storage", "apply_migrations",
             "verify_crypto", "verify_images", "verify_mounts", "probe_readiness"},
        )
        for value in report["timings_ms"].values():
            self.assertGreaterEqual(value, 0)
        rendered = json.dumps(report, sort_keys=True)
        self.assertNotIn("hidden", rendered)
        self.assertNotIn(str(self.bundle), rendered)
        self.assertNotIn(str(self.storage), rendered)
        self.assertNotIn(str(self.migrations), rendered)

    def test_plan_images_must_match_the_approved_bundle(self):
        plan = replace(self.plan, image_ids={**self.image_ids, "worker": "sha256:" + "0" * 64})
        report = execute_rehearsal(plan, self.steps())
        self.assertEqual(report["error"], {"code": "plan_manifest_mismatch"})
        self.assertEqual(report["restore_status"], "not_run")
        self.assertEqual(self.calls, [])

    def test_malformed_targets_are_rejected_without_echoing_inputs(self):
        for change in (
            {"readiness_url": "http://127.0.0.1:hidden/api/v1/health/ready"},
            {"readiness_url": "http://127.0.0.1:25432/api/v1/health/ready"},
            {"capture_id": "hidden"},
            {"storage_root": self.bundle / "storage"},
        ):
            with self.subTest(change=change):
                report = execute_rehearsal(replace(self.plan, **change), self.steps())
                self.assertEqual(report["error"]["code"], "unsafe_rehearsal_plan")
                self.assertEqual(report["restore_status"], "not_run")
                self.assertNotIn("hidden", json.dumps(report))
                self.assertEqual(self.calls, [])

    def test_invalid_pathlike_returns_safe_plan_rejection(self):
        class BadPath:
            def __fspath__(self):
                return 42

        report = execute_rehearsal(replace(self.plan, bundle=BadPath()), self.steps())
        self.assertEqual(report["error"], {"code": "unsafe_rehearsal_plan", "field": "bundle"})
        self.assertEqual(self.calls, [])

    def test_integer_flags_fail_isolation_and_mount_checks(self):
        for stage, evidence, error in (
            ("preflight", {"isolated": 1, "public_ports": 0, "external_channels": 0}, "unsafe_rehearsal_target"),
            ("verify_mounts", {"migrations_in_rehearsal": 1, "storage_in_rehearsal": 1}, "mount_evidence_mismatch"),
        ):
            with self.subTest(stage=stage):
                self.calls.clear()
                steps = self.steps()
                steps[stage] = lambda _plan: evidence
                report = execute_rehearsal(self.plan, steps)
                self.assertEqual(report["error"], {"stage": stage, "code": error})
                self.assertNotIn("probe_readiness", self.calls)
                if stage == "preflight":
                    self.assertNotIn("restore_database", self.calls)

    def test_database_object_count_must_match(self):
        steps = self.steps()
        steps["restore_database"] = lambda _plan: {"object_count": 1, "capture_id": self.capture, "watermark": 17}
        report = execute_rehearsal(self.plan, steps)
        self.assertEqual(report["error"], {"stage": "restore_database", "code": "database_evidence_mismatch"})
        self.assertNotIn("restore_storage", self.calls)

    def test_database_watermark_must_match_the_capture_cutoff(self):
        for restored_watermark in (16, 18, True):
            with self.subTest(restored_watermark=restored_watermark):
                self.calls.clear()
                steps = self.steps()

                def restore_database(_plan):
                    self.calls.append("restore_database")
                    return {"object_count": 2, "capture_id": self.capture, "watermark": restored_watermark}

                report = execute_rehearsal(self.plan, {**steps, "restore_database": restore_database})
                self.assertEqual(report["restore_status"], "blocked")
                self.assertEqual(report["error"], {
                    "stage": "restore_database", "code": "database_evidence_mismatch",
                })
                self.assertNotIn("database", report["evidence"])
                self.assertEqual(self.calls, ["preflight", "restore_database"])

    def test_database_watermark_uses_the_planned_cutoff(self):
        plan = replace(self.plan, expected_watermark=9)
        steps = self.steps()
        steps["restore_database"] = lambda _plan: {"object_count": 2, "capture_id": self.capture, "watermark": 9}
        report = execute_rehearsal(plan, steps)
        self.assertEqual(report["restore_status"], "passed")
        self.assertEqual(report["evidence"]["database"]["watermark"], 9)

    def test_invalid_expected_watermark_is_rejected_before_callbacks(self):
        for watermark in (True, 0, -1, "17"):
            with self.subTest(watermark=watermark):
                plan = replace(self.plan, expected_watermark=watermark)
                report = execute_rehearsal(plan, self.steps())
                self.assertEqual(report["restore_status"], "not_run")
                self.assertEqual(report["error"], {
                    "code": "unsafe_rehearsal_plan", "field": "expected_watermark",
                })
                self.assertEqual(self.calls, [])

    def test_unregistered_step_code_is_not_echoed(self):
        def fail(_plan):
            raise RecoveryStepError("hidden")

        steps = self.steps()
        steps["restore_database"] = fail
        report = execute_rehearsal(self.plan, steps)
        self.assertEqual(report["error"], {"stage": "restore_database", "code": "stage_failed"})
        self.assertNotIn("hidden", json.dumps(report))

    def test_verified_evidence_is_snapshotted_and_sensitive_fields_are_omitted(self):
        evidence = {"object_count": 2, "capture_id": self.capture, "watermark": 17}
        steps = self.steps()
        steps["restore_database"] = lambda _plan: evidence
        original = steps["restore_storage"]

        def restore_storage(plan):
            evidence["unexpected"] = "hidden"
            return original(plan)

        steps["restore_storage"] = restore_storage
        report = execute_rehearsal(self.plan, steps)
        self.assertEqual(report["status"], "restore_verified")
        self.assertNotIn("hidden", json.dumps(report))
        self.assertNotIn("secret_fingerprint", report["evidence"]["crypto"])
        self.assertNotIn("endpoint", report["evidence"]["readiness"])


    def test_isolation_preflight_failure_stops_rehearsal(self):
        def bad_preflight(plan):
            self.calls.append("preflight")
            return {"isolated": True, "public_ports": True, "external_channels": False}

        steps = self.steps()
        steps["preflight"] = bad_preflight
        report = execute_rehearsal(self.plan, steps)
        self.assertEqual(report["status"], "restore_failed")
        self.assertEqual(report["restore_status"], "blocked")
        self.assertEqual(report["error"], {"stage": "preflight", "code": "unsafe_rehearsal_target"})
        self.assertEqual(self.calls, ["preflight"])

    def test_storage_evidence_mismatch_stops_before_migrations(self):
        def bad_storage(plan):
            self.calls.append("restore_storage")
            return {"object_count": 2, "sha256": "9" * 64, "byte_identical": True}

        steps = self.steps()
        steps["restore_storage"] = bad_storage
        report = execute_rehearsal(self.plan, steps)
        self.assertEqual(report["status"], "restore_failed")
        self.assertEqual(report["error"], {"stage": "restore_storage", "code": "storage_evidence_mismatch"})
        self.assertEqual(self.calls[-1], "restore_storage")
        self.assertNotIn("apply_migrations", self.calls)

    def test_wrong_migration_head_is_blocked(self):
        def bad_migrations(plan):
            self.calls.append("apply_migrations")
            return {"head": "stale"}

        steps = self.steps()
        steps["apply_migrations"] = bad_migrations
        report = execute_rehearsal(self.plan, steps)
        self.assertEqual(report["status"], "restore_failed")
        self.assertEqual(report["error"], {"stage": "apply_migrations", "code": "migration_head_mismatch"})

    def test_wrong_image_id_is_blocked(self):
        evidence = dict(self.image_ids)
        evidence["worker"] = "sha256:" + "0" * 64

        def bad_images(plan):
            self.calls.append("verify_images")
            return evidence

        steps = self.steps()
        steps["verify_images"] = bad_images
        report = execute_rehearsal(self.plan, steps)
        self.assertEqual(report["status"], "restore_failed")
        self.assertEqual(report["error"], {"stage": "verify_images", "code": "image_id_mismatch"})

    def test_failed_step_becomes_safe_code_without_exception_text(self):
        def failing_database(plan):
            self.calls.append("restore_database")
            raise RecoveryStepError("restore_rejected", "secret reason and /tmp/private")

        steps = self.steps()
        steps["restore_database"] = failing_database
        report = execute_rehearsal(self.plan, steps)
        self.assertEqual(report["status"], "restore_failed")
        self.assertEqual(report["error"], {"stage": "restore_database", "code": "restore_rejected"})
        self.assertNotIn("secret reason", json.dumps(report))
        self.assertNotIn("/tmp/private", json.dumps(report))


if __name__ == "__main__":
    unittest.main()
