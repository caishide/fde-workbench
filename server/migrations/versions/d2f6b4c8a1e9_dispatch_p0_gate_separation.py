"""dispatch P0 round-1: gate acceptance separation + dispatch skeleton tables

goal-r1（派单设计 §8.3）：
- P0-5 门禁验收分离（§9.4，§8.8 开池四道闸之二）：gates 加
  submitted_by_user_id / decided_by_user_id / is_delivery_party 三列，
  decide_gate 校验「拍板人 ≠ 执行人」（403，代码强制不可绕过）。
- P0-6 events 白名单前置：新建 delivery_packages / dispatch_offers 两张
  §8.2 DDL 级骨架表（约束齐备，服务逻辑随 P0-1/P1-1/P1-2 后续轮落位），
  projects/events.py 注册 delivery_package / dispatch_offer 两类目标。

席位口径：delivery_packages 四席位 = 执行席位 seat_lead/delivery/consult/qa
（§2.4），与 delivery_settlements 的商务四席位（§7.2）不同名不同义。

Backup hint: additive columns (server_default 兜底存量行) + pure CREATE TABLE,
no data written. Downgrade drops both tables and the three gate columns.
"""
from alembic import op
import sqlalchemy as sa


revision = "d2f6b4c8a1e9"
down_revision = "a9c3f1d8e2b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- P0-5：gates 三列 ----
    op.add_column(
        "gates",
        sa.Column("submitted_by_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "gates",
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "gates",
        sa.Column(
            "is_delivery_party",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_foreign_key(
        "fk_gates_submitted_by_user",
        "gates",
        "users",
        ["submitted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_gates_decided_by_user",
        "gates",
        "users",
        ["decided_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ---- P0-6：delivery_packages（§2.2 新增字段 + §8.2 DDL 级约束）----
    op.create_table(
        "delivery_packages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("solution_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("package_code", sa.String(length=20), nullable=False),
        sa.Column("quote_id", sa.String(length=36), nullable=True),
        sa.Column("sow_type", sa.String(length=1), nullable=True),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "dispatch_mode", sa.String(length=10), nullable=False, server_default="assign"
        ),
        sa.Column(
            "dispatch_status", sa.String(length=12), nullable=False, server_default="draft"
        ),
        sa.Column(
            "dispatch_round", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column(
            "allow_competitive_claim",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "response_window_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("24"),
        ),
        sa.Column(
            "redispatch_radius_km",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("25"),
        ),
        sa.Column("required_level", sa.String(length=2), nullable=True),
        sa.Column("required_modules", sa.JSON(), nullable=True),
        sa.Column("required_industry", sa.String(length=64), nullable=True),
        sa.Column(
            "onsite_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("onsite_visits", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_user_id", sa.String(length=36), nullable=True),
        sa.Column("seat_lead", sa.String(length=36), nullable=True),
        sa.Column("seat_delivery", sa.String(length=36), nullable=True),
        sa.Column("seat_consult", sa.String(length=36), nullable=True),
        sa.Column("seat_qa", sa.String(length=36), nullable=True),
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
            ["solution_id"], ["project_solutions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["quote_id"], ["quotes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["accepted_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["seat_lead"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seat_delivery"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seat_consult"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["seat_qa"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_code", name="uq_delivery_packages_package_code"),
        sa.UniqueConstraint(
            "project_id", "dispatch_round", name="uq_delivery_packages_project_round"
        ),
        sa.CheckConstraint(
            "dispatch_mode IN ('assign', 'claim')",
            name="ck_delivery_packages_dispatch_mode",
        ),
        sa.CheckConstraint(
            "dispatch_status IN ('draft', 'published', 'offered', 'assigned', "
            "'accepted', 'rejected', 'expired', 'withdrawn')",
            name="ck_delivery_packages_dispatch_status",
        ),
        # §4.7 扩圈序列 25→50→100→全城；0 = 全城哨兵值
        sa.CheckConstraint(
            "redispatch_radius_km IN (25, 50, 100, 0)",
            name="ck_delivery_packages_redispatch_radius",
        ),
        sa.CheckConstraint(
            "sow_type IS NULL OR sow_type IN ('a', 'b', 'c', 'd')",
            name="ck_delivery_packages_sow_type",
        ),
        sa.CheckConstraint(
            "required_level IS NULL OR required_level IN ('L1', 'L2', 'L3', 'L4')",
            name="ck_delivery_packages_required_level",
        ),
    )
    op.create_index(
        "ix_delivery_packages_status", "delivery_packages", ["dispatch_status"]
    )

    # ---- P0-6：dispatch_offers（§6 留痕 + §8.2 约束 + 乐观锁 version）----
    op.create_table(
        "dispatch_offers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column(
            "dispatch_round", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
        sa.Column("candidate_user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status", sa.String(length=12), nullable=False, server_default="offered"
        ),
        sa.Column("match_breakdown", sa.JSON(), nullable=True),
        sa.Column("offered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "version", sa.Integer(), nullable=False, server_default=sa.text("1")
        ),
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
        sa.ForeignKeyConstraint(
            ["candidate_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "package_id",
            "dispatch_round",
            "candidate_user_id",
            name="uq_dispatch_offers_package_round_candidate",
        ),
        sa.CheckConstraint(
            "status IN ('offered', 'accepted', 'rejected', 'declined', "
            "'transferred', 'expired')",
            name="ck_dispatch_offers_status",
        ),
    )
    op.create_index(
        "ix_dispatch_offers_candidate", "dispatch_offers", ["candidate_user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dispatch_offers_candidate", table_name="dispatch_offers"
    )
    op.drop_table("dispatch_offers")
    op.drop_index(
        "ix_delivery_packages_status", table_name="delivery_packages"
    )
    op.drop_table("delivery_packages")
    op.drop_constraint("fk_gates_decided_by_user", "gates", type_="foreignkey")
    op.drop_constraint("fk_gates_submitted_by_user", "gates", type_="foreignkey")
    op.drop_column("gates", "is_delivery_party")
    op.drop_column("gates", "decided_by_user_id")
    op.drop_column("gates", "submitted_by_user_id")
