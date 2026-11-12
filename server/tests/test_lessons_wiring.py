# -*- coding: utf-8 -*-
"""agent 上下文知识片段接线测试与静态钉（L 线 L3 轮，2026-11-12）。

静态钉四组（钉 ``server/seeds/lessons.json`` 与 ``agents/lessons.py``）：
①种子 schema 闭集＋sha256 逐条一致（**改 text 必留 diff**）；②能力域闭集
（capability_tags ⊆ ``CAPABILITY_REQUIREMENTS`` 的 ``agent.*`` 键，persona
键不可作能力腿）；③答案字段词汇零命中（诊断卡判卷基准键族＋客户资料词
永不进种子——污染单向阀的 lessons 侧承载）；④接线行为（能力腿/行业过滤、
top-K 与单条截断、运行时软失败、渲染实例非空——设计稿 §5-L3 验收判据）。

种子内容纪律：只含抽象打法/判据，零案例答案、零客户资料、零未溯源数字；
来源＝SOP 现行产品已蒸馏资产＋诊断案例集展示面提炼（拍板留痕：双来源，
2026-11-12 蔡工交互拍板）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from fde_api.agents import lessons
from fde_api.control.access import CAPABILITY_REQUIREMENTS

SEED_PATH = Path(__file__).resolve().parents[1] / "seeds" / "lessons.json"

# 诊断卡判卷基准键族（污染单向阀：答案字段词汇零命中）＋客户资料词。
ANSWER_VOCAB = (
    "ground_truth",
    "problems_expected",
    "solution_direction",
    "fde_actions_expected",
    "must_not_hallucinate",
    "human_boundary",
    "真实姓名",
    "身份证",
    "微信号",
)


def _raw_seed() -> dict:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 静态钉①②③：种子内容质量（CI 强制）
# ---------------------------------------------------------------------------


def test_seed_schema_closed_and_sha256_matches_text():
    raw = _raw_seed()
    assert raw.get("version") == "lessons-v1"
    entries = raw.get("entries")
    assert isinstance(entries, list) and 10 <= len(entries) <= 20
    ids = [entry["id"] for entry in entries]
    assert len(ids) == len(set(ids))
    for entry in entries:
        assert lessons.REQUIRED_ENTRY_KEYS.issubset(entry), entry.get("id")
        assert not (set(entry) - lessons.REQUIRED_ENTRY_KEYS - lessons.OPTIONAL_ENTRY_KEYS)
        # sha256 逐条一致：改 text 必留 diff（指纹钉）。
        assert entry["sha256"] == hashlib.sha256(entry["text"].encode("utf-8")).hexdigest(), entry["id"]
        assert entry["source_ref"].strip(), entry["id"]
        assert entry["text"].strip() and len(entry["text"]) <= 200, entry["id"]


def test_seed_capability_tags_in_closed_domain():
    agent_keys = {key for key in CAPABILITY_REQUIREMENTS if key.startswith("agent.")}
    for entry in _raw_seed()["entries"]:
        tags = entry["capability_tags"]
        assert isinstance(tags, list) and tags, entry["id"]
        for tag in tags:
            assert tag in agent_keys, f"{entry['id']}: {tag}"
            assert not tag.startswith("agent.persona."), entry["id"]


def test_seed_zero_answer_vocab_and_customer_words():
    raw_text = SEED_PATH.read_text(encoding="utf-8")
    for word in ANSWER_VOCAB:
        assert word not in raw_text, word


def test_load_entries_rejects_malformed(tmp_path):
    bad = tmp_path / "lessons.json"
    bad.write_text(json.dumps({"version": "lessons-v1", "entries": [{"id": "x"}]}), encoding="utf-8")
    with pytest.raises(SystemExit):
        lessons.load_entries(bad)
    missing = tmp_path / "absent.json"
    with pytest.raises(SystemExit):
        lessons.load_entries(missing)


# ---------------------------------------------------------------------------
# 选择行为（纯函数，合成条目）
# ---------------------------------------------------------------------------


def _entries():
    return [
        {"id": "L1", "capability_tags": ["agent.module.solution"], "text": "方案甲" * 100, "industries": ["foreign_trade"]},
        {"id": "L2", "capability_tags": ["agent.module.presales"], "text": "售前乙", "industries": []},
        {"id": "L3", "capability_tags": ["agent.module.solution", "agent.quality_guard"], "text": "通用丙"},
        {"id": "L4", "capability_tags": ["agent.module.solution"], "text": "方案丁"},
    ]


def test_select_filters_by_capability_tier():
    picked = lessons.select_lessons(_entries(), capability_tier="agent.module.presales", top_k=5, max_chars=400)
    assert [row["id"] for row in picked] == ["L2"]
    picked = lessons.select_lessons(_entries(), capability_tier="agent.quality_guard", top_k=5, max_chars=400)
    assert [row["id"] for row in picked] == ["L3"]


def test_select_honors_industries_restriction():
    picked = lessons.select_lessons(
        _entries(), capability_tier="agent.module.solution", project_industry="legal_services", top_k=5, max_chars=400
    )
    # L1 限定 foreign_trade ⇒ 跳过；L3/L4 通用 ⇒ 注入。
    assert [row["id"] for row in picked] == ["L3", "L4"]
    picked = lessons.select_lessons(
        _entries(), capability_tier="agent.module.solution", project_industry="foreign_trade", top_k=5, max_chars=400
    )
    assert [row["id"] for row in picked] == ["L1", "L3", "L4"]


def test_select_top_k_and_max_chars_caps():
    picked = lessons.select_lessons(
        _entries(), capability_tier="agent.module.solution", project_industry="foreign_trade", top_k=2, max_chars=10
    )
    assert [row["id"] for row in picked] == ["L1", "L3"]
    assert all(len(row["text"]) <= 10 for row in picked)


# ---------------------------------------------------------------------------
# 接线（运行时软失败＋渲染实例）
# ---------------------------------------------------------------------------


def _settings(**overrides):
    base = {
        "agent_forbidden_terms": "",
        "fde_agent_lessons_enabled": True,
        "fde_agent_lessons_top_k": 3,
        "fde_agent_lessons_max_chars": 400,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_snippets_disabled_returns_empty():
    agent = SimpleNamespace(capability_tier="agent.module.solution")
    project = SimpleNamespace(template_snapshot=None)
    assert lessons.knowledge_snippets_for(
        project=project, agent=agent, settings=_settings(fde_agent_lessons_enabled=False)
    ) == ()


def test_snippets_soft_fail_on_missing_or_broken_seed(tmp_path):
    agent = SimpleNamespace(capability_tier="agent.module.solution")
    project = SimpleNamespace(template_snapshot=None)
    lessons.knowledge_snippets_for(project=project, agent=agent, settings=_settings())
    # 缺文件/形状坏 → 空元组（run 路径不炸；种子质量由 CI 静态钉拦截）。
    import unittest.mock as mock

    with mock.patch.object(lessons, "load_entries", side_effect=SystemExit("boom")):
        assert lessons.knowledge_snippets_for(project=project, agent=agent, settings=_settings()) == ()


def test_snippets_happy_path_reads_project_industry():
    agent = SimpleNamespace(capability_tier="agent.module.solution")
    project = SimpleNamespace(template_snapshot={"industry_name": "foreign_trade"})
    snippets = lessons.knowledge_snippets_for(project=project, agent=agent, settings=_settings())
    assert snippets and all("id" in row and "text" in row for row in snippets)


def test_render_context_knowledge_section_non_empty(monkeypatch):
    """验收判据：知识片段段非空渲染实例（设计稿 §5-L3）。"""
    from fde_api.agents import service as agent_service

    monkeypatch.setattr(agent_service, "_settings", lambda: _settings())
    project = SimpleNamespace(
        id="proj-lessons-smoke", project_code="P-LESSONS-SMOKE", template_snapshot=None
    )
    agent = SimpleNamespace(name="方案顾问", capability_tier="agent.module.solution")
    session = SimpleNamespace(scalar=lambda *a, **k: None)
    text, _refs = agent_service._render_context(session, project=project, agent=agent, solution=None)
    assert "## 知识片段" in text
    assert "（未检索到知识片段）" not in text
    # 方案腿条目在场（真实种子 → 真实渲染）。
    assert any(row["id"] in text for row in lessons.load_entries())
