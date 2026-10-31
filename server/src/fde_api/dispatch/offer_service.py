"""dispatch_offers 服务层（设计 §6，P1-1）。

并发控制（§6.3）：接单/确认走 VersionedMixin.version 显式比对（调用方传入
expected_version），冲突 409 stale_version；禁分布式锁（规则表 B3）。

offer 状态语义（§6 状态集六态的工程定义）：
- offered    已发出（assign 指派 / claim 抢单登记），等待响应；
- accepted   接单/中签确认完成（终态，触发包 accept + §9.3 交接）；
- declined   候选人拒单（§6.7 拒单权；原因只进事件留痕，不进任何分值）；
- rejected   平台侧撤销该候选资格（非候选人行为）；
- transferred 转单给次位候选（原 offer 留痕，§6.7）；
- expired    响应超时 / 同轮他人中签后被释放。

时限（§6.2 唯一权威表，经 DISPATCH_CONSTANTS 引用）：claim 中签确认窗
15 分钟；assign 响应窗 = 包 response_window_hours（默认 24h）。评估窗
3–5s 的收集期裁决属 P1-2 撮合核心（此处 claim 只做登记，留注⑩）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.dispatch.cities import claim_gate_status
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import DeliveryPackage, DispatchOffer
from fde_api.dispatch.packages import (
    handover_accepted_member,
    transition_package,
)
from fde_api.projects.events import record_event
from fde_api.system_configuration import DISPATCH_CONSTANTS
from fde_api.workbench.models import Project

DECLINE_REASONS = ("档期冲突", "能力不匹配", "距离", "其他")


def _offer_deadline(offer: DispatchOffer, package: DeliveryPackage) -> datetime | None:
    """§6.2：claim=15 分钟确认窗；assign=包响应窗（默认 24h）。"""
    if offer.offered_at is None:
        return None
    mode = (offer.match_breakdown or {}).get("mode")
    if mode == "claim":
        return offer.offered_at + timedelta(
            minutes=DISPATCH_CONSTANTS["claim_confirm_window_minutes"]
        )
    return offer.offered_at + timedelta(hours=package.response_window_hours)


def _load_offer(session: Session, offer_id: str) -> DispatchOffer:
    offer = session.get(DispatchOffer, offer_id)
    if offer is None:
        raise DispatchServiceError("offer_not_found", "派单 offer 不存在。", 404)
    return offer


def _check_version(offer: DispatchOffer, expected_version: int) -> None:
    """§6.3 乐观锁：显式比对调用方持有版本，冲突 409（先于其余业务校验）。"""
    if type(expected_version) is not int or expected_version != offer.version:
        raise DispatchServiceError(
            "stale_version", "offer 状态已变更，请刷新后重试。", 409
        )


def create_assign_offers(
    session: Session,
    *,
    actor: User,
    package_id: str,
    candidate_user_ids: tuple[str, ...],
) -> list[DispatchOffer]:
    """assign 指派：包 published → offered，对 Top-N 候选建 offer 行。
    match_breakdown 记 mode 与指派序（P1-2 撮合产出真实 breakdown 后替换）。"""
    if actor.role not in ("admin", "project_lead"):
        raise DispatchServiceError(
            "verifier_role_required", "只有平台侧可指派。", 403
        )
    if not candidate_user_ids:
        raise DispatchServiceError("invalid_request", "candidate_user_ids 不能为空。")
    unique_candidates = list(dict.fromkeys(candidate_user_ids))
    package = session.get(DeliveryPackage, package_id)
    if package is None:
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    if package.dispatch_status == "published":
        transition_package(session, actor=actor, package_id=package_id, action="offer")
        session.flush()
        session.refresh(package)
    if package.dispatch_status != "offered":
        raise DispatchServiceError(
            "invalid_dispatch_state", f"包状态 {package.dispatch_status} 不能发 offer。", 409
        )

    created: list[DispatchOffer] = []
    for position, candidate_id in enumerate(unique_candidates, start=1):
        existing = session.scalar(
            select(DispatchOffer.id).where(
                DispatchOffer.package_id == package.id,
                DispatchOffer.dispatch_round == package.dispatch_round,
                DispatchOffer.candidate_user_id == candidate_id,
            )
        )
        if existing is not None:
            raise DispatchServiceError(
                "offer_exists", "该候选在本轮已有 offer（409）。", 409
            )
        offer = DispatchOffer(
            package_id=package.id,
            dispatch_round=package.dispatch_round,
            candidate_user_id=candidate_id,
            status="offered",
            match_breakdown={"mode": "assign", "ranked_position": position},
            offered_at=datetime.now(timezone.utc),
        )
        session.add(offer)
        created.append(offer)
    session.flush()
    for offer in created:
        record_event(
            session,
            actor,
            "dispatch_offer_created",
            offer,
            {
                "mode": "assign",
                "dispatch_round": offer.dispatch_round,
                "candidate_user_id": offer.candidate_user_id,
                "offered_at": offer.offered_at.isoformat() if offer.offered_at else None,
            },
        )
    return created


def claim_package(
    session: Session,
    *,
    actor: User,
    package_id: str,
) -> DispatchOffer:
    """claim 抢单登记（C9 开闸三条件 + 种子城市开关全过才允许）。
    评估窗收集期裁决（3–5s）随 P1-2 撮合核心落位——本入口只登记候选（留注⑩）。"""
    if actor.role not in ("admin", "fde_engineer", "project_lead"):
        raise DispatchServiceError("forbidden", "当前角色不能抢单。", 403)
    package = session.get(DeliveryPackage, package_id)
    if package is None:
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    project_city = None
    project = session.get(Project, package.project_id)
    if project is not None:
        segments = (project.enterprise_code or "").split("·")
        project_city = segments[2] if len(segments) == 3 else None
    if not project_city:
        raise DispatchServiceError(
            "claim_city_unknown", "交付包无客户城归属（企业代号三段式缺城市段）。", 422
        )
    gate = claim_gate_status(session, project_city)
    if not gate["claim_open"]:
        raise DispatchServiceError(
            "claim_closed",
            f"该城抢单未开闸（§6.4：{'、'.join(k for k, v in gate['conditions'].items() if not v) or '城市开关关闭'}）。",
            403,
        )
    if package.dispatch_status == "published":
        transition_package(session, actor=actor, package_id=package_id, action="offer")
        session.flush()
        session.refresh(package)
    if package.dispatch_status != "offered":
        raise DispatchServiceError(
            "invalid_dispatch_state", f"包状态 {package.dispatch_status} 不能抢。", 409
        )
    existing = session.scalar(
        select(DispatchOffer.id).where(
            DispatchOffer.package_id == package.id,
            DispatchOffer.dispatch_round == package.dispatch_round,
            DispatchOffer.candidate_user_id == actor.id,
        )
    )
    if existing is not None:
        raise DispatchServiceError("offer_exists", "本轮已登记过抢单（409）。", 409)
    offer = DispatchOffer(
        package_id=package.id,
        dispatch_round=package.dispatch_round,
        candidate_user_id=actor.id,
        status="offered",
        match_breakdown={"mode": "claim"},
        offered_at=datetime.now(timezone.utc),
    )
    session.add(offer)
    session.flush()
    record_event(
        session,
        actor,
        "dispatch_offer_created",
        offer,
        {
            "mode": "claim",
            "dispatch_round": offer.dispatch_round,
            "city": project_city,
            "offered_at": offer.offered_at.isoformat() if offer.offered_at else None,
        },
    )
    return offer


def accept_offer(
    session: Session,
    *,
    actor: User,
    offer_id: str,
    expected_version: int,
) -> dict[str, Any]:
    """接单/中签确认（§6.3 乐观锁 → 时限校验 → 同轮互斥 → 包 accept）。

    返回 handover 待执行信息；§9.3 交接由调用方在主事务提交后执行
    （handover_accepted_member），本函数不自管事务。
    """
    offer = _load_offer(session, offer_id)
    _check_version(offer, expected_version)
    package = session.get(DeliveryPackage, offer.package_id)
    if package is None:
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    # 接单人 = 候选本人（平台侧可代确认中签，§6.2 确认窗语义）
    if actor.id != offer.candidate_user_id and actor.role not in ("admin", "project_lead"):
        raise DispatchServiceError("forbidden", "只有候选人本人或平台侧可接单。", 403)
    if offer.status != "offered":
        raise DispatchServiceError(
            "invalid_offer_state", f"offer 状态 {offer.status} 不能接单。", 409
        )
    deadline = _offer_deadline(offer, package)
    now = datetime.now(timezone.utc)
    if deadline is not None and now > deadline:
        raise DispatchServiceError(
            "offer_window_expired", "响应/确认窗已过（§6.2），offer 自动释放。", 409
        )

    # 同轮互斥：一人中签，其余候选释放（行锁串行化经包行 FOR UPDATE）
    package_lock = session.scalar(
        select(DeliveryPackage.id).where(DeliveryPackage.id == package.id).with_for_update()
    )
    assert package_lock is not None
    accepted_sibling = session.scalar(
        select(DispatchOffer.id).where(
            DispatchOffer.package_id == package.id,
            DispatchOffer.dispatch_round == offer.dispatch_round,
            DispatchOffer.status == "accepted",
            DispatchOffer.id != offer.id,
        )
    )
    if accepted_sibling is not None:
        raise DispatchServiceError(
            "offer_already_accepted", "该轮已有候选人接单。", 409
        )

    respond(offer, now)
    offer.status = "accepted"
    offer.version += 1
    session.flush()
    record_event(
        session,
        actor,
        "dispatch_offer_accepted",
        offer,
        {
            "candidate_user_id": offer.candidate_user_id,
            "dispatch_round": offer.dispatch_round,
            "version": offer.version,
        },
    )
    # 包接单 + 其余 offer 释放（同一事务，leader 交接在提交后）
    transition_package(
        session,
        actor=actor,
        package_id=package.id,
        action="accept",
        seat_delivery_user_id=offer.candidate_user_id,
    )
    released = _release_sibling_offers(
        session, actor=actor, package=package, round_no=offer.dispatch_round, keep_offer_id=offer.id
    )
    return {"offer": offer, "package": package, "released": released}


def respond(offer: DispatchOffer, now: datetime) -> None:
    if offer.responded_at is None:
        offer.responded_at = now


def _release_sibling_offers(
    session: Session,
    *,
    actor: User,
    package: DeliveryPackage,
    round_no: int,
    keep_offer_id: str,
) -> int:
    siblings = session.scalars(
        select(DispatchOffer).where(
            DispatchOffer.package_id == package.id,
            DispatchOffer.dispatch_round == round_no,
            DispatchOffer.id != keep_offer_id,
            DispatchOffer.status == "offered",
        )
    ).all()
    now = datetime.now(timezone.utc)
    for sibling in siblings:
        sibling.status = "expired"
        respond(sibling, now)
        sibling.version += 1
        record_event(
            session,
            actor,
            "dispatch_offer_expired",
            sibling,
            {"reason": "sibling_accepted", "dispatch_round": round_no},
        )
    return len(siblings)


def decline_offer(
    session: Session,
    *,
    actor: User,
    offer_id: str,
    expected_version: int,
    reason: str | None = None,
) -> DispatchOffer:
    """§6.7 拒单权：候选人本人拒单，原因枚举选填、只进事件留痕。
    每日 ≥4 次无条件且**不因此限制后续接单机会**（负面清单 A-6 #6 的防护=
    本函数永不因配额拒绝拒单）。"""
    offer = _load_offer(session, offer_id)
    _check_version(offer, expected_version)
    if actor.id != offer.candidate_user_id and actor.role not in ("admin",):
        raise DispatchServiceError("forbidden", "只有候选人本人可拒单。", 403)
    if offer.status != "offered":
        raise DispatchServiceError(
            "invalid_offer_state", f"offer 状态 {offer.status} 不能拒。", 409
        )
    if reason is not None and reason not in DECLINE_REASONS:
        raise DispatchServiceError(
            "invalid_request", f"拒单原因必须是 {'/'.join(DECLINE_REASONS)} 或缺省。"
        )
    respond(offer, datetime.now(timezone.utc))
    offer.status = "declined"
    offer.version += 1
    session.flush()
    record_event(
        session,
        actor,
        "dispatch_offer_declined",
        offer,
        {
            "candidate_user_id": offer.candidate_user_id,
            "reason": reason,
            "dispatch_round": offer.dispatch_round,
        },
    )
    _maybe_reject_package(session, actor=actor, package_id=offer.package_id, round_no=offer.dispatch_round)
    return offer


def _maybe_reject_package(
    session: Session, *, actor: User, package_id: str, round_no: int
) -> None:
    """本轮全部 offer 终结且无接受者 → 包 rejected（§2.5，重派入口）。"""
    package = session.get(DeliveryPackage, package_id)
    if package is None or package.dispatch_status != "offered":
        return
    live = session.scalar(
        select(DispatchOffer.id)
        .where(
            DispatchOffer.package_id == package_id,
            DispatchOffer.dispatch_round == round_no,
            DispatchOffer.status.in_(("offered", "accepted")),
        )
        .limit(1)
    )
    if live is None:
        transition_package(session, actor=actor, package_id=package_id, action="reject")


def expire_stale_offers(session: Session, *, now: datetime | None = None) -> int:
    """超时释放（jobs/请求路径惰性触发均可）：过时限的 offered → expired；
    包无活 offer → expired/reject 迁移（§2.5 响应超时路径）。"""
    now = now or datetime.now(timezone.utc)
    stale = session.scalars(
        select(DispatchOffer).where(DispatchOffer.status == "offered")
    ).all()
    expired = 0
    touched_packages: dict[str, DeliveryPackage] = {}
    for offer in stale:
        package = touched_packages.get(offer.package_id) or session.get(
            DeliveryPackage, offer.package_id
        )
        if package is None:
            continue
        touched_packages[offer.package_id] = package
        deadline = _offer_deadline(offer, package)
        if deadline is None or now <= deadline:
            continue
        respond(offer, now)
        offer.status = "expired"
        offer.version += 1
        expired += 1
        record_event(
            session,
            actor_system(session),
            "dispatch_offer_expired",
            offer,
            {"reason": "window_timeout", "dispatch_round": offer.dispatch_round},
        )
    for package in touched_packages.values():
        if package.dispatch_status != "offered":
            continue
        live = session.scalar(
            select(DispatchOffer.id)
            .where(
                DispatchOffer.package_id == package.id,
                DispatchOffer.dispatch_round == package.dispatch_round,
                DispatchOffer.status.in_(("offered", "accepted")),
            )
            .limit(1)
        )
        if live is None:
            transition_package(session, actor=actor_system(session), package_id=package.id, action="expire")
    return expired


def actor_system(session: Session) -> User:
    """超时释放的留痕 actor：取一个 admin（系统动作挂平台侧留痕）。"""
    admin = session.scalar(select(User).where(User.role == "admin").limit(1))
    if admin is None:
        raise DispatchServiceError("no_admin_user", "系统内无 admin，无法留痕。", 500)
    return admin


def accept_offer_and_handover(
    *,
    actor: User,
    offer_id: str,
    expected_version: int,
) -> dict[str, Any]:
    """API 入口：主事务（offer 乐观锁 + 包迁移 + 释放同轮）→ 提交后 §9.3 交接。"""
    session = db_session()
    try:
        with session.begin():
            result = accept_offer(
                session, actor=actor, offer_id=offer_id, expected_version=expected_version
            )
            offer, package = result["offer"], result["package"]
            payload = {
                "offer_id": offer.id,
                "status": offer.status,
                "version": offer.version,
                "package_id": package.id,
                "dispatch_status": package.dispatch_status,
                "dispatch_round": package.dispatch_round,
                "released_siblings": result.get("released", 0),
            }
        payload["handover"] = handover_accepted_member(
            package.project_id, offer.candidate_user_id
        )
        return payload
    finally:
        session.close()


def db_session():
    from fde_api.extensions import db

    return db.session()
