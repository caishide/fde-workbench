"""V3.3 M5-WP2 唯一 DDL 迁移：S-13 引用列 + Gate 评估回执 + 验收契约 + Glossary 晋升锚点。

链位：接 e1a9d4c6a9f1 之前的 e1a9d4c7b2f8（M4 D27 快照列）之后，append-only 单链。
WP2 全部 DDL 变更收口本文件（工作令 WP2 防冲突铁律 2：迁移唯一收口）。

additive-only 五件：
1. ``project_evidence`` +5 可空引用列（S-13 命名对齐：ontology_id /
   pinned_version_id / object_ref_id / action_request_id / logic_eval_digest）
   + pinned_version 索引——本体引用只作语义增强锚点，严禁替代原始文件指纹
   （唯一键 (project_id, source_uri, content_sha256) 原样保留，零互踩）；
   跨库无外键，归属强验由服务层执行（org 绑定版本在 evidence 服务面校验）。
2. 新表 ``gate_evaluation_receipts``（D29）：Gate 求值瞬间固化的不可变评估回执
   （输入快照哈希 + 当时熔断降级态 + D31 处置闭环判定）——历史重放只验回执，
   免疫实时网络抖动；Agent 与 ontology-service 无权改写（S-16 写通道不开放）。
3. 新表 ``acceptance_contracts``（D29）：结构化验收契约项（输入清单、量化规则
   引用、异人判定角色 acceptor、争议响应 SLA 默认 72h）。
4. ``ontology_terms`` + promoted_readonly/promoted_at 锚点列（改进单 4 单向
   晋升流：晋升后置只读投影；本迁移只落锚点，晋升逻辑归 WP3 独立模块）。
5. ``gates`` + ontology_dependency 可空列（S-16 内层等级的 per-project 持久
   锚点；NULL=用模板默认；下调变更走 S-12 Owner 异人审批锁后由服务层落值）。

Backup hint: additive only; downgrade drops the two tables and four column groups.
"""
import sqlalchemy as sa
from alembic import op

revision = "b2e8d4c6a9f1"
down_revision = "e1a9d4c7b2f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_evidence",
        sa.Column("ontology_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "project_evidence",
        sa.Column("pinned_version_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "project_evidence",
        sa.Column("object_ref_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "project_evidence",
        sa.Column("action_request_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "project_evidence",
        sa.Column("logic_eval_digest", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "ck_project_evidence_logic_digest_len",
        "project_evidence",
        "logic_eval_digest IS NULL OR char_length(logic_eval_digest) = 64",
    )
    op.create_index(
        "ix_project_evidence_pinned_version",
        "project_evidence",
        ["pinned_version_id"],
    )

    # 主线 PG 惯例（orgs 基线 a5e9c3f1b7d4 同款）：server_default now()；
    op.create_table(
        "gate_evaluation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gate_key", sa.String(10), nullable=False),
        sa.Column("ontology_id", sa.String(36), nullable=False),
        sa.Column("pinned_version_id", sa.String(36), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("domain_schema_sha256", sa.String(64), nullable=True),
        sa.Column("site_binding_sha256", sa.String(64), nullable=True),
        sa.Column("breaker_state", sa.String(16), nullable=False, server_default="closed"),
        sa.Column("disposition_closed", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("summary_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("gate_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "breaker_state IN ('closed', 'open', 'half_open')",
            name="ck_gate_evaluation_receipts_breaker_state",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_gate_evaluation_receipts_project_gate",
        "gate_evaluation_receipts",
        ["project_id", "gate_key"],
    )
    op.create_index(
        "ix_gate_evaluation_receipts_pinned_version",
        "gate_evaluation_receipts",
        ["pinned_version_id"],
    )

    op.create_table(
        "acceptance_contracts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gate_key", sa.String(10), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("items_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("acceptor_user_id", sa.String(36), nullable=True),
        sa.Column("sla_hours", sa.Integer(), nullable=False, server_default="72"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_by_user_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'superseded')",
            name="ck_acceptance_contracts_status",
        ),
        sa.CheckConstraint("sla_hours > 0", name="ck_acceptance_contracts_sla_positive"),
        sa.ForeignKeyConstraint(
            ["acceptor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_acceptance_contracts_project_status",
        "acceptance_contracts",
        ["project_id", "status"],
    )

    op.add_column(
        "ontology_terms",
        sa.Column(
            "promoted_readonly",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "ontology_terms",
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "gates",
        sa.Column("ontology_dependency", sa.String(12), nullable=True),
    )
    op.create_check_constraint(
        "ck_gates_ontology_dependency",
        "gates",
        "ontology_dependency IS NULL OR "
        "ontology_dependency IN ('required', 'optional', 'none')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_gates_ontology_dependency", "gates", type_="check")
    op.drop_column("gates", "ontology_dependency")
    op.drop_column("ontology_terms", "promoted_at")
    op.drop_column("ontology_terms", "promoted_readonly")
    op.drop_table("acceptance_contracts")
    op.drop_table("gate_evaluation_receipts")
    op.drop_index("ix_project_evidence_pinned_version", table_name="project_evidence")
    op.drop_constraint(
        "ck_project_evidence_logic_digest_len", "project_evidence", type_="check"
    )
    op.drop_column("project_evidence", "logic_eval_digest")
    op.drop_column("project_evidence", "action_request_id")
    op.drop_column("project_evidence", "object_ref_id")
    op.drop_column("project_evidence", "pinned_version_id")
    op.drop_column("project_evidence", "ontology_id")
