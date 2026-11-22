"""Offline, privacy-gated rollup for R2/R3 observation records.

The public contract is docs/optimization/R3-AI净收益观察汇总规格.md.  This module
is deliberately independent from the server and production data: it only reads a
closed JSON shape supplied by an authorized operator and never emits record ids,
free text, credentials, or per-record measurement values.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

SCHEMA_VERSION = 1
_RECORD_KEYS = {
    "observation_id",
    "cohort_id",
    "comparison_arm",
    "attempt_state",
    "result",
    "completion_mode",
    "first_acceptance",
    "accepted",
    "human_minutes",
    "rework_minutes",
    "wall_minutes",
    "model_cost_units",
}
_ARMS = ("manual", "ai_assisted")
_ATTEMPT_STATES = ("attempted", "not_attempted", "unknown")
_RESULTS = ("completed", "failed", "abandoned", "unknown", "not_applicable")
_COMPLETION_MODES = ("independent", "assisted", "not_applicable")
_FIRST_ACCEPTANCE = ("passed", "failed", "unknown", "not_entered")
_MEASUREMENT_KEYS = (
    "human_minutes",
    "rework_minutes",
    "wall_minutes",
    "model_cost_units",
)


class ObservationError(ValueError):
    """A fixed-code validation error; the offending value is never carried."""

    def __init__(self, field: str, reason: str, record_index: int | None = None):
        super().__init__(
            {
                "code": "invalid_record",
                "field": field,
                "reason": reason,
                "record_index": record_index,
            }
        )
        self.field = field
        self.reason = reason


def _code(value: Any, field: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,79}", value) is None:
        raise ObservationError(field, "invalid_code_identifier")
    return value


def _enum(value: Any, field: str, choices: Sequence[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ObservationError(field, "invalid_enum")
    return value


def _optional_number(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationError(field, "invalid_number")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise ObservationError(field, "invalid_number") from None
    if not math.isfinite(number) or number < 0:
        raise ObservationError(field, "invalid_number")
    return number


def _validate_record(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ObservationError("record", "not_object")
    unknown_keys = set(raw) - _RECORD_KEYS
    if unknown_keys:
        raise ObservationError("record", "unknown_field", index)
    missing_keys = _RECORD_KEYS - set(raw)
    if missing_keys:
        raise ObservationError(sorted(missing_keys)[0], "missing_field", index)

    attempt_state = _enum(raw["attempt_state"], "attempt_state", _ATTEMPT_STATES)
    result = _enum(raw["result"], "result", _RESULTS)
    completion_mode = _enum(
        raw["completion_mode"], "completion_mode", _COMPLETION_MODES
    )
    first_acceptance = _enum(
        raw["first_acceptance"], "first_acceptance", _FIRST_ACCEPTANCE
    )
    arm = _enum(raw["comparison_arm"], "comparison_arm", _ARMS)
    accepted = raw["accepted"]
    if not isinstance(accepted, bool):
        raise ObservationError("accepted", "invalid_boolean")

    if attempt_state == "attempted":
        if result == "not_applicable":
            raise ObservationError("result", "attempted_without_result")
    else:
        expected_result = (
            "not_applicable" if attempt_state == "not_attempted" else "unknown"
        )
        if result != expected_result:
            raise ObservationError("result", "unattempted_result_mismatch")

    if result == "completed":
        if completion_mode not in ("independent", "assisted"):
            raise ObservationError("completion_mode", "completed_mode_missing")
    elif completion_mode != "not_applicable":
        raise ObservationError("completion_mode", "incomplete_mode_present")

    if result == "completed":
        if first_acceptance == "not_entered":
            raise ObservationError("first_acceptance", "completed_without_acceptance")
    elif first_acceptance != "not_entered":
        raise ObservationError("first_acceptance", "uncompleted_acceptance_present")

    expected_accepted = first_acceptance == "passed"
    if accepted != expected_accepted:
        raise ObservationError("accepted", "acceptance_mismatch")

    if attempt_state != "attempted":
        for key in _MEASUREMENT_KEYS:
            if raw[key] is not None:
                raise ObservationError(key, "unattempted_measurement_present")

    measurements: dict[str, float | None] = {
        key: _optional_number(raw[key], key) for key in _MEASUREMENT_KEYS
    }
    if arm == "manual" and measurements["model_cost_units"] is not None:
        raise ObservationError("model_cost_units", "manual_cost_not_applicable")

    return {
        "observation_id": _code(raw["observation_id"], "observation_id"),
        "cohort_id": _code(raw["cohort_id"], "cohort_id"),
        "comparison_arm": arm,
        "attempt_state": attempt_state,
        "result": result,
        "completion_mode": completion_mode,
        "first_acceptance": first_acceptance,
        "accepted": accepted,
        **measurements,
    }


def _rate(value: float | None, sample_size: int) -> dict[str, Any]:
    if sample_size == 0 or value is None:
        return {
            "value": None,
            "sample_size": sample_size,
            "status": "insufficient_data",
        }
    return {"value": round(value, 4), "sample_size": sample_size, "status": "ok"}


def _time_metric(
    values: Sequence[float | None], *, not_applicable: int = 0
) -> dict[str, Any]:
    known = [float(value) for value in values if value is not None]
    return {
        "known_count": len(known),
        "records_unknown": sum(1 for value in values if value is None) - not_applicable,
        "records_not_applicable": not_applicable,
        "median": round(median(known), 4) if known else None,
    }


def _empty_totals() -> dict[str, int]:
    return {
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
    }


def _arm_measurements(records: Sequence[dict[str, Any]], arm: str) -> dict[str, Any]:
    values = {
        "human_minutes": [
            record["human_minutes"]
            for record in records
            if record["comparison_arm"] == arm
        ],
        "rework_minutes": [
            record["rework_minutes"]
            for record in records
            if record["comparison_arm"] == arm
        ],
        "wall_minutes": [
            record["wall_minutes"]
            for record in records
            if record["comparison_arm"] == arm
        ],
    }
    active: list[float | None] = []
    for record in records:
        if record["comparison_arm"] != arm:
            continue
        if record["human_minutes"] is None or record["rework_minutes"] is None:
            active.append(None)
        else:
            active.append(record["human_minutes"] + record["rework_minutes"])
    arm_records = [record for record in records if record["comparison_arm"] == arm]
    manual_not_applicable = len(arm_records) if arm == "manual" else 0
    return {
        "human_active_minutes": _time_metric(active),
        "rework_minutes": _time_metric(values["rework_minutes"]),
        "wall_minutes": _time_metric(values["wall_minutes"]),
        "model_cost_units": _time_metric(
            [record["model_cost_units"] for record in arm_records],
            not_applicable=manual_not_applicable,
        ),
    }


def _model_cost_per_accepted_output(
    records: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    ai_records = [
        record for record in records if record["comparison_arm"] == "ai_assisted"
    ]
    accepted_outputs = sum(1 for record in ai_records if record["accepted"])
    costs = [record["model_cost_units"] for record in ai_records]
    known_cost = sum(float(value) for value in costs if value is not None)
    unknown_cost = sum(1 for value in costs if value is None)
    if accepted_outputs == 0:
        status = "insufficient_data"
    elif unknown_cost:
        status = "incomplete"
    else:
        status = "ok"
    value = (
        known_cost / accepted_outputs if accepted_outputs and not unknown_cost else None
    )
    return {
        "value": round(value, 4) if value is not None else None,
        "sample_size": accepted_outputs,
        "known_cost_units": round(known_cost, 4),
        "unknown_cost_records": unknown_cost,
        "status": status,
    }


def _summarize(records: Sequence[dict[str, Any]], *, include_comparison: bool = False) -> dict[str, Any]:
    totals = _empty_totals()
    totals["records"] = len(records)
    for record in records:
        if record["attempt_state"] == "attempted":
            totals["attempted"] += 1
            if record["result"] == "completed":
                totals["completed"] += 1
            elif record["result"] == "failed":
                totals["failed"] += 1
            elif record["result"] == "abandoned":
                totals["abandoned"] += 1
            else:
                totals["result_unknown"] += 1
        elif record["attempt_state"] == "not_attempted":
            totals["not_attempted"] += 1
        else:
            totals["attempt_state_unknown"] += 1

        if record["completion_mode"] == "independent":
            totals["independent"] += 1
        elif record["completion_mode"] == "assisted":
            totals["assisted"] += 1

        if record["first_acceptance"] != "not_entered":
            totals["entered_first_acceptance"] += 1
            if record["first_acceptance"] == "passed":
                totals["first_acceptance_passed"] += 1
            elif record["first_acceptance"] == "failed":
                totals["first_acceptance_failed"] += 1
            else:
                totals["first_acceptance_unknown"] += 1
        if record["accepted"]:
            totals["accepted_outputs"] += 1

    completion_denominator = totals["attempted"]
    independent_denominator = totals["completed"]
    acceptance_denominator = totals["entered_first_acceptance"]
    rates = {
        "task_completion_rate": _rate(
            totals["completed"] / completion_denominator
            if completion_denominator
            else None,
            completion_denominator,
        ),
        "independent_completion_rate": _rate(
            totals["independent"] / independent_denominator
            if independent_denominator
            else None,
            independent_denominator,
        ),
        "first_acceptance_pass_rate": _rate(
            totals["first_acceptance_passed"] / acceptance_denominator
            if acceptance_denominator
            else None,
            acceptance_denominator,
        ),
    }
    manual = _arm_measurements(records, "manual")
    ai = _arm_measurements(records, "ai_assisted")
    comparison = {
        "human_active_minutes_delta": (
            round(
                manual["human_active_minutes"]["median"]
                - ai["human_active_minutes"]["median"],
                4,
            )
            if manual["human_active_minutes"]["median"] is not None
            and ai["human_active_minutes"]["median"] is not None
            else None
        ),
        "wall_minutes_delta": (
            round(manual["wall_minutes"]["median"] - ai["wall_minutes"]["median"], 4)
            if manual["wall_minutes"]["median"] is not None
            and ai["wall_minutes"]["median"] is not None
            else None
        ),
        "status": "observation_only",
    }
    report = {
        "totals": totals,
        "rates": rates,
        "measurements": {
            "human_active_minutes": {
                "manual": manual["human_active_minutes"],
                "ai_assisted": ai["human_active_minutes"],
            },
            "rework_minutes": {
                "manual": manual["rework_minutes"],
                "ai_assisted": ai["rework_minutes"],
            },
            "wall_minutes": {
                "manual": manual["wall_minutes"],
                "ai_assisted": ai["wall_minutes"],
            },
            "model_cost_units": {
                "manual": manual["model_cost_units"],
                "ai_assisted": ai["model_cost_units"],
            },
            "model_cost_per_accepted_output": _model_cost_per_accepted_output(records),
        },
    }
    if include_comparison:
        report["comparison"] = comparison
    return report


def build_observation_report(
    raw_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    records = []
    for index, raw in enumerate(raw_records):
        try:
            records.append(_validate_record(raw, index))
        except ObservationError as error:
            raise ObservationError(error.field, error.reason, index) from None
    cohorts: list[dict[str, Any]] = []
    for cohort_id in dict.fromkeys(record["cohort_id"] for record in records):
        cohort_records = [
            record for record in records if record["cohort_id"] == cohort_id
        ]
        cohorts.append({"cohort_id": cohort_id, "report": _summarize(cohort_records, include_comparison=True)})
    return {
        "schema_version": SCHEMA_VERSION,
        "interpretation": "observation_only",
        **_summarize(records, include_comparison=False),
        "cohorts": cohorts,
    }


def _parse_records(text: str) -> list[Any]:
    value = json.loads(text)
    if not isinstance(value, list):
        raise ValueError("not_list")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate closed-shape observation JSON."
    )
    parser.add_argument("--input", required=True, help="JSON file path, or - for stdin")
    args = parser.parse_args(argv)
    try:
        if args.input == "-":
            raw_records = _parse_records(sys.stdin.read())
        else:
            raw_records = _parse_records(Path(args.input).read_text(encoding="utf-8"))
        report = build_observation_report(raw_records)
    except ObservationError as error:
        print(json.dumps({"error": error.args[0]}, ensure_ascii=False))
        return 2
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        print(
            json.dumps(
                {
                    "error": {
                        "code": "invalid_input",
                        "field": "input",
                        "reason": "unreadable_or_invalid",
                    }
                },
                ensure_ascii=False,
            )
        )
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


