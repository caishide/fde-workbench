"""F 线 T2：五席位分账上线前初始基线版本（dispatch_rule_versions 种入）。

Revision ID: c8d2f6a4e9b1
Revises: b7e4c1a9f3d5
Create Date: 2026-11-11

ADR-011 §3（2026-11-10 16:57 拍板「不用公示，本项目还没上线呢」）：无存量
用户、无存量派单规则受影响 ⇒「初始基线」不是「规则变更」，§6.2 公示窗
不适用；**豁免边界＝仅此一行**——上线后任何改值仍必须走 create_rule_version
+ 30 天公示（规则文件 five-seat-split-rules.md §10，豁免分支一个都没有）。

种入内容：
- ``dispatch_rule_versions`` 一行 ``version_no=100``（保留段，1–99 留给
  上线后人工版本序列）、``status='active'``、``published_at = effective_at
  = 真实迁移执行时刻``（不倒填）、``published_by_user_id = NULL``（平台侧
  行为不伪装成人工动作）。
- 快照形状＝fde_api/dispatch/baseline.py 常量的内联字面量（逐位一致由
  test_dispatch_five_seat_baseline 三方闸钉死；**内联冻结**——常量日后
  变更不会追溯改写已应用库的基线字节，全新库与存量库种子逐位一致）：
  ``five_seat`` 块（平台 30% ＋ 池内 30/50/10/10，两把尺各自成键）＋
  Stage B 权重/等级映射分（与 DISPATCH_CONSTANTS 同值，基线 active 后
  撮合按快照打分）。**不含**旧四席位 ``seat_shares``（35/5/20/40 待迁移
  旧口径不进新层）：``seat_shares_for`` 对缺键回退常量，旧路径行为逐位
  不变。
- ``operation_events`` 留 ``initial_baseline`` 痕迹：actor 取库里最早
  user（迁移时刻无 user 则**诚实地跳过事件**——绝不为凑痕迹伪造 actor，
  全新库首个 alembic upgrade 时零 user 也能干净通过）；幂等：行/事件
  任一在场即短路与，重放不产生第二份。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "c8d2f6a4e9b1"
down_revision = "a9c5e2d7b3f1"  # 十四度插队改挂：夜审 r5 a9c5e2d7b3f1 之后，保单头
branch_labels = None
depends_on = None

# 内联冻结字面量（与 fde_api.dispatch.baseline.FIVE_SEAT_BASELINE_SNAPSHOT
# 逐位一致——三方闸 test_dispatch_five_seat_baseline 断言等值，改任一侧必红）。
_BASELINE_VERSION_NO = 100
_BASELINE_SNAPSHOT = {
    "snapshot_kind": "initial_baseline",
    "five_seat": {
        "platform_share_percent": 30,
        "pool_shares": {"lead": 30, "delivery": 50, "county": 10, "province": 10},
    },
    "stage_b_weights": {"level": 40, "industry": 30, "sla": 20, "geo_remote": 10},
    "level_score_map": {"L1": 40, "L2": 60, "L3": 80, "L4": 100},
}

_INSERT_ROW = sa.text(
    """
    INSERT INTO dispatch_rule_versions
        (id, version_no, status, rule_snapshot, published_at, effective_at,
         created_at, updated_at)
    VALUES (:id, :version_no, 'active', CAST(:snapshot AS json),
            :moment, :moment, :moment, :moment)
    ON CONFLICT (version_no) DO NOTHING
    """
)

_SELECT_ROW_ID = sa.text(
    "SELECT id FROM dispatch_rule_versions WHERE version_no = :version_no"
)

_SELECT_ACTOR = sa.text("SELECT id FROM users ORDER BY created_at ASC LIMIT 1")

_EVENT_EXISTS = sa.text(
    "SELECT 1 FROM operation_events"
    " WHERE event_type = 'initial_baseline' AND target_id = :target_id LIMIT 1"
)

_INSERT_EVENT = sa.text(
    """
    INSERT INTO operation_events
        (id, actor_user_id, project_id, target_type, target_id, event_type,
         occurred_at, changes)
    VALUES (:id, :actor, NULL, 'dispatch_rule_version', :target_id,
            'initial_baseline', :moment, CAST(:changes AS json))
    """
)


def _ensure_baseline_row(bind: sa.Connection) -> str | None:
    """种入基线行（幂等）：返回行 id；已在场（重放/并发）返回 None。"""
    existing = bind.execute(
        _SELECT_ROW_ID, {"version_no": _BASELINE_VERSION_NO}
    ).scalar()
    if existing is not None:
        return None
    moment = datetime.now(timezone.utc)  # 真实迁移执行时刻（不倒填）
    row_id = str(uuid.uuid4())
    bind.execute(
        _INSERT_ROW,
        {
            "id": row_id,
            "version_no": _BASELINE_VERSION_NO,
            "snapshot": json.dumps(_BASELINE_SNAPSHOT),
            "moment": moment,
        },
    )
    return row_id


def _record_baseline_event(bind: sa.Connection, row_id: str | None) -> None:
    """initial_baseline 痕迹：actor 取最早 user；无 user 诚实跳过。

    全新库首个 alembic upgrade 时 ``users`` 为空（种子是应用侧步骤），
    ``operation_events.actor_user_id`` NOT NULL FK 不允许伪造 actor——
    跳过即如实；存量库（活体部署）必有 user，痕迹必落。
    """
    if row_id is None:
        return
    if bind.execute(_EVENT_EXISTS, {"target_id": row_id}).scalar() is not None:
        return
    actor = bind.execute(_SELECT_ACTOR).scalar()
    if actor is None:
        return
    bind.execute(
        _INSERT_EVENT,
        {
            "id": str(uuid.uuid4()),
            "actor": actor,
            "target_id": row_id,
            "moment": datetime.now(timezone.utc),
            "changes": json.dumps(
                {
                    "version_no": _BASELINE_VERSION_NO,
                    "snapshot_kind": "initial_baseline",
                    "seeded_by": "migration",
                    "basis": "ADR-011 §3 / F 线 T2（上线前初始基线，豁免仅此一行）",
                }
            ),
        },
    )


def upgrade() -> None:
    _record_baseline_event(op.get_bind(), _ensure_baseline_row(op.get_bind()))


def downgrade() -> None:
    """删痕迹与种子行（按 snapshot_kind + 保留段版本号双条件定位）。"""
    bind = op.get_bind()
    row_ids = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT id FROM dispatch_rule_versions"
                " WHERE version_no = :version_no"
                " AND rule_snapshot->>'snapshot_kind' = 'initial_baseline'"
            ),
            {"version_no": _BASELINE_VERSION_NO},
        ).all()
    ]
    if not row_ids:
        return
    bind.execute(
        sa.text(
            "DELETE FROM operation_events"
            " WHERE event_type = 'initial_baseline'"
            " AND target_id = ANY(:row_ids)"
        ),
        {"row_ids": row_ids},
    )
    bind.execute(
        sa.text(
            "DELETE FROM dispatch_rule_versions"
            " WHERE id = ANY(:row_ids)"
            " AND rule_snapshot->>'snapshot_kind' = 'initial_baseline'"
        ),
        {"row_ids": row_ids},
    )
