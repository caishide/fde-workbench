from __future__ import annotations

import contextlib
import io
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any

from scripts.metrics.observation_rollup import ObservationError, build_observation_report, main


def record(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "observation_id": "OBS-001",
        "cohort_id": "PRESURVEY-A",
        "comparison_arm": "manual",
        "attempt_state": "attempted",
        "result": "completed",
        "completion_mode": "independent",
        "first_acceptance": "passed",
        "accepted": True,
        "human_minutes": 30,
        "rework_minutes": 0,
        "wall_minutes": 45,
        "model_cost_units": None,
    }
    value.update(overrides)
    return value


def card(report: dict[str, Any], key: str) -> dict[str, Any]:
    return report["rates"][key]


def measure(report: dict[str, Any], key: str, arm: str) -> dict[str, Any]:
    return report["measurements"][key][arm]


def cli_output(argv: list[str]) -> tuple[int, str]:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        exit_code = main(argv)
    return exit_code, stream.getvalue()


class ObservationRollupTests(unittest.TestCase):
    def test_empty_observations_keep_denominators_unknown(self) -> None:
        report = build_observation_report([])
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["interpretation"], "observation_only")
        self.assertEqual(
            report["totals"],
            {
                "records": 0,
                "attempted": 0,
                "completed": 0,
                "failed": 0,
                "abandoned": 0,
                "result_unknown": 0,
                "not_attempted": 0,
                "attempt_state_unknown": 0,
                "independent": 0,
                "assisted": 0,
                "entered_first_acceptance": 0,
                "first_acceptance_passed": 0,
                "first_acceptance_failed": 0,
                "first_acceptance_unknown": 0,
                "accepted_outputs": 0,
            },
        )
        self.assertEqual(card(report, "task_completion_rate")["status"], "insufficient_data")
        self.assertIsNone(card(report, "task_completion_rate")["value"])
        self.assertEqual(card(report, "independent_completion_rate")["status"], "insufficient_data")
        self.assertEqual(card(report, "first_acceptance_pass_rate")["status"], "insufficient_data")

    def test_mixed_denominators_and_rates_are_preserved(self) -> None:
        records = [
            record(),
            record(
                observation_id="OBS-002",
                comparison_arm="ai_assisted",
                completion_mode="assisted",
                first_acceptance="passed",
                accepted=True,
                human_minutes=10,
                rework_minutes=5,
                wall_minutes=20,
                model_cost_units=7,
            ),
            record(
                observation_id="OBS-003",
                comparison_arm="ai_assisted",
                result="failed",
                completion_mode="not_applicable",
                first_acceptance="not_entered",
                accepted=False,
                human_minutes=12,
                rework_minutes=None,
                wall_minutes=None,
                model_cost_units=3,
            ),
            record(
                observation_id="OBS-004",
                comparison_arm="ai_assisted",
                result="abandoned",
                completion_mode="not_applicable",
                first_acceptance="not_entered",
                accepted=False,
                human_minutes=None,
                rework_minutes=None,
                wall_minutes=None,
                model_cost_units=None,
            ),
            record(
                observation_id="OBS-005",
                comparison_arm="ai_assisted",
                result="unknown",
                completion_mode="not_applicable",
                first_acceptance="not_entered",
                accepted=False,
                human_minutes=None,
                rework_minutes=None,
                wall_minutes=None,
                model_cost_units=None,
            ),
            record(
                observation_id="OBS-006",
                attempt_state="not_attempted",
                result="not_applicable",
                completion_mode="not_applicable",
                first_acceptance="not_entered",
                accepted=False,
                human_minutes=None,
                rework_minutes=None,
                wall_minutes=None,
                model_cost_units=None,
            ),
            record(
                observation_id="OBS-007",
                attempt_state="unknown",
                result="unknown",
                completion_mode="not_applicable",
                first_acceptance="not_entered",
                accepted=False,
                human_minutes=None,
                rework_minutes=None,
                wall_minutes=None,
                model_cost_units=None,
            ),
        ]
        report = build_observation_report(records)
        totals = report["totals"]
        self.assertEqual(totals["records"], 7)
        self.assertEqual(totals["attempted"], 5)
        self.assertEqual(totals["completed"], 2)
        self.assertEqual(totals["failed"], 1)
        self.assertEqual(totals["abandoned"], 1)
        self.assertEqual(totals["result_unknown"], 1)
        self.assertEqual(totals["not_attempted"], 1)
        self.assertEqual(totals["attempt_state_unknown"], 1)
        self.assertEqual(totals["independent"], 1)
        self.assertEqual(totals["assisted"], 1)
        self.assertEqual(totals["entered_first_acceptance"], 2)
        self.assertEqual(totals["accepted_outputs"], 2)
        self.assertEqual(card(report, "task_completion_rate"), {"value": 0.4, "sample_size": 5, "status": "ok"})
        self.assertEqual(card(report, "independent_completion_rate"), {"value": 0.5, "sample_size": 2, "status": "ok"})
        self.assertEqual(card(report, "first_acceptance_pass_rate"), {"value": 1.0, "sample_size": 2, "status": "ok"})

        active = measure(report, "human_active_minutes", "ai_assisted")
        self.assertEqual(active["known_count"], 1)
        self.assertEqual(active["records_unknown"], 3)
        self.assertEqual(active["median"], 15)
        wall = measure(report, "wall_minutes", "ai_assisted")
        self.assertEqual(wall["known_count"], 1)
        self.assertEqual(wall["records_unknown"], 3)

        cost = report["measurements"]["model_cost_per_accepted_output"]
        self.assertIsNone(cost["value"])
        self.assertEqual(cost["sample_size"], 1)
        self.assertEqual(cost["known_cost_units"], 10)
        self.assertEqual(cost["unknown_cost_records"], 2)
        self.assertEqual(cost["status"], "incomplete")

    def test_cohort_comparison_is_explicit_and_observation_only(self) -> None:
        records = [
            record(observation_id="OBS-M1", cohort_id="TASK-A", human_minutes=60, rework_minutes=10, wall_minutes=90),
            record(
                observation_id="OBS-A1",
                cohort_id="TASK-A",
                comparison_arm="ai_assisted",
                first_acceptance="failed",
                accepted=False,
                human_minutes=15,
                rework_minutes=20,
                wall_minutes=40,
                model_cost_units=8,
            ),
            record(
                observation_id="OBS-A2",
                cohort_id="TASK-B",
                comparison_arm="ai_assisted",
                human_minutes=5,
                rework_minutes=0,
                wall_minutes=10,
                model_cost_units=2,
            ),
        ]
        report = build_observation_report(records)
        self.assertEqual([item["cohort_id"] for item in report["cohorts"]], ["TASK-A", "TASK-B"])
        task_a = report["cohorts"][0]["report"]
        comparison = task_a["comparison"]
        self.assertEqual(comparison["human_active_minutes_delta"], 35.0)
        self.assertEqual(comparison["wall_minutes_delta"], 50.0)
        self.assertEqual(comparison["status"], "observation_only")
        cost = task_a["measurements"]["model_cost_per_accepted_output"]
        self.assertEqual(cost["status"], "insufficient_data")
        self.assertIsNone(cost["value"])

    def test_unknown_ai_cost_does_not_fake_per_accepted_cost(self) -> None:
        records = [
            record(observation_id="OBS-C1", comparison_arm="ai_assisted", model_cost_units=4),
            record(
                observation_id="OBS-C2",
                comparison_arm="ai_assisted",
                result="failed",
                completion_mode="not_applicable",
                first_acceptance="not_entered",
                accepted=False,
                model_cost_units=None,
            ),
        ]
        report = build_observation_report(records)
        cost = report["measurements"]["model_cost_per_accepted_output"]
        self.assertIsNone(cost["value"])
        self.assertEqual(cost["status"], "incomplete")
        self.assertEqual(cost["known_cost_units"], 4)
        self.assertEqual(cost["unknown_cost_records"], 1)

    def assert_invalid(self, overrides: dict[str, Any], field: str) -> None:
        with self.assertRaises(ObservationError) as caught:
            build_observation_report([record(**overrides)])
        error = caught.exception.args[0]
        self.assertEqual(error["code"], "invalid_record")
        self.assertEqual(error["field"], field)
        self.assertNotIn(json.dumps(overrides), json.dumps(error))

    def test_completed_without_completion_mode_is_rejected(self) -> None:
        self.assert_invalid({"result": "completed", "completion_mode": "unknown"}, "completion_mode")

    def test_uncompleted_acceptance_is_rejected(self) -> None:
        self.assert_invalid({"result": "failed", "completion_mode": "not_applicable", "first_acceptance": "passed"}, "first_acceptance")

    def test_acceptance_decision_mismatch_is_rejected(self) -> None:
        self.assert_invalid({"first_acceptance": "passed", "accepted": False}, "accepted")

    def test_negative_human_minutes_are_rejected(self) -> None:
        self.assert_invalid({"human_minutes": -1}, "human_minutes")

    def test_boolean_model_cost_is_rejected(self) -> None:
        self.assert_invalid({"model_cost_units": True}, "model_cost_units")

    def test_nonfinite_model_cost_is_rejected(self) -> None:
        self.assert_invalid({"model_cost_units": math.inf}, "model_cost_units")

    def test_manual_model_cost_is_rejected(self) -> None:
        self.assert_invalid({"comparison_arm": "manual", "model_cost_units": 2}, "model_cost_units")

    def test_unknown_field_is_rejected_without_echoing_free_text(self) -> None:
        secret = "participant@example.com"
        with self.assertRaises(ObservationError) as caught:
            build_observation_report([record(contact=secret)])
        error = caught.exception.args[0]
        self.assertEqual(error["code"], "invalid_record")
        self.assertEqual(error["field"], "record")
        self.assertNotIn(secret, str(caught.exception))

    def test_cli_reads_json_and_writes_only_aggregates(self) -> None:
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False)
        try:
            json.dump([record(observation_id="OBS-CLI")], handle)
            handle.close()
            exit_code, output = cli_output(["--input", handle.name])
            payload = json.loads(output)
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["totals"]["records"], 1)
            self.assertEqual(payload["totals"]["accepted_outputs"], 1)
            self.assertNotIn("OBS-CLI", output)
        finally:
            os.unlink(handle.name)

    def test_cli_invalid_input_exits_two_without_value_echo(self) -> None:
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", delete=False)
        try:
            json.dump([record(human_minutes=-9)], handle)
            handle.close()
            exit_code, output = cli_output(["--input", handle.name])
            payload = json.loads(output)
            self.assertEqual(exit_code, 2)
            self.assertEqual(payload["error"]["code"], "invalid_record")
            self.assertEqual(payload["error"]["field"], "human_minutes")
            self.assertNotIn("-9", output)
        finally:
            os.unlink(handle.name)

    def test_missing_and_unattempted_measurements_report_fixed_fields(self) -> None:
        incomplete = {key: value for key, value in record().items() if key != "cohort_id"}
        with self.assertRaises(ObservationError) as caught:
            build_observation_report([incomplete])
        self.assertEqual(caught.exception.args[0]["field"], "cohort_id")

        invalid = record(
            attempt_state="not_attempted",
            result="not_applicable",
            completion_mode="not_applicable",
            first_acceptance="not_entered",
            accepted=False,
            human_minutes=30,
        )
        with self.assertRaises(ObservationError) as caught:
            build_observation_report([invalid])
        self.assertEqual(caught.exception.args[0]["field"], "human_minutes")

    def test_comparison_has_no_cross_arm_model_cost_delta(self) -> None:
        report = build_observation_report([record()])
        cohort_report = report["cohorts"][0]["report"]
        self.assertNotIn("model_cost_delta_units", cohort_report["comparison"])
        self.assertEqual(cohort_report["comparison"]["status"], "observation_only")

    def test_global_report_never_compares_distinct_cohorts(self) -> None:
        records = [
            record(observation_id="OBS-MG", cohort_id="TASK-A", human_minutes=60, rework_minutes=0, wall_minutes=90),
            record(
                observation_id="OBS-AG",
                cohort_id="TASK-B",
                comparison_arm="ai_assisted",
                result="failed",
                completion_mode="not_applicable",
                first_acceptance="not_entered",
                accepted=False,
                human_minutes=5,
                rework_minutes=0,
                wall_minutes=10,
                model_cost_units=2,
            ),
        ]
        report = build_observation_report(records)
        self.assertNotIn("comparison", report)
        self.assertNotIn("human_active_minutes_delta", json.dumps(report["totals"]))

    def test_output_contains_counts_and_median_but_not_record_values(self) -> None:
        report = build_observation_report([record(human_minutes=17, rework_minutes=3, wall_minutes=29)])
        text = json.dumps(report)
        self.assertNotIn("known_values", text)
        self.assertNotEqual(17, report["measurements"]["human_active_minutes"]["manual"]["known_count"])
        self.assertEqual(report["measurements"]["human_active_minutes"]["manual"]["known_count"], 1)
        self.assertEqual(report["measurements"]["human_active_minutes"]["manual"]["median"], 20)

    def test_contact_like_identifier_is_rejected(self) -> None:
        with self.assertRaises(ObservationError) as caught:
            build_observation_report([record(observation_id="participant@example.com")])
        self.assertEqual(caught.exception.args[0]["field"], "observation_id")

    def test_extreme_integer_is_a_fixed_record_error(self) -> None:
        with self.assertRaises(ObservationError) as caught:
            build_observation_report([record(model_cost_units=10**10000, comparison_arm="ai_assisted")])
        self.assertEqual(caught.exception.args[0]["field"], "model_cost_units")

if __name__ == "__main__":
    unittest.main()




