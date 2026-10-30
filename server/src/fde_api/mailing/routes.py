"""WP-E SES 回调路由（goal-r3 G9 预建）。

只暴露 SNS 退信/投诉回调端点。**不走 require_auth**——SNS 服务器不可能携带
工作台 JWT；鉴权由 service 层的签名校验 + TopicArn 白名单承担（签名即鉴权）。
发送路径不设 HTTP 路由：send_email 是 service 函数，批复下来由 worker/n8n
桥接层调用（避免在 SES 未批复时出现可打的发信口）。

SNS 的 POST 默认 content-type 是 text/plain，因此解析必须 force=True。
"""
from __future__ import annotations

from typing import Any

from flask import Blueprint, current_app, request

from fde_api.errors import error_response
from fde_api.extensions import db
from fde_api.mailing.service import MailingServiceError, handle_sns_envelope

mailing_blueprint = Blueprint("mailing", __name__, url_prefix="/api/v1/mailing")


@mailing_blueprint.post("/sns/events")
def sns_events_route():
    """SNS 退信/投诉/订阅确认回调。校验失败一律 403（SNS 会对非 2xx 重试）。"""
    envelope: Any = request.get_json(force=True, silent=True)
    session = db.session()
    try:
        result = handle_sns_envelope(
            settings=current_app.config["SETTINGS"], session=session, envelope=envelope
        )
        return {"status": result["status"], "data": result}, 200
    except MailingServiceError as error:
        return error_response(error.code, error.message, error.http_status)
    finally:
        session.close()
