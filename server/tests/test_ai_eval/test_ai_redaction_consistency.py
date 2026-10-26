"""E4 脱敏一致性回归钉：AI 两条路径对同一输入产出相同脱敏结果。

`ai/project_draft.py`（预调研 DOCX → 项目草稿）与 `guidance/jobs.py`（预调研 →
客户目标指引）此前行为不一致：前者把 DOCX 全文直接送进 LLM，未走
`guidance/redaction.py` 的 `redact_text`。本测试钉住两条路径的一致性。
"""
import io

import pytest

from fde_api.ai.project_draft import _messages
from fde_api.guidance.redaction import SensitiveCredentialDetected, redact_text

SENSITIVE_SAMPLE = (
    "联系邮箱 zhang.san@example.com，手机号 13800001111，"
    "座机 0755-88889999，身份证 11010119900307001X。"
)


def test_redact_text_masks_personal_identifiers():
    redacted = redact_text(SENSITIVE_SAMPLE)

    assert "zhang.san@example.com" not in redacted
    assert "13800001111" not in redacted
    assert "0755-88889999" not in redacted
    assert "11010119900307001X" not in redacted
    assert "[邮箱已脱敏]" in redacted
    assert "[手机号已脱敏]" in redacted
    assert "[证件号已脱敏]" in redacted


def test_redact_text_refuses_embedded_credentials():
    with pytest.raises(SensitiveCredentialDetected):
        redact_text("数据库密码：sk-abcdef1234567890abcdef")


def test_project_draft_messages_apply_the_same_redaction():
    """预调研全文进 LLM 前必须与 guidance 路径同套脱敏。"""
    messages = _messages(SENSITIVE_SAMPLE, "pre_diagnosis（预调研）")
    user_content = messages[1]["content"]

    assert "zhang.san@example.com" not in user_content
    assert "13800001111" not in user_content
    assert "11010119900307001X" not in user_content
    assert "[手机号已脱敏]" in user_content


def test_project_draft_refuses_embedded_credentials():
    """疑似凭据的预调研文件必须被明确拒绝，不把原文送出去。"""
    with pytest.raises(SensitiveCredentialDetected):
        _messages("数据库密码：sk-abcdef1234567890abcdef", "pre_diagnosis（预调研）")


def test_project_draft_and_guidance_paths_share_exact_redaction_output():
    """E4：项目草稿消息体与 guidance 的共享 redact_text 对相同原文产出一致结果。"""
    guidance_output = redact_text(SENSITIVE_SAMPLE)
    draft_user_message = _messages(
        SENSITIVE_SAMPLE, "pre_diagnosis（预调研）"
    )[1]["content"]
    assert draft_user_message.endswith(guidance_output)
    assert "zhang.san@example.com" not in draft_user_message
    assert "13800001111" not in draft_user_message
    assert "0755-88889999" not in draft_user_message
    assert "11010119900307001X" not in draft_user_message

import pytest


@pytest.fixture(scope="session", autouse=True)
def migrated_test_schema():
    """离线评测子树：覆盖仓库级迁移夹具，避免初始化共享 PG 测试库。"""
    yield
