"""p1_sop_schema

P1 schema 改造（设计 v0.3.2 §3.1/§3.2/§5.0）：
  1. projects 删 4 明文列（enterprise_name/contact_name/contact_phone/address），
     加 enterprise_code / openfde_engagement / fdeops_workspace / sop_phase / business_line
  2. project_tasks 加 sop_node / gate / evidence_uri / evidence_hash
  3. 新表 sop_nodes（16 条定义，种子灌入）与 gates（门禁状态机，P3 驱动）

前置条件：空库（P0 零数据迁移策略，fork 无生产数据），故 NOT NULL 新列不加过渡默认值。

Revision ID: b4e8c1a7d2f6
Revises: ebb003a5c3a8
Create Date: 2026-10-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b4e8c1a7d2f6'
down_revision: Union[str, Sequence[str], None] = 'ebb003a5c3a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DROPPED_ENTERPRISE_COLUMNS = (
    'enterprise_name',
    'enterprise_contact_name',
    'enterprise_contact_phone',
    'enterprise_address',
)


def upgrade() -> None:
    # --- 新表：sop_nodes（先建，projects.sop_phase / project_tasks.sop_node 的 FK 指向它）---
    op.create_table('sop_nodes',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('node_key', sa.String(length=20), nullable=False),
    sa.Column('name', sa.String(length=160), nullable=False),
    sa.Column('segment', sa.String(length=20), nullable=False),
    sa.Column('gate_key', sa.String(length=10), nullable=True),
    sa.Column('gate_note', sa.String(length=120), nullable=True),
    # TRIGGER 是 PG 保留字，SQLAlchemy 会自动加引号
    sa.Column('trigger', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('human_action', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('ai_action', sa.Text(), nullable=True),
    sa.Column('artifact', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('evidence_location', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('record_track', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('signer_role', sa.String(length=120), nullable=True),
    sa.Column('fail_exit', sa.Text(), server_default=sa.text("''"), nullable=False),
    sa.Column('next_node', sa.String(length=100), server_default=sa.text("''"), nullable=False),
    sa.Column('next_node_keys', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('contract_payment_auth', sa.Text(), nullable=True),
    sa.Column('source_uri', sa.String(length=500), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('human_ai_source_uri', sa.String(length=500), nullable=True),
    sa.Column('human_ai_content_hash', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("segment IN ('售前段', '交付段', '交付后段', '横切线')", name='ck_sop_nodes_segment'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('node_key', name='uq_sop_nodes_node_key')
    )

    # --- 新表：gates（门禁状态机，P3 驱动；P1 建表占位）---
    op.create_table('gates',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.String(length=36), nullable=False),
    sa.Column('gate_key', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
    sa.Column('evidence_checklist', sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('evidence_uri', sa.String(length=500), nullable=True),
    sa.Column('evidence_hash', sa.String(length=64), nullable=True),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision', sa.String(length=10), nullable=True),
    sa.Column('signer_role', sa.String(length=120), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default=sa.text('1'), nullable=False),
    sa.CheckConstraint("status IN ('pending', 'evidence', 'passed', 'conditional_pass', 'failed')", name='ck_gates_status'),
    sa.CheckConstraint("decision IS NULL OR decision IN ('proceed', 'pivot', 'stop')", name='ck_gates_decision'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'gate_key', name='uq_gates_project_gate')
    )
    op.create_index('ix_gates_project_id', 'gates', ['project_id'], unique=False)

    # --- projects：代号化（A2 红线）---
    op.add_column('projects', sa.Column('enterprise_code', sa.String(length=80), nullable=False))
    op.add_column('projects', sa.Column('openfde_engagement', sa.String(length=100), nullable=True))
    op.add_column('projects', sa.Column('fdeops_workspace', sa.String(length=160), nullable=True))
    # §1 分工铁律：G3 之后才在 workbench 立项 → 默认 S3（深度诊断）
    op.add_column('projects', sa.Column('sop_phase', sa.String(length=20), server_default='S3', nullable=False))
    op.add_column('projects', sa.Column('business_line', sa.String(length=20), server_default='FDE', nullable=False))
    op.create_check_constraint('ck_projects_business_line', 'projects', "business_line IN ('FDE')")
    op.create_unique_constraint('uq_projects_enterprise_code', 'projects', ['enterprise_code'])
    op.create_foreign_key(
        'fk_projects_sop_phase_sop_nodes', 'projects', 'sop_nodes',
        ['sop_phase'], ['node_key'], ondelete='RESTRICT',
    )
    for column in DROPPED_ENTERPRISE_COLUMNS:
        op.drop_column('projects', column)

    # --- project_tasks：SOP 挂点与证据出处指针（A4）---
    op.add_column('project_tasks', sa.Column('sop_node', sa.String(length=20), nullable=True))
    op.add_column('project_tasks', sa.Column('gate', sa.String(length=10), nullable=True))
    op.add_column('project_tasks', sa.Column('evidence_uri', sa.String(length=500), nullable=True))
    op.add_column('project_tasks', sa.Column('evidence_hash', sa.String(length=64), nullable=True))
    op.create_foreign_key(
        'fk_project_tasks_sop_node_sop_nodes', 'project_tasks', 'sop_nodes',
        ['sop_node'], ['node_key'], ondelete='RESTRICT',
    )


def downgrade() -> None:
    op.drop_constraint('fk_project_tasks_sop_node_sop_nodes', 'project_tasks', type_='foreignkey')
    op.drop_column('project_tasks', 'evidence_hash')
    op.drop_column('project_tasks', 'evidence_uri')
    op.drop_column('project_tasks', 'gate')
    op.drop_column('project_tasks', 'sop_node')

    # 还原 4 明文列（默认空串以满足 NOT NULL；仅用于降级回滚，不代表鼓励明文）
    op.add_column('projects', sa.Column('enterprise_name', sa.String(length=160), server_default=sa.text("''"), nullable=False))
    op.add_column('projects', sa.Column('enterprise_contact_name', sa.String(length=120), server_default=sa.text("''"), nullable=False))
    op.add_column('projects', sa.Column('enterprise_contact_phone', sa.String(length=60), server_default=sa.text("''"), nullable=False))
    op.add_column('projects', sa.Column('enterprise_address', sa.String(length=255), server_default=sa.text("''"), nullable=False))

    op.drop_constraint('fk_projects_sop_phase_sop_nodes', 'projects', type_='foreignkey')
    op.drop_constraint('uq_projects_enterprise_code', 'projects', type_='unique')
    op.drop_constraint('ck_projects_business_line', 'projects', type_='check')
    op.drop_column('projects', 'business_line')
    op.drop_column('projects', 'sop_phase')
    op.drop_column('projects', 'fdeops_workspace')
    op.drop_column('projects', 'openfde_engagement')
    op.drop_column('projects', 'enterprise_code')

    op.drop_index('ix_gates_project_id', table_name='gates')
    op.drop_table('gates')
    op.drop_table('sop_nodes')
