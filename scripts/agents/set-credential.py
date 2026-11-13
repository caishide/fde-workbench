r"""E11 一键配置智能体凭据（宿主裸跑态运维脚本）。

**为什么有这个脚本**：桌面端**零**凭据管理界面（只有 HTTP API），而
`POST /api/v1/agents/credentials` 要求「平台身份 ＋ system_operator AI 档」
且需自带 `Authorization: Bearer <access_token>`。access token 15 分钟过期、
登录接口还要求必填 `device_label`——手搓 curl 极易踩坑。本脚本把这三件事
一次做完：登录 → 取 access_token → 写凭据 → 校验回读。

跑法（宿主 Windows，server venv）：

```bash
# Git Bash / WSL / Linux / macOS
cd D:/test/fde-workbench/server
PYTHONPATH=src .venv/Scripts/python.exe ../scripts/agents/set-credential.py \
  --username "<你的平台身份账号>" --password "<你的密码>"
```

**PowerShell（Windows 默认终端）用这一条**——`PYTHONPATH=src` 是 bash 写法，
PowerShell 会报「无法将『PYTHONPATH=src』项识别为 cmdlet」：

```powershell
cd D:\test\fde-workbench\server
$env:PYTHONPATH="src"
.\.venv\Scripts\python.exe ..\scripts\agents\set-credential.py --username "<你的平台身份账号>" --password "<你的密码>"
```

**最省事的一条（推荐，两种终端都能跑）**——脚本会自动找 server venv 的解释器
并自行设置 `PYTHONPATH`，你**不用管 PYTHONPATH 是什么**：

```bash
python D:/test/fde-workbench/scripts/agents/set-credential.py --username "<你的平台身份账号>" --password "<你的密码>"
```

### 用户名密码填什么（最容易卡住的一步）

| 项 | 填什么 |
|---|---|
| **用户名** | **`admin`**（不是「蔡工FDE智能交付系统」——那是**产品名**，不是账号）。若你已经改过用户名，就填**你在桌面端能登录成功的那个用户名**。 |
| **密码** | ① **全新库**：`ChangeMe123!`（README「初始化」节的初始值，**首次登录强制改密**）② **你已经改过密**：填**你改后的密码**——也就是你在桌面端能登录成功的那一份。 |
| **为什么必须是 admin** | 写凭据要 `is_platform_operator`＝**平台身份**（`org_id IS NULL`）**且** `system_operator` AI 档。`admin` 角色**恒满足**这两条（`control/access.py:102` ＋ `orgs/isolation.py:36`）。别的角色即使被授予 system_operator 档，若有 `org_id`（企业身份）也会被 403 挡下。 |

⚠️ **登录连续失败 5 次会锁定约 15 分钟**（README）——密码拿不准时**别反复试**，
先在桌面端确认自己能登录成功，再来跑本脚本。

`--credential` 省略时写一个**占位串**——这是**当前唯一可用执行路径
（宿主通道）下的正确做法**：宿主通道对平台凭据**零注入**
（`agents/service.py:737` ＋ `agents/host_channel.py:150-160`），凭据行的
真实作用只是让 `credential_missing` 闸放行
（`agents/service.py:219-223`：凭据行不存在 ⇒ 409 `agent_unavailable`）。
仓库既有 bootstrap 脚本同款做法
（`scripts/simulation/sandbox_real_e2e.py:105`：明文写的是一句
`host-channel-slot-unused-by-real-adapter`，明说「不被真实适配器使用」）。

⚠️ 副作用提示：宿主通道下因为平台凭据**未被消费**，`host_channel.py:319-320`
会把 run 标成降级（`degraded=true` / `degraded_reason=host_channel_no_credential_injection`）。
这是**已知且如实标注**的状态，不是失败。

**边界（脚本不越权）**：

1. 本脚本**只写凭据行**——不发起 run、不接管、不重试、不拍板、不代确认。
2. **密码只经命令行参数传入、只用于一次登录**，不落盘、不进日志、不回显；
   但**命令行参数在进程列表里可见**（Windows `tasklist` 能看到）⇒ 建议用
   `--password-stdin`（从标准输入读一行），或在本机终端执行后随手清历史。
3. 明文只在内存中存在，落库是 Fernet 密文（`agents/credentials.py`），
   响应只回 `credential_configured: bool`，**永不回显**。
4. 脚本**不碰生产/开发库以外的任何东西**，只调既有 HTTP API——与 UI 走同一条路。
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
DEFAULT_CREDENTIAL_NAME = "default"
DEFAULT_DEVICE_LABEL = "蔡工FDE智能交付系统 运维脚本"
# 宿主通道下平台凭据零注入 ⇒ 占位串即可过闸（与既有 bootstrap 脚本同款）。
PLACEHOLDER_CREDENTIAL = "host-channel-slot-unused-by-real-adapter"


def _bootstrap_path() -> Path:
    """脚本自身路径（`scripts/agents/set-credential.py`）。"""
    return Path(__file__).resolve()


def _server_dir() -> Path:
    """仓库里的 `server/` 目录（本脚本的父父目录）。"""
    return _bootstrap_path().parents[2] / "server"


def _ensure_server_on_path() -> None:
    """把 `server/src` 挂进 `sys.path` —— 免去用户手工设 `PYTHONPATH`。

    本脚本**不需要** import 服务端包（它只调 HTTP API），但服务端在
    import 时需要 `src` 可寻址（例如 pydantic-settings 的 Settings）。
    这里主动补上，任何终端（PowerShell / bash）都直接可用。
    """
    src = _server_dir() / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _venv_python() -> Path | None:
    """server venv 里的解释器（Windows / POSIX 两种布局）。"""
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
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    """调 FDE API；返回 (状态码, 解析后的 JSON)。非 JSON 响应按原始文本塞进 `raw`。

    **禁用代理**：本机访问 `127.0.0.1:8010` 是环回直连，若走系统代理会拿到
    502「upstream connect failed」（本机装了代理软件时必现）。显式挂
    `ProxyHandler({})` 让环回请求不经代理。
    """
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
    """登录拿 access_token。

    `device_label` 是**必填**（`auth/routes.py:93` 的 `_required_strings`）——
    仓库 docs 里两处既有 curl 登录示例漏了它，会 400 `invalid_request`。
    """
    status, payload = _request(
        base_url=base_url,
        method="POST",
        path="/api/v1/auth/login",
        body={"username": username, "password": password, "device_label": device_label},
    )
    if status == 0:
        raise SystemExit(
            f"连不上服务端（{base_url}）——服务没起？先启动：\n"
            "  cd D:/test/fde-workbench && docker compose up -d\n"
            f"详细原因：{(payload.get('error') or {}).get('message')}"
        )
    if status != 200:
        error = payload.get("error") or {}
        code = error.get("code") or "-"
        message = error.get("message") or str(payload)
        hint = ""
        if status == 401:
            hint = (
                "\n提示：账号或密码不对。用户名填 `admin`（不是「蔡工FDE智能交付系统」——"
                "那是产品名）。全新库密码是 `ChangeMe123!`；改过密就填你改后的那份"
                "（能在桌面端登录成功的那份）。"
            )
        elif status == 400:
            hint = (
                "\n提示：请求被拒（多半是 device_label 缺失——本脚本已自动带上，"
                "若仍报 400 说明服务端版本较旧，请告诉 Agent）。"
            )
        raise SystemExit(f"登录失败（HTTP {status}）：{code} {message}{hint}")
    token = (payload.get("data") or {}).get("access_token")
    if not isinstance(token, str) or not token:
        raise SystemExit("登录响应里没有 access_token（字段名核对：auth/routes.py `_serialize_token_pair`）。")
    return token


def _save_credential(
    *, base_url: str, token: str, name: str, credential: str
) -> tuple[int, dict[str, Any]]:
    return _request(
        base_url=base_url,
        method="POST",
        path="/api/v1/agents/credentials",
        body={"name": name, "credential": credential},
        token=token,
    )


def _list_credentials(*, base_url: str, token: str) -> tuple[int, dict[str, Any]]:
    return _request(
        base_url=base_url, method="GET", path="/api/v1/agents/credentials", token=token
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="E11 一键配置智能体凭据（登录 → 取 token → 写凭据 → 回读校验）"
    )
    parser.add_argument("--username", required=True, help="平台身份账号（org_id 为空的 admin）")
    parser.add_argument(
        "--password",
        help="账号密码。不传则从标准输入读一行（推荐，避免出现在进程列表里）",
    )
    parser.add_argument(
        "--credential",
        help=(
            "凭据明文。省略则写占位串——宿主通道下平台凭据零注入，"
            "该行的作用只是让 credential_missing 闸放行"
        ),
    )
    parser.add_argument("--name", default=DEFAULT_CREDENTIAL_NAME, help="凭据名（默认 default）")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="服务端地址")
    parser.add_argument(
        "--device-label",
        default=DEFAULT_DEVICE_LABEL,
        help="device_label（登录必填；一般不用改）",
    )
    args = parser.parse_args(argv)

    _ensure_server_on_path()

    # ── 自举：若当前解释器不是 server venv 的那个，自动用它重跑自己 ────────
    # 目的：用户在任何终端（PowerShell / bash / cmd）敲
    #   python <脚本路径> --username ... --password ...
    # 都能跑通——不需要他手工设 PYTHONPATH，也不需要先 cd 进 server/。
    if os.environ.get("FDE_SET_CREDENTIAL_BOOTSTRAPPED") != "1":
        venv_python = _venv_python()
        if venv_python is not None and Path(sys.executable).resolve() != venv_python.resolve():
            env = dict(os.environ)
            env["FDE_SET_CREDENTIAL_BOOTSTRAPPED"] = "1"
            env["PYTHONPATH"] = os.pathsep.join(
                [str(_server_dir() / "src"), env.get("PYTHONPATH", "")]
            ).strip(os.pathsep)
            print(
                f"换用 server venv 解释器重跑：{venv_python}\n"
                "（这样你不需要自己设置 PYTHONPATH）\n",
                flush=True,
            )
            # 用子进程而非 os.execve：Windows 的 execve 不保留 stdout 重定向，
            # 会把后续输出吞掉（用户看不到任何结果，以为脚本坏了）。
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

    credential = args.credential or PLACEHOLDER_CREDENTIAL

    token = _login(
        base_url=args.base_url,
        username=args.username,
        password=password,
        device_label=args.device_label,
    )
    print("[1/3] 登录成功，已取 access_token。")

    status, payload = _save_credential(
        base_url=args.base_url, token=token, name=args.name, credential=credential
    )
    if status != 200:
        error = payload.get("error") or {}
        raise SystemExit(
            f"写凭据失败（HTTP {status}）：{error.get('code') or '-'} {error.get('message') or payload}\n"
            "提示：403 forbidden = 当前账号不是平台身份（org_id 为空）"
            "或没有 system_operator AI 档。"
        )
    print(f"[2/3] 凭据已写入：{args.name}（明文未回显，符合预期）。")

    status, payload = _list_credentials(base_url=args.base_url, token=token)
    if status != 200:
        raise SystemExit(f"回读凭据清单失败（HTTP {status}）。")
    items = payload.get("data") or []
    found = next((item for item in items if item.get("name") == args.name), None)
    if found is None:
        raise SystemExit(f"回读校验失败：清单里没有 {args.name}。")
    if not found.get("credential_configured"):
        raise SystemExit(f"回读校验失败：{args.name} 的 credential_configured 为 false。")
    print(f"[3/3] 回读校验通过：{args.name} → credential_configured=true")

    print()
    print("下一步（步骤三）：改 server/.env 的三个宿主通道变量，然后重建服务：")
    print("  FDE_AGENT_HOST_CHANNEL_ENABLED=1")
    print("  FDE_AGENT_HOST_ZCODE_BIN=<ZCode.exe 全路径>")
    print("  FDE_AGENT_HOST_ZCODE_CJS=<zcode.cjs 全路径>")
    print("  cd server && docker compose build && docker compose up -d && alembic upgrade head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
