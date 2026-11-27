"""B3-1（FDU 对照分析 D-1 拍板）：产能/单均工时的核验证据链（2026-11-27）。

链位：接 M7/S-21 c1a4e7b3d9f2 之后，保持单头。

背景：``fde_profiles.monthly_capacity_hours`` / ``avg_delivery_hours`` 是
同时接单上限（撮合 A4）的算法输入（``dispatch/matching.py`` ``_capacity_cap``），
但真实档案此前**零合法写路径**——唯一写入方＝派单仿真器，register 路由
以负例明确拒收产能字段覆盖（``test_dispatch_profile_enable.py``）。
本迁移给两列配与等级核验同规格的证据链（只存 source_uri 指针 + sha256
指纹，不存本体；核验人 = 平台管理员），写入口＝
``POST /admin/dispatch/profiles/<user_id>/capacity-evidence``
（admin + 密码双闸，沿 register/enable 家族）。

additive-only：4 新列可空，存量行逐位零变更。downgrade 逆序还原。
"""
import sqlalchemy as sa
from alembic import op

revision = "f6e9c3a1d7b4"
down_revision = "c1a4e7b3d9f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fde_profiles",
        sa.Column("capacity_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "fde_profiles",
        sa.Column("capacity_evidence_uri", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "fde_profiles",
        sa.Column("capacity_evidence_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "fde_profiles",
        sa.Column(
            "capacity_verified_by_user_id", sa.String(length=36), nullable=True
        ),
    )
    op.create_foreign_key(
        "fk_fde_profiles_capacity_verified_by",
        "fde_profiles",
        "users",
        ["capacity_verified_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_fde_profiles_capacity_verified_by", "fde_profiles", type_="foreignkey"
    )
    op.drop_column("fde_profiles", "capacity_verified_by_user_id")
    op.drop_column("fde_profiles", "capacity_evidence_sha256")
    op.drop_column("fde_profiles", "capacity_evidence_uri")
    op.drop_column("fde_profiles", "capacity_verified_at")
