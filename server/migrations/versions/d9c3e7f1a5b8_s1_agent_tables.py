"""S1 agent 表簇 + 沙箱基座（goal-d3，技术实施方案 §2/§4）

goal-d3：agent_registry / agent_runs / agent_artifacts / agent_tool_calls /
agent_credentials 五新表 + solution_review_checkpoints + project_solutions
生成来源四列（generated_by/agent_run_id/template_id/confidence，架构方案 §9
E3 列级 ALTER）。回填：d2 方案骨架把行业模板版本号藏在
source_json.industry_template_version_id（kind='skeleton'），本迁移把它列化；
generated_by 保持 'human'——骨架是 AI 不参与内容生成的人工草稿，'agent' 随
goal-d4 run 链启用。零删列、零改既有约束，纯增量可逆。

Backup hint: additive only; backfill copies a JSON key into a new nullable column.
"""
import sqlalchemy as sa
from alembic import op


revision = "d9c3e7f1a5b8"
down_revision = "c5d7e9f1a3b7"
branch_labels = None
depends_on = None


def _timestamp_columns() -> list[sa.Column]:
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
    op.create_table(
        "agent_registry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("capability_tier", sa.String(length=64), nullable=False),
        sa.Column("sandbox_profile", sa.String(length=64), nullable=False),
        sa.Column("max_cost_units", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("credential_ref", sa.String(length=120), nullable=True),
        # 声明式工具白名单（自动交付 §5.1），空数组 = 默认全拒
        sa.Column("allowed_tools", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "kind IN ('zcode', 'codex', 'claude_code', 'opencode', 'persona')",
            name="ck_agent_registry_kind",
        ),
        sa.CheckConstraint("max_cost_units >= 0", name="ck_agent_registry_max_cost"),
        sa.CheckConstraint("max_duration_ms >= 0", name="ck_agent_registry_max_duration"),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("initiated_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("capability_used", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="queued", nullable=False),
        sa.Column("context_ref", sa.String(length=255), nullable=False),
        sa.Column("token_cost", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("degraded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("degraded_reason", sa.String(length=32), nullable=True),
        sa.Column("fallback_level", sa.String(length=8), nullable=True),
        # 重试链软引用：不设 FK，允许指向已归档 run（goal-d3 报告 §二 登记）
        sa.Column("retry_of", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("cost_owner_type", sa.String(length=16), server_default="project", nullable=False),
        sa.Column("cost_owner_id", sa.String(length=64), nullable=True),
        sa.Column("handoff_user_id", sa.String(length=36), nullable=True),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_id"], ["agent_registry.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["initiated_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["handoff_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'timeout', 'budget_exceeded')",
            name="ck_agent_runs_status",
        ),
        sa.CheckConstraint(
            "fallback_level IS NULL OR fallback_level IN ('L0', 'L1', 'L2', 'L3')",
            name="ck_agent_runs_fallback_level",
        ),
        sa.CheckConstraint(
            "cost_owner_type IN ('project', 'seat', 'platform')",
            name="ck_agent_runs_cost_owner_type",
        ),
        sa.CheckConstraint("token_cost >= 0", name="ck_agent_runs_token_cost"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_agent_runs_duration"),
    )
    op.create_index(
        "ix_agent_runs_project_status", "agent_runs", ["project_id", "status"]
    )
    # 幂等键只建索引不设唯一：重试行与原 run 共享同一 key（goal-d3 报告 §二）
    op.create_index("ix_agent_runs_idempotency", "agent_runs", ["idempotency_key"])

    # —— project_solutions 生成来源四列（列级 ALTER）——
    op.add_column(
        "project_solutions",
        sa.Column("generated_by", sa.String(length=16), server_default="human", nullable=False),
    )
    op.add_column(
        "project_solutions", sa.Column("agent_run_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "project_solutions", sa.Column("template_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "project_solutions", sa.Column("confidence", sa.Float(), nullable=True)
    )
    op.create_check_constraint(
        "ck_project_solutions_generated_by",
        "project_solutions",
        "generated_by IN ('human', 'agent')",
    )
    op.create_foreign_key(
        "fk_project_solutions_agent_run",
        "project_solutions",
        "agent_runs",
        ["agent_run_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_project_solutions_template",
        "project_solutions",
        "industry_template_versions",
        ["template_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # 回填：d2 骨架的行业模板版本列化（只认现存版本 id，防御陈旧引用）
    op.execute(
        """
        UPDATE project_solutions ps
        SET template_id = ps.source_json->>'industry_template_version_id'
        WHERE ps.source_json IS NOT NULL
          AND ps.source_json->>'kind' = 'skeleton'
          AND ps.source_json->>'industry_template_version_id' IS NOT NULL
          AND EXISTS (
              SELECT 1 FROM industry_template_versions v
              WHERE v.id = ps.source_json->>'industry_template_version_id'
          )
        """
    )

    op.create_table(
        "agent_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("storage_ref", sa.String(length=255), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("reviewed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("linked_solution_id", sa.String(length=36), nullable=True),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["linked_solution_id"], ["project_solutions.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "kind IN ('code', 'doc', 'diff', 'config')", name="ck_agent_artifacts_kind"
        ),
        sa.CheckConstraint(
            "char_length(sha256) = 64", name="ck_agent_artifacts_sha256_len"
        ),
    )

    op.create_table(
        "agent_tool_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("capability", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.String(length=120), nullable=True),
        sa.Column("duration_ms", sa.Integer(), server_default=sa.text("0"), nullable=False),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "decision IN ('allowed', 'denied')", name="ck_agent_tool_calls_decision"
        ),
    )

    op.create_table(
        "agent_credentials",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("credential_ciphertext", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
    )

    op.create_table(
        "solution_review_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("solution_id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_type", sa.String(length=32), nullable=False),
        sa.Column("required_level", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("reviewer_user_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_ref", sa.String(length=255), nullable=True),
        *_timestamp_columns(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["solution_id"], ["project_solutions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint(
            "checkpoint_type IN ('template', 'rule', 'knowledge', 'signoff')",
            name="ck_solution_review_checkpoints_type",
        ),
        sa.CheckConstraint(
            "required_level IN ('assistant_read', 'project_operator', 'project_manager', 'system_operator')",
            name="ck_solution_review_checkpoints_level",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_solution_review_checkpoints_status",
        ),
    )
    op.create_index(
        "ix_solution_review_checkpoints_solution",
        "solution_review_checkpoints",
        ["solution_id", "status"],
    )


def downgrade() -> None:
    # 纯增量回滚：子表先删，再摘 project_solutions 新列（回填值随列丢弃，
    # source_json 原文不动——再升级可完整重放回填）。
    op.drop_index(
        "ix_solution_review_checkpoints_solution", table_name="solution_review_checkpoints"
    )
    op.drop_table("solution_review_checkpoints")
    op.drop_table("agent_credentials")
    op.drop_table("agent_tool_calls")
    op.drop_table("agent_artifacts")
    op.drop_constraint("fk_project_solutions_template", "project_solutions", type_="foreignkey")
    op.drop_constraint(
        "fk_project_solutions_agent_run", "project_solutions", type_="foreignkey"
    )
    op.drop_constraint(
        "ck_project_solutions_generated_by", "project_solutions", type_="check"
    )
    op.drop_column("project_solutions", "confidence")
    op.drop_column("project_solutions", "template_id")
    op.drop_column("project_solutions", "agent_run_id")
    op.drop_column("project_solutions", "generated_by")
    op.drop_index("ix_agent_runs_idempotency", table_name="agent_runs")
    op.drop_index("ix_agent_runs_project_status", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_table("agent_registry")
