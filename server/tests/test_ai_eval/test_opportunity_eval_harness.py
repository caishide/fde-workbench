"""机会识别 golden set 真模型评测 harness（N4 G-10）——协议 v0 形状与三道
insufficient_data 闸。

钉住：①报告形状（协议 v0 §2 字段在场、口径=simulation）；②凭据缺席 ⇒
insufficient_data（kpi 不编造）；③oracle 重放失败 ⇒ insufficient_data（环境
坏不出分）；④error 行不是 0 分（真模型腿存在 error ⇒ insufficient）；
⑤incidents 非空 ⇒ uplift ≤ 0（一票封顶）；⑥PASS 线截断语义（7/9 不四舍
五入过线）；⑦离线腿零模型调用（结构/格式/上限类不烧 token）。
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from conftest import SERVER_ROOT

_HARNESS_PATH = SERVER_ROOT.parent / "scripts" / "ai_eval" / "run_opportunity_eval.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("run_opportunity_eval", _HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def harness():
    return _load_harness()


class _FakeClient:
    """可编程假模型客户端：按 case 名返回脚本化产出或抛错。"""

    def __init__(self, script: dict[str, object], calls: list[str]):
        self._script = script
        self._calls = calls

    def complete_json(self, *, messages, request_id, max_tokens=8192, purpose=None, **_):
        assert purpose, "N2 纪律：AI 调用点必须显式传 purpose"
        self._calls.append(request_id)
        action = self._script.get(request_id)
        if isinstance(action, Exception):
            raise action
        if action is not None:
            return action
        return self._default_output


def _compliant_output(case: dict) -> dict:
    """从夹具 forms 构造完全合规产出（引文逐字＋零 PII）。"""
    first_answer = case["forms"][0]["answers"][0]
    candidate = {
        "name": f"机会-{case['name'][:12]}",
        "description": str(first_answer["value"]),
        "target_audience": "相关岗位",
        "next_action": "先做现状核实",
        "priority": "medium",
        "risk_level": "medium",
        "business_value_score": 3,
        "feasibility_score": 3,
        "data_readiness_score": 3,
        "research_answers": {},
        "evidence": [
            {
                "form_id": case["forms"][0]["form_id"],
                "form_name": case["forms"][0]["form_name"],
                "field_key": first_answer["field_key"],
                "question": str(first_answer.get("question", "")),
                "answer_excerpt": str(first_answer["value"]),
                "reason": "逐字摘录",
            }
        ],
    }
    return {"candidates": [candidate]}


def _fake_factory(script: dict[str, object]):
    calls: list[str] = []

    def factory(live_cases):
        keyed = {}
        for case in live_cases:
            keyed[f"ai-eval-{harness_sha16(case['name'])}"] = script.get(
                case["name"], _compliant_output(case)
            )
        return _FakeClient(keyed, calls)

    factory.calls = calls  # type: ignore[attr-defined]
    return factory


def harness_sha16(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def test_report_schema_protocol_fields(harness):
    report = harness.run_eval(client_factory=_fake_factory({}))
    for field in (
        "protocol", "engine_version", "seed", "口径", "generated_at",
        "golden_set", "assumptions", "per_case", "kpi", "kpi_baseline",
        "kpi_oracle", "uplift", "uplift_bounded", "pass_line", "incidents",
        "verdict",
    ):
        assert field in report, field
    assert report["protocol"] == "delivery-effect-eval-v0"
    assert report["口径"] == "simulation"
    assert report["kpi_baseline"] == 0.0 and report["kpi_oracle"] == 1.0
    assert report["pass_line"] == 0.8
    assert report["verdict"] == "pass"
    assert report["kpi"] == 1.0 and report["uplift_bounded"] == 1.0
    assert report["golden_set"]["cases_total"] == 23
    assert report["golden_set"]["live_cases"] == 9
    # 全合规假客户端 ⇒ 每例引文逐字独立复核成立。
    live_rows = [row for row in report["per_case"] if row["mode"] == "live_model"]
    assert len(live_rows) == 9 and all(row["status"] == "pass" for row in live_rows)


def test_no_credentials_is_insufficient_without_fabricated_score(harness):
    report = harness.run_eval(api_key=None, client_factory=None)
    assert report["verdict"] == "insufficient_data"
    assert "model_credentials_absent" in report["reason"]
    assert report["kpi"] is None and report["uplift_bounded"] is None


def test_oracle_replay_failure_is_insufficient(harness, tmp_path):
    golden = json.loads(harness.FIXTURE_PATH.read_text(encoding="utf-8"))
    golden["cases"][0]["expect"] = {"kept": 99}  # 篡改期望 ⇒ 重放必不匹配
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(golden, ensure_ascii=False), encoding="utf-8")
    report = harness.run_eval(
        fixture_path=broken, api_key="present", client_factory=_fake_factory({})
    )
    assert report["verdict"] == "insufficient_data"
    assert "oracle_replay_failed" in report["reason"]
    assert report["kpi"] is None


def test_error_row_is_insufficient_not_zero(harness):
    """真模型腿存在 error ⇒ error 行不是 0 分、是无数据（round16 纪律）。"""
    golden = json.loads(harness.FIXTURE_PATH.read_text(encoding="utf-8"))
    live_names = [case["name"] for case in golden["cases"] if case["kind"] in harness.LIVE_KINDS]
    script = {live_names[0]: RuntimeError("ai_timeout simulated")}
    report = harness.run_eval(api_key="present", client_factory=_fake_factory(script))
    assert report["verdict"] == "insufficient_data"
    assert "live_leg_errors=1" in report["reason"]
    assert report["kpi"] is None


def test_incident_caps_uplift_at_zero(harness):
    golden = json.loads(harness.FIXTURE_PATH.read_text(encoding="utf-8"))
    live_names = [case["name"] for case in golden["cases"] if case["kind"] in harness.LIVE_KINDS]
    leaky = _compliant_output(next(
        case for case in golden["cases"] if case["name"] == live_names[0]
    ))
    leaky["candidates"][0]["description"] = "联系人 13812345678 请致电"
    script = {live_names[0]: leaky}
    report = harness.run_eval(api_key="present", client_factory=_fake_factory(script))
    assert report["incidents"], "PII 事件必须被抓到"
    assert report["uplift_bounded"] <= 0, "incidents 非空 ⇒ uplift ≤ 0（一票封顶）"
    assert report["verdict"] == "below_pass_line"


def test_pass_line_truncates_instead_of_rounding(harness):
    golden = json.loads(harness.FIXTURE_PATH.read_text(encoding="utf-8"))
    live_names = [case["name"] for case in golden["cases"] if case["kind"] in harness.LIVE_KINDS]
    # 7/9 = 0.7777…：四舍五入到两位是 0.78，仍 < 0.8；用 8/9=0.8888 过线、
    # 7/9 不过线验证「截断不抬分」语义。
    script = {name: {"candidates": []} for name in live_names[:2]}
    report7 = harness.run_eval(api_key="present", client_factory=_fake_factory(script))
    # 7/9 = 0.77777… 截断为 0.7777（不四舍五入成 0.7778 抬分）⇒ 低于 PASS 线。
    assert report7["kpi"] == harness._trunc4(7 / 9) == 0.7777
    assert report7["verdict"] == "below_pass_line"
    script = {name: {"candidates": []} for name in live_names[:1]}
    report8 = harness.run_eval(api_key="present", client_factory=_fake_factory(script))
    assert report8["verdict"] == "pass"
    assert harness._trunc4(0.79999) == 0.7999


def test_offline_leg_never_calls_model(harness):
    factory = _fake_factory({})
    harness.run_eval(client_factory=factory)
    # 9 例真模型腿各一次调用；结构/格式/上限 14 例零调用。
    assert len(factory.calls) == 9


def test_empty_candidates_fail_but_do_not_count_as_incident(harness):
    """模型产出空候选 ⇒ 每例 fail（kept=0）；零 PII 事件；kpi=0 ⇒ below_pass_line。"""
    golden = json.loads(harness.FIXTURE_PATH.read_text(encoding="utf-8"))
    live_names = [case["name"] for case in golden["cases"] if case["kind"] in harness.LIVE_KINDS]
    script = {name: {"candidates": []} for name in live_names}
    report = harness.run_eval(api_key="present", client_factory=_fake_factory(script))
    live_rows = [row for row in report["per_case"] if row["mode"] == "live_model"]
    assert all(row["status"] == "fail" for row in live_rows)
    assert all(row["detail"] == "no_usable_candidates" for row in live_rows)
    assert report["incidents"] == []
    assert report["kpi"] == 0.0
    assert report["uplift_bounded"] == 0.0
    assert report["verdict"] == "below_pass_line"
