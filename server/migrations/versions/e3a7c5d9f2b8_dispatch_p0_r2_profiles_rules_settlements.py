"""dispatch P0 round-2: profiles / rule versions / settlements (goal-r2)

派单设计 §8.2/§8.3（簇②表建设）：
- P0-3 fde_level_evidence + fde_profiles（§3.2/§3.3 档案与等级证据链；
  先建 evidence 再建 profiles，profiles.level_evidence_id 外键指向它）。
- P0-8 dispatch_rule_versions（§6.2/规则表 B9 权重与规则版本快照）。
- P0-4 delivery_settlements（§7.2 席位级结算）+ payments.acceptance_passed_at
  一列（G8 过门联动打标；Payment 唯一约束不动，催款读时现算零改动）。

Backup hint: additive column (nullable) + pure CREATE TABLE, no data written.
Downgrade drops the four tables and the payments column, reverse order.
"""
from alembic import op
import sqlalchemy as sa


revision = "e3a7c5d9f2b8"
down_revision = "d2f6b4c8a1e9"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    # ---- P0-3 前置：复购判据可表达（§3.3「同一 enterprise_code 下 ≥2 个项目」）----
    # uq_projects_enterprise_code 全局唯一使复购不可表达；放宽为普通索引。
    # 代号红线不动（仍只存代号）；唯一性交还录入侧约定。goal-r2 留注③。
    op.drop_constraint(
        "uq_projects_enterprise_code", "projects", type_="unique"
    )
    op.create_index(
        "ix_projects_enterprise_code", "projects", ["enterprise_code"]
    )

    # ---- P0-3：fde_level_evidence（先建，profiles 引用它）----
    op.create_table(
        "fde_level_evidence",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("from_level", sa.String(length=4), nullable=True),
        sa.Column("to_level", sa.String(length=4), nullable=False),
        sa.Column("verified_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_summary", sa.JSON(), nullable=True),
        sa.Column("source_uri", sa.String(length=500), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["verified_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "from_level IS NULL OR from_level IN ('L1', 'L2', 'L3', 'L4')",
            name="ck_fde_level_evidence_from",
        ),
        sa.CheckConstraint(
            "to_level IN ('L1', 'L2', 'L3', 'L4')",
            name="ck_fde_level_evidence_to",
        ),
    )
    op.create_index(
        "ix_fde_level_evidence_verified_by",
        "fde_level_evidence",
        ["verified_by_user_id"],
    )

    # ---- P0-3：fde_profiles（一人一档案，PK=user_id）----
    op.create_table(
        "fde_profiles",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("level", sa.String(length=4), nullable=True),
        sa.Column("level_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("level_evidence_id", sa.String(length=36), nullable=True),
        sa.Column(
            "biz_cognition_score", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "scenario_eng_score", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "ai_tech_score", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "delivery_assure_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("industry_tags", sa.JSON(), nullable=True),
        sa.Column("module_tags", sa.JSON(), nullable=True),
        sa.Column("service_cities", sa.JSON(), nullable=True),
        sa.Column("home_city", sa.String(length=32), nullable=True),
        sa.Column("geo_fence_km", sa.Integer(), nullable=False, server_default=sa.text("25")),
        sa.Column("monthly_capacity_hours", sa.Integer(), nullable=True),
        sa.Column("avg_delivery_hours", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["level_evidence_id"], ["fde_level_evidence.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.CheckConstraint(
            "level IS NULL OR level IN ('L1', 'L2', 'L3', 'L4')",
            name="ck_fde_profiles_level",
        ),
        sa.CheckConstraint(
            "biz_cognition_score BETWEEN 0 AND 5",
            name="ck_fde_profiles_biz_cognition",
        ),
        sa.CheckConstraint(
            "scenario_eng_score BETWEEN 0 AND 5", name="ck_fde_profiles_scenario_eng"
        ),
        sa.CheckConstraint("ai_tech_score BETWEEN 0 AND 5", name="ck_fde_profiles_ai_tech"),
        sa.CheckConstraint(
            "delivery_assure_score BETWEEN 0 AND 5",
            name="ck_fde_profiles_delivery_assure",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'suspended')",
            name="ck_fde_profiles_status",
        ),
    )

    # ---- P0-8：dispatch_rule_versions ----
    op.create_table(
        "dispatch_rule_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column(
            "status", sa.String(length=12), nullable=False, server_default="draft"
        ),
        sa.Column("rule_snapshot", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_by_user_id", sa.String(length=36), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_no", name="uq_dispatch_rule_versions_version_no"),
        sa.CheckConstraint("version_no >= 1", name="ck_dispatch_rule_versions_no"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'active', 'retired')",
            name="ck_dispatch_rule_versions_status",
        ),
    )

    # ---- P0-4：delivery_settlements + payments.acceptance_passed_at ----
    op.create_table(
        "delivery_settlements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("settlement_key", sa.String(length=20), nullable=False),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("seat_platform_user_id", sa.String(length=36), nullable=True),
        sa.Column("seat_region_agent_user_id", sa.String(length=36), nullable=True),
        sa.Column("seat_city_partner_user_id", sa.String(length=36), nullable=True),
        sa.Column("seat_delivery_user_id", sa.String(length=36), nullable=True),
        sa.Column("platform_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("region_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("city_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("delivery_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "withholding_tax",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "status", sa.String(length=12), nullable=False, server_default="draft"
        ),
        sa.Column("acceptance_passed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_proof_source_uri", sa.String(length=500), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["package_id"], ["delivery_packages.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["seat_platform_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["seat_region_agent_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["seat_city_partner_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["seat_delivery_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "package_id", "settlement_key", name="uq_delivery_settlements_package_key"
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'accrued', 'payable', 'paid', 'disputed')",
            name="ck_delivery_settlements_status",
        ),
    )
    op.create_index(
        "ix_delivery_settlements_delivery_user",
        "delivery_settlements",
        ["seat_delivery_user_id"],
    )
    op.add_column(
        "payments",
        sa.Column("acceptance_passed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_projects_enterprise_code", table_name="projects")
    op.create_unique_constraint(
        "uq_projects_enterprise_code", "projects", ["enterprise_code"]
    )
    op.drop_column("payments", "acceptance_passed_at")
    op.drop_index(
        "ix_delivery_settlements_delivery_user", table_name="delivery_settlements"
    )
    op.drop_table("delivery_settlements")
    op.drop_table("dispatch_rule_versions")
    op.drop_table("fde_profiles")
    op.drop_index(
        "ix_fde_level_evidence_verified_by", table_name="fde_level_evidence"
    )
    op.drop_table("fde_level_evidence")
