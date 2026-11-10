"""多客户工作平台 M1：组织底座（orgs 表 + users/projects/operation_events.org_id 归属列）。

ADR-M1 §3（甲路线，任务书 §11-1/§11-2 拍板）：
- ``orgs``：类型 enterprise/internal；internal = 平台自有（承载存量回填与
  平台侧项目）。**迁移播种一行平台内部组织**（稳定 ID 与
  ``orgs.models.INTERNAL_ORG_ID`` 单一权威同源）。
- ``users.org_id``（可空 = 平台身份，ADR-M2 §4；**存量用户不回填**——拍板
  §11-8「org_id=NULL」语义，存量回归面最小化）/ ``projects.org_id``（可空，
  随即回填）/ ``operation_events.org_id``（可空 = 平台级事件）。三列均
  RESTRICT——归属与审计不级联删。
- **存量回填**：``UPDATE projects SET org_id=<internal> WHERE org_id IS NULL``
  （本迁移是 org_id 的诞生点，全部现存行都是 NULL；WHERE 守卫保证重放安全，
  幂等）。

Backup hint: additive + 幂等回填；downgrade 先降索引与三列再删 orgs 表（对称可逆）。
"""
import sqlalchemy as sa
from alembic import op

revision = "a5e9c3f1b7d4"
# 十二度插队改挂：F 线 T1 b7e4c1a9f3d5 之后，保单头
down_revision = "b7e4c1a9f3d5"
branch_labels = None
depends_on = None

# 与 fde_api.orgs.models.INTERNAL_ORG_ID / INTERNAL_ORG_NAME 单一权威同源
# （迁移不 import 应用代码——两处常量由测试钉住逐位一致）。
INTERNAL_ORG_ID = "00000000-0000-0000-0000-0000000fde01"
INTERNAL_ORG_NAME = "平台内部组织"


def upgrade() -> None:
    op.create_table(
        "orgs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("subject_key", sa.String(length=18), nullable=True),
        # 创建者纯指针无 FK（破 orgs⇄users FK 环——元数据不可排序；先例
        # minutes.draft_id 同形，provenance 由应用层维护）
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "org_type IN ('enterprise', 'internal')",
            name="ck_orgs_org_type",
        ),
        sa.UniqueConstraint("name", name="uq_orgs_name"),
        sa.UniqueConstraint("subject_key", name="uq_orgs_subject_key"),
    )
    # 平台内部组织种子：迁移层播种（部署即有归属目标；cli bootstrap 另有
    # 幂等 get-or-create 兜底，同 ID 同名）。
    op.bulk_insert(
        sa.table(
            "orgs",
            sa.column("id"),
            sa.column("org_type"),
            sa.column("name"),
        ),
        [
            {"id": INTERNAL_ORG_ID, "org_type": "internal", "name": INTERNAL_ORG_NAME},
        ],
    )

    op.add_column(
        "users",
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("orgs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_users_org_id", "users", ["org_id"], unique=False)

    op.add_column(
        "projects",
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("orgs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index("ix_projects_org_id", "projects", ["org_id"], unique=False)
    # 存量回填：既有项目全部归入平台内部组织（internal = 平台自有）。
    op.execute(
        sa.text("UPDATE projects SET org_id = :org_id WHERE org_id IS NULL").bindparams(
            sa.bindparam("org_id", INTERNAL_ORG_ID)
        )
    )

    op.add_column(
        "operation_events",
        sa.Column(
            "org_id",
            sa.String(length=36),
            sa.ForeignKey("orgs.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_operation_events_org_occurred",
        "operation_events",
        ["org_id", "occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    # child-first 可逆：索引 → 归属列 → orgs 表
    op.drop_index(
        "ix_operation_events_org_occurred", table_name="operation_events"
    )
    op.drop_column("operation_events", "org_id")
    op.drop_index("ix_projects_org_id", table_name="projects")
    op.drop_column("projects", "org_id")
    op.drop_index("ix_users_org_id", table_name="users")
    op.drop_column("users", "org_id")
    op.drop_table("orgs")
