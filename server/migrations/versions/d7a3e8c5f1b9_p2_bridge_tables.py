"""p2_bridge_tables

P2 集成桥（设计 v0.3.4 §4）：
  1. bridge_engagements——真相层 engagement 的单向投影（openfde/fdeops 双轨，
     A4 出处指针按轨道分列 source_uri + content_hash）
  2. bridge_sync_runs——采集/重投影日志，payload 保留原始快照供手动重放

架构修订（v0.3.4）：openfde CLI 是宿主侧 Windows Node 工具（better-sqlite3
Win 二进制 + pnpm/tsx），Linux 容器内 subprocess 不到——采集器在宿主侧
（scripts/bridge-poll.mjs，计划任务 15 min），服务端只做校验/投影/orphan。

Revision ID: d7a3e8c5f1b9
Revises: b4e8c1a7d2f6
Create Date: 2026-10-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd7a3e8c5f1b9'
down_revision: Union[str, Sequence[str], None] = 'b4e8c1a7d2f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 新表：bridge_engagements（真相层投影，文件永远赢）---
    op.create_table('bridge_engagements',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('slug', sa.String(length=80), nullable=False),
    sa.Column('openfde_status', sa.JSON(), nullable=True),
    sa.Column('openfde_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('openfde_source_uri', sa.String(length=500), nullable=True),
    sa.Column('openfde_content_hash', sa.String(length=64), nullable=True),
    sa.Column('fdeops_state', sa.JSON(), nullable=True),
    sa.Column('fdeops_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('fdeops_source_uri', sa.String(length=500), nullable=True),
    sa.Column('fdeops_content_hash', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug', name='uq_bridge_engagements_slug')
    )

    # --- 新表：bridge_sync_runs（采集日志，payload 供重投影重放）---
    op.create_table('bridge_sync_runs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('trigger', sa.String(length=20), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ok', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('engagements_seen', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('summary', sa.JSON(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('payload', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("trigger IN ('poller', 'manual_reproject')", name='ck_bridge_sync_runs_trigger'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_bridge_sync_runs_started_at', 'bridge_sync_runs', ['started_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_bridge_sync_runs_started_at', table_name='bridge_sync_runs')
    op.drop_table('bridge_sync_runs')
    op.drop_table('bridge_engagements')
