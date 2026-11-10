"""诊断评测批跑纯函数库测试（T-07/T-09；脚本层位于 scripts/，经 importlib 直载）。

覆盖：考卷拆分（首屏/诊断 + 自由文本落位 + 未知槽位拒绝）、参考材料装配
（通用措辞小节 + 缺答案 fail-closed）、期望带解析、run 目录与指纹、曲线聚合
与渲染（**双版本标签纪律** + 元验证闸呈现 + insufficient_data 语义 + 断点节）。

测试全部用**合成卡**——零真实案例材料（答案内容只存在于真相层与本测的假件）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "diagnostic_eval"
    / "eval_lib.py"
)
_spec = importlib.util.spec_from_file_location("diagnostic_eval_lib", _SCRIPT)
assert _spec is not None and _spec.loader is not None
eval_lib = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("diagnostic_eval_lib", eval_lib)
_spec.loader.exec_module(eval_lib)

SLOT_KEYS = {
    "first_screen": {"org.industry", "org.scale", "pol.qualification"},
    "diagnostic": {"biz.pain_stage", "ctx.free_text", "sys.systems"},
}


def _fixture(case_id: str = "demo-1") -> dict[str, Any]:
    return {
        "case_id": case_id,
        "sim_input": {
            "questionnaire_slots": {
                "org.industry": "制造与工业",
                "org.scale": "20–99人",
                "biz.pain_stage": "财务与内部流程",
                "sys.systems": ["ERP", "OA"],
            },
            "free_text_pain": "报销建单都是人来做，新来的不会就问老人。",
            "imperfection_notes": "刻意保留不完美",
        },
    }


def _card(case_id: str = "demo-1") -> dict[str, Any]:
    return {
        "case_id": case_id,
        "company_profile": {"industry": "制造", "scale": "中小", "anonymized": True},
        "ground_truth": {
            "problems_expected": ["人工建单易错", "系统数据互不相通", "经验依赖个人"],
            "solution_direction": "保留既有系统只读集成，以业务对象为主线串联",
            "result": "试点后单据处理时长下降（案例披露口径）",
            "human_boundary": "人定规则与拍板，机器跑采集与核对",
            "fde_actions_expected": ["采集脚本", "对账清单"],
            "must_not_hallucinate": ["企业未上 MES", "未见自建中台"],
        },
    }


# ── 考卷拆分 ─────────────────────────────────────────────────────────


def test_split_fixture_answers_separates_first_screen_and_diagnostic() -> None:
    first, diag = eval_lib.split_fixture_answers(_fixture(), slot_keys=SLOT_KEYS)
    assert first == {"org.industry": "制造与工业", "org.scale": "20–99人"}
    assert diag["biz.pain_stage"] == "财务与内部流程"
    assert diag["sys.systems"] == ["ERP", "OA"]
    assert diag["ctx.free_text"] == "报销建单都是人来做，新来的不会就问老人。"


def test_split_without_free_text_leaves_slot_absent() -> None:
    fixture = _fixture()
    fixture["sim_input"].pop("free_text_pain")
    _, diag = eval_lib.split_fixture_answers(fixture, slot_keys=SLOT_KEYS)
    assert "ctx.free_text" not in diag


def test_split_rejects_unknown_slot_keys() -> None:
    fixture = _fixture()
    fixture["sim_input"]["questionnaire_slots"]["hacker.field"] = "x"
    with pytest.raises(SystemExit) as caught:
        eval_lib.split_fixture_answers(fixture, slot_keys=SLOT_KEYS)
    assert "hacker.field" in str(caught.value)


def test_split_rejects_overlapping_slot_key_sets() -> None:
    overlap = {
        "first_screen": {"org.industry"},
        "diagnostic": {"org.industry"},
    }
    with pytest.raises(SystemExit) as caught:
        eval_lib.split_fixture_answers(_fixture(), slot_keys=overlap)
    assert "org.industry" in str(caught.value)


# ── 考卷适配（口语原话值 → 生产问卷闭集） ─────────────────────────────


def test_apply_answer_mapping_maps_placeholder_and_multi() -> None:
    mapping = {
        "org.industry": {"kind": "choice", "values": {"德国零部件制造": "制造与工业"}},
        "org.scale": {"kind": "choice", "values": {"（未填写）": None, "小工厂": "20–99人"}},
        "sys.systems": {"kind": "multi", "values": {"OA 和 ERP 都上有": ["OA 和 ERP 都上有"]}},
        "biz.cycle_time": {"kind": "free", "values": {"（未填写）": None}},
        "org.main_business": {"kind": "free", "values": {}},
    }
    out = eval_lib.apply_answer_mapping(
        "c1",
        {
            "org.industry": "德国零部件制造",
            "org.scale": "（未填写）",
            "sys.systems": "OA 和 ERP 都上有",
            "biz.cycle_time": "（未填写）",
            "org.main_business": "外贸出口，客户主要靠海外买家询盘",
        },
        mapping,
    )
    assert out["org.industry"] == "制造与工业"
    assert out["sys.systems"] == ["OA 和 ERP 都上有"]
    assert out["org.main_business"] == "外贸出口，客户主要靠海外买家询盘"  # free 原文直通
    assert "org.scale" not in out and "biz.cycle_time" not in out  # 占位符 → 省略


def test_apply_answer_mapping_unmapped_choice_value_fails_closed() -> None:
    mapping = {"org.industry": {"kind": "choice", "values": {"A": "制造与工业"}}}
    with pytest.raises(SystemExit) as caught:
        eval_lib.apply_answer_mapping("c1", {"org.industry": "没登记过的行业"}, mapping)
    assert "未登记映射" in str(caught.value)
    assert "没登记过的行业" in str(caught.value)


def test_apply_answer_mapping_missing_slot_rule_fails_closed() -> None:
    with pytest.raises(SystemExit) as caught:
        eval_lib.apply_answer_mapping("c1", {"biz.pain_stage": "获客"}, {})
    assert "缺映射规则" in str(caught.value)


def test_apply_answer_mapping_overrides_fill_required_and_remove() -> None:
    mapping = {
        "org.scale": {"kind": "choice", "values": {"（未填写）": None}},
        "biz.pain_stage": {"kind": "choice", "values": {"获客": "获客与销售"}},
    }
    out = eval_lib.apply_answer_mapping(
        "c1",
        {"org.scale": "（未填写）", "biz.pain_stage": "获客"},
        mapping,
        overrides={"org.scale": "20–99人", "biz.pain_stage": None},
    )
    assert out["org.scale"] == "20–99人"  # 必答槽位考官补填
    assert "biz.pain_stage" not in out  # override null=移除


# ── 参考材料装配 ─────────────────────────────────────────────────────


def test_reference_material_renders_all_sections_with_generic_labels() -> None:
    text = eval_lib.build_reference_material(_card())
    for needle in (
        "企业背景",
        "关键问题清单",
        "1. 人工建单易错",
        "参考方案方向",
        "结果口径",
        "人机边界要点",
        "交付动作参考",
        "禁编造清单",
        "1. 企业未上 MES",
    ):
        assert needle in text


def test_reference_material_without_profile() -> None:
    text = eval_lib.build_reference_material(_card(), include_profile=False)
    assert "企业背景" not in text
    assert "关键问题清单" in text


def test_reference_material_missing_ground_truth_block_fails_closed() -> None:
    card = _card()
    del card["ground_truth"]
    with pytest.raises(SystemExit):
        eval_lib.build_reference_material(card)


def test_reference_material_empty_card_fails_closed() -> None:
    card = {"case_id": "hollow", "ground_truth": {}}
    with pytest.raises(SystemExit):
        eval_lib.build_reference_material(card)


# ── 期望带与 run 目录 ────────────────────────────────────────────────


def test_parse_band() -> None:
    assert eval_lib.parse_band("78 – 98") == (78.0, 98.0)
    assert eval_lib.parse_band("70-95") == (70.0, 95.0)
    with pytest.raises(SystemExit):
        eval_lib.parse_band("一个数字都没有")


def test_run_dir_validates_run_id(tmp_path: Path) -> None:
    assert eval_lib.run_dir(tmp_path, "2026-11-11").name == "2026-11-11"
    assert eval_lib.run_dir(tmp_path, "ev1").name == "ev1"
    for bad in ("../escape", "", "a/b", "带 空格"):
        with pytest.raises(SystemExit):
            eval_lib.run_dir(tmp_path, bad)


# ── 曲线聚合与渲染 ───────────────────────────────────────────────────


def _write_run(root: Path, run_id: str, with_scores: bool, usable: bool = True) -> None:
    run_out = root / "eval-runs" / run_id
    run_out.mkdir(parents=True, exist_ok=True)
    eval_lib.write_json(
        run_out / "run.json",
        {
            "run_id": run_id,
            "eval_set_version": run_id,
            "created_at": f"2026-11-1{len(run_id)}T00:00:00+00:00",
            "prompt_version": "diagnostic-report-prompt-v1",
            "report_version": "diagnostic-report-v1",
            "judge_version": "rubric-v0.1" if with_scores else None,
            "cases": {"demo-1": {"report_file": "reports/demo-1.json"}},
        },
    )
    if with_scores:
        eval_lib.write_json(
            run_out / "scores.json",
            {
                "run_id": run_id,
                "judge_version": "rubric-v0.1",
                "meta_gate": {
                    "verdict": "pass" if usable else "fail",
                    "anchors": [
                        {"anchor_id": "A1", "total": 95, "expected_band": "78–98", "in_band": usable}
                    ],
                    "counterexamples": [{"case_id": "X1", "blocked": True}],
                },
                "usable_as_evolution_evidence": usable,
                "cases": {
                    "demo-1": {
                        "dimensions": {
                            "problem_coverage": 30,
                            "solution_alignment": 22,
                            "omission_hallucination": 15,
                            "actionability": 9,
                        },
                        "total": 76,
                        "verdict": "conditional",
                        "score_invalid": False,
                    }
                },
            },
        )


def test_aggregate_runs_orders_and_flags_half_state(tmp_path: Path) -> None:
    _write_run(tmp_path, "r2", with_scores=True)
    _write_run(tmp_path, "r1", with_scores=False)
    runs = eval_lib.aggregate_runs(tmp_path)
    assert [item["run_id"] for item in runs] == ["r1", "r2"]  # 按 created_at 稳定序
    assert runs[0]["scores"] is None
    assert runs[1]["scores"]["meta_gate"]["verdict"] == "pass"


def test_curve_md_empty_runs_is_insufficient_data(tmp_path: Path) -> None:
    text = eval_lib.render_curve_md([], doc_number=1)
    assert "insufficient_data" in text
    assert "评分曲线 1" in text


def test_curve_md_carries_double_version_labels_and_scores(tmp_path: Path) -> None:
    _write_run(tmp_path, "r1", with_scores=True)
    runs = eval_lib.aggregate_runs(tmp_path)
    text = eval_lib.render_curve_md(runs, doc_number=2)
    # 双版本标签：eval_set_version 与 prompt_version 同列呈现
    assert "`r1`" in text and "`diagnostic-report-prompt-v1`" in text
    assert "可作进化判定输入" in text
    assert "元验证闸" in text
    # 逐卡四维表
    for needle in ("①覆盖/40", "②方向/30", "③遗漏幻觉/20", "④落地/10", "**76**", "conditional"):
        assert needle in text
    # 阈值未校准声明 + 无报告正文
    assert "不校准" in text
    assert "刻意保留不完美" not in text  # 输入内容不进曲线文档
    assert "报销建单" not in text


def test_curve_md_marks_unusable_when_meta_gate_failed(tmp_path: Path) -> None:
    _write_run(tmp_path, "r1", with_scores=True, usable=False)
    runs = eval_lib.aggregate_runs(tmp_path)
    text = eval_lib.render_curve_md(runs, doc_number=1)
    assert "否（元验证未过）" in text


def test_curve_md_breakpoints_section(tmp_path: Path) -> None:
    text = eval_lib.render_curve_md(
        [], doc_number=3, breakpoints=["rubric v0.1（2026-11-11）：C1–C4 修订"]
    )
    assert "版本断点" in text
    assert "rubric v0.1（2026-11-11）：C1–C4 修订" in text


def test_write_and_sha256_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "x.json"
    eval_lib.write_json(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    digest = eval_lib.file_sha256(path)
    assert len(digest) == 64 and digest == eval_lib.file_sha256(path)
