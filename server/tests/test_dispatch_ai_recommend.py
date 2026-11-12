"""AI 原生化 N3c（G-06）：派单建议腿——规则引擎旁挂、返件式零落库。

验收面（任务书 N3c DoD① + G-06 消解判据复测动作）：
- ①并列双来源、闸唯一：规则腿与 ``match_package`` 共用 ``_stage_b_ranked``
  单一真身（回归由 test_dispatch_p1_r5 承载）；响应=规则腿（无 offer_id，
  零落库）＋AI 建议并列；
- ②AI 不自动派单：推荐路径零业务写（dispatch_offers 零行、包状态零变化）
  ——契约失败/脱敏失败同样零残留（fail-closed 家族一致）；
- ③采纳/驳回机械留痕：decision 端点只落 operation_events（adopted/rejected），
  零业务写；采纳的指派动作仍走既有 offers/publish（责任主体记人在那条链，
  既有用例承载）；
- ④单一入口＋归因（N2）：打桩 kwargs 钉 purpose/prompt_version/execution_id；
  J-1 白名单 DISPATCH_RECOMMENDATION_SYSTEM_PROMPT 钉见
  test_prompt_entrypoint_gate；
- ⑤前置闸全在 AI 调用前（零烧费）：场景 C 不调 AI；422/409/404/403 同尺。
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from fde_api.auth.models import User
from fde_api.auth.passwords import hash_password
from fde_api.auth.tokens import issue_access_token
from fde_api.control.dsh_runtime import DSHRuntimeError
from fde_api.dispatch import recommend_ai
from fde_api.dispatch.matching import match_package
from fde_api.dispatch.models import DeliveryPackage, DispatchOffer, DispatchRuleVersion, FdeProfile
from fde_api.dispatch.packages import create_package, publish_package
from fde_api.guidance.enterprise_dict import RedactionConfigError
from fde_api.workbench.models import (
    IndustryTemplate,
    IndustryTemplateVersion,
    OperationEvent,
    Project,
    Quote,
)
from sqlalchemy.orm import Session

from fde_api.solutions.models import ProjectSolution

from conftest import INITIAL_PASSWORD


def _user(username: str, role: str = "admin") -> User:
    return User(
        username=f"{username}.{uuid4().hex[:8]}",
        display_name=username,
        role=role,
        password_hash=hash_password(INITIAL_PASSWORD),
        must_change_password=False,
        is_active=True,
    )


class _Client:
    def __init__(self, client, user: User, headers: dict[str, str]):
        self.client = client
        self.user = user
        self.headers = headers

    def post(self, *args, **kwargs):
        return self.client.post(*args, headers=self.headers, **kwargs)


def _authorized(client, settings, user: User) -> _Client:
    return _Client(
        client, user, {"Authorization": f"Bearer {issue_access_token(user, settings)}"}
    )


def _profile(
    db_session,
    user: User,
    *,
    level: str | None = "L2",
    industry_tags: list[str] | None = None,
    home_city: str | None = "苏州",
    capacity: int = 100,
    avg_hours: int = 10,
) -> FdeProfile:
    db_session.add(user)
    row = FdeProfile(
        user_id=user.id,
        level=level,
        module_tags=[],
        industry_tags=industry_tags or ["制造业"],
        home_city=home_city,
        monthly_capacity_hours=capacity,
        avg_delivery_hours=avg_hours,
        status="active",
        is_active=True,
    )
    db_session.add(row)
    return row


def retire_active_rule_versions(db_session) -> None:
    """先退役常驻 active 行再自植（同 r5：active_rule_version scalar 无排序）。"""
    db_session.execute(
        update(DispatchRuleVersion)
        .where(DispatchRuleVersion.status == "active")
        .values(status="retired")
    )
    db_session.flush()


def _active_rule(db_session) -> DispatchRuleVersion:
    retire_active_rule_versions(db_session)
    row = DispatchRuleVersion(
        version_no=1,
        status="active",
        rule_snapshot={
            "stage_b_weights": {"level": 40, "industry": 30, "sla": 20, "geo_remote": 10},
            "level_score_map": {"L1": 40, "L2": 60, "L3": 80, "L4": 100},
            "seat_shares": {"platform": 35, "region": 5, "city": 20, "delivery": 40},
        },
        effective_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(row)
    db_session.flush()
    return row


def _published_package(
    db_session, *, remote: bool = False
) -> tuple[User, DeliveryPackage]:
    """admin + finalized 报价 + published 交付包（b1/r5 三件套口径）。"""
    admin = _user("n3c.admin")
    template = IndustryTemplate(
        template_key=f"n3c-tpl-{uuid4().hex[:8]}",
        name="n3c 模板",
        industry_name="制造业",
    )
    version = IndustryTemplateVersion(
        template=template,
        name="n3c 模板 v1",
        industry_name="制造业",
        version_number=1,
        status="published",
    )
    project = Project(
        project_code=f"N3C-{uuid4().hex[:6].upper()}",
        name="n3c 建议腿项目",
        enterprise_code="n3c 客户·制造·苏州",
        business_line="FDE_DISPATCH",
        planned_start_date=date(2026, 10, 31),
        leader_user_id=admin.id,
        source_template_version=version,
        template_snapshot={"industry_name": "制造业", "modules": []},
    )
    db_session.add_all([admin, project])
    db_session.flush()
    solution = ProjectSolution(
        project_id=project.id,
        name="n3c 方案",
        schedule="远程交付" if remote else "需到场实施",
        owner_user_id=admin.id,
    )
    db_session.add(solution)
    db_session.flush()
    quote = Quote(
        project_id=project.id,
        quote_key=f"Q-{uuid4().hex[:8]}",
        status="finalized",
        tier="standard",
        ideal_hours=Decimal("100"),
        realistic_hours=Decimal("100"),
        integration_factor=Decimal("1.00"),
        data_factor=Decimal("1.00"),
        compliance_factor=Decimal("1.00"),
        buffer_factor=Decimal("1.00"),
        hourly_rate=150,
        cash_cost=100000,
        margin_factor=Decimal("1.40"),
        b_layer_score=5,
        b_layer_factor=Decimal("1.00"),
        anchor_mode="steady",
        labor_cost=Decimal("100000"),
        total_cost=Decimal("100000"),
        formula_price=Decimal("200000"),
        anchor_low=200000,
        anchor_high=300000,
        branch="A",
        final_amount=Decimal("20000"),
        field_claims={"final_amount": "measured"},
    )
    db_session.add(quote)
    db_session.flush()
    package = create_package(
        db_session, actor=admin, solution_id=solution.id, quote_id=quote.id
    )
    db_session.flush()
    publish_package(db_session, actor=admin, package_id=package.id)
    db_session.flush()
    return admin, package


def _two_candidates(db_session) -> tuple[User, User]:
    cand_a = _user("n3c.candA", role="fde_engineer")
    cand_b = _user("n3c.candB", role="fde_engineer")
    _profile(db_session, cand_a, level="L3")
    _profile(db_session, cand_b, level="L2")
    return cand_a, cand_b


def _patch_ai(monkeypatch, outputs: list, calls: list) -> None:
    """固定输出序列打桩（quality N3a 同法）：dict=合法 payload；str=畸形原文；
    Exception=上抛；**末项对后续重试粘性复用**。time.sleep 一并钳零。"""
    state = {"i": 0}

    def _fake_execute(**kwargs):
        calls.append(kwargs)
        item = outputs[min(state["i"], len(outputs) - 1)]
        state["i"] += 1
        if isinstance(item, Exception):
            raise item
        if isinstance(item, dict):
            item = json.dumps(item, ensure_ascii=False)
        return {"text": item, "model": {"provider": "test", "name": "test-model"}, "provider_usage": {}}

    monkeypatch.setattr(recommend_ai, "execute_ai_prompt", _fake_execute)
    monkeypatch.setattr(recommend_ai.time, "sleep", lambda _seconds: None)


def _recommend(admin_client: _Client, package: DeliveryPackage):
    return admin_client.post(f"/api/v1/dispatch/packages/{package.id}/match-ai")


def _offers_of_package(db_session: Session, package: DeliveryPackage) -> list[DispatchOffer]:
    return list(
        db_session.scalars(
            select(DispatchOffer).where(DispatchOffer.package_id == package.id)
        )
    )


def _events(db_session: Session, event_type: str, package: DeliveryPackage) -> list[OperationEvent]:
    return list(
        db_session.scalars(
            select(OperationEvent).where(
                OperationEvent.event_type == event_type,
                OperationEvent.target_id == package.id,
            )
        )
    )


# ---------------------------------------------------------------------------
# 成功路径：并列双来源＋返件式零落库＋溯源留痕


def test_match_ai_happy_path_rule_plus_ai_zero_business_write(db_session, client, settings, monkeypatch) -> None:
    admin, package = _published_package(db_session)
    cand_a, cand_b = _two_candidates(db_session)
    _active_rule(db_session)
    db_session.commit()
    calls: list = []
    _patch_ai(
        monkeypatch,
        [
            {
                "suggestions": [
                    {"candidate_user_id": cand_b.id, "rank": 2, "rationale": " 等级 L2 达标，同城候选。"},
                    {"candidate_user_id": cand_a.id, "rank": 1, "rationale": "等级 L3 更高，同城候选。"},
                ]
            }
        ],
        calls,
    )
    response = _recommend(_authorized(client, settings, admin), package)
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]

    # 并列双来源：规则腿照常出（同一排序真身），AI 建议并列且 rank 归一升序
    assert data["scenario"] == "A"
    assert data["rule_result"]["rule_version"] == 1
    rule_ranks = [offer["rank"] for offer in data["rule_result"]["offers"]]
    assert rule_ranks == sorted(rule_ranks) and len(rule_ranks) == 2
    assert all("offer_id" not in offer for offer in data["rule_result"]["offers"]), "返件式：规则腿无 offer_id"
    suggestions = data["ai_suggestions"]
    assert [item["rank"] for item in suggestions] == [1, 2]
    assert suggestions[0]["candidate_user_id"] == cand_a.id
    assert suggestions[0]["rationale"] == "等级 L3 更高，同城候选。", "rationale strip 归一"
    assert data["prompt_version"] == recommend_ai.RECOMMEND_PROMPT_VERSION
    assert data["model"] == "test-model"
    assert data["ai_called"] is True and data["truncated"] is False

    # ②AI 不自动派单：dispatch_offers 零行＋包状态零变化（零业务写）
    assert _offers_of_package(db_session, package) == []
    db_session.flush()
    assert db_session.get(DeliveryPackage, package.id).dispatch_status == "published"

    # ④溯源（N2）：事件带 sha256/计数/版本/模型，不带建议全文
    events = _events(db_session, "dispatch_ai_recommended", package)
    assert len(events) == 1
    changes = events[0].changes
    assert changes["recommendation_sha256"] == data["recommendation_sha256"]
    assert len(changes["recommendation_sha256"]) == 64
    assert changes["suggestion_count"] == 2 and changes["candidate_count"] == 2
    assert changes["prompt_version"] == recommend_ai.RECOMMEND_PROMPT_VERSION
    assert changes["model"] == "test-model"
    assert "rationale" not in json.dumps(changes, ensure_ascii=False), "事件不带建议全文"

    # ①单一入口钉证：purpose/prompt_version/execution_id/use_tools
    call = calls[0]
    assert call["purpose"] == "dispatch_recommendation"
    assert call["prompt_version"] == recommend_ai.RECOMMEND_PROMPT_VERSION
    assert call["use_tools"] is False
    assert call["execution_id"].startswith("dispatch-recommend:")
    # 候选闭集进提示词（只有 id，零姓名/零展示名）
    assert cand_a.id in call["prompt"] and cand_b.id in call["prompt"]
    assert "n3c.candA" not in call["prompt"] and "n3c.candB" not in call["prompt"]


def test_match_ai_rule_leg_matches_match_package_ranking(db_session) -> None:
    """并列双来源的「同输入域」：建议腿规则序与 match_package 完全一致。"""
    from fde_api.dispatch.matching import _stage_a, _stage_b_ranked
    from fde_api.dispatch.models import resolve_onsite_required
    from fde_api.dispatch.recommend_ai import _build_user_prompt, _candidate_snapshot

    admin, package = _published_package(db_session)
    _two_candidates(db_session)
    version = _active_rule(db_session)
    rule = dict(version.rule_snapshot or {})
    quote = db_session.get(Quote, package.quote_id)
    rule["_required_industry"] = package.required_industry
    passed, _rejected = _stage_a(db_session, package, quote)
    scenario = "onsite" if resolve_onsite_required(package) else "remote"
    ranked = _stage_b_ranked(
        package=package, version=version, rule=rule, scenario=scenario, passed=passed
    )
    # 经 match_package 落库的规则序与建议腿排序真身同源（单一真身）
    result = match_package(db_session, actor=admin, package_id=package.id)
    match_ids = [offer["candidate_user_id"] for offer in result["offers"]]
    snapshot = _candidate_snapshot(ranked)
    snap_ids = [item["candidate_user_id"] for item in snapshot]
    assert match_ids == snap_ids, "Stage B 单一真身：两腿规则序逐位一致"
    prompt = _build_user_prompt(
        package=package,
        scenario=scenario,
        client_city="苏州",
        snapshot=snapshot,
        truncated=False,
    )
    assert all(item["candidate_user_id"] in prompt for item in snapshot)


# ---------------------------------------------------------------------------
# 前置闸全在 AI 调用前（零烧费）＋失败零写入


def test_match_ai_scenario_c_skips_ai_call(db_session, client, settings, monkeypatch) -> None:
    admin, package = _published_package(db_session)
    _active_rule(db_session)
    db_session.commit()
    calls: list = []
    _patch_ai(monkeypatch, [{"suggestions": []}], calls)
    response = _recommend(_authorized(client, settings, admin), package)
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["scenario"] == "C"
    assert data["ai_suggestions"] == [] and data["ai_called"] is False
    assert calls == [], "场景 C 不调 AI（零烧费）"
    assert _offers_of_package(db_session, package) == []


def test_match_ai_pregates_same_ruler_as_match(db_session, client, settings, monkeypatch) -> None:
    admin, package = _published_package(db_session)
    fde = _user("n3c.fde", role="fde_engineer")
    db_session.add(fde)
    db_session.flush()
    db_session.commit()
    fde_client = _authorized(client, settings, fde)
    assert _recommend(fde_client, package).status_code == 403, "非平台侧 403（与 match 同闸）"
    other = _authorized(client, settings, admin)
    missing = other.post("/api/v1/dispatch/packages/does-not-exist/match-ai")
    assert missing.status_code == 404 and missing.get_json()["error"]["code"] == "package_not_found"

    # draft 包（未发布）→ 409 invalid_dispatch_state
    draft_admin, draft_package = _published_package(db_session)
    draft_package.dispatch_status = "draft"
    db_session.commit()
    draft_response = _recommend(_authorized(client, settings, draft_admin), draft_package)
    assert draft_response.status_code == 409
    assert draft_response.get_json()["error"]["code"] == "invalid_dispatch_state"

    # §11.1 降级态：无已公示规则版本 → 422 rule_version_required
    admin2, package2 = _published_package(db_session)
    retire_active_rule_versions(db_session)
    db_session.commit()
    calls: list = []
    _patch_ai(monkeypatch, [{"suggestions": []}], calls)
    response = _recommend(_authorized(client, settings, admin2), package2)
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "rule_version_required"
    assert calls == [], "降级态不烧 AI"


def test_match_ai_contract_fail_retry_once_then_409_zero_write(db_session, client, settings, monkeypatch) -> None:
    admin, package = _published_package(db_session)
    cand_a, _cand_b = _two_candidates(db_session)
    _active_rule(db_session)
    db_session.commit()
    calls: list = []
    # 第一发：闭集外候选；第二发（重试）：rank 非全序——粘性复用后仍 409
    _patch_ai(
        monkeypatch,
        [
            {"suggestions": [{"candidate_user_id": "ghost-id", "rank": 1, "rationale": "闭集外"}]},
            {"suggestions": [{"candidate_user_id": cand_a.id, "rank": 7, "rationale": "rank 越界"}]},
        ],
        calls,
    )
    response = _recommend(_authorized(client, settings, admin), package)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"]["code"] == "ai_dispatch_contract_failed"
    assert len(calls) == 2, "契约失败即时重试一次"
    assert _offers_of_package(db_session, package) == []
    assert _events(db_session, "dispatch_ai_recommended", package) == [], "失败零事件零残留"
    assert db_session.get(DeliveryPackage, package.id).dispatch_status == "published"


def test_match_ai_transient_retry_recovers(db_session, client, settings, monkeypatch) -> None:
    admin, package = _published_package(db_session)
    cand_a, cand_b = _two_candidates(db_session)
    _active_rule(db_session)
    db_session.commit()
    calls: list = []
    _patch_ai(
        monkeypatch,
        [
            DSHRuntimeError("ai_rate_limited", "限流", retryable=True),
            {
                "suggestions": [
                    {"candidate_user_id": cand_a.id, "rank": 1, "rationale": "重试后成功"},
                    {"candidate_user_id": cand_b.id, "rank": 2, "rationale": "次序合理"},
                ]
            },
        ],
        calls,
    )
    response = _recommend(_authorized(client, settings, admin), package)
    assert response.status_code == 200, response.get_json()
    assert len(calls) == 2 and len(response.get_json()["data"]["ai_suggestions"]) == 2


def test_match_ai_terminal_dsh_error_maps_409(db_session, client, settings, monkeypatch) -> None:
    admin, package = _published_package(db_session)
    _two_candidates(db_session)
    _active_rule(db_session)
    db_session.commit()
    _patch_ai(monkeypatch, [DSHRuntimeError("ai_access_denied", "无权限", retryable=False)], [])
    response = _recommend(_authorized(client, settings, admin), package)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "ai_access_denied"


def test_match_ai_redaction_fail_closed(db_session, client, settings, monkeypatch) -> None:
    """输出端兜底脱敏：凭据串 422 sensitive_credential_detected；
    词典机制故障 422 pseudonym_dict_unavailable——均零写入。"""
    admin, package = _published_package(db_session)
    cand_a, cand_b = _two_candidates(db_session)
    _active_rule(db_session)
    db_session.commit()
    calls: list = []
    _patch_ai(
        monkeypatch,
        [
            {
                "suggestions": [
                    {"candidate_user_id": cand_a.id, "rank": 1, "rationale": "密钥: abcdefghijkl1234 可用"},
                    {"candidate_user_id": cand_b.id, "rank": 2, "rationale": "同城候选"},
                ]
            }
        ],
        calls,
    )
    response = _recommend(_authorized(client, settings, admin), package)
    assert response.status_code == 422, response.get_json()
    assert response.get_json()["error"]["code"] == "sensitive_credential_detected"
    assert _offers_of_package(db_session, package) == []
    assert _events(db_session, "dispatch_ai_recommended", package) == []

    # 词典机制故障：redact_text_detailed 上抛 RedactionConfigError → 422 fail-closed
    def _broken_redact(_value, *, project_code=""):
        raise RedactionConfigError("词典缺失")

    monkeypatch.setattr(recommend_ai, "redact_text_detailed", _broken_redact)
    response2 = _recommend(_authorized(client, settings, admin), package)
    assert response2.status_code == 422
    assert response2.get_json()["error"]["code"] == "pseudonym_dict_unavailable"


def test_match_ai_truncation_flag_and_visible_set(db_session, client, settings, monkeypatch) -> None:
    """候选超过上限：建议腿可见面按规则序截断（规则腿不受影响）。"""
    admin, package = _published_package(db_session)
    cand_a, cand_b = _two_candidates(db_session)
    _active_rule(db_session)
    db_session.commit()
    monkeypatch.setattr(recommend_ai, "MAX_AI_CANDIDATES", 1)
    calls: list = []
    _patch_ai(
        monkeypatch,
        [{"suggestions": [{"candidate_user_id": cand_a.id, "rank": 1, "rationale": "规则序首位"}]}],
        calls,
    )
    response = _recommend(_authorized(client, settings, admin), package)
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["truncated"] is True
    assert len(data["rule_result"]["offers"]) == 2, "规则腿不截断"
    assert len(data["ai_suggestions"]) == 1
    # 闭集=截断后可见面：闭集外候选进建议 → 契约拒
    calls2: list = []
    _patch_ai(
        monkeypatch,
        [{"suggestions": [{"candidate_user_id": cand_b.id, "rank": 1, "rationale": "被截断者"}]}],
        calls2,
    )
    response2 = _recommend(_authorized(client, settings, admin), package)
    assert response2.status_code == 409
    assert response2.get_json()["error"]["code"] == "ai_dispatch_contract_failed"


# ---------------------------------------------------------------------------
# decision 端点：采纳/驳回机械留痕（纯事件，零业务写）


def _sha() -> str:
    return "ab" * 32


def test_decision_adopted_and_rejected_event_only(db_session, client, settings) -> None:
    admin, package = _published_package(db_session)
    db_session.commit()
    admin_client = _authorized(client, settings, admin)
    response = admin_client.post(
        f"/api/v1/dispatch/packages/{package.id}/match-ai/decision",
        json={"decision": "adopted", "recommendation_sha256": _sha(), "adopted_candidate_ids": ["u-1", "u-2"]},
    )
    assert response.status_code == 200, response.get_json()
    adopted = _events(db_session, "dispatch_ai_recommendation_adopted", package)
    assert len(adopted) == 1
    assert adopted[0].changes == {"recommendation_sha256": _sha(), "adopted_candidate_ids": ["u-1", "u-2"]}
    assert _offers_of_package(db_session, package) == [], "decision 端点零业务写"

    response2 = admin_client.post(
        f"/api/v1/dispatch/packages/{package.id}/match-ai/decision",
        json={"decision": "rejected", "recommendation_sha256": _sha(), "adopted_candidate_ids": []},
    )
    assert response2.status_code == 200
    rejected = _events(db_session, "dispatch_ai_recommendation_rejected", package)
    assert len(rejected) == 1 and rejected[0].changes["adopted_candidate_ids"] == []
    assert db_session.get(DeliveryPackage, package.id).dispatch_status == "published"


def test_decision_validation_matrix(db_session, client, settings) -> None:
    admin, package = _published_package(db_session)
    db_session.commit()
    admin_client = _authorized(client, settings, admin)
    url = f"/api/v1/dispatch/packages/{package.id}/match-ai/decision"

    def _post(payload):
        return admin_client.post(url, json=payload)

    assert _post({"decision": "maybe", "recommendation_sha256": _sha(), "adopted_candidate_ids": []}).status_code == 400
    assert _post({"decision": "adopted", "recommendation_sha256": "nothex", "adopted_candidate_ids": ["u-1"]}).status_code == 400
    assert _post({"decision": "adopted", "recommendation_sha256": _sha(), "adopted_candidate_ids": []}).status_code == 400, "采纳必须带名单"
    assert _post({"decision": "rejected", "recommendation_sha256": _sha(), "adopted_candidate_ids": ["u-1"]}).status_code == 400, "驳回不带名单"
    assert _post({"decision": "adopted", "recommendation_sha256": _sha()}).status_code == 400, "恰三键"
    assert _post(
        {"decision": "adopted", "recommendation_sha256": _sha(), "adopted_candidate_ids": ["dup", "dup"]}
    ).status_code == 400, "名单去重"

    fde = _user("n3c.fde2", role="fde_engineer")
    db_session.add(fde)
    db_session.flush()
    db_session.commit()
    fde_response = _authorized(client, settings, fde).post(
        url, json={"decision": "adopted", "recommendation_sha256": _sha(), "adopted_candidate_ids": ["u-1"]}
    )
    assert fde_response.status_code == 403
    missing = admin_client.post(
        "/api/v1/dispatch/packages/does-not-exist/match-ai/decision",
        json={"decision": "adopted", "recommendation_sha256": _sha(), "adopted_candidate_ids": ["u-1"]},
    )
    assert missing.status_code == 404


# ---------------------------------------------------------------------------
# api_catalog 登记钉（dispatch 域「路由不得脱册」＋AI 不代拍板）


def test_new_routes_registered_in_api_catalog(client) -> None:
    """N3c 两条新路由必须在 api_catalog 登记（dispatch 域脱册钉）。

    建议腿：普通写（risk 1，不确认）——它只返建议，零业务写；
    终审留痕端点：**确认类**（risk 3）——AI 侧发起即待人工密码确认，
    AI 不代拍板（DoD①「人工终审不可绕过」的机械面）。
    """
    import re

    from fde_api.control.api_catalog import CATALOG

    match_ai = CATALOG["dispatch.packages_match_ai"]
    assert match_ai["method"] == "POST"
    assert match_ai["path"] == "/api/v1/dispatch/packages/{package_id}/match-ai"
    assert match_ai["effect"] == "write_db" and match_ai["risk"] == 1
    assert match_ai["confirmation"] is False

    decision = CATALOG["dispatch.packages_match_ai_decision"]
    assert decision["method"] == "POST"
    assert decision["path"] == "/api/v1/dispatch/packages/{package_id}/match-ai/decision"
    assert decision["effect"] == "write_db"
    assert decision["confirmation"] is True
    assert decision["risk"] == 3

    # 目录条目与真实路由逐位一致（防目录漂移）
    def _normalize(path: str) -> str:
        return re.sub(r"<(?:[^:<>]+:)?([^<>]+)>", lambda m: "{" + m.group(1) + "}", path)

    rules = {
        (method, _normalize(rule.rule))
        for rule in client.application.url_map.iter_rules()
        for method in (rule.methods - {"HEAD", "OPTIONS"})
    }
    assert ("POST", "/api/v1/dispatch/packages/{package_id}/match-ai") in rules
    assert ("POST", "/api/v1/dispatch/packages/{package_id}/match-ai/decision") in rules
