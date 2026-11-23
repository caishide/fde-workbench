"""Ecosystem OS M2 AI 总部岗位卡目录装载器（只读，零新表）。

数据真身＝``seeds/ai_hq_cards.json``（只读，随代码发布，非用户可写）——
评审纪要 C3 红线：AI 组织树实现为配置与数据，禁止新建 org-chart 类表/模块。
本模块是那份配置的 fail-fast 读面（沿 ``agents/tools.py`` tool_groups 先例）：
装载即对既有注册面逐项解析，坏种子宁可起不来也不静默带病上岗。

卡片不是权限系统（V1.0 §4.4 明文）——本装载器只做**引用闭集**校验，一切
实际权限仍在服务端工具/数据访问层强制执行（能力矩阵 / 工具组交集管线 /
api_execute 确认流 / mailing 五闸）。写动作零入口：卡片只能声明只读 API
操作与只读工具组引用。

状态机（activation_state）：
- ``pending_owner_approval``（出厂态）：联网任务必须全部禁用、卡片零出站域；
- ``active``：OWNER 三项拍板落地后的人工状态，允许声明出站域（逐域校验）；
- ``retired``：整卡退役，卡片仍须通过结构校验（历史可读）。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, NoReturn

# agents→ai / agents→control 均为单向边（无环）；跨包引用按教训②在函数内
# 懒导入，避免顶层 import 面扩大被包环冻结闸盯上。
_SEEDS_DIR = Path(__file__).resolve().parents[3] / "seeds"
_CARDS_PATH = _SEEDS_DIR / "ai_hq_cards.json"

#: V1.0 §4.2 六职能组名称（逐字闭集——改名/增删须同步任务书评审）。
EXPECTED_GROUP_NAMES: frozenset[str] = frozenset({
    "增长与招商运营",
    "招生与学习运营",
    "企业客户运营",
    "项目交付运营",
    "区域与伙伴运营",
    "产品与技术运营",
})

#: V1.0 §4.3 Human Approval Queue 六类（审批类别不得自造）。
HUMAN_APPROVAL_QUEUE: frozenset[str] = frozenset({
    "legal_commercial_decisions",
    "pricing_billing_settlement",
    "certification_final_review",
    "regional_authorization",
    "production_data_writes",
    "customer_acceptance_disputes",
})

#: 卡片可为空的挂载点字段（其余 REQUIRED 字段一律非空）。
# prompt_purposes：无模型调用的纯确定性卡（如运营值班员 MVP）合法为空；
# disabled_tasks / egress_domains / disabled_reason：视状态可为空。
OPTIONAL_CARD_FIELDS: frozenset[str] = frozenset({
    "disabled_tasks",
    "disabled_reason",
    "egress_domains",
    "prompt_purposes",
})

#: V1.0 §4.4 角色卡十三项标准字段（+ 挂载点扩展字段）。
REQUIRED_CARD_FIELDS: tuple[str, ...] = (
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

#: 挂载点扩展字段（引用既有注册面，缺一即装载失败）。
REQUIRED_LINK_FIELDS: tuple[str, ...] = (
    "function_groups",
    "enabled_tasks",
    "disabled_tasks",
    "prompt_purposes",
    "capability_legs",
    "declared_tier",
    "egress_domains",
    "allowed_api_operations",
)

ACTIVATION_STATES: frozenset[str] = frozenset({
    "pending_owner_approval",
    "active",
    "retired",
})

#: V1.0 §4.1 兼任制上限（不建几十个独立 Agent）。
MAX_CARDS = 7

#: 卡片工具白名单只许引用只读工具组（组内出现写类/外效工具即装载失败）。
READ_TOOL_EFFECTS: frozenset[str] = frozenset({"read"})


def _fail(message: str) -> NoReturn:
    raise RuntimeError(f"ai_hq_cards.json seed invalid: {message}")


#: 真相层 token（仓库红线：客户真实资料只留 D:\test\FDE 等本地工作目录，
#: 卡片产物位置/数据范围声明不得指向它们）。
_FORBIDDEN_TRUTH_TOKENS: tuple[str, ...] = ("D:\\test\\FDE", "D:/test/FDE", "fdeops", "openfde")


def _nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as error:
        raise RuntimeError("ai_hq_cards.json seed unavailable") from error
    if not isinstance(payload, dict):
        _fail("top level must be an object")
    return payload


def _validate_groups(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = payload.get("function_groups")
    if not isinstance(groups, list) or len(groups) != len(EXPECTED_GROUP_NAMES):
        _fail(f"function_groups must list exactly {len(EXPECTED_GROUP_NAMES)} groups")
    by_key: dict[str, dict[str, Any]] = {}
    for group in groups:
        if not isinstance(group, dict):
            _fail("group row must be an object")
        name = group.get("name")
        key = group.get("key")
        if name not in EXPECTED_GROUP_NAMES:
            _fail(f"unknown group name: {name!r}")
        if not isinstance(key, str) or not key:
            _fail(f"group {name!r}: key missing")
        if key in by_key:
            _fail(f"duplicate group key: {key}")
        for field in ("roles", "outputs", "prohibitions"):
            if not isinstance(group.get(field), list) or not group[field]:
                _fail(f"group {key}: {field} must be a non-empty list")
        principles = group.get("principles", [])
        if not isinstance(principles, list):
            _fail(f"group {key}: principles must be a list")
        tasks = group.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            _fail(f"group {key}: tasks must be a non-empty list")
        for task in tasks:
            if (
                not isinstance(task, dict)
                or not isinstance(task.get("key"), str)
                or not task["key"]
                or not isinstance(task.get("requires_egress"), bool)
            ):
                _fail(f"group {key}: task rows invalid")
        by_key[key] = group
    org_tree = payload.get("org_tree")
    if not isinstance(org_tree, dict) or set(org_tree.get("group_keys") or []) != set(by_key):
        _fail("org_tree.group_keys must match function_groups keys")
    queue = org_tree.get("human_approval_queue")
    if not isinstance(queue, list) or set(queue) != HUMAN_APPROVAL_QUEUE:
        _fail("org_tree.human_approval_queue must equal the six V1.0 §4.3 categories")
    return by_key


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _validate_card(
    card: dict[str, Any],
    group_by_key: dict[str, dict[str, Any]],
    default_state: str,
) -> None:
    agent_key = card.get("agent_key")
    if not isinstance(agent_key, str) or not agent_key:
        _fail("card agent_key missing")
    # 真相层红线（挂卡即校验）：卡片任何字符串值不得指向本地真相层目录。
    for text in _iter_strings(card):
        for token in _FORBIDDEN_TRUTH_TOKENS:
            if token in text:
                _fail(f"card {agent_key}: forbidden truth-layer reference {token!r}")
    for field in REQUIRED_CARD_FIELDS + REQUIRED_LINK_FIELDS:
        if field in OPTIONAL_CARD_FIELDS:
            continue
        if not _nonempty(card.get(field)):
            _fail(f"card {agent_key}: field {field} empty")
    from fde_api.control.access import ACCESS_RANK, CAPABILITY_REQUIREMENTS
    from fde_api.control.api_catalog import CATALOG

    # 审批面：必挂人工审批，类别不得自造。
    if card.get("requires_human_approval") is not True:
        _fail(f"card {agent_key}: requires_human_approval must be true")
    queue = card.get("approval_queue")
    if not isinstance(queue, list) or not queue or not set(queue) <= HUMAN_APPROVAL_QUEUE:
        _fail(f"card {agent_key}: approval_queue must be a non-empty subset of the six categories")

    # 组与任务引用闭集。
    group_keys = set(card["function_groups"])
    unknown_groups = group_keys - set(group_by_key)
    if unknown_groups:
        _fail(f"card {agent_key}: unknown function_groups {sorted(unknown_groups)}")
    task_keys: dict[str, bool] = {}
    for key, group in group_by_key.items():
        for task in group["tasks"]:
            task_keys[task["key"]] = bool(task["requires_egress"])
    enabled, disabled = set(card["enabled_tasks"]), set(card["disabled_tasks"])
    unknown_tasks = (enabled | disabled) - set(task_keys)
    if unknown_tasks:
        _fail(f"card {agent_key}: unknown tasks {sorted(unknown_tasks)}")
    if enabled & disabled:
        _fail(f"card {agent_key}: tasks both enabled and disabled {sorted(enabled & disabled)}")

    # 出站纪律：出厂态联网任务全禁用（并写明原因）、零出站域；active 态才允许逐域声明。
    state = str(card.get("activation_state") or default_state)
    network_disabled = {key for key in disabled if task_keys[key]}
    if state == "pending_owner_approval":
        network_enabled = {key for key in enabled if task_keys[key]}
        if network_enabled:
            _fail(
                f"card {agent_key}: network tasks must stay disabled before owner approval: {sorted(network_enabled)}"
            )
        if card["egress_domains"]:
            _fail(f"card {agent_key}: egress_domains must be empty before owner approval")
        if network_disabled and not str(card.get("disabled_reason") or "").strip():
            _fail(f"card {agent_key}: disabled network tasks need a disabled_reason")
    elif state == "active":
        domains = card["egress_domains"]
        if not all(isinstance(domain, str) and domain and "/" not in domain for domain in domains):
            _fail(f"card {agent_key}: active-state egress_domains must be bare domain names")

    # 提示词 purpose：在册且在内网白名单（下划线风格）。
    from fde_api.ai.overlays import purpose_allowed
    from fde_api.ai.prompt_registry import PROMPT_REGISTRATIONS

    registered = {entry.key: entry.key.replace(".", "_") for entry in PROMPT_REGISTRATIONS}
    for key in card["prompt_purposes"]:
        if key not in registered:
            _fail(f"card {agent_key}: purpose not registered {key}")
        if not purpose_allowed(registered[key]):
            _fail(f"card {agent_key}: purpose is public-surface or not whitelisted {key}")

    # 能力腿：在既有矩阵内，声明档位不低于每条要求。
    tier = card.get("declared_tier")
    if tier not in ACCESS_RANK:
        _fail(f"card {agent_key}: unknown declared_tier {tier!r}")
    for leg in card["capability_legs"]:
        if leg not in CAPABILITY_REQUIREMENTS:
            _fail(f"card {agent_key}: unknown capability leg {leg}")
        required = CAPABILITY_REQUIREMENTS[leg]
        if ACCESS_RANK[tier] < ACCESS_RANK[required]:
            _fail(f"card {agent_key}: tier {tier} below requirement {required} of {leg}")

    # 工具白名单：只许引用既有只读工具组（组内含写类/外效工具即拒绝）。
    from fde_api.agents.tools import load_tool_groups
    from fde_api.control.mcp_gateway import TOOLS

    groups = load_tool_groups()
    for item in card["tool_allowlist"]:
        if not isinstance(item, str) or not item.startswith("group:"):
            _fail(f"card {agent_key}: tool_allowlist must reference groups only: {item!r}")
        group_name = item.split(":", 1)[1]
        if group_name not in groups:
            _fail(f"card {agent_key}: unknown tool group {group_name}")
        for tool in groups[group_name]:
            effect = TOOLS.get(tool, (None, None, None, "read", 0))[3] if tool in TOOLS else None
            if effect is not None and effect not in READ_TOOL_EFFECTS:
                _fail(f"card {agent_key}: tool group {group_name} contains non-read tool {tool}")

    # API 操作：⊆ 目录且全只读（无写类、无确认类、无外效）。
    for operation in card["allowed_api_operations"]:
        row = CATALOG.get(operation)
        if row is None:
            _fail(f"card {agent_key}: unknown api operation {operation}")
        if row["effect"] != "read" or row["confirmation"]:
            _fail(f"card {agent_key}: api operation must be read-only and non-confirmation {operation}")

    # 禁止事项须覆盖所属组的全部禁止项（红线不得在挂卡时丢失）。
    declared = set(card["prohibitions"])
    for group_key in card["function_groups"]:
        missing = set(group_by_key[group_key]["prohibitions"]) - declared
        if missing:
            _fail(f"card {agent_key}: missing group prohibitions {sorted(missing)}")


@lru_cache(maxsize=1)
def load_hq_cards() -> dict[str, Any]:
    """装载并校验岗位卡目录（进程级缓存，沿 agents.json 首访装载先例）。

    返回原始 dict（校验通过）；任何引用闭集破坏 ⇒ ``RuntimeError``（fail-fast，
    沿 tool_groups 先例：坏种子宁可起不来也不静默带病上岗）。
    """
    return _validate_payload_unmemoized(_load_payload(_CARDS_PATH))


def _validate_payload_unmemoized(payload: dict[str, Any]) -> dict[str, Any]:
    """全量校验（无缓存）——装载主体；测试负例直接喂变异 payload 复用。"""
    if payload.get("version") != 1:
        _fail("version must be 1")
    state = payload.get("activation_state")
    if state not in ACTIVATION_STATES:
        _fail(f"unknown activation_state {state!r}")
    group_by_key = _validate_groups(payload)
    cards = payload.get("cards")
    if not isinstance(cards, list) or not (1 <= len(cards) <= MAX_CARDS):
        _fail(f"cards must be a non-empty list of at most {MAX_CARDS}")
    seen_keys: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            _fail("card row must be an object")
        agent_key = card.get("agent_key")
        if not isinstance(agent_key, str) or not agent_key:
            _fail("card agent_key missing")
        if agent_key in seen_keys:
            _fail(f"duplicate agent_key: {agent_key}")
        seen_keys.add(agent_key)
        _validate_card(card, group_by_key, state)
    return payload
