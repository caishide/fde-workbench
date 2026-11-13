"""⑦ 宿主通道出站限制面（agents/host_egress_proxy.py + 接线）。

覆盖面：白名单规范化 fail-closed · 域名后缀匹配 · 真实回环代理三行为
（CONNECT 放行隧道回环 / CONNECT 域外 403+审计 / 明文 HTTP 拒绝）·
run_host_channel env 注入与审计回收 · 停机收口 · service 接线静态钉。
代理用真实 127.0.0.1 回环 socket（CI 可用）；zcode 面用假件（同
test_host_channel.py 契约）——CI 无 zcode 也能断言全行为。
"""
from __future__ import annotations

import json
import socket
import tempfile
import threading
from pathlib import Path

import pytest

from fde_api.agents.adapter import AgentRunContext
from fde_api.agents.host_channel import HostChannelError, HostChannelSettings, run_host_channel
from fde_api.agents.host_egress_proxy import (
    EgressGateError,
    HostEgressGate,
    host_matches_allowlist,
    normalize_allowlist,
    summarize_audit,
)


# ---------------------------------------------------------------------------
# 假件（与 test_host_channel.py 同构，自持不跨文件依赖）
# ---------------------------------------------------------------------------


class FakeProc:
    def __init__(self, *, stdout="", stderr="", returncode=0):
        self.pid = 4242
        self._stdout = stdout
        self._stderr = stderr
        self._returncode = returncode
        self.killed = False

    @property
    def returncode(self) -> int:
        return self._returncode

    def kill(self) -> None:
        self.killed = True

    def communicate(self, timeout=None):  # noqa: ANN001 - 测试假件
        return self._stdout, self._stderr


class RecordingSpawner:
    def __init__(self, proc: FakeProc):
        self.proc = proc
        self.calls: list[dict] = []

    def __call__(self, argv, *, env, cwd, stdout, stderr, stdin):  # noqa: ANN001
        self.calls.append({"argv": list(argv), "env": dict(env), "cwd": cwd})
        return self.proc


class FakeScanner:
    receipt_state = "ok"

    def scan(self):
        return []


def _ctx() -> AgentRunContext:
    return AgentRunContext(
        run_id="run-egress-1",
        project_code="somwyn",
        capability="agent.code.write",
        workspace_host="D:/ws/agent-workspaces/run-egress-1",
        allowed_tools=frozenset({"read_file"}),
    )


# N2 前置校验注入（goal-sprint r2）：与 test_host_channel 同款——临时 CLI
# 配置让 spawn 前置校验确定性放行；provider 覆盖开关不进单测 env。
_CLI_CONFIG_PATH = Path(tempfile.mkdtemp(prefix="zcode-cli-config-")) / "config.json"
_CLI_CONFIG_PATH.write_text(
    json.dumps({"defaultModelSelection": {"providerId": "prov", "modelId": "model-x"}}),
    encoding="utf-8",
)
_SETTINGS = HostChannelSettings(
    zcode_bin="C:/zcode/ZCode.exe",
    cjs_path="C:/zcode/resources/glm/zcode.cjs",
    cli_config_path=str(_CLI_CONFIG_PATH),
)
_SUMMARY = json.dumps({
    "sessionId": "sess_1",
    "usage": {"outputTokens": 8, "inputTokens": 4},
})


@pytest.fixture(autouse=True)
def _clean_provider_switch_env(monkeypatch):
    monkeypatch.delenv("ZCODE_BUILTIN_PROVIDER_CONFIG_FILE", raising=False)
    monkeypatch.delenv("ZCODE_PERSONAL_PROVIDER_CONFIG_FILE", raising=False)


# ---------------------------------------------------------------------------
# 白名单规范化与匹配
# ---------------------------------------------------------------------------


def test_normalize_rejects_empty_as_fail_closed() -> None:
    with pytest.raises(EgressGateError):
        normalize_allowlist(["", "  "])


def test_normalize_rejects_illegal_entry_shapes() -> None:
    for bad in ("api.z.ai/path", "host:443", "*", "a*b"):
        with pytest.raises(EgressGateError):
            normalize_allowlist([bad])


def test_normalize_lowercases_and_strips_trailing_dot() -> None:
    assert normalize_allowlist([" API.Z.AI. ", "BigModel.cn"]) == frozenset({"api.z.ai", "bigmodel.cn"})


def test_host_matches_exact_and_subdomain_not_partial_suffix() -> None:
    allow = frozenset({"api.z.ai"})
    assert host_matches_allowlist("api.z.ai", allow)
    assert host_matches_allowlist("API.Z.AI.", allow)
    assert host_matches_allowlist("gw.api.z.ai", allow)
    assert not host_matches_allowlist("evil-api.z.ai", allow)  # 非子域边界
    assert not host_matches_allowlist("z.ai", allow)  # 后缀条目不放行裸根域
    assert not host_matches_allowlist("1.2.3.4", allow)  # 裸 IP 不命中域名条目


# ---------------------------------------------------------------------------
# 真实回环代理三行为
# ---------------------------------------------------------------------------


def _echo_server() -> tuple[socket.socket, int]:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(4)
    port = int(server.getsockname()[1])

    def serve() -> None:
        try:
            while True:
                conn, _ = server.accept()

                def handle(c: socket.socket) -> None:
                    try:
                        data = c.recv(65536)
                        c.sendall(data)  # 原样回显
                    except OSError:
                        pass
                    finally:
                        c.close()

                threading.Thread(target=handle, args=(conn,), daemon=True).start()
        except OSError:
            pass

    threading.Thread(target=serve, daemon=True).start()
    return server, port


def _connect_via_proxy(proxy_port: int, authority: str) -> tuple[bytes, socket.socket | None]:
    client = socket.create_connection(("127.0.0.1", proxy_port), timeout=5)
    client.settimeout(5)
    client.sendall(f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode())
    response = b""
    while b"\r\n\r\n" not in response:
        chunk = client.recv(4096)
        if not chunk:
            break
        response += chunk
    status_line = response.split(b"\r\n", 1)[0]
    return status_line, client


def test_loopback_connect_exempt_from_allowlist_and_relays() -> None:
    """goal-sprint r3 真机验收发现钉（2026-11-13）：zcode 本地 broker 回环
    IPC（127.0.0.1:18787）不在白名单内、其客户端又无视 NO_PROXY——闸侧
    回环豁免必须放行回环 CONNECT（审计 ``tunnel_loopback``，不参与白名单
    判定），否则宿主通道在闸开启时死在 API 调用前。"""
    echo, echo_port = _echo_server()
    gate = HostEgressGate(["api.z.ai"])  # 部署态同款白名单：不含 127.0.0.1
    proxy_port = gate.start()
    try:
        status, tunnel = _connect_via_proxy(proxy_port, f"127.0.0.1:{echo_port}")
        assert b"200" in status
        assert tunnel is not None
        tunnel.sendall(b"ping-loopback")
        assert tunnel.recv(65536) == b"ping-loopback"
        tunnel.close()
        entries = gate.drain_audit()
        assert [entry.kind for entry in entries] == ["tunnel_loopback"]
        assert entries[0].host == "127.0.0.1"
        assert entries[0].port == echo_port
    finally:
        gate.stop()
        echo.close()


def test_loopback_alias_localhost_also_exempt() -> None:
    echo, echo_port = _echo_server()
    gate = HostEgressGate(["api.z.ai"])
    proxy_port = gate.start()
    try:
        status, tunnel = _connect_via_proxy(proxy_port, f"localhost:{echo_port}")
        assert b"200" in status
        assert tunnel is not None
        tunnel.close()
        entries = gate.drain_audit()
        assert [entry.kind for entry in entries] == ["tunnel_loopback"]
        assert entries[0].host == "localhost"
    finally:
        gate.stop()
        echo.close()


def test_tunnel_blocked_domain_records_audit() -> None:
    gate = HostEgressGate(["api.z.ai"])
    proxy_port = gate.start()
    try:
        status, tunnel = _connect_via_proxy(proxy_port, "telemetry.example.com:443")
        assert b"403" in status
        assert tunnel is not None
        tunnel.close()
        entries = gate.drain_audit()
        assert [entry.kind for entry in entries] == ["tunnel_blocked"]
        assert entries[0].host == "telemetry.example.com"
    finally:
        gate.stop()


def test_plain_http_absolute_form_is_denied() -> None:
    gate = HostEgressGate(["api.z.ai"])
    proxy_port = gate.start()
    try:
        client = socket.create_connection(("127.0.0.1", proxy_port), timeout=5)
        client.settimeout(5)
        client.sendall(b"GET http://plain.example.com/x HTTP/1.1\r\nHost: plain.example.com\r\n\r\n")
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = client.recv(4096)
            if not chunk:
                break
            response += chunk
        assert response.split(b"\r\n", 1)[0].startswith(b"HTTP/1.1 403")
        client.close()
        entries = gate.drain_audit()
        assert [entry.kind for entry in entries] == ["plain_http_blocked"]
    finally:
        gate.stop()


def test_stop_closes_listener_and_blocks_further_use() -> None:
    gate = HostEgressGate(["api.z.ai"])
    proxy_port = gate.start()
    gate.stop()
    with pytest.raises((OSError, EgressGateError)):
        socket.create_connection(("127.0.0.1", proxy_port), timeout=1).close()
    assert gate.drain_audit() == ()


def test_summarize_audit_counts_and_dedupes_domains() -> None:
    entries = [
        {"kind": "tunnel_allowed", "host": "api.z.ai", "port": 443, "ts": 1.0},
        {"kind": "tunnel_blocked", "host": "telemetry.example.com", "port": 443, "ts": 2.0},
        {"kind": "tunnel_blocked", "host": "telemetry.example.com", "port": 80, "ts": 3.0},
    ]
    summary = summarize_audit(entries)
    assert summary["total"] == 3
    assert summary["kinds"] == {"tunnel_allowed": 1, "tunnel_blocked": 2}
    assert summary["domains"] == ["api.z.ai", "telemetry.example.com"]
    assert summary["domains_truncated"] is False


# ---------------------------------------------------------------------------
# run_host_channel 接线
# ---------------------------------------------------------------------------


def test_run_injects_proxy_env_and_collects_audit() -> None:
    gate = HostEgressGate(["api.z.ai", "bigmodel.cn"])
    spawner = RecordingSpawner(FakeProc(stdout=_SUMMARY))
    result = run_host_channel(_ctx(), _SETTINGS, output_scanner=FakeScanner(), spawner=spawner, egress_gate=gate)
    assert result.status == "completed"
    env = spawner.calls[0]["env"]
    proxy = env["HTTPS_PROXY"]
    assert env["HTTP_PROXY"] == proxy
    assert env["https_proxy"] == proxy
    assert env["NO_PROXY"] == "localhost,127.0.0.1,::1"
    # A′ 实测补件（2026-11-11 四探针）：zcode 内嵌 Node 24 默认无视代理 env，
    # 须 NODE_USE_ENV_PROXY=1 才走——缺失即整闸空转（探针二铁证）。
    assert env["NODE_USE_ENV_PROXY"] == "1"
    # run 结束代理已停：同端口不再接受连接（生命周期 = 单 run）
    port = int(proxy.rsplit(":", 1)[1])
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()


def test_run_without_gate_leaves_proxy_env_absent() -> None:
    spawner = RecordingSpawner(FakeProc(stdout=_SUMMARY))
    result = run_host_channel(_ctx(), _SETTINGS, output_scanner=FakeScanner(), spawner=spawner)
    assert result.status == "completed"
    assert result.egress_audit == ()
    env = spawner.calls[0]["env"]
    assert "HTTPS_PROXY" not in env
    assert "NO_PROXY" not in env


def test_run_completes_gate_stopped_and_audit_field_present() -> None:
    gate = HostEgressGate(["api.z.ai"])
    spawner = RecordingSpawner(FakeProc(stdout=_SUMMARY, returncode=0))
    result = run_host_channel(_ctx(), _SETTINGS, output_scanner=FakeScanner(), spawner=spawner, egress_gate=gate)
    # FakeProc 不产生真实连接 ⇒ 审计为空表但字段在；代理已停（端口从 env 回读）。
    assert result.egress_audit == ()
    proxy = spawner.calls[0]["env"]["HTTPS_PROXY"]
    port = int(proxy.rsplit(":", 1)[1])
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1).close()


def test_run_gate_start_failure_is_channel_error_not_spawn() -> None:
    class BrokenGate:
        def start(self) -> int:
            raise OSError("bind failed")

    spawner = RecordingSpawner(FakeProc(stdout=_SUMMARY))
    with pytest.raises(HostChannelError):
        run_host_channel(_ctx(), _SETTINGS, output_scanner=FakeScanner(), spawner=spawner, egress_gate=BrokenGate())
    assert spawner.calls == []  # 未 spawn（不发起不计费）


# ---------------------------------------------------------------------------
# service 接线静态钉（防止配置面被静默拆除）
# ---------------------------------------------------------------------------


def test_service_wiring_wires_gate_and_audit_event() -> None:
    import inspect

    from fde_api.agents import service

    source = inspect.getsource(service)
    assert "agent_host_egress_gate_enabled" in source
    assert "HostEgressGate(" in source
    assert "egress_gate=egress_gate" in source
    assert "agent_egress_audit" in source
    assert "summarize_audit" in source
