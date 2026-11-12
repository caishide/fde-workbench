"""指标越限 → 提示词复审工单（N4 G-14）——评估器三道闸与工单形状。

钉住：①出厂闸默认关＝永不建单（安全钉）；②规则闭集校验 fail-closed
（未知指标/未注册 prompt_ref/坏 JSON/非法 op/threshold 非数值）；③越限判定
（insufficient_data 永不判越限；严格比较语义）；④工单 draft 形状（target=
prompt 文本指针、finding_codes=[metrics_v31_breach]、created_by=None、指纹
16hex）；⑤同日幂等（每规则每日至多一张）。
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import delete

from test_agents_d4_harness import d4_app, d4_client, d4_settings  # noqa: F401  (pytest fixture)
from test_metrics_report import _user
from test_metrics_v31 import _seed_workflow_run
from test_quality_test_plans import _leader_project

from fde_api.extensions import db
from fde_api.metrics.review_tickets import (
    TICKET_METRIC_IDS,
    TicketRuleError,
    evaluate_metric_review_tickets,
    parse_rules,
)
from fde_api.simulation.models import ImprovementProposal

_VALID_RULE = (
    '[{"metric":"workflow_completion_rate","op":"<","threshold":0.5,'
    '"prompt_ref":"plans.delivery_plan_draft"}]'
)


@pytest.fixture(autouse=True)
def _clean_tickets(db_session):
    yield
    db_session.rollback()
    db_session.execute(delete(ImprovementProposal))
    db_session.commit()


@pytest.fixture()
def ticket_settings(d4_app, monkeypatch):
    cfg = SimpleNamespace(ai_review_ticket_enabled=False, ai_review_ticket_rules="")
    monkeypatch.setitem(d4_app.config, "SETTINGS", cfg)
    return cfg


def _seed_completion_rate(db_session, d4_client, d4_settings, *, succeeded: int, failed: int) -> None:
    """构造 workflow_completion_rate = succeeded/(succeeded+failed)。"""
    leader, project = _leader_project(db_session, d4_client, d4_settings, f"客户T{uuid4().hex[:6]}")
    for _ in range(succeeded):
        _seed_workflow_run(db_session, project, leader.user, status="succeeded", hops=0)
    for _ in range(failed):
        _seed_workflow_run(db_session, project, leader.user, status="failed", hops=0)
    db_session.commit()


def test_shipped_defaults_are_safe(ticket_settings, d4_app, db_session):
    """出厂闸默认关＋规则空 ⇒ 有数据也不建单（G-14 fail-safe 安全钉）。"""
    assert ticket_settings.ai_review_ticket_enabled is False
    assert ticket_settings.ai_review_ticket_rules == ""
    with d4_app.app_context():
        summary = evaluate_metric_review_tickets(db_session)
    assert summary == {
        "enabled": False,
        "rules_evaluated": 0,
        "breaches": 0,
        "created": 0,
        "skipped_existing": 0,
        "tickets": [],
    }
    assert db_session.query(ImprovementProposal).count() == 0


def test_disabled_gate_ignores_even_breaching_data(db_session, d4_client, d4_settings, ticket_settings, d4_app):
    _seed_completion_rate(db_session, d4_client, d4_settings, succeeded=0, failed=4)
    ticket_settings.ai_review_ticket_enabled = False
    ticket_settings.ai_review_ticket_rules = _VALID_RULE
    with d4_app.app_context():
        summary = evaluate_metric_review_tickets(db_session)
    assert summary["created"] == 0
    assert db_session.query(ImprovementProposal).count() == 0


def test_breach_creates_ticket(db_session, d4_client, d4_settings, ticket_settings, d4_app):
    _seed_completion_rate(db_session, d4_client, d4_settings, succeeded=1, failed=3)
    ticket_settings.ai_review_ticket_enabled = True
    ticket_settings.ai_review_ticket_rules = _VALID_RULE
    with d4_app.app_context():
        summary = evaluate_metric_review_tickets(db_session)
    assert summary["enabled"] is True
    assert summary["rules_evaluated"] == 1
    assert summary["breaches"] == 1
    assert summary["created"] == 1
    ticket = summary["tickets"][0]
    assert ticket["status"] == "draft"
    assert ticket["target"] == {"kind": "prompt", "ref": "plans.delivery_plan_draft"}
    assert ticket["finding_codes"] == ["metrics_v31_breach"]
    row = db_session.query(ImprovementProposal).one()
    assert len(row.fingerprint) == 16
    assert row.status == "draft"
    assert row.created_by_user_id is None
    assert row.proposal_key.startswith("TICKET-")


def test_no_breach_creates_nothing(db_session, d4_client, d4_settings, ticket_settings, d4_app):
    _seed_completion_rate(db_session, d4_client, d4_settings, succeeded=4, failed=0)
    ticket_settings.ai_review_ticket_enabled = True
    ticket_settings.ai_review_ticket_rules = _VALID_RULE
    with d4_app.app_context():
        summary = evaluate_metric_review_tickets(db_session)
    assert summary["breaches"] == 0 and summary["created"] == 0
    assert db_session.query(ImprovementProposal).count() == 0


def test_insufficient_data_never_fires(db_session, d4_settings, ticket_settings, d4_app):
    """空库 ⇒ workflow_completion_rate insufficient_data ⇒ 永不判越限（不编造）。"""
    ticket_settings.ai_review_ticket_enabled = True
    ticket_settings.ai_review_ticket_rules = _VALID_RULE
    with d4_app.app_context():
        summary = evaluate_metric_review_tickets(db_session)
    assert summary["breaches"] == 0 and summary["created"] == 0


def test_threshold_boundary_is_strict(db_session, d4_client, d4_settings, ticket_settings, d4_app):
    """op 语义机械：value==threshold 时 `>` 不触发、`>=` 触发。"""
    _seed_completion_rate(db_session, d4_client, d4_settings, succeeded=1, failed=1)
    ticket_settings.ai_review_ticket_enabled = True
    ticket_settings.ai_review_ticket_rules = (
        '[{"metric":"workflow_completion_rate","op":">","threshold":0.5,'
        '"prompt_ref":"plans.delivery_plan_draft"}]'
    )
    with d4_app.app_context():
        assert evaluate_metric_review_tickets(db_session)["created"] == 0
    ticket_settings.ai_review_ticket_rules = (
        '[{"metric":"workflow_completion_rate","op":">=","threshold":0.5,'
        '"prompt_ref":"plans.delivery_plan_draft"}]'
    )
    with d4_app.app_context():
        assert evaluate_metric_review_tickets(db_session)["created"] == 1


def test_same_day_evaluation_is_idempotent(db_session, d4_client, d4_settings, ticket_settings, d4_app):
    _seed_completion_rate(db_session, d4_client, d4_settings, succeeded=0, failed=4)
    ticket_settings.ai_review_ticket_enabled = True
    ticket_settings.ai_review_ticket_rules = _VALID_RULE
    with d4_app.app_context():
        first = evaluate_metric_review_tickets(db_session)
        second = evaluate_metric_review_tickets(db_session)
    assert first["created"] == 1
    assert second["created"] == 0 and second["skipped_existing"] == 1
    assert db_session.query(ImprovementProposal).count() == 1


def test_rule_validation_closed_sets():
    assert parse_rules("") == []
    assert parse_rules(None) == []
    assert parse_rules("   ") == []
    with pytest.raises(TicketRuleError) as bad_json:
        parse_rules("{not json")
    assert bad_json.value.code == "ticket_rules_invalid_json"
    with pytest.raises(TicketRuleError) as unknown_metric:
        parse_rules(
            '[{"metric":"nonexistent_metric","op":"<","threshold":1,'
            '"prompt_ref":"plans.delivery_plan_draft"}]'
        )
    assert unknown_metric.value.code == "ticket_rule_unknown_metric"
    with pytest.raises(TicketRuleError) as unthresholdable:
        parse_rules(
            '[{"metric":"workflow_hops_distribution","op":"<","threshold":1,'
            '"prompt_ref":"plans.delivery_plan_draft"}]'
        )
    assert unthresholdable.value.code == "ticket_rule_unknown_metric"
    with pytest.raises(TicketRuleError) as bad_op:
        parse_rules(
            '[{"metric":"workflow_completion_rate","op":"==","threshold":1,'
            '"prompt_ref":"plans.delivery_plan_draft"}]'
        )
    assert bad_op.value.code == "ticket_rule_invalid_op"
    with pytest.raises(TicketRuleError) as bad_threshold:
        parse_rules(
            '[{"metric":"workflow_completion_rate","op":"<","threshold":"0.5",'
            '"prompt_ref":"plans.delivery_plan_draft"}]'
        )
    assert bad_threshold.value.code == "ticket_rule_invalid_threshold"
    with pytest.raises(TicketRuleError) as unknown_ref:
        parse_rules(
            '[{"metric":"workflow_completion_rate","op":"<","threshold":0.5,'
            '"prompt_ref":"not.a.registered.key"}]'
        )
    assert unknown_ref.value.code == "ticket_rule_unknown_prompt_ref"


def test_metric_closed_set_excludes_object_valued_metrics():
    """hops_distribution 是 {avg,max} 对象值不可阈值化，不在闭集。"""
    assert "workflow_hops_distribution" not in TICKET_METRIC_IDS
    assert len(TICKET_METRIC_IDS) == 6
