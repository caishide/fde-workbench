"""宿主通道出站限制面——任务书 §9 前置⑦ 方案 A（本地正向代理白名单闸）。

设计提请：``docs/architecture/宿主通道网络限制面设计提请-v1.md``（#270 落盘，
2026-11-11 蔡工拍板采纳推荐 A 后实施）。容器沙箱有 ``network_mode: none``
硬边界；宿主通道（T-Z1 裁定 A）进程走宿主自身网络，此前的代码级出口约束
为零——本模块补上同尺的宿主侧限制面：

1. **默认拒绝、白名单放行**：spawn zcode 前起一个仅监听 ``127.0.0.1``
   临时端口的正向代理（纯 stdlib，无第三方依赖），以
   ``HTTP_PROXY/HTTPS_PROXY/NO_PROXY`` 注入进程 env；白名单外的 CONNECT
   隧道请求一律 ``403`` 拒绝，明文 HTTP（absolute-form）一律拒绝——模型
   API 均为 HTTPS，明文出站无业务必要。
2. **出口可审计、只记域名**：每次放行/拒绝落 ``EgressAuditEntry``（时间
   戳＋类别＋域名＋端口），run 结束由 service 层汇总落 ``operation_events``
   （``agent_egress_audit``）；不记 URL/路径/内容（红线：审计面只记域名）。
3. **生命周期 = 单 run**：代理随 ``run_host_channel`` 启停——先于 spawn
   启动、``finally`` 停止；隧道中继线程为 daemon，宿主 zcode 进程退出
   即断流回收（socket EOF 传播），无残留。
4. **fail-closed 语义**：闸开启但白名单为空 ⇒ 构造即 ``EgressGateError``
   ⇒ service 层转 L2 模板填空、本次不计费（既不无限制放行，也不静默
   全拒绝制造假 run）；白名单条目含 ``/``/``:``/``*`` 等非法形状同样
   拒绝——白名单的 guess 风险留给配置审查，不在运行期放宽。

域名匹配口径：**域名后缀精确匹配**（等于条目，或以 ``.``+条目 结尾的
子域）；大小写不敏感；裸 IP 不命中域名条目（如需放行必须显式列出 IP
字面量）。匹配发生在 DNS 解析**之前**（先审域名再 connect，防绕行）。

与 zcode 的兼容前提（设计提请 §3 方案 A 前置实测）：zcode 网络栈尊重
``HTTPS_PROXY`` 环境变量——实测记录见设计提请实施注记；若实测不过则按
提请退方案 B（OS 防火墙），本模块保持闸门语义不变。

测试注入：代理监听真实 127.0.0.1 回环（CI 可用）；``run_host_channel``
的 ``egress_gate`` 形参与 ``spawner`` 同构可注入——CI 无 zcode 也能断言
env 注入/审计回收/停机全行为。
"""

from __future__ import annotations

import socket
import socketserver
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

# 请求头读取上限：CONNECT 头部几 KB 量级，16KB 封顶防慢速膨胀。
_MAX_HEAD_BYTES = 16 * 1024
# 头部读取/上游连接的 socket 超时（秒）。隧道建立后不设 idle 超时——
# 流式响应与工具执行期的静默间隔可能远超分钟级，靠 run 生命周期兜底。
_HEAD_TIMEOUT_SECONDS = 30.0


class EgressGateError(RuntimeError):
    """出站闸配置错误（A 类：run 拒绝发起，不计费——同 HostChannelError 语义）。"""


def normalize_allowlist(raw: Sequence[str]) -> frozenset[str]:
    """逗号分隔白名单 → 规范化域名后缀集合（小写、去空白、形状校验）。"""
    entries: set[str] = set()
    for item in raw:
        entry = item.strip().lower().rstrip(".")
        if not entry:
            continue
        if any(bad in entry for bad in ("/", ":", "*", "@", " ")):
            raise EgressGateError(f"egress 白名单条目形状非法：{item!r}（仅接受裸域名后缀）")
        entries.add(entry)
    if not entries:
        raise EgressGateError("egress 白名单为空：闸开启即全拒绝（fail-closed，请先配置 FDE_AGENT_HOST_EGRESS_ALLOWLIST）")
    return frozenset(entries)


def host_matches_allowlist(host: str, allowlist: frozenset[str]) -> bool:
    """域名后缀匹配：host == entry 或 host 以 ``.entry`` 结尾；大小写不敏感。"""
    candidate = host.strip().lower().rstrip(".")
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    for entry in allowlist:
        if candidate == entry or candidate.endswith("." + entry):
            return True
    return False


@dataclass(frozen=True)
class EgressAuditEntry:
    """单次出站判定（只记域名与端口，绝不记路径/内容）。"""

    ts: float
    kind: str  # tunnel_allowed / tunnel_blocked / tunnel_upstream_error / plain_http_blocked
    host: str
    port: int

    def as_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "kind": self.kind, "host": self.host, "port": self.port}


class _EgressProxyHandler(socketserver.BaseRequestHandler):
    """单连接处理器：CONNECT 白名单隧道 / 其余一律拒绝。"""

    # server 实例上由 HostEgressGate 挂载：
    #   allowlist: frozenset[str] / audit: _AuditSink

    def handle(self) -> None:  # noqa: C901 - 单连接小状态机，拆函数反而散
        head = self._read_head()
        if head is None:
            return
        request_line = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = request_line.split()
        if len(parts) < 3:
            self._audit_and_respond("plain_http_blocked", "(unparseable)", 0, blocked=True)
            return
        method, target = parts[0].upper(), parts[1]
        if method != "CONNECT":
            # absolute-form 明文 HTTP：一律拒绝（模型 API 均为 HTTPS）。
            host = self._plain_target_host(target)
            self._audit_and_respond("plain_http_blocked", host, 0, blocked=True)
            return
        authority = target.rsplit(":", 1)
        if len(authority) != 2 or not authority[1].isdigit():
            self._audit_and_respond("tunnel_blocked", target, 0, blocked=True)
            return
        host, port = authority[0], int(authority[1])
        if not host_matches_allowlist(host, self.server.egress_allowlist):  # type: ignore[attr-defined]
            self._audit_and_respond("tunnel_blocked", host, port, blocked=True)
            return
        self._audit("tunnel_allowed", host, port)
        try:
            upstream = socket.create_connection((host, port), timeout=_HEAD_TIMEOUT_SECONDS)
        except OSError:
            self._audit("tunnel_upstream_error", host, port)
            self._respond(b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\n\r\n")
            return
        try:
            self._respond(b"HTTP/1.1 200 Connection established\r\n\r\n")
            self._relay(upstream)
        finally:
            try:
                upstream.close()
            except OSError:
                pass

    # ---- 头部读取与响应 -------------------------------------------------

    def _read_head(self) -> bytes | None:
        request = self.request
        request.settimeout(_HEAD_TIMEOUT_SECONDS)
        buffer = bytearray()
        while b"\r\n\r\n" not in buffer:
            try:
                chunk = request.recv(4096)
            except OSError:
                return None
            if not chunk:
                return None
            buffer.extend(chunk)
            if len(buffer) > _MAX_HEAD_BYTES:
                return None
        return bytes(buffer)

    def _respond(self, payload: bytes) -> None:
        try:
            self.request.sendall(payload)
        except OSError:
            pass

    def _audit_and_respond(self, kind: str, host: str, port: int, *, blocked: bool) -> None:
        self._audit(kind, host, port)
        reason = "egress allowlist" if blocked else "error"
        self._respond(
            f"HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\nX-Egress-Reason: {reason}\r\n\r\n".encode("latin-1")
        )

    # ---- 审计与中继 -----------------------------------------------------

    def _audit(self, kind: str, host: str, port: int) -> None:
        self.server.audit.record(EgressAuditEntry(ts=time.time(), kind=kind, host=host, port=port))  # type: ignore[attr-defined]

    def _plain_target_host(self, target: str) -> str:
        # absolute-form：http://host/... → 取 authority；其余 best effort。
        candidate = target.split("://", 1)[-1].split("/", 1)[0]
        return candidate.rsplit(":", 1)[0] if candidate else "(unparseable)"

    def _relay(self, upstream: socket.socket) -> None:
        def pump(src: socket.socket, dst: socket.socket) -> None:
            try:
                while True:
                    data = src.recv(65536)
                    if not data:
                        break
                    dst.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    dst.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        client = self.request
        threads = [
            threading.Thread(target=pump, args=(client, upstream), daemon=True),
            threading.Thread(target=pump, args=(upstream, client), daemon=True),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()


class _AuditSink:
    """线程安全审计汇（内存态，run 结束 drain——持久化在 operation_events）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[EgressAuditEntry] = []

    def record(self, entry: EgressAuditEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def drain(self) -> tuple[EgressAuditEntry, ...]:
        with self._lock:
            entries = tuple(self._entries)
            self._entries.clear()
        return entries


class _EgressProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = False  # 临时端口一次性，无重用必要
    daemon_threads = True
    request_queue_size = 32

    def __init__(self, allowlist: frozenset[str], audit: _AuditSink) -> None:
        self.egress_allowlist = allowlist
        self.audit = audit
        super().__init__(("127.0.0.1", 0), _EgressProxyHandler)


class HostEgressGate:
    """单 run 出站闸：bind → env 注入 → run 结束 stop → drain 审计。

    构造即校验白名单（空/非法形状 ⇒ ``EgressGateError``，fail-closed）；
    ``start()`` 绑定 127.0.0.1 临时端口并起 serve 线程；``stop()`` 停接受
    循环并关监听 socket（在途隧道为 daemon 线程，随对端断开自然回收）。
    审计汇的属主是 gate 本体（不是 server）——``stop()`` 之后 ``drain_audit()``
    仍可回收本次 run 的全部条目。
    """

    def __init__(self, allowlist_raw: Sequence[str]) -> None:
        self.allowlist = normalize_allowlist(allowlist_raw)
        self._sink = _AuditSink()
        self._server: _EgressProxyServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._server is None:
            raise EgressGateError("egress 代理未启动（先 start()）")
        return int(self._server.server_address[1])

    def start(self) -> int:
        if self._server is not None:
            raise EgressGateError("egress 代理已启动（勿重复 start）")
        server = _EgressProxyServer(self.allowlist, self._sink)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
        thread.start()
        self._server = server
        self._thread = thread
        return self.port

    def stop(self) -> None:
        if self._server is None:
            return
        server, self._server, self._thread = self._server, None, None
        server.shutdown()
        server.server_close()

    def proxy_env(self) -> dict[str, str]:
        """spawn env 注入：代理指向自身，回环地址直连（NO_PROXY 防自环）。

        ``NODE_USE_ENV_PROXY=1`` 是 zcode 兼容前提的实测补件（2026-11-11
        四探针实录）：zcode 0.17.1（Electron 44 / 内嵌 Node 24.21）**默认
        无视 ``HTTPS_PROXY``**（无效白名单仍 exit 0＝绕行铁证）；Node 24
        起内建 ``NODE_USE_ENV_PROXY`` 后其 fetch/undici 才走 env 代理——
        开关注入后同探针转 **exit 1 被拦＋审计留痕**，真实白名单转放行。
        边界如实记录：该开关只约束遵守它的 Node 运行时；zcode 升级（换
        Node 版本/网络栈）须复测本节四探针，失效即按设计提请退方案 B。
        """
        proxy = f"http://127.0.0.1:{self.port}"
        return {
            "HTTP_PROXY": proxy,
            "HTTPS_PROXY": proxy,
            "http_proxy": proxy,
            "https_proxy": proxy,
            "NO_PROXY": "localhost,127.0.0.1,::1",
            "no_proxy": "localhost,127.0.0.1,::1",
            "NODE_USE_ENV_PROXY": "1",
        }

    def drain_audit(self) -> tuple[EgressAuditEntry, ...]:
        return self._sink.drain()


def summarize_audit(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """审计条目 → 事件 details 形状（计数＋去重域名有界清单，不记内容）。"""
    kinds: dict[str, int] = {}
    domains: set[str] = set()
    for entry in entries:
        kind = str(entry.get("kind", ""))
        kinds[kind] = kinds.get(kind, 0) + 1
        host = str(entry.get("host", ""))
        if host:
            domains.add(host)
    ordered = sorted(domains)
    return {
        "total": len(entries),
        "kinds": kinds,
        "domains": ordered[:20],
        "domains_truncated": len(ordered) > 20,
    }


__all__ = [
    "EgressAuditEntry",
    "EgressGateError",
    "HostEgressGate",
    "host_matches_allowlist",
    "normalize_allowlist",
    "summarize_audit",
]
