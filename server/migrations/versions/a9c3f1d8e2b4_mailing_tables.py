"""add mailing_sends / mailing_events tables

WP-E SES 发信模块预建（goal-r3 G9）：发送台账 + SES/SNS 反馈事件表。
模块默认关闭（FDE_SES_ENABLED!=true），表建好后无任何行为影响；
SES 生产批复下来改配置即启用。

两表都是运维事实：不挂项目/用户外键（回调可能在一切业务行清理后到达）；
幂等由唯一键承载（sends.idempotency_key / events.event_key，SNS 是
at-least-once 投递）。只落地址 + 事件分类 + 通知 sha256 指纹，不落通知原文。

Backup hint: pure CREATE TABLE, no data written. Downgrade drops both tables
(and the send/feedback history) — only run with explicit confirmation.
"""
from alembic import op
import sqlalchemy as sa


revision = "a9c3f1d8e2b4"
down_revision = "f3c8d2b7a1e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mailing_sends",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("message_id", sa.String(length=200), nullable=False),
        sa.Column("sender", sa.String(length=320), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "sent_at",
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key", name="uq_mailing_sends_idempotency_key"
        ),
    )
    op.create_index(
        "ix_mailing_sends_message_id", "mailing_sends", ["message_id"]
    )
    op.create_index("ix_mailing_sends_sent_at", "mailing_sends", ["sent_at"])

    op.create_table(
        "mailing_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_key", sa.String(length=400), nullable=False),
        sa.Column("message_id", sa.String(length=200), nullable=False),
        sa.Column("notification_type", sa.String(length=40), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("feedback_type", sa.String(length=60), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", name="uq_mailing_events_event_key"),
    )
    op.create_index(
        "ix_mailing_events_recipient_type",
        "mailing_events",
        ["recipient", "notification_type"],
    )
    op.create_index(
        "ix_mailing_events_message_id", "mailing_events", ["message_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_mailing_events_message_id", table_name="mailing_events")
    op.drop_index(
        "ix_mailing_events_recipient_type", table_name="mailing_events"
    )
    op.drop_table("mailing_events")
    op.drop_index("ix_mailing_sends_sent_at", table_name="mailing_sends")
    op.drop_index("ix_mailing_sends_message_id", table_name="mailing_sends")
    op.drop_table("mailing_sends")
