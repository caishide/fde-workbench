"""诊断域数据模型：``lead_diagnostic_sessions``（获客线索行）。

**与项目的隔离**（本域最关键的一条结构纪律）：

- **零外键指向 ``projects``**——线索 ≠ 项目，沿 transcripts 草稿区同款隔离手法
  （``test_diagnostics_mvp`` 用 metadata 扫描钉死「零外键指向 projects」）。
- **认领 = 显式转化动作**（T-11）：``claimed_by_user_id`` 只是指针，认领本身
  **不自动写交付真相层**；转正式交付时另走 presurvey 项目流程。
- ``source_type`` / ``channel_ref`` / ``claim_window_*`` 只落**结构**不落数
  （P-2：三档归因比例挂账到价格轮；比例属 G3 收入科目层，与四席位交付分成
  分层不混算）。

**匿名面**：``anonymous_token`` 的**明文不入库**——库里只有 sha256 指纹，
客户端持有明文；库泄漏不等于会话被接管（沿 share token 同款做法）。

**红线条码化**：本表存的是企业**自愿自填**的线索数据（有明示同意 + 隐私政策
+ 留存期），与交付真相层资料（扫描件/凭证）纪律不同；正文字段同样走脱敏管线。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fde_api.auth.models import UTCDateTime
from fde_api.workbench.models import Base, TimestampMixin, new_uuid

# 状态机：draft → submitted → report_ready → claimed | expired
# T-10a 只落 draft/submitted（测算卡与问卷答案）；report_ready/claimed 由
# T-10b（AI 报告）与 T-11（认领）推进。
SESSION_STATUSES = (
    "draft",
    "submitted",
    "report_ready",
    "claimed",
    "expired",
)

# 三档归因的**结构**（P-2）：direct=平台直达 / channel=内容与活动渠道 /
# partner=区域合作商专属链接。比例不落数。
SOURCE_TYPES = ("direct", "channel", "partner")

# 认领窗口（P-2：90 天认领窗口制，日期在 T-11 落）
CLAIM_WINDOW_DAYS = 90

# 线索留存期（个保法：留存期 + 删除请求通道）
SESSION_RETENTION_DAYS = 30


class LeadDiagnosticSession(Base, TimestampMixin):
    """一次免注册诊断会话。

    一行 = 一次匿名诊断尝试。``answers`` 存问卷答案（代号化后），
    ``assessment`` 存首屏政策补贴测算卡（纯规则结果），``report`` 存 AI 报告
    （T-10b 落），``lead_contact`` 存留资信息（可空——摘要免注册可见）。
    """

    __tablename__ = "lead_diagnostic_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'submitted', 'report_ready', 'claimed', 'expired')",
            name="ck_lead_diagnostic_sessions_status",
        ),
        CheckConstraint(
            "source_type IN ('direct', 'channel', 'partner')",
            name="ck_lead_diagnostic_sessions_source_type",
        ),
        CheckConstraint(
            "char_length(token_sha256) = 64",
            name="ck_lead_diagnostic_sessions_token_sha_len",
        ),
        CheckConstraint(
            "char_length(created_ip_hash) = 64",
            name="ck_lead_diagnostic_sessions_ip_hash_len",
        ),
        # 指纹唯一：同一个匿名令牌只对应一行（令牌碰撞或重放都归一行）
        Index("ux_lead_diagnostic_sessions_token", "token_sha256", unique=True),
        # 分享指纹：可空（未生成分享链接时无值），非空时唯一 + 64 位
        Index(
            "ux_lead_diagnostic_sessions_share_token",
            "share_token_sha256",
            unique=True,
        ),
        CheckConstraint(
            "share_token_sha256 IS NULL OR char_length(share_token_sha256) = 64",
            name="ck_lead_diagnostic_sessions_share_token_len",
        ),
        # 认领窗口的到期日必填（认领时限是机制的一部分，不能留空）
        CheckConstraint(
            "claim_window_expires_at IS NOT NULL",
            name="ck_lead_diagnostic_sessions_claim_window",
        ),
        Index("ix_lead_diagnostic_sessions_status_created", "status", "created_at"),
        Index("ix_lead_diagnostic_sessions_source", "source_type", "channel_ref"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # 匿名令牌**只存指纹**（明文在客户端；库泄漏不等于会话被接管）
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    # 问卷答案（键为槽位键）；首屏 5 题与续填槽位分开存，便于「已答/未答」判定
    answers: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # 首屏测算卡结果（纯规则；R-1：定性档位，无分数）
    assessment: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # AI 报告（T-10b；三层 + 政策层；生成完成前恒为 NULL）
    report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # 报告生成请求时刻（异步：受理 ≠ 就绪；用于区分「未请求」与「生成中」）
    report_requested_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # 分享令牌**只存指纹**（明文只在生成响应里返回一次）
    # ——分享页是**只读**面（无写权限），故令牌可入 URL；会话令牌是写权限凭证，
    # 只走请求头。两者权限域不同，指纹域也分开（不同域分隔前缀）。
    share_token_sha256: Mapped[str | None] = mapped_column(String(64))
    # 留资信息（可空——摘要免注册即时可见）
    lead_contact: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # 三档归因结构（P-2：比例不落数）
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="direct", server_default="direct")
    channel_ref: Mapped[str | None] = mapped_column(String(80))
    # 来源 IP 的**稳定假名**（sha256(ip + 密钥，域分隔）——不是明文 IP）
    created_ip_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # 认领窗口到期（P-2：90 天）
    claim_window_expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    # 留存期到期（个保法：留存期 + 删除请求通道）
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    report_ready_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    claimed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # 认领人（指针；认领须平台接受——P-6：claimed ≠ accepted）
    claimed_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # 认领档位（P-2 三档：A 渠道报备 / B 认领转化 / C 平台留存；比例不落数）
    attribution_tier: Mapped[str | None] = mapped_column(String(20))
    # 失败原因（异步生成失败时留痕；不吞错）
    failure_code: Mapped[str | None] = mapped_column(String(60))
    failure_message: Mapped[str | None] = mapped_column(Text)
