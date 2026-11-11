"""多客户工作平台 M2：四入口统一注册底座（users 注册列 + user_registrations 表）。

任务书 §7-M2 / ADR-M2 §2 / ADR-M4（2026-11-11 OWNER 拍板：部署闸整体关闭、
区域伙伴个人主体＋机构字段、G6 收拢委托统一注册服务）：

- ``users`` 加三列：``email``（可空唯一——**存量与 admin 建号用户不回填**，
  与 org_id=NULL 存量不回填同款语义；PG 唯一索引多行 NULL 合法共存）／
  ``email_verified_at``／``registration_state``（NOT NULL，server_default
  'active'——存量行与管理员建号直落 active，零回填语句）。
- NEW ``user_registrations``：一账号一行（RESTRICT 引用 users），登记入口
  闭集（enterprise/founder/deliverer/partner）、申报材料 JSON（**只收指针 +
  sha256 指纹**——证据原件永不入库）、一次性验证令牌指纹（64 hex 唯一，
  重发即轮换）与审核留痕。

Backup hint: 纯 additive（加列加表）；downgrade 先删表再删列（对称可逆）。
"""
import sqlalchemy as sa
from alembic import op

revision = "b8d4f6a2c9e7"
# 十三度插队改挂：F 线 T2 c8d2f6a4e9b1（其前为夜审 r5 a9c5e2d7b3f1）之后，保单头
down_revision = "c8d2f6a4e9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users", sa.Column("email", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column(
            "registration_state",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_users_registration_state",
        "users",
        "registration_state IN ('pending_email', 'pending_review', 'active',"
        " 'suspended', 'rejected')",
    )
    # 可空唯一：存量多行 NULL 共存（PG 语义）；email 是注册面验证通道。
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "user_registrations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("entry", sa.String(length=16), nullable=False),
        sa.Column("materials_json", sa.JSON(), nullable=True),
        sa.Column("token_sha256", sa.String(length=64), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by_user_id",
            sa.String(length=36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "entry IN ('enterprise', 'founder', 'deliverer', 'partner')",
            name="ck_user_registrations_entry",
        ),
        sa.CheckConstraint(
            "token_sha256 IS NULL OR char_length(token_sha256) = 64",
            name="ck_user_registrations_token_sha256",
        ),
        sa.UniqueConstraint("token_sha256", name="uq_user_registrations_token_sha256"),
    )


def downgrade() -> None:
    # child-first 可逆：注册表 → email 列族
    op.drop_table("user_registrations")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_constraint("ck_users_registration_state", "users", type_="check")
    op.drop_column("users", "registration_state")
    op.drop_column("users", "email_verified_at")
    op.drop_column("users", "email")
