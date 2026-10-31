"""沙箱基座（goal-d3，技术实施方案 §4 / 决议 D4）。

四条硬边界（V2 契约，tests/test_sandbox_isolation.py 逐条锁定）：

1. 宿主机无凭据明文——Fernet 解密只发生在注入时刻，值经进程环境（内存管道）
   传给 docker exec，argv/磁盘/日志零明文（``redact`` 供日志路径兜底）。
2. 只挂 run workspace——每 run 恰好一个 bind mount，映射到容器内
   /workspace；真相层（``D:\\test\\FDE\\…``）与 ``.env`` 一律拒绝。
3. egress——默认 ``--network none``（deny 基线）；allowlist 档（goal-d4 实装）
   由 ``EgressPlan`` 建 per-run 网络 + iptables 白名单（白名单 CIDR 逐条
   ACCEPT 置顶 + 本子网 REJECT 兜底，kill 时逆序回收）。argv 事实层经可注入
   后端在 CI 断言；真实 iptables 生效性归 d6 试点联调（人工项）。
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
from hashlib import sha256
from ipaddress import ip_network
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
    # deny = --network none（默认基线）；allowlist = EgressPlan per-run 网络
    egress: str = "deny"


DEFAULT_SANDBOX_PROFILE = SandboxProfile()

# per-run egress 网络的子网基座（前两段）；第三段由 run_id 哈希确定性派生，
# 避免并发 run 抢同一子网。私有段 172.31.0.0/16 属 docker 默认池之外带。
EGRESS_SUBNET_BASE = "172.31"


def derive_run_subnet(run_id: str, *, base: str = EGRESS_SUBNET_BASE) -> str:
    """run_id → 确定性 /24 子网（同 run 重复规划得到同一子网，便于审计）。"""
    digest = sha256(run_id.encode("utf-8")).hexdigest()
    return f"{base}.{int(digest[:8], 16) % 256}.0/24"


def _iptables_argv(
    image: str, flag: str, subnet: str, cidr: str | None, target: str
) -> list[str]:
    """iptables 事实经一次性助手容器在宿主 netns 执行（需 NET_ADMIN）。"""
    argv = [
        "run",
        "--rm",
        "--net",
        "host",
        "--cap-add",
        "NET_ADMIN",
        image,
        "iptables",
        flag,
        "FORWARD",
        "-s",
        subnet,
    ]
    if cidr is not None:
        argv.extend(["-d", cidr])
    argv.extend(["-j", target])
    return argv


@dataclass(frozen=True)
class EgressPlan:
    """allowlist 档的 per-run 网络与 iptables 白名单计划（技术文档 §4）。

    白名单 CIDR 逐条 ACCEPT（``-I`` 置顶）+ 本 run 子网兜底 REJECT
    （``-A`` 追加，只作用于本子网，不碰宿主其他转发规则）；teardown 逆序
    删除。执行依赖 sandbox 镜像内有 iptables（docker/sandbox 已安装）。
    """

    run_id: str
    subnet: str
    allow_cidrs: tuple[str, ...]

    @property
    def network_name(self) -> str:
        return f"agent-egress-{self.run_id}"

    def provisioning_argv(self, image: str) -> list[list[str]]:
        plan = [
            [
                "network",
                "create",
                "--driver",
                "bridge",
                "--subnet",
                self.subnet,
                self.network_name,
            ]
        ]
        for cidr in self.allow_cidrs:
            plan.append(_iptables_argv(image, "-I", self.subnet, cidr, "ACCEPT"))
        plan.append(_iptables_argv(image, "-A", self.subnet, None, "REJECT"))
        return plan

    def teardown_argv(self, image: str) -> list[list[str]]:
        """严格逆序：REJECT 先撤 → ACCEPT 逆序撤 → 网络 removal。"""
        plan = [_iptables_argv(image, "-D", self.subnet, None, "REJECT")]
        plan.extend(
            _iptables_argv(image, "-D", self.subnet, cidr, "ACCEPT")
            for cidr in reversed(self.allow_cidrs)
        )
        plan.append(["network", "rm", self.network_name])
        return plan


def _parse_egress_allowlist(allowlist: Sequence[str]) -> tuple[str, ...]:
    """逗号/序列输入 → 规范化 IPv4 CIDR 元组；空表或非法段一律拒绝。"""
    cidrs: list[str] = []
    for item in allowlist:
        value = item.strip()
        if not value:
            continue
        try:
            network = ip_network(value, strict=False)
        except ValueError as error:
            raise SandboxError("egress_allowlist_invalid") from error
        if network.version != 4:
            raise SandboxError("egress_allowlist_invalid")
        cidrs.append(str(network))
    if not cidrs:
        raise SandboxError("egress_allowlist_empty")
    return tuple(cidrs)


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
        egress_plan: EgressPlan | None = None,
    ) -> None:
        _assert_mountable_workspace(workspace_host)
        self.run_id = run_id
        self.profile = profile
        self.workspace_host = workspace_host
        self.image = image
        self._backend = backend
        self.container_name = f"agent-run-{run_id}"
        self.egress_plan = egress_plan
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
        egress_allowlist: Sequence[str] = (),
    ) -> "SandboxHandle":
        """拉起 per-run 容器（--name agent-run-{run_id}，资源上限强制）。

        egress=deny → ``--network none``（基线，allowlist 参数必须为空）；
        egress=allowlist → 先经 ``EgressPlan`` 建 per-run 网络 + iptables
        白名单，容器挂到该网络；其他档显式拒绝，绝不静默放通。
        """
        plan: EgressPlan | None
        if profile.egress == "allowlist":
            plan = EgressPlan(
                run_id=run_id,
                subnet=derive_run_subnet(run_id),
                allow_cidrs=_parse_egress_allowlist(egress_allowlist),
            )
        elif profile.egress == "deny":
            if egress_allowlist:
                # deny 档带白名单是配置矛盾——拒绝而非静默忽略
                raise SandboxError("egress_allowlist_conflicts_deny")
            plan = None
        else:
            raise SandboxError("sandbox_profile_egress_unknown")
        handle = cls(
            run_id=run_id,
            profile=profile,
            workspace_host=workspace_host,
            image=image,
            backend=backend,
            egress_plan=plan,
        )
        if plan is not None:
            for argv in plan.provisioning_argv(image):
                backend.run(argv)
        backend.run(
            [
                "run",
                "-d",
                "--name",
                handle.container_name,
                # V2-③：deny 基线断网；allowlist 挂 per-run 白名单网络
                "--network",
                plan.network_name if plan is not None else "none",
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

    def exec(self, credentials: Mapping[str, str], command: Sequence[str]) -> None:
        """注入凭据执行容器内命令（d4 适配器 spawn 段的落地点）。"""
        argv, credential_env = self.exec_argv(credentials, command)
        merged = {**os.environ, **credential_env}
        self._backend.run(argv, env=merged)

    def redact(self, text: str, credentials: Mapping[str, str]) -> str:
        """日志兜底：把任何凭据值替换为 ***（V2-① 的纵深防御半边）。"""
        for value in credentials.values():
            if value:
                text = text.replace(value, "***")
        return text

    def kill(self) -> None:
        """销毁容器并回收 tmpfs/egress 网络（V2-④）；幂等——重复 kill 无害。"""
        if self.destroyed:
            return
        self._backend.run(["rm", "-f", self.container_name])
        if self.egress_plan is not None:
            for argv in self.egress_plan.teardown_argv(self.image):
                self._backend.run(argv)
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
