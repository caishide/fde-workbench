"""诊断评测集 fixtures 同步脚本（获客诊断工具实施任务书 T-06）。

从**本地真相层**的案例卡生成**只含输入**的评测 fixtures。

设计要点（红线 R-4：标准答案永不进仓库，生成器也不得从仓库读到答案）：

1. **按字段允许名单复制，不是按禁止名单过滤。** 禁止名单可被改名绕过
   （换一个名字就漏了），允许名单绕不过去：不在名单里的字段根本不会被读取。
2. **本脚本源码内不出现任何答案字段名。** 脚本因此在结构上就**不可能**
   复制答案字段——不是靠自律，是靠它根本不知道那些字段叫什么。
   （这条由 ``test_diagnostic_eval_contamination.py::test_n7_…`` 机械守。）
3. **答案键只以指针 + 指纹形式登记**：``answer_key_ref``（相对路径 + sha256）。
   指纹的作用是「改答案必留 diff」：真相层卡片被改动 ⇒ 指纹变化 ⇒
   仓库侧登记表与 fixtures 必须同步更新 ⇒ 评审看得见。

用法（本地操作者用；真相层不在场时 fail-closed）::

    python server/tests/fixtures/diagnostic_eval/sync_from_truth_layer.py
    FDE_DIAG_EVAL_TRUTH_ROOT=/path/to/诊断案例集 python .../sync_from_truth_layer.py

真相层根目录解析顺序：环境变量 ``FDE_DIAG_EVAL_TRUTH_ROOT`` → 默认 Windows 路径
``D:\\test\\FDE\\knowledge\\诊断案例集``。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

TRUTH_ROOT_ENV = "FDE_DIAG_EVAL_TRUTH_ROOT"
DEFAULT_TRUTH_ROOT = Path(r"D:\test\FDE\knowledge\诊断案例集")
CARDS_SUBDIR = "cards"
FIXTURE_VERSION = "diag-eval-v0"

# ── 字段允许名单（不在名单里的字段一律不读取） ──────────────────────────
# 顶层：从卡片复制到 fixture 的键
ALLOWED_CARD_FIELDS = ("case_id", "card_version", "attribution", "sim_input", "eval")
# 署名段：红线第 8 条要求派生物带署名与来源对照表，故连同出处一并复制
ALLOWED_ATTRIBUTION_FIELDS = (
    "license",
    "license_holder",
    "attribution_line",
    "original_url",
    "case_page_url",
    "snapshot",
)
# 输入段：问卷槽位答案 + 自由文本痛点 + 刻意不完美说明
ALLOWED_SIM_INPUT_FIELDS = (
    "questionnaire_slots",
    "free_text_pain",
    "imperfection_notes",
)
# 评测元信息段
ALLOWED_EVAL_FIELDS = (
    "difficulty",
    "contamination_class",
    "meta_role",
    "eval_eligible",
)

# fixture 顶层键（与 ALLOWED_CARD_FIELDS 派生，用于产物形状自检）
FIXTURE_TOP_LEVEL_KEYS = (
    "fixture_version",
    "case_id",
    "card_version",
    "attribution",
    "answer_key_ref",
    "sim_input",
    "eval_meta",
)


def resolve_truth_root() -> Path:
    """解析真相层根目录；环境变量优先。"""
    raw = os.environ.get(TRUTH_ROOT_ENV)
    return Path(raw) if raw else DEFAULT_TRUTH_ROOT


def sha256_file(path: Path) -> str:
    """返回文件字节的 sha256 十六进制串。"""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pick(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """按允许名单取字段；缺键不报错（该字段在本卡不存在即不出现）。"""
    return {key: source[key] for key in keys if key in source}


def build_fixture(card: dict[str, Any], card_path: Path, truth_root: Path) -> dict[str, Any]:
    """由一张案例卡构造一个 fixture（只取允许名单内的字段）。"""
    attribution = pick(card.get("attribution") or {}, ALLOWED_ATTRIBUTION_FIELDS)
    sim_input = pick(card.get("sim_input") or {}, ALLOWED_SIM_INPUT_FIELDS)
    eval_meta = pick(card.get("eval") or {}, ALLOWED_EVAL_FIELDS)

    fixture: dict[str, Any] = {
        "fixture_version": FIXTURE_VERSION,
        "case_id": card.get("case_id"),
        "card_version": card.get("card_version"),
        "attribution": attribution,
        "answer_key_ref": {
            "relative_path": card_path.relative_to(truth_root).as_posix(),
            "sha256": sha256_file(card_path),
            "pointer_note": "标准答案只存本地真相层；仓库内零答案内容",
        },
        "sim_input": sim_input,
        "eval_meta": eval_meta,
    }
    return fixture


def write_json(path: Path, payload: Any) -> None:
    """以 UTF-8 + 2 空格缩进写出 JSON（末尾换行）。"""
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    truth_root = resolve_truth_root()
    cards_dir = truth_root / CARDS_SUBDIR
    if not cards_dir.is_dir():
        sys.stderr.write(
            "真相层不可用：%s（%s 或环境变量 %s 指向可用目录）\n"
            % (cards_dir, DEFAULT_TRUTH_ROOT, TRUTH_ROOT_ENV)
        )
        return 2

    out_dir = Path(__file__).resolve().parent
    card_paths = sorted(cards_dir.glob("*.json"))
    if not card_paths:
        sys.stderr.write("真相层案例卡为空：%s\n" % cards_dir)
        return 2

    digests: dict[str, Any] = {}
    for card_path in card_paths:
        with card_path.open(encoding="utf-8") as fh:
            card = json.load(fh)
        case_id = str(card.get("case_id") or card_path.stem)
        fixture = build_fixture(card, card_path, truth_root)
        missing = [key for key in ("case_id", "sim_input") if not fixture.get(key)]
        if missing:
            sys.stderr.write("案例卡缺字段 %s：%s\n" % (missing, card_path))
            return 2
        write_json(out_dir / ("%s.json" % case_id), fixture)
        digests[case_id] = {
            "relative_path": fixture["answer_key_ref"]["relative_path"],
            "sha256": fixture["answer_key_ref"]["sha256"],
        }

    write_json(
        out_dir / "answer_key_digests.json",
        {
            "registry_version": FIXTURE_VERSION,
            "note": "答案键指纹登记表——改答案必留 diff（与 fixtures 逐项一致）",
            "cases": digests,
        },
    )
    sys.stdout.write("已生成 %d 份 fixtures → %s\n" % (len(card_paths), out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
