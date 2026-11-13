"""goal-crv 修复批 B 回归钉（QR-024 直连流式计量 + QR-025 预调研 DOCX 原件零外发）。

测试数据全部为合成样本（AGENTS.md 红线：真实客户资料不可入仓）。
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from uuid import uuid4

import pytest
from flask import g
from sqlalchemy import select

from fde_api.ai.auditing import tokens_used_this_month
from fde_api.ai.deepseek import DeepSeekClient, DeepSeekError
from fde_api.ai.kimi import KimiFileClient
from fde_api.ai.project_draft import ProjectDraftError, draft_from_presurvey
from fde_api.auth.models import User
from fde_api.config import Settings
from fde_api.extensions import db
from fde_api.guidance.enterprise_dict import EXTRA_DICT_ENV, reset_dict_cache
from fde_api.workbench.models import AICallAudit, ModuleCatalog

_SYNTHETIC_ENTERPRISE = "黑名单示例控股公司"  # server/seeds/enterprise-names.txt 合成示例
_SYNTHETIC_CREDENTIAL = "接口密钥：example-api-key-not-real-123456"


class _FakeDirectResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, stream_lines: list[bytes | str] | None = None):
        self.status_code = status_code
        self.headers: dict[str, str] = {}
        self._payload = payload
        self._stream_lines = stream_lines or []

    def json(self):
        if self._payload is None:
            raise ValueError("SSE stream body is not single JSON")
        return self._payload

    def iter_lines(self, decode_unicode: bool = False):
        return iter(self._stream_lines)


class _RecordingSession:
    def __init__(self, responses: list[_FakeDirectResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def post(self, url: str, **kwargs):
        self.calls.append(("post", url, kwargs))
        return self._responses.pop(0)

    def get(self, url: str, **kwargs):  # pragma: no cover - 若被调即红线失守
        self.calls.append(("get", url, kwargs))
        raise AssertionError(f"unexpected GET {url}")

    def delete(self, url: str, **kwargs):  # pragma: no cover - 若被调即红线失守
        self.calls.append(("delete", url, kwargs))
        raise AssertionError(f"unexpected DELETE {url}")


def _make_user(db_session, prefix: str) -> User:
    user = User(
        username=f"{prefix}.{uuid4().hex[:8]}",
        display_name=prefix,
        role="admin",
        password_hash="unused",
        must_change_password=False,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _docx_bytes(text: str) -> io.BytesIO:
    from docx import Document

    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


# --- QR-024：直连腿流式 usage 采集、诚实 None 与预算闸真实计量 ----------------


def test_qr024_stream_parses_terminal_empty_choices_usage_and_matches_non_stream(app, db_session, monkeypatch):
    """流式与非流式在相同 token 用量下入账数值完全对齐，且流式末端 choices=[] 不丢 usage。"""
    monkeypatch.setattr(app.config["SETTINGS"], "dsh_enabled", False)
    monkeypatch.setattr(app.config["SETTINGS"], "ai_monthly_token_budget", 0)

    stream_user = _make_user(db_session, "qr024.stream")
    sync_user = _make_user(db_session, "qr024.sync")

    sse_lines = [
        b'data: {"choices":[{"delta":{"reasoning_content":"step1"}}],"usage":null}',
        b'data: {"choices":[{"delta":{"content":"{\\"ok\\":true}"}}],"usage":null}',
        b'data: {"choices":[],"usage":{"prompt_tokens":42,"completion_tokens":18,"total_tokens":60}}',
        b"data: [DONE]",
    ]
    sync_payload = {
        "choices": [{"message": {"content": '{"ok":true}'}}],
        "usage": {"prompt_tokens": 42, "completion_tokens": 18, "total_tokens": 60},
    }

    stream_session = _RecordingSession([_FakeDirectResponse(200, payload=None, stream_lines=sse_lines)])
    sync_session = _RecordingSession([_FakeDirectResponse(200, payload=sync_payload)])

    events: list[dict[str, str]] = []
    stream_req_id = f"qr024-stream-{uuid4().hex[:8]}"
    sync_req_id = f"qr024-sync-{uuid4().hex[:8]}"

    with app.app_context():
        g.current_user = stream_user
        stream_res = DeepSeekClient(
            base_url="https://api.deepseek.example",
            api_key="test-key",
            model="deepseek-chat",
            timeout_seconds=15,
            session=stream_session,
            sleep=lambda _: None,
        ).complete_json(
            messages=[{"role": "user", "content": "ping"}],
            request_id=stream_req_id,
            on_event=events.append,
            purpose="unit_test",
        )

        g.current_user = sync_user
        sync_res = DeepSeekClient(
            base_url="https://api.deepseek.example",
            api_key="test-key",
            model="deepseek-chat",
            timeout_seconds=15,
            session=sync_session,
            sleep=lambda _: None,
        ).complete_json(
            messages=[{"role": "user", "content": "ping"}],
            request_id=sync_req_id,
            on_event=None,
            purpose="unit_test",
        )

    assert stream_res == sync_res == {"ok": True}
    assert stream_session.calls[0][2]["json"]["stream_options"] == {"include_usage": True}
    assert "stream_options" not in sync_session.calls[0][2]["json"]

    db_session.expire_all()
    stream_audit = db_session.scalar(select(AICallAudit).where(AICallAudit.request_id == stream_req_id))
    sync_audit = db_session.scalar(select(AICallAudit).where(AICallAudit.request_id == sync_req_id))
    assert stream_audit is not None and sync_audit is not None
    assert (stream_audit.input_tokens, stream_audit.output_tokens) == (42, 18)
    assert (sync_audit.input_tokens, sync_audit.output_tokens) == (42, 18)

    with app.app_context():
        with db.session() as check_session:
            assert tokens_used_this_month(check_session, stream_user.id) == 60
            assert tokens_used_this_month(check_session, sync_user.id) == 60


def test_qr024_stream_usage_enforces_monthly_budget_gate_on_subsequent_call(app, db_session, monkeypatch):
    """流式调用真实累加月度用量，达预算上限后下一次调用在发起网络请求前被拦截。"""
    monkeypatch.setattr(app.config["SETTINGS"], "dsh_enabled", False)
    monkeypatch.setattr(app.config["SETTINGS"], "ai_monthly_token_budget", 100)
    user = _make_user(db_session, "qr024.budget")

    first_sse = [
        b'data: {"choices":[{"delta":{"content":"{\\"step\\":1}"}}]}',
        b'data: {"choices":[],"usage":{"prompt_tokens":65,"completion_tokens":35}}',
        b"data: [DONE]",
    ]
    session = _RecordingSession([
        _FakeDirectResponse(200, payload=None, stream_lines=first_sse),
        _FakeDirectResponse(200, payload=None, stream_lines=first_sse),
    ])
    client = DeepSeekClient(
        base_url="https://api.deepseek.example",
        api_key="test-key",
        model="deepseek-chat",
        timeout_seconds=15,
        session=session,
        sleep=lambda _: None,
    )
    first_id = f"qr024-b1-{uuid4().hex[:8]}"
    second_id = f"qr024-b2-{uuid4().hex[:8]}"

    with app.app_context():
        g.current_user = user
        first = client.complete_json(
            messages=[{"role": "user", "content": "step1"}],
            request_id=first_id,
            on_event=lambda _: None,
            purpose="unit_test",
        )
        assert first == {"step": 1}
        assert len(session.calls) == 1

        with pytest.raises(DeepSeekError) as caught:
            client.complete_json(
                messages=[{"role": "user", "content": "step2"}],
                request_id=second_id,
                on_event=lambda _: None,
                purpose="unit_test",
            )

    assert caught.value.code == "ai_budget_exceeded"
    assert caught.value.retryable is False
    # 第二次在发起供应商 HTTP 请求前被预算门拦下
    assert len(session.calls) == 1
    db_session.expire_all()
    blocked = db_session.scalar(select(AICallAudit).where(AICallAudit.request_id == second_id))
    assert blocked is not None
    assert blocked.status == "budget_blocked"
    assert blocked.error_code == "ai_budget_exceeded"


@pytest.mark.parametrize(
    "bad_usage_chunk",
    [
        None,
        b'data: {"choices":[],"usage":null}',
        b'data: {"choices":[],"usage":{}}',
        b'data: {"choices":[],"usage":{"prompt_tokens":"nan","completion_tokens":5}}',
        b'data: {"choices":[],"usage":{"prompt_tokens":true,"completion_tokens":5}}',
    ],
)
def test_qr024_missing_or_malformed_stream_usage_records_none_never_zero(
    app, db_session, monkeypatch, bad_usage_chunk
):
    """供应商未返回或返回畸形 usage 时诚实置 None，严禁静默写 0 冒充免费调用。"""
    monkeypatch.setattr(app.config["SETTINGS"], "dsh_enabled", False)
    monkeypatch.setattr(app.config["SETTINGS"], "ai_monthly_token_budget", 0)
    user = _make_user(db_session, "qr024.none")

    lines: list[bytes] = [b'data: {"choices":[{"delta":{"content":"{\\"ok\\":1}"}}]}']
    if bad_usage_chunk is not None:
        lines.append(bad_usage_chunk)
    lines.append(b"data: [DONE]")

    session = _RecordingSession([_FakeDirectResponse(200, payload=None, stream_lines=lines)])
    req_id = f"qr024-none-{uuid4().hex[:8]}"

    with app.app_context():
        g.current_user = user
        res = DeepSeekClient(
            base_url="https://api.deepseek.example",
            api_key="test-key",
            model="deepseek-chat",
            timeout_seconds=15,
            session=session,
            sleep=lambda _: None,
        ).complete_json(
            messages=[{"role": "user", "content": "hi"}],
            request_id=req_id,
            on_event=lambda _: None,
            purpose="unit_test",
        )

    assert res == {"ok": 1}
    db_session.expire_all()
    audit = db_session.scalar(select(AICallAudit).where(AICallAudit.request_id == req_id))
    assert audit is not None
    assert audit.input_tokens is None
    assert audit.output_tokens is None


def test_qr024_trailing_null_usage_does_not_clobber_collected_usage():
    """若有效 usage 出现在倒数第二帧、尾帧带 usage:null，不得把已采集值覆盖回 None。"""
    lines = [
        b'data: {"choices":[{"delta":{"content":"{\\"ok\\":1}"}}],"usage":{"prompt_tokens":11,"completion_tokens":7}}',
        b'data: {"choices":[],"usage":null}',
        b"data: [DONE]",
    ]
    session = _RecordingSession([_FakeDirectResponse(200, payload=None, stream_lines=lines)])
    client = DeepSeekClient(
        base_url="https://api.deepseek.example",
        api_key="test-key",
        model="deepseek-chat",
        timeout_seconds=15,
        session=session,
        sleep=lambda _: None,
    )
    res = client.complete_json(
        messages=[{"role": "user", "content": "hi"}],
        request_id="qr024-no-clobber",
        on_event=lambda _: None,
        purpose="unit_test",
    )
    assert res == {"ok": 1}
    assert client._last_usage == {"input": 11, "output": 7}


# --- QR-025：预调研 DOCX 原件禁止出站，脱敏/凭据拦截必在任何外呼前 -----------


def test_qr025_kimi_source_has_no_remote_files_upload_leg():
    """静态钉：kimi.py 不得保留向供应商 /files 上传/读取/删除原件的路径，默认配置为 True。"""
    kimi_src = (
        Path(__file__).resolve().parents[1] / "src" / "fde_api" / "ai" / "kimi.py"
    ).read_text(encoding="utf-8")
    assert '"/files"' not in kimi_src
    assert "/files/" not in kimi_src
    assert "file-extract" not in kimi_src
    assert Settings.model_fields["kimi_local_docx_extract"].default is True


def test_qr025_explicit_local_extract_false_still_extracts_locally_without_upload():
    """存量 .env 若残留 FDE_KIMI_LOCAL_DOCX_EXTRACT=false，仍强制走本地提取、零 /files 外呼。"""
    sse = [
        ("data: " + json.dumps({"choices": [{"delta": {"content": '{"ok": true}'}}]})).encode("utf-8"),
        b"data: [DONE]",
    ]
    session = _RecordingSession([_FakeDirectResponse(200, payload={}, stream_lines=sse)])
    client = KimiFileClient(
        base_url="https://api.moonshot.example/v1",
        api_key="test-key",
        model="kimi-k3",
        timeout_seconds=30,
        session=session,
        local_extract=False,
    )
    seen: list[str] = []
    parsed = client.analyze_docx_json(
        stream=_docx_bytes("本地解析安全正文"),
        filename="presurvey.docx",
        request_id="qr025-compat",
        build_messages=lambda content: seen.append(content) or [{"role": "user", "content": content}],
    )
    assert parsed == {"ok": True}
    assert len(seen) == 1 and "本地解析安全正文" in seen[0]
    assert len(session.calls) == 1
    assert session.calls[0][1] == "https://api.moonshot.example/v1/chat/completions"


def test_qr025_presurvey_draft_blocks_credentials_before_any_outbound_http(app, db_session, monkeypatch):
    """E4 红线端到端：DOCX 含疑似凭据时本地解析即在 build_messages 阻断，供应商零网络请求。"""
    monkeypatch.delenv(EXTRA_DICT_ENV, raising=False)
    reset_dict_cache()
    monkeypatch.setattr(app.config["SETTINGS"], "dsh_enabled", False)
    monkeypatch.setattr(app.config["SETTINGS"], "kimi_project_presurvey_api_key", "test-key")
    monkeypatch.setattr(app.config["SETTINGS"], "kimi_local_docx_extract", False)

    session = _RecordingSession([])
    monkeypatch.setattr("fde_api.ai.kimi.requests.Session", lambda: session)

    with app.app_context():
        with pytest.raises(ProjectDraftError) as caught:
            draft_from_presurvey(
                stream=_docx_bytes(f"项目背景说明。{_SYNTHETIC_CREDENTIAL}"),
                filename="presurvey.docx",
            )

    assert caught.value.code == "sensitive_content_detected"
    assert caught.value.status == 400
    assert session.calls == []


def test_qr025_presurvey_draft_redacts_enterprise_and_pii_before_outbound_chat(app, db_session, monkeypatch):
    """A2 红线端到端：DOCX 含企业名与手机号时原件不出站，唯一出站 chat 请求已脱敏。"""
    monkeypatch.delenv(EXTRA_DICT_ENV, raising=False)
    reset_dict_cache()
    monkeypatch.setattr(app.config["SETTINGS"], "dsh_enabled", False)
    monkeypatch.setattr(app.config["SETTINGS"], "kimi_project_presurvey_api_key", "test-key")
    monkeypatch.setattr(app.config["SETTINGS"], "kimi_local_docx_extract", False)

    db_session.add(
        ModuleCatalog(
            module_key=f"mod_{uuid4().hex[:6]}",
            name="预调研模块",
            description="测试模块",
            sort_order=1,
            is_active=True,
        )
    )
    db_session.commit()

    reply = {"project": {"name": "代号项目", "enterprise_code": "客户A·制造·苏州"}, "modules": []}
    sse = [
        ("data: " + json.dumps({"choices": [{"delta": {"content": json.dumps(reply, ensure_ascii=False)}}]}, ensure_ascii=False)).encode("utf-8"),
        b"data: [DONE]",
    ]
    session = _RecordingSession([_FakeDirectResponse(200, payload={}, stream_lines=sse)])
    monkeypatch.setattr("fde_api.ai.kimi.requests.Session", lambda: session)

    with app.app_context():
        draft = draft_from_presurvey(
            stream=_docx_bytes(f"甲方为 {_SYNTHETIC_ENTERPRISE}，联系人王工 13800138000，需求 MES 对接。"),
            filename="presurvey.docx",
        )

    assert draft["project"]["name"] == "代号项目"
    assert len(session.calls) == 1
    method, url, kwargs = session.calls[0]
    assert method == "post"
    assert url.endswith("/chat/completions")
    wire_json = json.dumps(kwargs["json"], ensure_ascii=False)
    assert _SYNTHETIC_ENTERPRISE not in wire_json
    assert "13800138000" not in wire_json
    assert "MES 对接" in wire_json
