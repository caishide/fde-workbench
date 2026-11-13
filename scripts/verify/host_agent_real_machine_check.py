r"""goal-sprint r3 隔离环境真机验收：宿主代理一次非交互执行产出可校验产物。

**工程级验收**（不创建生产 AgentRun＝H4 边界不碰；N1 首个生产 run 仍归
蔡工亲手发起，窗口 2026-11-19 止）。链路全真、只把「服务端」换成进程内
存根（四咬合面 status/claim/context/receipt 形状与真实路由逐字段同源）：

- 真实传输：``HttpHostTransport`` over loopback HTTP（含 ``{data:…}``
  信封拆解）；
- 真实 spawn：``run_host_channel`` 默认 spawner → 真实 zcode 0.17.1
  非交互（``-p <任务书> --json --cwd <隔离工作区>``，凭据走宿主登录态）；
- 真实 ⑦ 出站闸：``HostEgressGate`` ＋ GLM 端点族白名单（部署态同款六域），
  ``NODE_USE_ENV_PROXY=1`` 实测补件随 proxy_env 注入；
- 隔离工作区：TEMP 下一次性目录，**绝不触碰** ``D:\test\FDE\`` 真相层
  （``assert_host_workspace_allowed`` 拒绝清单双保险）。

判据（全部过才算过，任一不过进程退出码 1）：
  1. 一次生命周期收场＝回执 ``status=completed``；
  2. 回执 ``artifacts[0].sha256`` ＝ 工作区产物**字节级重算**指纹（可校验产物）；
  3. ``summary`` 投影 billable_units > 0（真模型消耗，非空转）；
  4. context 咬合面被消费（面料经服务端读面下发）；
  5. egress 审计摘要落在回执里且域名全部白名单域/回环、零 blocked
     （⑦ 边界宿主侧实证；回环＝zcode 本地 broker IPC，r3 实测豁免面）。

用法：``server/.venv/Scripts/python.exe scripts/verify/host_agent_real_machine_check.py``
（zcode 路径可用 FDE_AGENT_HOST_ZCODE_BIN / FDE_AGENT_HOST_ZCODE_CJS 覆写）。
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_SERVER_SRC = Path(__file__).resolve().parents[2] / "server" / "src"
sys.path.insert(0, str(_SERVER_SRC))

from fde_api.agents.host_agent import HostAgentConfig, run_once

TASK_MARKER = "R3-VERIFY-OK"

TASK_MD = """# 任务书（goal-sprint r3 真机验收）

- 项目代号: VERIFY-R3
- 能力: agent.verify

请在 output/ 目录创建 report.md：第一行必须是固定标记
`{marker} <当前ISO时间戳>`，其后再写一行本次执行的平台描述（任意）。
另在 output/ 创建 manifest.json，必须是 JSON 数组（不是对象）：
`[{{"path": "report.md", "kind": "doc", "source_refs": ["verify"]}}]`。
除上述两份文件外不要做任何其他事情。
"""

# ⑦ 部署态同款白名单（AGENTS.md 红线第 7 条六域）。
EGRESS_ALLOWLIST = ["zcode.z.ai", "api.z.ai", "z.ai", "api.minimaxi.com", "bigmodel.cn", "open.bigmodel.cn"]

# 存根咬合面（形状与 routes.py 三路由 + host_context 逐字段同源）
CLAIM_PAYLOAD = {
    "run_id": "verify-r3-hostagent",
    "project_id": "proj-verify",
    "capability": "agent.verify",
    "context_ref": "stub://verify",
    "allowed_tools": [],
    "max_duration_ms": 300_000,
    "max_cost_units": 0,
    "claimed_at": "2026-11-13T00:00:00+00:00",
    "already_running": False,
}


class _StubServer:
    """进程内存根服务端：记录回执、下发领取/面料。"""

    def __init__(self) -> None:
        self.receipts: list[dict] = []
        self.context_served = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _send(self, code: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/api/v1/agents/host/status":
                    self._send(200, {"data": {"pending": 1, "lost_marked": 0}})
                elif self.path.startswith("/api/v1/agents/host/runs/") and self.path.endswith("/context"):
                    outer.context_served = True
                    workspace = outer.workspace
                    self._send(200, {
                        "data": {
                            "run_id": CLAIM_PAYLOAD["run_id"],
                            "files": {
                                "context.md": "# 验收上下文\n本轮为工程级隔离验收（代号 VERIFY-R3）。\n",
                                "task.md": (workspace / "task.md").read_text(encoding="utf-8"),
                                "AGENTS.md": "# 验收纪律\n只做任务书内的事。\n",
                            },
                        }
                    })
                else:
                    self._send(404, {"data": None, "error": {"code": "not_found", "message": "nf"}})

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                payload = json.loads(raw.decode("utf-8"))
                if self.path == "/api/v1/agents/host/claim":
                    self._send(200, {"data": CLAIM_PAYLOAD})
                elif self.path.startswith("/api/v1/agents/host/runs/") and self.path.endswith("/receipt"):
                    outer.receipts.append(payload)
                    self._send(200, {"data": {"run_id": CLAIM_PAYLOAD["run_id"], "status": payload.get("status"), "duplicate": False}})
                else:
                    self._send(404, {"data": None, "error": {"code": "not_found", "message": "nf"}})

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self.workspace: Path | None = None
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        self._server.shutdown()


def main() -> int:
    zcode_bin = sys.argv[1] if len(sys.argv) > 1 else "D:/software/zcode/ZCode.exe"
    zcode_cjs = sys.argv[2] if len(sys.argv) > 2 else "D:/software/zcode/resources/glm/zcode.cjs"
    temp_root = Path(tempfile.mkdtemp(prefix="fde-hostagent-verify-"))
    workspace = temp_root / CLAIM_PAYLOAD["run_id"]
    (workspace / "output").mkdir(parents=True, exist_ok=True)
    (workspace / "task.md").write_text(TASK_MD.format(marker=TASK_MARKER), encoding="utf-8")

    stub = _StubServer()
    stub.workspace = workspace
    config = HostAgentConfig(
        api_base=f"http://127.0.0.1:{stub.port}",
        poll_token="verify-token-not-a-secret",
        workspace_root=str(temp_root),
        zcode_bin=zcode_bin,
        cjs_path=zcode_cjs,
        cli_config_path="",  # 缺省 ~/.zcode/cli/config.json（N2 事实②）
        egress_gate_enabled=True,
        egress_allowlist=tuple(EGRESS_ALLOWLIST),
    )
    print(f"[verify] stub=http://127.0.0.1:{stub.port} workspace={workspace}")
    try:
        outcome = run_once(config)  # 真实传输 + 真实 spawn + 真实出站闸
    finally:
        stub.stop()

    checks: list[tuple[str, bool, str]] = []
    checks.append(("outcome=receipted", outcome.get("outcome") == "receipted", str(outcome.get("outcome"))))
    # 判据读 **POST 本体**（stub.receipts[0]＝回执载荷）；outcome["receipt"]
    # 是存根响应的整信封（{data:…}），不作判据源。
    payload_recorded = stub.receipts[0] if stub.receipts else {}
    checks.append(("回执 status=completed", payload_recorded.get("status") == "completed", str(payload_recorded.get("status"))))
    artifacts = payload_recorded.get("artifacts") or []
    report = workspace / "output" / "report.md"
    digest = hashlib.sha256(report.read_bytes()).hexdigest() if report.is_file() else ""
    received = artifacts[0].get("sha256") if artifacts else ""
    checks.append(("产物指纹字节级一致", bool(digest) and digest == received, f"receipt={received[:16]}… actual={digest[:16]}…"))
    summary = payload_recorded.get("summary") or {}
    projection = summary.get("projection") or {}
    usage = summary.get("usage") or {}
    billable = int(projection.get("totalTokenCount") or 0) or (int(usage.get("inputTokens") or 0) + int(usage.get("outputTokens") or 0))
    checks.append(("billable_units>0（真模型消耗）", billable > 0, str(billable)))
    checks.append(("context 咬合面被消费", stub.context_served, str(stub.context_served)))
    # ⑦ 审计判据：回执携 summarize_audit 有界摘要；域名只许白名单域或回环
    # （zcode 本地 broker IPC，r3 实测豁免面），类别不许出现 blocked。
    audit = payload_recorded.get("egress_audit") or {}
    allowed_hosts = set(EGRESS_ALLOWLIST) | {"127.0.0.1", "localhost", "::1"}
    benign_kinds = {"tunnel_allowed", "tunnel_loopback", "tunnel_upstream_error"}
    audit_domains = set(audit.get("domains") or [])
    audit_kinds = set(audit.get("kinds") or {})
    audit_ok = bool(audit) and audit_domains <= allowed_hosts and audit_kinds <= benign_kinds
    checks.append((
        "egress 审计全部白名单域/回环且零 blocked",
        audit_ok,
        f"kinds={sorted(audit_kinds)} domains={sorted(audit_domains)}",
    ))
    if not all(ok for _, ok, _ in checks):
        print("[诊断] 回执载荷 =", json.dumps(payload_recorded, ensure_ascii=False)[:1200])
        print("[诊断] outcome =", json.dumps({k: v for k, v in outcome.items() if k != "receipt"}, ensure_ascii=False)[:600])

    print("=" * 56)
    all_pass = True
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}  {detail if not ok else ''}")
        all_pass = all_pass and ok
    print(f"  产物: {report}")
    print(f"  产物 sha256: {digest}")
    print(f"  汇总: usage={json.dumps(usage, ensure_ascii=False)} projection={json.dumps(projection, ensure_ascii=False)}")
    print(f"  工作区: {workspace}")
    print("=" * 56)
    print("VERIFY-R3 RESULT:", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
