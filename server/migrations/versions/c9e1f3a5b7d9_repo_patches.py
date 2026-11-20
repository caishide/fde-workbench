"""repo_patches table + repo_bindings.grant_json column (AF3-WP2 typed Patch adapter)

One row per typed PatchPlan application (20 号 §3 WP2): plan digest (zero
plaintext — entry contents never land in the DB; the artifact truth lives in
the binding repo's git history via applied_commit) + idempotency
(UNIQUE(org_id, binding_id, patch_id) — replay returns the first result with
zero repeated side effects) + status closed set (applied|failed; gate-level
rejections do NOT insert a row — rejection-path-no-row discipline, AE1 口径;
execution failures record a failed row with error snapshot) + base_commit /
applied_commit pair as the T4 evidence anchor (05 §2.1 T4 行 commit/产物 hash).

repo_bindings.grant_json (评审 D3 清偿): 04 §3.3 binding 五要素之「执行 grant」
机器落法 — JSON null = full agent_allowed set; otherwise {"ops": [...]} subset
whitelist (closed-set violation rejected at bind time; runtime violation 403
tool_not_allowed). Additive column (nullable), append-only 纪律合规。
"""
from alembic import op
import sqlalchemy as sa

revision = "c9e1f3a5b7d9"
down_revision = "a3f5e7c9d1b3"
branch_labels = None
depends_on = None

PATCH_STATUSES = ("applied", "failed")


def upgrade() -> None:
    op.add_column(
        "repo_bindings",
        sa.Column("grant_json", sa.JSON(), nullable=True),
    )
    op.create_table(
        "repo_patches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("patch_id", sa.String(128), nullable=False),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("entry_count", sa.Integer(), nullable=False),
        sa.Column("base_commit", sa.String(40), nullable=False),
        sa.Column("applied_commit", sa.String(40), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=False, server_default=sa.text("''")),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("audit_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            f"status IN {PATCH_STATUSES!r}",
            name="ck_repo_patches_status",
        ),
        sa.UniqueConstraint("org_id", "binding_id", "patch_id", name="uq_repo_patches_org_binding_patch"),
    )
    op.create_index("ix_repo_patches_org_status", "repo_patches", ["org_id", "status"])
    op.create_index("ix_repo_patches_binding", "repo_patches", ["binding_id"])


def downgrade() -> None:
    op.drop_index("ix_repo_patches_binding", table_name="repo_patches")
    op.drop_index("ix_repo_patches_org_status", table_name="repo_patches")
    op.drop_table("repo_patches")
    op.drop_column("repo_bindings", "grant_json")
