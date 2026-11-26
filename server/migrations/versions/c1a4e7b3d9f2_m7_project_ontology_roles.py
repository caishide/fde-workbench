"""project_ontology_roles：项目级本体审批角色授予（M7 / S-21）

纯新增表（append-only，零改既有表）：本体审批角色的真身落 Workbench 侧。

背景（M7 决策单第 2 条）：runtime 的审批角色此前取自请求体自报——服务端只验
「提议人 ≠ 复核人」与「每角色一票」，一个非提议人可连投三票把变更集批掉。
M7 起角色须由 Workbench 侧授权数据派生，签进 X-FDE-Context 的 roles 声明
（进 HMAC 覆盖面），runtime 再校验「投票角色 ∈ 声明角色」与「三必签角色异人」。

约束：role 闭集四值（与 runtime approvals.role CHECK 同源）；
uq(project_id, user_id, role) 同一人同一角色不重复授予；
org_id = 项目归属（projects.org_id，与绑定同源，D10 段 2 口径）；
granted_by_user_id 留痕授权责任。

Backup hint: additive only; downgrade drops the table (child-free).
"""

import sqlalchemy as sa
from alembic import op

revision = "c1a4e7b3d9f2"
down_revision = "b8d2f6a0c4e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_ontology_roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("granted_by_user_id", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "role IN ('business_owner', 'model_consultant', 'data_owner', 'risk')",
            name="ck_project_ontology_roles_role",
        ),
        sa.UniqueConstraint(
            "project_id",
            "user_id",
            "role",
            name="uq_project_ontology_roles_project_user_role",
        ),
    )
    op.create_index(
        "ix_project_ontology_roles_project", "project_ontology_roles", ["project_id"]
    )
    op.create_index("ix_project_ontology_roles_user", "project_ontology_roles", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_project_ontology_roles_user", table_name="project_ontology_roles")
    op.drop_index("ix_project_ontology_roles_project", table_name="project_ontology_roles")
    op.drop_table("project_ontology_roles")
