"""获客诊断 T-15：渠道链接注册表（lead_diagnostic_channel_links）。

落地形（获客诊断工具实施任务书 §3 T-15：渠道链接 ID 体系）：

- **R4 专属链接 = 归因凭证**：访客经链接进入 ⇒ 服务端机械落
  ``source_type='partner'``（A 渠道报备档），零手工记账（P-2）。
- **token 只存 sha256 指纹**（64 位 CHECK＋唯一索引）——明文只在创建响应里
  返回一次（沿匿名会话令牌同尺）；库泄漏拿不到可用链接。
- ``created_by`` 指向 users 且 **SET NULL**（发链接的平台操作员离职不锁表）；
  **零外键指向 projects**（线索 ≠ 项目）；与线索行零外键（``channel_ref``
  写回的是链接行 UUID，松耦合——删链接不改历史归因）。
- 停用是软撤（``is_active=False``＋``deactivated_at``）：历史归因不改写，
  新会话不再解析为 partner（fail-closed 降档 direct）。

幂等：建表 + 两索引（token 唯一、is_active）；downgrade 对称可逆（删索引→表）。

Backup hint: additive only; downgrade drops the new table.
"""
import sqlalchemy as sa
from alembic import op

revision = "a3e8c2f6b9d4"
down_revision = "d7e2f4a9c1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lead_diagnostic_channel_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("region_name", sa.String(length=80), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
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
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "char_length(token_sha256) = 64",
            name="ck_lead_diagnostic_channel_links_token_sha_len",
        ),
        sa.CheckConstraint(
            "is_active OR deactivated_at IS NOT NULL",
            name="ck_lead_diagnostic_channel_links_deactivate_shape",
        ),
    )
    op.create_index(
        "ux_lead_diagnostic_channel_links_token",
        "lead_diagnostic_channel_links",
        ["token_sha256"],
        unique=True,
    )
    op.create_index(
        "ix_lead_diagnostic_channel_links_active",
        "lead_diagnostic_channel_links",
        ["is_active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lead_diagnostic_channel_links_active", table_name="lead_diagnostic_channel_links"
    )
    op.drop_index(
        "ux_lead_diagnostic_channel_links_token", table_name="lead_diagnostic_channel_links"
    )
    op.drop_table("lead_diagnostic_channel_links")
