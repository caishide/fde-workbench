"""AE2-WP5 评分器：落盘复合任务记录 → 逐条断言判定 → 指标与 Wilson 区间。

纪律（沿 AE1 05:41/05:54/05:47/05:66，引擎与组件**只读复用零改动**）：
- 断言求值复用 ``ae_eval.assertions.evaluate_all_detailed``（冻结文法零改动）
  与 ``AssertionOutcome``（判定＋文法错误登记位）；
- 分母纪律：不得事后改分母——所有运行全部计入；``expected_runs`` 分母锚不符
  即顶层 ``denominator_mismatch`` 显著标注（分母本身不改）；
- 报告口径：唯一任务数与运行次数分列；
- 比例区间：95% Wilson（小样本稳健）。

AE2 指标（复合任务面）：
- ``task_success_rate``：通过全部必需断言的运行数 / 运行总数；
- ``idempotency_rate``：任务内复放槽（replay2/replay3）快照与首次**运行级一致**
  的比例（execution_id 不新分配且 status 同——B7 逐字一致的机读代理；
  逐字节等值由 WP3 单元钉 B7 覆盖）；
- ``rollback_zero_residual_rate``：存在补偿过程（``attempts.first.rollback``
  非 null）的运行中残留为空的比例——「回滚零遗留」的机读锚（残留逐条诚实
  登记的语义由 WP3 单元钉 B3/B5/B6 覆盖）。

本模块是**纯函数面**（无 DB / 无网络）：落盘记录进、指标出。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ae_eval.assertions import evaluate_all_detailed
from ae_eval.records import RunRecord
from ae_eval.scorer import AssertionOutcome, MetricSummary, wilson_interval

__all__ = ["TaskScore", "score_records"]


@dataclass
class TaskScore:
    """一个复合任务（一次运行）的判定结果（沿 AE1 TaskScore 同构）。"""

    task_id: str
    run_index: int
    outcomes: list[AssertionOutcome] = field(default_factory=list)
    note: str = ""
    known_task: bool = True

    @property
    def passed(self) -> bool:
        """全部断言同时为真＝该次运行通过（断言数为 0＝不通过——证据缺失不得静默通过）。"""
        return bool(self.outcomes) and all(outcome.passed for outcome in self.outcomes)

    @property
    def failed_expressions(self) -> list[str]:
        return [outcome.expression for outcome in self.outcomes if not outcome.passed]

    @property
    def syntax_errors(self) -> list[str]:
        return [outcome.expression for outcome in self.outcomes if outcome.error is not None]

    def to_json(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "run_index": self.run_index,
            "passed": self.passed,
            "known_task": self.known_task,
            "failed_expressions": self.failed_expressions,
            "syntax_errors": self.syntax_errors,
            "note": self.note,
            "assertions": [
                {"expression": outcome.expression, "passed": outcome.passed, "error": outcome.error}
                for outcome in self.outcomes
            ],
        }


def _load_taskset(taskset_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(taskset_path).read_text(encoding="utf-8"))


def _replay_consistent(record: RunRecord, slot: str) -> bool:
    """复放槽与首次运行级一致（execution_id 不新分配且 status 同）。"""
    first = record.attempts.get("first") or {}
    attempt = record.attempts.get(slot)
    if attempt is None or not first:
        return False
    return (
        attempt.get("execution_id") == first.get("execution_id")
        and attempt.get("status") == first.get("status")
    )


def score_records(
    records: list[RunRecord],
    taskset_path: str | Path,
    *,
    expected_runs: int | None = None,
) -> dict[str, Any]:
    """落盘记录 × 冻结复合任务集 → 逐条判定 + 指标 + 报告数据（AE2 版）。"""
    taskset = _load_taskset(taskset_path)
    assertions_by_task: dict[str, list[str]] = {
        str(task["id"]): list(task["assertions"]) for task in taskset["tasks"]
    }

    scores: list[TaskScore] = []
    for record in records:
        expressions = assertions_by_task.get(record.task_id)
        known_task = expressions is not None
        if expressions is None:
            expressions = []  # 任务集外 ID：零断言 ⇒ 不通过，且 note 明示（沿 AE1 补强 G3-22）
        outcomes = [
            AssertionOutcome(expression=expression, passed=passed, error=error)
            for expression, passed, error in evaluate_all_detailed(expressions, record.envelope())
        ]
        note = record.note
        if not known_task:
            note = f"{note} unknown_task_id:任务集外任务 ID（无断言可判）".strip()
        scores.append(
            TaskScore(
                task_id=record.task_id,
                run_index=record.run_index,
                outcomes=outcomes,
                note=note,
                known_task=known_task,
            )
        )

    total_runs = len(scores)
    passed_runs = sum(1 for score in scores if score.passed)
    unique_tasks = len({score.task_id for score in scores})

    # 幂等率：任务内复放槽与首次运行级一致（execution_id 不新分配＋status 同）。
    replay_checks = 0
    replay_passed = 0
    for record in records:
        for slot in ("replay2", "replay3"):
            if record.attempts.get(slot) is None:
                continue
            replay_checks += 1
            if _replay_consistent(record, slot):
                replay_passed += 1

    # 回滚零遗留率：存在补偿过程的运行中，残留为空的比例（诚实登记的语义由
    # WP3 单元钉覆盖——此处只钉「评测面生产运行残留为空」）。
    rollback_runs = 0
    rollback_clean = 0
    for record in records:
        first = record.attempts.get("first") or {}
        rollback = first.get("rollback")
        if rollback is None:
            continue
        rollback_runs += 1
        residual = rollback.get("residual")
        if isinstance(residual, list) and not residual:
            rollback_clean += 1

    metrics = [
        MetricSummary(
            name="task_success_rate",
            numerator=passed_runs,
            denominator=total_runs,
            note="通过全部必需断言的运行数 / 预登记运行总数（05:54 不许改分母）",
        ),
        MetricSummary(
            name="idempotency_rate",
            numerator=replay_passed,
            denominator=replay_checks,
            note="复放槽与首次运行级一致（execution_id 不新分配且 status 同）的比例——B7 逐字节等值由 WP3 单元钉覆盖",
        ),
        MetricSummary(
            name="rollback_zero_residual_rate",
            numerator=rollback_clean,
            denominator=rollback_runs,
            note="存在补偿过程的运行中残留为空的比例（54 号 §5.2 B2 回滚零遗留机读锚）",
        ),
    ]

    result: dict[str, Any] = {
        "taskset": {
            "version": taskset.get("version"),
            "status": taskset.get("status"),
            "task_count": len(taskset["tasks"]),
            "assertion_count": sum(len(task["assertions"]) for task in taskset["tasks"]),
            "hidden_slots": taskset.get("hidden_ratio", {}).get("hidden_count"),
        },
        "counts": {
            "unique_task_count": unique_tasks,
            "run_count": total_runs,
            "assertion_evaluations": sum(len(score.outcomes) for score in scores),
            "note": "唯一任务数与运行次数分列（05:47：同一任务重复 3 次不等于 3 个业务案例）",
        },
        "task_scores": [score.to_json() for score in scores],
        "metrics": [metric.to_json() for metric in metrics],
        "failed_task_scores": [score.to_json() for score in scores if not score.passed],
    }
    if expected_runs is not None and total_runs != expected_runs:
        result["denominator_mismatch"] = {
            "expected_runs": expected_runs,
            "actual_runs": total_runs,
            "note": "预登记运行总数与落盘记录数不符——分母未改（05:54），本标注须人工复核后方可采信报告",
        }
    return result


# wilson_interval 经 ae_eval.scorer 复用（零改动）——显式登记以防误删
_ = wilson_interval
