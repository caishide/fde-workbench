"""获客诊断工具 T-10a：匿名诊断会话表（lead_diagnostic_sessions）。

本仓**第一个公网免注册写面**的落地形（获客诊断工具实施任务书 §3 T-10）：

- 一行 = 一次匿名诊断尝试（线索行）。**零外键指向 projects**——线索 ≠ 项目，
  沿 transcripts 草稿区同款隔离手法（metadata 扫描钉死）。
- ``token_sha256``：匿名令牌的**指纹**（明文只在客户端，库里只存 sha256）——
  库泄漏不等于会话被接管。
- ``created_ip_hash``：来源 IP 的稳定假名（sha256(ip + 密钥，域分隔)），
  **不是明文 IP**。
- ``source_type`` / ``channel_ref`` / ``attribution_tier`` / ``claim_window_*``：
  三档归因的**结构**（P-2：比例只落结构不落数，挂账到价格轮）。
- ``status`` 状态机 draft → submitted → report_ready → claimed | expired
  （T-10a 只落前两态；report_ready 由 T-10b 推进，claimed 由 T-11 推进）。

**零播种**：本表是匿名访客会话，无默认行。

Backup hint: additive only; downgrade drops the single new table.
"""
import sqlalchemy as sa
from alembic import op

revision = "f3a9c7e1d5b2"
down_revision = "e8b3f7c2d9a5"
branch_labels = None
depends_on = None


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "lead_diagnostic_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("answers", sa.JSON(), nullable=True),
        sa.Column("assessment", sa.JSON(), nullable=True),
        sa.Column("report", sa.JSON(), nullable=True),
        sa.Column("lead_contact", sa.JSON(), nullable=True),
        sa.Column("source_type", sa.String(length=20), nullable=False, server_default="direct"),
        sa.Column("channel_ref", sa.String(length=80), nullable=True),
        sa.Column("created_ip_hash", sa.String(length=64), nullable=False),
        sa.Column("claim_window_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("attribution_tier", sa.String(length=20), nullable=True),
        sa.Column("failure_code", sa.String(length=60), nullable=True),
        sa.Column("failure_message", sa.Text(), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["claimed_by_user_id"], ["users.id"], name="fk_lead_diagnostic_sessions_claimed_by", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'report_ready', 'claimed', 'expired')",
            name="ck_lead_diagnostic_sessions_status",
        ),
        sa.CheckConstraint(
            "source_type IN ('direct', 'channel', 'partner')",
            name="ck_lead_diagnostic_sessions_source_type",
        ),
        sa.CheckConstraint(
            "char_length(token_sha256) = 64", name="ck_lead_diagnostic_sessions_token_sha_len"
        ),
        sa.CheckConstraint(
            "char_length(created_ip_hash) = 64", name="ck_lead_diagnostic_sessions_ip_hash_len"
        ),
        sa.CheckConstraint(
            "claim_window_expires_at IS NOT NULL", name="ck_lead_diagnostic_sessions_claim_window"
        ),
    )
    op.create_index(
        "ux_lead_diagnostic_sessions_token",
        "lead_diagnostic_sessions",
        ["token_sha256"],
        unique=True,
    )
    op.create_index(
        "ix_lead_diagnostic_sessions_status_created",
        "lead_diagnostic_sessions",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_lead_diagnostic_sessions_source",
        "lead_diagnostic_sessions",
        ["source_type", "channel_ref"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_diagnostic_sessions_source", table_name="lead_diagnostic_sessions")
    op.drop_index("ix_lead_diagnostic_sessions_status_created", table_name="lead_diagnostic_sessions")
    op.drop_index("ux_lead_diagnostic_sessions_token", table_name="lead_diagnostic_sessions")
    op.drop_table("lead_diagnostic_sessions")
