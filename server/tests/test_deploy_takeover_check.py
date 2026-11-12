# -*- coding: utf-8 -*-
"""接管检查器测试（教训⑩机械闸化；脚本位于 scripts/deploy/，经 importlib 直载）。

覆盖：键名解析（CRLF/注释/散文剔除）／compose 插值变量四形态／树模式三查
（全绿零值泄漏／缺关键键 FAIL／example 差集 WARN 不拦／缺文件结构错）／
main 退出码 0/1/2／仓库权威钉（example 必载关键键＋事故键钉死在册）／
live 两查（僵尸挂载／容器 env 缺键／注入 runner，Windows-only 路径可注入）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "deploy" / "takeover_check.py"
)
_spec = importlib.util.spec_from_file_location("deploy_takeover_check", _SCRIPT)
assert _spec is not None and _spec.loader is not None
takeover = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("deploy_takeover_check", takeover)
_spec.loader.exec_module(takeover)

_COMPOSE = (
    "services:\n"
    "  api:\n"
    "    environment:\n"
    "      FDE_DATABASE_URL: postgresql+psycopg://fde:${FDE_DB_PASSWORD:?FDE_DB_PASSWORD missing in .env}@db:5432/x\n"
    "      OTHER: ${FDE_OTHER_VAR:-fallback}\n"
    "      THIRD: ${FDE_THIRD_VAR-default}\n"
    "      FOURTH: ${FDE_FOURTH_VAR?required}\n"
)


def _server_env_text() -> str:
    return "".join(f"{k}=value-of-{k}\n" for k in takeover.CRITICAL_SERVER_KEYS)


def _make_tree(
    tmp_path: Path,
    *,
    root_env: str = "FDE_DB_PASSWORD=db-pass\nFDE_OTHER_VAR=x\nFDE_THIRD_VAR=y\nFDE_FOURTH_VAR=z\n",
    server_env: str | None = _server_env_text(),
    example: str | None = "",
) -> Path:
    tree = tmp_path / "tree"
    (tree / "server").mkdir(parents=True)
    (tree / "compose.yaml").write_text(_COMPOSE, encoding="utf-8")
    (tree / ".env").write_text(root_env, encoding="utf-8")
    if server_env is not None:
        (tree / "server" / ".env").write_text(server_env, encoding="utf-8")
    if example is not None:
        (tree / "server" / ".env.example").write_text(example, encoding="utf-8")
    return tree


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


def test_parse_env_names_handles_crlf_comments_and_prose():
    text = (
        "KEY_A=value\r\n"
        "\r\n"
        "# 注释散文一行没有等号\r\n"
        "# KEY_B=commented-documented\r\n"
        "export KEY_C=exported\r\n"
        "# 说明: 这行散文里有等号 but 键名不合法 nope=bar\r\n"
    )
    assert takeover.parse_env_names(text) == ["KEY_A", "KEY_B", "KEY_C"]


def test_compose_var_names_covers_all_forms():
    text = (
        "a: ${V1}\n"
        "b: ${V2:-def}\n"
        "c: ${V3-def}\n"
        "d: ${V4:?missing}\n"
        "e: ${V5?required}\n"
        "f: ${V1}\n"
    )
    assert takeover.compose_var_names(text) == ["V1", "V2", "V3", "V4", "V5"]


# ---------------------------------------------------------------------------
# 树模式
# ---------------------------------------------------------------------------


def test_check_tree_all_green_and_never_leaks_values(tmp_path):
    tree = _make_tree(tmp_path, example="FDE_EXTRA_KEY=\n")
    lines = takeover.check_tree(tree)
    assert not any(line.startswith("[FAIL]") for line in lines)
    assert any(line.startswith("[OK]") for line in lines)
    blob = "\n".join(lines)
    assert "value-of-" not in blob and "db-pass" not in blob  # 键值永不打印


def test_check_tree_missing_critical_key_fails(tmp_path):
    env = _server_env_text().replace("FDE_AGENT_HOST_EGRESS_GATE_ENABLED=value-of-FDE_AGENT_HOST_EGRESS_GATE_ENABLED\n", "")
    tree = _make_tree(tmp_path, server_env=env)
    lines = takeover.check_tree(tree)
    fails = [line for line in lines if line.startswith("[FAIL]")]
    assert any("FDE_AGENT_HOST_EGRESS_GATE_ENABLED" in line for line in fails)


def test_check_tree_example_only_key_warns_but_passes(tmp_path):
    tree = _make_tree(tmp_path, example="# FDE_OPTIONAL_DOCUMENTED=\n")
    lines = takeover.check_tree(tree)
    assert any("[WARN]" in line and "FDE_OPTIONAL_DOCUMENTED" in line for line in lines)
    assert not any(line.startswith("[FAIL]") for line in lines)


def test_check_tree_compose_var_missing_fails(tmp_path):
    tree = _make_tree(tmp_path, root_env="FDE_DB_PASSWORD=x\n")
    lines = takeover.check_tree(tree)
    fails = "\n".join(line for line in lines if line.startswith("[FAIL]"))
    assert "FDE_OTHER_VAR" in fails and "FDE_FOURTH_VAR" in fails


def test_check_tree_missing_files_structural(tmp_path):
    lines = takeover.check_tree(tmp_path / "nowhere")
    assert all(line.startswith("[FAIL] 缺文件") for line in lines)


def test_main_exit_codes(tmp_path):
    tree = _make_tree(tmp_path)
    with mock.patch.object(sys, "argv", ["t", "--tree", str(tree)]):
        assert takeover.main() == 0
    with mock.patch.object(sys, "argv", ["t", "--tree", str(tmp_path / "nowhere")]):
        assert takeover.main() == 2
    bad = _make_tree(tmp_path / "b", server_env="FDE_JWT_SECRET=x\n")
    with mock.patch.object(sys, "argv", ["t", "--tree", str(bad)]):
        assert takeover.main() == 1


# ---------------------------------------------------------------------------
# 仓库权威钉
# ---------------------------------------------------------------------------


def test_critical_keys_documented_in_env_example():
    """权威链自洽：关键键必须全部在 server/.env.example 载名（含注释形态）。"""
    example = (
        Path(__file__).resolve().parents[2] / "server" / ".env.example"
    ).read_text(encoding="utf-8")
    documented = set(takeover.parse_env_names(example))
    for name in takeover.CRITICAL_SERVER_KEYS:
        assert name in documented, f"关键键未在 .env.example 载名: {name}"


def test_incident_keys_pinned_in_critical_list():
    """事故家族三发主角不得从关键键清单 shrink（⑦ 出站闸两键＋模型槽位）。"""
    for name in (
        "FDE_AGENT_HOST_EGRESS_GATE_ENABLED",
        "FDE_AGENT_HOST_EGRESS_ALLOWLIST",
        "FDE_DEEPSEEK_SIMULATION_EVALUATION_MODEL",
    ):
        assert name in takeover.CRITICAL_SERVER_KEYS


# ---------------------------------------------------------------------------
# live 两查（注入 runner，不触真 docker）
# ---------------------------------------------------------------------------


def _fake_runner(mount_source: str | None, env_text: str | None):
    mounts = json.dumps(
        [{"Destination": "/app/migrations", "Source": mount_source or ""}]
        if mount_source is not None
        else []
    )

    def runner(args: list[str]) -> str:
        if args[0] == "inspect":
            return mounts
        if args[0] == "exec":
            assert env_text is not None
            return env_text
        raise AssertionError(args)

    return runner


def test_live_green_when_mount_exists_and_env_full(tmp_path):
    real = tmp_path / "real-tree" / "server" / "migrations"
    real.mkdir(parents=True)
    lines = takeover.run_live_checks(
        "fde-workbench",
        "Ubuntu-24.04",
        _fake_runner(str(real), _server_env_text()),
    )
    assert not any(line.startswith("[FAIL]") for line in lines)
    assert any("[OK] migrations 挂载源在场" in line for line in lines)


def test_live_zombie_mount_detected(tmp_path):
    ghost = str(tmp_path / "deleted-tree" / "migrations")  # 不创建＝已删树
    lines = takeover.run_live_checks(
        "fde-workbench", "Ubuntu-24.04", _fake_runner(ghost, _server_env_text())
    )
    assert any("[FAIL] migrations 挂载源已不存在（僵尸挂载）" in line for line in lines)


def test_live_container_env_missing_key_fails(tmp_path):
    real = tmp_path / "t2" / "migrations"
    real.mkdir(parents=True)
    env_text = _server_env_text().replace("FDE_DEEPSEEK_SIMULATION_EVALUATION_MODEL=value-of-FDE_DEEPSEEK_SIMULATION_EVALUATION_MODEL\n", "")
    lines = takeover.run_live_checks(
        "fde-workbench", "Ubuntu-24.04", _fake_runner(str(real), env_text)
    )
    assert any("容器 env 缺关键键: FDE_DEEPSEEK_SIMULATION_EVALUATION_MODEL" in line for line in lines)


def test_live_api_container_unreachable_fails():
    def dead_runner(args: list[str]) -> str:
        raise RuntimeError("docker 命令失败（exit=1）: inspect")

    lines = takeover.run_live_checks("fde-workbench", "Ubuntu-24.04", dead_runner)
    assert any("[FAIL] live 检查不可用（api 容器 fde-workbench-api-1 无法检视）" in line for line in lines)


# ---------------------------------------------------------------------------
# 命令装配（Windows-only 路径显式传 platform，CI 可跑）
# ---------------------------------------------------------------------------


def test_build_docker_cmd_platform_injected():
    assert takeover.build_docker_cmd("Ubuntu-24.04", ["ps"], platform="win32") == [
        "wsl",
        "-d",
        "Ubuntu-24.04",
        "--",
        "docker",
        "ps",
    ]
    assert takeover.build_docker_cmd("Ubuntu-24.04", ["ps"], platform="linux") == [
        "docker",
        "ps",
    ]


def test_wsl_path_to_windows_translation():
    assert (
        takeover.wsl_path_to_windows("/mnt/d/test/tree/server/migrations", platform="win32")
        == "D:\\test\\tree\\server\\migrations"
    )
    # 非 /mnt 形态与非 Windows 平台原样返回
    assert takeover.wsl_path_to_windows("/var/lib/docker/x", platform="win32") == "/var/lib/docker/x"
    assert (
        takeover.wsl_path_to_windows("/mnt/d/test/tree", platform="linux")
        == "/mnt/d/test/tree"
    )


def test_live_mount_check_uses_translated_host_path():
    """Windows 宿主上挂载源须翻译后再查存在性（实弹冒烟抓到的盲区钉）。"""
    seen: list[str] = []

    def capturing_exists(path: str) -> bool:
        seen.append(path)
        return True

    lines = takeover.run_live_checks(
        "fde-workbench",
        "Ubuntu-24.04",
        _fake_runner("/mnt/d/deploy-tree/server/migrations", _server_env_text()),
        mount_exists=capturing_exists,
        platform="win32",
    )
    assert not any(line.startswith("[FAIL]") for line in lines)
    assert seen == ["D:\\deploy-tree\\server\\migrations"]
