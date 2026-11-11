"""F 线 T5：就近硬闸加固（不提权）——onsite_required 三态化。

ADR-011 §5-D ＋ 任务书 §4-T5／§12 动作 1：

- 旧形态：``delivery_packages.onsite_required`` = ``BOOLEAN NOT NULL DEFAULT
  false``，取值由 ``packages._derive_onsite_required(schedule)`` 按四个关键词
  （现场／到场／驻场／驻点）派生 ⇒ **方案文本漏写即同城硬闸整体失效**，
  只剩 ``geo_remote=10`` 的软权重。
- 新形态（三态）：
  - ``NULL`` ＝ **未设置** ⇒ 读侧兜底按「FDE 交付项目默认到场型」判 True；
  - ``True``  ＝ 显式到场型；
  - ``False`` ＝ **仅此一种**是纯远程型（须显式标记）。
  关键词派生降级为「字段为空时的兜底」，不再决定新建包的默认语义。

**存量回填规则（存量行为逐位零变更）**：本迁移把存量行的 ``NULL``/``false``
按**旧派生规则**（schedule 四关键词命中即 True，否则 False）重算回填——
存量远程型包**不会**被误加同城围栏，而新建包走新默认（到场型）。
换言之：**存量零变更、新建默认到场型**，两者在回填点处精确衔接。

**权重不动**（任务书 §12 动作 3）：``stage_b_weights`` 维持 40/30/20/10；
``geo_remote``／``sort_key_onsite``／``sort_key_remote`` 一字未改。
本迁移只改一列的可空性与取值语义，不动任何权重常量。

Backup hint: column-only change; downgrade restores NOT NULL + false default
and re-derives existing rows by the same keyword rule (round-trip safe).
"""
import sqlalchemy as sa
from alembic import op

revision = "a7c2f9e1b4d8"
down_revision = "e5c9f2a7d4b6"
branch_labels = None
depends_on = None

# 旧派生规则的四关键词（与 packages._ONSITE_KEYWORDS 同源，迁移侧独立复刻
# 以免导入业务模块导致迁移环境依赖漂移）。
_ONSITE_KEYWORDS = ("现场", "到场", "驻场", "驻点")


def _recompute() -> None:
    """按 schedule 四关键词重算 onsite_required（存量语义保持）。

    命中任一关键词 ⇒ True（到场型）；否则 ⇒ False（纯远程型）——与迁移前的
    ``_derive_onsite_required`` 判定逐位一致，故存量行行为零变更。
    """
    op.execute(
        """
        UPDATE delivery_packages AS p
        SET onsite_required = COALESCE(
            (
                SELECT bool_or(
                    s.schedule LIKE '%' || k.keyword || '%'
                )
                FROM project_solutions AS s
                CROSS JOIN (VALUES ('现场'), ('到场'), ('驻场'), ('驻点'))
                    AS k(keyword)
                WHERE s.id = p.solution_id
            ),
            false
        )
        """
    )


def upgrade() -> None:
    # ① 存量按旧派生规则回填（先于改可空：NOT NULL 列不接受 NULL 写入）。
    _recompute()
    # ② 列改可空 + 去默认值 ⇒ NULL 成为「未设置」的合法取值。
    op.alter_column(
        "delivery_packages",
        "onsite_required",
        existing_type=sa.Boolean(),
        nullable=True,
        server_default=None,
    )


def downgrade() -> None:
    # ① NULL 行按旧派生规则回填（恢复 NOT NULL 前必须无 NULL）。
    op.execute("UPDATE delivery_packages SET onsite_required = false WHERE onsite_required IS NULL")
    # ② 恢复 NOT NULL + false 默认。
    op.alter_column(
        "delivery_packages",
        "onsite_required",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )
