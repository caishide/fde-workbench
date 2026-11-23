"""Ecosystem OS M2 AI 总部岗位卡机械钉（挂卡式零新表）。

对应立项书《EcosystemOS_M2立项书_AI总部MVP挂卡式_草案_v0.1》验收条件 A1–A8。
批次二补强：校验逻辑下沉至生产装载器 ``fde_api.agents.hq_cards.load_hq_cards``
（fail-fast，沿 tool_groups 先例），本文件钉两件事——

1. **装载器行为**：对种子做合法引用闭集校验（purpose 注册与内网白名单／能力腿
   在既有矩阵／审批类别 ⊆ V1.0 §4.3 六类／工具组纯读／API 操作全只读／出站
   纪律／组禁止项不漏挂），任何破坏 ⇒ RuntimeError 且指名道姓；
2. **种子静态面**：零新表零新模块线索、桌面零改动、外发通道零声明。

纪律：本文件只读种子与既有注册面，不写库、不发信、不出站。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fde_api.agents import hq_cards
from fde_api.agents.hq_cards import (
    EXPECTED_GROUP_NAMES,
    HUMAN_APPROVAL_QUEUE,
    MAX_CARDS,
    REQUIRED_CARD_FIELDS,
    load_hq_cards,
)

SEEDS_DIR = Path(__file__).resolve().parents[1] / "seeds"
CARDS_PATH = SEEDS_DIR / "ai_hq_cards.json"
TOOL_GROUPS_PATH = SEEDS_DIR / "tool_groups.json"


@pytest.fixture(scope="module")
def cards_doc() -> dict[str, Any]:
    return load_hq_cards()


@pytest.fixture(scope="module")
def cards(cards_doc: dict[str, Any]) -> list[dict[str, Any]]:
    return list(cards_doc["cards"])


def _mutated_copy(cards_doc: dict[str, Any], mutate) -> dict[str, Any]:
    """深拷贝种子并施加变异（供装载器负例断言）。"""
    import copy

    doc = copy.deepcopy(cards_doc)
    mutate(doc)
    return doc


def _assert_load_fails(cards_doc: dict[str, Any], mutate, fragment: str) -> None:
    doc = _mutated_copy(cards_doc, mutate)
    with pytest.raises(RuntimeError) as error:
        hq_cards._validate_payload_unmemoized(doc)
    assert fragment in str(error.value)


# ------------------------------------------------------------------ A1 零新表
def test_cards_are_data_only_no_new_table_or_module():
    """A1：岗位卡是数据面目录——零新表、零新模块（纪要 C3 红线）。"""
    raw = CARDS_PATH.read_text(encoding="utf-8")
    for token in ("__tablename__", "Mapped[", "Base,", "alembic", "revision ="):
        assert token not in raw, f"岗位卡目录不得含建表/迁移线索：{token}"


def test_cards_live_in_seeds_not_in_src(cards_doc: dict[str, Any]) -> None:
    """A1：目录落 seeds/（随代码发布的只读数据面），不落独立表。"""
    assert CARDS_PATH.parent == SEEDS_DIR
    assert "cards" in CARDS_PATH.name
    raw = CARDS_PATH.read_text(encoding="utf-8")
    for table in ("agent_registry", "org_chart", "job_card", "ai_hq_card"):
        assert table not in raw, f"岗位卡不得落独立表：{table}"
    assert cards_doc["activation_state"] == "pending_owner_approval"


# ------------------------------------------------------- A2 purpose 注册与白名单
def test_every_card_purpose_is_registered_and_allowed(cards: list[dict[str, Any]]) -> None:
    """A2：卡片声明的 purpose 必须在 prompt_registry 在册且在内网白名单内。"""
    from fde_api.ai.overlays import purpose_allowed
    from fde_api.ai.prompt_registry import PROMPT_REGISTRATIONS

    registered = {entry.key for entry in PROMPT_REGISTRATIONS}
    public = {
        entry.key
        for entry in PROMPT_REGISTRATIONS
        if not purpose_allowed(entry.key.replace(".", "_"))
    }
    for card in cards:
        for key in card["prompt_purposes"]:
            assert key in registered, f"{card['agent_key']}: purpose 未注册 {key}"
            assert key not in public, f"{card['agent_key']}: purpose 是公网面 {key}"


def test_loader_rejects_unregistered_purpose(cards_doc: dict[str, Any]) -> None:
    """A2 负例：引用未注册 purpose ⇒ 装载失败且指名道姓。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][1].update({"prompt_purposes": ["does.not.exist"]}),
        "purpose not registered",
    )


def test_loader_rejects_public_surface_purpose(cards_doc: dict[str, Any]) -> None:
    """A2 负例：引用公网面 purpose ⇒ 装载失败（内网白名单排除）。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][1].update({"prompt_purposes": ["diagnostics.report"]}),
        "not whitelisted",
    )


# ------------------------------------------------------------ A3 确认类不越界
def test_high_risk_actions_require_human_approval(cards: list[dict[str, Any]]) -> None:
    """A3：卡片高危动作一律挂人工审批——AI 不自批。"""
    for card in cards:
        assert card["requires_human_approval"] is True, f"{card['agent_key']}: 必须挂人工审批"
        assert card["approval_queue"], f"{card['agent_key']}: 审批队列不得为空"
        assert set(card["approval_queue"]) <= HUMAN_APPROVAL_QUEUE, f"{card['agent_key']}: 自造审批类别"


def test_card_api_operations_are_read_only(cards: list[dict[str, Any]]) -> None:
    """A3：卡片声明的 API 操作必须 ⊆ 目录且全只读（无写类/确认类/外效）。"""
    from fde_api.control.api_catalog import CATALOG

    for card in cards:
        assert card["allowed_api_operations"], f"{card['agent_key']}: 须显式声明操作闭集"
        for operation in card["allowed_api_operations"]:
            row = CATALOG.get(operation)
            assert row is not None, f"{card['agent_key']}: 未知操作 {operation}"
            assert row["effect"] == "read", f"{card['agent_key']}: 非只读操作 {operation}"
            assert not row["confirmation"], f"{card['agent_key']}: 确认类操作 {operation}"


def test_loader_rejects_write_operation(cards_doc: dict[str, Any]) -> None:
    """A3 负例：声明写类操作 ⇒ 装载失败。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][0]["allowed_api_operations"].append("projects.create"),
        "must be read-only",
    )


def test_loader_rejects_self_made_approval_queue(cards_doc: dict[str, Any]) -> None:
    """A3 负例：自造审批类别 ⇒ 装载失败。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][0].update({"approval_queue": ["self_made_queue"]}),
        "six categories",
    )


def test_capability_legs_are_registered_and_tier_consistent(cards: list[dict[str, Any]]) -> None:
    """A3：能力腿必须在既有能力矩阵内，且声明档位不高于矩阵要求。"""
    from fde_api.control.access import ACCESS_RANK, CAPABILITY_REQUIREMENTS

    for card in cards:
        assert card["capability_legs"], f"{card['agent_key']}: 必须声明能力腿"
        for leg in card["capability_legs"]:
            assert leg in CAPABILITY_REQUIREMENTS, f"{card['agent_key']}: 未知能力腿 {leg}"
            required = CAPABILITY_REQUIREMENTS[leg]
            assert ACCESS_RANK[card["declared_tier"]] >= ACCESS_RANK[required], (
                f"{card['agent_key']}: 声明档位 {card['declared_tier']} 低于能力 {leg} 要求的 {required}"
            )


def test_loader_rejects_unknown_capability_leg(cards_doc: dict[str, Any]) -> None:
    """A3 负例：未知能力腿 ⇒ 装载失败。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][2].update({"capability_legs": ["capability.not.registered"]}),
        "unknown capability leg",
    )


# ----------------------------------------------------------------- A4 只读面
def test_cards_declare_no_write_entry(cards: list[dict[str, Any]]) -> None:
    """A4：卡片不引入写入口——能力腿只落在只读/计划类，写类动作走既有确认闸。"""
    write_legs = {"workbench.write", "memo.shared.write", "task.batch_assign", "ontology.write", "agent.code.write"}
    for card in cards:
        assert not (set(card["capability_legs"]) & write_legs), (
            f"{card['agent_key']}: MVP-1 不得持写类能力腿"
        )


def test_tool_allowlist_points_to_readonly_groups(cards: list[dict[str, Any]]) -> None:
    """A4：工具白名单只引用既有工具组，且组内全部是只读工具。"""
    from fde_api.agents.tools import load_tool_groups
    from fde_api.control.mcp_gateway import TOOLS

    groups = load_tool_groups()
    for card in cards:
        assert card["tool_allowlist"], f"{card['agent_key']}: 工具白名单不得为空"
        for item in card["tool_allowlist"]:
            assert item.startswith("group:"), f"{card['agent_key']}: 只许引用工具组 {item}"
            group_name = item.split(":", 1)[1]
            assert group_name in groups, f"{card['agent_key']}: 未知工具组 {group_name}"
            for tool in groups[group_name]:
                effect = TOOLS[tool][3] if tool in TOOLS else "read"  # 沙箱 read_file 视为只读
                assert effect == "read", f"{card['agent_key']}: 工具组 {group_name} 含非只读工具 {tool}"


def test_loader_rejects_non_read_tool_group(cards_doc: dict[str, Any]) -> None:
    """A4 负例：引用含写类工具的组 ⇒ 装载失败。

    ``ontology-agent`` 组含 ``ontology_action_propose``（write_db）——
    用它构造一个临时组引用，验证装载器按效果拒绝而非按名单拒绝。
    """
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][0].update({"tool_allowlist": ["group:ontology-agent"]}),
        "non-read tool",
    )


def test_loader_rejects_unknown_tool_group(cards_doc: dict[str, Any]) -> None:
    """A4 负例：未知工具组 ⇒ 装载失败。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][0].update({"tool_allowlist": ["group:not_a_group"]}),
        "unknown tool group",
    )


# ------------------------------------------------------------ A5 出口面闭集
def test_cards_have_no_direct_outbound_channel(cards: list[dict[str, Any]]) -> None:
    """A5：卡片不自带发信/外发通道——出口只走既有文档面与 mailing 五闸。"""
    raw = CARDS_PATH.read_text(encoding="utf-8")
    for token in ("smtp", "ses_client", "send_email(", "requests.get", "httpx", "urllib"):
        assert token not in raw.lower(), f"岗位卡目录不得含直接外发通道：{token}"


def test_loader_rejects_external_effect_operation(cards_doc: dict[str, Any]) -> None:
    """A5 负例：声明外效操作（排队作业/模型调用）⇒ 装载失败。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][0]["allowed_api_operations"].append("documents.generate"),
        "must be read-only",
    )


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
        joined = "\n".join(_iter_strings(card))
        for token in truth_tokens:
            assert token not in joined, f"{card['agent_key']}: 禁止触碰真相层 {token}"
    assistant = next(card for card in cards if card["agent_key"] == "ai_hq.product_engineering_assistant")
    assert any("执行被审代码" in item for item in assistant["prohibitions"]), "AI 审查不执行被审代码（仓库红线）"


def test_loader_rejects_truth_layer_reference(cards_doc: dict[str, Any]) -> None:
    """A6 负例：产物位置指向真相层 ⇒ 装载失败（装载器承担路径红线）。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][0].update({"artifact_location": "D:/test/FDE/engagements/raw"}),
        "forbidden truth-layer reference",
    )


# ------------------------------------------------------------- A7 出站零扩张
def test_mvp1_has_no_egress_and_disables_network_tasks(cards_doc: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """A7：出站白名单未拍板前——联网任务全禁用、卡片零出站域、禁用联网任务须写原因。"""
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
        disabled = set(card["disabled_tasks"])
        if disabled & network_tasks:
            assert str(card.get("disabled_reason") or "").strip(), (
                f"{card['agent_key']}: 禁用联网任务须写原因"
            )


def test_loader_rejects_enabled_network_task(cards_doc: dict[str, Any]) -> None:
    """A7 负例：出厂态启用联网任务 ⇒ 装载失败（先从禁用清单移除，规避互斥）。"""
    network_task = next(
        task["key"]
        for group in cards_doc["function_groups"]
        for task in group["tasks"]
        if task["requires_egress"]
    )

    def mutate(doc: dict[str, Any]) -> None:
        card = doc["cards"][0]
        card["disabled_tasks"] = [key for key in card["disabled_tasks"] if key != network_task]
        card["enabled_tasks"].append(network_task)

    _assert_load_fails(cards_doc, mutate, "must stay disabled")


def test_loader_rejects_egress_domains_before_approval(cards_doc: dict[str, Any]) -> None:
    """A7 负例：出厂态携带出站域 ⇒ 装载失败。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][0].update({"egress_domains": ["example.com"]}),
        "egress_domains must be empty",
    )


# ---------------------------------------------------------------- A8 桌面零改
def test_cards_do_not_require_desktop_changes() -> None:
    """A8：MVP-1 为服务端数据面，桌面端零改动。"""
    raw = CARDS_PATH.read_text(encoding="utf-8")
    assert ".tsx" not in raw and "desktop/" not in raw


# ------------------------------------------------------- 组织树与卡片完整性
def test_six_function_groups_present_with_prohibitions(cards_doc: dict[str, Any]) -> None:
    """V1.0 §4.2：六职能组齐全，每组带岗位、产出与禁止事项。"""
    groups = cards_doc["function_groups"]
    assert {group["name"] for group in groups} == set(EXPECTED_GROUP_NAMES)
    for group in groups:
        assert group["roles"], f"{group['key']}: 岗位不得为空"
        assert group["outputs"], f"{group['key']}: 产出不得为空"
        assert group["prohibitions"], f"{group['key']}: 禁止事项不得为空"


def test_card_count_and_completeness(cards: list[dict[str, Any]]) -> None:
    """V1.0 §4.4：兼任制上限内，卡片十三项标准字段齐全非空。"""
    assert 1 <= len(cards) <= MAX_CARDS, f"岗位卡数量越界：{len(cards)}"
    for card in cards:
        for field in REQUIRED_CARD_FIELDS:
            assert card.get(field) not in (None, "", [], {}), f"{card.get('agent_key')}: 空字段 {field}"


def test_card_group_and_task_references_resolve(cards_doc: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """卡片的职能组与任务引用必须解析得到——不得指向不存在的组或任务。"""
    group_keys = {group["key"] for group in cards_doc["function_groups"]}
    task_keys = {task["key"] for group in cards_doc["function_groups"] for task in group["tasks"]}
    for card in cards:
        assert set(card["function_groups"]) <= group_keys, f"{card['agent_key']}: 未知职能组"
        assert set(card["enabled_tasks"]) <= task_keys, f"{card['agent_key']}: 未知任务"
        assert set(card["disabled_tasks"]) <= task_keys, f"{card['agent_key']}: 未知任务"
        assert not (set(card["enabled_tasks"]) & set(card["disabled_tasks"])), (
            f"{card['agent_key']}: 任务同时启用与禁用"
        )


def test_card_prohibitions_include_group_prohibitions(cards_doc: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    """卡片禁止事项须覆盖其所属职能组的全部禁止项（红线不得在挂卡时丢失）。"""
    group_prohibitions = {group["key"]: set(group["prohibitions"]) for group in cards_doc["function_groups"]}
    for card in cards:
        declared = set(card["prohibitions"])
        for group_key in card["function_groups"]:
            missing = group_prohibitions[group_key] - declared
            assert not missing, f"{card['agent_key']}: 漏挂组禁止项 {missing}"


def test_loader_rejects_missing_group_prohibition(cards_doc: dict[str, Any]) -> None:
    """负例：漏挂组禁止项 ⇒ 装载失败。"""
    _assert_load_fails(
        cards_doc,
        lambda doc: doc["cards"][0].update({"prohibitions": ["仅保留一条"]}),
        "missing group prohibitions",
    )


def test_loader_rejects_duplicate_agent_key(cards_doc: dict[str, Any]) -> None:
    """负例：重复 agent_key ⇒ 装载失败。"""
    duplicate = json.loads(json.dumps(cards_doc["cards"][1], ensure_ascii=False))
    duplicate["agent_key"] = cards_doc["cards"][0]["agent_key"]

    def mutate(doc: dict[str, Any]) -> None:
        doc["cards"][1] = duplicate

    _assert_load_fails(cards_doc, mutate, "duplicate agent_key")


def test_loader_rejects_card_count_above_concurrency_limit(cards_doc: dict[str, Any]) -> None:
    """V1.0 §4.1：超过兼任制上限 ⇒ 装载失败（不建几十个独立 Agent）。"""

    def mutate(doc: dict[str, Any]) -> None:
        extra = json.loads(json.dumps(doc["cards"][0], ensure_ascii=False))
        doc["cards"] = doc["cards"] + [extra for _ in range(MAX_CARDS)]

    _assert_load_fails(cards_doc, mutate, "at most")
