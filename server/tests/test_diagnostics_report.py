"""获客诊断工具 T-10b：AI 报告生成（异步 + 契约 + 分享）。

守的是三件事：

1. **R-1~R-7 的机械闸**——七条需求各有可断言的检查（数字闸／政策闸／第一步闸／
   一一映射闸／禁用词闸／闭环闸）。模型说什么不可信，**结构上**拦住失真。
2. **异步面诚实**——受理只入队不阻塞；失败落 ``failure_code``（访客看得到），
   不吞错、不把会话卡在「生成中」。
3. **分享面不越权**——分享页只给**摘要层**（不含企业自填原文与联系方式）；
   完整报告仍只在**已留资**的本人会话里可见（留资闸不被分享链接绕过）。

这些用例**不联网、不调真模型**：AI 入口在用例里被替换成固定输出。
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from fde_api.auth.models import User
from fde_api.diagnostics import jobs as diag_jobs
from fde_api.diagnostics.models import LeadDiagnosticSession
from test_diagnostics_mvp import _FakeRedis
from fde_api.diagnostics.report_contract import (
    NumberKey,
    ReportContractError,
    allowed_number_tokens,
    assemble_report,
    parse_report_json,
    report_share_view,
    sourced_number_tokens,
    validate_report_payload,
)
from fde_api.diagnostics.service import hash_share_token, hash_token
from fde_api.jobs.models import OutboxEvent

TOKEN_HEADER = "X-Diagnostic-Token"

FIRST_SCREEN_READY = {
    "org.industry": "制造与工业",
    "org.scale": "100–499人",
    "pol.qualification": ["规上工业企业"],
    "pol.declaration_history": "从未申报过",
    "pol.digitalization_project": "已有在推进的数字化改造",
}

CONTACT = {"contact": "someone@example.com", "name": "张三", "consent": True}


def _good_payload() -> dict[str, Any]:
    """一份**契约合规**的模型输出（各用例按需改写）。"""
    return {
        "headline": "数字化基础已具备申报前提，先补齐数据口径。",
        "findings": [
            {"id": "f1", "problem": "订单数据分散在多个系统，口径不统一", "stage": "identify"},
            {"id": "f2", "problem": "缺少统一的数据归集责任人", "stage": "locate"},
        ],
        "first_step": {"when": "本周", "what": "把本周的订单数据导出一份清单", "output": "一份字段口径对照表"},
        "actions": [
            {"finding_id": "f1", "action": "整理各系统的订单字段", "expected_output": "字段对照表"},
            {"finding_id": "f2", "action": "指定数据归集责任人", "expected_output": "责任人名单"},
        ],
        "closing_loop": {
            "identified": "订单口径不统一",
            "located": "分散在多个业务系统",
            "handled": "先出字段对照表再统一归集",
            "written_back": "把对照表沉淀到内部文档",
        },
        "policy_ids": ["guofa_2025_11"],
        "open_questions": ["现有系统之间的接口方式待澄清"],
    }


# ── 契约闸（纯函数，不碰库） ─────────────────────────────────────────


def _validate(
    payload: dict[str, Any], *, allowed: set[NumberKey] | None = None
) -> dict[str, Any]:
    return validate_report_payload(payload, allowed_numbers=allowed or set())


def test_contract_accepts_compliant_payload() -> None:
    validated = _validate(_good_payload())
    assert validated["first_step"]["when"] == "本周"
    assert len(validated["findings"]) == 2


def test_r1_rejects_score_field() -> None:
    """R-1：报告里不许有分数字段（多一个键即拒收）。"""
    payload = _good_payload()
    payload["score"] = 82
    with pytest.raises(ReportContractError) as caught:
        _validate(payload)
    assert caught.value.code == "report_contract_invalid"


def test_r2_rejects_unknown_policy_id() -> None:
    """R-2：政策编号必须是弹药库里的那几条。"""
    payload = _good_payload()
    payload["policy_ids"] = ["made_up_policy"]
    with pytest.raises(ReportContractError) as caught:
        _validate(payload)
    assert caught.value.code == "report_contract_unknown_policy"


def test_r3_requires_first_step_three_elements() -> None:
    """R-3：第一步三要素齐全，when 闭集＝本周。"""
    payload = _good_payload()
    payload["first_step"]["output"] = ""
    with pytest.raises(ReportContractError):
        _validate(payload)
    payload = _good_payload()
    payload["first_step"]["when"] = "下个月"
    with pytest.raises(ReportContractError):
        _validate(payload)


def test_r4_rejects_unsourced_number_but_allows_questionnaire_number() -> None:
    """R-4：数字要有来源——问卷里出现过的放行，凭空出现的拒收。"""
    payload = _good_payload()
    payload["headline"] = "预计三个月内可以完成改造。"
    with pytest.raises(ReportContractError) as caught:
        _validate(payload)
    assert caught.value.code == "report_unsourced_number"

    payload = _good_payload()
    payload["headline"] = "现有人员规模在 100–499人 区间，先补齐数据口径。"
    allowed = allowed_number_tokens({"org.scale": "100–499人"})
    validated = _validate(payload, allowed=allowed)
    assert validated["headline"]


def test_r4_allows_number_when_marked_as_to_be_clarified() -> None:
    """R-4 的另一个出口：标「待澄清」并说明缺什么。"""
    payload = _good_payload()
    payload["headline"] = "预计三个月内可以完成改造（周期待澄清，缺历史排产数据）。"
    validated = _validate(payload)
    assert "待澄清" in validated["headline"]


def test_r5_requires_action_per_finding() -> None:
    """R-5：每个识别出来的问题都要有对应动作。"""
    payload = _good_payload()
    payload["actions"] = payload["actions"][:1]
    with pytest.raises(ReportContractError) as caught:
        _validate(payload)
    assert caught.value.code == "report_action_unmapped"


def test_r5_rejects_dangling_action_reference() -> None:
    payload = _good_payload()
    payload["actions"][0]["finding_id"] = "f9"
    with pytest.raises(ReportContractError):
        _validate(payload)


def test_r6_rejects_completion_claim_in_advice() -> None:
    """R-6：建议段不得把选型期写成已完成。"""
    payload = _good_payload()
    payload["actions"][0]["action"] = "已完成改造并全面上线"
    with pytest.raises(ReportContractError) as caught:
        _validate(payload)
    assert caught.value.code == "report_forbidden_claim"


def test_r6_scope_is_advice_section_only() -> None:
    """R-6 扫描范围＝建议段（现状段是客户原话，不在此闸拦）。"""
    payload = _good_payload()
    payload["findings"][0]["problem"] = "客户去年已完成改造但现在停滞"
    validated = _validate(payload)
    assert validated["findings"][0]["problem"]


def test_r7_requires_four_closing_loop_stages() -> None:
    """R-7：识别→定位→处置→回写 四段齐。"""
    payload = _good_payload()
    del payload["closing_loop"]["written_back"]
    with pytest.raises(ReportContractError):
        _validate(payload)
    payload = _good_payload()
    payload["closing_loop"]["handled"] = "  "
    with pytest.raises(ReportContractError):
        _validate(payload)


def test_parse_tolerates_code_fence_but_rejects_garbage() -> None:
    parsed = parse_report_json("```json\n" + json.dumps(_good_payload(), ensure_ascii=False) + "\n```")
    assert parsed["headline"]
    with pytest.raises(ReportContractError):
        parse_report_json("模型今天不方便回答")


def test_assembly_injects_policy_official_text_server_side() -> None:
    """R-2：政策原文口径由**服务端**注入（模型只选编号）。"""
    validated = _validate(_good_payload())
    report = assemble_report(
        payload=validated,
        assessment={"readiness_tier": "具备申报基础"},
        model_info={"provider": "test", "name": "test-model"},
        generated_at="2026-11-11T00:00:00+00:00",
        prompt_version="diagnostic-report-prompt-v1",
    )
    opportunity = report["layers"]["policy"]["opportunities"][0]
    assert opportunity["policy_id"] == "guofa_2025_11"
    assert opportunity["original_basis"] == "原文口径"
    assert opportunity["interpretation_basis"] == "我方解读"
    assert opportunity["official_source_url"]
    assert opportunity["snapshot_date"] == "2026-10-19"
    assert opportunity["official_text"]
    assert report["layers"]["situation"]["headline"]
    assert report["layers"]["action"]["first_step"]["when"] == "本周"


def test_share_view_omits_free_text_and_contact() -> None:
    """分享视图只给摘要层：不含企业自填原文与联系方式。"""
    validated = _validate(_good_payload())
    report = assemble_report(
        payload=validated,
        assessment=None,
        model_info=None,
        generated_at="2026-11-11T00:00:00+00:00",
        prompt_version="diagnostic-report-prompt-v1",
    )
    view = report_share_view(report)
    assert view is not None
    text = json.dumps(view, ensure_ascii=False)
    assert "someone@example.com" not in text
    # 闭环四段在分享视图里只给「有没有」，不给原文
    assert "识别到什么" not in text
    assert view["first_step"]["when"] == "本周"
    assert view["loop_completed"]["written_back"] is True


# ── 受理面（异步入队） ───────────────────────────────────────────────


@pytest.fixture
def diag_app(app):
    app.config["SETTINGS"] = app.config["SETTINGS"].model_copy(
        update={
            "diagnostics_enabled": True,
            "diagnostics_rate_fail_closed": True,
            "diagnostics_ai_actor_username": "diag-actor",
        }
    )
    # 配额闸用进程内假 Redis（与 test_diagnostics_mvp 同款）——共享开发 Redis 的
    # IP 日配额键按日期累积，跨 run 复用同一序号来源 IP（PerTestIPClient 每个
    # run 从 1 重来）会把低位 IP 的计数器推过 20 ⇒ 测试面 429。CI 全新 Redis
    # 免疫，但本地多轮必撞——隔离缺陷在本文件修死，不靠「清 Redis」续命。
    app.extensions["fde_api_redis"] = _FakeRedis()
    return app


@pytest.fixture
def diag_client(diag_app):
    return diag_app.test_client()


def _prepare_session(diag_client) -> tuple[str, str]:
    """走完首屏 → 续填 → 留资，返回（会话令牌, 会话 id）。"""
    response = diag_client.post("/api/v1/diagnostics/sessions", json={})
    assert response.status_code == 200, response.get_json()
    token = response.get_json()["data"]["token"]
    session_id = response.get_json()["data"]["id"]
    response = diag_client.post(
        "/api/v1/diagnostics/session/assessment",
        json={"answers": FIRST_SCREEN_READY},
        headers={TOKEN_HEADER: token},
    )
    assert response.status_code == 200, response.get_json()
    response = diag_client.post(
        "/api/v1/diagnostics/session/lead",
        json={"contact": CONTACT},
        headers={TOKEN_HEADER: token},
    )
    assert response.status_code == 200, response.get_json()
    return token, session_id


def test_report_request_requires_lead_capture(diag_client) -> None:
    """留资闸：没留资不能要完整报告（既是商业闸也是成本闸）。"""
    response = diag_client.post("/api/v1/diagnostics/sessions", json={})
    token = response.get_json()["data"]["token"]
    response = diag_client.post(
        "/api/v1/diagnostics/session/assessment",
        json={"answers": FIRST_SCREEN_READY},
        headers={TOKEN_HEADER: token},
    )
    assert response.status_code == 200
    response = diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "lead_required"


def test_report_request_enqueues_job_asynchronously(diag_client, db_session) -> None:
    """受理只入队（202），不阻塞；outbox 事件与业务写同事务。"""
    token, session_id = _prepare_session(diag_client)
    response = diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    assert response.status_code == 202
    data = response.get_json()["data"]
    assert data["report_state"] == "requested"
    assert data["report_requested_at"]
    assert data["report"] is None
    events = db_session.scalars(
        select(OutboxEvent).where(OutboxEvent.aggregate_id == session_id)
    ).all()
    assert [event.topic for event in events] == ["diagnostics.report"]


def test_report_request_is_idempotent_while_in_flight(diag_client, db_session) -> None:
    """生成中重复请求 ⇒ 幂等（不重复入队、不重复计费）。"""
    token, session_id = _prepare_session(diag_client)
    for _ in range(2):
        response = diag_client.post(
            "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
        )
        assert response.status_code == 202
    events = db_session.scalars(
        select(OutboxEvent).where(OutboxEvent.aggregate_id == session_id)
    ).all()
    assert len(events) == 1


def test_report_is_invisible_before_lead_capture(diag_client, db_session) -> None:
    """留资闸：报告只在已留资的会话里可见。"""
    response = diag_client.post("/api/v1/diagnostics/sessions", json={})
    token = response.get_json()["data"]["token"]
    session_id = response.get_json()["data"]["id"]
    row = db_session.get(LeadDiagnosticSession, session_id)
    row.report = {"layers": {"situation": {"headline": "内部报告"}}}
    db_session.commit()
    response = diag_client.get("/api/v1/diagnostics/session", headers={TOKEN_HEADER: token})
    assert response.status_code == 200
    assert response.get_json()["data"]["report"] is None


# ── 分享面 ───────────────────────────────────────────────────────────


def test_share_link_is_readonly_summary_and_rotates(diag_client, db_session) -> None:
    """分享链接：只读摘要；每次生成分享令牌轮换旧链接。"""
    token, session_id = _prepare_session(diag_client)
    row = db_session.get(LeadDiagnosticSession, session_id)
    row.report = {
        "version": "diagnostic-report-v1",
        "generated_at": "2026-11-11T00:00:00+00:00",
        "layers": {
            "situation": {"headline": "摘要结论", "findings": [], "open_questions": []},
            "action": {
                "first_step": {"when": "本周", "what": "导出一份清单", "output": "对照表"},
                "actions": [],
                "closing_loop": {
                    "identified": "a",
                    "located": "b",
                    "handled": "c",
                    "written_back": "d",
                },
            },
            "policy": {"opportunities": []},
        },
    }
    db_session.commit()

    response = diag_client.post(
        "/api/v1/diagnostics/session/share", json={}, headers={TOKEN_HEADER: token}
    )
    assert response.status_code == 200
    first_token = response.get_json()["data"]["share_token"]
    db_session.expire_all()
    row = db_session.get(LeadDiagnosticSession, session_id)
    assert row.share_token_sha256 == hash_share_token(first_token)

    response = diag_client.get(f"/api/v1/diagnostics/share/{first_token}")
    assert response.status_code == 200
    assert response.get_json()["data"]["headline"] == "摘要结论"

    response = diag_client.post(
        "/api/v1/diagnostics/session/share", json={}, headers={TOKEN_HEADER: token}
    )
    second_token = response.get_json()["data"]["share_token"]
    assert second_token != first_token
    # 旧链接立即失效
    response = diag_client.get(f"/api/v1/diagnostics/share/{first_token}")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "share_not_found"


def test_share_unknown_token_returns_404(diag_client) -> None:
    response = diag_client.get("/api/v1/diagnostics/share/not-a-real-token")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "share_not_found"


# ── worker 腿（AI 入口被替换成固定输出） ─────────────────────────────


def _actor_user(db_session, username: str = "diag-actor") -> User:
    user = User(username=username, display_name="诊断服务账号", role="admin", password_hash="x")
    db_session.add(user)
    db_session.commit()
    return user


def _run_handler(app, db_session, session_id: str, outputs: list[Any]):
    """直调 worker handler；outputs 逐次弹出（模拟重试序列）。"""

    def _fake_execute(**kwargs):
        item = outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return {
            "text": item,
            "model": {"provider": "test", "name": "test-model"},
            "provider_usage": {},
        }

    original = diag_jobs.execute_ai_prompt
    diag_jobs.execute_ai_prompt = _fake_execute
    job = SimpleNamespace(target_id=session_id)
    try:
        with app.app_context():
            diag_jobs.handle_diagnostic_report(job)
    finally:
        diag_jobs.execute_ai_prompt = original
    db_session.expire_all()
    return db_session.get(LeadDiagnosticSession, session_id)


def test_worker_generates_report_and_marks_ready(diag_app, diag_client, db_session) -> None:
    """handler 成功路径：三层报告落库，状态推进到 report_ready。"""
    _actor_user(db_session)
    token, session_id = _prepare_session(diag_client)
    response = diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    assert response.status_code == 202
    row = _run_handler(
        diag_app, db_session, session_id, [json.dumps(_good_payload(), ensure_ascii=False)]
    )
    assert row.status == "report_ready"
    assert row.report_ready_at is not None
    assert row.failure_code is None
    assert row.report["layers"]["situation"]["headline"]
    assert row.report["layers"]["action"]["first_step"]["when"] == "本周"
    assert row.report["layers"]["policy"]["opportunities"][0]["official_text"]


def test_worker_records_contract_failure_without_breaking_session(
    diag_app, diag_client, db_session
) -> None:
    """契约违规 ⇒ 落失败码（重试一次仍不过），会话不卡在生成中。"""
    _actor_user(db_session)
    token, session_id = _prepare_session(diag_client)
    diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    bad = _good_payload()
    del bad["first_step"]
    row = _run_handler(
        diag_app,
        db_session,
        session_id,
        [json.dumps(bad, ensure_ascii=False), json.dumps(bad, ensure_ascii=False)],
    )
    assert row.status == "submitted"
    assert row.failure_code == "report_contract_invalid"
    assert row.failure_message


def test_worker_records_ai_failure(diag_app, diag_client, db_session) -> None:
    """AI 侧故障 ⇒ 失败码落库（不吞错）。"""
    from fde_api.control.ai_server_client import DSHRuntimeError

    _actor_user(db_session)
    token, session_id = _prepare_session(diag_client)
    diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    row = _run_handler(
        diag_app,
        db_session,
        session_id,
        [DSHRuntimeError("ai_service_unavailable", "服务暂不可用。", retryable=False)],
    )
    assert row.status == "submitted"
    assert row.failure_code == "ai_service_unavailable"


def test_worker_skips_when_report_already_ready(diag_app, diag_client, db_session) -> None:
    """幂等：报告已就绪 ⇒ 不再调 AI（重复投递不覆盖已有结论）。"""
    _actor_user(db_session)
    token, session_id = _prepare_session(diag_client)
    diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    row = _run_handler(
        diag_app, db_session, session_id, [json.dumps(_good_payload(), ensure_ascii=False)]
    )
    assert row.status == "report_ready"
    # 第二次投递：没有输出可弹 ⇒ 若真调了 AI 会 IndexError
    row = _run_handler(diag_app, db_session, session_id, [])
    assert row.status == "report_ready"


def test_ai_actor_missing_fails_closed(diag_app, db_session) -> None:
    """未配置服务账号 ⇒ fail-closed 503（不静默降级成「没有报告」）。"""
    from fde_api.diagnostics.service import DiagnosticsServiceError, resolve_ai_actor

    diag_app.config["SETTINGS"] = diag_app.config["SETTINGS"].model_copy(
        update={"diagnostics_ai_actor_username": ""}
    )
    with diag_app.app_context():
        with pytest.raises(DiagnosticsServiceError) as caught:
            resolve_ai_actor(db_session)
        assert caught.value.status == 503
        assert caught.value.code == "diagnostic_ai_unavailable"


# ── curve 1 修复轮（2026-11-11）：预算标定钉 + 诊断模型槽位显式化 ──────


def test_report_budget_calibrated_for_thinking_models() -> None:
    """真机归因钉（curve 1，2026-11-11）：6000 预算下推理模型思考吃穿预算
    ⇒ ai_output_truncated ×3 + 截断残 JSON 契约违规 ×3（6 卡全灭）。同端点
    同模型的 judge 通道实测 16000 双连过（输出 7.1k/8.2k）；MiniMax-M3.1-Flash
    硬顶 16384（V31-P1 实测）——16000 贴顶而不过。静默回退旧值必须转红。"""
    assert diag_jobs.REPORT_MAX_TOKENS >= 16000


def test_model_slot_default_off_keeps_preference_chain(diag_app) -> None:
    """槽位缺省空 ⇒ 不接管（零行为变更）：既有解析链（服务账号偏好行 →
    system-default）在 curve 1 真机归因中工作正常——接管必须显式 opt-in。"""
    with diag_app.app_context():
        assert diag_jobs._diagnostic_model_override() is None


def test_model_slot_set_takes_over_model_selection(diag_app) -> None:
    """设槽位 ⇒ 整体接管：模型名/端点/密钥齐备，provider 由 base_url 单点
    命名（MiniMax 端点不得标成 deepseek——model_preferences 同一把尺）。"""
    from pydantic import SecretStr

    diag_app.config["SETTINGS"] = diag_app.config["SETTINGS"].model_copy(
        update={
            "deepseek_diagnostic_report_model": "MiniMax-M3.1-Flash",
            "deepseek_base_url": "https://api.minimaxi.com/v1",
            "deepseek_api_key": SecretStr("k" * 40),
        }
    )
    with diag_app.app_context():
        override = diag_jobs._diagnostic_model_override()
    assert override is not None
    assert override["model"] == "MiniMax-M3.1-Flash"
    assert override["base_url"] == "https://api.minimaxi.com/v1"
    assert override["provider"] == "minimax"
    assert override["api_key"] == "k" * 40


def test_model_slot_set_without_credentials_fails_closed(diag_app) -> None:
    """显式接管却缺端点/密钥 ⇒ fail-closed：静默回落偏好链会把「设了槽位却
    没生效」掩盖掉（CR-046 家族：配置面沉默失效应显式暴露）。"""
    diag_app.config["SETTINGS"] = diag_app.config["SETTINGS"].model_copy(
        update={
            "deepseek_diagnostic_report_model": "MiniMax-M3.1-Flash",
            "deepseek_base_url": "https://api.minimaxi.com/v1",
            "deepseek_api_key": None,
        }
    )
    with diag_app.app_context():
        with pytest.raises(diag_jobs.ReportGenerationError) as caught:
            diag_jobs._diagnostic_model_override()
    assert caught.value.code == "report_model_slot_incomplete"


def test_worker_passes_budget_and_slot_to_execute(diag_app, diag_client, db_session) -> None:
    """端到端接线钉：handler 把 16000 预算与槽位解析结果传给 execute_ai_prompt
    （缺省槽位 ⇒ model_override=None，不绕开偏好解析链）。"""
    captured: dict[str, Any] = {}

    def _fake_execute(**kwargs):
        captured.update(kwargs)
        return {
            "text": json.dumps(_good_payload(), ensure_ascii=False),
            "model": {"provider": "test", "name": "test-model"},
            "provider_usage": {},
        }

    _actor_user(db_session)
    token, session_id = _prepare_session(diag_client)
    diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    original = diag_jobs.execute_ai_prompt
    diag_jobs.execute_ai_prompt = _fake_execute
    job = SimpleNamespace(target_id=session_id)
    try:
        with diag_app.app_context():
            diag_jobs.handle_diagnostic_report(job)
    finally:
        diag_jobs.execute_ai_prompt = original
    assert captured["max_tokens"] == diag_jobs.REPORT_MAX_TOKENS
    assert captured["model_override"] is None


def test_worker_passes_slot_override_to_execute_when_set(diag_app, diag_client, db_session) -> None:
    """端到端接线钉（设值态）：槽位非空 ⇒ handler 必须把接管 dict 原样传给
    execute_ai_prompt——摘掉 _call_model 的 model_override 接线时本钉转红
    （缺省态两路同为 None，无判别力）。"""
    from pydantic import SecretStr

    captured: dict[str, Any] = {}

    def _fake_execute(**kwargs):
        captured.update(kwargs)
        return {
            "text": json.dumps(_good_payload(), ensure_ascii=False),
            "model": {"provider": "test", "name": "test-model"},
            "provider_usage": {},
        }

    diag_app.config["SETTINGS"] = diag_app.config["SETTINGS"].model_copy(
        update={
            "deepseek_diagnostic_report_model": "MiniMax-M3.1-Flash",
            "deepseek_base_url": "https://api.minimaxi.com/v1",
            "deepseek_api_key": SecretStr("k" * 40),
        }
    )
    _actor_user(db_session)
    token, session_id = _prepare_session(diag_client)
    diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    original = diag_jobs.execute_ai_prompt
    diag_jobs.execute_ai_prompt = _fake_execute
    job = SimpleNamespace(target_id=session_id)
    try:
        with diag_app.app_context():
            diag_jobs.handle_diagnostic_report(job)
    finally:
        diag_jobs.execute_ai_prompt = original
    override = captured.get("model_override")
    assert override is not None and override["model"] == "MiniMax-M3.1-Flash"


# ── curve 3 修复轮（2026-11-11）：数字闸 v2 口径重界定 + 拒因回灌 ────────
#
# 归因（curve 2 真机）：三张卡全灭在 report_unsourced_number，而被判无源的
# 三个字面是「一个」「一套」「两套」——**都不是编造的业务数字**。根因是闸的
# 口径与机制（D1 口径错位／D2 裁决依赖测算卡偶然字面／D3 重试盲抽），不是
# 模型编数字。本节钉的是 v2 的四条语义边界 + 修复回灌接线。


def test_number_gate_v2_scope_by_layer() -> None:
    """作用域分层（v2 D1）：现状层的数字必检；处方层的计数/周期是建议参数
    ⇒ 免检；但**金额与比例类任何层都必检**（基线数字编造的重灾面）。"""
    # 现状层（结论）里的无源数字 ⇒ 拒收
    payload = _good_payload()
    payload["headline"] = "设备停机造成的损失约每月 12 万元。"
    with pytest.raises(ReportContractError) as caught:
        _validate(payload)
    assert caught.value.code == "report_unsourced_number"

    # 处方层（建议）里的计数与周期 ⇒ 放行（「一套」「两周」是产出数量/节奏）
    payload = _good_payload()
    payload["first_step"]["output"] = "输出一套清单，两周内完成一次演练。"
    validated = _validate(payload)
    assert validated["first_step"]["output"]

    # 处方层里的金额与比例 ⇒ 仍拒收（编造基线数字的重灾面）
    payload = _good_payload()
    payload["actions"][0]["expected_output"] = "一份能证明节省 30% 成本的对比记录。"
    with pytest.raises(ReportContractError) as caught:
        _validate(payload)
    assert caught.value.code == "report_unsourced_number"


def test_number_gate_v2_indefinite_quantifier_is_not_a_quantity() -> None:
    """泛指量词不是量级断言：「一个」「一套」「几家」在中文里多为泛指/单数用法
    （a set of… / a few），不构成量级断言 ⇒ 免检。**兜底分工**：客户事实类编造
    （如「只有一个师傅」的师徒配比）由 rubric ③ 的 must_not_hallucinate 与展示闸
    C1 兜底——契约闸的误拒会直接毙掉整份报告，代价与漏放不对称。"""
    payload = _good_payload()
    payload["first_step"]["what"] = "选一个高频场景，输出一套清单。"
    validated = _validate(payload)
    assert validated["first_step"]["what"]

    payload = _good_payload()
    payload["findings"][0]["problem"] = "有几家外包供应商各自维护一套台账。"
    validated = _validate(payload)
    assert validated["findings"][0]["problem"]

    payload = _good_payload()
    payload["findings"][0]["problem"] = "公司只有一个系统承接全部订单。"
    validated = _validate(payload)
    assert validated["findings"][0]["problem"]


def test_number_gate_v2_normalizes_chinese_and_arabic_numerals() -> None:
    """中文数字与阿拉伯数字归一：「两套」≡「2套」——同一来源的两种写法必须
    等价（v1 按字面比对 ⇒ 「2套」在答案里而报告写「两套」会被误拒）。
    本钉落在**现状层**（处方层的计数免检 ⇒ 放这里就没有判别力）。"""
    allowed = allowed_number_tokens({"sys.systems": "OA 与 ERP 2套系统"})
    payload = _good_payload()
    payload["headline"] = "现有 OA 与 ERP 两套系统互不相通，先补齐数据口径。"
    validated = _validate(payload, allowed=allowed)
    assert validated["headline"]


def test_number_gate_v2_sourced_set_excludes_rule_generated_boilerplate() -> None:
    """可溯源集合重界定（v2 D2）：测算卡的**规则生成文本**（下一步建议/免责
    声明/解读）与政策原文口径里的量值**不是**数字来源——v1 把整个测算卡当来源，
    于是规则措辞里偶然出现的数字会替客户事实「担保」（同一句话在两张卡上结论
    相反：判定取决于措辞的偶然字面，不是数字本身有没有来源）。"""
    assessment = {
        "readiness_tier": "先做基础准备",
        "matched_policies": [
            {
                "policy_id": "guofa_2025_11",
                "title": "《国务院关于深入实施「人工智能+」行动的意见》",
                "doc_number": "国发〔2025〕11号",
                "issued_on": "2025-08-21",
                "original_wording": "到 2027 年……应用普及率超 70%",
                "official_source_url": "https://www.gov.cn/example.pdf",
                "snapshot_date": "2026-10-19",
            }
        ],
        "next_actions": ["先做 3 类单据的盘点"],
        "disclaimers": ["快照超 30 天须重核"],
    }
    allowed = sourced_number_tokens({"org.scale": "20–99人"}, assessment)

    # 规则生成措辞里的「3」不再让现状层的「3 类单据」放行
    payload = _good_payload()
    payload["findings"][0]["problem"] = "现有 3 类单据需要人工核对。"
    with pytest.raises(ReportContractError) as caught:
        _validate(payload, allowed=allowed)
    assert caught.value.code == "report_unsourced_number"

    # 政策原文口径里的 70% 不是客户事实的来源（否则任何百分比都能借政策放行）
    payload = _good_payload()
    payload["actions"][0]["expected_output"] = "一份证明能提升 70% 效率的对比记录。"
    with pytest.raises(ReportContractError) as caught:
        _validate(payload, allowed=allowed)
    assert caught.value.code == "report_unsourced_number"


def test_number_gate_v2_policy_citation_numbers_are_sourced() -> None:
    """政策**引文的编号与日期**是合法来源（报告可以引用文号，不该被数字闸拦）。"""
    assessment = {
        "matched_policies": [
            {
                "policy_id": "guofa_2025_11",
                "title": "《国务院关于深入实施「人工智能+」行动的意见》",
                "doc_number": "国发〔2025〕11号",
                "issued_on": "2025-08-21",
                "original_wording": "到 2027 年……应用普及率超 70%",
                "official_source_url": "https://www.gov.cn/example.pdf",
                "snapshot_date": "2026-10-19",
            }
        ],
        "policy_snapshot_date": "2026-10-19",
    }
    allowed = sourced_number_tokens({"org.scale": "20–99人"}, assessment)
    payload = _good_payload()
    payload["headline"] = "申报口径按国发〔2025〕11号原文执行，先补齐数据口径。"
    validated = _validate(payload, allowed=allowed)
    assert validated["headline"]


def test_number_gate_version_recorded_in_report() -> None:
    """数字闸版本随报告落库：口径变 ⇒ 报告可比性变，必须能追责。"""
    from fde_api.diagnostics.report_contract import NUMBER_GATE_VERSION

    assert NUMBER_GATE_VERSION == "number-gate-v2"
    validated = _validate(_good_payload())
    report = assemble_report(
        payload=validated,
        assessment=None,
        model_info=None,
        generated_at="2026-11-11T00:00:00+00:00",
        prompt_version="diagnostic-report-prompt-v2",
    )
    assert report["number_gate_version"] == "number-gate-v2"


def test_prompt_v2_number_clause_aligned_with_gate() -> None:
    """提示词 v2（curve 3 断点）：R-4 条款必须与 number-gate-v2 口径一致——
    数字来源＝问卷答案＋政策引文；现状层必检／建议里的节奏与产出数量可写。
    提示词与闸口径漂移 ⇒ 生成器按一套口径写、闸按另一套判 ⇒ 白烧调用。"""
    from fde_api.diagnostics.prompts import (
        DIAGNOSTIC_REPORT_SYSTEM_PROMPT,
        REPORT_PROMPT_VERSION,
    )

    assert REPORT_PROMPT_VERSION == "diagnostic-report-prompt-v2"
    assert "问卷答案里客户自己说的" in DIAGNOSTIC_REPORT_SYSTEM_PROMPT
    assert "政策引文里的编号与日期" in DIAGNOSTIC_REPORT_SYSTEM_PROMPT
    assert "重试修复" in DIAGNOSTIC_REPORT_SYSTEM_PROMPT


def test_worker_feeds_rejection_reason_into_retry(
    diag_app, diag_client, db_session
) -> None:
    """拒因回灌（v2 D3）：第一次被契约拒收 ⇒ 第二次的提示词必须带拒因，
    让重试是**修复**而不是同提示词盲重抽（v1 下一个量词会毙掉整份报告）。"""
    prompts: list[str] = []

    def _fake_execute(**kwargs):
        prompts.append(str(kwargs.get("prompt") or ""))
        if len(prompts) == 1:
            bad = _good_payload()
            bad["headline"] = "设备停机造成的损失约每月 12 万元。"
            return {
                "text": json.dumps(bad, ensure_ascii=False),
                "model": {"provider": "test", "name": "test-model"},
                "provider_usage": {},
            }
        return {
            "text": json.dumps(_good_payload(), ensure_ascii=False),
            "model": {"provider": "test", "name": "test-model"},
            "provider_usage": {},
        }

    _actor_user(db_session)
    token, session_id = _prepare_session(diag_client)
    diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    original = diag_jobs.execute_ai_prompt
    diag_jobs.execute_ai_prompt = _fake_execute
    job = SimpleNamespace(target_id=session_id)
    try:
        with diag_app.app_context():
            diag_jobs.handle_diagnostic_report(job)
    finally:
        diag_jobs.execute_ai_prompt = original
    db_session.expire_all()
    row = db_session.get(LeadDiagnosticSession, session_id)
    assert row.status == "report_ready"
    assert len(prompts) == 2
    assert "repair" not in prompts[0]
    assert "repair" in prompts[1]
    assert "report_unsourced_number" in prompts[1] or "12" in prompts[1]


def test_worker_uses_sourced_number_set_not_whole_assessment(
    diag_app, diag_client, db_session
) -> None:
    """worker 端到端接线钉（v2 D2）：数字来源集合＝客户答案＋政策引文，
    **不是**整个测算卡——测算卡规则生成文本里的数字不构成来源。"""
    _actor_user(db_session)
    token, session_id = _prepare_session(diag_client)
    diag_client.post(
        "/api/v1/diagnostics/session/report", json={}, headers={TOKEN_HEADER: token}
    )
    db_session.expire_all()
    row = db_session.get(LeadDiagnosticSession, session_id)
    row.assessment = {
        "readiness_tier": "先做基础准备",
        "matched_policies": [],
        "next_actions": ["先做 3 类单据的盘点"],
    }
    db_session.commit()
    bad = _good_payload()
    bad["findings"][0]["problem"] = "现有 3 类单据需要人工核对。"
    row = _run_handler(
        diag_app,
        db_session,
        session_id,
        [json.dumps(bad, ensure_ascii=False), json.dumps(bad, ensure_ascii=False)],
    )
    assert row.status == "submitted"
    assert row.failure_code == "report_unsourced_number"
