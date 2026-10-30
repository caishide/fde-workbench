"""SES 发信策略测试：验收场景矩阵（docs/验收场景矩阵-G3.md）链 3 的 pytest 落地。

G3 只钉纯策略；G9 在此之上接 mock SES 客户端、SNS 回调端点与持久化记录，
场景表必须保持同名映射。
"""
from datetime import timedelta

import pytest

from fde_api.mailing import policy


class TestFourFeedbackStates:
    """场景 3.1：四态分类——throttle 可重试，其余不可。"""

    @pytest.mark.parametrize("event", ["sent", "bounce", "complaint"])
    def test_terminal_states_are_not_retryable(self, event):
        assert policy.feedback_is_retryable(event) is False

    def test_throttle_is_retryable(self):
        assert policy.feedback_is_retryable("throttle") is True

    def test_unknown_state_rejected(self):
        with pytest.raises(ValueError):
            policy.feedback_is_retryable("opened")  # type: ignore[arg]


class TestSuppression:
    """场景 3.6：bounce/complaint 拉黑地址，sent/throttle 不拉黑。"""

    @pytest.mark.parametrize("event", ["bounce", "complaint"])
    def test_bounce_and_complaint_suppress(self, event):
        assert policy.should_suppress(event) is True

    @pytest.mark.parametrize("event", ["sent", "throttle"])
    def test_sent_and_throttle_do_not_suppress(self, event):
        assert policy.should_suppress(event) is False


class TestIdempotency:
    """场景 3.2：同 message_id 二次发送判 drop_duplicate（重试=同 id 新 attempt）。"""

    def test_first_send_passes_the_gate(self):
        decision = policy.decide_send(
            enabled=True,
            message_id="m-1",
            seen_message_ids=set(),
            recipient_suppressed=False,
            today_sent_count=0,
        )
        assert decision.action == policy.SEND

    def test_duplicate_message_id_is_dropped(self):
        decision = policy.decide_send(
            enabled=True,
            message_id="m-1",
            seen_message_ids={"m-1"},
            recipient_suppressed=False,
            today_sent_count=0,
        )
        assert decision.action == policy.DROP_DUPLICATE

    def test_duplicate_decision_precedes_quota_and_suppression(self):
        # 判定顺序：幂等先于限额/抑制——重放旧请求在满额/拉黑后仍判 duplicate
        decision = policy.decide_send(
            enabled=True,
            message_id="m-1",
            seen_message_ids={"m-1"},
            recipient_suppressed=True,
            today_sent_count=99,
        )
        assert decision.action == policy.DROP_DUPLICATE


class TestDailyQuota:
    """场景 3.3：每日限额——达到上限（沙盒默认 10）即拒。"""

    def test_default_sandbox_limit_is_ten(self):
        assert policy.SANDBOX_DAILY_LIMIT == 10

    def test_at_limit_is_dropped(self):
        decision = policy.decide_send(
            enabled=True,
            message_id="m-2",
            seen_message_ids=set(),
            recipient_suppressed=False,
            today_sent_count=10,
        )
        assert decision.action == policy.DROP_OVER_QUOTA

    def test_under_limit_sends(self):
        decision = policy.decide_send(
            enabled=True,
            message_id="m-2",
            seen_message_ids=set(),
            recipient_suppressed=False,
            today_sent_count=9,
        )
        assert decision.action == policy.SEND

    def test_limit_is_configurable(self):
        decision = policy.decide_send(
            enabled=True,
            message_id="m-2",
            seen_message_ids=set(),
            recipient_suppressed=False,
            today_sent_count=200,
            daily_limit=500,
        )
        assert decision.action == policy.SEND


class TestMasterSwitch:
    """场景 3.4：FDE_SES_ENABLED 未开启时一切发送 drop_disabled（默认关闭）。"""

    def test_disabled_beats_everything_else(self):
        decision = policy.decide_send(
            enabled=False,
            message_id="m-3",
            seen_message_ids=set(),
            recipient_suppressed=False,
            today_sent_count=0,
        )
        assert decision.action == policy.DROP_DISABLED

    def test_disabled_even_when_duplicate(self):
        decision = policy.decide_send(
            enabled=False,
            message_id="m-3",
            seen_message_ids={"m-3"},
            recipient_suppressed=False,
            today_sent_count=0,
        )
        assert decision.action == policy.DROP_DISABLED


class TestSenderDomain:
    """场景 3.5：只允许配置子域（如 mail.somwyn.com），主域 somwyn.com 拒绝。"""

    def test_configured_subdomain_root_allowed(self):
        assert policy.is_allowed_sender_domain("mail.somwyn.com", "mail.somwyn.com") is True

    def test_deeper_subdomain_allowed(self):
        assert policy.is_allowed_sender_domain("outbound.mail.somwyn.com", "mail.somwyn.com") is True

    def test_apex_domain_forbidden(self):
        assert policy.is_allowed_sender_domain("somwyn.com", "mail.somwyn.com") is False

    def test_unrelated_domain_forbidden(self):
        assert policy.is_allowed_sender_domain("example.com", "mail.somwyn.com") is False

    def test_lookalike_suffix_forbidden(self):
        # 不是子域，只是后缀碰瓷（evilsomwyn.com）
        assert policy.is_allowed_sender_domain("evilsomwyn.com", "mail.somwyn.com") is False

    def test_case_and_trailing_dot_normalized(self):
        assert policy.is_allowed_sender_domain("Mail.Somwyn.COM.", "mail.somwyn.com") is True


class TestRetrySemantics:
    """throttle 重试：指数退避封顶 15m，attempt 上限 3。"""

    def test_backoff_doubles_then_caps(self):
        assert policy.next_retry_delay(1) == timedelta(minutes=1)
        assert policy.next_retry_delay(2) == timedelta(minutes=2)
        assert policy.next_retry_delay(3) == timedelta(minutes=4)
        assert policy.next_retry_delay(10) == timedelta(minutes=15)

    def test_attempt_must_be_positive(self):
        with pytest.raises(ValueError):
            policy.next_retry_delay(0)

    def test_attempts_beyond_max_are_rejected(self):
        assert policy.retry_allows(0) is True
        assert policy.retry_allows(2) is True
        assert policy.retry_allows(3) is False
