"""商业化运维就绪度汇总（只读、admin）——配置缺口 ＋ 售卖闸条件登记态。

**为什么有这层**：任务书 §17 的商业数值本期**一律不落数**（保护期长度／续期
条件／归属判定／分成比例／认证费金额／试运营升级指标），区域售卖闸的四项合规
条件也依赖法务与外部输入——这些「缺什么、缺到哪一步」此前只活在文档里，管理员
在系统里看不到，「上线才发现没填」的风险全靠人记。本模块把缺口汇总成**一个
只读面**：状态权威在服务端（配置位行 ＋ 售卖闸行），桌面端只负责呈现。

三条纪律：

1. **不落任何数值**：本模块只报状态（``unset``／``configured``）与键名，
   **绝不补默认值**——缺省即「不可收款／不可触限」的 fail-closed 方向不变；
2. **治理面不进 api_catalog**：与既有 commercial admin 面同款（写面已如此）；
3. **不读证据正文**：售卖闸条件只出「是否已登记」＋指针，与 ``serialize_gate``
   同尺（证据原件永不入库、不回显）。

标签与「等谁拍板」的话术是**服务端单一权威**（``FEE_SLOT_LABELS`` 等）——
桌面端只渲染，不自带口径，避免两处各写一份说明而漂移。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.commercial.attribution_service import list_rules
from fde_api.commercial.ledger_service import list_fee_configs, list_split_rules
from fde_api.commercial.models import (
    CHARGEABLE_FEE_KEYS,
    FEE_CONFIG_KEYS,
    OPPORTUNITY_RULE_KEYS,
)
from fde_api.commercial.regional_service import get_or_create_gate, serialize_gate
from fde_api.commercial.service import CommercialServiceError

# ── 槽位标签与「等谁拍板」（服务端单一权威；桌面端只渲染）──
FEE_SLOT_LABELS: dict[str, str] = {
    "certification_fee": "认证费金额",
    "mentoring_period_days": "陪跑期限",
    "certification_pass_threshold": "认证通过线",
}

OPPORTUNITY_SLOT_LABELS: dict[str, str] = {
    "protection_period_days": "保护期长度",
    "renewal_conditions": "续期条件",
    "customer_choice": "客户自主选择权",
    "dispute_handling": "争议处理机制",
    "attribution_criteria": "归属判定",
}

GATE_CONDITION_LABELS: dict[str, str] = {
    "filing": "特许经营合同备案",
    "disclosure": "订立前书面披露",
    "cooling_off": "单方解除冷静期条款",
    "qualification": "主体资格（至少 2 个直营店且经营满 1 年）",
}

# 缺口等谁——指向**已登记的外部输入**，不发明新流程
WAITING_NUMERIC = "任务书 §17 商业数值拍板（数值本期一律不落数）"
WAITING_SPLIT = "任务书 §17 分成比例拍板"
WAITING_LEGAL = "法务/合规外部输入（ADR-005 §2.2 合规条件登记）"


def _require_admin(actor: User) -> None:
    if actor.role != "admin":
        raise CommercialServiceError(
            "commercial_admin_required", "商业化治理面仅系统运维员可用。", 403
        )


def _slot_entries(
    keys: tuple[str, ...],
    rows: list[Any],
    *,
    labels: dict[str, str],
    waiting_for: str,
    chargeable: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    """按**权威键集**枚举槽位（行只提供状态）——槽位永不缺项。

    键集是常量（``FEE_CONFIG_KEYS``／``OPPORTUNITY_RULE_KEYS``），行是状态：
    读面按键集枚举而不是按行枚举，因此即使某行缺失也照常呈现（status=unset），
    不会静默少报一个槽位——「缺什么」正是这块屏存在的意义。
    """
    by_key = {row.key: row for row in rows}
    entries: list[dict[str, Any]] = []
    for key in keys:
        row = by_key.get(key)
        status = row.status if row is not None else "unset"
        entries.append(
            {
                "key": key,
                "label": labels.get(key, key),
                "value_kind": getattr(row, "value_kind", None),
                "status": status,
                "configured": status == "configured",
                "chargeable": key in chargeable,
                "waiting_for": None if status == "configured" else waiting_for,
            }
        )
    return entries


def commercial_readiness(session: Session, *, actor: User) -> dict[str, Any]:
    """商业化就绪度汇总（admin）——只报状态与键名，**不落数值**。"""
    _require_admin(actor)

    fee_entries = _slot_entries(
        FEE_CONFIG_KEYS,
        list_fee_configs(session),
        labels=FEE_SLOT_LABELS,
        waiting_for=WAITING_NUMERIC,
        chargeable=CHARGEABLE_FEE_KEYS,
    )
    rule_entries = _slot_entries(
        OPPORTUNITY_RULE_KEYS,
        list_rules(session),
        labels=OPPORTUNITY_SLOT_LABELS,
        waiting_for=WAITING_NUMERIC,
    )
    split_rows = list_split_rules(session)
    split_configured = [row for row in split_rows if row.status == "configured"]

    gate = get_or_create_gate(session)
    gate_payload = serialize_gate(gate)
    missing_conditions = [
        key for key, item in gate_payload["conditions"].items() if not item["registered"]
    ]
    condition_entries = [
        {
            "key": key,
            "label": GATE_CONDITION_LABELS.get(key, key),
            "registered": item["registered"],
            "signed_at": item["signed_at"],
            "waiting_for": None if item["registered"] else WAITING_LEGAL,
        }
        for key, item in gate_payload["conditions"].items()
    ]

    unset_fee = [entry for entry in fee_entries if not entry["configured"]]
    unset_rules = [entry for entry in rule_entries if not entry["configured"]]
    blockers: list[dict[str, Any]] = []
    for entry in unset_fee:
        blockers.append(
            {
                "kind": "fee_config",
                "key": entry["key"],
                "label": entry["label"],
                "severity": "blocking" if entry["chargeable"] else "pending",
                "waiting_for": entry["waiting_for"],
            }
        )
    for entry in unset_rules:
        blockers.append(
            {
                "kind": "opportunity_rule",
                "key": entry["key"],
                "label": entry["label"],
                "severity": "blocking",
                "waiting_for": entry["waiting_for"],
            }
        )
    if not split_configured:
        blockers.append(
            {
                "kind": "split_rule",
                "key": "split_rules",
                "label": "项目分成比例（按角色 × 项目类型）",
                "severity": "pending",
                "waiting_for": WAITING_SPLIT,
            }
        )
    for entry in condition_entries:
        if not entry["registered"]:
            blockers.append(
                {
                    "kind": "sale_gate_condition",
                    "key": entry["key"],
                    "label": entry["label"],
                    "severity": "blocking",
                    "waiting_for": entry["waiting_for"],
                }
            )

    return {
        "config_slots": {
            "fee_configs": fee_entries,
            "opportunity_rules": rule_entries,
            "split_rules": {
                "status": "configured" if split_configured else "unset",
                "rows": len(split_rows),
                "configured_rows": len(split_configured),
                "waiting_for": None if split_configured else WAITING_SPLIT,
            },
        },
        "sale_gate": {
            "status": gate_payload["status"],
            "conditions": condition_entries,
            "missing_conditions": missing_conditions,
            "ready_to_open": gate_payload["status"] != "opened" and not missing_conditions,
            "opened_at": gate_payload["opened_at"],
        },
        "blockers": blockers,
        "summary": {
            "unset_fee_configs": len(unset_fee),
            "unset_opportunity_rules": len(unset_rules),
            "split_rules_configured": len(split_configured),
            "missing_gate_conditions": len(missing_conditions),
            "blocking_count": sum(1 for item in blockers if item["severity"] == "blocking"),
        },
    }
