"""获客诊断 T-16 价格轮：转化费口径落值 pending_pricing → ratio_applied。

落地形（蔡工 2026-11-12 拍板④：转化费＝比例制——A 渠道报备缺省 20%、
B 认领转化缺省 10%，配置面可调）：

- ``lead_diagnostic_claims.fee_basis`` 的闭集由
  ``('none', 'pending_pricing')`` 换为 ``('none', 'ratio_applied')``——
  结构值换值（口径落定），不是加列：比例数值**只在配置面**
  （``Settings.diagnostics_fee_ratio_tier_a/b``，env
  ``FDE_DIAGNOSTICS_FEE_RATIO_TIER_A/B`` 可调），模型列**零比例零金额
  字段**（T-11 静态钉原样保留，本迁移不碰列名）。
- **零存量行论证**（本迁移无数据迁移的原因）：主部署诊断闸
  ``FDE_DIAGNOSTICS_ENABLED`` 默认关（404）期间零认领单落库；独立轻
  部署（fde-diag）库为全新库。两处部署的 ``pending_pricing`` 行数均为
  零 ⇒ 直接 drop+recreate CHECK 无需逐行改值。若未来在存量非零的库上
  回放本迁移，CHECK 重建会**如实失败**（fail-closed，不带错跑）。
- ``ratio_applied`` 语义＝「按平台配置比例计」：结算时点的比例读配置面
  现值（不冻结快照——冻结列会引入第二份比例数字，违反「比例只落结构
  不落数」红线）；结算政策由运营口径承载。

幂等：drop 约束→create 约束，各一次；downgrade 对称可逆（换回
``pending_pricing`` 闭集，同样依赖零存量行）。

Backup hint: 约束级变更（drop+create 同名约束）；零数据改写。
"""
from alembic import op

revision = "f2a7c4e9b6d3"
down_revision = "a3e8c2f6b9d4"
branch_labels = None
depends_on = None

_NEW_CHECK = "fee_basis IS NULL OR fee_basis IN ('none', 'ratio_applied')"
_OLD_CHECK = "fee_basis IS NULL OR fee_basis IN ('none', 'pending_pricing')"
_CHECK_NAME = "ck_lead_diagnostic_claims_fee_basis"


def upgrade() -> None:
    op.drop_constraint(_CHECK_NAME, "lead_diagnostic_claims", type_="check")
    op.create_check_constraint(_CHECK_NAME, "lead_diagnostic_claims", _NEW_CHECK)


def downgrade() -> None:
    op.drop_constraint(_CHECK_NAME, "lead_diagnostic_claims", type_="check")
    op.create_check_constraint(_CHECK_NAME, "lead_diagnostic_claims", _OLD_CHECK)
