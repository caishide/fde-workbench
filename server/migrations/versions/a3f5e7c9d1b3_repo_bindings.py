"""repo_bindings table (AF3-WP1 solution-repo work-surface binding)

One row per work-tree binding (20 号 §3 WP1; 04 §3.3: 每次工作区绑定 repo、
基线 commit、分支、路径白名单与执行 grant): repo/workspace roots + frozen
allow_roots snapshot (binding-time freeze — re-binding to change) + base
commit + feature branch + status closed set (active|revoked; revoke takes
effect immediately). Unique per (org_id, repo_root, branch).

Append-only disposition: no PATCH/DELETE surface (status flips to revoked
once; binding history retained for evidence binding in WP5). Existing tables
and constraints are untouched (禁改清单第 6/10 项).
"""
from alembic import op
import sqlalchemy as sa

revision = "a3f5e7c9d1b3"
down_revision = "b3e8c7d1a9f4"
branch_labels = None
depends_on = None

BINDING_STATUSES = ("active", "revoked")


def upgrade() -> None:
    op.create_table(
        "repo_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("requester_id", sa.String(64), nullable=False),
        sa.Column("repo_root", sa.String(500), nullable=False),
        sa.Column("workspace_root", sa.String(500), nullable=False),
        sa.Column("allow_roots_json", sa.JSON(), nullable=False),
        sa.Column("base_commit", sa.String(40), nullable=False),
        sa.Column("branch", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("audit_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            f"status IN {BINDING_STATUSES!r}",
            name="ck_repo_bindings_status",
        ),
        sa.UniqueConstraint("org_id", "repo_root", "branch", name="uq_repo_bindings_org_repo_branch"),
    )
    op.create_index(
        "ix_repo_bindings_org_status",
        "repo_bindings",
        ["org_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_repo_bindings_org_status", table_name="repo_bindings")
    op.drop_table("repo_bindings")
