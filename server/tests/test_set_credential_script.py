"""E11 一键凭据配置脚本的用例（`scripts/agents/set-credential.py`）。

覆盖：
1. **登录带 `device_label`**（必填，漏了 400）——脚本必须带；
2. **登录响应取 `access_token`**（不是 `token`）；
3. **写凭据用 `POST /api/v1/agents/credentials` ＋ Bearer**；
4. **回读校验**（`credential_configured=true`）；
5. **`--credential` 省略时写占位串**（宿主通道零注入 ⇒ 占位串即可过闸）；
6. **登录失败时明确报错退出**（不吞错）。

**不联网**——用本地假 HTTP 服务（http.server）接请求，校验真实请求形状。
"""
from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "agents" / "set-credential.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("set_credential_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Handler(BaseHTTPRequestHandler):
    """假 API 服务：记录收到的请求，按路径回响应。"""

    calls: list[dict[str, Any]] = []
    login_status = 200
    save_status = 200
    list_status = 200

    def log_message(self, *args: Any) -> None:  # 静默
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
            "method": "POST",
            "path": self.path,
            "body": body,
            "authorization": self.headers.get("Authorization"),
        })
        if self.path == "/api/v1/auth/login":
            if type(self).login_status != 200:
                self._reply(type(self).login_status, {
                    "data": None,
                    "error": {"code": "invalid_credentials", "message": "账号或密码不正确。"},
                })
                return
            self._reply(200, {"data": {"access_token": "tok-abc", "refresh_token": "ref-xyz"},
                              "error": None})
            return
        if self.path == "/api/v1/agents/credentials":
            if type(self).save_status != 200:
                self._reply(type(self).save_status, {
                    "data": None,
                    "error": {"code": "forbidden", "message": "当前账号无权配置智能体凭据。"},
                })
                return
            self._reply(200, {"data": {"id": "c1", "name": body.get("name"),
                                       "credential_configured": True}, "error": None})
            return
        self._reply(404, {"data": None, "error": {"code": "not_found", "message": "?"}})

    def do_GET(self) -> None:  # noqa: N802
        self.calls.append({
            "method": "GET",
            "path": self.path,
            "body": {},
            "authorization": self.headers.get("Authorization"),
        })
        if self.path == "/api/v1/agents/credentials":
            if type(self).list_status != 200:
                self._reply(type(self).list_status, {"data": None, "error": {"code": "x", "message": "y"}})
                return
            self._reply(200, {"data": [{"id": "c1", "name": "default",
                                        "credential_configured": True}], "error": None})
            return
        self._reply(404, {"data": None, "error": {"code": "not_found", "message": "?"}})


@pytest.fixture
def api_server():
    _Handler.calls = []
    _Handler.login_status = 200
    _Handler.save_status = 200
    _Handler.list_status = 200
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def test_login_request_carries_device_label(api_server):
    """登录必须带 `device_label`——漏了服务端 400 invalid_request。"""
    module = _load_module()
    module.main(["--username", "admin", "--password", "pw", "--base-url", api_server])

    login_calls = [c for c in _Handler.calls if c["path"] == "/api/v1/auth/login"]
    assert len(login_calls) == 1
    assert login_calls[0]["body"]["device_label"], "device_label 必填，不能为空"


def test_write_credential_uses_bearer_and_correct_shape(api_server):
    """写凭据请求：Bearer 头 ＋ 只带 name/credential 两个字段。"""
    module = _load_module()
    module.main([
        "--username", "admin", "--password", "pw", "--base-url", api_server,
        "--credential", "zkey-123",
    ])

    save_calls = [c for c in _Handler.calls if c["path"] == "/api/v1/agents/credentials"
                  and c["method"] == "POST"]
    assert len(save_calls) == 1
    assert save_calls[0]["authorization"] == "Bearer tok-abc"
    assert set(save_calls[0]["body"]) == {"name", "credential"}
    assert save_calls[0]["body"]["name"] == "default"
    assert save_calls[0]["body"]["credential"] == "zkey-123"


def test_credential_omitted_falls_back_to_placeholder(api_server):
    """省略 --credential ⇒ 写占位串（宿主通道零注入，占位即可过闸）。"""
    module = _load_module()
    module.main(["--username", "admin", "--password", "pw", "--base-url", api_server])

    save_calls = [c for c in _Handler.calls if c["method"] == "POST"
                  and c["path"] == "/api/v1/agents/credentials"]
    assert len(save_calls) == 1
    assert save_calls[0]["body"]["credential"] == module.PLACEHOLDER_CREDENTIAL


def test_script_verifies_by_reading_back(api_server):
    """脚本必须回读校验（不是“写完就报成功”）。"""
    module = _load_module()
    module.main(["--username", "admin", "--password", "pw", "--base-url", api_server])

    list_calls = [c for c in _Handler.calls if c["method"] == "GET"
                  and c["path"] == "/api/v1/agents/credentials"]
    assert len(list_calls) == 1
    assert list_calls[0]["authorization"] == "Bearer tok-abc"


def test_login_failure_exits_with_message(api_server):
    """登录失败 ⇒ 明确报错退出（不吞错、不继续写凭据）。"""
    _Handler.login_status = 401
    module = _load_module()
    with pytest.raises(SystemExit) as error:
        module.main(["--username", "admin", "--password", "bad", "--base-url", api_server])
    assert "登录失败" in str(error.value)
    assert not [c for c in _Handler.calls if c["method"] == "POST"
                and c["path"] == "/api/v1/agents/credentials"]


def test_forbidden_on_save_exits_with_hint(api_server):
    """403 ⇒ 提示「平台身份 / system_operator AI 档」（小白能据此自查）。"""
    _Handler.save_status = 403
    module = _load_module()
    with pytest.raises(SystemExit) as error:
        module.main(["--username", "eng", "--password", "pw", "--base-url", api_server])
    message = str(error.value)
    assert "写凭据失败" in message
    assert "平台身份" in message


def test_missing_password_without_stdin_exits(api_server, monkeypatch):
    """既没 --password 又没标准输入 ⇒ 明确提示，不静默用空密码。"""
    class _NotTTY:
        def isatty(self) -> bool:
            return True

        def readline(self) -> str:
            return ""

    module = _load_module()
    monkeypatch.setattr(module.sys, "stdin", _NotTTY())
    with pytest.raises(SystemExit) as error:
        module.main(["--username", "admin", "--base-url", api_server])
    assert "密码" in str(error.value)
