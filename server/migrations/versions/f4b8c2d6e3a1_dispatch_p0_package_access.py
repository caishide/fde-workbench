"""dispatch P0 round-3: package_access + delivery seat amount (goal-r3)

派单设计 §8.3（簇②收尾，P0-1/P0-2）：
- P0-2 package_access（§9.2 跨主体只读授权「第三语义」，不复用 Project.members）：
  Unique(package_id, user_id, role) + role Check(lead/seller/delivery/audit) + revoked_at。
- P0-1 补列 delivery_packages.delivery_seat_amount（§7.1/§9.2 显示义务）：
  发布时按当时报价物化冻结的交付方席位 40% 金额——交付包 API 禁 join
  quotes（§9.2 纪律①），金额只能来自本列。

Backup hint: pure CREATE TABLE + one nullable column, no data written.
Downgrade drops both (reverse order).
"""
from alembic import op
import sqlalchemy as sa


revision = "f4b8c2d6e3a1"
down_revision = "e3a7c5d9f2b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "package_access",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("granted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["granted_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "package_id", "user_id", "role", name="uq_package_access_package_user_role"
        ),
        sa.CheckConstraint(
            "role IN ('lead', 'seller', 'delivery', 'audit')",
            name="ck_package_access_role",
        ),
    )
    op.create_index("ix_package_access_user", "package_access", ["user_id"])
    op.add_column(
        "delivery_packages",
        sa.Column("delivery_seat_amount", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("delivery_packages", "delivery_seat_amount")
    op.drop_index("ix_package_access_user", table_name="package_access")
    op.drop_table("package_access")
