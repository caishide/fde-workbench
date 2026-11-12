"""交付效果评测协议 v0：机会识别 golden set 真模型评测（AI 原生化 N4，G-10）。

**非必需观察轮**（任务书 D-6 缺省）：本 harness 产出的 uplift 报告只做观察
证据，**不是任何门禁**——PASS 阈值未用我方自身数据校准（协议 v0 纪律：阈值
数字为上游参考值），攒够样本前不转必需、不进 PR gate。

评测对象：``server/tests/fixtures/ai/opportunity_golden_set.json``（23 例）。
两腿：
- **离线腿（oracle 重放）**：全部 23 例按夹具既有期望重放生产后处理管线
  （``_normalize_candidates``）——这是协议 v0 §1「oracle 可回放」的机械验证：
  重放不匹配 ⇒ 环境已坏 ⇒ 整份报告 ``insufficient_data``（不编造分数）；
- **真模型腿**（citation 6＋pseudonym 3＝9 例）：对每例用生产提示词装配
  （``build_ai_opportunity_messages``）连真模型，原始产出过同一生产管线：
  通过 = kept≥1 ∧ 引文逐字（独立复核）∧ 原始产出零 PII 事件。结构/格式/上限
  三类（14 例）是纯后处理确定性用例，不涉模型——留离线腿。

算分（协议 v0 §1）：``kpi``＝真模型腿通过率；``kpi_baseline``＝0（do_nothing
＝无 AI 产出）；``kpi_oracle``＝1（完全合规产出，重放已验证可回放）；
``uplift``＝(kpi−0)/(1−0)；分数**截断不四舍五入**；PASS 线 0.8；``incidents``
非空 ⇒ uplift ≤ 0（一票封顶）；``uplift_bounded``＝max(−1, uplift)。

insufficient_data（协议 v0：无 oracle/不出分）：①oracle 重放失败 ②模型凭据
缺席 ③真模型腿存在未响应例（error 行不是 0 分、是无数据——round16 纪律）。

模型凭据（CI/本地）：``FDE_DEEPSEEK_API_KEY``（缺席＝insufficient_data，
job 保持绿）；可选 ``FDE_DEEPSEEK_BASE_URL`` / ``FDE_DEEPSEEK_AI_OPPORTUNITY_MODEL``
/ ``FDE_DEEPSEEK_TIMEOUT_SECONDS``。★供应商红线：只允许按量付费 key。
提示词正文不入库不入报告（N6 纪律）：报告只带 system 串 sha256 指纹。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "server" / "src"))

from fde_api.ai.ai_opportunity_prompt import build_ai_opportunity_messages  # noqa: E402
from fde_api.ai.ai_opportunity_service import _normalize_candidates  # noqa: E402
from fde_api.ai.deepseek import DeepSeekClient  # noqa: E402

FIXTURE_PATH = _REPO_ROOT / "server" / "tests" / "fixtures" / "ai" / "opportunity_golden_set.json"
ENGINE_VERSION = "opportunity-eval-v0"
PASS_LINE = 0.8
# 真模型腿（citation+pseudonym）共 9 例；观察轮要求全响应（缺一即 insufficient）。
LIVE_KINDS = ("citation", "pseudonym")
PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_TIMEOUT_SECONDS = 90


def _trunc4(value: float) -> float:
    """协议 v0：分数截断不四舍五入（4 位小数，防 0.7999 侥幸过线）。"""
    return math.floor(value * 10000) / 10000


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _offline_replay(case: dict[str, Any]) -> dict[str, Any]:
    """离线腿：夹具既有期望重放生产后处理管线（oracle 可回放性验证）。"""
    raw: Any = {"candidates": [case["candidate"]]} if case["candidate"] is not None else {"candidates": "broken"}
    expect = case["expect"]
    try:
        if expect.get("error"):
            from fde_api.ai.ai_opportunity_service import AIOpportunityDiscoveryError

            try:
                _normalize_candidates(raw, case["forms"], format_only=expect.get("format_only", False))
            except AIOpportunityDiscoveryError as error:
                status = "ok" if error.code == expect["error"] else "oracle_mismatch"
                detail = "" if status == "ok" else f"error {error.code} != {expect['error']}"
                return {"name": case["name"], "kind": case["kind"], "mode": "offline_replay", "status": status, "detail": detail}
            return {"name": case["name"], "kind": case["kind"], "mode": "offline_replay", "status": "oracle_mismatch", "detail": "expected error not raised"}
        candidates = _normalize_candidates(raw, case["forms"], format_only=expect.get("format_only", False))
        status = "ok" if len(candidates) == expect["kept"] else "oracle_mismatch"
        detail = "" if status == "ok" else f"kept {len(candidates)} != {expect['kept']}"
        return {"name": case["name"], "kind": case["kind"], "mode": "offline_replay", "status": status, "detail": detail}
    except Exception as error:  # noqa: BLE001 - 重放意外异常＝环境坏
        return {"name": case["name"], "kind": case["kind"], "mode": "offline_replay", "status": "oracle_mismatch", "detail": f"unexpected: {error}"}


def _context_for(case: dict[str, Any]) -> dict[str, Any]:
    """用夹具 forms 装配与生产完全同形的 context（build_ai_opportunity_messages 输入）。"""
    return {
        "project": {"name": "golden-set-eval", "enterprise_code": "GOLDEN-SET"},
        "scope": {"subject_id": "golden-set-subject", "subject_type": "enterprise", "name": "golden-set"},
        "included_forms": list(case["forms"]),
        "included_memos": [],
        "existing_opportunities": [],
        "user_guidance": "",
        "guidance_source": None,
        "expand": True,
    }


def _verbatim_ok(candidate: dict[str, Any], forms: list[dict[str, Any]]) -> bool:
    """引文逐字独立复核：每条 evidence.answer_excerpt 必须逐字出自来源 answers.value。"""
    source_values = {
        str(answer.get("value", ""))
        for form in forms
        for answer in (form.get("answers") or [])
    }
    for evidence in candidate.get("evidence") or []:
        excerpt = str(evidence.get("answer_excerpt", ""))
        if excerpt and excerpt not in source_values:
            return False
    return True


def _run_live_case(case: dict[str, Any], client: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"name": case["name"], "kind": case["kind"], "mode": "live_model"}
    messages = build_ai_opportunity_messages(_context_for(case))
    request_id = f"ai-eval-{_sha16(case['name'])}"
    try:
        raw = client.complete_json(messages=messages, request_id=request_id, max_tokens=8192, purpose="opportunity_discovery")
    except Exception as error:  # noqa: BLE001 - error 行不是 0 分，是无数据
        row["status"] = "error"
        row["detail"] = f"{type(error).__name__}: {error}"[:200]
        return row
    raw_text = json.dumps(raw, ensure_ascii=False)
    incidents = [match for match in PHONE_PATTERN.findall(raw_text)]
    kept = _normalize_candidates(dict(raw), case["forms"])
    if not kept:
        row["status"] = "fail"
        row["detail"] = "no_usable_candidates" + ("; pii_incident" if incidents else "")
    elif not all(_verbatim_ok(candidate, case["forms"]) for candidate in kept):
        row["status"] = "fail"
        row["detail"] = "citation_not_verbatim"
    elif incidents:
        row["status"] = "fail"
        row["detail"] = "pseudonym_leak_incident"
    else:
        row["status"] = "pass"
        row["detail"] = f"kept={len(kept)}"
    row["incidents"] = incidents
    return row


def run_eval(
    *,
    fixture_path: Path | None = None,
    api_key: str | None = None,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    client_factory: Callable[[list[dict[str, str]]], Any] | None = None,
) -> dict[str, Any]:
    """跑完整评测并返回协议 v0 形状的报告（client_factory 仅供测试注入假客户端）。"""
    fixture_path = fixture_path or FIXTURE_PATH
    golden = json.loads(fixture_path.read_text(encoding="utf-8"))
    cases = list(golden["cases"])
    live_cases = [case for case in cases if case["kind"] in LIVE_KINDS]
    offline_cases = [case for case in cases if case["kind"] not in LIVE_KINDS]

    offline_rows = [_offline_replay(case) for case in cases]
    replay_ok = all(row["status"] == "ok" for row in offline_rows)
    system_fingerprint = _sha16(build_ai_opportunity_messages(_context_for(cases[0]))[0]["content"])

    report: dict[str, Any] = {
        "protocol": "delivery-effect-eval-v0",
        "engine_version": ENGINE_VERSION,
        "seed": 0,
        "口径": "simulation",
        "generated_at": datetime.now(UTC).isoformat(),
        "model": model,
        # 该提示词是函数内联串、无注册版本标签（N6 注册表纪律）——报告带指纹
        # 不编造版本号；提示词正文一字节不入报告。
        "prompt_fingerprint": system_fingerprint,
        "golden_set": {
            "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
            "cases_total": len(cases),
            "live_cases": len(live_cases),
            "offline_cases": len(offline_cases),
        },
        "assumptions": {
            "baseline": "do_nothing＝无 AI 候选产出＝0",
            "oracle": "完全合规产出＝1；离线腿黄金候选重放验证 oracle 可回放",
            "scoring": "真模型腿＝原始产出过生产后处理管线 kept≥1 ∧ 引文逐字 ∧ 零 PII 事件",
            "pass_line_source": "协议 v0 §1 上游参考值——未用我方数据校准，观察轮不设门禁",
        },
        "per_case": offline_rows,
        "kpi": None,
        "kpi_baseline": 0.0,
        "kpi_oracle": 1.0,
        "uplift": None,
        "uplift_bounded": None,
        "pass_line": PASS_LINE,
        "incidents": [],
        "verdict": "insufficient_data",
        "reason": "",
    }

    def _insufficient(reason: str) -> dict[str, Any]:
        report["reason"] = reason
        return report

    if not replay_ok:
        return _insufficient("oracle_replay_failed：离线腿期望重放不匹配＝评测环境已坏，不出分")
    if client_factory is None and not api_key:
        return _insufficient("model_credentials_absent：未配置 FDE_DEEPSEEK_API_KEY，真模型腿不跑、不编造分数")

    client = client_factory(list(live_cases)) if client_factory else DeepSeekClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    live_rows = [_run_live_case(case, client) for case in live_cases]
    report["per_case"] = live_rows + offline_rows
    errors = [row for row in live_rows if row["status"] == "error"]
    incidents = [row["name"] for row in live_rows if row.get("incidents")]
    report["incidents"] = [
        {"case": name, "type": "pseudonym_leak", "detail": "真模型腿原始产出命中手机号形态"}
        for name in incidents
    ]
    if errors:
        return _insufficient(f"live_leg_errors={len(errors)}：error 行不是 0 分、是无数据（round16 纪律）")

    passed = sum(1 for row in live_rows if row["status"] == "pass")
    kpi = passed / len(live_rows) if live_rows else 0.0
    uplift = _trunc4((kpi - report["kpi_baseline"]) / (report["kpi_oracle"] - report["kpi_baseline"]))
    if incidents:
        uplift = min(uplift, 0.0)
    uplift_bounded = max(-1.0, uplift)
    report.update(
        {
            "kpi": _trunc4(kpi),
            "uplift": uplift,
            "uplift_bounded": uplift_bounded,
            "verdict": "pass" if uplift_bounded >= PASS_LINE else "below_pass_line",
            "reason": "",
        }
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="机会识别 golden set 真模型评测（协议 v0，非必需观察轮）")
    parser.add_argument("--output", type=Path, default=None, help="报告 JSON 落盘路径（缺省只打印）")
    args = parser.parse_args()
    api_key = os.environ.get("FDE_DEEPSEEK_API_KEY") or ""
    report = run_eval(
        api_key=api_key or None,
        base_url=os.environ.get("FDE_DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL,
        model=os.environ.get("FDE_DEEPSEEK_AI_OPPORTUNITY_MODEL") or DEFAULT_MODEL,
        timeout_seconds=int(os.environ.get("FDE_DEEPSEEK_TIMEOUT_SECONDS") or DEFAULT_TIMEOUT_SECONDS),
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    print(
        f"verdict={report['verdict']} uplift_bounded={report['uplift_bounded']} "
        f"reason={report['reason']}",
        file=sys.stderr,
    )
    # 观察轮：任何 verdict 都不算失败——报告即证据（harness 自身崩溃才会非零退出）。
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
