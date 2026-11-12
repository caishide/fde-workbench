# -*- coding: utf-8 -*-
"""训练场 run 分布读数库测试（L 线 L2 轮；脚本层位于 scripts/，经 importlib 直载）。

覆盖：轴定义与分组（逐场景三轴／锚点两轴）、三条机械不变量（失败/缺分run
不是 0 分是无数据；hard_fail 行排除；n<2 不编造 stdev）、判定规则语义
（严格大于／insufficient_data／本线规则号）、eval_lib 复用单一真身。

测试全部用**合成记录**——零真实案例材料（批跑正文与判卷基准只存在于真相层，
仓库侧只有分数与轴值；设计稿 `docs/audit/交付案例学习闭环-三缺口设计稿-2026-11-11.md` §2.2）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "simulation"
    / "run_distributions.py"
)
_spec = importlib.util.spec_from_file_location("simulation_run_distributions", _SCRIPT)
assert _spec is not None and _spec.loader is not None
run_distributions = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("simulation_run_distributions", run_distributions)
_spec.loader.exec_module(run_distributions)


def _record(
    run_id: str,
    scenario_key: str,
    *,
    status: str = "succeeded",
    error: dict | None = None,
    degraded: bool = False,
    scenario_version: int = 2,
    rubric_version: str = "rubric-v1",
    adapter_mode: str = "mock",
    evaluator_version: str = "rules-evaluator@rubric-v1",
    total: float | None = 80.0,
    verdict: str = "pass",
) -> dict:
    layers: dict = {}
    if status == "succeeded" and not degraded:
        row: dict = {"total_score": total, "verdict": verdict, "evaluator_id": evaluator_version.split("@")[0]}
        if total is None:
            row.pop("total_score")
        layers = {"deterministic": dict(row), "model": dict(row)}
    return {
        "run_id": run_id,
        "run_key": f"{scenario_key}:normal:v{scenario_version}:seed42:a1:cfg0",
        "scenario_key": scenario_key,
        "scenario_version": scenario_version,
        "variant": "normal",
        "split": "train",
        "adapter_mode": adapter_mode,
        "seed": 42,
        "attempt": 1,
        "status": status,
        "error": error,
        "degraded": degraded,
        "evaluation": {
            "rubric_version": rubric_version,
            "evaluator_version": evaluator_version,
            "layers": layers,
        },
    }


# ---------------------------------------------------------------------------
# 登记与 fail-closed
# ---------------------------------------------------------------------------


def test_rule_id_registered_and_carried_in_summary():
    assert run_distributions.RULE_ID == "delta-noise-band-simulation-2026-11-12"
    summary = run_distributions.collect_distributions([_record("r1", "S-A")])
    assert summary["rule_id"] == run_distributions.RULE_ID
    verdict = run_distributions.decide_pair(1.0, {"n": 3, "range": 1.0}, {"n": 3, "range": 1.0})
    assert verdict["rule_id"] == run_distributions.RULE_ID


def test_unknown_layer_fails_closed():
    with pytest.raises(SystemExit):
        run_distributions.collect_distributions([_record("r1", "S-A")], layer="judge")


def test_eval_lib_reuse_single_source_stats():
    # 复用证明：分布读数与 eval_lib 逐位一致（不复制实现）。
    stats = run_distributions.collect_distributions(
        [_record(f"r{i}", "S-A", total=70 + i) for i in range(3)]
    )["scenario_groups"]["2|rubric-v1|mock"]["scenario_scores"]["S-A"]
    reference = __import__("eval_lib").distribution_stats([70.0, 71.0, 72.0])
    assert stats == reference


# ---------------------------------------------------------------------------
# 分组轴
# ---------------------------------------------------------------------------


def test_scenario_group_axes_same_axes_same_group():
    records = [
        _record("r1", "S-A", adapter_mode="mock"),
        _record("r2", "S-A", adapter_mode="mock"),
    ]
    summary = run_distributions.collect_distributions(records)
    assert list(summary["scenario_groups"]) == ["2|rubric-v1|mock"]
    assert summary["scenario_groups"]["2|rubric-v1|mock"]["scenario_scores"]["S-A"]["n"] == 2


def test_scenario_group_axes_adapter_split():
    records = [
        _record("r1", "S-A", adapter_mode="mock"),
        _record("r2", "S-A", adapter_mode="real"),
    ]
    summary = run_distributions.collect_distributions(records)
    assert set(summary["scenario_groups"]) == {"2|rubric-v1|mock", "2|rubric-v1|real"}
    for group in summary["scenario_groups"].values():
        assert group["scenario_scores"]["S-A"]["n"] == 1


def test_anchor_groups_merge_within_axes_split_across_axes():
    records = [
        _record("a1", "ANCHOR-1", total=80.0),
        _record("a2", "ANCHOR-1", total=82.0),
        # 换评估器版本 ⇒ 另一组（锚点可跨 run 合并、不可跨轴合并）。
        _record("a3", "ANCHOR-1", total=90.0, evaluator_version="rules-evaluator@rubric-v2", rubric_version="rubric-v2"),
    ]
    summary = run_distributions.collect_distributions(records, anchor_keys=["ANCHOR-1"])
    groups = summary["anchor_groups"]
    assert set(groups) == {"rubric-v1|rules-evaluator@rubric-v1", "rubric-v2|rules-evaluator@rubric-v2"}
    assert groups["rubric-v1|rules-evaluator@rubric-v1"]["anchor_scores"]["anchor"]["n"] == 2
    assert groups["rubric-v2|rules-evaluator@rubric-v2"]["anchor_scores"]["anchor"]["n"] == 1


def test_anchor_keys_subset_routing():
    records = [_record("a1", "ANCHOR-1"), _record("r1", "S-A")]
    summary = run_distributions.collect_distributions(records, anchor_keys=["ANCHOR-1"])
    # 归属不串：锚点键只进锚点分支，其余只进逐场景分支。
    assert summary["anchor_groups"]
    scenario_names = [
        name
        for group in summary["scenario_groups"].values()
        for name in (group.get("scenario_scores") or {})
    ]
    assert scenario_names == ["S-A"]
    assert "ANCHOR-1" not in scenario_names


# ---------------------------------------------------------------------------
# 机械不变量
# ---------------------------------------------------------------------------


def test_failed_run_is_no_data_not_zero():
    records = [
        _record("r1", "S-A"),
        _record("r2", "S-A", status="failed", error={"code": "adapter_unavailable"}),
        _record("r3", "S-A", degraded=True),
    ]
    summary = run_distributions.collect_distributions(records)
    group = summary["scenario_groups"]["2|rubric-v1|mock"]
    assert group["scenario_scores"]["S-A"]["n"] == 1
    assert summary["excluded_rows"]["failed_runs"] == 2
    assert group["runs"] == ["r1"]


def test_missing_or_hardfail_score_rows_are_no_data():
    records = [
        _record("r1", "S-A", total=None),
        _record("r2", "S-A", verdict="hard_fail"),
        _record("r3", "S-A"),
    ]
    summary = run_distributions.collect_distributions(records)
    group = summary["scenario_groups"]["2|rubric-v1|mock"]
    assert group["scenario_scores"]["S-A"]["n"] == 1
    assert summary["excluded_rows"]["score_rows"] == 2


def test_stdev_not_fabricated_for_n1():
    stats = run_distributions.collect_distributions([_record("r1", "S-A")])[
        "scenario_groups"
    ]["2|rubric-v1|mock"]["scenario_scores"]["S-A"]
    assert stats["n"] == 1
    assert stats["stdev"] is None


# ---------------------------------------------------------------------------
# 判定规则（语义照搬 eval_lib：严格大于／insufficient_data）
# ---------------------------------------------------------------------------


def _dist(values: list[float]) -> dict:
    import eval_lib

    return eval_lib.distribution_stats(values)


def test_decidable_requires_strict_greater():
    # |Δ| > 噪声带（极差较大者）⇒ 可判定。
    a = _dist([80.0, 81.0, 82.0])  # 极差 2
    b = _dist([90.0, 91.0, 92.0])  # 极差 2；Δ=10 > 2
    verdict = run_distributions.decide_pair(10.0, a, b)
    assert verdict["decidable"] is True
    assert verdict["reason"] == ""
    # 恰等于噪声带 ⇒ 落噪声域（严格大于）。
    c = _dist([80.0, 81.0, 84.0])  # 极差 4
    d = _dist([84.0, 85.0, 88.0])  # 极差 4；Δ=4 == 带宽
    verdict = run_distributions.decide_pair(4.0, c, d)
    assert verdict["decidable"] is False
    assert verdict["reason"] == "within_noise"


def test_insufficient_data_is_not_undecidable():
    a = _dist([80.0, 81.0])
    b = _dist([95.0, 96.0])
    verdict = run_distributions.decide_pair(15.0, a, b)
    assert verdict["decidable"] is None
    assert verdict["reason"] == "insufficient_data"


def test_decide_against_anchor_pairs_and_no_anchor_reason():
    records = [
        # 锚点 n=3（达最小样本）
        *[_record(f"a{i}", "ANCHOR-1", total=80.0 + i) for i in range(3)],
        # 逐场景 n=2（不足 ⇒ insufficient_data）
        *[_record(f"r{i}", "S-A", total=90.0 + i) for i in range(2)],
    ]
    summary = run_distributions.collect_distributions(records, anchor_keys=["ANCHOR-1"])
    verdicts = run_distributions.decide_against_anchor(summary)
    assert len(verdicts) == 1
    assert verdicts[0]["decidable"] is None
    assert verdicts[0]["reason"] == "insufficient_data"

    empty = run_distributions.collect_distributions([_record("r1", "S-A")])
    verdicts = run_distributions.decide_against_anchor(empty)
    assert verdicts[0]["reason"] == "no_anchor_distribution"


def test_render_summary_md_contains_rule_and_tables():
    records = [
        *[_record(f"a{i}", "ANCHOR-1", total=80.0 + i) for i in range(3)],
        *[_record(f"r{i}", "S-A", total=90.0 + i) for i in range(2)],
    ]
    summary = run_distributions.collect_distributions(records, anchor_keys=["ANCHOR-1"])
    verdicts = run_distributions.decide_against_anchor(summary)
    text = run_distributions.render_summary_md(summary, verdicts)
    assert run_distributions.RULE_ID in text
    assert "insufficient_data" in text
    assert "failed_runs=0 / score_rows=0 / anchor_rows=0" in text
