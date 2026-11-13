"""agent_runs 发起时刻白名单快照列 frozen_tools（goal-sprint r2，2026-11-13）。

链位：接 N4 发布通道迁移 b5d9e2f4a7c1 之后（单头 73→74）。

吸收依据：goal-crv r5 QR-089（`agents/service.py:1693` claim 载荷
allowed_tools 实时读 registry——「允许名单随 run 冻结」（``_execute_run``
docstring 既有承诺）契约失守：发起后 registry 名单变更会经领取载荷放大
进宿主执行面）。修复＝快照列：``start_run`` 三重交集（声明 ∖ 平台 deny ∖
能力不可行）在 run 行落冻结副本，宿主领取载荷读快照而非 registry 实时值。

additive-only：单列可空无默认——旧行读路径零变化（NULL ⇒ 领取面回落
registry 读，兼容既有行；新行一律落快照）。downgrade 逆序还原。

Backup hint: additive only; downgrade drops the column.
"""
import sqlalchemy as sa
from alembic import op

revision = "c8e2a6f0b9d4"
down_revision = "b5d9e2f4a7c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("frozen_tools", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "frozen_tools")
