"""WP28/I4：worker / scheduler 的存活心跳（compose healthcheck 的判据来源）。

缺陷基线：worker 与 scheduler 是无端口 CLI 循环，容器层面只能知道「进程还在」，
看不见「循环卡死」——任务永远停在 pending 而 docker 仍报 Up。compose 因此
没法给这两个服务配上有意义的 healthcheck。

本套件钉住心跳语义：写入 → 新鲜则健康；无心跳 / 过期 → 不健康；Redis 不可用
→ 不健康（依赖断了不该算健康）。
"""

import pytest
from redis.exceptions import RedisError

from fde_api.health import heartbeat as heartbeat_module
from fde_api.health.heartbeat import (
    SCHEDULER_HEARTBEAT_TTL_SECONDS,
    WORKER_HEARTBEAT_TTL_SECONDS,
    beat,
    check,
    heartbeat_key,
)


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, tuple[str, int | None]] = {}
        self.ttls: list[tuple[str, int | None]] = []

    def set(self, key, value, ex=None):
        self.store[key] = (value, ex)
        self.ttls.append((key, ex))

    def get(self, key):
        entry = self.store.get(key)
        return None if entry is None else entry[0]


class _BrokenRedis:
    def set(self, *args, **kwargs):
        raise RedisError("connection refused")

    def get(self, *args, **kwargs):
        raise RedisError("connection refused")


@pytest.fixture
def fake_redis(monkeypatch):
    """替换心跳模块的连接解析（不碰真实 Redis）。"""
    fake = _FakeRedis()
    monkeypatch.setattr(heartbeat_module, "_redis_connection", lambda: fake)
    return fake


@pytest.fixture
def broken_redis(monkeypatch):
    monkeypatch.setattr(
        heartbeat_module, "_redis_connection", lambda: _BrokenRedis()
    )
    return _BrokenRedis()


@pytest.mark.parametrize(
    ("name", "expected_ttl"),
    [
        ("worker", WORKER_HEARTBEAT_TTL_SECONDS),
        ("scheduler", SCHEDULER_HEARTBEAT_TTL_SECONDS),
    ],
)
def test_beat_writes_heartbeat_with_ttl(fake_redis, name, expected_ttl):
    assert beat(name) is True
    assert heartbeat_key(name) in fake_redis.store
    assert fake_redis.ttls == [(heartbeat_key(name), expected_ttl)]


def test_check_reports_healthy_after_beat(fake_redis):
    beat("worker")

    healthy, detail = check("worker")

    assert healthy is True
    assert "heartbeat age" in detail


def test_check_reports_unhealthy_without_heartbeat(fake_redis):
    """没有心跳键 = 循环从未跑过或已卡死超时 → 不健康。"""
    healthy, detail = check("worker")

    assert healthy is False
    assert "no heartbeat key" in detail


def test_check_reports_unhealthy_when_heartbeat_is_stale(fake_redis):
    """心跳时间戳过期（循环卡住不再刷新）→ 不健康。"""
    fake_redis.store[heartbeat_key("worker")] = ("1", None)

    healthy, detail = check("worker")

    assert healthy is False
    assert "stale" in detail


def test_check_reports_unhealthy_when_redis_unavailable(broken_redis):
    """Redis 不可用 → 不健康（依赖断了不算健康），且不抛异常。"""
    healthy, detail = check("worker")

    assert healthy is False
    assert "redis unavailable" in detail


def test_beat_survives_redis_outage(broken_redis):
    """Redis 挂掉时心跳写入失败但不得打断 worker/scheduler 循环。"""
    assert beat("worker") is False


def test_unknown_heartbeat_name_rejected(fake_redis):
    with pytest.raises(ValueError):
        beat("not-a-service")
    with pytest.raises(ValueError):
        check("not-a-service")
