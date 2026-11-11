"""获客诊断工具 T-11：认领单表（lead_diagnostic_claims）＋ 线索行加两列。

落地形（获客诊断工具实施任务书 §3 T-11：线索模型与认领闸）：

- **认领单**（新表）：一行 = 一份认领申请。**claimed ≠ accepted**（P-6）——
  ``status`` 闭集 pending/accepted/rejected/withdrawn，**未决申请不得带裁定
  字段**（CHECK 钉死：pending ⇒ 无 decided_at / 无档位 / 无台账号）。
- **认领 ≠ 转交付**：接受认领只改线索行的指针与档位，**不建项目、不写交付
  真相层**——线索表**零外键指向 projects**（沿 T-10a 隔离纪律）。
- **线索行加两列**：
  ``subject_fingerprint``（主体指纹 = sha256(规范化联系方式)，**明文不入库**；
  自认领判定用）＋ ``region_name``（R4 仅本区域认领的判定基准；可空＝线索
  未登记区域 ⇒ R4 认领 fail-closed）。
- **台账行**（``ledger_row`` JSON）：leads.md §一 **九字段 ＋ 线索号 ＋ 资料
  索引**的**代号化**内容——联系方式/姓名/企业真实名**一律不出现**。落账由宿主
  侧脚本写真相层文件，服务端**不碰真相层文件**。
- **比例不落数**（P-2）：``attribution_tier`` 只落 A/B/C 三档结构，
  ``fee_basis`` 只落 none/pending_pricing 结构——**没有任何比例字段**。

**零播种**：本表是员工认领动作的产物，无默认行。

Backup hint: additive only; downgrade drops the new table and the two columns.
"""
import sqlalchemy as sa
from alembic import op

revision = "d7e2f4a9c1b3"
down_revision = "c1d4e7f9a2b3"
branch_labels = None
depends_on = None


def _timestamp_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    # ── 线索行加两列（T-11 认领闸的判定基准）──
    op.add_column(
        "lead_diagnostic_sessions",
        sa.Column("subject_fingerprint", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "lead_diagnostic_sessions",
        sa.Column("region_name", sa.String(length=120), nullable=True),
    )
    op.create_check_constraint(
        "ck_lead_diagnostic_sessions_attribution_tier",
        "lead_diagnostic_sessions",
        "attribution_tier IS NULL OR attribution_tier IN ('A', 'B', 'C')",
    )
    op.create_check_constraint(
        "ck_lead_diagnostic_sessions_subject_fingerprint_len",
        "lead_diagnostic_sessions",
        "subject_fingerprint IS NULL OR char_length(subject_fingerprint) = 64",
    )

    op.create_table(
        "lead_diagnostic_claims",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("claimant_user_id", sa.String(length=36), nullable=False),
        sa.Column("claimant_kind", sa.String(length=20), nullable=False),
        sa.Column("region_name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attribution_tier", sa.String(length=4), nullable=True),
        sa.Column("fee_basis", sa.String(length=20), nullable=True),
        sa.Column("self_claim", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("self_claim_signals", sa.JSON(), nullable=True),
        sa.Column("subject_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("claimed_ip_hash", sa.String(length=64), nullable=True),
        sa.Column("ledger_date", sa.String(length=10), nullable=True),
        sa.Column("ledger_seq", sa.Integer(), nullable=True),
        sa.Column("ledger_line_no", sa.String(length=20), nullable=True),
        sa.Column("ledger_row", sa.JSON(), nullable=True),
        sa.Column("ledger_hash", sa.String(length=64), nullable=True),
        sa.Column("ledger_written_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(length=500), nullable=True),
        sa.Column("tier_override", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("note", sa.String(length=500), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["lead_diagnostic_sessions.id"],
            name="fk_lead_diagnostic_claims_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["claimant_user_id"],
            ["users.id"],
            name="fk_lead_diagnostic_claims_claimant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name="fk_lead_diagnostic_claims_decided_by",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ledger_date", "ledger_seq", name="uq_lead_diagnostic_claims_ledger_seq"
        ),
        sa.UniqueConstraint("ledger_line_no", name="uq_lead_diagnostic_claims_ledger_line_no"),
        sa.CheckConstraint(
            "claimant_kind IN ('r2_entrepreneur', 'r4_partner')",
            name="ck_lead_diagnostic_claims_claimant_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'withdrawn')",
            name="ck_lead_diagnostic_claims_status",
        ),
        sa.CheckConstraint(
            "attribution_tier IS NULL OR attribution_tier IN ('A', 'B', 'C')",
            name="ck_lead_diagnostic_claims_attribution_tier",
        ),
        sa.CheckConstraint(
            "fee_basis IS NULL OR fee_basis IN ('none', 'pending_pricing')",
            name="ck_lead_diagnostic_claims_fee_basis",
        ),
        sa.CheckConstraint(
            "claimant_kind <> 'r4_partner' OR region_name IS NOT NULL",
            name="ck_lead_diagnostic_claims_r4_region",
        ),
        sa.CheckConstraint(
            "status <> 'pending' OR (decided_at IS NULL AND attribution_tier IS NULL "
            "AND ledger_line_no IS NULL)",
            name="ck_lead_diagnostic_claims_pending_shape",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'withdrawn') OR (decided_at IS NOT NULL "
            "AND decided_by_user_id IS NOT NULL AND decision_note IS NOT NULL)",
            name="ck_lead_diagnostic_claims_decision_shape",
        ),
        sa.CheckConstraint(
            "status <> 'accepted' OR (ledger_line_no IS NOT NULL AND ledger_row IS NOT NULL)",
            name="ck_lead_diagnostic_claims_accepted_ledger",
        ),
        sa.CheckConstraint(
            "status = 'accepted' OR ledger_line_no IS NULL",
            name="ck_lead_diagnostic_claims_ledger_only_when_accepted",
        ),
        sa.CheckConstraint(
            "subject_fingerprint IS NULL OR char_length(subject_fingerprint) = 64",
            name="ck_lead_diagnostic_claims_subject_fingerprint_len",
        ),
        sa.CheckConstraint(
            "claimed_ip_hash IS NULL OR char_length(claimed_ip_hash) = 64",
            name="ck_lead_diagnostic_claims_ip_hash_len",
        ),
        sa.CheckConstraint(
            "ledger_hash IS NULL OR char_length(ledger_hash) = 64",
            name="ck_lead_diagnostic_claims_ledger_hash_len",
        ),
    )
    op.create_index(
        "ix_lead_diagnostic_claims_session",
        "lead_diagnostic_claims",
        ["session_id"],
    )
    op.create_index(
        "ix_lead_diagnostic_claims_claimant",
        "lead_diagnostic_claims",
        ["claimant_user_id"],
    )
    op.create_index(
        "ix_lead_diagnostic_claims_status",
        "lead_diagnostic_claims",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_lead_diagnostic_claims_status", table_name="lead_diagnostic_claims")
    op.drop_index("ix_lead_diagnostic_claims_claimant", table_name="lead_diagnostic_claims")
    op.drop_index("ix_lead_diagnostic_claims_session", table_name="lead_diagnostic_claims")
    op.drop_table("lead_diagnostic_claims")
    op.drop_constraint(
        "ck_lead_diagnostic_sessions_subject_fingerprint_len",
        "lead_diagnostic_sessions",
        type_="check",
    )
    op.drop_constraint(
        "ck_lead_diagnostic_sessions_attribution_tier",
        "lead_diagnostic_sessions",
        type_="check",
    )
    op.drop_column("lead_diagnostic_sessions", "region_name")
    op.drop_column("lead_diagnostic_sessions", "subject_fingerprint")
