"""提示词版本注册表与质量路由 fail-safe 钉（AI 原生化 N6／差距台账 G-13）。

四类机械钉：
1. **指纹耦合钉**——注册表 ``content_sha256`` 字面量 vs 常量现算 sha256：
   改了提示词正文而不同步注册表（升版本＋换指纹）⇒ 红（任务书 N6 风险①）；
2. **AST 全常量必注册钉**——``server/src`` 模块级 ``*SYSTEM_PROMPT*`` 字符串
   常量（含 f-string）必须全部在册，且注册表零幽灵条目（双向 ≡）；
3. **出厂默认值安全钉**——质量路由三键出厂态＝关/空/0.8：不开闸永不切模型
   （任务书 N6「明确不做」；T-10a 出厂默认值安全钉同款家族）；
4. **fail-safe 矩阵钉**——四道闸（未开闸/指针空/文件不可读或坏 JSON/无该
   purpose 行或形状不合法/分数低于下限）任一不满足恒 ``None``＝沿用既有链。
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fde_api.ai import prompt_registry
from fde_api.ai.model_routing import resolve_quality_route

SRC = Path(__file__).resolve().parents[1] / "src" / "fde_api"

# 判据复测下限：G-13 点名 5 常量＋N3 系/诊断/派单等已在册者，全量 ≥12。
MIN_REGISTRATIONS = 12


# --------------------------------------------------------------- 1. 指纹耦合
def test_registry_content_hash_coupling():
    """改提示词正文而不同步注册表 ⇒ 红（改内容必须先升版本）。"""
    assert len(prompt_registry.PROMPT_REGISTRATIONS) >= MIN_REGISTRATIONS
    for entry in prompt_registry.PROMPT_REGISTRATIONS:
        module = importlib.import_module(entry.module)
        value = getattr(module, entry.constant)
        assert isinstance(value, str) and value, f"{entry.key}: 常量须非空字符串"
        assert entry.content_sha256, f"{entry.key}: 必须登记 content_sha256 字面量"
        actual = hashlib.sha256(value.encode("utf-8")).hexdigest()
        assert actual == entry.content_sha256, (
            f"{entry.key} 提示词正文已变但注册表未同步——"
            f"请在 ai/prompt_registry.py 升版本标签并更新 content_sha256"
        )


# --------------------------------------------------------------- 2. AST 全量钉
def _module_dotted(path: Path) -> str:
    rel = path.relative_to(SRC)
    parts = list(rel.parts[:-1])
    if rel.stem != "__init__":
        parts.append(rel.stem)
    return ".".join(["fde_api", *parts])


def _module_level_prompt_constants() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        dotted = _module_dotted(path)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign):
                if node.value is None:  # 裸标注（`x: int`）无值，跳过
                    continue
                targets, value = [node.target], node.value
            else:
                continue
            if value is None or not isinstance(
                value, (ast.Constant, ast.JoinedStr, ast.BinOp)
            ):
                # Constant＝纯字符串；JoinedStr＝f-string；BinOp＝「基础＋派生段」
                # 拼接（如 discovery 的 chunk 模板）——三者都是确定性文本模板，
                # 均须在册（指纹耦合钉同样逐条覆盖）。
                continue
            for target in targets:
                if isinstance(target, ast.Name) and "SYSTEM_PROMPT" in target.id:
                    found.add((dotted, target.id))
    return found


def test_all_system_prompt_constants_registered_two_way():
    """src 全部模块级 *SYSTEM_PROMPT* 常量在册（缺登记⇒红）＋注册表零幽灵条目。"""
    found = _module_level_prompt_constants()
    registered = {(e.module, e.constant) for e in prompt_registry.PROMPT_REGISTRATIONS}
    missing = found - registered
    assert not missing, f"SYSTEM_PROMPT 常量未进注册表（请在 ai/prompt_registry.py 登记）：{sorted(missing)}"
    phantoms = registered - found
    assert not phantoms, f"注册表含不存在的常量（幽灵条目）：{sorted(phantoms)}"
    assert registered == found
    assert len(registered) >= MIN_REGISTRATIONS


# --------------------------------------------------------------- 3. 版本归因
def test_existing_version_labels_preserved():
    """既有版本标签逐字保留（N2/N3a/N3b/N3c/curve3 归因链零回归）。"""
    expected = {
        ("fde_api.discovery.prompt", "DISCOVERY_SYSTEM_PROMPT"): "discovery-prompt-v2",
        ("fde_api.quality.draft", "QUALITY_TESTCASE_DRAFT_SYSTEM_PROMPT"): "quality-draft-prompt-v1",
        ("fde_api.plans.draft_ai", "DELIVERY_PLAN_DRAFT_SYSTEM_PROMPT"): "plan-draft-prompt-v1",
        ("fde_api.workflows.draft_ai", "WORKFLOW_DAG_DRAFT_SYSTEM_PROMPT"): "workflow-dag-prompt-v1",
        ("fde_api.diagnostics.prompts", "DIAGNOSTIC_REPORT_SYSTEM_PROMPT"): "diagnostic-report-prompt-v2",
        ("fde_api.dispatch.recommend_ai", "DISPATCH_RECOMMENDATION_SYSTEM_PROMPT"): "dispatch-recommend-prompt-v1",
        ("fde_api.ai.industry_template_prompt", "CHAT_SYSTEM_PROMPT"): "industry-template-chat-prompt-v1",
        ("fde_api.ai.industry_template_prompt", "GENERATION_SYSTEM_PROMPT"): "industry-template-gen-prompt-v1",
        ("fde_api.ai.research_form_prompt", "SYSTEM_PROMPT"): "research-form-prompt-v1",
        ("fde_api.simulation.evaluation_prompt", "SYSTEM_PROMPT"): "simulation-eval-prompt-v1",
        ("fde_api.simulation.diagnostic_judge", "SYSTEM_PROMPT"): "diagnostic-judge-prompt-v1",
    }
    for key, version in expected.items():
        assert prompt_registry.version_of(*key) == version, key


def test_version_of_unknown_key_fails_loud():
    with pytest.raises(KeyError):
        prompt_registry.version_of("fde_api.no.such.module", "SYSTEM_PROMPT")


def test_module_reexports_sourced_from_registry():
    """模块侧只 re-export：标签真身只在注册表（抽查 G-13 点名的五处）。"""
    from fde_api.discovery import models as discovery_models
    from fde_api.ai.industry_template_prompt import (
        CHAT_PROMPT_VERSION,
        GENERATION_PROMPT_VERSION,
    )
    from fde_api.ai.research_form_prompt import PROMPT_VERSION as research_version
    from fde_api.simulation.evaluation_prompt import EVALUATION_PROMPT_VERSION

    assert discovery_models.PROMPT_VERSION == prompt_registry.version_of(
        "fde_api.discovery.prompt", "DISCOVERY_SYSTEM_PROMPT"
    )
    assert CHAT_PROMPT_VERSION == prompt_registry.version_of(
        "fde_api.ai.industry_template_prompt", "CHAT_SYSTEM_PROMPT"
    )
    assert GENERATION_PROMPT_VERSION == prompt_registry.version_of(
        "fde_api.ai.industry_template_prompt", "GENERATION_SYSTEM_PROMPT"
    )
    assert research_version == prompt_registry.version_of(
        "fde_api.ai.research_form_prompt", "SYSTEM_PROMPT"
    )
    assert EVALUATION_PROMPT_VERSION == prompt_registry.version_of(
        "fde_api.simulation.evaluation_prompt", "SYSTEM_PROMPT"
    )


# --------------------------------------------------------------- 4. 路由 fail-safe
def test_quality_route_shipped_defaults_are_safe(settings):
    """出厂默认安全钉：闸关/指针空/下限 0.8——不开闸永不切模型。"""
    assert settings.ai_quality_route_enabled is False
    assert settings.ai_quality_route_summary_uri == ""
    assert settings.ai_quality_route_min_score == pytest.approx(0.8)


@pytest.fixture()
def route_settings(app, monkeypatch, tmp_path):
    cfg = SimpleNamespace(
        ai_quality_route_enabled=True,
        ai_quality_route_summary_uri=str(tmp_path / "summary.json"),
        ai_quality_route_min_score=0.8,
    )
    monkeypatch.setitem(app.config, "SETTINGS", cfg)
    return cfg


def _write_summary(path: Path, data: object) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _summary_path(route_settings) -> Path:
    return Path(route_settings.ai_quality_route_summary_uri)


QUALIFYING = {
    "dispatch_recommendation": {"provider": "glm", "model": "glm-pro", "score": 0.9},
    "weak_entry": {"provider": "glm", "model": "glm-lite", "score": 0.3},
    "bad_shape": {"provider": "glm", "score": 0.9},
}


def test_route_disabled_never_switches_even_with_qualifying_data(app, monkeypatch, tmp_path):
    summary = tmp_path / "summary.json"
    _write_summary(summary, QUALIFYING)
    monkeypatch.setitem(
        app.config,
        "SETTINGS",
        SimpleNamespace(
            ai_quality_route_enabled=False,
            ai_quality_route_summary_uri=str(summary),
            ai_quality_route_min_score=0.8,
        ),
    )
    with app.app_context():
        assert resolve_quality_route("dispatch_recommendation") is None


def test_route_happy_path_returns_model(app, route_settings):
    _write_summary(_summary_path(route_settings), QUALIFYING)
    with app.app_context():
        assert resolve_quality_route("dispatch_recommendation") == {
            "provider": "glm",
            "model": "glm-pro",
        }


def test_route_below_score_floor_returns_none(app, route_settings):
    _write_summary(_summary_path(route_settings), QUALIFYING)
    with app.app_context():
        assert resolve_quality_route("weak_entry") is None


def test_route_unknown_purpose_returns_none(app, route_settings):
    _write_summary(_summary_path(route_settings), QUALIFYING)
    with app.app_context():
        assert resolve_quality_route("no_such_purpose") is None


def test_route_missing_summary_file_returns_none(app, route_settings):
    with app.app_context():
        assert resolve_quality_route("dispatch_recommendation") is None


def test_route_empty_uri_returns_none(app, monkeypatch):
    monkeypatch.setitem(
        app.config,
        "SETTINGS",
        SimpleNamespace(
            ai_quality_route_enabled=True,
            ai_quality_route_summary_uri="",
            ai_quality_route_min_score=0.8,
        ),
    )
    with app.app_context():
        assert resolve_quality_route("dispatch_recommendation") is None


def test_route_corrupt_json_returns_none(app, route_settings):
    _summary_path(route_settings).write_text("{not json", encoding="utf-8")
    with app.app_context():
        assert resolve_quality_route("dispatch_recommendation") is None


def test_route_malformed_entry_returns_none(app, route_settings):
    _write_summary(_summary_path(route_settings), QUALIFYING)
    with app.app_context():
        assert resolve_quality_route("bad_shape") is None


# --------------------------------------------------------------- 5. 链序源钉
def test_execute_prompt_chain_orders_quality_route_between_override_and_preference():
    """源序钉：显式 model_override ＞ 质量路由 ＞ 人工偏好链——路由不得越过显式覆盖。"""
    text = (SRC / "control" / "ai_server_client.py").read_text(encoding="utf-8").replace(
        "\r\n", "\n"
    )
    assert (
        "model_override\n"
        "            or resolve_quality_route(purpose)\n"
        "            or resolve_model_preference(session, user_id, preference_id)"
    ) in text
