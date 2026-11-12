"""获客诊断工具 T-10a：匿名诊断面（数据模型 + 问卷 + 政策补贴测算卡 + 闸）。

本仓**第一个公网免注册写面**——因此这组用例守的是「匿名面不许被悄悄放开」：

- 部署闸默认**关闭** ⇒ 路由 404（不确认面存在）；
- 令牌**只存指纹**、IP**只存假名**（库泄漏 ≠ 会话被接管）；
- **零外键指向 projects**（线索 ≠ 项目）；
- 配额双闸（每 IP 每日 / 每令牌），Redis 故障**默认 fail-closed**；
- 测算卡**不落金额、不落分数**（R-1 / R-4），原文口径与我方解读**分层**；
- 答案过脱敏管线（企业名不入库）。

这些用例不联网、不调模型——T-10a 是纯规则层。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from redis.exceptions import RedisError
from sqlalchemy import select

from fde_api.auth.models import Base
from fde_api.diagnostics.models import LeadDiagnosticSession
from fde_api.diagnostics.service import hash_token

TOKEN_HEADER = "X-Diagnostic-Token"


class _FakeRedis:
    """最小 incr/expire/ttl/delete 语义（沿登录限流测试同款）。"""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    def ttl(self, key: int | str) -> int:
        return self.ttls.get(str(key), 86400)

    def delete(self, *keys: str) -> None:
        for key in keys:
            self.counters.pop(key, None)
            self.ttls.pop(key, None)


class _BrokenRedis:
    def incr(self, key: str) -> int:
        raise RedisError("connection refused")

    def expire(self, key: str, seconds: int) -> None:
        raise RedisError("connection refused")

    def ttl(self, key: str) -> int:
        raise RedisError("connection refused")

    def delete(self, *keys: str) -> None:
        raise RedisError("connection refused")


FIRST_SCREEN_READY = {
    "org.industry": "制造与工业",
    "org.scale": "100–499人",
    "pol.qualification": ["规上工业企业"],
    "pol.declaration_history": "从未申报过",
    "pol.digitalization_project": "已有在推进的数字化改造",
}


@pytest.fixture
def diag_app(app):
    """打开诊断面（部署闸开）+ 假 Redis（配额闸可测）。"""
    app.config["SETTINGS"] = app.config["SETTINGS"].model_copy(
        update={"diagnostics_enabled": True, "diagnostics_rate_fail_closed": True}
    )
    app.extensions["fde_api_redis"] = _FakeRedis()
    return app


@pytest.fixture
def diag_client(diag_app):
    return diag_app.test_client()


def _create(diag_client, **kwargs) -> str:
    response = diag_client.post("/api/v1/diagnostics/sessions", json=kwargs)
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]["token"]


def _assess(diag_client, token: str, answers: dict):
    return diag_client.post(
        "/api/v1/diagnostics/session/assessment",
        json={"answers": answers},
        headers={TOKEN_HEADER: token},
    )


# ── 部署闸 ───────────────────────────────────────────────────────────


def test_shipped_defaults_are_safe(test_settings):
    """**出厂默认**必须是安全值：诊断面关闭 ＋ 限流故障 fail-closed。

    这条钉的是**默认值**本身——``.env.example`` 与文档承诺的默认行为在此被钉住；
    配置项改默认值时不必改用例，但必须让这条转红。
    """
    assert test_settings.diagnostics_enabled is False
    assert test_settings.diagnostics_rate_fail_closed is True


def test_diagnostics_disabled_by_default_returns_404(client):
    """默认关闭 ⇒ 匿名面不存在（404，不是 403）。"""
    for path, method in (
        ("/api/v1/diagnostics/questionnaire", "get"),
        ("/api/v1/diagnostics/sessions", "post"),
        ("/api/v1/diagnostics/session", "get"),
    ):
        response = getattr(client, method)(path, json={} if method == "post" else None)
        assert response.status_code == 404, path
        assert response.get_json()["error"]["code"] == "not_found"


def test_diagnostics_enabled_exposes_questionnaire(diag_client):
    """启用后问卷定义可读：首屏 5 题 + 续填槽位，总量 ≤ 30。"""
    response = diag_client.get("/api/v1/diagnostics/questionnaire")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert len(data["first_screen"]) == 5
    assert data["total_questions"] <= 30
    keys = {slot["key"] for slot in data["first_screen"]} | {
        slot["key"] for slot in data["diagnostic"]
    }
    assert "ctx.contact" not in keys  # 联系方式不进问卷


# ── 匿名令牌与 IP 假名 ───────────────────────────────────────────────


def test_token_stored_as_fingerprint_only(diag_app, diag_client, db_session):
    """库里只有令牌的 sha256；明文令牌不出现在任何列。"""
    token = _create(diag_client)
    row = db_session.scalars(select(LeadDiagnosticSession)).one()
    assert row.token_sha256 == hash_token(token)
    assert token not in row.token_sha256
    assert token not in json.dumps(row.answers or {}, ensure_ascii=False)


def test_ip_is_pseudonymised_not_plaintext(diag_app, diag_client, db_session):
    """来源 IP 落库是假名，不是明文 IP。"""
    _create(diag_client)
    row = db_session.scalars(select(LeadDiagnosticSession)).one()
    assert len(row.created_ip_hash) == 64
    assert "127.0.0.1" not in row.created_ip_hash


def test_no_foreign_key_to_projects():
    """线索 ≠ 项目：本表**零外键指向 projects**（metadata 扫描钉死）。"""
    table = LeadDiagnosticSession.__table__
    project_refs = [
        fk.target_fullname
        for fk in table.foreign_keys
        if "projects" in fk.target_fullname
    ]
    assert project_refs == []


# ── 测算卡（纯规则） ─────────────────────────────────────────────────


def test_assessment_is_pure_rules_without_amount_or_score(diag_client):
    """测算卡不落补贴金额、不落分数（R-1 / R-4）。"""
    token = _create(diag_client)
    response = _assess(diag_client, token, FIRST_SCREEN_READY)
    assert response.status_code == 200
    assessment = response.get_json()["data"]["assessment"]
    text = json.dumps(assessment, ensure_ascii=False)
    assert "元" not in text  # 无金额
    assert "/100" not in text  # 无分数
    assert assessment["readiness_tier"] == "具备申报基础"


def test_assessment_separates_original_wording_and_interpretation(diag_client):
    """原文口径与我方解读分层，不混写。"""
    token = _create(diag_client)
    assessment = _assess(diag_client, token, FIRST_SCREEN_READY).get_json()["data"]["assessment"]
    assert assessment["basis_labels"] == {"original": "原文口径", "interpretation": "我方解读"}
    for item in assessment["matched_policies"]:
        assert item["original_basis"] == "原文口径"
        assert item["interpretation_basis"] == "我方解读"
        assert item["official_source_url"]
        assert item["snapshot_date"]
    for item in assessment["missing_requirements"]:
        assert item["basis"] == "我方解读"


def test_assessment_matches_smart_factory_only_for_qualified_manufacturers(diag_client):
    """智能工厂梯度培育的命中条件：制造与工业 + 规上工业企业。"""
    token = _create(diag_client)
    assessment = _assess(diag_client, token, FIRST_SCREEN_READY).get_json()["data"]["assessment"]
    matched_ids = {item["policy_id"] for item in assessment["matched_policies"]}
    assert "miit_lianyue_2026_343" in matched_ids

    token2 = _create(diag_client)
    other = dict(FIRST_SCREEN_READY)
    other["pol.qualification"] = ["高新技术企业"]
    assessment2 = _assess(diag_client, token2, other).get_json()["data"]["assessment"]
    matched2 = {item["policy_id"] for item in assessment2["matched_policies"]}
    assert "miit_lianyue_2026_343" not in matched2
    assert "guofa_2025_11" in matched2  # 普适方向仍在


def test_assessment_is_deterministic(diag_client):
    """纯规则：同样的答案必得同样的结果。"""
    first = _assess(diag_client, _create(diag_client), FIRST_SCREEN_READY).get_json()["data"]
    second = _assess(diag_client, _create(diag_client), FIRST_SCREEN_READY).get_json()["data"]
    assert first["assessment"] == second["assessment"]


def test_assessment_tier_differs_by_digitalization_state(diag_client):
    """档位随「有无在推进的数字化改造」变化（准备度分档）。"""
    token = _create(diag_client)
    not_ready = dict(FIRST_SCREEN_READY)
    not_ready["pol.digitalization_project"] = "完全没有"
    assessment = _assess(diag_client, token, not_ready).get_json()["data"]["assessment"]
    assert assessment["readiness_tier"] != "具备申报基础"


# ── 校验闸 ───────────────────────────────────────────────────────────


def test_unknown_slot_is_rejected(diag_client):
    """未知槽位键一律拒绝（防脏数据与越权写入）。"""
    token = _create(diag_client)
    response = _assess(diag_client, token, {"org.industry": "制造与工业", "hack.key": "x"})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_answers"


def test_closed_option_set_is_enforced(diag_client):
    """选项闭合：未定义选项拒绝。"""
    token = _create(diag_client)
    payload = dict(FIRST_SCREEN_READY)
    payload["org.industry"] = "不存在的行业"
    response = _assess(diag_client, token, payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_answers"


def test_required_slots_are_enforced(diag_client):
    """必答题未作答 ⇒ 400 并点名缺哪几题。"""
    token = _create(diag_client)
    response = _assess(diag_client, token, {"org.industry": "制造与工业"})
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "incomplete_answers"
    assert "org.scale" in error["details"]["missing"]


def test_diagnostic_answers_require_first_screen(diag_client):
    """未完成首屏测算就续填 ⇒ 409（首屏是钩子位，不可跳过）。"""
    token = _create(diag_client)
    response = diag_client.post(
        "/api/v1/diagnostics/session/answers",
        json={"answers": {"biz.current_process": "我们靠老师傅报价"}},
        headers={TOKEN_HEADER: token},
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "first_screen_required"


def test_diagnostic_answers_reject_first_screen_slots(diag_client):
    """续填面不接受首屏槽位（两个面的职责分开）。"""
    token = _create(diag_client)
    _assess(diag_client, token, FIRST_SCREEN_READY)
    response = diag_client.post(
        "/api/v1/diagnostics/session/answers",
        json={"answers": {"org.industry": "零售与消费"}},
        headers={TOKEN_HEADER: token},
    )
    assert response.status_code == 400


# ── 留资闸 ───────────────────────────────────────────────────────────


def test_lead_capture_requires_consent(diag_client):
    """留资须明示同意（个保法：明示用途 + 同意）。"""
    token = _create(diag_client)
    _assess(diag_client, token, FIRST_SCREEN_READY)
    response = diag_client.post(
        "/api/v1/diagnostics/session/lead",
        json={"contact": {"contact": "13800000000"}},
        headers={TOKEN_HEADER: token},
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "consent_required"


def test_lead_capture_stores_contact_and_gates_report(diag_client):
    """留资后记录联系方式；未留资时报告不可见（留资闸）。"""
    token = _create(diag_client)
    _assess(diag_client, token, FIRST_SCREEN_READY)
    before = diag_client.get(
        "/api/v1/diagnostics/session", headers={TOKEN_HEADER: token}
    ).get_json()["data"]
    assert before["lead_captured"] is False
    assert before["report"] is None

    response = diag_client.post(
        "/api/v1/diagnostics/session/lead",
        json={"contact": {"contact": "contact@example.com", "name": "厂长", "consent": True}},
        headers={TOKEN_HEADER: token},
    )
    assert response.status_code == 200
    after = response.get_json()["data"]
    assert after["lead_captured"] is True


# ── 配额闸 ───────────────────────────────────────────────────────────


def test_ip_daily_limit_is_enforced(diag_app, diag_client):
    """每 IP 每日上限：超限 ⇒ 429。"""
    diag_app.config["SETTINGS"] = diag_app.config["SETTINGS"].model_copy(
        update={"diagnostics_daily_ip_limit": 2}
    )
    assert _create(diag_client)
    assert _create(diag_client)
    response = diag_client.post("/api/v1/diagnostics/sessions", json={})
    assert response.status_code == 429
    assert response.get_json()["error"]["code"] == "diagnostics_rate_limited"


def test_session_quota_is_enforced(diag_app, diag_client):
    """每匿名令牌配额：超限 ⇒ 429。"""
    diag_app.config["SETTINGS"] = diag_app.config["SETTINGS"].model_copy(
        update={"diagnostics_session_quota": 1}
    )
    token = _create(diag_client)
    assert _assess(diag_client, token, FIRST_SCREEN_READY).status_code == 200
    response = _assess(diag_client, token, FIRST_SCREEN_READY)
    assert response.status_code == 429


def test_rate_limiter_failure_is_fail_closed(diag_app, diag_client):
    """Redis 故障 ⇒ 默认 fail-closed（公开写面不放行）。"""
    diag_app.extensions["fde_api_redis"] = _BrokenRedis()
    response = diag_client.post("/api/v1/diagnostics/sessions", json={})
    assert response.status_code == 429
    assert response.get_json()["error"]["code"] == "diagnostics_rate_limited"


def test_rate_limiter_failure_can_be_fail_open(diag_app, diag_client):
    """显式切 fail-open ⇒ 放行（与登录面同款可配置）。"""
    diag_app.config["SETTINGS"] = diag_app.config["SETTINGS"].model_copy(
        update={"diagnostics_rate_fail_closed": False}
    )
    diag_app.extensions["fde_api_redis"] = _BrokenRedis()
    assert diag_client.post("/api/v1/diagnostics/sessions", json={}).status_code == 200


# ── 归因结构 ─────────────────────────────────────────────────────────


def test_source_rules(diag_client):
    """T-15 契约两条：``partner`` 声明一律 400（A 档只能由链接推导）；
    ``channel`` 免费名目仍须自带渠道标识。"""
    partner = diag_client.post(
        "/api/v1/diagnostics/sessions", json={"source_type": "partner"}
    )
    assert partner.status_code == 400
    assert partner.get_json()["error"]["code"] == "partner_source_forbidden"
    bare_channel = diag_client.post(
        "/api/v1/diagnostics/sessions", json={"source_type": "channel"}
    )
    assert bare_channel.status_code == 400
    assert bare_channel.get_json()["error"]["code"] == "channel_ref_required"


def test_stale_channel_ref_fails_closed_to_direct(diag_app, diag_client, db_session):
    """无效渠道标识 ⇒ **降档 direct**（不拦真实线索）但 ref 原样留痕（诚实审计）。"""
    diag_app.config["SETTINGS"] = diag_app.config["SETTINGS"].model_copy(
        update={"diagnostics_daily_ip_limit": 50}
    )
    token = _create(diag_client, channel_ref="r4-zhang-001")
    row = db_session.scalars(select(LeadDiagnosticSession)).one()
    assert row.source_type == "direct"  # 无有效链接证据不给 A 档
    assert row.channel_ref == "r4-zhang-001"
    assert row.attribution_tier is None  # 比例与档位留给 T-11（只落结构不落数）
    assert token


# ── 脱敏 ─────────────────────────────────────────────────────────────


def test_free_text_answer_is_redacted_before_storage(diag_app, diag_client, db_session):
    """答案过脱敏管线：企业名不入库（T-A2）。"""
    token = _create(diag_client)
    _assess(diag_client, token, FIRST_SCREEN_READY)
    response = diag_client.post(
        "/api/v1/diagnostics/session/answers",
        json={"answers": {"ctx.free_text": "我们合成测试集团今年要改造产线"}},
        headers={TOKEN_HEADER: token},
    )
    assert response.status_code == 200
    row = db_session.scalars(select(LeadDiagnosticSession)).one()
    assert "合成测试集团" not in json.dumps(row.answers or {}, ensure_ascii=False)


def test_missing_session_token_is_rejected(diag_client):
    """会话令牌走请求头（不放 URL——URL 会进访问日志）。"""
    response = diag_client.get("/api/v1/diagnostics/session")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "session_token_required"
