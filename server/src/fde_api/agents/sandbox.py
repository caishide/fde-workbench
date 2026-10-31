"""沙箱基座（goal-d3，技术实施方案 §4 / 决议 D4）。

四条硬边界（V2 契约，tests/test_sandbox_isolation.py 逐条锁定）：

1. 宿主机无凭据明文——Fernet 解密只发生在注入时刻，值经进程环境（内存管道）
   传给 docker exec，argv/磁盘/日志零明文（``redact`` 供日志路径兜底）。
2. 只挂 run workspace——每 run 恰好一个 bind mount，映射到容器内
   /workspace；真相层（``D:\test\FDE\…``）与 ``.env`` 一律拒绝。
3. egress deny——默认 ``--network none``；allowlist 档需要 per-run 网络 +
   iptables 白名单与真实 daemon 联调，归 goal-d4，此处显式拒绝而非静默放通。
4. 销毁回收——kill 后容器销毁，tmpfs 随之回收；销毁后的句柄拒绝一切操作。

后端可注入（CI/Windows 宿主无 docker daemon 也能测全参数事实）：生产用
``DockerBackend``（docker CLI），测试用捕获 argv/env 的假后端。沙箱拉起失败
属自动交付 §3.2 异常 A 类：调用方（d4）不发起 run，走 L2 模板填空，零计费。
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

# 拒挂标记（红线：真相层与密钥文件永不进沙箱）。大小写不敏感子串匹配，
# 覆盖 Windows 盘符两种分隔符写法；技术文档 §4 同款口径。
FORBIDDEN_MOUNT_MARKERS: tuple[str, ...] = (
    ".env",
    "d:\\test\\fde",
    "d:/test/fde",
    "fdeops",
    "openfde",
)

WORKSPACE_MOUNT_POINT = "/workspace"


class SandboxError(RuntimeError):
    """沙箱基座错误（异常 A 类：不发起 run，降级 L2 零计费）。"""


@dataclass(frozen=True)
class SandboxProfile:
    """单 run 资源基线；默认值与 Settings.sandbox_* / compose 基线一致。"""

    name: str = "default"
    memory: str = "512m"
    cpus: str = "1.0"
    pids_limit: int = 128
    timeout_seconds: int = 300
    tmpfs_size: str = "512m"
    # deny = --network none（唯一已实装档）；allowlist 归 d4
    egress: str = "deny"


DEFAULT_SANDBOX_PROFILE = SandboxProfile()


class SandboxBackend(Protocol):
    """docker CLI 可注入后端：argv 是完整 docker 子命令（不含 docker 本身）。"""

    def run(self, argv: Sequence[str], *, env: Mapping[str, str] | None = None) -> None: ...


@dataclass
class DockerBackend:
    """生产后端：经 docker CLI 拉起/回收 per-run 容器。

    env 只为凭据注入而透传（内存管道）；不传时继承当前进程环境。
    """

    docker_bin: str = "docker"

    def run(self, argv: Sequence[str], *, env: Mapping[str, str] | None = None) -> None:
        merged = dict(os.environ) if env is None else dict(env)
        try:
            completed = subprocess.run(
                [self.docker_bin, *argv],
                check=True,
                capture_output=True,
                env=merged,
            )
        except FileNotFoundError as error:
            raise SandboxError("sandbox_runtime_missing") from error
        except subprocess.CalledProcessError as error:
            # stderr 可能含宿主路径，按 redact 纪律不外抛原文
            raise SandboxError("sandbox_command_failed") from error
        _ = completed


class SandboxHandle:
    """一次 agent run 的沙箱句柄：create → (inject/exec) → kill。"""

    def __init__(
        self,
        *,
        run_id: str,
        profile: SandboxProfile,
        workspace_host: str,
        image: str,
        backend: SandboxBackend,
    ) -> None:
        if profile.egress != "deny":
            # 显式拒绝而非静默放通：allowlist 需 per-run 网络 + iptables（d4）
            raise SandboxError("egress_allowlist_not_available")
        _assert_mountable_workspace(workspace_host)
        self.run_id = run_id
        self.profile = profile
        self.workspace_host = workspace_host
        self.image = image
        self._backend = backend
        self.container_name = f"agent-run-{run_id}"
        self.destroyed = False

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        profile: SandboxProfile = DEFAULT_SANDBOX_PROFILE,
        workspace_host: str,
        image: str = "fde-sandbox-runner:latest",
        backend: SandboxBackend,
    ) -> "SandboxHandle":
        """拉起 per-run 容器（--name agent-run-{run_id}，断网 + 资源上限）。"""
        handle = cls(
            run_id=run_id,
            profile=profile,
            workspace_host=workspace_host,
            image=image,
            backend=backend,
        )
        backend.run(
            [
                "run",
                "-d",
                "--name",
                handle.container_name,
                # V2-③ egress deny：默认断网是基线事实，不是可配置项
                "--network",
                "none",
                "--memory",
                profile.memory,
                "--cpus",
                profile.cpus,
                "--pids-limit",
                str(profile.pids_limit),
                # V2-④ 销毁回收：tmpfs 是一次性的，容器销毁即回收
                "--tmpfs",
                f"{WORKSPACE_MOUNT_POINT}:size={profile.tmpfs_size}",
                # V2-② 只挂 run workspace：恰好一个 bind mount
                "-v",
                f"{handle.workspace_host}:{WORKSPACE_MOUNT_POINT}:rw",
                image,
                "sleep",
                "infinity",
            ]
        )
        return handle

    def exec_argv(
        self, credentials: Mapping[str, str], command: Sequence[str]
    ) -> tuple[list[str], dict[str, str]]:
        """构造凭据注入的 exec 调用：argv 只含变量名，值走 env（内存管道）。

        返回 (argv, env)：argv 形如 ``exec -i -e NAME … <container> <command>``，
        env 是应传给后端的完整进程环境（含凭据明文——仅存在于内存映射）。
        日志路径一律走 :meth:`redact`，绝不序列化这里的 env。
        """
        if self.destroyed:
            raise SandboxError("sandbox_destroyed")
        argv: list[str] = ["exec", "-i"]
        for name in credentials:
            _assert_env_name(name)
            argv.extend(["-e", name])
        argv.append(self.container_name)
        argv.extend(command)
        return argv, dict(credentials)

    def redact(self, text: str, credentials: Mapping[str, str]) -> str:
        """日志兜底：把任何凭据值替换为 ***（V2-① 的纵深防御半边）。"""
        for value in credentials.values():
            if value:
                text = text.replace(value, "***")
        return text

    def kill(self) -> None:
        """销毁容器并回收 tmpfs（V2-④）；幂等——重复 kill 是无害操作。"""
        if self.destroyed:
            return
        self._backend.run(["rm", "-f", self.container_name])
        self.destroyed = True


def _assert_mountable_workspace(workspace_host: str) -> None:
    lowered = workspace_host.lower()
    for marker in FORBIDDEN_MOUNT_MARKERS:
        if marker in lowered:
            raise SandboxError("workspace_mount_forbidden")


def _assert_env_name(name: str) -> None:
    if not name or any(character not in _ENV_NAME_ALPHABET for character in name):
        raise SandboxError("invalid_credential_name")


_ENV_NAME_ALPHABET = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
)
