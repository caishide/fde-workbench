"""多客户 M4 批次 B：AI 预算按企业 org（任务书 §7-M4「按主体分别设额」）。

钉面：
- **org 汇总口径**：企业身份（``users.org_id`` 非空）的用量＝同 org 全员月度
  合计，额度值取 ``orgs.ai_monthly_token_budget``——单 user 口径下不超限、
  org 合计超限 ⇒ 必拦（防企业内多账号分摊绕过主体额度）。
- **回退语义**：org 未配置（NULL）⇒ 回落实例值＋按 user 汇总（＝现状零回归）。
- **平台身份**：``org_id=NULL`` 不受 org 额度约束（§11-8 语义不变）。
- **0 = 不限额**（沿 E7 心智）；**设施故障 fail-open 由调用方 try 承担**。
- **admin 双闸写面**：非 admin 403；无密码/错密码 403；留痕无密码；值闭集
  （``None``/≥0 整数，其余 400）。
- **静态钉**：全仓 ``budget_exceeded`` 调用点只许在 ``ai/auditing.py`` 内部
  （三腿调用点必须走 ``subject_budget_exceeded``，防新调用点绕过主体化）。
- **迁移往返**：``c3f7b1d9e5a2`` additive 加列（显式父版本惯例）。
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select

from conftest import INITIAL_PASSWORD
from fde_api.ai.auditing import subject_budget_exceeded
from fde_api.auth.models import User
from fde_api.commercial.org_budget_service import (
    OrgBudgetServiceError,
    get_org_ai_budget,
    set_org_ai_budget,
)
from fde_api.control.ai_server_client import execute_ai_prompt
from fde_api.control.dsh_runtime import DSHRuntimeError, dsh_runtime
from fde_api.orgs.models import Org
from fde_api.workbench.models import AICallAudit, OperationEvent
from multi_tenant_harness import make_enterprise_org, make_user
from test_ai_server_budget_audit import RecordingRuntime, provider_model


def _seed_usage(db_session, user_id: str, input_tokens: int, output_tokens: int) -> None:
    db_session.add(
        AICallAudit(
            request_id=f"m4b-{uuid4().hex[:12]}",
            actor_user_id=user_id,
            purpose="m4b-seed",
            model="seed-model",
            used_fallback=False,
            duration_ms=1,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            status="succeeded",
            error_code=None,
        )
    )
    db_session.commit()


def _set_org_budget(db_session, org: Org, budget: int | None) -> None:
    org.ai_monthly_token_budget = budget
    db_session.commit()


# ─────────────────────────── 判定层 ───────────────────────────


def test_enterprise_org_budget_uses_org_wide_sum(db_session, make_org_users):
    """同 org 两账号单独都不超、合计超 ⇒ 拦（org 汇总口径；实例值故意给大）。"""
    org, user_a, user_b = make_org_users
    _set_org_budget(db_session, org, 1000)
    _seed_usage(db_session, user_a.id, 600, 0)
    _seed_usage(db_session, user_b.id, 500, 0)
    # instance_budget=10**9：若误按实例值/单 user 判 ⇒ False，本断言即红。
    assert subject_budget_exceeded(db_session, user_a.id, instance_budget=10**9) is True
    assert subject_budget_exceeded(db_session, user_b.id, instance_budget=10**9) is True


def test_enterprise_org_unconfigured_falls_back_to_instance_per_user(db_session, make_org_users):
    """org 未配置（NULL）⇒ 回落实例值＋按 user 汇总（＝现状零回归）。"""
    org, user_a, user_b = make_org_users
    assert org.ai_monthly_token_budget is None
    _seed_usage(db_session, user_a.id, 600, 0)
    assert subject_budget_exceeded(db_session, user_a.id, instance_budget=500) is True
    # 回退态按 user：同 org 的 user_b 自身无用量 ⇒ 不拦。
    assert subject_budget_exceeded(db_session, user_b.id, instance_budget=500) is False


def test_platform_identity_uses_instance_budget_per_user(db_session):
    """平台身份（org_id=NULL）沿用实例值＋按 user（现状语义不变）。"""
    user = make_user(db_session, role="admin", org_id=None)
    other = make_user(db_session, role="admin", org_id=None)
    _seed_usage(db_session, user.id, 600, 0)
    assert subject_budget_exceeded(db_session, user.id, instance_budget=500) is True
    assert subject_budget_exceeded(db_session, other.id, instance_budget=500) is False


def test_org_budget_zero_means_unlimited(db_session, make_org_users):
    """org 配置 0 ＝ 不限额（沿 E7 心智）；用量再大也放行。"""
    org, user_a, _user_b = make_org_users
    _set_org_budget(db_session, org, 0)
    _seed_usage(db_session, user_a.id, 999_999, 0)
    assert subject_budget_exceeded(db_session, user_a.id, instance_budget=1) is False


# ─────────────────────────── DSH 主路径接线 ───────────────────────────


def test_dsh_main_path_blocks_enterprise_user_at_org_budget(app, db_session, monkeypatch, make_org_users):
    """接线钉：execute_ai_prompt 对企业身份按 org 额度拦（org 值 ≠ 实例值也生效）。"""
    org, user_a, _user_b = make_org_users
    _set_org_budget(db_session, org, 100)
    _seed_usage(db_session, user_a.id, 100, 0)
    monkeypatch.setattr(app.config["SETTINGS"], "ai_monthly_token_budget", 10**9)
    runtime = RecordingRuntime()
    with app.app_context():
        monkeypatch.setattr(dsh_runtime.current, "primary", runtime)
        with pytest.raises(DSHRuntimeError) as caught:
            execute_ai_prompt(
                user_id=user_a.id, prompt="你好", execution_id=f"m4b-{uuid4().hex[:8]}",
                model_override=provider_model(), use_tools=False, purpose="m4b_gate",
            )
    assert caught.value.code == "ai_budget_exceeded"
    assert runtime.executions == []  # 拦截在发起前：零 DSH 请求


# ─────────────────────────── 治理面（admin 双闸） ───────────────────────────


def test_org_budget_admin_face_double_gate(db_session, make_org_users):
    org, _user_a, _user_b = make_org_users
    admin = make_user(db_session, role="admin", org_id=None)
    viewer = make_user(db_session, role="viewer", org_id=None)

    with pytest.raises(OrgBudgetServiceError) as exc:
        get_org_ai_budget(db_session, actor=viewer, org_id=org.id)
    assert (exc.value.code, exc.value.status) == ("commercial_admin_required", 403)

    with pytest.raises(OrgBudgetServiceError) as exc:
        set_org_ai_budget(db_session, actor=viewer, org_id=org.id, budget=100, confirm_password="x")
    assert (exc.value.code, exc.value.status) == ("commercial_admin_required", 403)

    # admin 无密码 ⇒ 400；错密码 ⇒ 403（限流计数）。
    with pytest.raises(OrgBudgetServiceError) as exc:
        set_org_ai_budget(db_session, actor=admin, org_id=org.id, budget=100, confirm_password=None)
    assert (exc.value.code, exc.value.status) == ("invalid_request", 400)
    with pytest.raises(OrgBudgetServiceError) as exc:
        set_org_ai_budget(
            db_session, actor=admin, org_id=org.id, budget=100,
            confirm_password="definitely-wrong-password",
        )
    assert (exc.value.code, exc.value.status) == ("invalid_password", 403)

    db_session.add(_passworded_admin(admin))
    db_session.commit()
    data = set_org_ai_budget(
        db_session, actor=admin, org_id=org.id, budget=1200, confirm_password=INITIAL_PASSWORD
    )
    assert data["configured_budget"] == 1200 and data["fallback_to_instance"] is False
    # 留痕：事件在库且**无密码**。
    event = db_session.scalar(
        select(OperationEvent).where(OperationEvent.event_type == "org_ai_budget_set")
    )
    assert event is not None
    assert "password" not in str(event.changes).lower()
    # 读面回读。
    view = get_org_ai_budget(db_session, actor=admin, org_id=org.id)
    assert view["configured_budget"] == 1200
    assert view["fallback_to_instance"] is False


def test_org_budget_value_closure_and_reset(db_session, make_org_users):
    """值闭集：负数/浮点/字符串 ⇒ 400；None ⇒ 清回未配置（回退 True）。"""
    org, _user_a, _user_b = make_org_users
    admin = _passworded_admin(make_user(db_session, role="admin", org_id=None))
    db_session.add(admin)
    db_session.commit()
    for bad in (-1, 1.5, "100", True):
        with pytest.raises(OrgBudgetServiceError) as exc:
            set_org_ai_budget(
                db_session, actor=admin, org_id=org.id, budget=bad, confirm_password=INITIAL_PASSWORD
            )
        assert (exc.value.code, exc.value.status) == ("invalid_budget", 400)
    data = set_org_ai_budget(
        db_session, actor=admin, org_id=org.id, budget=None, confirm_password=INITIAL_PASSWORD
    )
    assert data["configured_budget"] is None and data["fallback_to_instance"] is True


def test_org_budget_unknown_org_404(db_session):
    admin = make_user(db_session, role="admin", org_id=None)
    with pytest.raises(OrgBudgetServiceError) as exc:
        get_org_ai_budget(db_session, actor=admin, org_id="no-such-org")
    assert (exc.value.code, exc.value.status) == ("org_not_found", 404)


# ─────────────────────────── 静态钉：调用点全部主体化 ───────────────────────────


def test_budget_gate_call_sites_all_subject_aware():
    """全仓 ``budget_exceeded(`` 调用点只许在 ``ai/auditing.py`` 内部；三腿
    （deepseek/DSH 主路径/kimi）必须走 ``subject_budget_exceeded``。"""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src" / "fde_api"
    offenders: list[str] = []
    for path in src.rglob("*.py"):
        rel = path.relative_to(src).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "budget_exceeded(" not in line or line.strip().startswith("#"):
                continue
            if rel == "ai/auditing.py":
                continue  # 权威定义所在（含 def 行与内部复用）
            # 只拦「直接调用」budget_exceeded；subject_budget_exceeded 放行。
            if re.search(r"(?<!subject_)budget_exceeded\(", line):
                offenders.append(f"{rel}:{lineno}: {line.strip()[:80]}")
    assert offenders == [], "预算门调用点绕过主体化单一权威点：\n" + "\n".join(offenders)


# ─────────────────────────── 迁移往返 ───────────────────────────


def test_org_ai_budget_migration_roundtrip(db_session):
    """``c3f7b1d9e5a2`` additive 加列（显式父版本惯例，不假设自己是链尖）。"""
    from sqlalchemy import inspect

    engine = db_session.get_bind()
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("orgs")}
    assert "ai_monthly_token_budget" in columns
    # 可空性：新旧行都合法（NULL=未配置）。
    nullable = next(c["nullable"] for c in inspector.get_columns("orgs") if c["name"] == "ai_monthly_token_budget")
    assert nullable is True


# ─────────────────────────── 夹具与常量 ───────────────────────────

def _passworded_admin(admin: User) -> User:
    from fde_api.auth.passwords import hash_password

    admin.password_hash = hash_password(INITIAL_PASSWORD)
    return admin


@pytest.fixture()
def make_org_users(db_session):
    """企业 org ＋ 同 org 两账号（企业身份）。"""
    org = make_enterprise_org(db_session)
    user_a = make_user(db_session, role="viewer", org_id=org.id)
    user_b = make_user(db_session, role="viewer", org_id=org.id)
    return org, user_a, user_b
