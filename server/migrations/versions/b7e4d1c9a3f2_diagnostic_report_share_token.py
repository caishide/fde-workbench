"""获客诊断工具 T-10b：报告生成请求时刻 + 分享令牌指纹。

在 T-10a 的 ``lead_diagnostic_sessions`` 上**只加两列**（不建新表）：

- ``report_requested_at``：报告生成请求时刻（异步面：受理 ≠ 就绪）。有了它，
  ``submitted`` 态能区分「还没请求」与「已请求·生成中」——访客轮询时看得到
  真实进度，而不是一个空报告。
- ``share_token_sha256``：分享令牌**指纹**（明文只在生成响应里返回一次）。
  可空（未生成分享链接时无值）；非空时唯一。分享页是**只读**面，故令牌可入
  URL；会话令牌是写权限凭证，只走请求头。两者指纹域分开（不同域分隔前缀），
  任一泄漏都不越界。

**零播种**：本迁移不插任何行。

Backup hint: additive only; downgrade drops the two added columns and index.
"""
import sqlalchemy as sa
from alembic import op

revision = "b7e4d1c9a3f2"
down_revision = "f3a9c7e1d5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lead_diagnostic_sessions",
        sa.Column("report_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "lead_diagnostic_sessions",
        sa.Column("share_token_sha256", sa.String(length=64), nullable=True),
    )
    op.create_check_constraint(
        "ck_lead_diagnostic_sessions_share_token_len",
        "lead_diagnostic_sessions",
        "share_token_sha256 IS NULL OR char_length(share_token_sha256) = 64",
    )
    op.create_index(
        "ux_lead_diagnostic_sessions_share_token",
        "lead_diagnostic_sessions",
        ["share_token_sha256"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ux_lead_diagnostic_sessions_share_token", table_name="lead_diagnostic_sessions"
    )
    op.drop_constraint(
        "ck_lead_diagnostic_sessions_share_token_len",
        "lead_diagnostic_sessions",
        type_="check",
    )
    op.drop_column("lead_diagnostic_sessions", "share_token_sha256")
    op.drop_column("lead_diagnostic_sessions", "report_requested_at")
