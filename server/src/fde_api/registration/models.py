"""多客户 M2：注册生命周期表 ``user_registrations``（ADR-M4）。

每个自助注册账号一行（user_id 主键，账号在注册事务里同时建）：登记入口、
申报材料（**只收指针 + sha256 指纹**——证据原件永不入库，AGENTS 红线）、
邮箱验证令牌指纹与审核留痕。账号生命周期状态机在 ``users.registration_state``
（ADR-M4 §1），本表只承载注册 intake 与审核簿记，不复制状态。

只依赖 ``auth.models``（Base 所在地）——单向导入，不产生环。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import JSON

from fde_api.auth.models import (
    Base,
    CURRENT_TIMESTAMP_SQL,
    UTC_TIMESTAMP_SQL,
    UTCDateTime,
    UTCTimestamp,
)

ENTRY_ENTERPRISE = "enterprise"
ENTRY_FOUNDER = "founder"
ENTRY_DELIVERER = "deliverer"
ENTRY_PARTNER = "partner"
# 四入口闭集（ADR-M4 §1）。**区域服务商排在最后**（sec 评审「入口默认置后」；
# /registrations/entries 读面按此序出货）。申请≠售卖：售卖流由 G5
# regional_sale_gate 默认关兜底。
ENTRY_TYPES: tuple[str, ...] = (
    ENTRY_ENTERPRISE,
    ENTRY_FOUNDER,
    ENTRY_DELIVERER,
    ENTRY_PARTNER,
)

REVIEW_DECISION_APPROVE = "approve"
REVIEW_DECISION_REJECT = "reject"
REVIEW_DECISIONS = frozenset({REVIEW_DECISION_APPROVE, REVIEW_DECISION_REJECT})


def new_registration_id() -> str:
    return str(uuid4())


class UserRegistration(Base):
    __tablename__ = "user_registrations"
    __table_args__ = (
        CheckConstraint(
            "entry IN ('enterprise', 'founder', 'deliverer', 'partner')",
            name="ck_user_registrations_entry",
        ),
        # 令牌指纹＝64 位小写 hex（诊断匿名令牌同形态）；明文只出现在邮件里。
        CheckConstraint(
            "token_sha256 IS NULL OR char_length(token_sha256) = 64",
            name="ck_user_registrations_token_sha256",
        ),
        # 一次性令牌：重发即轮换（旧行被覆写 ⇒ 旧链接失效）；指纹唯一防碰撞。
        UniqueConstraint("token_sha256", name="uq_user_registrations_token_sha256"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_registration_id)
    # 一账号一行：账号在注册事务里同时创建（RESTRICT＝账号不级联删）。
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    entry: Mapped[str] = mapped_column(String(16), nullable=False)
    # 入口申报材料（JSON，形状按入口文档化并逐入口校验）：
    #   deliverer → {"materials": [{kind?, source_uri, sha256}, …]}（R 分层申请，
    #               GAP-01 证据链口径，指针+指纹）
    #   partner   → {"org_name": …, "region_name": …}（机构字段；个人主体拍板，
    #               ADR-M2 §6-2——不落 orgs 行）
    #   enterprise/founder → NULL
    materials_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # 邮箱验证令牌：sha256 指纹入库 + 有效期 + 一次性消费戳。可空＝尚未签发
    # （注册事务里必然随行签发；列可空只为 downgrade 形状完整）。
    token_sha256: Mapped[str | None] = mapped_column(String(64))
    token_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    token_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    token_consumed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # 审核留痕（review 动作落；approve/reject 各一次，reviewed 后状态终判）。
    reviewed_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    review_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=UTC_TIMESTAMP_SQL
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCTimestamp(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_SQL,
    )

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if self.id is None:
            self.id = new_registration_id()
