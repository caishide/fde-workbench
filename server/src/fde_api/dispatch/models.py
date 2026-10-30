"""dispatch 模型：交付包派单态 + 派单 offer 留痕（设计 §2/§4/§6/§8.2）。

goal-r1（P0-6）只落 §8.2 DDL 级约束与 OperationEvent 目标注册；
发布/快照冻结（§2.3）、匹配算法（§4）、offer 服务（§6）随 P0-1/P1-1/P1-2
后续轮次进同一包（§8.6），不在本文件预埋半成品逻辑。

字段来源：设计 §2.2 映射表「新增」行 + §8.2 约束清单 + §9.2 字段白名单引用。
席位口径：本表四席位是执行席位 seat_lead/delivery/consult/qa（§2.4「包 × 角色」
的合同事实），与 delivery_settlements 的商务四席位 platform/region/city/delivery
（§7.2）不同名不同义，落库不得混用。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fde_api.auth.models import UTCDateTime
from fde_api.workbench.models import Base, TimestampMixin, VersionedMixin, new_uuid


class DeliveryPackage(Base, TimestampMixin):
    """交付包派单态（§2.1：方案正文留在 project_solutions，本表只存派单态）。"""

    __tablename__ = "delivery_packages"
    __table_args__ = (
        UniqueConstraint("package_code", name="uq_delivery_packages_package_code"),
        # §2.3 规则 3：版本对 = (project_id, dispatch_round)
        UniqueConstraint(
            "project_id", "dispatch_round", name="uq_delivery_packages_project_round"
        ),
        CheckConstraint(
            "dispatch_mode IN ('assign', 'claim')",
            name="ck_delivery_packages_dispatch_mode",
        ),
        CheckConstraint(
            "dispatch_status IN ('draft', 'published', 'offered', 'assigned', "
            "'accepted', 'rejected', 'expired', 'withdrawn')",
            name="ck_delivery_packages_dispatch_status",
        ),
        # §4.7 扩圈序列 25→50→100→全城；0 = 全城哨兵值（§8.2 注释即契约）
        CheckConstraint(
            "redispatch_radius_km IN (25, 50, 100, 0)",
            name="ck_delivery_packages_redispatch_radius",
        ),
        CheckConstraint(
            "sow_type IS NULL OR sow_type IN ('a', 'b', 'c', 'd')",
            name="ck_delivery_packages_sow_type",
        ),
        CheckConstraint(
            "required_level IS NULL OR required_level IN ('L1', 'L2', 'L3', 'L4')",
            name="ck_delivery_packages_required_level",
        ),
        # §6.4 开闸统计口径按 published 包数计数，状态列单查
        Index("ix_delivery_packages_status", "dispatch_status"),
    )

    # §2.2：package_id 直接引用 ProjectSolution.id（不另造 uuid），solution_id 再挂 FK
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    solution_id: Mapped[str] = mapped_column(
        ForeignKey("project_solutions.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    # 展示码（§9.2 交付包字段白名单第 1 项）；生成规则随发布服务（P0-1）落位
    package_code: Mapped[str] = mapped_column(String(20), nullable=False)
    quote_id: Mapped[str | None] = mapped_column(ForeignKey("quotes.id", ondelete="RESTRICT"))
    sow_type: Mapped[str | None] = mapped_column(String(1))
    # §2.3：发布时计算一次即冻结；撤回→改→重发才是新哈希 + dispatch_round 递增
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    dispatch_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, default="assign", server_default="assign"
    )
    dispatch_status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="draft", server_default="draft"
    )
    dispatch_round: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    allow_competitive_claim: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # §6.2 时间常数唯一权威表：响应窗默认 24h（可按包覆盖）
    response_window_hours: Mapped[int] = mapped_column(
        Integer, nullable=False, default=24, server_default="24"
    )
    redispatch_radius_km: Mapped[int] = mapped_column(
        Integer, nullable=False, default=25, server_default="25"
    )
    # §4.5：由 Quote 系数推导（tier 基档 + 任一因子触发最多上调一级），人工覆盖须留痕
    required_level: Mapped[str | None] = mapped_column(String(2))
    required_modules: Mapped[list[Any] | None] = mapped_column(JSON)
    required_industry: Mapped[str | None] = mapped_column(String(64))
    # §4.6：onsite_required 从 ProjectSolution.schedule 派生后落库
    onsite_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    onsite_visits: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    published_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    accepted_user_id: Mapped[str |None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    # 四席位 = 执行席位（§2.4 理由一：席位是「包 × 角色」的合同事实，不挂项目）
    seat_lead: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    seat_delivery: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    seat_consult: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    seat_qa: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class DispatchOffer(Base, TimestampMixin, VersionedMixin):
    """派单/抢单全量留痕（§6；一包 × 一轮 × 一候选人一行）。

    乐观锁：接单/中签/确认走 VersionedMixin.version 比对，冲突 409
    stale_version（§6.3，沿用本仓 32 模型已泛化模式，禁分布式锁）。
    """

    __tablename__ = "dispatch_offers"
    __table_args__ = (
        UniqueConstraint(
            "package_id",
            "dispatch_round",
            "candidate_user_id",
            name="uq_dispatch_offers_package_round_candidate",
        ),
        CheckConstraint(
            "status IN ('offered', 'accepted', 'rejected', 'declined', "
            "'transferred', 'expired')",
            name="ck_dispatch_offers_status",
        ),
        Index("ix_dispatch_offers_candidate", "candidate_user_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    package_id: Mapped[str] = mapped_column(
        ForeignKey("delivery_packages.id", ondelete="RESTRICT"), nullable=False
    )
    dispatch_round: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    candidate_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="offered", server_default="offered"
    )
    # §4.8 输出契约：Top3 + match_breakdown 结构化明细；rule_version 指向
    # 当时版权本（P0-8 判据：版本切换后旧 offer 仍指旧版权本）
    match_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # §6.2：评估窗/响应窗起算时刻（服务逻辑 P1-1 落位）
    offered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    responded_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
