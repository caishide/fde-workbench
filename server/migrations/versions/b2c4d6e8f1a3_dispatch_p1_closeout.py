"""dispatch P1 closeout: quote ownership + disputes table (goal-r6)

派单设计 §8.4 P1 收官（P1-6/P1-7 载体 + §8.1 第 8 张表）：
- P1-6 quotes.owner_user_id（报价归属人，nullable FK users SET NULL + 索引；
  存量不回填=「无归属（平台侧台账报价）」语义）。
- disputes（§6.6 四层仲裁 + §7.5 T+30 对账草稿）：layer/status Check、
  L0 对账单 source_uri 指针、snapshot_hash 锚定当时版本、48h SLA 字段、
  处罚类动作 100% 人工（自动侧只产 L0 草稿）。

Backup hint: additive column + pure CREATE TABLE, no data written.
Downgrade drops the table and the column.
"""
from alembic import op
import sqlalchemy as sa


revision = "b2c4d6e8f1a3"
down_revision = "a7f3c1e9d5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("quotes", sa.Column("owner_user_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_quotes_owner_user", "quotes", "users", ["owner_user_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_quotes_owner", "quotes", ["owner_user_id"])

    op.create_table(
        "disputes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("settlement_key", sa.String(length=20), nullable=True),
        sa.Column("layer", sa.String(length=2), nullable=False, server_default="L0"),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="draft"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text(), nullable=False),
        sa.Column("l0_report_source_uri", sa.String(length=500), nullable=True),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("opened_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("handled_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["package_id"], ["delivery_packages.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["opened_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["handled_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("layer IN ('L0', 'L1', 'L2', 'L3')", name="ck_disputes_layer"),
        sa.CheckConstraint(
            "status IN ('draft', 'open', 'reviewing', 'resolved', 'closed')",
            name="ck_disputes_status",
        ),
    )
    op.create_index("ix_disputes_package", "disputes", ["package_id"])
    op.create_index("ix_disputes_status", "disputes", ["status"])


def downgrade() -> None:
    op.drop_index("ix_disputes_status", table_name="disputes")
    op.drop_index("ix_disputes_package", table_name="disputes")
    op.drop_table("disputes")
    op.drop_index("ix_quotes_owner", table_name="quotes")
    op.drop_constraint("fk_quotes_owner_user", "quotes", type_="foreignkey")
    op.drop_column("quotes", "owner_user_id")
