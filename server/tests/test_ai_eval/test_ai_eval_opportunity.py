"""E2 AI 评测集（golden set）：锁住 AI 机会识别的当前质量基线。

数据在 ``tests/fixtures/ai/opportunity_golden_set.json``（23 条），覆盖三类：

- **结构合法性**：字段缺失/取值非法/证据结构损坏 → 候选必须被丢弃
- **引文准确性**（E3）：``answer_excerpt`` 必须逐字来自被选中的原文，否则剔除
- **代号化不泄漏**（A2）：候选文本里不得出现明文企业名/联系人/电话

本轮不引入 RAG/语义检索（§2 范围边界），评测集的作用是把「当前能到哪」
钉住：任何让基线变差的改动都会在这里失败。
"""
import json
from pathlib import Path

import pytest

from fde_api.ai.ai_opportunity_service import (
    AIOpportunityDiscoveryError,
    _normalize_candidates,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "ai" / "opportunity_golden_set.json"
GOLDEN = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES = GOLDEN["cases"]


def _ids(cases):
    return [case["name"] for case in cases]


def test_golden_set_meets_minimum_size():
    """E2 要求 20–50 条 golden case。"""
    assert 20 <= len(CASES) <= 50, len(CASES)


def test_golden_set_covers_all_required_dimensions():
    kinds = {case["kind"] for case in CASES}
    assert {"citation", "structure", "pseudonym"} <= kinds, kinds


@pytest.mark.parametrize("case", CASES, ids=_ids(CASES))
def test_golden_case(case):
    raw = {"candidates": [case["candidate"]]} if case["candidate"] is not None else {"candidates": "broken"}
    expect = case["expect"]

    if expect.get("error"):
        with pytest.raises(AIOpportunityDiscoveryError) as excinfo:
            _normalize_candidates(raw, case["forms"], format_only=expect.get("format_only", False))
        assert excinfo.value.code == expect["error"]
        return

    candidates = _normalize_candidates(
        raw, case["forms"], format_only=expect.get("format_only", False)
    )
    assert len(candidates) == expect["kept"], (
        f"{case['name']}: expected {expect['kept']} candidate(s), got {len(candidates)}"
    )
    if not candidates:
        return

    candidate = candidates[0]
    if "evidence_count" in expect:
        assert len(candidate["evidence"]) == expect["evidence_count"]
    if expect.get("format_only"):
        for key in expect.get("expect_blank", []):
            assert candidate[key] == "", f"{key} 应被清空"
        for key, value in expect.get("expect_defaults", {}).items():
            assert candidate[key] == value, f"{key} 应回落为默认值"
    for plaintext in expect.get("forbid_plaintext", []):
        blob = json.dumps(candidate, ensure_ascii=False)
        assert plaintext not in blob, f"候选文本泄漏明文：{plaintext}"


def test_prompt_requires_traceable_evidence():
    """E3 的前提：提示词本身要求引文来自原文。"""
    from fde_api.ai.ai_opportunity_prompt import build_ai_opportunity_messages

    messages = build_ai_opportunity_messages({"expand": True})
    system = messages[0]["content"]
    assert "原文" in system
    assert "answer_excerpt" in system

import pytest


@pytest.fixture(scope="session", autouse=True)
def migrated_test_schema():
    """离线评测子树：覆盖仓库级迁移夹具，避免初始化共享 PG 测试库。"""
    yield
