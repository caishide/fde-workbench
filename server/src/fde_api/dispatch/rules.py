"""dispatch_rule_versions 权重与规则版本服务（设计 §4.3/§6.2/规则表 B9，P0-8）。

权重唯一来源是版本表：Stage B 权重、等级映射分、席位份额全部进
rule_snapshot JSON，实现代码只准引用（回退 DISPATCH_CONSTANTS），不许散落
硬编码。改规则 = 新版本 + 公示：重大调整生效日 ≥ 公示日 + 30 天（§6.2），
create_rule_version 强制校验；已发 offer 的 match_breakdown.rule_version
永指当时版本（版本切换不回写，§8.3 P0-8 验收判据）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fde_api.auth.models import ROLE_ADMIN, User
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import DispatchRuleVersion
from fde_api.projects.events import record_event
from fde_api.system_configuration import DISPATCH_CONSTANTS

# rule_snapshot 必备节（§4.3/§6.2/§7.1 快照内容清单）
REQUIRED_SNAPSHOT_KEYS = ("stage_b_weights", "level_score_map", "seat_shares")

_VERIFIER_ROLES = {ROLE_ADMIN}


def _require_actor_admin(actor: User) -> None:
    if actor.role not in _VERIFIER_ROLES:
        raise DispatchServiceError(
            "verifier_role_required", "规则版本只能由平台方（admin）发布。", 403
        )


def default_rule_snapshot() -> dict[str, Any]:
    """首版快照 = DISPATCH_CONSTANTS 的规则节投影（发布时显式落库，此后
    常量与版本解耦：版本表才是 active 口径的唯一来源）。"""
    return {
        "stage_b_weights": dict(DISPATCH_CONSTANTS["stage_b_weights"]),
        "level_score_map": dict(DISPATCH_CONSTANTS["level_score_map"]),
        "seat_shares": dict(DISPATCH_CONSTANTS["seat_shares"]),
        "cold_start_seat_shares": dict(DISPATCH_CONSTANTS["cold_start_seat_shares"]),
        "cold_start_first_orders": DISPATCH_CONSTANTS["cold_start_first_orders"],
        "top_n": DISPATCH_CONSTANTS["top_n"],
    }


def create_rule_version(
    session: Session,
    *,
    actor: User,
    version_no: int,
    rule_snapshot: dict[str, Any],
    published_at: datetime | None = None,
    effective_at: datetime,
) -> DispatchRuleVersion:
    """发布新版本：status='published'，到 effective_at 才可被 activate。
    §6.2 公示窗强制：effective_at − published_at ≥ 30 天（默认口径；非权重
    微调是否豁免留待拍板，先一刀切保守）。"""
    _require_actor_admin(actor)
    if type(version_no) is not int or version_no < 1:
        raise DispatchServiceError("invalid_request", "version_no 必须是 ≥1 整数。")
    if not isinstance(rule_snapshot, dict) or not all(
        key in rule_snapshot for key in REQUIRED_SNAPSHOT_KEYS
    ):
        raise DispatchServiceError(
            "invalid_request",
            f"rule_snapshot 必须包含：{'、'.join(REQUIRED_SNAPSHOT_KEYS)}。",
        )
    published = published_at or datetime.now(timezone.utc)
    if effective_at < published + timedelta(
        days=DISPATCH_CONSTANTS["weight_public_notice_days"]
    ):
        raise DispatchServiceError(
            "notice_window_required",
            "规则重大调整须公示 ≥30 天：生效日不得早于发布日 + 30 天（§6.2）。",
            422,
        )
    existing = session.scalar(
        select(DispatchRuleVersion).where(DispatchRuleVersion.version_no == version_no)
    )
    if existing is not None:
        raise DispatchServiceError("version_conflict", "该版本号已存在。", 409)
    row = DispatchRuleVersion(
        version_no=version_no,
        status="published",
        rule_snapshot=rule_snapshot,
        published_at=published,
        effective_at=effective_at,
        published_by_user_id=actor.id,
    )
    session.add(row)
    session.flush()
    record_event(
        session,
        actor,
        "dispatch_rule_published",
        actor,
        {
            "version_no": version_no,
            "effective_at": effective_at.isoformat(),
            "keys": sorted(rule_snapshot),
        },
    )
    return row


def activate_due_versions(session: Session, *, now: datetime | None = None) -> int:
    """到点生效（月度 jobs / 请求路径惰性触发均可）：published 且 effective_at
    已到 → active；原 active 版本转 retired。同一时刻至多一个 active。"""
    now = now or datetime.now(timezone.utc)
    due = session.scalars(
        select(DispatchRuleVersion).where(
            DispatchRuleVersion.status == "published",
            DispatchRuleVersion.effective_at.is_not(None),
            DispatchRuleVersion.effective_at <= now,
        )
    ).all()
    activated = 0
    for row in due:
        current = session.scalar(
            select(DispatchRuleVersion).where(DispatchRuleVersion.status == "active")
        )
        if current is not None:
            if current.version_no == row.version_no:
                continue
            current.status = "retired"
            current.retired_at = now
        row.status = "active"
        activated += 1
    if activated:
        session.flush()
    return activated


def active_rule_version(session: Session) -> DispatchRuleVersion | None:
    return session.scalar(
        select(DispatchRuleVersion).where(DispatchRuleVersion.status == "active")
    )


def active_rule_snapshot(session: Session) -> dict[str, Any] | None:
    row = active_rule_version(session)
    return row.rule_snapshot if row is not None else None
