"""交付案例导入转换器测试（L 线 L1 轮；脚本层位于 scripts/，经 importlib 直载）。

覆盖：允许名单 fail-closed（未知键/attribution 缺项）、scenario_key_mismatch
同服务端语义、生产闸门（validate_scenario + 三视图泄漏自检）、输出落点仓内
拒绝、批次与 manifest 形状、真相层实卡验收（不在场显式 skip 不静默绿）。

测试全部用**合成卡**——零真实案例材料（判卷基准内容只存在于真相层与本地
导入包，仓库侧只有指针＋sha256；任务书 `docs/audit/交付案例学习闭环-L1任务书-2026-11-12.md`）。
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
    / "simulation"
    / "import_cases.py"
)
_spec = importlib.util.spec_from_file_location("simulation_case_import", _SCRIPT)
assert _spec is not None and _spec.loader is not None
import_cases = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("simulation_case_import", import_cases)
_spec.loader.exec_module(import_cases)

# 真相层实卡目录（L1 首批；不在场 ⇒ skip——不静默绿）
TRUTH_CARDS_DIR = Path(r"D:\test\FDE\knowledge\交付场景导入包\cards")


def _demo_card(card_id: str = "IMP-DEMO-01") -> dict[str, Any]:
    """合成导入卡：内容全为演示假件，形状与训练场种子同构。"""
    return {
        "card_id": card_id,
        "card_version": "import-card-v1",
        "generated_at": "2026-11-12",
        "attribution": {
            "source_type": "synthetic_test",
            "source_pointer": "truth-layer://demo/demo-card.json",
            "license": "合成演示件",
            "snapshot_date": "2026-11-12",
            "rewritten": True,
            "rewrite_declaration": "测试合成卡，非任何真实案例材料。",
            "attribution_line": "合成演示 · 测试夹具",
        },
        "scenario": {
            "name": "演示企业甲的台账整理",
            "industry": "demo_industry",
            "tags": ["演示"],
            "difficulty": "standard",
            "split": "train",
        },
        "content": {
            "customer_profile": {
                "company_type": "演示用假想企业（10 人小团队）",
                "stakeholders": ["演示老板"],
                "maturity": "纸质台账 + Excel",
                "decision_style": "演示口径：看重见效速度",
                "real_budget": "演示口径：5 万以内",
            },
            "visible": {
                "initial_brief": ["我们台账太乱了，想上 AI 整理一下"],
                "known_systems": ["Excel 台账"],
                "constraints": {
                    "budget": "5 万以内",
                    "timeline": "1 个月",
                },
            },
            "hidden": {
                "facts": [
                    {
                        "fact_id": "DEMO-F1",
                        "text": "台账里混着两个业务线的口径，直接汇总会对不上账。",
                        "category": "data",
                        "disclosure_stage": "interview",
                        "probe_keywords": ["台账", "口径", "汇总", "业务线"],
                        "condition": "顾问询问台账结构与汇总口径",
                    }
                ]
            },
            "misleading_request": "直接买一个 AI 表格工具自动整理",
        },
        "reference": {
            "expected_outcomes": ["识别双业务线口径冲突是真实问题"],
            "acceptance_criteria": ["方案含口径拆分与汇总规则"],
            "rubric": {
                "must_identify": ["双业务线口径冲突"],
                "must_avoid": ["把工具采购当方案本身"],
                "must_produce": ["口径拆分规则与汇总路径"],
            },
        },
    }


def _write_card(cards_dir: Path, card: dict[str, Any]) -> Path:
    cards_dir.mkdir(parents=True, exist_ok=True)
    path = cards_dir / f"{card['card_id']}.json"
    path.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _run_convert(tmp_path: Path, card: dict[str, Any] | None = None) -> tuple[int, Path, Path]:
    cards_dir = tmp_path / "cards"
    out_dir = tmp_path / "out"
    if card is not None:
        _write_card(cards_dir, card)
    else:
        _write_card(cards_dir, _demo_card())
    failed = import_cases.convert(cards_dir=cards_dir, out_dir=out_dir)
    return failed, cards_dir, out_dir


def test_happy_path_payload_shape() -> None:
    payload, errors = import_cases.build_payload(_demo_card())
    assert errors == []
    assert payload["scenario_key"] == "IMP-DEMO-01"
    assert payload["source_kind"] == "import"
    assert payload["status"] == "draft"
    assert payload["content"]["case_code"] == "IMP-DEMO-01"
    assert payload["source_ref"] == "truth-layer://demo/demo-card.json"
    assert import_cases.gate_payload(payload) == []


def test_convert_writes_package_batch_and_manifest(tmp_path: Path) -> None:
    failed, _, out_dir = _run_convert(tmp_path)
    assert failed == 0
    package = out_dir / "packages" / "IMP-DEMO-01.json"
    assert package.exists()
    envelope = json.loads(package.read_text(encoding="utf-8"))
    assert set(envelope) == {"scenarios"}
    assert envelope["scenarios"][0]["scenario_key"] == "IMP-DEMO-01"
    batch_files = list((out_dir / "packages").glob("import-batch-*.json"))
    assert len(batch_files) == 1
    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = {entry["scenario_key"]: entry for entry in manifest["entries"]}
    assert "IMP-DEMO-01" in entries
    assert len(entries["IMP-DEMO-01"]["package_sha256"]) == 64
    assert "(batch)" in entries


def test_missing_attribution_key_refused(tmp_path: Path) -> None:
    card = _demo_card()
    del card["attribution"]["license"]
    failed, _, out_dir = _run_convert(tmp_path, card)
    assert failed == 1
    assert not (out_dir / "packages" / "IMP-DEMO-01.json").exists()


def test_unknown_top_level_key_refused(tmp_path: Path) -> None:
    card = _demo_card()
    card["extra_notes"] = ["不允许的附加键"]
    failed, _, out_dir = _run_convert(tmp_path, card)
    assert failed == 1
    assert not (out_dir / "packages" / "IMP-DEMO-01.json").exists()


def test_case_code_mismatch_refused(tmp_path: Path) -> None:
    card = _demo_card()
    card["content"]["case_code"] = "IMP-SOMEONE-ELSE"
    failed, _, out_dir = _run_convert(tmp_path, card)
    assert failed == 1
    assert not (out_dir / "packages" / "IMP-DEMO-01.json").exists()


def test_answer_side_key_in_content_refused(tmp_path: Path) -> None:
    card = _demo_card()
    card["content"]["visible"]["constraints"]["must_identify"] = ["判卷基准混进客户可见面"]
    failed, _, out_dir = _run_convert(tmp_path, card)
    assert failed == 1
    assert not (out_dir / "packages" / "IMP-DEMO-01.json").exists()


def test_out_dir_inside_repo_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(import_cases, "REPO_ROOT", tmp_path / "fake-repo")
    (tmp_path / "fake-repo").mkdir()
    with pytest.raises(SystemExit, match="永不进仓"):
        import_cases.convert(
            cards_dir=tmp_path / "cards",
            out_dir=tmp_path / "fake-repo" / "server" / "seeds",
        )


def test_truth_layer_cards_accepted_when_present(tmp_path: Path) -> None:
    """真相层在卡时实卡全过闸；不在场显式 skip（与污染钉 N6 同设计）。"""
    if not TRUTH_CARDS_DIR.exists():
        pytest.skip("真相层导入卡目录不在场（非本机环境），跳过实卡验收")
    out_dir = tmp_path / "out"
    failed = import_cases.convert(cards_dir=TRUTH_CARDS_DIR, out_dir=out_dir)
    assert failed == 0
    packages = sorted((out_dir / "packages").glob("IMP-*.json"))
    assert len(packages) >= 3
