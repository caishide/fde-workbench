"""多客户 M4 批次 C：队列 job 主体标签——outbox_events.subject_org ＋ background_jobs.org_id。

任务书 §7-M4「队列 job 携带主体标签用于计量」（盘点表维度 4 Q1）：

- ``outbox_events.subject_org`` ``VARCHAR(36) NULL``——入队调用点显式声明
  （``enqueue_outbox`` keyword-only 必填＝机械闸；平台面/未登记显式传
  ``None``＝平台级）。
- ``background_jobs.org_id`` ``VARCHAR(36) NULL``——dispatch 单点从事件复制；
  ``NULL``=平台级（与 ``org_id=NULL`` 平台身份语义同构）。**计量面非授权面**。
- ``ix_background_jobs_org_id``——计量读面按 org 分组统计。

**零数据回填**：存量行保持 ``NULL``＝平台级（存量平台自用语义如实），
不做任何按 target 推测的回填（推断不伪装成事实）。

Backup hint: additive columns + index only; downgrade drops all three
(round-trip safe, no data rewrite).
"""
import sqlalchemy as sa
from alembic import op

revision = "e9b4f7c2a8d3"
down_revision = "c3f7b1d9e5a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outbox_events",
        sa.Column("subject_org", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("org_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_background_jobs_org_id", "background_jobs", ["org_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_org_id", table_name="background_jobs")
    op.drop_column("background_jobs", "org_id")
    op.drop_column("outbox_events", "subject_org")
