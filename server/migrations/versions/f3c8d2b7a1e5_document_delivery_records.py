"""add document_delivery_records table

WP30/J3：交付审计专用表。D5 的交付审计此前只落通用 operation_events，
无法按「交付」维度检索。本表按「项目 + 交付时间」「版本」建索引，
可直接回答「客户拿到了哪一版、谁签发的、什么时候」。

表里只有指针与指纹（version_id + sha256 + actor），不含客户明文。

Backup hint: pure CREATE TABLE, no data written. Downgrade drops the table
(and its delivery history) — only run with explicit confirmation.
"""
from alembic import op
import sqlalchemy as sa


revision = "f3c8d2b7a1e5"
down_revision = "e5b8a1c9d3f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_delivery_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("delivery_key", sa.String(length=200), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("version_id", sa.String(length=36), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("actor_username", sa.String(length=120), nullable=False, server_default=""),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["project_documents.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="SET NULL"
        ),
        # 交付是历史事实：版本被删不应抹掉审计痕迹（指向置空，保留当时的
        # version_number / sha256 快照）。RESTRICT 会让「删版本」被审计挡住。
        sa.ForeignKeyConstraint(
            ["version_id"], ["project_document_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "delivery_key", name="uq_document_delivery_records_delivery_key"
        ),
    )
    op.create_index(
        "ix_document_delivery_records_project_delivered",
        "document_delivery_records",
        ["project_id", "delivered_at"],
    )
    op.create_index(
        "ix_document_delivery_records_version_id",
        "document_delivery_records",
        ["version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_delivery_records_version_id", table_name="document_delivery_records"
    )
    op.drop_index(
        "ix_document_delivery_records_project_delivered",
        table_name="document_delivery_records",
    )
    op.drop_table("document_delivery_records")
