"""Summarize synthetic capacity traces from one load level without connecting to the application."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import stat
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_OFFSET_MS = 2**53 - 1
CHAINS = ("open_project", "save_research_plan", "background_generation", "evidence_approval")
OUTCOMES = ("succeeded", "recovered", "failed", "incomplete")
PHASES = ("request", "queue", "execution", "human_wait")
SAMPLE_FIELDS = {"chain", "outcome", *PHASES}


class TraceError(ValueError):
    def __init__(self, code: str, *, name: str | None = None, index: int | None = None):
        super().__init__(code)
        self.payload: dict[str, str | int] = {"error": code}
        if name is not None:
            self.payload["field"] = name
        if index is not None:
            self.payload["index"] = index


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise TraceError("duplicate_key")
        obj[key] = value
    return obj


def _reject_constant(_: str) -> None:
    raise TraceError("invalid_json")


def read_trace(path: Path) -> Any:
    if path.drive.startswith(("\\\\", "//")):
        raise TraceError("invalid_input_path")
    try:
        if not stat.S_ISREG(path.stat().st_mode):
            raise TraceError("invalid_input_path")
        with path.open("rb") as source:
            document = source.read(MAX_INPUT_BYTES + 1)
    except OSError:
        raise TraceError("input_unreadable") from None
    if len(document) > MAX_INPUT_BYTES:
        raise TraceError("input_too_large")
    try:
        return json.loads(
            document.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except TraceError:
        raise
    except (ValueError, RecursionError):
        raise TraceError("invalid_json") from None


def _interval_total(intervals: Any, name: str, index: int) -> int:
    if not isinstance(intervals, list):
        raise TraceError("invalid_intervals", name=name, index=index)
    previous_end = total = 0
    for pair in intervals:
        if not isinstance(pair, list) or len(pair) != 2:
            raise TraceError("invalid_intervals", name=name, index=index)
        start, end = pair
        if type(start) is not int or type(end) is not int or not (
            previous_end <= start <= end <= MAX_OFFSET_MS
        ):
            raise TraceError("invalid_intervals", name=name, index=index)
        total += end - start
        previous_end = end
    return total


@dataclass
class PhaseStats:
    durations: list[int] = field(default_factory=list)
    missing: int = 0
    not_applicable: int = 0

    def add(self, intervals: Any, phase: str, index: int) -> None:
        if intervals is None:
            self.missing += 1
        elif isinstance(intervals, list) and not intervals:
            self.not_applicable += 1
        else:
            self.durations.append(_interval_total(intervals, phase, index))

    def summarize(self) -> dict[str, int | None]:
        values = sorted(self.durations)
        count = len(values)
        return {
            "measured": count,
            "missing": self.missing,
            "not_applicable": self.not_applicable,
            "p50_ms": values[(50 * count + 99) // 100 - 1] if count else None,
            "p95_ms": values[(95 * count + 99) // 100 - 1] if count else None,
            "max_ms": values[-1] if count else None,
        }


def build_capacity_report(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or set(document) != {"schema_version", "samples"}:
        raise TraceError("invalid_document_fields")
    version = document["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise TraceError("unsupported_schema")
    samples = document["samples"]
    if not isinstance(samples, list):
        raise TraceError("invalid_samples")

    by_outcome = {chain: dict.fromkeys(OUTCOMES, 0) for chain in CHAINS}
    by_phase = {chain: {phase: PhaseStats() for phase in PHASES} for chain in CHAINS}
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict) or set(sample) != SAMPLE_FIELDS:
            raise TraceError("invalid_sample_fields", index=index)
        chain, outcome = sample["chain"], sample["outcome"]
        if chain not in CHAINS:
            raise TraceError("invalid_enum", name="chain", index=index)
        if outcome not in OUTCOMES:
            raise TraceError("invalid_enum", name="outcome", index=index)
        by_outcome[chain][outcome] += 1
        for phase in PHASES:
            by_phase[chain][phase].add(sample[phase], phase, index)

    return {
        "schema_version": SCHEMA_VERSION,
        "chains": {
            chain: {
                "samples": sum(by_outcome[chain].values()),
                "outcomes": by_outcome[chain],
                "phases": {phase: stats.summarize() for phase, stats in by_phase[chain].items()},
            }
            for chain in CHAINS
        },
    }


class TraceArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise TraceError("invalid_arguments")


def main() -> int:
    parser = TraceArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="Local JSON trace from one isolated load level")
    try:
        args = parser.parse_args()
        report = build_capacity_report(read_trace(args.trace))
    except TraceError as error:
        print(json.dumps(error.payload))
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
