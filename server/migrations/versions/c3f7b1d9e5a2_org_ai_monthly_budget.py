"""多客户 M4 批次 B：AI 预算按企业 org——``orgs.ai_monthly_token_budget`` 加列。

任务书 §7-M4「AI 预算闸从整实例单值改为按主体额度」（GAP-04 额度账承接）：

- ``orgs.ai_monthly_token_budget`` ``INTEGER NULL``——``NULL`` ＝ **未配置**，
  读侧回落实例值 ``settings.ai_monthly_token_budget``（现状语义零回归）；
  ``0`` ＝ 不限额（沿 E7 心智）；正数 ＝ 该 org 的月度 token 额度。
- 判定语义在 ``ai/auditing.py::subject_budget_exceeded``（单一权威点）：企业
  身份（``users.org_id`` 非空）按同 org 全员月度合计判 org 额度；平台身份
  （``org_id=NULL``，§11-8 语义不变）沿用实例值＋按 user 汇总（现状）。
- **零数值预写**（G 线纪律）：迁移只加列，不播种任何预算数值。

Backup hint: additive column-only change; downgrade drops the column
(round-trip safe, no data rewrite).
"""
import sqlalchemy as sa
from alembic import op

revision = "c3f7b1d9e5a2"
down_revision = "a7c2f9e1b4d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orgs",
        sa.Column("ai_monthly_token_budget", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orgs", "ai_monthly_token_budget")
