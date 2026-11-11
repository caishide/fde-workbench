"""多客户工作平台 M5-1：企业组织成员邀请表（org_member_invitations）。

M5-1 规格 v1 §1–§2：邀请是 org 归属面，不是第二套权限体系（红线 8）；接受邀请
唯一副作用＝把受邀用户 users.org_id 置为本 org（归属维度，可见性由既有
project_org_scope_filter 覆盖）。一次性令牌（sha256 指纹入库、明文只走链接）＋
邮箱绑定（sec 评审：邀请是社会工程攻击面）＋ 三态互斥（pending/accepted/revoked）。

幂等：建表 + 三索引（令牌唯一、部分唯一索引用 pending 去重、org 列表索引）；
downgrade 对称可逆（删部分唯一索引 → 令牌唯一索引 → 表）。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c1d4e7f9a2b3"
down_revision = "e9b4f7c2a8d3"  # M4 批次 C（rebase 后现 head；原 a7c2f9e1b4d8 已分叉）
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_member_invitations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("orgs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("invited_email", sa.String(length=255), nullable=False),
        sa.Column(
            "invited_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        # 一次性令牌指纹（64 位 hex）；明文只出现在邀请链接
        sa.Column("token_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "token_expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "accepted_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
            "token_sha256 IS NULL OR char_length(token_sha256) = 64",
            name="ck_org_member_invitations_token_sha256",
        ),
        # 三态互斥：accepted/revoked 至多一个落戳（pending＝两者皆 NULL）
        sa.CheckConstraint(
            "(accepted_at IS NULL) OR (revoked_at IS NULL)",
            name="ck_org_member_invitations_terminal_mutex",
        ),
        # 一次性令牌指纹唯一（明文只走链接）
        sa.UniqueConstraint("token_sha256", name="uq_org_member_invitations_token"),
    )
    # 每 org 同邮箱至多一份待接受邀请（重复邀请刷屏防护）
    op.create_index(
        "uq_org_member_invitations_pending",
        "org_member_invitations",
        ["org_id", "invited_email"],
        unique=True,
        postgresql_where=sa.text("accepted_at IS NULL AND revoked_at IS NULL"),
    )
    op.create_index(
        "ix_org_member_invitations_org",
        "org_member_invitations",
        ["org_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_org_member_invitations_org", table_name="org_member_invitations"
    )
    op.drop_index(
        "uq_org_member_invitations_pending", table_name="org_member_invitations"
    )
    op.drop_table("org_member_invitations")
