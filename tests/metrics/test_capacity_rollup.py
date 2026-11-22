"""Contract checks for the offline capacity CLI using synthetic traces."""

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

CLI = Path(__file__).resolve().parents[2] / "scripts" / "metrics" / "capacity_rollup.py"
CHAINS = ("open_project", "save_research_plan", "background_generation", "evidence_approval")


def sample(chain="background_generation", outcome="succeeded", **phases):
    return {
        "chain": chain,
        "outcome": outcome,
        "request": [[0, 12]],
        "queue": [],
        "execution": [],
        "human_wait": [],
        **phases,
    }


def trace(*samples):
    return json.dumps({"schema_version": 1, "samples": samples}).encode()


class CapacityRollupTests(unittest.TestCase):
    def run_cli(self, content):
        with TemporaryDirectory() as root:
            path = Path(root) / "trace.json"
            if content is not None:
                path.write_bytes(content)
            result = subprocess.run(
                [sys.executable, str(CLI), str(path)],
                capture_output=True, text=True, encoding="utf-8", timeout=10,
            )
        self.assertEqual(result.stderr, "")
        return result.returncode, json.loads(result.stdout)

    def test_four_chains_and_multi_attempt_intervals(self):
        status, report = self.run_cli(trace(
            sample("open_project", request=[[0, 3], [8, 13]]),
            sample("save_research_plan", request=[[0, 16]]),
            sample(outcome="recovered", queue=[[8, 15], [40, 52]], execution=[[15, 30], [52, 80]]),
            sample("evidence_approval", human_wait=[[20, 120]]),
        ))
        self.assertEqual(status, 0)
        self.assertEqual(report["schema_version"], 1)
        chains = report["chains"]
        self.assertEqual(tuple(chains), CHAINS)
        self.assertEqual(chains["open_project"]["phases"]["request"]["p50_ms"], 8)
        self.assertEqual(chains["save_research_plan"]["phases"]["request"]["p50_ms"], 16)
        self.assertEqual(chains["evidence_approval"]["phases"]["human_wait"]["p50_ms"], 100)
        background = chains["background_generation"]
        self.assertEqual(background["samples"], 1)
        self.assertEqual(background["outcomes"], {
            "succeeded": 0, "recovered": 1, "failed": 0, "incomplete": 0,
        })
        self.assertEqual(background["phases"]["request"]["p50_ms"], 12)
        self.assertEqual(background["phases"]["queue"]["p50_ms"], 19)
        self.assertEqual(background["phases"]["execution"]["p50_ms"], 43)

    def test_failure_contributes_and_percentiles_use_nearest_rank(self):
        rows = [sample(request=[[0, n]]) for n in range(18)]
        rows.append(sample(outcome="failed", request=[[0, 100]]))
        rows.append(sample(outcome="incomplete", request=[[0, 101]]))
        rows.append(sample(outcome="incomplete", request=None))
        rows.append(sample(request=[]))
        status, report = self.run_cli(trace(*rows))
        self.assertEqual(status, 0)
        background = report["chains"]["background_generation"]
        self.assertEqual(background["samples"], 22)
        self.assertEqual(background["outcomes"], {
            "succeeded": 19, "recovered": 0, "failed": 1, "incomplete": 2,
        })
        self.assertEqual(background["phases"]["request"], {
            "measured": 20, "missing": 1, "not_applicable": 1,
            "p50_ms": 9, "p95_ms": 100, "max_ms": 101,
        })

    def test_empty_report_has_no_latency_observation(self):
        status, report = self.run_cli(trace())
        self.assertEqual(status, 0)
        self.assertEqual(tuple(report["chains"]), CHAINS)
        for chain in report["chains"].values():
            self.assertEqual(chain["samples"], 0)
            self.assertEqual(chain["phases"]["queue"], {
                "measured": 0, "missing": 0, "not_applicable": 0,
                "p50_ms": None, "p95_ms": None, "max_ms": None,
            })

    def test_invalid_interval_reports_fixed_name_and_index(self):
        for intervals in (
            [[True, 20]], [[-1, 0]], [[8, 2]], [[2, 8], [7, 10]],
            [[8, 8], [2, 2]], [[0, 2**53]], [[0, 0.0]], [[0]], {"unexpected": 1},
        ):
            with self.subTest(intervals=intervals):
                status, error = self.run_cli(trace(sample(), sample(queue=intervals)))
                self.assertEqual(status, 2)
                self.assertEqual(error, {"error": "invalid_intervals", "field": "queue", "index": 1})

    def test_closed_record_never_echoes_untrusted_keys_or_values(self):
        for row, field, code in (
            (sample(private_text="synthetic-private-marker"), None, "invalid_sample_fields"),
            (sample(chain="synthetic-private-marker"), "chain", "invalid_enum"),
            (sample(outcome=["synthetic-private-marker"]), "outcome", "invalid_enum"),
        ):
            with self.subTest(code=code, field=field):
                expected = {"error": code, "index": 0}
                if field is not None:
                    expected["field"] = field
                self.assertEqual(self.run_cli(trace(row)), (2, expected))

    def test_argument_errors_and_directory_path_return_fixed_errors(self):
        with TemporaryDirectory() as root:
            for args, code in (
                ([root], "invalid_input_path"),
                (["--synthetic-private-marker"], "invalid_arguments"),
            ):
                with self.subTest(code=code):
                    result = subprocess.run(
                        [sys.executable, str(CLI), *args],
                        capture_output=True, text=True, encoding="utf-8", timeout=10,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stderr, "")
                    self.assertEqual(json.loads(result.stdout), {"error": code})

    def test_invalid_input_fails_closed(self):
        for content, code in (
            (None, "input_unreadable"),
            (b" " * (4 * 1024 * 1024 + 1), "input_too_large"),
            (b"\xff", "invalid_json"),
            (b"[" * 3000, "invalid_json"),
            (b'{"schema_version": 1, "samples": [NaN]}', "invalid_json"),
            (b'{"schema_version": 1, "samples": [{"x": 1, "x": 2}]}', "duplicate_key"),
            (b'{"schema_version": true, "samples": []}', "unsupported_schema"),
            (b'{"schema_version": 1, "samples": {}}', "invalid_samples"),
            (b'{"schema_version": 1, "samples": [], "extra": 0}', "invalid_document_fields"),
        ):
            with self.subTest(code=code):
                self.assertEqual(self.run_cli(content), (2, {"error": code}))
