"""诊断评测集的**评测集污染隔离**静态钉（获客诊断工具实施任务书 T-06，2026-11-10）。

红线 R-4：案例卡的**标准答案**（问题清单 / 方案方向 / 结果口径 / 人机边界）
**永不进**生成器提示词、few-shot、知识库与检索索引。

本钉把这条红线从「流程纪律」变成「机械闸」——七条：

- **N1** fixtures 纯净：仓库内评测 fixtures 的 JSON 键里零答案字段名；
- **N2** 生成器可见面（``server/src``）零答案字段名、零评测集路径引用；
- **N3** 知识库 / 种子面（``server/seeds``、``desktop/src``）同上；
- **N4** fixtures 形状：必备键齐全、指纹为 64 位十六进制、输入侧非空且只有允许字段；
- **N5** 指纹登记：fixtures 的答案键指针与仓库侧登记表逐项一致（**改答案必留 diff**）；
- **N6** 真值层交叉核验：真相层在场时重算 sha256 比对；不在场则**显式 skip**
  （不静默绿——这是「无 oracle ⇒ insufficient_data」纪律的代码形态）；
- **N7** 同步脚本按**字段允许名单**工作，且脚本源码**零答案字段名**——
  脚本在结构上不可能复制答案字段（不是自律，是它根本不知道那些字段叫什么）。

口径说明：``answer_key_ref`` 是**指针**不是答案，允许存在；禁止的是答案字段
（``ground_truth`` / ``solution_direction`` / ``problems_expected`` /
``human_boundary`` / ``must_not_hallucinate``）与其内容。
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
SERVER_DIR = TESTS_DIR.parent
REPO_ROOT = SERVER_DIR.parent

FIXTURES_DIR = TESTS_DIR / "fixtures" / "diagnostic_eval"
SRC_DIR = SERVER_DIR / "src" / "fde_api"
SEEDS_DIR = SERVER_DIR / "seeds"
DESKTOP_SRC = REPO_ROOT / "desktop" / "src"
SYNC_SCRIPT = FIXTURES_DIR / "sync_from_truth_layer.py"
REGISTRY_FILE = FIXTURES_DIR / "answer_key_digests.json"

TRUTH_ROOT_ENV = "FDE_DIAG_EVAL_TRUTH_ROOT"
DEFAULT_TRUTH_ROOT = Path(r"D:\test\FDE\knowledge\诊断案例集")

# 答案字段名（禁止出现在生成器可见面与 fixtures 内）
FORBIDDEN_KEYS = (
    "ground_truth",
    "solution_direction",
    "problems_expected",
    "human_boundary",
    "must_not_hallucinate",
)
# 生成器可见面不得引用的路径 / 指针 token
FORBIDDEN_PATH_TOKENS = (
    "diagnostic_eval",
    "诊断案例集",
    "answer_key",
)

# fixtures 顶层必备键
REQUIRED_FIXTURE_KEYS = (
    "fixture_version",
    "case_id",
    "card_version",
    "attribution",
    "answer_key_ref",
    "sim_input",
    "eval_meta",
)
# fixtures 输入侧允许出现的键（与同步脚本的允许名单一致）
ALLOWED_SIM_INPUT_KEYS = (
    "questionnaire_slots",
    "free_text_pain",
    "imperfection_notes",
)
# 答案键指针的必备键
REQUIRED_REF_KEYS = ("relative_path", "sha256")
# 同步脚本必须声明的允许名单常量
REQUIRED_ALLOWLIST_CONSTANTS = (
    "ALLOWED_CARD_FIELDS",
    "ALLOWED_ATTRIBUTION_FIELDS",
    "ALLOWED_SIM_INPUT_FIELDS",
    "ALLOWED_EVAL_FIELDS",
)

_SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".json", ".txt", ".yml", ".yaml"}
_SKIP_DIR_NAMES = {"node_modules", ".git", "__pycache__", "dist", "build", ".venv"}


def _iter_json_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.json") if p.is_file())


def _iter_scan_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in _SCAN_SUFFIXES:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        out.append(path)
    return out


def _collect_json_keys(payload: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(str(key))
            keys |= _collect_json_keys(value)
    elif isinstance(payload, list):
        for item in payload:
            keys |= _collect_json_keys(item)
    return keys


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_fixtures() -> dict[str, dict[str, Any]]:
    fixtures: dict[str, dict[str, Any]] = {}
    for path in _iter_json_files(FIXTURES_DIR):
        # registry（答案键指纹登记簿）与 answer_mapping（考卷口语值 → 生产
        # 问卷闭集适配表）是 fixtures 目录里的非考卷数据文件，均不按考卷校验。
        if path.name in (REGISTRY_FILE.name, "answer_mapping.json"):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        fixtures[str(payload.get("case_id"))] = payload
    return fixtures


def _load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))


def _truth_root() -> Path | None:
    raw = os.environ.get(TRUTH_ROOT_ENV)
    root = Path(raw) if raw else DEFAULT_TRUTH_ROOT
    return root if root.is_dir() else None


def test_n1_fixtures_carry_no_answer_key_fields() -> None:
    """N1：评测 fixtures 的 JSON 键里零答案字段名。"""
    violations: list[str] = []
    for path in _iter_json_files(FIXTURES_DIR):
        payload = json.loads(path.read_text(encoding="utf-8"))
        bad = sorted(_collect_json_keys(payload) & set(FORBIDDEN_KEYS))
        if bad:
            violations.append("%s: %s" % (path.name, bad))
    assert violations == [], f"评测 fixtures 内出现答案字段键名：{violations}"


def test_n2_generator_visible_surface_has_no_answer_key_material() -> None:
    """N2：生成器可见面（server/src）零答案字段名、零评测集路径引用。"""
    violations: list[str] = []
    for path in _iter_scan_files(SRC_DIR):
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in FORBIDDEN_KEYS + FORBIDDEN_PATH_TOKENS:
            if token in text:
                rel = path.relative_to(REPO_ROOT).as_posix()
                violations.append("%s: %s" % (rel, token))
    assert violations == [], f"生成器可见面出现答案材料或评测集引用：{violations}"


def test_n3_knowledge_and_seed_surface_has_no_answer_key_material() -> None:
    """N3：知识库 / 种子面（server/seeds、desktop/src）同上。"""
    violations: list[str] = []
    for root in (SEEDS_DIR, DESKTOP_SRC):
        if not root.is_dir():
            continue
        for path in _iter_scan_files(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            for token in FORBIDDEN_KEYS + FORBIDDEN_PATH_TOKENS:
                if token in text:
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    violations.append("%s: %s" % (rel, token))
    assert violations == [], f"知识库 / 种子面出现答案材料或评测集引用：{violations}"


def test_n4_fixtures_shape_is_complete_and_input_only() -> None:
    """N4：fixtures 形状——必备键齐全、指纹 64 位十六进制、输入侧非空且只有允许字段。"""
    fixtures = _load_fixtures()
    assert fixtures, "评测 fixtures 为空——先跑 sync_from_truth_layer.py 生成"
    problems: list[str] = []
    for case_id, payload in sorted(fixtures.items()):
        missing = [key for key in REQUIRED_FIXTURE_KEYS if key not in payload]
        if missing:
            problems.append("%s 缺键 %s" % (case_id, missing))
            continue
        ref = payload["answer_key_ref"]
        for key in REQUIRED_REF_KEYS:
            if key not in ref:
                problems.append("%s answer_key_ref 缺 %s" % (case_id, key))
        digest = str(ref.get("sha256", ""))
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            problems.append("%s sha256 形状不合法：%r" % (case_id, digest))
        sim_input = payload["sim_input"]
        extra = sorted(set(sim_input) - set(ALLOWED_SIM_INPUT_KEYS))
        if extra:
            problems.append("%s 输入侧出现允许名单外字段 %s" % (case_id, extra))
        if not str(sim_input.get("free_text_pain", "")).strip():
            problems.append("%s free_text_pain 为空" % case_id)
        slots = sim_input.get("questionnaire_slots")
        if not isinstance(slots, dict) or not slots:
            problems.append("%s questionnaire_slots 为空" % case_id)
        for key in ("difficulty", "contamination_class"):
            if not payload["eval_meta"].get(key):
                problems.append("%s eval_meta 缺 %s" % (case_id, key))
    assert problems == [], f"评测 fixtures 形状不合规：{problems}"


def test_n5_answer_key_digest_registry_matches_fixtures() -> None:
    """N5：指纹登记表与 fixtures 逐项一致——改答案必留 diff。"""
    registry = _load_registry()
    cases = registry.get("cases")
    assert isinstance(cases, dict) and cases, "答案键指纹登记表为空或形状不对"
    fixtures = _load_fixtures()
    assert set(cases) == set(fixtures), (
        "登记表与 fixtures 的 case_id 集合不一致：登记表 %s / fixtures %s"
        % (sorted(cases), sorted(fixtures))
    )
    mismatches: list[str] = []
    for case_id, entry in sorted(cases.items()):
        ref = fixtures[case_id]["answer_key_ref"]
        if str(entry.get("sha256")) != str(ref.get("sha256")):
            mismatches.append("%s sha256 不一致" % case_id)
        if str(entry.get("relative_path")) != str(ref.get("relative_path")):
            mismatches.append("%s relative_path 不一致" % case_id)
    assert mismatches == [], f"答案键指纹登记表与 fixtures 不一致：{mismatches}"


def test_n6_truth_layer_digests_match_when_available() -> None:
    """N6：真相层在场时重算答案键 sha256 比对；不在场显式 skip（不静默绿）。"""
    root = _truth_root()
    if root is None:
        pytest.skip(
            "真相层不在场（%s 未设置且默认路径不可用）——跳过答案键指纹交叉核验，"
            "非静默通过" % TRUTH_ROOT_ENV
        )
    cases = _load_registry().get("cases", {})
    mismatches: list[str] = []
    for case_id, entry in sorted(cases.items()):
        card_path = root / str(entry.get("relative_path"))
        if not card_path.is_file():
            mismatches.append("%s 真相层文件缺失：%s" % (case_id, card_path))
            continue
        actual = _sha256(card_path)
        if actual != str(entry.get("sha256")):
            mismatches.append(
                "%s 答案键指纹漂移：登记 %s / 实际 %s" % (case_id, entry.get("sha256"), actual)
            )
    assert mismatches == [], f"答案键指纹与真相层不一致（改答案未同步登记）：{mismatches}"


def test_n7_sync_script_is_allowlist_based_and_names_no_answer_fields() -> None:
    """N7：同步脚本按字段允许名单工作，且源码零答案字段名。"""
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    named = [token for token in FORBIDDEN_KEYS if token in text]
    assert named == [], (
        "同步脚本源码出现答案字段名 %s——脚本不得知道答案字段叫什么，"
        "否则它就可能复制答案" % named
    )
    missing = [name for name in REQUIRED_ALLOWLIST_CONSTANTS if name not in text]
    assert missing == [], f"同步脚本缺少字段允许名单常量：{missing}"
    assert "pick(" in text, "同步脚本必须经由允许名单取字段（pick）而非整体拷贝"
