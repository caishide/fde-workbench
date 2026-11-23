"""Ecosystem OS M2 AI 总部岗位卡机械钉（挂卡式零新表）。

对应立项书《EcosystemOS_M2立项书_AI总部MVP挂卡式_草案_v0.1》验收条件 A1–A8：

A1 岗位卡落既有注册面／零新表零新迁移；
A2 每张卡的 purpose 在 prompt_registry 注册且在 overlay 白名单内；
A3 高危动作不得越出既有确认类语义；
A4 运营待办只读（人工决策仍走 propose/confirm 闸）——由 AI 不引入写入口的静态面承担；
A5 简报产出走既有文档/发信面，零新通道（卡片声明的出口面闭集）；
A6 留痕经 record_event，且不触真相层（卡片声明禁止路径）；
A7 出站白名单零变更（MVP-1 联网任务全禁用、卡片零出站域）；
A8 桌面端零改动。

纪律：本文件只读种子与既有注册表，不写库、不发信、不出站。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fde_api.ai import overlays, prompt_registry
from fde_api.control.access import ACCESS_RANK, CAPABILITY_REQUIREMENTS

SEEDS_DIR = Path(__file__).resolve().parents[1] / "seeds"
CARDS_PATH = SEEDS_DIR / "ai_hq_cards.json"
TOOL_GROUPS_PATH = SEEDS_DIR / "tool_groups.json"

# V1.0 §4.2 六个 AI 职能组（名称逐字）。
EXPECTED_GROUPS = {
    "增长与招商运营",
    "招生与学习运营",
    "企业客户运营",
    "项目交付运营",
    "区域与伙伴运营",
    "产品与技术运营",
}
# V1.0 §4.4 角色卡必须标准化的字段（逐项）。
REQUIRED_CARD_FIELDS = (
    "agent_key",
    "position_name",
    "version",
    "goal_and_duties",
    "input_data_scope",
    "output_schema",
    "tool_allowlist",
    "prohibitions",
    "budget_and_runtime_limit",
    "failure_fallback",
    "requires_human_approval",
    "artifact_location",
    "evaluation_metrics",
    "owner_and_release_record",
)
# V1.0 §4.4「提示词不是权限系统」——卡片必须声明能力腿。
REQUIRED_CAPABILITY_KEY = "capability_legs"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def cards_doc() -> dict[str, Any]:
    return _load(CARDS_PATH)


@pytest.fixture(scope="module")
def cards(cards_doc: dict[str, Any]) -> list[dict[str, Any]]:
    return list(cards_doc["cards"])


# ------------------------------------------------------------------ A1 零新表
def test_cards_are_data_only_no_new_table_or_module():
    """A1：岗位卡是数据面目录——零新表、零新模块（纪要 C3 红线）。"""
    doc = _load(CARDS_PATH)
    assert doc["version"] == 1
    # 目录里不得出现任何模型/迁移线索（真身是 JSON，不是 ORM 类）。
    raw = CARDS_PATH.read_text(encoding="utf-8")
    for token in ("__tablename__", "Mapped[", "Base,", "alembic", "revision ="):
        assert token not in raw, f"岗位卡目录不得含建表/迁移线索：{token}"


def test_cards_live_in_seeds_not_in_src(cards_doc: dict[str, Any]) -> None:
    """A1：目录落 seeds/（随代码发布的只读数据面），不落 src/ 的新模块。"""
    assert CARDS_PATH.parent == SEEDS_DIR
    assert "cards" in CARDS_PATH.name
    # 卡片不得引用任何新建表名（DB 真身是 agent_registry 等既有表）。
    raw = CARDS_PATH.read_text(encoding="utf-8")
    for table in ("agent_registry", "org_chart", "job_card", "ai_hq_card"):
        assert table not in raw, f"岗位卡不得落独立表：{table}"
    assert cards_doc["activation_state"] == "pending_owner_approval"


# ------------------------------------------------------- A2 purpose 注册与白名单
def _underscore(key: str) -> str:
    """overlay 白名单用下划线风格（``plans.delivery_plan_draft`` → ``plans_delivery_plan_draft``）。"""
    return key.replace(".", "_")


def test_every_card_purpose_is_registered_and_allowed(cards: list[dict[str, Any]]) -> None:
    """A2：卡片声明的 purpose 必须在 prompt_registry 在册且在 overlay 内网白名单内。"""
    registered = {entry.key for entry in prompt_registry.PROMPT_REGISTRATIONS}
    for card in cards:
        for key in card["prompt_purposes"]:
            assert key in registered, f"{card['agent_key']}: purpose 未注册 {key}"
            assert overlays.purpose_allowed(_underscore(key)), (
                f"{card['agent_key']}: purpose 不在内网白名单 {key}"
            )


def test_purpose_whitelist_closure_stays_intact(cards: list[dict[str, Any]]) -> None:
    """A2：新增卡不得扩大 overlay 白名单——内网闭集仍等于注册表减公网面。"""
    registered = {entry.key for entry in prompt_registry.PROMPT_REGISTRATIONS}
    allowed = {key for key in registered if overlays.purpose_allowed(_underscore(key))}
    assert allowed < registered, "公网面必须仍在白名单之外"
    # 卡片不得引用公网面 purpose（diagnostics.report 等）。
    public = registered - allowed
    for card in cards:
        assert not (set(card["prompt_purposes"]) & public), f"{card['agent_key']}: 引用了公网面 purpose"


# ------------------------------------------------------------ A3 确认类不越界
def test_high_risk_actions_require_human_approval(cards: list[dict[str, Any]]) -> None:
    """A3：卡片高危动作一律挂人工审批——AI 不自批。"""
    for card in cards:
        assert card["requires_human_approval"] is True, f"{card['agent_key']}: 必须挂人工审批"
        assert card["approval_queue"], f"{card['agent_key']}: 审批队列不得为空"


def test_approval_queue_subset_of_v1_human_queue(cards_doc: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """A3：审批类别取自 V1.0 §4.3 的 Human Approval Queue 六类，不得自造。"""
    known = set(cards_doc["org_tree"]["human_approval_queue"])
    assert len(known) == 6
    for card in cards:
        assert set(card["approval_queue"]) <= known, f"{card['agent_key']}: 自造审批类别"


def test_capability_legs_are_registered_and_tier_consistent(cards: list[dict[str, Any]]) -> None:
    """A3：能力腿必须在既有能力矩阵内，且声明档位不高于矩阵要求。"""
    for card in cards:
        assert card[REQUIRED_CAPABILITY_KEY], f"{card['agent_key']}: 必须声明能力腿"
        for leg in card[REQUIRED_CAPABILITY_KEY]:
            assert leg in CAPABILITY_REQUIREMENTS, f"{card['agent_key']}: 未知能力腿 {leg}"
            required = CAPABILITY_REQUIREMENTS[leg]
            assert ACCESS_RANK[card["declared_tier"]] >= ACCESS_RANK[required], (
                f"{card['agent_key']}: 声明档位 {card['declared_tier']} 低于能力 {leg} 要求的 {required}"
            )


# ----------------------------------------------------------------- A4 只读面
def test_cards_declare_no_write_entry(cards: list[dict[str, Any]]) -> None:
    """A4：卡片不引入写入口——能力腿只落在只读/计划类，写类动作走既有确认闸。"""
    write_legs = {"workbench.write", "memo.shared.write", "task.batch_assign", "ontology.write", "agent.code.write"}
    for card in cards:
        assert not (set(card[REQUIRED_CAPABILITY_KEY]) & write_legs), (
            f"{card['agent_key']}: MVP-1 不得持写类能力腿"
        )


def test_tool_allowlist_points_to_existing_groups(cards: list[dict[str, Any]]) -> None:
    """A4/A5：工具白名单只引用既有工具组（不新建工具面）。"""
    groups = {row["name"] for row in _load(TOOL_GROUPS_PATH)["tool_groups"]}
    for card in cards:
        assert card["tool_allowlist"], f"{card['agent_key']}: 工具白名单不得为空"
        for item in card["tool_allowlist"]:
            assert item.startswith("group:"), f"{card['agent_key']}: 只许引用工具组 {item}"
            assert item.split(":", 1)[1] in groups, f"{card['agent_key']}: 未知工具组 {item}"


# ------------------------------------------------------------ A5 出口面闭集
def test_cards_have_no_direct_outbound_channel(cards: list[dict[str, Any]]) -> None:
    """A5：卡片不自带发信/外发通道——出口只走既有文档面与 mailing 五闸。"""
    raw = CARDS_PATH.read_text(encoding="utf-8")
    for token in ("smtp", "ses_client", "send_email(", "requests.get", "httpx", "urllib"):
        assert token not in raw.lower(), f"岗位卡目录不得含直接外发通道：{token}"


# --------------------------------------------------------------- A6 留痕与红线
def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def test_cards_forbid_truth_layer_and_execute_audited_code(cards: list[dict[str, Any]]) -> None:
    """A6：卡片禁止触碰真相层；代码审查类岗位禁止执行被审代码。"""
    truth_tokens = ("D:\\test\\FDE", "D:/test/FDE", "fdeops", "openfde")
    for card in cards:
        # 按值判定（不按 JSON 重新转义后的文本——转义会把反斜杠翻倍导致漏检）。
        joined = "\n".join(_iter_strings(card))
        for token in truth_tokens:
            assert token not in joined, f"{card['agent_key']}: 禁止触碰真相层 {token}"
    assistant = next(card for card in cards if card["agent_key"] == "ai_hq.product_engineering_assistant")
    assert any("执行被审代码" in item for item in assistant["prohibitions"]), "AI 审查不执行被审代码（仓库红线）"


# ------------------------------------------------------------- A7 出站零扩张
def test_mvp1_has_no_egress_and_disables_network_tasks(cards_doc: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """A7：出站白名单未拍板前——联网任务全禁用、卡片零出站域。"""
    network_tasks = {
        task["key"]
        for group in cards_doc["function_groups"]
        for task in group["tasks"]
        if task["requires_egress"]
    }
    assert network_tasks, "联网任务集合不得为空（否则 A7 断言空转）"
    for card in cards:
        assert card["egress_domains"] == [], f"{card['agent_key']}: MVP-1 零出站"
        enabled = set(card["enabled_tasks"])
        assert not (enabled & network_tasks), f"{card['agent_key']}: 联网任务不得启用 {enabled & network_tasks}"
        # 联网任务须显式列入禁用清单并给出原因。
        declared = set(card["disabled_tasks"])
        assert network_tasks & set(task["key"] for group in cards_doc["function_groups"] for task in group["tasks"]) & enabled == set()
        for key in card["disabled_tasks"]:
            assert key in declared
            if key in network_tasks:
                assert card["disabled_reason"], f"{card['agent_key']}: 禁用联网任务须写原因"


def test_egress_allowlist_untouched_in_mvp1(cards: list[dict[str, Any]]) -> None:
    """A7：卡片不得携带任何出站域名。"""
    for card in cards:
        assert card["egress_domains"] == []
        assert card["egress_domains"] == []


# ---------------------------------------------------------------- A8 桌面零改
def test_cards_do_not_require_desktop_changes() -> None:
    """A8：MVP-1 为服务端数据面，桌面端零改动。"""
    raw = CARDS_PATH.read_text(encoding="utf-8")
    assert ".tsx" not in raw and "desktop/" not in raw


# ------------------------------------------------------- 组织树与卡片完整性
def test_six_function_groups_present_with_prohibitions(cards_doc: dict[str, Any]) -> None:
    """V1.0 §4.2：六职能组齐全，每组带岗位、产出与禁止事项。"""
    groups = cards_doc["function_groups"]
    assert {group["name"] for group in groups} == EXPECTED_GROUPS
    assert set(cards_doc["org_tree"]["group_keys"]) == {group["key"] for group in groups}
    for group in groups:
        assert group["roles"], f"{group['key']}: 岗位不得为空"
        assert group["outputs"], f"{group['key']}: 产出不得为空"
        assert group["prohibitions"], f"{group['key']}: 禁止事项不得为空"


def test_card_count_and_completeness(cards: list[dict[str, Any]]) -> None:
    """V1.0 §4.1：先用 5–7 个 Agent 兼任，不建几十个独立 Agent；字段齐全。"""
    assert 1 <= len(cards) <= 7, f"岗位卡数量越界：{len(cards)}"
    for card in cards:
        for field in REQUIRED_CARD_FIELDS:
            assert field in card, f"{card.get('agent_key')}: 缺字段 {field}"
            assert card[field] not in (None, "", [], {}), f"{card.get('agent_key')}: 空字段 {field}"


def test_card_group_and_task_references_resolve(cards_doc: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """卡片的职能组与任务引用必须解析得到——不得指向不存在的组或任务。"""
    group_keys = {group["key"] for group in cards_doc["function_groups"]}
    task_keys = {task["key"] for group in cards_doc["function_groups"] for task in group["tasks"]}
    for card in cards:
        assert set(card["function_groups"]) <= group_keys, f"{card['agent_key']}: 未知职能组"
        assert set(card["enabled_tasks"]) <= task_keys, f"{card['agent_key']}: 未知任务"
        assert set(card["disabled_tasks"]) <= task_keys, f"{card['agent_key']}: 未知任务"
        assert not (set(card["enabled_tasks"]) & set(card["disabled_tasks"])), f"{card['agent_key']}: 任务同时启用与禁用"


def test_card_prohibitions_include_group_prohibitions(cards_doc: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """卡片禁止事项须覆盖其所属职能组的全部禁止项（红线不得在挂卡时丢失）。"""
    group_prohibitions = {group["key"]: set(group["prohibitions"]) for group in cards_doc["function_groups"]}
    for card in cards:
        declared = set(card["prohibitions"])
        for group_key in card["function_groups"]:
            missing = group_prohibitions[group_key] - declared
            assert not missing, f"{card['agent_key']}: 漏挂组禁止项 {missing}"
