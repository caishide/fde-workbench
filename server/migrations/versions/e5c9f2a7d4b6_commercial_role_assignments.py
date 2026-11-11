"""F 线 T4：兼任承载表（commercial_role_assignments）。

ADR-011 §3.8（同一主体可兼任拉单＋交付；任务书 §4 T4）：

- 一人多角色：一人可有多行（多角色并存），每行附**生效区间**
  （``valid_from``／``valid_until``，后者空＝长期有效）与**来源**
  （书面依据指针＋sha256 指纹，不内嵌正文——证据红线同款）。
- ``commercial_entitlements.commercial_role`` 单值列保留为「主角色」兼容
  读面（**不删列**）；``users.role`` 权限角色**零改动**（ADR-001 保护
  清单；本表正交于权限）。
- 自拉自交（lead 与 delivery 同一 payee）允许，但**验收人恒为平台**——
  该结构性排除落在 ``projects.payment_service.mark_acceptance_passed``
  咽喉（服务层，非本迁移）；本迁移只承载兼任事实。
- 同角色生效区间重叠的拒绝在服务层（行锁＋重叠判定 409
  ``role_assignment_overlap``）；DB 层 CHECK 只钉窗口方向
  （``valid_until > valid_from``）与角色闭集。

Backup hint: additive only; downgrade drops the single new table.
"""
import sqlalchemy as sa
from alembic import op

revision = "e5c9f2a7d4b6"
down_revision = "b8d4f6a2c9e7"  # 十七度插队改挂：多客户 M2 b8d4f6a2c9e7 之后，保单头
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commercial_role_assignments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("commercial_role", sa.String(length=2), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_uri", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("assigned_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_commercial_role_assignments"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_commercial_role_assignments_user",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            name="fk_commercial_role_assignments_assigned_by",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "commercial_role IN ('R1', 'R2', 'R3', 'R4')",
            name="ck_commercial_role_assignments_role",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_commercial_role_assignments_window",
        ),
    )
    op.create_index(
        "ix_commercial_role_assignments_user",
        "commercial_role_assignments",
        ["user_id", "commercial_role"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_commercial_role_assignments_user", table_name="commercial_role_assignments"
    )
    op.drop_table("commercial_role_assignments")
