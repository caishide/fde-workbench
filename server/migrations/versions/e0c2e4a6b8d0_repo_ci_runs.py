"""repo_ci_runs table (AF3-WP3 fixed trusted CI bundle runs)

One row per CI bundle execution (design-first spec `_af3-wp3-ci-bundle-spec.md`
§3.4): bundle closed-set id + head commit anchor + verdict closed set
(green|red|error — error = timeout/infrastructure, honestly attributed, never
masquerades as red) + nodeid-level executed checks (the "CI green without
running new assertions" counter-evidence face, 05 §5 AF3 行) + new test nodeids
relative to the binding baseline. Append-only, re-runnable (no UNIQUE — every
run is a new row). Existing tables and constraints are untouched.
"""
from alembic import op
import sqlalchemy as sa

revision = "e0c2e4a6b8d0"
down_revision = "c9e1f3a5b7d9"
branch_labels = None
depends_on = None

VERDICTS = ("green", "red", "error")


def upgrade() -> None:
    op.create_table(
        "repo_ci_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("bundle_id", sa.String(64), nullable=False),
        sa.Column("head_commit", sa.String(40), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("executed_json", sa.JSON(), nullable=False),
        sa.Column("new_tests_json", sa.JSON(), nullable=False),
        sa.Column("stdout_head", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("stderr_head", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("error_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            f"verdict IN {VERDICTS!r}",
            name="ck_repo_ci_runs_verdict",
        ),
        sa.Index("ix_repo_ci_runs_org_binding", "org_id", "binding_id"),
    )


def downgrade() -> None:
    op.drop_table("repo_ci_runs")
