"""AI 原生化 N4（G-11）：改进提案受控发布通道——release_json 列＋status 闭集扩 published。

落地形（任务书 §Path 2b G-11：静态钉由「零写入」改为「只许经发布通道写」）：

- ``improvement_proposals`` 加 ``release_json``（JSON 可空，NULL=未发布）——
  发布/回滚的唯一状态承载列：``{released_at, released_by_user_id,
  released_version, release_note, rollback:{rolled_back_at, rolled_back_by_user_id,
  rollback_note}|None}``。**不建** ``published_at``/``apply_status`` 之类散列
  （静态钉禁列名清单原样保留——发布状态只许住 ``release_json`` 一列）。
- ``status`` CHECK 闭集 ``('draft','in_review','approved','rejected')`` 扩
  ``'published'``——发布/回滚把 status 在 ``approved ⇄ published`` 间移动
  （由 ``simulation/release_channel.py`` 单点执行）。
- **发布 ≠ 自动落地**（任务书边界「不自动上线提示词改动」）：本迁移与通道
  只承载**受控记账**——提示词/Skill/本体正文零触碰，正文改动仍由人工在治理
  面实施；提示词正文不入库（N6 纪律），``target_json`` 仍是文本指针。

幂等：加列一次＋drop/create CHECK 各一次。downgrade 对称可逆；若存量
``published`` 行非零，旧 CHECK 重建会被 PG 如实拒绝（fail-closed，不带错跑）。

Backup hint: 加列（NULL 无回填）＋约束级变更（drop+create 同名约束）；零数据改写。
"""
from alembic import op
import sqlalchemy as sa

revision = "b5d9e2f4a7c1"
down_revision = "f2a7c4e9b6d3"
branch_labels = None
depends_on = None

_CHECK_NAME = "ck_improvement_proposals_status"
_NEW_CHECK = "status IN ('draft', 'in_review', 'approved', 'rejected', 'published')"
_OLD_CHECK = "status IN ('draft', 'in_review', 'approved', 'rejected')"


def upgrade() -> None:
    op.add_column(
        "improvement_proposals",
        sa.Column("release_json", sa.JSON(), nullable=True),
    )
    op.drop_constraint(_CHECK_NAME, "improvement_proposals", type_="check")
    op.create_check_constraint(_CHECK_NAME, "improvement_proposals", _NEW_CHECK)


def downgrade() -> None:
    # published 行非零时旧 CHECK 重建失败（PG 建约束即校验存量）＝如实拒绝。
    op.drop_constraint(_CHECK_NAME, "improvement_proposals", type_="check")
    op.create_check_constraint(_CHECK_NAME, "improvement_proposals", _OLD_CHECK)
    op.drop_column("improvement_proposals", "release_json")
