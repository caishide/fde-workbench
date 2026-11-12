"""指标越限 → 提示词复审工单（AI 原生化 N4，G-14）。

**「指标触发至少一个自动改进动作」的机械落点**：v31 数值指标按规则判越限
⇒ 经 ``simulation/release_channel.create_review_ticket``（全仓唯一提案写入
点，静态钉守）自动生成**draft 提案形态的复审工单**（target=prompt 文本指
针）。动作是「工单」，不是自动改提示词（任务书 N4 边界）。

**fail-safe 三道闸（沿 N6 质量路由同尺）**：
1. 出厂闸 ``FDE_AI_REVIEW_TICKET_ENABLED`` 默认 False ⇒ 永不建单；
2. 规则 JSON（``FDE_AI_REVIEW_TICKET_RULES``）空/不可解析 ⇒ 无规则不建单
   （评估入口对「闸开但规则坏」显式 422 fail-closed——开闸却配了坏规则是
   运维错误，不静默吞）；
3. 指标 ``insufficient_data``（value None 或样本 0）⇒ 永不判越限（不编造）。

规则闭集校验：metric ∈ v31 六个数值指标（hops_distribution 是 {avg,max} 对
象值不可阈值化，不在闭集）；op ∈ {<, <=, >, >=}；prompt_ref ∈
``ai/prompt_registry.py`` 注册键（未注册键 422——工单必须指向在册提示词面）。
工单指纹含 UTC 日 ⇒ 每规则每日至多一张，重复评估幂等。
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from fde_api.metrics.service import build_metrics_report
from fde_api.simulation import release_channel

# v31 数值指标闭集（可阈值化的六个；hops_distribution 值是 {avg,max} 对象，
# 不进闭集——想守 hops 上限请用 workflows 域已有的 MAX_RUN_HOPS 熔断）。
TICKET_METRIC_IDS = (
    "workflow_completion_rate",
    "workflow_approval_latency_minutes",
    "requirement_approval_rate",
    "ontology_candidate_adoption_rate",
    "plan_task_decomposition_rate",
    "test_first_pass_rate",
)

_OPS = ("<", "<=", ">", ">=")


class TicketRuleError(Exception):
    """规则面运维错误（422 fail-closed：闸开但规则坏＝显式报错不静默）。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_rules(raw: str | None) -> list[dict[str, Any]]:
    """解析并闭集校验复审规则（空 ⇒ []；坏 ⇒ TicketRuleError）。"""
    text = (raw or "").strip()
    if not text:
        return []
    try:
        rules = json.loads(text)
    except json.JSONDecodeError as error:
        raise TicketRuleError(
            "ticket_rules_invalid_json", f"复审规则不是合法 JSON：{error}"
        ) from None
    if not isinstance(rules, list) or not rules:
        raise TicketRuleError("ticket_rules_invalid_json", "复审规则必须是非空 JSON 数组。")
    from fde_api.ai.prompt_registry import PROMPT_REGISTRATIONS

    registered_keys = {entry.key for entry in PROMPT_REGISTRATIONS}
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(rules):
        if not isinstance(item, dict):
            raise TicketRuleError("ticket_rules_invalid_json", f"规则#{index} 必须是对象。")
        metric = item.get("metric")
        op = item.get("op")
        threshold = item.get("threshold")
        prompt_ref = item.get("prompt_ref")
        if metric not in TICKET_METRIC_IDS:
            raise TicketRuleError(
                "ticket_rule_unknown_metric",
                f"规则#{index} metric 不可阈值化或不在 v31 数值指标闭集：{metric}"
                f"（允许：{', '.join(TICKET_METRIC_IDS)}）",
            )
        if op not in _OPS:
            raise TicketRuleError("ticket_rule_invalid_op", f"规则#{index} op 非法：{op}")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise TicketRuleError(
                "ticket_rule_invalid_threshold", f"规则#{index} threshold 必须是数值。"
            )
        if prompt_ref not in registered_keys:
            raise TicketRuleError(
                "ticket_rule_unknown_prompt_ref",
                f"规则#{index} prompt_ref 未在提示词注册表登记：{prompt_ref}",
            )
        validated.append(
            {"metric": metric, "op": op, "threshold": threshold, "prompt_ref": prompt_ref}
        )
    return validated


def _breaches(metric: dict[str, Any], op: str, threshold: float) -> bool:
    """越限判定：insufficient_data 永不判越限（第三道闸，不编造）。"""
    value = metric.get("value")
    sample = metric.get("sample_size")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    if isinstance(sample, bool) or not isinstance(sample, int) or sample <= 0:
        return False
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    return value >= threshold


def evaluate_metric_review_tickets(session: Session) -> dict[str, Any]:
    """评估全部规则并建单（CLI 入口；无 actor——工单 draft 由人工复核认领）。"""
    from flask import current_app

    settings = current_app.config["SETTINGS"]
    if not settings.ai_review_ticket_enabled:
        return {
            "enabled": False,
            "rules_evaluated": 0,
            "breaches": 0,
            "created": 0,
            "skipped_existing": 0,
            "tickets": [],
        }
    rules = parse_rules(settings.ai_review_ticket_rules)
    report = build_metrics_report(session)
    metrics_by_key: dict[str, dict[str, Any]] = {}
    for section in report.get("sections", {}).values():
        for metric in section:
            metrics_by_key[metric["key"]] = metric
    utc_date = datetime.now(UTC).date().isoformat()
    tickets: list[dict[str, Any]] = []
    skipped = 0
    breaches = 0
    for rule in rules:
        metric = metrics_by_key.get(rule["metric"])
        if metric is None:
            # 闭集校验已保证 metric 合法；报告缺行＝口径漂移，fail-closed。
            raise TicketRuleError(
                "ticket_metric_missing_in_report",
                f"指标 {rule['metric']} 未出现在指标报告（口径漂移？）",
            )
        if not _breaches(metric, rule["op"], float(rule["threshold"])):
            continue
        breaches += 1
        ticket, outcome = release_channel.create_review_ticket(
            rule=rule,
            evidence={
                "utc_date": utc_date,
                "value": metric.get("value"),
                "sample_size": metric.get("sample_size"),
                "metric_status": metric.get("status"),
                "metric_key": metric.get("key"),
                "report_generated_at": report.get("generated_at"),
            },
        )
        if outcome == "created" and ticket is not None:
            tickets.append(ticket)
        else:
            skipped += 1
    return {
        "enabled": True,
        "rules_evaluated": len(rules),
        "breaches": breaches,
        "created": len(tickets),
        "skipped_existing": skipped,
        "tickets": tickets,
    }
