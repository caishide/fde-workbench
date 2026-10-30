"""WP-E SES 发信事实表（goal-r3 G9 预建）。

两张表都是运维事实，不挂项目/用户外键——SES 回调可能在发送行清理后到达，
事实一旦发生就独立留存（与 document_delivery_records 的「历史事实」口径一致）：

- ``mailing_sends``：发送台账。幂等键唯一（调用方业务键），SES MessageId
  发出后回填；每日限额按 sent_at 汇总。
- ``mailing_events``：SES/SNS 反馈事件（bounce/complaint/delivery/throttle/
  订阅确认）。``event_key`` 唯一承载幂等——SNS 是 at-least-once 投递，
  同一通知重放不产生第二条记录。

隐私口径：本表只落地址与事件分类 + 原始通知的 sha256 指纹，不落通知原文
（退信诊断里可能带客户侧邮件内容）。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from fde_api.auth.models import UTC_TIMESTAMP_SQL, UTCDateTime
from fde_api.workbench.models import Base, TimestampMixin, new_uuid

# notification_type 取值：bounce / complaint / delivery / throttle /
# subscription_confirmed / send_failed。bounce 与 complaint 使地址进抑制
# （由 service 查询判定，见 mailing/service.py::_recipient_suppressed）。
NOTIFICATION_BOUNCE = "bounce"
NOTIFICATION_COMPLAINT = "complaint"
NOTIFICATION_DELIVERY = "delivery"
NOTIFICATION_THROTTLE = "throttle"
NOTIFICATION_SUBSCRIPTION = "subscription_confirmed"
NOTIFICATION_SEND_FAILED = "send_failed"

SUPPRESSING_TYPES = (NOTIFICATION_BOUNCE, NOTIFICATION_COMPLAINT)


class MailingSend(Base, TimestampMixin):
    """一次被 SES 接受的发送（台账行）。"""

    __tablename__ = "mailing_sends"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_mailing_sends_idempotency_key"),
        Index("ix_mailing_sends_message_id", "message_id"),
        Index("ix_mailing_sends_sent_at", "sent_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # 幂等键：调用方业务键（如 预调研通知:{project_id}:{version_id}）。重试=同键
    # 新 attempt，键不变；同键二次请求 = drop_duplicate。
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    # SES 返回的 MessageId；发出前为空串（throttle/失败不建行）。
    message_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    sender: Mapped[str] = mapped_column(String(320), nullable=False)
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    # 只记 SES 接受（sent）；失败/throttle 走 mailing_events，不占用发送台账。
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="sent")
    sent_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=UTC_TIMESTAMP_SQL
    )


class MailingEvent(Base, TimestampMixin):
    """一条 SES/SNS 反馈事件（幂等：event_key 唯一）。"""

    __tablename__ = "mailing_events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_mailing_events_event_key"),
        Index("ix_mailing_events_recipient_type", "recipient", "notification_type"),
        Index("ix_mailing_events_message_id", "message_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # 幂等键：SNS 通知用 {message_id}:{notification_type}:{recipient}；
    # 本地事件（throttle/发送失败/订阅确认）由 service 拼装（含 attempt 等维度）。
    event_key: Mapped[str] = mapped_column(String(400), nullable=False)
    message_id: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    notification_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # 单收件人事件落地址；信封级事件（订阅确认/整信失败）为空串。
    recipient: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    # 分类细分：bounceSubType / complaintFeedbackType / throttle / send 失败码等。
    feedback_type: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    # 原始 SNS Message 的 sha256 指纹（不落原文）。
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    occurred_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
