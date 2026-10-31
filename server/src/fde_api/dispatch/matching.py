"""撮合核心（设计 §4，P1-2，L 级主战役）。

两段式管线（§4.1）：Stage A 五资格门（硬过滤，不打分）→ 场景裁决
（A 到场=字典序 / B 远程=加权 / C 候选池空=不自动派）→ Top3 + match_breakdown
落 dispatch_offers + OperationEvent 逐人留痕（§4.8 输出契约）。

降级态前置（§11.1 + 留注⑬）：自动撮合要求存在 published/active 规则版本
（=权重已公示）；无版本 → 422 rule_version_required，回退人工排序——
这正是备案未定期间（附录 B-①）的合规运行形态。

match_breakdown 是对被派方的「释明算法」展示数据（§4.8/§5.4）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fde_api.auth.models import User
from fde_api.dispatch import scoring
from fde_api.dispatch.cities import load_dispatch_cities
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.models import (
    DeliveryPackage,
    DispatchOffer,
    FdeProfile,
)
from fde_api.dispatch.packages import transition_package
from fde_api.dispatch.rules import active_rule_version
from fde_api.projects.events import record_event
from fde_api.system_configuration import DISPATCH_CONSTANTS
from fde_api.workbench.models import ModuleCatalog, Project, Quote

_TIER_BASE = {"light": 1, "standard": 2, "flagship": 3}


def derive_required_level(quote: Quote) -> str:
    """§4.5：Quote 系数 → L1–L4（基档 + 任一因子触发最多上调一级，封顶 L4）。"""
    base = _TIER_BASE.get(quote.tier, 2)
    triggered = (
        quote.data_factor >= Decimal("1.3")
        or quote.compliance_factor >= Decimal("1.2")
        or quote.integration_factor >= Decimal("1.4")
    )
    return f"L{min(base + (1 if triggered else 0), 4)}"


def override_required_level(
    session: Session, *, actor: User, package_id: str, level: str, reason: str
) -> DeliveryPackage:
    """§4.5/§4.6：发布前人工覆盖 required_level，必填 reason + 留痕
    （快照在覆盖后的发布时计算，§2.3 顺序天然成立）。"""
    if actor.role not in ("admin", "project_lead"):
        raise DispatchServiceError("forbidden", "只有平台侧可覆盖等级门槛。", 403)
    if level not in ("L1", "L2", "L3", "L4"):
        raise DispatchServiceError("invalid_request", "level 必须是 L1/L2/L3/L4。")
    if not isinstance(reason, str) or not reason.strip():
        raise DispatchServiceError("invalid_request", "覆盖必须写明 reason。")
    package = session.get(DeliveryPackage, package_id)
    if package is None:
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    if package.dispatch_status != "draft":
        raise DispatchServiceError(
            "invalid_dispatch_state", "只能对 draft 包覆盖等级门槛（发布后快照已冻结）。", 409
        )
    previous = package.required_level
    package.required_level = level
    session.flush()
    record_event(
        session,
        actor,
        "delivery_package_level_overridden",
        package,
        {"from": previous, "to": level, "reason": reason.strip()},
    )
    return package


def _city_index() -> dict[str, tuple[str | None, str | None]]:
    return {
        row["city"]: (row.get("province"), row.get("metro_group"))
        for row in load_dispatch_cities()
    }


def _client_city(session: Session, package: DeliveryPackage) -> str | None:
    project = session.get(Project, package.project_id)
    if project is None:
        return None
    segments = (project.enterprise_code or "").split("·")
    return segments[2] if len(segments) == 3 else None


def allowed_geo_tier(package: DeliveryPackage, quote: Quote | None) -> int:
    """§4.7 扩圈链：同城 → 同省 → 邻接都市圈 → 全国。每降一档 = round+1，
    首轮（round=1）只同城；tier3（全国）仅旗舰档且客户书面确认（确认件
    指针二期落位——一期以 quote.tier='flagship' 为必要条件，留注⑮）。"""
    allowed = min(package.dispatch_round - 1, 3)
    if allowed >= 3 and (quote is None or quote.tier != "flagship"):
        allowed = 2
    return allowed


def _in_hand_count(session: Session, user_id: str) -> int:
    """A4 在途计数（§4.2）：本人为候选/接单方的未终结 offer 数。"""
    return session.scalar(
        select(func.count())
        .select_from(DispatchOffer)
        .where(
            DispatchOffer.candidate_user_id == user_id,
            DispatchOffer.status.in_(("offered", "accepted")),
        )
    ) or 0


def _capacity_cap(profile: FdeProfile) -> int:
    """同时接单上限 = floor(月产能 ÷ max(单均工时, 1))，自动算不允许手工设
    （§4.2 A4 / BP 规则五）；产能未申报按 0（不可接单）。"""
    if not profile.monthly_capacity_hours:
        return 0
    return profile.monthly_capacity_hours // max(profile.avg_delivery_hours or 0, 1)


def _stage_a(
    session: Session, package: DeliveryPackage, quote: Quote | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """五资格门评估（§4.2）。返回 (通过的候选明细, 被淘汰的明细——场景 C
    诊断与释明用)。模块 A2：包侧存 module_catalog_id（§2.2 映射），档案侧
    存 module_key（§3.2）——经 ModuleCatalog 归一后比较（代码实测口径）。"""
    required_ids = set(package.required_modules or [])
    key_by_id = {}
    if required_ids:
        rows = session.execute(
            select(ModuleCatalog.id, ModuleCatalog.module_key).where(
                ModuleCatalog.id.in_(required_ids)
            )
        ).all()
        key_by_id = {row[0]: row[1] for row in rows}
    required_keys = {key_by_id[rid] for rid in required_ids if rid in key_by_id}

    client_city = _client_city(session, package)
    city_index = _city_index()
    allowed_tier = (
        allowed_geo_tier(package, quote) if package.onsite_required else 3
    )
    passed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    profiles = session.scalars(
        select(FdeProfile).where(FdeProfile.status == "active", FdeProfile.is_active.is_(True))
    ).all()
    for profile in profiles:
        level = profile.level
        a1 = scoring.level_rank(level) >= scoring.level_rank(package.required_level)
        tag_keys = {str(tag) for tag in (profile.module_tags or [])}
        a2 = required_keys <= tag_keys
        a3 = (
            not package.required_industry
            or package.required_industry
            in {str(tag) for tag in (profile.industry_tags or [])}
        )
        in_hand = _in_hand_count(session, profile.user_id)
        cap = _capacity_cap(profile)
        a4 = in_hand < cap
        tier = scoring.geo_tier(profile.home_city, client_city, city_index)
        a5 = (not package.onsite_required) or tier <= allowed_tier
        detail = {
            "A1": {"level": level, "required": package.required_level, "ok": a1},
            "A2": {"required_modules": sorted(required_keys), "ok": a2},
            "A3": {"industry": package.required_industry, "ok": a3},
            "A4": {"in_hand": in_hand, "cap": cap, "ok": a4},
            "A5": {"home_city": profile.home_city, "tier": tier, "allowed": allowed_tier, "ok": a5},
        }
        entry = {"profile": profile, "tier": tier, "client_city": client_city, "gates": detail}
        (passed if (a1 and a2 and a3 and a4 and a5) else rejected).append(entry)
    return passed, rejected


def _explanation(entry: dict[str, Any], scenario: str, rank: int) -> str:
    gates = entry["gates"]
    tier = entry["tier"]
    tier_label = {0: "同城", 1: "同省", 2: "邻接都市圈", 3: "全国"}[tier]
    level = entry["profile"].level
    industry = gates["A3"]["industry"]
    return (
        f"{'到场型' if scenario == 'onsite' else '远程型'}第 {rank} 顺位：{tier_label}候选；"
        f"等级 {level or '未定级'} 达标；行业"
        f"{'精确命中 ' + str(industry) if industry else '无要求'}；档期可协商。"
    )


def match_package(
    session: Session, *, actor: User, package_id: str
) -> dict[str, Any]:
    """对 published 包跑两段式撮合，落 Top3 offer（§4.1–§4.8）。"""
    if actor.role not in ("admin", "project_lead"):
        raise DispatchServiceError("forbidden", "只有平台侧可执行撮合。", 403)
    package = session.get(DeliveryPackage, package_id)
    if package is None:
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    if package.dispatch_status != "published":
        raise DispatchServiceError(
            "invalid_dispatch_state", f"包状态 {package.dispatch_status} 不能撮合（需 published）。", 409
        )
    existing = session.scalar(
        select(DispatchOffer.id).where(
            DispatchOffer.package_id == package.id,
            DispatchOffer.dispatch_round == package.dispatch_round,
        )
    )
    if existing is not None:
        raise DispatchServiceError(
            "offer_exists", "本轮已有 offer（重派先走 republish 递增轮次）。", 409
        )
    version = active_rule_version(session)
    if version is None:
        raise DispatchServiceError(
            "rule_version_required",
            "无已公示的规则版本（§11.1 降级态：只跑 Stage A + 人工排序，不自动派）。",
            422,
        )
    rule = dict(version.rule_snapshot or {})
    quote = session.get(Quote, package.quote_id) if package.quote_id else None
    rule["_required_industry"] = package.required_industry

    passed, rejected = _stage_a(session, package, quote)
    scenario = "onsite" if package.onsite_required else "remote"
    if not passed:
        # 场景 C：不自动派，通知交付总监（事件全量留痕，§4.4）
        record_event(
            session,
            actor,
            "dispatch_matching_scenario_c",
            package,
            {
                "scenario": "onsite" if scenario == "onsite" else "remote",
                "rejected": [
                    {"user_id": item["profile"].user_id, "gates": item["gates"]}
                    for item in rejected
                ],
                "action": "manual_fallback",
            },
        )
        return {
            "scenario": "C",
            "offers": [],
            "rejected": [item["profile"].user_id for item in rejected],
            "rule_version": version.version_no,
        }

    seed = scoring.tie_break_seed(package.id, package.dispatch_round, version.version_no)
    ranked: list[tuple[tuple, dict[str, Any], dict[str, Any]]] = []
    for entry in passed:
        profile = entry["profile"]
        industry = scoring.industry_score(
            profile.industry_tags, package.required_industry
        )
        if scenario == "onsite":
            key = scoring.sort_key_onsite(
                tier=entry["tier"],
                level=profile.level,
                industry=industry,
                sla=scoring.sla_score(),
            )
            stage_b = {
                "geo_tier": entry["tier"],
                "ability": {"level": profile.level, "score": scoring.level_score(profile.level, rule)},
                "industry": industry,
                "sla": scoring.sla_score(),
            }
        else:
            weighted = scoring.weighted_score(
                level=profile.level,
                industry_tags=profile.industry_tags,
                tier=entry["tier"],
                rule=rule,
            )
            key = scoring.sort_key_remote(
                weighted=weighted,
                in_fence=scoring.in_fence(profile.home_city, entry["client_city"], profile.geo_fence_km),
                seed=seed,
                candidate_key=profile.user_id,
            )
            stage_b = {
                "weighted_score": weighted,
                "ability": {"level": profile.level, "score": scoring.level_score(profile.level, rule)},
                "industry": industry,
                "sla": scoring.sla_score(),
                "geo": scoring.geo_score(entry["tier"]),
            }
        ranked.append((key, entry, stage_b))
    ranked.sort(key=lambda item: item[0])

    top_n = int(DISPATCH_CONSTANTS["top_n"])
    created: list[DispatchOffer] = []
    for rank, (key, entry, stage_b) in enumerate(ranked[:top_n], start=1):
        profile = entry["profile"]
        offer = DispatchOffer(
            package_id=package.id,
            dispatch_round=package.dispatch_round,
            candidate_user_id=profile.user_id,
            status="offered",
            match_breakdown={
                "rule_version": version.id,
                "version_no": version.version_no,
                "scenario": scenario,
                "stage_a": entry["gates"],
                "stage_b": stage_b,
                "rank": rank,
                "explanation": _explanation(entry, scenario, rank),
            },
            offered_at=datetime.now(timezone.utc),
        )
        session.add(offer)
        created.append(offer)
    session.flush()
    transition_package(session, actor=actor, package_id=package.id, action="offer")
    for offer in created:
        record_event(
            session,
            actor,
            "dispatch_offer_created",
            offer,
            {
                "mode": "match",
                "rank": offer.match_breakdown["rank"],
                "scenario": scenario,
                "rule_version_no": version.version_no,
                "candidate_user_id": offer.candidate_user_id,
            },
        )
    return {
        "scenario": "A" if scenario == "onsite" else "B",
        "offers": [
            {
                "offer_id": offer.id,
                "candidate_user_id": offer.candidate_user_id,
                "rank": offer.match_breakdown["rank"],
                "explanation": offer.match_breakdown["explanation"],
            }
            for offer in created
        ],
        "rejected": [item["profile"].user_id for item in rejected],
        "rule_version": version.version_no,
    }
