"""F 线 T1：五席位纵向分配明细表（dispatch_settlement_allocations）。

ADR-011 §5-A 选型 A（2026-11-10 拍板；OWNER 书面签字 2026-11-10，见
docs/commercialization/分账口径改造-书面签字待补页-2026-11-10.md）：

- 一结算 × 一席位一行；空缺席位**显式记 0 不省行**（ADR-011 §3.5 四条硬
  要求：显式 0＋平台吸收闭环＋原因码＋admin 人工确认＋事件留痕）。
- 原因码闭集 ``no_province_partner`` / ``self_sourced_self_delivered`` /
  ``no_sourcer``——唯一成文处 ``rules/five-seat-split-rules.md`` 机器可读块
  （T2 起 JSON↔常量↔迁移种子三方机器闸；本迁移零播种、不预写业务数值）。
- ``delivery_settlements`` **零加列**（ADR-003 §2.1 结构钉）：四总额列 =
  本表同事务派生的兼容镜像，服务层 ``allocate_five_seats`` 写入并断言
  Σ明细 = Σ旧四列 = 基数；绕层直写 409。
- ``(settlement_id, seat_key)`` 唯一：防同席位重复计提。

Backup hint: additive only; downgrade drops the single new table.
"""
import sqlalchemy as sa
from alembic import op

revision = "b7e4c1a9f3d5"
down_revision = "b7e4d1c9a3f2"  # 十一度插队改挂：T-10b b7e4d1c9a3f2 之后，保单头
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dispatch_settlement_allocations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("settlement_id", sa.String(length=36), nullable=False),
        sa.Column("seat_key", sa.String(length=12), nullable=False),
        sa.Column("payee_user_id", sa.String(length=36), nullable=True),
        sa.Column("shares_in_pool", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("reason_code", sa.String(length=40), nullable=True),
        sa.Column("rule_version_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dispatch_settlement_allocations"),
        sa.ForeignKeyConstraint(
            ["settlement_id"],
            ["delivery_settlements.id"],
            name="fk_dispatch_settlement_allocations_settlement",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["payee_user_id"],
            ["users.id"],
            name="fk_dispatch_settlement_allocations_payee",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rule_version_id"],
            ["dispatch_rule_versions.id"],
            name="fk_dispatch_settlement_allocations_rule_version",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "seat_key IN ('platform', 'lead', 'delivery', 'county', 'province')",
            name="ck_dispatch_settlement_allocations_seat_key",
        ),
        sa.CheckConstraint(
            "status IN ('paid', 'vacant')",
            name="ck_dispatch_settlement_allocations_status",
        ),
        sa.CheckConstraint(
            "status != 'vacant' OR (amount = 0 AND reason_code IS NOT NULL)",
            name="ck_dispatch_settlement_allocations_vacant_shape",
        ),
        sa.CheckConstraint(
            "status != 'paid' OR reason_code IS NULL",
            name="ck_dispatch_settlement_allocations_paid_shape",
        ),
        sa.CheckConstraint(
            "status != 'vacant' OR payee_user_id IS NULL",
            name="ck_dispatch_settlement_allocations_vacant_payee_exclusive",
        ),
        sa.CheckConstraint(
            "status != 'paid' OR payee_user_id IS NOT NULL OR seat_key = 'platform'",
            name="ck_dispatch_settlement_allocations_paid_payee_shape",
        ),
        sa.CheckConstraint(
            "seat_key != 'platform' OR payee_user_id IS NULL",
            name="ck_dispatch_settlement_allocations_platform_payee_null",
        ),
        sa.CheckConstraint(
            "(seat_key = 'platform' AND shares_in_pool IS NULL)"
            " OR (seat_key != 'platform' AND shares_in_pool IS NOT NULL)",
            name="ck_dispatch_settlement_allocations_platform_shares_null",
        ),
        sa.CheckConstraint(
            "shares_in_pool IS NULL OR shares_in_pool BETWEEN 0 AND 100",
            name="ck_dispatch_settlement_allocations_shares_range",
        ),
        sa.CheckConstraint(
            "amount >= 0",
            name="ck_dispatch_settlement_allocations_amount_nonneg",
        ),
        sa.UniqueConstraint(
            "settlement_id",
            "seat_key",
            name="uq_dispatch_settlement_allocations_settlement_seat",
        ),
    )


def downgrade() -> None:
    op.drop_table("dispatch_settlement_allocations")
