"""AI 派单建议腿（AI 原生化 N3c G-06，任务书 §15 序 4）：规则引擎旁挂返件式建议。

并列双来源、闸唯一（N3b ADR 同构拍板，2026-11-12 蔡工交互拍板四项之一）：

- **规则腿照常出**——两段式 Stage A→Stage B 排序单一真身
  ``matching._stage_b_ranked``（与 ``match_package`` 共用），规则结果
  不落库照常可展示；无已公示规则版本 ⇒ 422 rule_version_required
  （§11.1 降级态与 match 同尺）；
- **AI 腿返件式零落库**——同输入域（Stage A 过闸候选的结构化快照）产出
  叠加建议；本模块零业务写路径（不写 dispatch_offers／不改包状态）＝
  判据「AI 不自动派单」的结构保证；采纳＝人工按建议走既有指派/发布
  （责任主体天然记人），显式采纳/驳回留痕走纯事件
  ``record_recommendation_decision``（只落 operation_events，零业务写）；
- 机制沿 N3a/N3b 先例：``execute_ai_prompt`` 单一入口（purpose＋
  prompt_version 归因）＋输出契约闭集校验（candidate ∈ Stage A 过闸
  集合、rank 全序、rationale 限长；重试一次仍违 ⇒ 409
  ai_dispatch_contract_failed）＋输出端兜底脱敏（词典故障/凭据串
  fail-closed 422）。

Stage A 零过闸（场景 C）不调 AI 直接返回（零烧费）；候选超过
``MAX_AI_CANDIDATES`` 按规则序截断建议腿可见面（规则腿不受影响，
truncated 如实随响应）。
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from uuid import uuid4

from fde_api.ai.prompt_registry import version_of
from fde_api.auth.models import User
from fde_api.control.ai_server_client import execute_ai_prompt
from fde_api.control.dsh_runtime import DSHRuntimeError
from fde_api.dispatch.errors import DispatchServiceError
from fde_api.dispatch.matching import (
    _client_city,
    _explanation,
    _stage_a,
    _stage_b_ranked,
)
from fde_api.dispatch.models import DeliveryPackage, resolve_onsite_required
from fde_api.dispatch.rules import active_rule_version
from fde_api.guidance.enterprise_dict import RedactionConfigError
from fde_api.guidance.redaction import SensitiveCredentialDetected, redact_text_detailed
from fde_api.projects.events import record_event
from fde_api.system_configuration import DISPATCH_CONSTANTS
from fde_api.workbench.models import Project, Quote

# 提示词版本（N2 归因纪律；提示词正文改动必须升版本）。
# N6/G-13：标签唯一权威＝ai/prompt_registry.py（正文改动必同步注册表升版本）。
RECOMMEND_PROMPT_VERSION = version_of("fde_api.dispatch.recommend_ai", "DISPATCH_RECOMMENDATION_SYSTEM_PROMPT")
# 审计 purpose（ai_call_audits NOT NULL CHECK；≤60 字自由文本域）。
RECOMMEND_PURPOSE = "dispatch_recommendation"
# AI 可见候选上限（建议腿可见面截断边界，ADR §8 预授权风格）——规则腿
# 不受影响，truncated 标志如实随响应。
MAX_AI_CANDIDATES = 50
MAX_RATIONALE_CHARS = 200

_TRANSIENT_RETRY_CODES = frozenset(
    {"ai_rate_limited", "ai_timeout", "ai_service_unavailable", "ai_unavailable"}
)
_RETRY_BACKOFF_SECONDS = 1.0
# 契约/JSON 失败即时重试上限（概率性畸形输出——discovery/quality 同值）。
_CONTRACT_RETRY_LIMIT = 1

DISPATCH_RECOMMENDATION_SYSTEM_PROMPT = f"""你是交付派单的推荐助手。输入是单个交付包的结构化撮合上下文，以及资格门（Stage A）已通过的候选人结构化快照（含规则引擎 Stage B 排序结果）。你只做排序建议，不是决策者：最终派单永远由人工采纳完成。

只输出一个 JSON 对象，形如：
{{"suggestions": [{{"candidate_user_id": "<候选id>", "rank": 1, "rationale": "<理由>"}}]}}

规则：
- candidate_user_id 必须逐字取自输入候选列表，不得发明、不得改写；建议列表是候选子集（按推荐顺序排列）。
- rank 是整数，从 1 开始严格递增，不得重复。
- rationale 不超过 {MAX_RATIONALE_CHARS} 字，只能引用输入中出现的结构化字段（等级/行业/模块标签/地理档位/在途与产能/规则分/新人围栏），不得虚构任何事实。
- 输出只能是上述 JSON 对象，不要输出其他文字。"""


class DispatchRecommendationContractError(Exception):
    """AI 建议输出违反闭集契约（整批拒；重试一次仍违 ⇒ 409）。"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def validate_dispatch_recommendation(
    payload: Any, valid_candidate_ids: set[str]
) -> list[dict[str, Any]]:
    """输出契约闭集校验＋确定性归一化（rank 升序；#209 组序教训同裁）。

    契约：恰 ``{"suggestions": [...]}``；每条恰 ``{candidate_user_id, rank,
    rationale}``；candidate ∈ Stage A 过闸闭集且不重复；rank 为 1..N 全序
    排列；rationale strip 后 1..MAX_RATIONALE_CHARS。违规抛
    ``DispatchRecommendationContractError``（code 进 409 detail）。
    """
    if not isinstance(payload, dict) or set(payload) != {"suggestions"}:
        raise DispatchRecommendationContractError("top_level_shape")
    suggestions = payload["suggestions"]
    if not isinstance(suggestions, list) or not suggestions:
        raise DispatchRecommendationContractError("suggestions_shape")
    if len(suggestions) > len(valid_candidate_ids):
        raise DispatchRecommendationContractError("suggestions_overflow")
    seen_ids: set[str] = set()
    ranks: list[int] = []
    items: list[dict[str, Any]] = []
    for entry in suggestions:
        if not isinstance(entry, dict) or set(entry) != {
            "candidate_user_id",
            "rank",
            "rationale",
        }:
            raise DispatchRecommendationContractError("item_shape")
        candidate_id = entry["candidate_user_id"]
        rank = entry["rank"]
        rationale = entry["rationale"]
        if not isinstance(candidate_id, str) or candidate_id not in valid_candidate_ids:
            raise DispatchRecommendationContractError("candidate_closed_set")
        if candidate_id in seen_ids:
            raise DispatchRecommendationContractError("candidate_duplicate")
        if type(rank) is not int or rank < 1:
            raise DispatchRecommendationContractError("rank_shape")
        if not isinstance(rationale, str) or not (
            1 <= len(rationale.strip()) <= MAX_RATIONALE_CHARS
        ):
            raise DispatchRecommendationContractError("rationale_shape")
        seen_ids.add(candidate_id)
        ranks.append(rank)
        items.append(
            {
                "candidate_user_id": candidate_id,
                "rank": rank,
                "rationale": rationale.strip(),
            }
        )
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        raise DispatchRecommendationContractError("rank_permutation")
    items.sort(key=lambda item: item["rank"])
    return items


def _candidate_snapshot(ranked: list[tuple]) -> list[dict[str, Any]]:
    """Stage A 过闸候选的结构化快照（AI 可见面）。

    只含结构化字段：零姓名/零展示名/零客户真实资料——候选人身份对模型
    只以 user_id（不透明 id）出现，身份类信息不进提示词。
    """
    snapshot: list[dict[str, Any]] = []
    for rule_rank, (_key, entry, stage_b) in enumerate(
        ranked[:MAX_AI_CANDIDATES], start=1
    ):
        profile = entry["profile"]
        snapshot.append(
            {
                "candidate_user_id": profile.user_id,
                "level": profile.level,
                "industry_tags": sorted(str(tag) for tag in (profile.industry_tags or [])),
                "module_tags": sorted(str(tag) for tag in (profile.module_tags or [])),
                "home_city": profile.home_city,
                "geo_tier": entry["tier"],
                "in_fence_city": profile.home_city == entry["client_city"],
                "newcomer_city_only": bool(entry["gates"]["A5"]["newcomer_city_only"]),
                "rule_rank": rule_rank,
                "rule_stage_b": stage_b,
            }
        )
    return snapshot


def _build_user_prompt(
    *,
    package: DeliveryPackage,
    scenario: str,
    client_city: str | None,
    snapshot: list[dict[str, Any]],
    truncated: bool,
) -> str:
    context = {
        "package": {
            "required_level": package.required_level,
            "required_industry": package.required_industry,
            "scenario": scenario,
            "client_city": client_city,
            "dispatch_round": package.dispatch_round,
        },
        "candidates": snapshot,
        "notes": (
            "候选已全部通过 Stage A 资格门；rule_rank/rule_stage_b 为规则引擎排序结果，"
            "可参考亦可偏离，但理由只能引用输入字段。"
            + (
                f"候选超过上限 {MAX_AI_CANDIDATES} 名已按规则序截断，仅列前 {MAX_AI_CANDIDATES} 名。"
                if truncated
                else ""
            )
        ),
    }
    return json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _suggestions_sha256(suggestions: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        suggestions, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _run_recommend_ai(
    *,
    user_id: str,
    project_id: str,
    prompt: str,
    execution_id: str,
    valid_candidate_ids: set[str],
) -> tuple[list[dict[str, Any]], str | None]:
    """完整建议调用（克隆 quality/draft ``_run_draft_ai`` 纪律）。

    概率性契约/JSON 失败即时重试一次；瞬时错误退避重试一次。成功返回
    （归一化建议, 模型名）；不可恢复失败上抛
    ``DispatchRecommendationContractError`` / ``json.JSONDecodeError`` /
    ``DSHRuntimeError``（由路由面映射 HTTP）。
    """
    attempts = 0
    while True:
        attempts += 1
        try:
            answer: Any = execute_ai_prompt(
                user_id=user_id,
                prompt=prompt,
                system_prompt=DISPATCH_RECOMMENDATION_SYSTEM_PROMPT,
                use_tools=False,
                project_id=project_id,
                execution_id=execution_id,
                purpose=RECOMMEND_PURPOSE,
                prompt_version=RECOMMEND_PROMPT_VERSION,
                return_metadata=True,
            )
            if not isinstance(answer, dict):
                answer = dict(text=answer, model={})
            text = answer.get("text")
            payload = json.loads(text) if isinstance(text, str) else text
            suggestions = validate_dispatch_recommendation(payload, valid_candidate_ids)
            model_name = str(((answer.get("model") or {}).get("name") or "")) or None
            return suggestions, model_name
        except (json.JSONDecodeError, DispatchRecommendationContractError):
            if attempts > _CONTRACT_RETRY_LIMIT:
                raise
            # 概率性契约/JSON 失败：立即重试（discovery/quality 同裁）
        except DSHRuntimeError as error:
            if error.code not in _TRANSIENT_RETRY_CODES or attempts > _CONTRACT_RETRY_LIMIT:
                raise
            time.sleep(_RETRY_BACKOFF_SECONDS)


def recommend_dispatch_package(
    session: Any, *, actor: User, package_id: str
) -> dict[str, Any]:
    """AI 派单建议（返件式零落库；admin/project_lead——与 match 同闸）。

    失败语义（fail-closed，全管线零业务写入——事件留痕除外）：
    - 非平台侧 ⇒ 403 forbidden；包不存在 ⇒ 404；非 published ⇒ 409
      invalid_dispatch_state（与 match 同尺；本路由**不查 offer_exists**
      ——建议是只读叠加，本轮 offer 已在也可比对）；
    - 无已公示规则版本 ⇒ 422 rule_version_required（§11.1 降级态同尺）；
    - Stage A 零过闸 ⇒ 场景 C 直接返回（**不调 AI，零烧费**）；
    - AI 通道/预算/权限 ⇒ ``DSHRuntimeError`` 原样上抛（路由面 503/409 映射）；
    - 契约违规 ⇒ 重试一次仍违 ⇒ 409 ai_dispatch_contract_failed；
    - 词典机制故障 ⇒ 422 pseudonym_dict_unavailable；建议文本命中凭据串 ⇒
      422 sensitive_credential_detected（均 fail-closed，零写入）。
    成功 ⇒ 事件 ``dispatch_ai_recommended``（sha256＋计数，不带建议全文）
    ＋返件（规则腿排序＋AI 建议并列）。
    """
    if actor.role not in ("admin", "project_lead"):
        raise DispatchServiceError("forbidden", "只有平台侧可执行撮合建议。", 403)
    package = session.get(DeliveryPackage, package_id)
    if package is None:
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    if package.dispatch_status != "published":
        raise DispatchServiceError(
            "invalid_dispatch_state",
            f"包状态 {package.dispatch_status} 不能生成撮合建议（需 published）。",
            409,
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
    scenario = "onsite" if resolve_onsite_required(package) else "remote"
    rejected_ids = [item["profile"].user_id for item in rejected]
    if not passed:
        # 场景 C：不自动派也不烧 AI——只读叠加同样无候选可建议（§4.4 同尺）。
        return {
            "scenario": "C",
            "rule_result": {
                "offers": [],
                "rejected": rejected_ids,
                "rule_version": version.version_no,
            },
            "ai_suggestions": [],
            "recommendation_sha256": _suggestions_sha256([]),
            "ai_called": False,
            "model": None,
            "prompt_version": RECOMMEND_PROMPT_VERSION,
            "truncated": False,
        }

    ranked = _stage_b_ranked(
        package=package, version=version, rule=rule, scenario=scenario, passed=passed
    )
    snapshot = _candidate_snapshot(ranked)
    truncated = len(ranked) > MAX_AI_CANDIDATES
    client_city = _client_city(session, package)
    prompt = _build_user_prompt(
        package=package,
        scenario=scenario,
        client_city=client_city,
        snapshot=snapshot,
        truncated=truncated,
    )
    valid_ids = {item["candidate_user_id"] for item in snapshot}
    execution_id = f"dispatch-recommend:{package.id}:{uuid4().hex[:8]}"
    try:
        suggestions, model_name = _run_recommend_ai(
            user_id=actor.id,
            project_id=package.project_id,
            prompt=prompt,
            execution_id=execution_id,
            valid_candidate_ids=valid_ids,
        )
    except (DispatchRecommendationContractError, json.JSONDecodeError) as error:
        detail = getattr(error, "code", None) or "invalid_json"
        raise DispatchServiceError(
            "ai_dispatch_contract_failed",
            f"AI 撮合建议未通过契约校验（已自动重试仍失败：{detail}），请重跑或更换模型。",
            409,
        ) from error
    # ── 输出端兜底脱敏（rationale 是唯一自由文本面；fail-closed 双闸）──
    project = session.get(Project, package.project_id)
    project_code = project.enterprise_code if project else ""
    try:
        for item in suggestions:
            item["rationale"] = redact_text_detailed(
                item["rationale"], project_code=project_code
            ).text
    except SensitiveCredentialDetected as error:
        raise DispatchServiceError(
            "sensitive_credential_detected",
            "AI 建议文本命中疑似凭据串，已整批拒绝。",
            422,
        ) from error
    except RedactionConfigError as error:
        raise DispatchServiceError(
            "pseudonym_dict_unavailable",
            "脱敏词典不可用（fail-closed），建议未生成。",
            422,
        ) from error

    recommendation_sha256 = _suggestions_sha256(suggestions)
    record_event(
        session,
        actor,
        "dispatch_ai_recommended",
        package,
        {
            "recommendation_sha256": recommendation_sha256,
            "candidate_count": len(snapshot),
            "suggestion_count": len(suggestions),
            "scenario": scenario,
            "truncated": truncated,
            "prompt_version": RECOMMEND_PROMPT_VERSION,
            "model": model_name,
        },
    )
    top_n = int(DISPATCH_CONSTANTS["top_n"])
    return {
        "scenario": "A" if scenario == "onsite" else "B",
        "rule_result": {
            # 规则腿照常出（同一 _stage_b_ranked 单一真身）；返件式＝
            # 无 offer_id（不落 dispatch_offers，与 match 的落库面相区分）。
            "offers": [
                {
                    "candidate_user_id": entry["profile"].user_id,
                    "rank": rank,
                    "explanation": _explanation(entry, scenario, rank),
                }
                for rank, (_key, entry, _stage_b) in enumerate(
                    ranked[:top_n], start=1
                )
            ],
            "rejected": rejected_ids,
            "rule_version": version.version_no,
        },
        "ai_suggestions": suggestions,
        "recommendation_sha256": recommendation_sha256,
        "ai_called": True,
        "model": model_name,
        "prompt_version": RECOMMEND_PROMPT_VERSION,
        "truncated": truncated,
    }


def record_recommendation_decision(
    session: Any, *, actor: User, package_id: str, payload: Any
) -> dict[str, Any]:
    """显式采纳/驳回留痕（纯事件端点；N3c G-06 判据「可被人工采纳/驳回」）。

    **零业务写**：采纳的指派动作仍须走既有 offers/publish（责任主体记人
    在那条链上）；本函数只落 operation_events（adopted/rejected 双事件名）
    ＋回显决定。契约：
    - 恰 ``{decision, recommendation_sha256, adopted_candidate_ids}``；
    - decision ∈ {adopted, rejected}；sha256 必须 64 位十六进制（归一化小写）；
    - adopted ⇒ adopted_candidate_ids 必须非空去重字符串列表（≤MAX_AI_CANDIDATES）；
    - rejected ⇒ adopted_candidate_ids 必须为空数组（驳回不收集名单）。
    """
    if actor.role not in ("admin", "project_lead"):
        raise DispatchServiceError("forbidden", "只有平台侧可记录撮合建议决定。", 403)
    package = session.get(DeliveryPackage, package_id)
    if package is None:
        raise DispatchServiceError("package_not_found", "交付包不存在。", 404)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"decision", "recommendation_sha256", "adopted_candidate_ids"}
    ):
        raise DispatchServiceError(
            "invalid_request",
            "请求体必须恰含 decision/recommendation_sha256/adopted_candidate_ids。",
            400,
        )
    decision = payload["decision"]
    raw_sha = payload["recommendation_sha256"]
    adopted = payload["adopted_candidate_ids"]
    if decision not in ("adopted", "rejected"):
        raise DispatchServiceError(
            "invalid_request", "decision 必须是 adopted 或 rejected。", 400
        )
    sha = raw_sha.strip().lower() if isinstance(raw_sha, str) else ""
    if len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha):
        raise DispatchServiceError(
            "invalid_request", "recommendation_sha256 必须是 64 位十六进制指纹。", 400
        )
    if decision == "adopted":
        if (
            not isinstance(adopted, list)
            or not adopted
            or len(adopted) > MAX_AI_CANDIDATES
            or any(
                not isinstance(item, str) or not item.strip() or len(item) > 64
                for item in adopted
            )
            or len(set(adopted)) != len(adopted)
        ):
            raise DispatchServiceError(
                "invalid_request",
                "采纳决定必须带非空去重的 adopted_candidate_ids 字符串列表。",
                400,
            )
    elif adopted != []:
        raise DispatchServiceError(
            "invalid_request", "驳回决定的 adopted_candidate_ids 必须为空数组。", 400
        )
    event_name = (
        "dispatch_ai_recommendation_adopted"
        if decision == "adopted"
        else "dispatch_ai_recommendation_rejected"
    )
    record_event(
        session,
        actor,
        event_name,
        package,
        {
            "recommendation_sha256": sha,
            "adopted_candidate_ids": adopted if decision == "adopted" else [],
        },
    )
    return {
        "decision": decision,
        "package_id": package.id,
        "recommendation_sha256": sha,
    }
