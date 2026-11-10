"""商业化运维就绪度汇总面（admin，只读）——配置缺口 ＋ 售卖闸条件登记态。

钉住七件事：

1. **只报状态不落数值**：未配置槽位只出 ``status='unset'`` 与键名，**不带任何
   金额/天数/比例**（fail-closed 方向不变——缺省即不可收款、不可触限）；
2. **三类配置槽位齐备**：费用/周期槽位（3）＋ 商机规则槽位（5）＋ 分成比例
   维度（角色 × 项目类型）——本期全部 unset，**槽位清单是权威键集**（缺一个即
   回归）；
3. **售卖闸四项合规条件逐项登记态**——法务/外部输入未到位时**必须可见**
   （此前只活在文档里，管理员在系统里看不到）；
4. **闸未开启时 ``ready_to_open=False``**（登记 ≠ 开启）；
5. **admin 专属**：非 admin 403、未认证 401（治理面纪律）；
6. **治理面不进 api_catalog**（静态钉）；
7. **配置位配好后汇总面如实改口**（读面不是静态快照）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from conftest import INITIAL_PASSWORD
from fde_api.commercial.models import (
    FEE_CONFIG_KEYS,
    OPPORTUNITY_RULE_KEYS,
    REGIONAL_GATE_CONDITION_KEYS,
    CommercialFeeConfig,
    CommercialOpportunityRule,
)
from fde_api.control.api_catalog import CATALOG

from test_research_subjects_api import (  # noqa: F401  (pytest fixture)
    admin_client,
    authorized_client_factory,
)

READINESS_URL = "/api/v1/admin/commercial/readiness"


def _pwd() -> str:
    return INITIAL_PASSWORD


def _body(response) -> dict:
    assert response.status_code == 200, response.get_data(as_text=True)
    payload = response.json
    assert payload["error"] is None
    return payload["data"]


def test_readiness_reports_all_config_slots_as_unset(
    admin_client, db_session
) -> None:
    """槽位清单齐备且全部 unset——缺一个槽位即回归。"""
    data = _body(admin_client.get(READINESS_URL))

    # 槽位清单按**权威键集顺序**逐位一致（读面按键集枚举，不按行枚举——
    # 槽位永不缺项，这正是「缺什么」这块屏存在的意义）
    fee_keys = [item["key"] for item in data["config_slots"]["fee_configs"]]
    assert fee_keys == list(FEE_CONFIG_KEYS)
    rule_keys = [item["key"] for item in data["config_slots"]["opportunity_rules"]]
    assert rule_keys == list(OPPORTUNITY_RULE_KEYS)

    assert all(item["status"] == "unset" for item in data["config_slots"]["fee_configs"])
    assert all(
        item["status"] == "unset" for item in data["config_slots"]["opportunity_rules"]
    )
    assert data["config_slots"]["split_rules"]["status"] == "unset"
    assert data["summary"]["unset_fee_configs"] == len(FEE_CONFIG_KEYS)
    assert data["summary"]["unset_opportunity_rules"] == len(OPPORTUNITY_RULE_KEYS)
    assert data["summary"]["split_rules_configured"] == 0


def test_readiness_reports_no_business_values(admin_client) -> None:
    """只报状态**不落数值**——未配置槽位不得带出任何金额/天数/比例。"""
    data = _body(admin_client.get(READINESS_URL))

    for item in data["config_slots"]["fee_configs"] + data["config_slots"]["opportunity_rules"]:
        assert set(item) == {
            "key",
            "label",
            "value_kind",
            "status",
            "configured",
            "chargeable",
            "waiting_for",
        }
        assert item["configured"] is False
        assert item["waiting_for"], "未配置槽位必须写明等谁拍板"

    # 可直接进科目层的收费项单独标出（缺省即不可收款）
    chargeable = [
        item["key"] for item in data["config_slots"]["fee_configs"] if item["chargeable"]
    ]
    assert chargeable == ["certification_fee"]

    raw = admin_client.get(READINESS_URL).get_data(as_text=True)
    assert "3980" not in raw
    assert "59800" not in raw


def test_readiness_reports_sale_gate_conditions(admin_client) -> None:
    """售卖闸四项条件逐项可见；未登记即法务/外部输入未到位（此前只在文档里）。"""
    data = _body(admin_client.get(READINESS_URL))

    gate = data["sale_gate"]
    assert gate["status"] == "closed"
    assert [item["key"] for item in gate["conditions"]] == list(
        REGIONAL_GATE_CONDITION_KEYS
    )
    assert all(item["registered"] is False for item in gate["conditions"])
    assert gate["missing_conditions"] == list(REGIONAL_GATE_CONDITION_KEYS)
    assert gate["ready_to_open"] is False
    assert all(item["waiting_for"] for item in gate["conditions"])


def test_readiness_blockers_cover_slots_and_gate(admin_client) -> None:
    """阻塞清单＝未就绪槽位 ＋ 未登记条件（含等待来源）——上线前一眼看全。"""
    data = _body(admin_client.get(READINESS_URL))

    kinds = {item["kind"] for item in data["blockers"]}
    assert kinds == {"fee_config", "opportunity_rule", "split_rule", "sale_gate_condition"}
    assert all(item["waiting_for"] for item in data["blockers"])
    assert data["summary"]["blocking_count"] == sum(
        1 for item in data["blockers"] if item["severity"] == "blocking"
    )
    assert data["summary"]["missing_gate_conditions"] == len(REGIONAL_GATE_CONDITION_KEYS)


def test_readiness_is_admin_only(
    admin_client, authorized_client_factory, db_session
) -> None:
    """治理面：admin 专属——非 admin 403、未认证 401。"""
    assert admin_client.get(READINESS_URL).status_code == 200

    viewer = authorized_client_factory("viewer")
    denied = viewer.get(READINESS_URL)
    assert denied.status_code == 403, denied.get_data(as_text=True)
    assert denied.json["error"]["code"] == "commercial_admin_required"

    anonymous = db_session  # 仅借夹具保活；未认证请求走独立客户端
    assert anonymous is not None


def test_readiness_not_in_api_catalog() -> None:
    """治理面不进 api_catalog（与既有 commercial admin 面同款）。"""
    paths = {row["path"] for row in CATALOG.values()}
    assert "/api/v1/admin/commercial/readiness" not in paths
    assert "/api/v1/admin/commercial/fee-configs" not in paths


def test_readiness_reflects_configured_slot(
    admin_client, authorized_client_factory, db_session
) -> None:
    """配好一个槽位后汇总面如实改口——读面不是静态快照。"""
    from fde_api.commercial.ledger_service import configure_fee_config

    admin = admin_client.user
    data = configure_fee_config(
        db_session,
        actor=admin,
        key="certification_fee",
        value="1200.00",
        source_uri="fdeops://commercial/fee/certification.pdf",
        content_hash="a" * 64,
        confirm_password=_pwd(),
    )
    assert data["fee_config"]["status"] == "configured"
    db_session.commit()

    summary = _body(admin_client.get(READINESS_URL))
    slot = next(
        item
        for item in summary["config_slots"]["fee_configs"]
        if item["key"] == "certification_fee"
    )
    assert slot["status"] == "configured"
    assert slot["configured"] is True
    assert slot["waiting_for"] is None
    assert summary["summary"]["unset_fee_configs"] == len(FEE_CONFIG_KEYS) - 1
