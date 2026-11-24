"""funnel data_origin columns (Ecosystem OS M2 acceptance #9: real/simulated/drill)

OWNER 拍板（2026-11-24 交互式，推荐项获选）立项补分层标记：四段漏斗对象中的
三张主体表各加 ``data_origin`` 闭集列（drill/real/simulated；缺省 real），
CHECK 钉死。派单 offer 不加列——offer 严格从属交付包，来源经 package_id
传导（简报漏斗 join 包取 origin）。

回填口径（本迁移的**已核实假设**）：2026-11-24 活库只读探针证实
delivery_packages 4 行全部属 E2E 机制造蜂项目（FDE-2026xxxx-*，业务线
FDE_DISPATCH，全 accepted）⇒ 存量交付包回填 'drill'。dispatch_offers 4 行
经包传导同判（无列）。regional_partners / fde_profiles 迁移时为空表（0 行），
无回填对象。其余部署如存在真实存量行，须在升级前人工核regist（当前本系统
单机单租户，无他部署）。
"""
from alembic import op
import sqlalchemy as sa

revision = "b8d2f6a0c4e8"
down_revision = "f2a4b6c8d0e2"
branch_labels = None
depends_on = None

_ORIGINS = ("drill", "real", "simulated")


def upgrade() -> None:
    for table in ("delivery_packages", "regional_partners", "fde_profiles"):
        op.add_column(
            table,
            sa.Column(
                "data_origin",
                sa.String(12),
                nullable=False,
                server_default="real",
            ),
        )
        op.create_check_constraint(
            f"ck_{table}_data_origin",
            table,
            f"data_origin IN {_ORIGINS!r}",
        )
    # 存量交付包＝已核实的机制造蜂行（见模块头回填口径）⇒ drill
    op.execute("UPDATE delivery_packages SET data_origin = 'drill'")


def downgrade() -> None:
    for table in ("delivery_packages", "regional_partners", "fde_profiles"):
        op.drop_constraint(f"ck_{table}_data_origin", table, type_="check")
        op.drop_column(table, "data_origin")
