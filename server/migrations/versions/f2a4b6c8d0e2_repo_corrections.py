"""repo_corrections table (AF3-WP4 correction loop trajectory)

One row per correction-loop trajectory (20 号 §3 WP4; AF1① 预算内收敛;
05 §2.1 T4 修复轨迹; 05 §3 错误修复成功率「预算内真实读取失败并通过复测」):
failed CI run anchor (verdict=red — correction must consume a real failure,
AF2④) + rounds consumed (≤ max_rounds budget) + per-round patch_id list
(trajectory evidence; patch plaintext lives in RepoPatch/绑定仓 git history) +
final re-run anchor + verdict + status closed set (corrected |
budget_exhausted | failed — honest terminal, no unlimited retry).
Append-only, re-runnable (no UNIQUE — each trajectory is a new row).
"""
from alembic import op
import sqlalchemy as sa

revision = "f2a4b6c8d0e2"
down_revision = "e0c2e4a6b8d0"
branch_labels = None
depends_on = None

STATUSES = ("corrected", "budget_exhausted", "failed")


def upgrade() -> None:
    op.create_table(
        "repo_corrections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("failed_run_id", sa.String(36), nullable=False),
        sa.Column("bundle_id", sa.String(64), nullable=False),
        sa.Column("rounds_consumed", sa.Integer(), nullable=False),
        sa.Column("patches_json", sa.JSON(), nullable=False),
        sa.Column("final_run_id", sa.String(36), nullable=False),
        sa.Column("final_verdict", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            f"status IN {STATUSES!r}",
            name="ck_repo_corrections_status",
        ),
        sa.Index("ix_repo_corrections_org_binding", "org_id", "binding_id"),
    )


def downgrade() -> None:
    op.drop_table("repo_corrections")
