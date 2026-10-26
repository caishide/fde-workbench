"""add ai_call_audits table

E7：AI 供应商调用审计。每次调用落一条（模型/耗时/token/结果状态），
月度 token 预算按该表按用户汇总核算；预算拦截也落一条
status='budget_blocked'。表里没有任何密钥或明文上下文字段。

Backup hint: pure CREATE TABLE, no data written. Downgrade drops the table
(and its audit history) — only run with explicit confirmation.
"""
from alembic import op
import sqlalchemy as sa


revision = "e5b8a1c9d3f7"
down_revision = "b8d4f2a6c0e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_call_audits",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("request_id", sa.String(length=120), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("purpose", sa.String(length=60), nullable=True),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column(
            "used_fallback",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_code", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'budget_blocked')",
            name="ck_ai_call_audits_status",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_call_audits_actor_created",
        "ai_call_audits",
        ["actor_user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_call_audits_actor_created", table_name="ai_call_audits")
    op.drop_table("ai_call_audits")
