"""WP-E SES 发信模块 mock 全覆盖（goal-r3 G9，落地 G3 场景矩阵链 3）。

红线：绝不发送真实邮件——AWS 面全部 mock（假客户端 / botocore Stubber /
签名证书测试内自签 + fetch 注入）。覆盖：

- 发送闸门接线（policy.decide_send 的服务层落地）：开关 / 幂等 / 抑制 /
  限额（含「只数当日」口径）/ 发信域约束（主域拒绝）；
- throttle / 拒收的事件留痕与可重试性；
- BotoSesClient 的 boto3 参数映射与错误分类（Stubber，无网络）；
- SNS 回调：订阅确认 / bounce / complaint / delivery、幂等重放、
  签名与主题白名单拒绝、HTTP 路由（含 text/plain content-type）；
- 配置校验器：enabled 必带子域/FROM/TopicArn，主域 FROM 拒绝。
"""
from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from botocore.stub import Stubber
from flask import Flask
from sqlalchemy import select

from fde_api.config import Settings
from fde_api.mailing import policy, service
from fde_api.mailing.models import MailingEvent, MailingSend
from fde_api.mailing.ses_client import (
    BotoSesClient,
    SesSendError,
    create_ses_client,
)
from fde_api.mailing.service import MailingServiceError, handle_sns_envelope, send_email

TEST_ARN = "arn:aws:sns:us-east-1:111122223333:fde-mail-events"


def enabled_settings(test_settings: Settings, **overrides: Any) -> Settings:
    """启用态配置。model_copy 跳过校验器——主域 FROM 等非法面由此构造。"""
    return test_settings.model_copy(
        update={
            "ses_enabled": True,
            "ses_send_subdomain": "mail.somwyn.com",
            "ses_from_address": "no-reply@mail.somwyn.com",
            "ses_topic_arn": TEST_ARN,
            "ses_daily_limit": 2,
            **overrides,
        }
    )


class FakeSesClient:
    """内存假客户端：计数调用，可注入异常（绝不发真邮件）。"""

    def __init__(self, message_id: str = "ses-msg-1", error: SesSendError | None = None):
        self.calls: list[dict[str, str]] = []
        self.message_id = message_id
        self.error = error

    def send_text(self, *, sender: str, recipient: str, subject: str, body: str) -> str:
        self.calls.append(
            {"sender": sender, "recipient": recipient, "subject": subject, "body": body}
        )
        if self.error is not None:
            raise self.error
        return self.message_id


# ---------------------------------------------------------------------------
# 发送闸门
# ---------------------------------------------------------------------------


def test_send_disabled_rejects(test_settings, db_session):
    with pytest.raises(MailingServiceError) as err:
        send_email(
            settings=test_settings,
            session=db_session,
            recipient="lead@example.com",
            subject="hi",
            body="hi",
            idempotency_key="k1",
        )
    assert err.value.code == policy.DROP_DISABLED
    assert err.value.http_status == 409


def test_send_happy_path_records_send(test_settings, db_session):
    fake = FakeSesClient()
    result = send_email(
        settings=enabled_settings(test_settings),
        session=db_session,
        recipient="lead@example.com",
        subject="预调研提醒",
        body="正文",
        idempotency_key="notify:p1:v1",
        client=fake,
    )
    assert result == {"action": policy.SEND, "message_id": "ses-msg-1"}
    assert len(fake.calls) == 1
    assert fake.calls[0]["sender"] == "no-reply@mail.somwyn.com"
    row = db_session.scalar(select(MailingSend).where(MailingSend.idempotency_key == "notify:p1:v1"))
    assert row is not None
    assert row.message_id == "ses-msg-1"
    assert row.status == "sent"
    assert row.recipient == "lead@example.com"


def test_send_duplicate_idempotency_key_drops(test_settings, db_session):
    fake = FakeSesClient()
    kwargs = dict(
        settings=enabled_settings(test_settings),
        session=db_session,
        recipient="lead@example.com",
        subject="s",
        body="b",
        idempotency_key="dup-1",
        client=fake,
    )
    send_email(**kwargs)
    with pytest.raises(MailingServiceError) as err:
        send_email(**kwargs)
    assert err.value.code == policy.DROP_DUPLICATE
    assert len(fake.calls) == 1  # 重试=同键新 attempt；同键二次请求不再打 SES


def test_send_suppressed_recipient_drops(test_settings, db_session):
    db_session.add(
        MailingEvent(
            event_key="old-msg:bounce:lead@example.com",
            notification_type="bounce",
            recipient="lead@example.com",
            feedback_type="Permanent",
        )
    )
    db_session.commit()
    fake = FakeSesClient()
    with pytest.raises(MailingServiceError) as err:
        send_email(
            settings=enabled_settings(test_settings),
            session=db_session,
            recipient="lead@example.com",
            subject="s",
            body="b",
            idempotency_key="sup-1",
            client=fake,
        )
    assert err.value.code == policy.DROP_SUPPRESSED
    assert fake.calls == []


def test_send_over_quota_drops(test_settings, db_session):
    cfg = enabled_settings(test_settings)  # ses_daily_limit=2
    fake = FakeSesClient()
    for i in range(2):
        send_email(
            settings=cfg,
            session=db_session,
            recipient=f"lead{i}@example.com",
            subject="s",
            body="b",
            idempotency_key=f"q-{i}",
            client=fake,
        )
    with pytest.raises(MailingServiceError) as err:
        send_email(
            settings=cfg,
            session=db_session,
            recipient="third@example.com",
            subject="s",
            body="b",
            idempotency_key="q-3",
            client=fake,
        )
    assert err.value.code == policy.DROP_OVER_QUOTA
    assert len(fake.calls) == 2


def test_send_quota_only_counts_today(test_settings, db_session):
    cfg = enabled_settings(test_settings)
    yesterday = datetime.now(UTC) - timedelta(days=1)
    for i in range(2):
        db_session.add(
            MailingSend(
                idempotency_key=f"y-{i}",
                message_id=f"old-{i}",
                sender="no-reply@mail.somwyn.com",
                recipient=f"y{i}@example.com",
                status="sent",
                sent_at=yesterday,
            )
        )
    db_session.commit()
    fake = FakeSesClient()
    result = send_email(
        settings=cfg,
        session=db_session,
        recipient="today@example.com",
        subject="s",
        body="b",
        idempotency_key="today-1",
        client=fake,
    )
    assert result["action"] == policy.SEND  # 昨天的发送不占今日限额


def test_send_main_domain_forbidden(test_settings, db_session):
    # model_copy 跳过校验器：构造「FROM 在主域」的非法配置面，服务层必须拦
    cfg = enabled_settings(
        test_settings,
        ses_from_address="no-reply@somwyn.com",
    )
    fake = FakeSesClient()
    with pytest.raises(MailingServiceError) as err:
        send_email(
            settings=cfg,
            session=db_session,
            recipient="lead@example.com",
            subject="s",
            body="b",
            idempotency_key="dom-1",
            client=fake,
        )
    assert err.value.code == policy.DROP_DOMAIN
    assert fake.calls == []


def test_send_throttle_records_event_and_retryable(test_settings, db_session):
    fake = FakeSesClient(error=SesSendError("throttle", "SES throttling.", retryable=True))
    with pytest.raises(MailingServiceError) as err:
        send_email(
            settings=enabled_settings(test_settings),
            session=db_session,
            recipient="lead@example.com",
            subject="s",
            body="b",
            idempotency_key="th-1",
            client=fake,
        )
    assert err.value.code == "throttle"
    assert err.value.http_status == 503  # retryable
    event = db_session.scalar(select(MailingEvent).where(MailingEvent.recipient == "lead@example.com"))
    assert event is not None
    assert event.notification_type == "throttle"
    assert db_session.scalars(select(MailingSend)).all() == []  # 失败不占发送台账


def test_send_rejected_records_failure(test_settings, db_session):
    fake = FakeSesClient(
        error=SesSendError("message_rejected", "rejected.", retryable=False)
    )
    with pytest.raises(MailingServiceError) as err:
        send_email(
            settings=enabled_settings(test_settings),
            session=db_session,
            recipient="lead@example.com",
            subject="s",
            body="b",
            idempotency_key="rj-1",
            client=fake,
        )
    assert err.value.http_status == 502  # 不可重试
    event = db_session.scalar(select(MailingEvent).where(MailingEvent.event_key == "rj-1:message_rejected:lead@example.com"))
    assert event is not None
    assert event.notification_type == "send_failed"


def test_factory_none_when_disabled(test_settings):
    assert create_ses_client(test_settings) is None


def test_factory_boto_client_when_enabled(test_settings):
    client = create_ses_client(enabled_settings(test_settings))
    assert isinstance(client, BotoSesClient)


# ---------------------------------------------------------------------------
# BotoSesClient（Stubber：参数映射与错误分类，无网络）
# ---------------------------------------------------------------------------


def _stub_client(test_settings, **overrides):
    client = BotoSesClient(enabled_settings(test_settings, **overrides))
    return client, Stubber(client._client)


def test_boto_client_send_maps_fields(test_settings):
    client, stubber = _stub_client(
        test_settings,
        ses_reply_to_address="reply@mail.somwyn.com",
        ses_configuration_set="fde-mail",
    )
    expected = {
        "FromEmailAddress": "no-reply@mail.somwyn.com",
        "Destination": {"ToAddresses": ["lead@example.com"]},
        "Content": {
            "Simple": {
                "Subject": {"Data": "主题", "Charset": "UTF-8"},
                "Body": {"Text": {"Data": "正文", "Charset": "UTF-8"}},
            }
        },
        "ReplyToAddresses": ["reply@mail.somwyn.com"],
        "ConfigurationSetName": "fde-mail",
    }
    stubber.add_response("send_email", {"MessageId": "aws-111"}, expected)
    with stubber:
        message_id = client.send_text(
            sender="no-reply@mail.somwyn.com",
            recipient="lead@example.com",
            subject="主题",
            body="正文",
        )
    assert message_id == "aws-111"
    stubber.assert_no_pending_responses()


def test_boto_client_throttle_is_retryable(test_settings):
    from botocore.exceptions import ClientError

    client, stubber = _stub_client(test_settings)
    stubber.add_client_error(
        "send_email", "ThrottlingException", expected_params={"FromEmailAddress": "no-reply@mail.somwyn.com",
        "Destination": {"ToAddresses": ["lead@example.com"]},
        "Content": {
            "Simple": {
                "Subject": {"Data": "s", "Charset": "UTF-8"},
                "Body": {"Text": {"Data": "b", "Charset": "UTF-8"}},
            }
        }}
    )
    with stubber:
        with pytest.raises(SesSendError) as err:
            client.send_text(
                sender="no-reply@mail.somwyn.com",
                recipient="lead@example.com",
                subject="s",
                body="b",
            )
    assert err.value.retryable is True
    assert err.value.code == "throttle"


def test_boto_client_rejected_is_not_retryable(test_settings):
    from botocore.exceptions import ClientError

    client, stubber = _stub_client(test_settings)
    stubber.add_client_error(
        "send_email", "MessageRejected", expected_params={"FromEmailAddress": "no-reply@mail.somwyn.com",
        "Destination": {"ToAddresses": ["lead@example.com"]},
        "Content": {
            "Simple": {
                "Subject": {"Data": "s", "Charset": "UTF-8"},
                "Body": {"Text": {"Data": "b", "Charset": "UTF-8"}},
            }
        }}
    )
    with stubber:
        with pytest.raises(SesSendError) as err:
            client.send_text(
                sender="no-reply@mail.somwyn.com",
                recipient="lead@example.com",
                subject="s",
                body="b",
            )
    assert err.value.retryable is False


# ---------------------------------------------------------------------------
# SNS 回调
# ---------------------------------------------------------------------------

_CONFIRM_FIELDS = ("Message", "MessageId", "SubscribeURL", "Timestamp", "TopicArn", "Type")
_NOTIFICATION_FIELDS = ("Message", "MessageId", "Timestamp", "TopicArn", "Type")
SUBSCRIBE_URL = "https://sns.us-east-1.amazonaws.com/SubscriptionConfirmation?u=t"
CERT_URL = "https://sns.us-east-1.amazonaws.com/SimpleNotificationService-cert.pem"


def _base_envelope(message: str, message_type: str) -> dict[str, Any]:
    return {
        "Type": message_type,
        "MessageId": "sns-env-1",
        "TopicArn": TEST_ARN,
        "Timestamp": "2026-10-30T12:00:00.000Z",
        "SignatureVersion": "1",
        "SigningCertURL": CERT_URL,
        "SubscribeURL": SUBSCRIBE_URL,
        "Signature": "",
        "Message": message,
    }


def _sign(envelope: dict[str, Any], key: Any) -> dict[str, Any]:
    fields = (
        _CONFIRM_FIELDS if envelope["Type"].endswith("Confirmation") else _NOTIFICATION_FIELDS
    )
    canonical = "".join(str(envelope.get(f, "")) for f in fields)
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    signature = key.sign(canonical.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
    envelope["Signature"] = base64.b64encode(signature).decode("ascii")
    return envelope


@pytest.fixture(scope="module")
def sns_key():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.us-east-1.amazonaws.com")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return key, cert.public_bytes(serialization.Encoding.PEM)


def _fetch_factory(cert_pem: bytes, seen: list[str]):
    def fetch(url: str) -> bytes:
        seen.append(url)
        if url == CERT_URL:
            return cert_pem
        return b"{}"

    return fetch


def test_sns_disabled_rejected(test_settings, db_session):
    with pytest.raises(MailingServiceError) as err:
        handle_sns_envelope(
            settings=test_settings, session=db_session, envelope={"Type": "Notification"}
        )
    assert err.value.code == "mailing_disabled"
    assert err.value.http_status == 403


def test_sns_subscription_confirmation_records(test_settings, db_session, sns_key):
    key, cert_pem = sns_key
    seen: list[str] = []
    envelope = _sign(_base_envelope("subscribe", "SubscriptionConfirmation"), key)
    result = handle_sns_envelope(
        settings=enabled_settings(test_settings),
        session=db_session,
        envelope=envelope,
        fetch=_fetch_factory(cert_pem, seen),
    )
    assert result == {"status": "confirmed", "recorded": 1, "duplicates": 0}
    assert SUBSCRIBE_URL in seen  # 回访了订阅确认 URL
    event = db_session.scalar(select(MailingEvent).where(MailingEvent.notification_type == "subscription_confirmed"))
    assert event is not None
    # 重放：SNS at-least-once，不重复记
    again = handle_sns_envelope(
        settings=enabled_settings(test_settings),
        session=db_session,
        envelope=dict(envelope),
        fetch=_fetch_factory(cert_pem, []),
    )
    assert again["recorded"] == 0


def test_sns_bounce_records_per_recipient_and_suppresses(test_settings, db_session, sns_key):
    key, cert_pem = sns_key
    notification = {
        "notificationType": "bounce",
        "mail": {"messageId": "aws-bounce-1"},
        "bounce": {
            "bounceType": "Permanent",
            "bounceSubType": "General",
            "bouncedRecipients": [
                {"emailAddress": "dead@example.com"},
                {"emailAddress": "gone@example.com"},
            ],
        },
    }
    envelope = _sign(_base_envelope(json.dumps(notification), "Notification"), key)
    result = handle_sns_envelope(
        settings=enabled_settings(test_settings),
        session=db_session,
        envelope=envelope,
        fetch=_fetch_factory(cert_pem, []),
    )
    assert result == {"status": "processed", "recorded": 2, "duplicates": 0}
    # 同址再发 → 抑制
    fake = FakeSesClient()
    with pytest.raises(MailingServiceError) as err:
        send_email(
            settings=enabled_settings(test_settings),
            session=db_session,
            recipient="dead@example.com",
            subject="s",
            body="b",
            idempotency_key="after-bounce",
            client=fake,
        )
    assert err.value.code == policy.DROP_SUPPRESSED
    assert fake.calls == []


def test_sns_bounce_redelivery_is_idempotent(test_settings, db_session, sns_key):
    key, cert_pem = sns_key
    notification = {
        "notificationType": "bounce",
        "mail": {"messageId": "aws-bounce-2"},
        "bounce": {
            "bounceType": "Permanent",
            "bounceSubType": "General",
            "bouncedRecipients": [{"emailAddress": "dead2@example.com"}],
        },
    }
    envelope = _sign(_base_envelope(json.dumps(notification), "Notification"), key)
    first = handle_sns_envelope(
        settings=enabled_settings(test_settings),
        session=db_session,
        envelope=envelope,
        fetch=_fetch_factory(cert_pem, []),
    )
    second = handle_sns_envelope(
        settings=enabled_settings(test_settings),
        session=db_session,
        envelope=dict(envelope),
        fetch=_fetch_factory(cert_pem, []),
    )
    assert first["recorded"] == 1
    assert second == {"status": "processed", "recorded": 0, "duplicates": 1}


def test_sns_complaint_records_feedback_type(test_settings, db_session, sns_key):
    key, cert_pem = sns_key
    notification = {
        "notificationType": "complaint",
        "mail": {"messageId": "aws-comp-1"},
        "complaint": {
            "complaintFeedbackType": "abuse",
            "complainedRecipients": [{"emailAddress": "annoyed@example.com"}],
        },
    }
    envelope = _sign(_base_envelope(json.dumps(notification), "Notification"), key)
    result = handle_sns_envelope(
        settings=enabled_settings(test_settings),
        session=db_session,
        envelope=envelope,
        fetch=_fetch_factory(cert_pem, []),
    )
    assert result["recorded"] == 1
    event = db_session.scalar(
        select(MailingEvent).where(MailingEvent.recipient == "annoyed@example.com")
    )
    assert event.notification_type == "complaint"
    assert event.feedback_type == "abuse"
    assert event.payload_sha256  # 原文指纹在库，原文不在


def test_sns_delivery_not_suppressing(test_settings, db_session, sns_key):
    key, cert_pem = sns_key
    notification = {
        "notificationType": "delivery",
        "mail": {"messageId": "aws-del-1"},
        "delivery": {"recipients": [{"emailAddress": "ok@example.com"}]},
    }
    envelope = _sign(_base_envelope(json.dumps(notification), "Notification"), key)
    handle_sns_envelope(
        settings=enabled_settings(test_settings),
        session=db_session,
        envelope=envelope,
        fetch=_fetch_factory(cert_pem, []),
    )
    fake = FakeSesClient()
    result = send_email(
        settings=enabled_settings(test_settings),
        session=db_session,
        recipient="ok@example.com",
        subject="s",
        body="b",
        idempotency_key="after-delivery",
        client=fake,
    )
    assert result["action"] == policy.SEND  # delivery 不影响地址


def test_sns_wrong_topic_rejected(test_settings, db_session, sns_key):
    key, cert_pem = sns_key
    envelope = _sign(_base_envelope("x", "SubscriptionConfirmation"), key)
    envelope["TopicArn"] = "arn:aws:sns:us-east-1:111122223333:other-topic"
    with pytest.raises(MailingServiceError) as err:
        handle_sns_envelope(
            settings=enabled_settings(test_settings),
            session=db_session,
            envelope=envelope,
            fetch=_fetch_factory(cert_pem, []),
        )
    assert err.value.code == "unknown_sns_topic"
    assert err.value.http_status == 403


def test_sns_bad_signature_rejected(test_settings, db_session, sns_key):
    key, cert_pem = sns_key
    envelope = _sign(_base_envelope("x", "SubscriptionConfirmation"), key)
    envelope["Message"] = "tampered"  # 签名与内容不再匹配
    with pytest.raises(MailingServiceError) as err:
        handle_sns_envelope(
            settings=enabled_settings(test_settings),
            session=db_session,
            envelope=envelope,
            fetch=_fetch_factory(cert_pem, []),
        )
    assert err.value.code == "invalid_sns_signature"


def test_sns_foreign_cert_url_rejected(test_settings, db_session, sns_key):
    key, cert_pem = sns_key
    envelope = _sign(_base_envelope("x", "SubscriptionConfirmation"), key)
    envelope["SigningCertURL"] = "https://evil.example.com/cert.pem"
    seen: list[str] = []
    with pytest.raises(MailingServiceError) as err:
        handle_sns_envelope(
            settings=enabled_settings(test_settings),
            session=db_session,
            envelope=envelope,
            fetch=_fetch_factory(cert_pem, seen),
        )
    assert err.value.code == "invalid_sns_certificate_url"
    assert seen == []  # 未发起任何外联


def test_sns_invalid_notification_json_rejected(test_settings, db_session, sns_key):
    key, cert_pem = sns_key
    envelope = _sign(_base_envelope("not-json", "Notification"), key)
    with pytest.raises(MailingServiceError) as err:
        handle_sns_envelope(
            settings=enabled_settings(test_settings),
            session=db_session,
            envelope=envelope,
            fetch=_fetch_factory(cert_pem, []),
        )
    assert err.value.code == "invalid_sns_notification"


# ---------------------------------------------------------------------------
# HTTP 路由 + 配置校验器
# ---------------------------------------------------------------------------


def test_sns_route_disabled_403(test_settings):
    from fde_api.app import create_app

    app: Flask = create_app(test_settings)
    app.config.update(TESTING=True)
    client = app.test_client()
    response = client.post(
        "/api/v1/mailing/sns/events", json={"Type": "Notification", "MessageId": "m"}
    )
    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "mailing_disabled"


def test_sns_route_accepts_text_plain_envelope(test_settings, sns_key, monkeypatch):
    """SNS 的 POST 是 text/plain——路由必须 force 解析。"""
    from fde_api.app import create_app

    key, cert_pem = sns_key
    envelope = _sign(_base_envelope(json.dumps({
        "notificationType": "delivery",
        "mail": {"messageId": "aws-route-1"},
        "delivery": {"recipients": [{"emailAddress": "route@example.com"}]},
    }), "Notification"), key)
    monkeypatch.setattr(
        service, "_default_fetch", _fetch_factory(cert_pem, [])
    )
    app = create_app(enabled_settings(test_settings))
    app.config.update(TESTING=True)
    client = app.test_client()
    response = client.post(
        "/api/v1/mailing/sns/events",
        data=json.dumps(envelope),
        content_type="text/plain",
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["recorded"] == 1


def test_settings_validator_requires_ses_surface(test_settings):
    base = dict(
        env="test",
        database_url=test_settings.database_url,
        redis_url="redis://127.0.0.1:16379/2",
        jwt_secret="test-secret-with-at-least-thirty-two-characters",
        ses_enabled=True,
    )
    with pytest.raises(ValueError, match="missing_ses_sender_configuration"):
        Settings(**base, ses_topic_arn=TEST_ARN)
    with pytest.raises(ValueError, match="missing_ses_topic_arn"):
        Settings(
            **base,
            ses_send_subdomain="mail.somwyn.com",
            ses_from_address="no-reply@mail.somwyn.com",
            ses_topic_arn="",
        )
    with pytest.raises(ValueError, match="ses_sender_domain_forbidden"):
        Settings(
            **base,
            ses_send_subdomain="mail.somwyn.com",
            ses_from_address="no-reply@somwyn.com",  # 主域不发信
            ses_topic_arn=TEST_ARN,
        )
    valid = Settings(
        **base,
        ses_send_subdomain="mail.somwyn.com",
        ses_from_address="no-reply@mail.somwyn.com",
        ses_topic_arn=TEST_ARN,
    )
    assert valid.ses_enabled is True
