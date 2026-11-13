r"""E11 一键配置智能体凭据（宿主裸跑态运维脚本）。

**为什么有这个脚本**：桌面端**零**凭据管理界面（只有 HTTP API），而
`POST /api/v1/agents/credentials` 要求「平台身份 ＋ system_operator AI 档」
且需自带 `Authorization: Bearer <access_token>`。access token 15 分钟过期、
登录接口还要求必填 `device_label`——手搓 curl 极易踩坑。本脚本把这三件事
一次做完：登录 → 取 access_token → 写凭据 → 校验回读。

跑法（宿主 Windows，server venv）：

```bash
cd server
PYTHONPATH=src python ../scripts/agents/set-credential.py \
  --username "<你的平台身份账号>" \
  --password "<你的密码>" \
  --credential "<zcode 凭据明文>" \
  --name default
```

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
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8010"
DEFAULT_CREDENTIAL_NAME = "default"
DEFAULT_DEVICE_LABEL = "蔡工FDE智能交付系统 运维脚本"
# 宿主通道下平台凭据零注入 ⇒ 占位串即可过闸（与既有 bootstrap 脚本同款）。
PLACEHOLDER_CREDENTIAL = "host-channel-slot-unused-by-real-adapter"


def _request(
    *,
    base_url: str,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    """调 FDE API；返回 (状态码, 解析后的 JSON)。非 JSON 响应按原始文本塞进 `raw`。"""
    url = f"{base_url.rstrip('/')}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        status = int(error.code)
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
    if status != 200:
        error = payload.get("error") or {}
        raise SystemExit(
            f"登录失败（HTTP {status}）：{error.get('code') or '-'} {error.get('message') or payload}"
        )
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
