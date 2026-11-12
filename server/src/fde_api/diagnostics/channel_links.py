"""获客诊断 T-15：渠道链接注册表（R4 专属链接 ＝ 归因凭证）。

**解决什么**：T-11 的 A 档归因读 ``lead.source_type == 'partner'``，而
``source_type`` 此前是**客户端声明**的——任何人 POST ``{"source_type":
"partner", "channel_ref": "x"}`` 就能造出 A 档线索（未来的收费档）。本模块
把渠道报备收进**注册表**：``partner`` 归因**只能**由有效链接 token 服务端
推导，客户端声明一律拒绝——归因机械可判，零手工记账（P-2）。

**语义三条**：

1. **明文只此一次**：创建响应返回明文 token（admin 拼进专属链接后交付渠道
   方）；库里只有 sha256（沿匿名会话令牌同尺）。
2. **fail-closed 降档**：访客带着过期/无效 token 进来 ⇒ 会话照常建（stale
   链接不拦真实线索），但落 ``direct``——没有有效证据就不给 A 档；降档是
   诚实语义，不是错误（响应带解析后的 ``source_type``，前端可知）。
3. **历史归因不改写**：停用链接是软撤（新会话不再解析），既有线索行的
   ``source_type='partner'`` 不回滚——归因在**会话创建时刻**定格。

``channel_ref`` 写回线索行的是**链接行 UUID**（``sessions.channel_ref`` 是
普通字符串列，不加外键——线索域与注册表松耦合，删链接不改历史归因）。
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from fde_api.diagnostics.models import LeadDiagnosticChannelLink, LeadDiagnosticSession
from fde_api.diagnostics.service import _error, ensure_enabled, hash_token
from fde_api.extensions import db

# 渠道方备注长度上限（代号化纪律：不写真实姓名/联系方式）
MAX_NOTE_CHARS = 200
# 渠道方区域长度上限（与认领区域同尺）
MAX_REGION_CHARS = 80


def create_link(
    *,
    actor: Any,
    payload: dict[str, Any],
) -> tuple[LeadDiagnosticChannelLink, str]:
    """新建渠道链接；返回（行, 明文 token）——**明文只此一次**。"""
    ensure_enabled()
    region_raw = payload.get("region_name")
    region_name = str(region_raw).strip() if region_raw is not None else ""
    if len(region_name) > MAX_REGION_CHARS:
        raise _error("invalid_region", "区域名称过长。", 400)
    note_raw = payload.get("note")
    note = str(note_raw).strip() if note_raw is not None else ""
    if len(note) > MAX_NOTE_CHARS:
        raise _error("note_too_long", "备注过长。", 400)
    token = secrets.token_urlsafe(24)
    with db.session() as session:
        row = LeadDiagnosticChannelLink(
            token_sha256=hash_token(token),
            region_name=region_name or None,
            note=note or None,
            is_active=True,
            created_by_user_id=actor.id,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row, token


def resolve_link(token: str) -> LeadDiagnosticChannelLink | None:
    """按明文 token 解析**在用**的链接（指纹查表；停用/未知 ⇒ None）。"""
    digest = hash_token(token)
    with db.session() as session:
        return session.scalar(
            select(LeadDiagnosticChannelLink).where(
                LeadDiagnosticChannelLink.token_sha256 == digest,
                LeadDiagnosticChannelLink.is_active.is_(True),
            )
        )


def list_links(*, limit: int = 100) -> list[dict[str, Any]]:
    """渠道链接清单（**无明文 token**；带在册线索数——渠道方对账可见）。"""
    capped = max(1, min(int(limit or 100), 500))
    with db.session() as session:
        rows = list(
            session.scalars(
                select(LeadDiagnosticChannelLink)
                .order_by(LeadDiagnosticChannelLink.created_at.desc())
                .limit(capped)
            )
        )
        counts: dict[str, int] = {}
        if rows:
            link_ids = [row.id for row in rows]
            grouped = session.execute(
                select(
                    LeadDiagnosticSession.channel_ref,
                    func.count(LeadDiagnosticSession.id),
                )
                .where(LeadDiagnosticSession.channel_ref.in_(link_ids))
                .group_by(LeadDiagnosticSession.channel_ref)
            ).all()
            counts = {ref: int(count) for ref, count in grouped}
        return [serialize_link(row, counts.get(row.id, 0)) for row in rows]


def deactivate_link(*, actor: Any, link_id: str) -> LeadDiagnosticChannelLink:
    """停用链接（软撤：历史归因不改写，新会话不再解析）。"""
    with db.session() as session:
        row = session.get(LeadDiagnosticChannelLink, link_id)
        if row is None:
            raise _error("channel_link_not_found", "渠道链接不存在。", 404)
        if row.is_active:
            row.is_active = False
            row.deactivated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
        return row


def serialize_link(row: LeadDiagnosticChannelLink, lead_count: int = 0) -> dict[str, Any]:
    """投影（**无明文 token**——指纹也不外露，只在库内比对）。"""
    return {
        "id": row.id,
        "region_name": row.region_name,
        "note": row.note,
        "is_active": row.is_active,
        "deactivated_at": row.deactivated_at.isoformat() if row.deactivated_at else None,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "lead_count": lead_count,
    }


__all__ = [
    "create_link",
    "deactivate_link",
    "list_links",
    "resolve_link",
    "serialize_link",
]
