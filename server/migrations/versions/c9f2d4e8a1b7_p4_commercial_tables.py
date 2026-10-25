"""p4_commercial_tables

P4 报价/收款/合同（设计 v0.3 §6，三表纯新增）：
  1. quotes——报价台账（承接《报价计算卡-v1.1》：输入=系数（初始假设待回校），
     输出=公式计算列；field_claims 存每个数字的 claim_status 四值；
     对外报价单不出现系数——HTML 草稿只出三档）
  2. payments——收款与催款（里程碑定义=seeds/payment_milestones.json 投影，
     溯源映射表 v1.3；状态不落库，received_at/invoice_no 现算；
     dunning D+7/15/30/60 读时现算；G8 stop 由门禁引擎联动打 settlement_reason）
  3. contracts——合同台账（只存指针与条款摘要，PDF 本体在 fdeops 文件系统）

Revision ID: c9f2d4e8a1b7
Revises: d7a3e8c5f1b9
Create Date: 2026-10-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c9f2d4e8a1b7'
down_revision: Union[str, Sequence[str], None] = 'd7a3e8c5f1b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 新表：quotes（报价台账，报价卡 v1.1 程序化）---
    op.create_table('quotes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('quote_key', sa.String(length=40), nullable=False),
    sa.Column('tier', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=10), server_default='draft', nullable=False),
    sa.Column('ideal_hours', sa.Numeric(7, 2), nullable=False),
    sa.Column('integration_factor', sa.Numeric(4, 2), nullable=False),
    sa.Column('data_factor', sa.Numeric(4, 2), nullable=False),
    sa.Column('compliance_factor', sa.Numeric(4, 2), nullable=False),
    sa.Column('buffer_factor', sa.Numeric(4, 2), nullable=False),
    sa.Column('hourly_rate', sa.Integer(), nullable=False),
    sa.Column('cash_cost', sa.Integer(), nullable=False),
    sa.Column('margin_factor', sa.Numeric(3, 2), nullable=False),
    sa.Column('b_layer_score', sa.Integer(), nullable=False),
    sa.Column('anchor_mode', sa.String(length=12), nullable=False),
    sa.Column('preset', sa.String(length=40), nullable=True),
    sa.Column('realistic_hours', sa.Numeric(8, 2), nullable=False),
    sa.Column('labor_cost', sa.Numeric(12, 2), nullable=False),
    sa.Column('total_cost', sa.Numeric(12, 2), nullable=False),
    sa.Column('formula_price', sa.Numeric(12, 2), nullable=False),
    sa.Column('b_layer_factor', sa.Numeric(4, 2), nullable=False),
    sa.Column('anchor_low', sa.Integer(), nullable=False),
    sa.Column('anchor_high', sa.Integer(), nullable=False),
    sa.Column('branch', sa.String(length=1), nullable=False),
    sa.Column('quote_low', sa.Numeric(12, 2), nullable=True),
    sa.Column('quote_high', sa.Numeric(12, 2), nullable=True),
    sa.Column('c_handling', sa.String(length=20), nullable=True),
    sa.Column('final_amount', sa.Numeric(12, 2), nullable=True),
    sa.Column('final_deviation_pct', sa.Numeric(7, 4), nullable=True),
    sa.Column('allowance_cap', sa.Numeric(12, 2), nullable=True),
    sa.Column('allowance_paid', sa.Numeric(12, 2), server_default='0', nullable=False),
    sa.Column('ticket_deal', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('ticket_note', sa.Text(), nullable=False),
    sa.Column('actual_hours', sa.Numeric(8, 2), nullable=True),
    sa.Column('deviation_pct', sa.Numeric(7, 4), nullable=True),
    sa.Column('deviation_reason', sa.Text(), nullable=False),
    sa.Column('calibrated_buffer_factor', sa.Numeric(4, 2), nullable=True),
    sa.Column('field_claims', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint("tier IN ('light', 'standard', 'flagship')", name='ck_quotes_tier'),
    sa.CheckConstraint("anchor_mode IN ('cold_start', 'steady')", name='ck_quotes_anchor_mode'),
    sa.CheckConstraint("status IN ('draft', 'finalized')", name='ck_quotes_status'),
    sa.CheckConstraint("b_layer_score >= 0 AND b_layer_score <= 10", name='ck_quotes_b_score'),
    sa.CheckConstraint("branch IN ('A', 'B', 'C')", name='ck_quotes_branch'),
    sa.CheckConstraint("c_handling IS NULL OR c_handling IN ('scope_cut', 'split_phases', 'external_collab', 'ticket_deal')", name='ck_quotes_c_handling'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'quote_key', name='uq_quotes_project_key')
    )
    op.create_index('ix_quotes_project_id', 'quotes', ['project_id'], unique=False)

    # --- 新表：payments（收款与催款，里程碑定义投影）---
    op.create_table('payments',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('milestone_key', sa.String(length=20), nullable=False),
    sa.Column('sow_type', sa.String(length=1), nullable=False),
    sa.Column('collects', sa.String(length=80), nullable=False),
    sa.Column('timing', sa.String(length=160), nullable=False),
    sa.Column('ratio', sa.Numeric(4, 2), nullable=True),
    sa.Column('amount', sa.Numeric(12, 2), nullable=False),
    sa.Column('received_amount', sa.Numeric(12, 2), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('received_at', sa.Date(), nullable=True),
    sa.Column('invoice_no', sa.String(length=60), nullable=True),
    sa.Column('settlement_reason', sa.String(length=20), nullable=True),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('source_uri', sa.String(length=500), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("sow_type IN ('a', 'b', 'c', 'd')", name='ck_payments_sow_type'),
    sa.CheckConstraint("settlement_reason IS NULL OR settlement_reason IN ('g8_stop')", name='ck_payments_settlement_reason'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'milestone_key', name='uq_payments_project_milestone')
    )
    op.create_index('ix_payments_project_id', 'payments', ['project_id'], unique=False)

    # --- 新表：contracts（合同台账，只存指针）---
    op.create_table('contracts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('sow_type', sa.String(length=1), nullable=False),
    sa.Column('signed_at', sa.Date(), nullable=True),
    sa.Column('payment_terms', sa.Text(), nullable=False),
    sa.Column('acceptance_window_days', sa.Integer(), nullable=False),
    sa.Column('termination_terms', sa.Text(), nullable=False),
    sa.Column('source_uri', sa.String(length=500), nullable=True),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint("sow_type IN ('a', 'b', 'c', 'd')", name='ck_contracts_sow_type'),
    sa.CheckConstraint("acceptance_window_days >= 1", name='ck_contracts_acceptance_window'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'sow_type', name='uq_contracts_project_sow')
    )
    op.create_index('ix_contracts_project_id', 'contracts', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_contracts_project_id', table_name='contracts')
    op.drop_table('contracts')
    op.drop_index('ix_payments_project_id', table_name='payments')
    op.drop_table('payments')
    op.drop_index('ix_quotes_project_id', table_name='quotes')
    op.drop_table('quotes')
