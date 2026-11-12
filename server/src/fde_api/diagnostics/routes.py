"""诊断域路由（获客诊断工具 T-10a）。

**这是本仓第一个公网免注册写面**——因此路由层的纪律比别的域更严：

- **无 JWT**（免注册是设计），但**有部署闸**：``FDE_DIAGNOSTICS_ENABLED``
  默认关闭 ⇒ 一律 404（不确认面存在）。D-3 独立轻部署：诊断面单独
  compose / 单独库 / 单独域名，与工作台真相层物理隔离。
- **会话令牌走请求头**（``X-Diagnostic-Token``），**不放 URL**——URL 会进
  访问日志，令牌是持有即权的凭证。
- **来源参数** ``source_type`` / ``channel_ref`` 由**渠道链接自带**（R4 专属
  诊断链接），服务端据此落归因，**零手工记账**（P-2）。
"""
from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, request

from fde_api.diagnostics import service
from fde_api.diagnostics.questionnaire import questionnaire_payload
from fde_api.errors import error_response

diagnostics_blueprint = Blueprint("diagnostics", __name__, url_prefix="/api/v1/diagnostics")

TOKEN_HEADER = "X-Diagnostic-Token"

MAX_CHANNEL_REF_CHARS = 80


def _payload() -> dict[str, Any]:
    value = request.get_json(silent=True)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise service.DiagnosticsServiceError("invalid_request", "请求内容必须为 JSON 对象。", 400)
    return value


def _data(value: Any):
    return jsonify({"data": value, "error": None})


def _token() -> str:
    token = request.headers.get(TOKEN_HEADER, "").strip()
    if not token:
        raise service.DiagnosticsServiceError(
            "session_token_required",
            "缺少会话令牌，请在 X-Diagnostic-Token 请求头中携带。",
            401,
        )
    return token


def _channel_ref() -> str | None:
    raw = request.args.get("channel_ref", "").strip()
    if not raw:
        return None
    if len(raw) > MAX_CHANNEL_REF_CHARS:
        raise service.DiagnosticsServiceError(
            "invalid_channel_ref", "渠道标识过长。", 400
        )
    return raw


@diagnostics_blueprint.get("/questionnaire")
def questionnaire_route():
    """固定诊断问卷定义（公开只读；不含答案键）。"""
    service.ensure_enabled()
    return _data(questionnaire_payload())


@diagnostics_blueprint.post("/sessions")
def create_session_route():
    """创建匿名会话；返回明文令牌（**只此一次**，库里只存指纹）。"""
    service.ensure_enabled()
    body = _payload()
    source_type = body.get("source_type") or "direct"
    if not isinstance(source_type, str):
        raise service.DiagnosticsServiceError("invalid_source_type", "来源类型非法。", 400)
    channel_ref = body.get("channel_ref") or _channel_ref()
    if channel_ref is not None and not isinstance(channel_ref, str):
        raise service.DiagnosticsServiceError("invalid_channel_ref", "渠道标识必须是字符串。", 400)
    if channel_ref is not None and len(channel_ref) > 80:
        raise service.DiagnosticsServiceError("invalid_channel_ref", "渠道标识过长。", 400)
    row, token = service.create_session(
        ip_address=request.remote_addr,
        source_type=source_type,
        channel_ref=channel_ref,
    )
    return _data({**service.serialize_session(row), "token": token})


@diagnostics_blueprint.get("/session")
def get_session_route():
    """读会话状态 + 测算卡（免注册可见；报告需已留资）。"""
    service.ensure_enabled()
    row = service.get_session(_token())
    return _data(service.serialize_session(row))


@diagnostics_blueprint.post("/session/assessment")
def submit_assessment_route():
    """提交首屏答案 → 纯规则出政策补贴测算卡（零 AI、即时可见）。"""
    service.ensure_enabled()
    body = _payload()
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise service.DiagnosticsServiceError(
            "invalid_answers", "answers 必须是对象。", 400
        )
    row = service.submit_first_screen(_token(), answers)
    return _data(service.serialize_session(row))


@diagnostics_blueprint.post("/session/answers")
def submit_answers_route():
    """提交诊断问卷答案（续填；需先完成首屏测算）。"""
    service.ensure_enabled()
    body = _payload()
    answers = body.get("answers")
    if not isinstance(answers, dict):
        raise service.DiagnosticsServiceError(
            "invalid_answers", "answers 必须是对象。", 400
        )
    row = service.submit_answers(_token(), answers)
    return _data(service.serialize_session(row))


@diagnostics_blueprint.post("/session/lead")
def capture_lead_route():
    """留资（提交联系方式 + 隐私政策同意）——完整报告的解锁条件。"""
    service.ensure_enabled()
    body = _payload()
    contact = body.get("contact")
    if not isinstance(contact, dict):
        raise service.DiagnosticsServiceError(
            "invalid_contact", "contact 必须是对象。", 400
        )
    row = service.capture_lead(_token(), contact)
    return _data(service.serialize_session(row))


@diagnostics_blueprint.post("/session/report")
def request_report_route():
    """受理报告生成（**异步**）：立即返回 202，报告就绪后轮询会话。"""
    service.ensure_enabled()
    row = service.request_report(_token())
    return _data(service.serialize_session(row)), 202


@diagnostics_blueprint.post("/session/share")
def create_share_link_route():
    """生成分享链接（**只读**凭证；明文只此一次，每次调用轮换旧链接）。"""
    service.ensure_enabled()
    row, share_token = service.create_share_link(_token())
    return _data(
        {
            **service.serialize_session(row),
            "share_token": share_token,
            "share_path": f"/api/v1/diagnostics/share/{share_token}",
        }
    )


@diagnostics_blueprint.get("/share/<share_token>")
def read_share_route(share_token: str):
    """分享页只读视图（**摘要层**；不含企业自填原文与联系方式）。"""
    service.ensure_enabled()
    return _data(service.read_share(share_token))


@diagnostics_blueprint.app_errorhandler(service.DiagnosticsServiceError)
def handle_service_error(error: service.DiagnosticsServiceError):
    return error_response(error.code, error.message, error.status, error.detail or None)
