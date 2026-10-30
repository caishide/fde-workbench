"""WP-E SESv2 发送客户端（goal-r3 G9 预建）。

协议层与 AWS 解耦：service 只依赖 :class:`SesClient` 协议，测试用内存假客户端
（G3 场景矩阵链 3 的 mock 口径），**绝不发送真实邮件**。真实的
:class:`BotoSesClient` 只在 ``FDE_SES_ENABLED=true`` 时由工厂构造，boto3 延迟
导入——默认关闭的部署不触碰 AWS 栈。

错误分类沿 guidance 的口径：throttle 可重试，其余（域名未验证/模板拒收/认证）
不可重试——调用方按 ``SesSendError.retryable`` 走 policy.retry_allows 退避。
"""
from __future__ import annotations

from typing import Protocol

from fde_api.config import Settings


class SesSendError(Exception):
    """发送失败的可分类错误。"""

    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class SesClient(Protocol):
    """SESv2 SendEmail 的最小协议面。"""

    def send_text(
        self, *, sender: str, recipient: str, subject: str, body: str
    ) -> str:
        """发送纯文本邮件，返回 SES MessageId。"""
        ...  # pragma: no cover - 协议方法


class BotoSesClient:
    """SESv2 真客户端（boto3 延迟导入；仅 enabled 时构造）。"""

    def __init__(self, settings: Settings) -> None:
        import boto3  # 延迟导入：默认关闭的部署不 import AWS 栈

        self._settings = settings
        self._client = boto3.client("sesv2", region_name=settings.ses_region)

    def send_text(
        self, *, sender: str, recipient: str, subject: str, body: str
    ) -> str:
        from botocore.exceptions import ClientError

        kwargs: dict[str, object] = {
            "FromEmailAddress": sender,
            "Destination": {"ToAddresses": [recipient]},
            "Content": {
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                }
            },
        }
        if self._settings.ses_reply_to_address:
            kwargs["ReplyToAddresses"] = [self._settings.ses_reply_to_address]
        if self._settings.ses_configuration_set:
            kwargs["ConfigurationSetName"] = self._settings.ses_configuration_set
        try:
            response = self._client.send_email(**kwargs)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "")
            if code in ("Throttling", "ThrottlingException"):
                raise SesSendError("throttle", "SES throttling.", retryable=True) from error
            if code == "MessageRejected":
                raise SesSendError(
                    "message_rejected", "SES rejected the message.", retryable=False
                ) from error
            raise SesSendError(
                "send_failed", f"SES send failed: {code or 'unknown'}.", retryable=False
            ) from error
        message_id = response.get("MessageId")
        if not isinstance(message_id, str) or not message_id:
            raise SesSendError(
                "send_failed", "SES returned no MessageId.", retryable=False
            )
        return message_id


def create_ses_client(settings: Settings) -> SesClient | None:
    """工厂：模块关闭返回 None（service 直接落 mailing_disabled）。"""
    if not settings.ses_enabled:
        return None
    return BotoSesClient(settings)
