r"""E11 一键发起 agent run（宿主裸跑态运维脚本）。

**为什么有这个脚本**：桌面端「发起 run」的唯一入口是 AI 对话里的
`api_execute` 工具，而该工具**只在 DSH runtime 在线时暴露**
（`control/ai_server_client.py:370`：`issue_mcp_token(...) if (use_tools and dsh_usable)`）。
本机**没有 DSH 容器**（`FDE_DSH_ENABLED` 默认 False，8020 无服务）⇒ AI 对话走
降级直连 ⇒ 直连只暴露 13 个**只读**工具（`control/ai_tool_loop.py:42-56`，
不含 `api_execute`）⇒ **模型调不了任何写动作**，会话表现为「没执行完就断了」。

本脚本走**人直接调既有 HTTP API**这条路（与在桌面端点按钮同级）：
登录 → 选 agent → 发起 run → 回读 run 详情。

跑法（任意终端，脚本自举换 server venv 解释器）：

```bash
python D:/test/fde-workbench/scripts/agents/start-run.py --username admin --password "你的密码"
```

可选参数：

```bash
  --project pilot-001              # 项目名或 id（默认 pilot-001）
  --agent "售前智能体"                # agent 名或 id（默认：自动挑一个「已配凭据且可用」的）
  --idempotency-key pilot-001-first-run-001
  --difficulty standard|high
  --dry-run                        # 只查可用 agent 与项目，不真的发起
```

**边界（脚本不越权）**：

1. 本脚本**只发起 run**（机械执行）——**产物接受、门禁拍板、审批确认一律不碰**。
2. **不代人工确认**：走的是人直调 HTTP API（不经 `awaiting_confirmation` 二次确认，
   与桌面端人直调同语义）；AI 侧的「受控提议通道」红线不受影响。
3. **不改任何配置**：凭据槽位、宿主通道、`.env` 一概不动。
4. **失败即停**：任一闸不过就打印**闸位与原因**并退出，不重试、不绕闸。
5. **幂等**：同 `--idempotency-key` 重复跑**不会重复计费、不会重复落产物**
   （服务端按幂等键复用既有 run）。

**已知的三个前置**（脚本会逐项检查并给可执行提示）：

- ① agent 的 `credential_ref` 必须指向**已存在的凭据槽位**，否则 409 `credential_missing`；
- ② 宿主通道须开启（`FDE_AGENT_HOST_CHANNEL_ENABLED=1`）且 zcode 路径已配，
  否则 409 `agent_unavailable` / `host_channel_bin_missing`；
- ③ 账号须具备该 agent 的能力档位（admin 角色恒为 `system_operator` ⇒ 天然满足）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8010"
DEFAULT_DEVICE_LABEL = "蔡工FDE智能交付系统 运维脚本"
DEFAULT_PROJECT = "pilot-001"
DEFAULT_IDEMPOTENCY_KEY = "pilot-001-first-run-001"
BOOTSTRAP_ENV = "FDE_SET_CREDENTIAL_BOOTSTRAPPED"


def _bootstrap_path() -> Path:
    return Path(__file__).resolve()


def _server_dir() -> Path:
    return _bootstrap_path().parents[2] / "server"


def _ensure_server_on_path() -> None:
    src = _server_dir() / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _venv_python() -> Path | None:
    server = _server_dir()
    for relative in (
        Path(".venv") / "Scripts" / "python.exe",
        Path(".venv") / "bin" / "python",
        Path(".venv") / "bin" / "python3",
    ):
        candidate = server / relative
        if candidate.is_file():
            return candidate
    return None


def _request(
    *,
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: int = 60,
) -> tuple[int, dict[str, Any]]:
    """调 FDE API；返回 (状态码, 解析后的 JSON)。环回请求**禁用系统代理**。"""
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        status = int(error.code)
    except urllib.error.URLError as error:
        return 0, {"error": {"code": "connection_failed", "message": str(error.reason)}}
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        payload = {"raw": raw}
    if not isinstance(payload, dict):
        payload = {"raw": payload}
    return status, payload


def _login(*, base_url: str, username: str, password: str, device_label: str) -> str:
    status, payload = _request(
        base_url=base_url,
        method="POST",
        path="/api/v1/auth/login",
        body={"username": username, "password": password, "device_label": device_label},
    )
    if status == 0:
        raise SystemExit(
            f"连不上服务端（{base_url}）——服务没起？先启动：\n"
            "  cd D:/test/fde-workbench && docker compose up -d"
        )
    if status != 200:
        error = payload.get("error") or {}
        raise SystemExit(
            f"登录失败（HTTP {status}）：{error.get('code') or '-'} {error.get('message') or payload}\n"
            "提示：用户名填 admin（不是产品名「蔡工FDE智能交付系统」）；密码填你在桌面端"
            "能登录成功的那份。"
        )
    token = (payload.get("data") or {}).get("access_token")
    if not isinstance(token, str) or not token:
        raise SystemExit("登录响应里没有 access_token。")
    return token


def _data(payload: dict[str, Any]) -> Any:
    return payload.get("data")


def _error_text(payload: dict[str, Any]) -> str:
    error = payload.get("error") or {}
    parts = [str(error.get("code") or "-"), str(error.get("message") or "")]
    details = error.get("details")
    if details:
        parts.append(json.dumps(details, ensure_ascii=False))
    return " ".join(part for part in parts if part)


def _resolve_project(base_url: str, token: str, wanted: str) -> tuple[str, str]:
    """把项目名/id 解析成 (id, 显示名)。找不到就报错并列出候选。"""
    status, payload = _request(
        base_url=base_url, method="GET", path="/api/v1/projects", token=token
    )
    if status != 200:
        raise SystemExit(f"查项目列表失败（HTTP {status}）：{_error_text(payload)}")
    items = _data(payload) or []
    if isinstance(items, dict):
        items = items.get("items") or []
    for item in items:
        if item.get("id") == wanted or item.get("name") == wanted:
            return str(item.get("id")), str(item.get("name") or wanted)
    names = ", ".join(f"{i.get('name')}({str(i.get('id'))[:8]}…)" for i in items[:8]) or "(空)"
    raise SystemExit(f"找不到项目「{wanted}」。可见项目：{names}")


def _list_agents(base_url: str, token: str) -> list[dict[str, Any]]:
    status, payload = _request(
        base_url=base_url, method="GET", path="/api/v1/agents", token=token
    )
    if status != 200:
        raise SystemExit(f"查智能体注册表失败（HTTP {status}）：{_error_text(payload)}")
    items = _data(payload) or []
    if isinstance(items, dict):
        items = items.get("items") or []
    return [i for i in items if isinstance(i, dict)]


def _has_credential(item: dict[str, Any]) -> bool:
    """该 agent 的凭据槽位是否已配。

    `GET /api/v1/agents` 的响应**没有** `credential_configured` 字段，只有
    `available` ＋ `unavailable_reason`（取值：`disabled` / `adapter_missing` /
    `credential_missing` / `tools_unavailable` / 空＝可用）
    ⇒ 这里以「不可用原因不是 credential_missing」作为「已配凭据」的判据。
    """
    return str(item.get("unavailable_reason") or "") != "credential_missing"


def _pick_agent(
    agents: list[dict[str, Any]], wanted: str | None
) -> dict[str, Any]:
    """选 agent：指定了就按名/id 找；没指定就挑**第一个可用且已配凭据**的。"""
    if wanted:
        for item in agents:
            if item.get("id") == wanted or item.get("name") == wanted:
                return item
        names = ", ".join(str(i.get("name")) for i in agents[:10])
        raise SystemExit(f"找不到智能体「{wanted}」。可选：{names}")
    for item in agents:
        if item.get("kind") == "persona":
            continue
        if item.get("available") and _has_credential(item):
            return item
    for item in agents:
        if item.get("kind") != "persona" and item.get("available"):
            return item
    raise SystemExit(
        "没有任何可用智能体。请检查：① 宿主通道是否开启（server/.env 的 "
        "FDE_AGENT_HOST_CHANNEL_ENABLED=1）；② zcode 路径是否配对；"
        "③ 凭据槽位是否存在（跑 set-credential.py）。"
    )


def _agent_table(agents: list[dict[str, Any]]) -> str:
    header = f"  {'名称'.ljust(12)}{'可用'.ljust(6)}{'凭据'.ljust(8)}不可用原因"
    lines = [header]
    for item in agents:
        name = str(item.get("name") or "")[:10]
        available = "是" if item.get("available") else "否"
        credential = "已配" if _has_credential(item) else "★缺★"
        reason = str(item.get("unavailable_reason") or "")
        lines.append(f"  {name.ljust(12)}{available.ljust(6)}{credential.ljust(8)}{reason}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="E11 一键发起 agent run（人直调既有 HTTP API）")
    parser.add_argument("--username", required=True, help="平台身份账号（admin）")
    parser.add_argument("--password", help="账号密码。不传则从标准输入读一行")
    parser.add_argument("--project", default=DEFAULT_PROJECT, help="项目名或 id（默认 pilot-001）")
    parser.add_argument("--agent", help="智能体名或 id（默认自动挑可用的）")
    parser.add_argument("--idempotency-key", default=DEFAULT_IDEMPOTENCY_KEY, help="幂等键")
    parser.add_argument("--difficulty", default="standard", choices=("standard", "high"))
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="服务端地址")
    parser.add_argument("--device-label", default=DEFAULT_DEVICE_LABEL, help="device_label（登录必填）")
    parser.add_argument("--dry-run", action="store_true", help="只查可用 agent 与项目，不发起")
    args = parser.parse_args(argv)

    _ensure_server_on_path()

    # 自举：用 server venv 解释器重跑（用户不必设 PYTHONPATH）。
    if os.environ.get(BOOTSTRAP_ENV) != "1":
        venv_python = _venv_python()
        if venv_python is not None and Path(sys.executable).resolve() != venv_python.resolve():
            env = dict(os.environ)
            env[BOOTSTRAP_ENV] = "1"
            env["PYTHONPATH"] = os.pathsep.join(
                [str(_server_dir() / "src"), env.get("PYTHONPATH", "")]
            ).strip(os.pathsep)
            print(
                f"换用 server venv 解释器重跑：{venv_python}\n"
                "（这样你不需要自己设置 PYTHONPATH）\n",
                flush=True,
            )
            import subprocess

            completed = subprocess.run(
                [str(venv_python), str(_bootstrap_path()), *sys.argv[1:]],
                env=env,
                check=False,
            )
            raise SystemExit(completed.returncode)

    password = args.password
    if password is None:
        if sys.stdin.isatty():
            raise SystemExit(
                "未提供 --password 且标准输入不是终端：请直接带 --password，"
                "或用 `echo <密码> | python ...` 从标准输入传入。"
            )
        password = sys.stdin.readline().rstrip("\r\n")
    if not password:
        raise SystemExit("密码为空。")

    token = _login(
        base_url=args.base_url,
        username=args.username,
        password=password,
        device_label=args.device_label,
    )
    print("[1/4] 登录成功，已取 access_token。")

    project_id, project_name = _resolve_project(args.base_url, token, args.project)
    print(f"[2/4] 项目已定位：{project_name}（{project_id}）")

    agents = _list_agents(args.base_url, token)
    agent = _pick_agent(agents, args.agent)
    agent_id = str(agent.get("id") or "")
    agent_name = str(agent.get("name") or "")
    print(f"[3/4] 智能体已选定：{agent_name}（{agent_id}）")
    print("\n可用智能体一览：")
    print(_agent_table(agents))

    if args.dry_run:
        print("\n[dry-run] 按要求未发起 run。去掉 --dry-run 即可真发起。")
        return 0

    status, payload = _request(
        base_url=args.base_url,
        method="POST",
        path=f"/api/v1/agents/{agent_id}/run",
        body={
            "project_id": project_id,
            "idempotency_key": args.idempotency_key,
            "difficulty": args.difficulty,
        },
        token=token,
        timeout=120,
    )
    if status not in (200, 201):
        print(f"\n✗ 发起 run 失败（HTTP {status}）：{_error_text(payload)}")
        print("\n按错误码自查：")
        print("  credential_missing      → 该 agent 的凭据槽位是空的，换一个已配凭据的 agent")
        print("  host_channel_bin_missing→ server/.env 的 zcode 路径没配对")
        print("  project_not_found       → 项目 id 不对")
        print("  agent_unavailable       → 看上面「不可用原因」列")
        print("  403 forbidden           → 账号缺该 agent 的能力档位")
        return 1

    data = _data(payload) or {}
    run_id = str(data.get("id") or "")
    print(f"\n[4/4] run 已落库：{run_id}（status={data.get('status')}）")

    detail_status, detail_payload = _request(
        base_url=args.base_url,
        method="GET",
        path=f"/api/v1/agents/runs/{run_id}",
        token=token,
    )
    if detail_status == 200:
        detail = _data(detail_payload) or {}
        print("\nrun 详情：")
        for key in (
            "id",
            "status",
            "agent_id",
            "project_id",
            "degraded",
            "degraded_reason",
            "fallback_level",
            "exit_code",
            "token_cost",
            "duration_ms",
            "error_code",
        ):
            if key in detail:
                print(f"  {key} = {json.dumps(detail[key], ensure_ascii=False)}")
    else:
        print(f"（回读详情失败：HTTP {detail_status}）")

    print("\n下一步：")
    print("  1) 桌面端「项目 → 智能体」tab 看这条 run 的状态；")
    print("  2) 让 Agent 跑 scripts/verify/verify-run-evidence.sql 采集证据（只读）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
