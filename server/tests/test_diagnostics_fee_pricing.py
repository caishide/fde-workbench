"""获客诊断 T-16 价格轮：转化费比例只在配置面（机械钉）。

蔡工 2026-11-12 拍板④：转化费＝比例制——A 渠道报备缺省 20%、B 认领转化
缺省 10%（C 平台留存零转化费，不走比例）。这一组用例守的是：

- **比例数值只在配置面**（``Settings.diagnostics_fee_ratio_tier_a/b``）：
  出厂默认值、env 覆写、越界 fail-fast（**「填 20 想表达 20%」的经典笔误
  必须启动即炸**——商业口径错配宁可起不来，不可带错跑）；
- **口径结构值换值**：``fee_basis`` 闭集 = ``('none', 'ratio_applied')``，
  退役值 ``pending_pricing`` **不得复活**；DB CHECK 同步换值（迁移静态钉）；
- **_fee_basis 映射**：A/B → ``ratio_applied``、C → ``none``；
- **投影不携带比例数字**：认领单投影键闭集钉死——任何新增键必须显式过本钉
  （dispatch 域「报价/收款明细永不出现在响应里」同款纪律）；
- **台账行零变化**：T-16 只动口径结构值，台账十二列序与内容一字不动。
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from fde_api.config import Settings
from fde_api.diagnostics import claim_service
from fde_api.diagnostics.claim_service import LEDGER_COLUMNS, serialize_claim
from fde_api.diagnostics.models import FEE_BASES, LeadDiagnosticClaim

BASE_SETTINGS = {
    "_env_file": None,
    "database_url": "sqlite://",
    "redis_url": "redis://127.0.0.1:6379/15",
    "jwt_secret": "test-secret-with-at-least-thirty-two-characters",
}

_SERVER_ROOT = Path(__file__).resolve().parents[1]


# ── 配置面：出厂默认值 ────────────────────────────────────────────────


def test_shipped_fee_ratio_defaults_are_20_and_10_percent():
    """出厂默认＝A 20%／B 10%（拍板④缺省值；漂移即红）。"""
    settings = Settings(env="test", **BASE_SETTINGS)
    assert settings.diagnostics_fee_ratio_tier_a == Decimal("0.20")
    assert settings.diagnostics_fee_ratio_tier_b == Decimal("0.10")


def test_fee_ratio_is_configurable_via_settings_kwargs():
    """配置面可调：_kwargs 覆写生效（部署侧经 env 自动映射同构）。"""
    settings = Settings(
        env="test",
        diagnostics_fee_ratio_tier_a="0.30",
        diagnostics_fee_ratio_tier_b="0.05",
        **BASE_SETTINGS,
    )
    assert settings.diagnostics_fee_ratio_tier_a == Decimal("0.30")
    assert settings.diagnostics_fee_ratio_tier_b == Decimal("0.05")


@pytest.mark.parametrize("bad", ["20", "1.5", "-0.1", "2"])
def test_out_of_range_fee_ratio_fails_fast(bad):
    """越界启动即炸——含「填 20 想表达 20%」的经典笔误。"""
    with pytest.raises(ValidationError):
        Settings(env="test", diagnostics_fee_ratio_tier_a=bad, **BASE_SETTINGS)


@pytest.mark.parametrize("edge", ["0", "0.0", "1", "1.0"])
def test_fee_ratio_boundaries_are_inclusive(edge):
    """0 与 1 是合法端点（ge=0 le=1 含端点；0%＝该档暂免转化费）。"""
    settings = Settings(env="test", diagnostics_fee_ratio_tier_b=edge, **BASE_SETTINGS)
    assert settings.diagnostics_fee_ratio_tier_b == Decimal(edge)


# ── 口径结构值闭集 ────────────────────────────────────────────────────


def test_fee_bases_closed_set_after_t16():
    """闭集 = ('none', 'ratio_applied')；退役值 pending_pricing 不得复活。"""
    assert FEE_BASES == ("none", "ratio_applied")
    assert "pending_pricing" not in FEE_BASES


def test_migration_swaps_check_constraint_closed_set():
    """DB CHECK 迁移静态钉：upgrade 换 ratio_applied、downgrade 对称换回。"""
    path = _SERVER_ROOT / "migrations" / "versions" / "f2a7c4e9b6d3_diagnostic_fee_ratio_basis.py"
    source = path.read_text(encoding="utf-8")
    assert "fee_basis IN ('none', 'ratio_applied')" in source
    assert "fee_basis IN ('none', 'pending_pricing')" in source  # downgrade 对称
    assert 'down_revision = "a3e8c2f6b9d4"' in source  # 挂 T-15 之后保单头


# ── _fee_basis 映射 ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("tier", "expected"),
    [("A", "ratio_applied"), ("B", "ratio_applied"), ("C", "none")],
)
def test_fee_basis_maps_tiers(tier, expected):
    """A/B 按平台配置比例计；C 档零转化费（映射闭集）。"""
    assert claim_service._fee_basis(tier) == expected


def test_fee_basis_maps_unknown_tier_to_ratio_applied():
    """未知档位按 A/B 同腿处理（fail-safe 结构值，档位闭集由归因面守）。"""
    assert claim_service._fee_basis("X") == "ratio_applied"


# ── 投影不携带比例数字 ────────────────────────────────────────────────


def test_claim_projection_key_set_is_closed_and_ratio_free():
    """认领单投影键**闭集钉死**且零比例/金额语义键。

    任何未来新增键都必须显式过本钉——防止有人顺手把比例数字塞进响应
    （比例只在配置面；dispatch 域「报价/收款明细不出响应」同款纪律）。
    """
    row = LeadDiagnosticClaim()
    keys = set(serialize_claim(row))
    assert keys == {
        "id",
        "session_id",
        "claimant_user_id",
        "claimant_kind",
        "region_name",
        "status",
        "attribution_tier",
        "fee_basis",
        "self_claim",
        "self_claim_signals",
        "tier_override",
        "ledger_line_no",
        "ledger_row",
        "ledger_written_at",
        "decided_by_user_id",
        "decided_at",
        "decision_note",
        "note",
        "created_at",
    }
    banned = ("rate", "ratio", "percent", "commission", "amount", "fee_rate")
    assert not any(word in key for key in keys for word in banned), sorted(keys)


def test_fee_basis_value_shape_never_carries_a_number():
    """``fee_basis`` 是**结构值**不是数字：合法取值都不含比例字面。"""
    assert all(value in FEE_BASES for value in ("none", "ratio_applied"))
    assert all(not any(ch.isdigit() for ch in value) for value in FEE_BASES)


# ── 台账行零变化 ──────────────────────────────────────────────────────


def test_ledger_columns_untouched_by_t16():
    """T-16 只动口径结构值——台账十二列序与内容一字不动。"""
    assert LEDGER_COLUMNS == (
        "线索号",
        "#",
        "来源",
        "行业",
        "联系人角色",
        "痛点一句话",
        "资格五问得分",
        "下一步动作+日期",
        "①状态",
        "②来源人/报备到期日",
        "③回访触发日",
        "④资料索引",
    )
