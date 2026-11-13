"""E11 一键发起 run 脚本的用例（`scripts/agents/start-run.py`）。

覆盖：
1. **登录带 `device_label`**（必填，漏了 400）；
2. **项目按名或 id 解析**（找不到时报错并列出候选）；
3. **agent 自动挑选**：跳过 persona、跳过不可用的、跳过缺凭据的；
4. **发起 run 的请求形状**：路径 `/api/v1/agents/<id>/run`、body 三字段
   （`project_id` / `idempotency_key` / `difficulty`）、Bearer 头；
5. **`--dry-run` 不发起**（只查不写）；
6. **失败即停并给错误码自查提示**（不重试、不绕闸）。

**不联网**——本地假 HTTP 服务。
"""
from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "agents" / "start-run.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("start_run_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Handler(BaseHTTPRequestHandler):
    calls: list[dict[str, Any]] = []
    login_status = 200
    projects_status = 200
    agents_status = 200
    run_status = 201
    detail_status = 200
    agents_payload: list[dict[str, Any]] = []
    projects_payload: list[dict[str, Any]] = []

    def log_message(self, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except ValueError:
            return {}

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self) -> None:  # noqa: N802
        body = self._read_json()
        self.calls.append({
            "method": "POST", "path": self.path, "body": body,
            "authorization": self.headers.get("Authorization"),
        })
        if self.path == "/api/v1/auth/login":
            if type(self).login_status != 200:
                self._reply(type(self).login_status, {
                    "data": None,
                    "error": {"code": "invalid_credentials", "message": "账号或密码不正确。"}})
                return
            self._reply(200, {"data": {"access_token": "tok-abc"}, "error": None})
            return
        if self.path.startswith("/api/v1/agents/") and self.path.endswith("/run"):
            if type(self).run_status not in (200, 201):
                self._reply(type(self).run_status, {
                    "data": None,
                    "error": {"code": "agent_unavailable", "message": "智能体当前不可用。",
                              "details": {"reason": "credential_missing"}}})
                return
            self._reply(type(self).run_status, {
                "data": {"id": "run-1", "status": "queued"}, "error": None})
            return
        self._reply(404, {"data": None, "error": {"code": "not_found", "message": "?"}})

    def do_GET(self) -> None:  # noqa: N802
        self.calls.append({
            "method": "GET", "path": self.path, "body": {},
            "authorization": self.headers.get("Authorization"),
        })
        if self.path == "/api/v1/projects":
            if type(self).projects_status != 200:
                self._reply(type(self).projects_status, {
                    "data": None, "error": {"code": "x", "message": "y"}})
                return
            self._reply(200, {"data": {"items": type(self).projects_payload}, "error": None})
            return
        if self.path == "/api/v1/agents":
            if type(self).agents_status != 200:
                self._reply(type(self).agents_status, {
                    "data": None, "error": {"code": "x", "message": "y"}})
                return
            self._reply(200, {"data": {"items": type(self).agents_payload}, "error": None})
            return
        if self.path.startswith("/api/v1/agents/runs/"):
            if type(self).detail_status != 200:
                self._reply(type(self).detail_status, {
                    "data": None, "error": {"code": "x", "message": "y"}})
                return
            self._reply(200, {"data": {"id": "run-1", "status": "queued", "degraded": False},
                              "error": None})
            return
        self._reply(404, {"data": None, "error": {"code": "not_found", "message": "?"}})


@pytest.fixture
def api_server():
    _Handler.calls = []
    _Handler.login_status = 200
    _Handler.projects_status = 200
    _Handler.agents_status = 200
    _Handler.run_status = 201
    _Handler.detail_status = 200
    _Handler.projects_payload = [
        {"id": "proj-1", "name": "pilot-001"},
        {"id": "proj-2", "name": "other"},
    ]
    _Handler.agents_payload = [
        {"id": "a-persona", "name": "模拟财务视角", "kind": "persona",
         "available": True, "unavailable_reason": None},
        {"id": "a-nocred", "name": "质量守卫", "kind": "zcode",
         "available": False, "unavailable_reason": "credential_missing"},
        {"id": "a-ok", "name": "售前智能体", "kind": "zcode",
         "available": True, "unavailable_reason": None},
        {"id": "a-ok2", "name": "方案智能体", "kind": "zcode",
         "available": True, "unavailable_reason": None},
    ]
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def _run(module, api_server, *extra: str):
    return module.main([
        "--username", "admin", "--password", "pw", "--base-url", api_server, *extra
    ])


def test_login_request_carries_device_label(api_server):
    """登录必须带 device_label（漏了服务端 400）。"""
    module = _load_module()
    _run(module, api_server, "--dry-run")
    login_calls = [c for c in _Handler.calls if c["path"] == "/api/v1/auth/login"]
    assert len(login_calls) == 1
    assert login_calls[0]["body"]["device_label"]


def test_project_resolved_by_name(api_server):
    """项目按名字解析成 id。"""
    module = _load_module()
    _run(module, api_server, "--dry-run")
    assert module._resolve_project(api_server, "tok-abc", "pilot-001")[0] == "proj-1"


def test_project_resolved_by_id(api_server):
    """项目按 id 也能解析。"""
    module = _load_module()
    assert module._resolve_project(api_server, "tok-abc", "proj-2")[0] == "proj-2"


def test_missing_project_lists_candidates(api_server):
    """找不到项目 ⇒ 报错并列出可见项目（小白能据此纠正）。"""
    module = _load_module()
    with pytest.raises(SystemExit) as error:
        module._resolve_project(api_server, "tok-abc", "nope")
    assert "找不到项目" in str(error.value)
    assert "pilot-001" in str(error.value)


def test_agent_pick_skips_persona_and_missing_credential(api_server):
    """自动挑 agent：跳过 persona、跳过缺凭据的。"""
    module = _load_module()
    agents = module._list_agents(api_server, "tok-abc")
    picked = module._pick_agent(agents, None)
    assert picked["id"] == "a-ok"


def test_agent_pick_by_name(api_server):
    """按名字指定 agent。"""
    module = _load_module()
    agents = module._list_agents(api_server, "tok-abc")
    assert module._pick_agent(agents, "方案智能体")["id"] == "a-ok2"


def test_dry_run_does_not_start_run(api_server):
    """--dry-run 只查不发起。"""
    module = _load_module()
    _run(module, api_server, "--dry-run")
    assert not [c for c in _Handler.calls if c["path"].endswith("/run")]


def test_start_run_request_shape(api_server):
    """发起 run：路径 + Bearer + body 三字段。"""
    module = _load_module()
    _run(module, api_server)
    run_calls = [c for c in _Handler.calls if c["path"].endswith("/run")]
    assert len(run_calls) == 1
    assert run_calls[0]["path"] == "/api/v1/agents/a-ok/run"
    assert run_calls[0]["authorization"] == "Bearer tok-abc"
    assert set(run_calls[0]["body"]) == {"project_id", "idempotency_key", "difficulty"}
    assert run_calls[0]["body"]["project_id"] == "proj-1"


def test_start_run_reads_back_detail(api_server):
    """发起后回读 run 详情（GET /agents/runs/<id>）。"""
    module = _load_module()
    _run(module, api_server)
    detail_calls = [c for c in _Handler.calls if c["path"].startswith("/api/v1/agents/runs/")]
    assert len(detail_calls) == 1


def test_failed_run_exits_nonzero_with_hint(api_server, capsys):
    """发起失败 ⇒ 返回非零退出码并给错误码自查提示（不重试、不绕闸）。"""
    _Handler.run_status = 409
    module = _load_module()
    code = _run(module, api_server)
    assert code == 1
    printed = capsys.readouterr().out
    assert "发起 run 失败" in printed
    assert "credential_missing" in printed


def test_login_failure_exits_with_hint(api_server):
    """登录失败 ⇒ 明确提示（含「用户名填 admin，不是产品名」）。"""
    _Handler.login_status = 401
    module = _load_module()
    with pytest.raises(SystemExit) as error:
        _run(module, api_server, "--dry-run")
    message = str(error.value)
    assert "登录失败" in message
    assert "admin" in message
