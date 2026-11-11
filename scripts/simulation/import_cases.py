"""交付案例学习闭环 L1——真相层导入卡 → 训练场导入包转换器（L 线 L1 轮）。

跑法（宿主 Windows；真相层只读，导入包只落 ``--out-dir``）：

```bash
python scripts/simulation/import_cases.py \
  --cards-dir "D:\\test\\FDE\\knowledge\\交付场景导入包\\cards" \
  --out-dir   "D:\\test\\FDE\\knowledge\\交付场景导入包\\packages"
```

**输入**：``import_card_v1`` 卡（JSON）——训练场**原生形状**（content/reference
与 ``server/src/fde_api/simulation/seeds/CASE-*.json`` 同构）。卡件由 AI 起草、
人工审阅；转换器只做机械装配与闸门校验，零内容生成。

**闸门（逐卡，fail-closed）**：
1. 卡 schema 允许名单——未知顶层键/缺必填 attribution ⇒ 拒；
2. ``validate_scenario``（生产校验器，八规则）；
3. ``load_view`` 三视图泄漏自检（生产装载器，tester/customer/judge）；
4. 输出与输入目录**必须在本仓之外**（导入包含判卷基准，永不进仓）。

**输出**：逐卡 ``<card_id>.json``（``{"scenarios": [payload]}``，与
``POST /simulation/scenarios/import`` 信封一致）＋ 合并批次件 ＋ ``manifest.json``
（逐包 sha256）。任何卡失败不阻断其余卡（逐条回显），存在失败 ⇒ 退出码 1。

**纪律**：``source_kind='import'``、``status='draft'`` 由本转换器写死——
导入建行与激活（draft→active）都是人工动作，本脚本不代发起、不碰 API。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SERVER_SRC = Path(__file__).resolve().parents[2] / "server" / "src"
sys.path.insert(0, str(SERVER_SRC))

REPO_ROOT = Path(__file__).resolve().parents[2]

from fde_api.simulation.scenarios.loader import ScenarioLeakError, load_view  # noqa: E402
from fde_api.simulation.scenarios.validator import validate_scenario  # noqa: E402

CARD_VERSION = "import-card-v1"
CARD_ID_PREFIX = "IMP-"

# 卡顶层键允许名单（钉⑦同款思路：允许名单绕不过去，禁止名单可被改名绕过）
CARD_TOP_LEVEL_KEYS = (
    "card_id",
    "card_version",
    "generated_at",
    "attribution",
    "scenario",
    "content",
    "reference",
    "provenance",
)

# attribution 必填键（缺一即拒——每张进训练场的卡必须可溯源可核许可）
ATTRIBUTION_REQUIRED_KEYS = (
    "source_type",
    "source_pointer",
    "license",
    "snapshot_date",
    "rewritten",
    "rewrite_declaration",
)

# scenario 元数据段允许名单（其余 create payload 字段由转换器写死，卡不许带）
SCENARIO_META_KEYS = (
    "name",
    "industry",
    "tags",
    "difficulty",
    "split",
    "rubric_version",
    "note",
)

DIFFICULTIES = ("basic", "standard", "hard")
SPLITS = ("train", "regression", "blind")


def _card_errors(card: Any) -> list[str]:
    """卡级结构校验（允许名单 + 必填），返回错误码列表（空 = 通过）。"""
    errors: list[str] = []
    if not isinstance(card, dict):
        return ["card_not_object"]
    for key in ("card_id", "attribution", "scenario", "content", "reference"):
        if key not in card:
            errors.append("card_missing_required")
            break
    if errors:
        return errors
    card_id = card.get("card_id")
    if not isinstance(card_id, str) or not card_id.startswith(CARD_ID_PREFIX):
        errors.append("card_id_invalid")
    card_version = card.get("card_version")
    if card_version != CARD_VERSION:
        errors.append("card_version_unsupported")
    for key in card:
        if key not in CARD_TOP_LEVEL_KEYS:
            errors.append("card_unknown_key")
    attribution = card.get("attribution")
    if not isinstance(attribution, dict):
        errors.append("attribution_missing")
    else:
        for key in ATTRIBUTION_REQUIRED_KEYS:
            if key not in attribution:
                errors.append("attribution_missing")
                break
    scenario = card.get("scenario")
    if not isinstance(scenario, dict) or not isinstance(scenario.get("name"), str) or not scenario.get("name").strip():
        errors.append("scenario_meta_invalid")
    elif isinstance(scenario, dict):
        for key in scenario:
            if key not in SCENARIO_META_KEYS:
                errors.append("scenario_meta_unknown_key")
        difficulty = scenario.get("difficulty")
        if difficulty is not None and difficulty not in DIFFICULTIES:
            errors.append("scenario_meta_invalid")
        split = scenario.get("split")
        if split is not None and split not in SPLITS:
            errors.append("scenario_meta_invalid")
    if not isinstance(card.get("content"), dict):
        errors.append("content_not_object")
    if not isinstance(card.get("reference"), dict):
        errors.append("reference_not_object")
    return list(dict.fromkeys(errors))


def build_payload(card: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """卡 → ``create_scenario`` 导入 payload。返回 (payload, errors)。"""
    errors = _card_errors(card)
    if errors:
        return {}, errors
    card_id = card["card_id"]
    scenario = card["scenario"]
    content = dict(card["content"])
    case_code = content.get("case_code")
    if case_code is None:
        content["case_code"] = card_id
    elif case_code != card_id:
        # 与服务端同语义：显式业务键不一致必须报出（scenario_key_mismatch），不静默改写。
        return {}, ["scenario_key_mismatch"]
    payload: dict[str, Any] = {
        "scenario_key": card_id,
        "name": scenario["name"],
        "industry": scenario.get("industry") or "general",
        "variant": "normal",
        "difficulty": scenario.get("difficulty") or "standard",
        "split": scenario.get("split") or "train",
        "status": "draft",
        "tags": scenario.get("tags") or [],
        "rubric_version": scenario.get("rubric_version") or "rubric-v1",
        "source_kind": "import",
        "source_ref": card["attribution"]["source_pointer"],
        "note": scenario.get("note") or card["attribution"].get("attribution_line"),
        "content": content,
        "reference": card["reference"],
    }
    return payload, []


def gate_payload(payload: dict[str, Any]) -> list[str]:
    """生产闸门：校验器 + 三视图泄漏自检。返回错误描述列表（空 = 通过）。"""
    errors: list[str] = []
    scenario_key = payload["scenario_key"]
    errors.extend(
        f"validate_scenario:{code}"
        for code in validate_scenario(
            payload["content"],
            payload["reference"],
            scenario_key=scenario_key,
            variant=payload["variant"],
            split=payload["split"],
        )
    )
    for view in ("tester", "customer", "judge"):
        try:
            load_view(payload["content"], payload["reference"], view)
        except ScenarioLeakError as leak:
            errors.append(f"leak:{view}:{leak.code}:{json.dumps(leak.detail, ensure_ascii=False)}")
    return errors


def _guard_inside_repo(path: Path, label: str) -> None:
    """导入卡与导入包都含判卷基准——目录解析后落在本仓内即拒（fail-closed）。"""
    resolved = path.resolve()
    repo_resolved = REPO_ROOT.resolve()
    if resolved == repo_resolved or repo_resolved in resolved.parents:
        raise SystemExit(f"拒绝：{label} 在本仓内（{resolved}）——判卷基准永不进仓，请改到真相层目录。")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def convert(
    *,
    cards_dir: Path,
    out_dir: Path,
    only_card: str | None = None,
) -> int:
    """跑全部卡，返回失败卡数。"""
    _guard_inside_repo(cards_dir, "cards-dir")
    _guard_inside_repo(out_dir, "out-dir")
    card_paths = sorted(cards_dir.glob("*.json"))
    if only_card:
        card_paths = [p for p in card_paths if p.stem == only_card]
        if not card_paths:
            print(f"[fail] 未找到卡：{only_card}")
            return 1
    if not card_paths:
        print(f"[fail] 卡目录为空：{cards_dir}")
        return 1

    packages_dir = out_dir / "packages"
    manifest_entries: list[dict[str, Any]] = []
    batch_payloads: list[dict[str, Any]] = []
    failed = 0

    for card_path in card_paths:
        card = json.loads(card_path.read_text(encoding="utf-8"))
        card_id = card.get("card_id") if isinstance(card, dict) else None
        label = card_id or card_path.stem
        payload, errors = build_payload(card)
        if not errors:
            errors = gate_payload(payload)
        if errors:
            failed += 1
            print(f"[fail] {label}: {errors}")
            continue
        package_path = packages_dir / f"{payload['scenario_key']}.json"
        _write_json(package_path, {"scenarios": [payload]})
        batch_payloads.append(payload)
        manifest_entries.append(
            {
                "scenario_key": payload["scenario_key"],
                "card_file": card_path.name,
                "card_sha256": _sha256(card_path),
                "package_file": str(package_path.relative_to(out_dir)),
                "package_sha256": _sha256(package_path),
                "source_ref": payload["source_ref"],
                "status": payload["status"],
            }
        )
        print(f"[ok] {payload['scenario_key']} -> {package_path.name}")

    if batch_payloads:
        batch_name = f"import-batch-{datetime.now(UTC).strftime('%Y%m%d')}.json"
        batch_path = packages_dir / batch_name
        _write_json(batch_path, {"scenarios": batch_payloads})
        manifest_entries.append(
            {
                "scenario_key": "(batch)",
                "package_file": str(batch_path.relative_to(out_dir)),
                "package_sha256": _sha256(batch_path),
            }
        )
    manifest_path = out_dir / "manifest.json"
    _write_json(
        manifest_path,
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "card_version": CARD_VERSION,
            "entries": manifest_entries,
        },
    )
    print(f"[done] {len(manifest_entries) - (1 if batch_payloads else 0)} 包 / 失败 {failed}；manifest -> {manifest_path}")
    return failed


def main() -> None:
    parser = argparse.ArgumentParser(description="真相层导入卡 → 训练场导入包（L1）")
    parser.add_argument("--cards-dir", required=True, help="import_card_v1 卡目录（仓外真相层）")
    parser.add_argument("--out-dir", required=True, help="导入包输出目录（仓外真相层）")
    parser.add_argument("--card", default=None, help="只转换指定 card_id")
    args = parser.parse_args()
    failed = convert(
        cards_dir=Path(args.cards_dir),
        out_dir=Path(args.out_dir),
        only_card=args.card,
    )
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
