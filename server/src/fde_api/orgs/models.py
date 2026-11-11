"""M1：``orgs`` 表——归属维度的单一命名空间（ADR-M1 §3）。

甲路线拍板（任务书 §11-1/§11-2）：``orgs`` 独立表（类型 enterprise/internal），
``users.org_id`` / ``projects.org_id`` / ``operation_events.org_id`` 指向它；
项目域 83 张表经 ``projects.org_id`` 推导，不逐表加列。**零新建平行权限表**
（G6 红线复述）：成员可见性仍由既有 ``project_members`` 决定，org 只是
归属与统计口径，不单独授权。

本模块只依赖 ``auth.models``（Base 所在地），被 ``workbench.models`` 尾部
导入——不产生环。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from fde_api.auth.models import (
    Base,
    CURRENT_TIMESTAMP_SQL,
    UTC_TIMESTAMP_SQL,
    UTCDateTime,
    UTCTimestamp,
)

ORG_TYPE_ENTERPRISE = "enterprise"
ORG_TYPE_INTERNAL = "internal"
ORG_TYPES = frozenset({ORG_TYPE_ENTERPRISE, ORG_TYPE_INTERNAL})

# 平台内部组织的稳定 ID：迁移种子 / cli bootstrap / 归属兜底 / 测试夹具
# 四处同源（单一权威）。语义边界（ADR-M1 §3/§4）：``org_id=NULL`` = 平台身份
# 不受 org 限制（admin/交付咨询）；``internal`` org = 平台自有数据与存量
# 回填的归属命名空间。两者不是同一件事。
INTERNAL_ORG_ID = "00000000-0000-0000-0000-0000000fde01"
INTERNAL_ORG_NAME = "平台内部组织"


def new_org_id() -> str:
    return str(uuid4())


class Org(Base):
    __tablename__ = "orgs"
    __table_args__ = (
        CheckConstraint(
            f"org_type IN ('{ORG_TYPE_ENTERPRISE}', '{ORG_TYPE_INTERNAL}')",
            name="ck_orgs_org_type",
        ),
        UniqueConstraint("name", name="uq_orgs_name"),
        # 可空唯一：PG 语义下多行 NULL 共存——未挂主体键的 org 不受影响
        UniqueConstraint("subject_key", name="uq_orgs_subject_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_org_id)
    org_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 企业代号化名（红线 2：客户真实名称不入库，只存代号）
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # 可选挂 G6 企业主体键（规范化 USCC，18 位；1 org : 1 subject_key）
    subject_key: Mapped[str | None] = mapped_column(String(18))
    # 多客户 M4 批次 B（任务书 §7-M4「AI 预算按主体分别设额」）：企业 org 的
    # AI 月度 token 预算（**可空＝未配置**，读侧回落实例值 ``ai_monthly_token_budget``
    # ＝现状语义零回归；``0``＝不限额，沿 E7 心智）。企业身份用户的用量按
    # 同 org 全员月度合计判此额度；平台身份不受 org 额度约束（按 user 现状）。
    ai_monthly_token_budget: Mapped[int | None] = mapped_column(Integer)
    # 创建者＝**纯指针无 FK**（先例：transcripts minutes.draft_id 同形）——
    # users.org_id→orgs 与 orgs.created_by→users 互指会构成 FK 环，元数据
    # 不可拓扑排序（SAWarning: unresolvable cycles）；provenance 由应用层
    # 维护即可，不值得为此引入 use_alter 复杂度。
    created_by_user_id: Mapped[str | None] = mapped_column(String(36))
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
            self.id = new_org_id()
