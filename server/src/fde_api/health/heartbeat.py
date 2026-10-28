"""worker / scheduler 的存活心跳（WP28/I4）。

为什么需要：worker 与 scheduler 都是不起 HTTP 端口的 CLI 循环（`flask worker`
/ `flask scheduler`）。容器层面只能知道「进程还在」，看不见「循环卡死」——
此时任务永远停在 pending，而 docker 仍报 Up。本模块让两个循环各写一个带 TTL
的 Redis 心跳键，healthcheck 据此判定容器是否真的在干活。

键约定：`fde:health:<name>`（name ∈ {worker, scheduler}），TTL 内会被循环刷新；
循环一旦卡住，键自然过期 → healthcheck 失败 → 容器标记 unhealthy。

用法（容器内 healthcheck）：
    python -m fde_api.health.heartbeat worker
    python -m fde_api.health.heartbeat scheduler
退出码 0 = 心跳新鲜；1 = 心跳缺失或过期；2 = Redis 不可用（判为不健康——
依赖断了就不该算健康）。
"""

from __future__ import annotations

import os
import sys
import time

from flask import current_app, has_app_context
from redis import Redis
from redis.exceptions import RedisError

# 心跳 TTL：worker 循环空转时每 ~5s 一轮，scheduler 默认 30s 一轮（上限 300s），
# TTL 取两个循环间隔的数倍余量，既不误报也不迟报。
WORKER_HEARTBEAT_TTL_SECONDS = 180
SCHEDULER_HEARTBEAT_TTL_SECONDS = 900
KNOWN_NAMES = ("worker", "scheduler")


def heartbeat_key(name: str) -> str:
    return f"fde:health:{name}"


def _redis_connection() -> Redis:
    """app 上下文内用扩展里的客户端；CLI（healthcheck）用环境变量自建连接。"""
    if has_app_context():
        return current_app.extensions["fde_api_redis"]
    url = os.environ.get("FDE_REDIS_URL", "").strip()
    if not url:
        raise RedisError("FDE_REDIS_URL is not set (heartbeat probe needs it)")
    return Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)


def beat(name: str) -> bool:
    """写一次心跳；返回是否写成功（Redis 不可用时 False，不抛异常打断循环）。"""
    if name not in KNOWN_NAMES:
        raise ValueError(f"unknown heartbeat name: {name}")
    ttl = (
        WORKER_HEARTBEAT_TTL_SECONDS
        if name == "worker"
        else SCHEDULER_HEARTBEAT_TTL_SECONDS
    )
    try:
        _redis_connection().set(heartbeat_key(name), str(int(time.time())), ex=ttl)
        return True
    except RedisError:
        return False


def check(name: str) -> tuple[bool, str]:
    """检查心跳是否新鲜；返回 (是否健康, 说明)。"""
    if name not in KNOWN_NAMES:
        raise ValueError(f"unknown heartbeat name: {name}")
    try:
        raw = _redis_connection().get(heartbeat_key(name))
    except RedisError as error:
        return False, f"redis unavailable: {error}"
    if raw is None:
        return False, f"no heartbeat key {heartbeat_key(name)}"
    try:
        payload = raw.decode() if isinstance(raw, bytes) else str(raw)
        age = int(time.time()) - int(payload)
    except (TypeError, ValueError):
        return False, "heartbeat value is not a timestamp"
    ttl = (
        WORKER_HEARTBEAT_TTL_SECONDS
        if name == "worker"
        else SCHEDULER_HEARTBEAT_TTL_SECONDS
    )
    if age > ttl:
        return False, f"heartbeat stale: {age}s > {ttl}s"
    return True, f"heartbeat age {age}s"


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1 or args[0] not in KNOWN_NAMES:
        print(f"usage: python -m fde_api.health.heartbeat {{{'|'.join(KNOWN_NAMES)}}}")
        return 2
    healthy, detail = check(args[0])
    print(("OK " if healthy else "FAIL ") + detail)
    return 0 if healthy else 1


if __name__ == "__main__":
    # CLI 模式下没有 Flask app 上下文，直接用 Settings 建连接。
    raise SystemExit(main())
