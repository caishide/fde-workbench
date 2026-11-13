"""宿主代理进程本体（goal-sprint r3：agents/host_agent.py）。

覆盖：env 配置闭集 / preflight fail-fast（N2 两事实复用同一对校验器）/
单次生命周期（status→claim→context→spawn→receipt）/ spawn 失败如实回执
failed / 回执投递失败抛错（run 挂 host_running 待失联标记）/ 产物指纹
宿主侧现算逐位一致 / 传输面请求形状。全部免网络免 zcode（假传输 + 假
runner），与 host_channel 测试同款纯单元纪律。
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

import pytest

from fde_api.agents.adapter import AgentRunContext, AgentRunResult, ArtifactFile
from fde_api.agents.host_agent import (
    HostAgentConfig,
    HostAgentError,
    HttpHostTransport,
    build_receipt_payload,
    materialize_workspace,
    preflight,
    run_once,
)
from fde_api.agents.host_channel import HostChannelError

_BASE_ENV = {
    "FDE_AGENT_HOST_API_BASE": "http://127.0.0.1:8010",
    "FDE_AGENT_HOST_POLL_TOKEN": "poll-token-0123456789abcdef",
    "FDE_AGENT_WORKSPACE_ROOT": "D:/host-ws",
    "FDE_AGENT_HOST_ZCODE_BIN": "C:/zcode/ZCode.exe",
    "FDE_AGENT_HOST_ZCODE_CJS": "C:/zcode/resources/glm/zcode.cjs",
}

_SUMMARY = {
    "sessionId": "sess_hostagent",
    "traceId": "tr1",
    "turnId": "tn1",
    "usage": {"inputTokens": 10, "outputTokens": 20},
    "projection": {"status": "done", "totalTokenCount": 30},
}

_CLAIM = {
    "run_id": "run-abc-123",
    "project_id": "proj-1",
    "capability": "agent.module.acceptance",
    "allowed_tools": ["read_file", "write_file"],
    "max_duration_ms": 240_000,
    "max_cost_units": 5_000,
    "already_running": False,
}


@pytest.fixture(autouse=True)
def _clean_provider_switch_env(monkeypatch):
    """本机（Windows 宿主）进程 env 可能真实带 provider 开关——单测先清场。

    r2 同款教训：preflight 校验对象是真实进程 env；部署态残留会让「单边
    成对失败」用例拿到完整对而不红（假绿家族）。
    """
    monkeypatch.delenv("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE", raising=False)
    monkeypatch.delenv("ZCODE_PERSONAL_PROVIDER_CONFIG_FILE", raising=False)

_CONTEXT = {
    "run_id": "run-abc-123",
    "files": {"context.md": "CTX", "task.md": "TASK-BODY", "AGENTS.md": "AGENTS"},
}


class FakeTransport:
    """传输假件：脚本化应答 + 调用记录。"""

    def __init__(self, *, claim=(200, dict(_CLAIM)), context=(200, dict(_CONTEXT)), receipt_code=200):
        self.status_calls = 0
        self.claim_calls: list[str | None] = []
        self.context_calls: list[str] = []
        self.receipt_calls: list[tuple[str, dict]] = []
        self._claim = claim
        self._context = context
        self._receipt_code = receipt_code

    def get_status(self):
        self.status_calls += 1
        return {"pending": 1, "lost_marked": 0}

    def claim(self, run_id=None):
        self.claim_calls.append(run_id)
        return self._claim

    def fetch_context(self, run_id):
        self.context_calls.append(run_id)
        return self._context

    def receipt(self, run_id, payload):
        self.receipt_calls.append((run_id, dict(payload)))
        return (self._receipt_code, {"run_id": run_id, "status": payload.get("status"), "duplicate": False})


def _write_cli_config(tmp_path) -> Path:
    """在 tmp 内造一份合法的 zcode CLI 配置（含 defaultModelSelection）。"""
    path = tmp_path / "zcode-cli-config.json"
    path.write_text(
        json.dumps({"defaultModelSelection": {"providerId": "prov", "modelId": "model-x"}}),
        encoding="utf-8",
    )
    return path


def _config(tmp_path, **overrides) -> HostAgentConfig:
    payload = dict(_BASE_ENV)
    payload["FDE_AGENT_WORKSPACE_ROOT"] = str(tmp_path / "host-ws")
    # N2 前置校验隔离（与 test_host_channel.py 同款纪律）：preflight 真读
    # 默认模型配置文件，缺省路径落在 HOME 下——CI runner 无此文件 ⇒ 六例
    # 假红（r3 首个 CI 红即此因），开发机真机态又让「缺键」负例不可达。
    # 单测一律注入 tmp 内造的合法配置；负例用 overrides 显式覆盖路径。
    payload["FDE_AGENT_HOST_ZCODE_CLI_CONFIG"] = str(_write_cli_config(tmp_path))
    payload.update(overrides)
    return HostAgentConfig.from_env(payload)


# ---------------------------------------------------------------------------
# 配置闭集 / preflight
# ---------------------------------------------------------------------------


def test_from_env_requires_minimum_config(tmp_path) -> None:
    with pytest.raises(HostAgentError) as ei:
        HostAgentConfig.from_env({})
    assert ei.value.code == "config_missing"
    config = _config(tmp_path)
    assert config.api_base == "http://127.0.0.1:8010"
    assert config.zcode_bin == "C:/zcode/ZCode.exe"


def test_from_env_egress_gate_requires_allowlist(tmp_path) -> None:
    """⑦ fail-closed：闸开白名单空 = 配置半态，拒绝起跑。"""
    with pytest.raises(HostAgentError, match="ALLOWLIST"):
        _config(tmp_path, FDE_AGENT_HOST_EGRESS_GATE_ENABLED="1", FDE_AGENT_HOST_EGRESS_ALLOWLIST="")
    config = _config(tmp_path, FDE_AGENT_HOST_EGRESS_GATE_ENABLED="1", FDE_AGENT_HOST_EGRESS_ALLOWLIST="a.com, b.com")
    assert config.egress_allowlist == ("a.com", "b.com")


def test_preflight_reuses_same_validators(tmp_path, monkeypatch) -> None:
    """preflight 复用 host_preflight 同一对校验器：部署半态在 claim 之前失败。"""
    monkeypatch.setenv("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE", "D:/prov/builtin.json")
    with pytest.raises(HostChannelError, match="成对"):
        preflight(_config(tmp_path))
    monkeypatch.delenv("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE")
    monkeypatch.setenv("ZCODE_PERSONAL_PROVIDER_CONFIG_FILE", "D:/prov/personal.json")
    with pytest.raises(HostChannelError, match="成对"):
        preflight(_config(tmp_path))
    monkeypatch.delenv("ZCODE_PERSONAL_PROVIDER_CONFIG_FILE")
    broken = _config(tmp_path, FDE_AGENT_HOST_ZCODE_CLI_CONFIG=str(tmp_path / "missing.json"))
    with pytest.raises(HostChannelError, match="defaultModelSelection"):
        preflight(broken)
    good = tmp_path / "config.json"
    good.write_text(json.dumps({"defaultModelSelection": {"providerId": "prov", "modelId": "m"}}), encoding="utf-8")
    preflight(_config(tmp_path, FDE_AGENT_HOST_ZCODE_CLI_CONFIG=str(good)))


def test_preflight_falls_back_to_default_cli_config_path(tmp_path, monkeypatch) -> None:
    """未注入 CLI 配置路径 ⇒ 走缺省路径（HOME 下）——打桩钉住该语义。

    不读真实 HOME 内容（真机态与 CI runner 态都必须是绿的）：缺省路径被
    替换成 tmp 内不存在的文件，缺键失败信息必须点名该路径。
    """
    missing = tmp_path / "no-such-zcode-cli-config.json"
    monkeypatch.setattr("fde_api.agents.host_agent.default_cli_config_path", lambda: missing)
    payload = dict(_BASE_ENV)
    payload["FDE_AGENT_WORKSPACE_ROOT"] = str(tmp_path / "host-ws")
    config = HostAgentConfig.from_env(payload)
    assert config.cli_config_path == ""
    with pytest.raises(HostChannelError, match="defaultModelSelection") as ei:
        preflight(config)
    assert str(missing) in str(ei.value)


# ---------------------------------------------------------------------------
# 工作区落盘
# ---------------------------------------------------------------------------


def test_materialize_writes_files_verbatim(tmp_path) -> None:
    config = _config(tmp_path)
    workspace = materialize_workspace(config, run_id="run-abc-123", context=_CONTEXT)
    assert workspace == Path(config.workspace_root) / "run-abc-123"
    assert (workspace / "task.md").read_text(encoding="utf-8") == "TASK-BODY"
    assert (workspace / "context.md").read_text(encoding="utf-8") == "CTX"
    assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "AGENTS"
    assert (workspace / "output").is_dir()


def test_materialize_refuses_bad_run_id_and_blank_task(tmp_path) -> None:
    config = _config(tmp_path)
    with pytest.raises(HostAgentError, match="run_id"):
        materialize_workspace(config, run_id="../evil", context=_CONTEXT)
    blank = {"files": {"context.md": "CTX", "task.md": "   ", "AGENTS.md": "A"}}
    with pytest.raises(HostAgentError, match="task.md"):
        materialize_workspace(config, run_id="run-1", context=blank)


# ---------------------------------------------------------------------------
# 单次生命周期
# ---------------------------------------------------------------------------


class _FakeRunner:
    """假 spawn 真身：记录 ctx/settings，可脚本化返回结果或抛错。"""

    def __init__(self, result: AgentRunResult | None = None, error: Exception | None = None):
        self.calls: list[tuple[AgentRunContext, object]] = []
        self._result = result
        self._error = error

    def __call__(self, ctx, settings, **kwargs):  # noqa: ANN001, ANN003
        self.calls.append((ctx, settings))
        if self._error is not None:
            raise self._error
        # 回执保真：产物文件由「执行」写盘（模拟 zcode 产出 + manifest）
        output = Path(ctx.workspace_host) / "output"
        (output / "report.md").write_text("# 报告正文\n", encoding="utf-8")
        (output / "manifest.json").write_text(
            json.dumps([{"path": "report.md", "kind": "doc", "source_refs": ["t-1"]}]), encoding="utf-8"
        )
        return self._result


def _completed_result() -> AgentRunResult:
    return AgentRunResult(
        status="completed",
        exit_code=0,
        token_cost=30,
        duration_ms=1500,
        artifacts=(ArtifactFile(path="report.md", kind="doc", source_refs=("t-1",)),),
        tool_calls=(),
        degraded=False,
        degraded_reason=None,
        summary_payload=dict(_SUMMARY),
    )


def test_run_once_idle_when_claim_404(tmp_path) -> None:
    transport = FakeTransport(claim=(404, {"error": {"code": "agent_run_not_found"}}))
    runner = _FakeRunner(_completed_result())
    outcome = run_once(_config(tmp_path), transport=transport, runner=runner)
    assert outcome["outcome"] == "idle"
    assert transport.context_calls == []  # 未领取不取面料
    assert runner.calls == []  # 未领取不 spawn


def test_run_once_full_loop_receipted_with_verbatim_digest(tmp_path) -> None:
    transport = FakeTransport()
    runner = _FakeRunner(_completed_result())
    outcome = run_once(_config(tmp_path), transport=transport, runner=runner)
    assert outcome["outcome"] == "receipted" and outcome["status"] == "completed"
    assert transport.status_calls == 1  # 「宿主在，标记就在」：每次起跑先 status
    ctx, _settings = runner.calls[0]
    assert ctx.run_id == "run-abc-123"
    assert ctx.allowed_tools == frozenset({"read_file", "write_file"})
    assert ctx.timeout_ms == 240_000 and ctx.max_cost_units == 5_000
    assert ctx.credentials == {}  # 零凭据注入（红线）
    run_id, payload = transport.receipt_calls[0]
    assert run_id == "run-abc-123"
    assert payload["status"] == "completed" and payload["exit_code"] == 0
    assert payload["summary"] == _SUMMARY  # --json 汇总原样回传（解析归服务端）
    assert payload["token_cost"] == 30
    # 产物指纹宿主侧现算，与磁盘逐位一致
    assert len(payload["artifacts"]) == 1
    artifact = payload["artifacts"][0]
    expected = hashlib.sha256((Path(ctx.workspace_host) / "output" / "report.md").read_bytes()).hexdigest()
    assert artifact["sha256"] == expected
    assert artifact["path"] == "report.md" and artifact["kind"] == "doc" and artifact["source_refs"] == ["t-1"]


def test_run_once_spawn_failure_lands_failed_receipt(tmp_path) -> None:
    transport = FakeTransport()
    runner = _FakeRunner(error=HostChannelError("preflight 二道闸拒绝"))
    outcome = run_once(_config(tmp_path), transport=transport, runner=runner)
    assert outcome["outcome"] == "failed_receipted"
    run_id, payload = transport.receipt_calls[0]
    assert run_id == "run-abc-123"
    assert payload["status"] == "failed"
    assert "exit_code" not in payload  # 无退出码不编造（QR-095 fail-closed 同口径）
    assert payload["summary"] == {}
    assert payload["degraded_reason"].startswith("host_agent_spawn_failed:")


def test_run_once_receipt_rejected_raises(tmp_path) -> None:
    transport = FakeTransport(receipt_code=500)
    runner = _FakeRunner(_completed_result())
    with pytest.raises(HostAgentError) as ei:
        run_once(_config(tmp_path), transport=transport, runner=runner)
    assert ei.value.code == "receipt_rejected"


def test_run_once_claim_rejected_raises(tmp_path) -> None:
    transport = FakeTransport(claim=(403, {"error": {"code": "host_claim_conflict"}}))
    with pytest.raises(HostAgentError) as ei:
        run_once(_config(tmp_path), transport=transport, runner=_FakeRunner())
    assert ei.value.code == "claim_rejected"


def test_run_once_missing_claim_run_id_raises(tmp_path) -> None:
    transport = FakeTransport(claim=(200, {"already_running": False}))
    with pytest.raises(HostAgentError, match="run_id"):
        run_once(_config(tmp_path), transport=transport, runner=_FakeRunner())


def test_run_once_preflight_fails_before_claim(tmp_path, monkeypatch) -> None:
    """fail-fast 语义：preflight 未过 ⇒ 连 status 都不打（不领取不触失联标记）。"""
    transport = FakeTransport()
    monkeypatch.setenv("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE", "D:/prov/builtin.json")
    with pytest.raises(HostChannelError, match="成对"):
        run_once(_config(tmp_path), transport=transport, runner=_FakeRunner())
    assert transport.status_calls == 0 and transport.claim_calls == []


# ---------------------------------------------------------------------------
# 回执载荷 / HTTP 传输形状
# ---------------------------------------------------------------------------


def test_build_receipt_payload_skips_missing_digest(tmp_path) -> None:
    """扫描清单里有但磁盘缺文件：不编指纹（服务端按 sha256_missing 记 failure）。"""
    workspace = tmp_path / "ws"
    (workspace / "output").mkdir(parents=True)
    result = AgentRunResult(
        status="completed",
        exit_code=None,  # 无退出码（如 spawn 前失败路径）→ 载荷如实缺席该键
        token_cost=1,
        duration_ms=1,
        artifacts=(
            ArtifactFile(path="ghost.md", kind="doc", source_refs=("t",)),
            ArtifactFile(path="real.md", kind="doc", source_refs=("t",)),
        ),
        tool_calls=(),
        degraded=False,
        degraded_reason=None,
        summary_payload=None,
    )
    (workspace / "output" / "real.md").write_text("x", encoding="utf-8")
    payload = build_receipt_payload(result, workspace)
    assert [a["path"] for a in payload["artifacts"]] == ["real.md"]
    assert payload["summary"] == {}  # 汇总缺席 → 空对象（服务端必填形状）
    assert "exit_code" not in payload  # 无 int 退出码不编造（QR-095 同口径）


def test_http_transport_request_shape(monkeypatch, tmp_path) -> None:
    """urllib 请求形状：URL/方法/令牌头；非 2xx 返回 (code, body) 不抛。"""
    captured: dict = {}

    class _FakeResponse:
        status = 200

        def read(self):
            return json.dumps({"pending": 0}).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return False

    def _fake_urlopen(request, timeout=None):  # noqa: ANN001
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    transport = HttpHostTransport(api_base="http://127.0.0.1:8010/", poll_token="tok-123")
    body = transport.get_status()
    assert body == {"pending": 0}
    assert captured["url"] == "http://127.0.0.1:8010/api/v1/agents/host/status"
    assert captured["method"] == "GET"
    headers_lower = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers_lower.get("x-host-poll-token") == "tok-123"

    class _ErrResponse:
        status = 200

        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *args):  # noqa: ANN002
            return False

    import urllib.error as _ue

    def _fake_urlopen_404(request, timeout=None):  # noqa: ANN001
        raise _ue.HTTPError(url=request.full_url, code=404, msg="nf", hdrs=None, fp=None)

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen_404)
    code, payload = transport.claim()
    assert code == 404 and payload == {}
