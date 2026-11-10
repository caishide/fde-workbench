"""F 线 T2：五席位分账「上线前初始基线」回归（ADR-011 §3，规则文件 §10）。

- 迁移种入 ``dispatch_rule_versions`` 一行 ``version_no=100``（保留段）/
  ``status='active'``/``published_at == effective_at``（真实迁移执行时刻）/
  ``published_by_user_id IS NULL``（平台侧行为不伪装成人工动作）。
- 快照形状：``five_seat`` 块（平台 30% ＋ 池内 30/50/10/10，两把尺各自成
  键）＋Stage B 权重/等级映射分（与常量同值）；**不含**旧四席位
  ``seat_shares``（35/5/20/40 待迁移旧口径不进新层）。
- 三方逐位一致闸：规则文件 JSON 块 ↔ ``dispatch/baseline.py`` 常量 ↔
  迁移内联字面量。
- 豁免边界：初始基线豁免仅此一行——基线在场时 ``create_rule_version``
  的 30 天公示闸照常咬合（零公示第二版 422），激活后基线正常退役。
- 旧路径不受扰：``seat_shares_for`` 对缺键回退 ``DISPATCH_CONSTANTS``。
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from alembic import command
import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.dispatch import baseline as baseline_mod
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import DispatchRuleVersion
from fde_api.dispatch.rules import (
    activate_due_versions,
    active_rule_version,
    create_rule_version,
    default_rule_snapshot,
)
from fde_api.dispatch.settlements import seat_shares_for
from fde_api.system_configuration import DISPATCH_CONSTANTS
from fde_api.workbench.models import OperationEvent

from conftest import INITIAL_PASSWORD, SERVER_ROOT
from test_dispatch_p1_r5 import _onsite_package

RULES_FILE = (
    SERVER_ROOT.parent / "docs" / "commercialization" / "rules" / "five-seat-split-rules.md"
)


def _user(username: str) -> User:
    return User(
        username=f"{username}.{uuid4().hex[:8]}",
        display_name=username,
        role="admin",
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )


def _load_migration_module():
    """按路径加载迁移模块（文件名含连字符，常规 import 不可达）。"""
    path = (
        SERVER_ROOT
        / "migrations"
        / "versions"
        / "c8d2f6a4e9b1_dispatch_five_seat_baseline.py"
    )
    spec = importlib.util.spec_from_file_location("t2_baseline_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rules_file_block() -> dict:
    """取规则文件 five-seat-split-rules 机器可读 JSON 块（剥 ```json 围栏）。"""
    text = RULES_FILE.read_text(encoding="utf-8")
    marker = "<!-- five-seat-split-rules:begin -->"
    end = "<!-- five-seat-split-rules:end -->"
    block = text.split(marker, 1)[1].split(end, 1)[0].strip()
    if block.startswith("```"):
        block = block.split("\n", 1)[1]  # 去 ```json 行
        block = block.rsplit("```", 1)[0]  # 去收尾围栏
    return json.loads(block.strip())


def _baseline_row(db_session) -> DispatchRuleVersion:
    return db_session.scalar(
        select(DispatchRuleVersion).where(
            DispatchRuleVersion.version_no
            == baseline_mod.FIVE_SEAT_BASELINE_VERSION_NO
        )
    )


# ---------------------------------------------------------------------------
# 三方逐位一致闸：规则文件 ↔ 常量 ↔ 迁移内联字面量
# ---------------------------------------------------------------------------


def test_three_way_machine_gate_rules_file_constants_migration():
    """规则文件 JSON 块 ↔ baseline 常量 ↔ 迁移内联字面量三方逐位一致。"""
    block = _rules_file_block()["rule_versioning"]["initial_baseline"]
    migration = _load_migration_module()

    assert block["version_no"] == baseline_mod.FIVE_SEAT_BASELINE_VERSION_NO
    assert block["version_no"] == migration._BASELINE_VERSION_NO
    assert block["status_seeded"] == "active"
    assert block["published_at_equals_effective_at"] is True
    assert block["timestamps"] == "real_execution_time_no_backfill"
    assert block["seeded_by"] == "migration"
    assert block["legacy_four_seat_semantics_forbidden"] is True
    assert block["audit_event"] == "initial_baseline"
    assert (
        block["snapshot_seat_shares_semantics"]
        == baseline_mod.FIVE_SEAT_BASELINE_SNAPSHOT["five_seat"]
        == migration._BASELINE_SNAPSHOT["five_seat"]
    )
    assert (
        baseline_mod.FIVE_SEAT_BASELINE_SNAPSHOT == migration._BASELINE_SNAPSHOT
    )


def test_baseline_snapshot_stage_b_matches_constants():
    """基线随行的 Stage B 权重/等级映射分与 DISPATCH_CONSTANTS 同值
    （撮合按快照打分不落空权重），且不含旧四席位语义。"""
    snapshot = baseline_mod.FIVE_SEAT_BASELINE_SNAPSHOT
    assert snapshot["stage_b_weights"] == DISPATCH_CONSTANTS["stage_b_weights"]
    assert snapshot["level_score_map"] == DISPATCH_CONSTANTS["level_score_map"]
    assert "seat_shares" not in snapshot
    assert "cold_start_seat_shares" not in snapshot
    assert "cold_start_first_orders" not in snapshot


# ---------------------------------------------------------------------------
# 迁移种入行：形状与豁免边界
# ---------------------------------------------------------------------------


def test_baseline_row_seeded_active(db_session):
    """基线行在场：v100/active/双时刻相等且非空/published_by NULL/快照逐位。"""
    row = _baseline_row(db_session)
    assert row is not None
    assert row.status == "active"
    assert row.published_at is not None
    assert row.effective_at == row.published_at
    assert row.published_by_user_id is None
    assert row.rule_snapshot == baseline_mod.FIVE_SEAT_BASELINE_SNAPSHOT


def test_baseline_snapshot_free_of_legacy_four_seat_semantics(db_session):
    """35/5/20/40 待迁移旧口径不得出现在基线快照任何一层。"""
    row = _baseline_row(db_session)
    serialized = json.dumps(row.rule_snapshot)
    assert '"seat_shares"' not in serialized
    assert "35" not in serialized.split("five_seat")[0]


def test_legacy_seat_shares_fallback_unchanged(db_session):
    """旧结算路径契约：基线在场但快照缺 seat_shares 键 ⇒ 回退常量逐位不变；
    冷启动档已废止（ADR-011 §3.9）——只有基准一路，无第二口径。"""
    admin, package = _onsite_package(db_session)
    shares = seat_shares_for(db_session, package)
    assert shares == {
        key: int(value) for key, value in DISPATCH_CONSTANTS["seat_shares"].items()
    }
    assert active_rule_version(db_session) is not None


# ---------------------------------------------------------------------------
# 豁免边界：基线在场，公示闸照常咬合
# ---------------------------------------------------------------------------


def test_second_version_zero_notice_still_422(db_session):
    """T2 反例：基线存在后再发第二版且零公示 ⇒ 422 notice_window_required。

    闸序证明：公示窗校验先于版本号冲突校验——基线在场不改变 422 的错误码。"""
    admin = _user("t2.baseline.admin")
    db_session.add(admin)
    db_session.flush()
    now = datetime.now(timezone.utc)
    with pytest.raises(DispatchServiceError) as excinfo:
        create_rule_version(
            db_session,
            actor=admin,
            version_no=2,
            rule_snapshot=default_rule_snapshot(),
            published_at=now,
            effective_at=now + timedelta(days=29),
        )
    assert excinfo.value.code == "notice_window_required"
    assert excinfo.value.status == 422


def test_second_version_with_notice_publishes_and_activate_retires_baseline(db_session):
    """公示窗合规的第二版照常发布；到点激活后基线退役、同刻至多一个 active。"""
    admin = _user("t2.baseline.admin2")
    db_session.add(admin)
    db_session.flush()
    now = datetime.now(timezone.utc)
    create_rule_version(
        db_session,
        actor=admin,
        version_no=2,
        rule_snapshot=default_rule_snapshot(),
        published_at=now - timedelta(days=40),
        effective_at=now - timedelta(days=10),
    )
    db_session.flush()
    assert activate_due_versions(db_session, now=now) == 1
    db_session.refresh(_baseline_row(db_session))
    assert _baseline_row(db_session).status == "retired"
    current = active_rule_version(db_session)
    assert current is not None and current.version_no == 2


# ---------------------------------------------------------------------------
# initial_baseline 痕迹：有 actor 落事件 / 无 actor 诚实跳过 / 幂等
# ---------------------------------------------------------------------------


def test_baseline_event_recorded_with_actor_and_idempotent(db_session):
    """有 user 时事件落库（actor=最早 user），重放不产生第二份。"""
    first = _user("t2.event.first")
    db_session.add(first)
    db_session.flush()
    migration = _load_migration_module()
    row = _baseline_row(db_session)
    migration._record_baseline_event(db_session.connection(), row.id)
    db_session.flush()
    events = db_session.scalars(
        select(OperationEvent).where(
            OperationEvent.event_type == "initial_baseline",
            OperationEvent.target_id == row.id,
        )
    ).all()
    assert len(events) == 1
    assert events[0].actor_user_id == first.id
    assert events[0].changes["seeded_by"] == "migration"
    assert events[0].changes["version_no"] == baseline_mod.FIVE_SEAT_BASELINE_VERSION_NO

    migration._record_baseline_event(db_session.connection(), row.id)
    db_session.flush()
    again = db_session.scalars(
        select(OperationEvent).where(
            OperationEvent.event_type == "initial_baseline",
            OperationEvent.target_id == row.id,
        )
    ).all()
    assert len(again) == 1  # 幂等：不产生第二份痕迹


def test_baseline_migration_roundtrip(alembic_config, engine):
    """T2 迁移往返：downgrade 一步即删行与痕迹、upgrade 回 head 即重种
    （测试库迁移时刻无 user ⇒ 事件诚实缺席、行诚实在场）。"""
    from sqlalchemy import text

    command.downgrade(alembic_config, "b7e4c1a9f3d5")
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT count(*) FROM dispatch_rule_versions"
                " WHERE rule_snapshot->>'snapshot_kind' = 'initial_baseline'"
            )
        ).scalar()
        events = conn.execute(
            text(
                "SELECT count(*) FROM operation_events"
                " WHERE event_type = 'initial_baseline'"
            )
        ).scalar()
    assert rows == 0
    assert events == 0

    command.upgrade(alembic_config, "head")
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT version_no, status, published_at, effective_at,"
                " published_by_user_id FROM dispatch_rule_versions"
                " WHERE rule_snapshot->>'snapshot_kind' = 'initial_baseline'"
            )
        ).first()
        events = conn.execute(
            text(
                "SELECT count(*) FROM operation_events"
                " WHERE event_type = 'initial_baseline'"
            )
        ).scalar()
    assert row is not None
    assert row[0] == 100 and row[1] == "active"
    assert row[2] is not None and row[2] == row[3]
    assert row[4] is None  # 测试库迁移时刻零 user：痕迹诚实跳过
    assert events == 0
