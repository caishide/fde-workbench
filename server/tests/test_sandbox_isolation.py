"""V2 沙箱隔离四断言（goal-d3，技术实施方案 §4 / §9）。

V2 判定 = egress deny / 只挂 run workspace / 凭据不落宿主明文 / 销毁回收。
docker daemon 不可入 CI，全部断言落在可注入后端的 argv/env 事实与 compose
基线文本上（§10 纪律：Windows-only 路径必须可注入/可 mock）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fde_api.agents.sandbox import (
    DEFAULT_SANDBOX_PROFILE,
    DockerBackend,
    SandboxError,
    SandboxHandle,
    SandboxProfile,
)

SERVER_ROOT = Path(__file__).resolve().parents[1]


class RecordingBackend:
    """捕获每次调用的 argv 与 env——测试据此断言 docker 参数事实。"""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, str] | None]] = []

    def run(self, argv, *, env=None) -> None:
        self.calls.append((list(argv), dict(env) if env is not None else None))

    @property
    def argvs(self) -> list[list[str]]:
        return [argv for argv, _ in self.calls]


def _create_handle(backend: RecordingBackend, *, workspace: str = "/tmp/ws/run-1"):
    return SandboxHandle.create(
        run_id="run-v2-1",
        profile=DEFAULT_SANDBOX_PROFILE,
        workspace_host=workspace,
        backend=backend,
    )


def test_v2_credentials_never_reach_argv_or_disk() -> None:
    """V2-① 宿主机无凭据明文：值只在 env 内存映射里，argv/日志零明文。"""
    recording = RecordingBackend()
    handle = _create_handle(recording)
    credentials = {"ZCODE_API_KEY": "super-secret-value-123", "OTHER": "tick-value"}
    argv, env = handle.exec_argv(credentials, ["zcode", "--task", "build"])

    # argv 只含变量名（-e NAME），值绝不进 argv（shell 历史/ps 可见层）
    joined = " ".join(argv)
    assert "-e" in argv and "ZCODE_API_KEY" in argv
    for value in credentials.values():
        assert value not in joined
    # 值只经 env 内存管道传给后端
    assert env["ZCODE_API_KEY"] == "super-secret-value-123"
    # create 阶段（docker run）完全不带凭据
    for past_argv in recording.argvs:
        assert "super-secret-value-123" not in " ".join(past_argv)
    # 纵深防御：日志兜底 redact 把值替换为 ***
    leaked = "error near super-secret-value-123 and tick-value"
    assert handle.redact(leaked, credentials) == "error near *** and ***"


def test_v2_mounts_only_run_workspace() -> None:
    """V2-② 只挂 run workspace：恰好一个 bind mount，真相层/.env 拒绝。"""
    recording = RecordingBackend()
    _create_handle(recording, workspace="/home/fde/sandbox-workspaces/run-v2-2")
    run_argv = recording.argvs[0]
    mounts = [
        run_argv[index + 1] for index, part in enumerate(run_argv) if part == "-v"
    ]
    assert mounts == ["/home/fde/sandbox-workspaces/run-v2-2:/workspace:rw"]
    # 除此之外无任何挂载面（无 --mount、无其他 -v）
    assert "--mount" not in run_argv
    assert len(mounts) == 1
    # 真相层与密钥文件路径在构造期即拒绝
    for forbidden in (
        "D:\\test\\FDE\\engagements\\somwyn\\.fde",
        "/srv/fdeops/workdir",
        "/app/server/.env",
    ):
        with pytest.raises(SandboxError, match="workspace_mount_forbidden"):
            SandboxHandle.create(
                run_id="run-forbidden",
                workspace_host=forbidden,
                backend=RecordingBackend(),
            )


def test_v2_egress_denied_by_default_and_compose_baseline() -> None:
    """V2-③ egress deny：run 参数 --network none；compose 基线断网 + 无端口。"""
    recording = RecordingBackend()
    _create_handle(recording)
    run_argv = recording.argvs[0]
    assert run_argv[run_argv.index("--network") + 1] == "none"
    # 资源上限随 create 强制（§4：CPU/内存/pids 由 docker resource flags 强制）
    assert run_argv[run_argv.index("--memory") + 1] == DEFAULT_SANDBOX_PROFILE.memory
    assert run_argv[run_argv.index("--cpus") + 1] == DEFAULT_SANDBOX_PROFILE.cpus
    assert run_argv[run_argv.index("--pids-limit") + 1] == str(
        DEFAULT_SANDBOX_PROFILE.pids_limit
    )
    assert run_argv[run_argv.index("--tmpfs") + 1] == "/workspace:size=512m"
    # allowlist 档未实装：显式拒绝而非静默放通（d4 随适配器落地）
    with pytest.raises(SandboxError, match="egress_allowlist_not_available"):
        SandboxHandle.create(
            run_id="run-egress",
            profile=SandboxProfile(egress="allowlist"),
            workspace_host="/tmp/ws",
            backend=RecordingBackend(),
        )

    # compose 基线（文本切片，不引入 pyyaml 依赖）
    compose = (SERVER_ROOT.parent / "compose.yaml").read_text(encoding="utf-8")
    start = compose.index("  sandbox-runner:")
    end = len(compose)
    for marker in ("\nnetworks:", "\nvolumes:", "\n  worker:", "\n  api:"):
        position = compose.find(marker, start)
        if position != -1:
            end = min(end, position)
    section = compose[start:end]
    assert "build: ./docker/sandbox" in section
    assert "privileged: false" in section
    assert "network_mode: none" in section
    assert "- /workspace:size=512m" in section
    assert "profiles:" in section and "sandbox" in section
    # 断网基座不得发布任何端口
    assert "ports:" not in section


def test_v2_destroy_reclaims_container_and_workspace() -> None:
    """V2-④ 销毁回收：kill 后 rm -f，tmpfs 随容器回收；销毁后拒绝操作。"""
    recording = RecordingBackend()
    handle = _create_handle(recording)
    # 容器命名口径：--name agent-run-{run_id}
    assert f"--name agent-run-{handle.run_id}" in " ".join(recording.argvs[0])
    assert not handle.destroyed

    handle.kill()
    assert recording.argvs[-1] == ["rm", "-f", "agent-run-run-v2-1"]
    assert handle.destroyed
    # 幂等：重复 kill 不再发命令
    handle.kill()
    assert len(recording.argvs) == 2
    # 销毁后的句柄拒绝一切操作
    with pytest.raises(SandboxError, match="sandbox_destroyed"):
        handle.exec_argv({"KEY": "value"}, ["any"])


def test_docker_backend_wraps_cli_failures_without_leaking_stderr() -> None:
    """生产后端：CLI 缺失/失败归一为 A 类异常，stderr 原文不外抛（redact 纪律）。"""
    backend = DockerBackend(docker_bin="fdefinitely-not-docker")
    with pytest.raises(SandboxError, match="sandbox_runtime_missing"):
        backend.run(["ps"])
    # 存在但非零退出的命令 → sandbox_command_failed（跨平台用解释器自身）
    import sys

    failing = DockerBackend(docker_bin=sys.executable)
    with pytest.raises(SandboxError, match="sandbox_command_failed"):
        failing.run(["-c", "import sys; sys.exit(3)"])
