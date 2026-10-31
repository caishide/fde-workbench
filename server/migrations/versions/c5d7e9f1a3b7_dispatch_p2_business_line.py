"""dispatch P2: business_line dispatch-ready (goal-r7, P2-3)

派单设计 §8.5 P2-3：projects.business_line CHECK 'FDE' → ('FDE','FDE_DISPATCH')
（§11.1 注释已预留路径）。'FDE_DISPATCH' 的写入入口（派单池立项）随 P2 后续
轮启用——本迁移只放行枚举值，存量数据零变化。

Backup hint: constraint swap only, no data written.
"""
from alembic import op


revision = "c5d7e9f1a3b7"
down_revision = "b2c4d6e8f1a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_projects_business_line", "projects", type_="check")
    op.create_check_constraint(
        "ck_projects_business_line",
        "projects",
        "business_line IN ('FDE', 'FDE_DISPATCH')",
    )


def downgrade() -> None:
    # 回滚前须保证无 'FDE_DISPATCH' 行（当前无写入入口；防御性清理由运营执行）
    op.execute("UPDATE projects SET business_line = 'FDE' WHERE business_line = 'FDE_DISPATCH'")
    op.drop_constraint("ck_projects_business_line", "projects", type_="check")
    op.create_check_constraint(
        "ck_projects_business_line",
        "projects",
        "business_line IN ('FDE')",
    )
