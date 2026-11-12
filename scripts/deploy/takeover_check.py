# -*- coding: utf-8 -*-
"""接管部署树检查器（教训⑩机械闸化，2026-11-13）。

背景＝env 键静默丢失事故家族三发（2026-11-12：T-15→n6impl→n4n5）：部署配置不进
VCS，每次换树接管都得从上一棵树拷 `.env`；拷错来源 ⇒ 关键键静默丢失（⑦ 出站闸两键、
模型槽位键……），活体照跑直到功能面才炸。本脚本把「接管前必 diff 前任键名集」变成
机械闸——**只读键名，永不打印键值**。

用法::

    python scripts/deploy/takeover_check.py --tree <部署树根> [--live]
                                            [--wsl-distro Ubuntu-24.04]
                                            [--project fde-workbench]

树模式（总是执行）：
  1. 根 `.env` 含 compose.yaml 全部 ``${VAR}`` 插值变量（含 ``:?err``/``:-def`` 形态）；
  2. `server/.env` 含全部关键键（CRITICAL_SERVER_KEYS）；
  3. `server/.env.example` 有而 `server/.env` 无的键 → WARN（建议核对，不拦）。

live 模式（--live，接管前对现役栈执行）：
  4. api 容器 migrations 挂载源在宿主磁盘上存在（僵尸挂载——部署树已删的隐蔽态）；
  5. api 容器 env 含全部关键键。

退出码：0＝全过；1＝有 FAIL；2＝用法/结构错误（缺文件、--tree 不是目录）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# 接管时 server/.env 必须在场的关键键（键名不是秘密；值永不打印）。
# 前三键＝AI 端点与鉴权根；后三键＝事故家族三发的主角（⑦ 出站闸两键＋训练场模型槽位）。
CRITICAL_SERVER_KEYS: tuple[str, ...] = (
    "FDE_JWT_SECRET",
    "FDE_DEEPSEEK_API_KEY",
    "FDE_DEEPSEEK_BASE_URL",
    "FDE_AGENT_HOST_EGRESS_GATE_ENABLED",
    "FDE_AGENT_HOST_EGRESS_ALLOWLIST",
    "FDE_DEEPSEEK_SIMULATION_EVALUATION_MODEL",
)

MIGRATIONS_MOUNT_DEST = "/app/migrations"

_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# ${VAR} / ${VAR:-def} / ${VAR-def} / ${VAR:?err} / ${VAR?err}
_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:[:?-][^}]*)?\}")


def parse_env_names(text: str) -> list[str]:
    """提取 env 文件的键名（含 `# KEY=` 注释形态——被注释的键名同样是要交接的名字）。

    值一律不返回；散文注释行（无 ``=`` 或提取名不似键名）自然剔除。
    """
    names: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            line = line[1:].strip()
            if "=" not in line:
                continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        name = line.split("=", 1)[0].strip()
        if name and _NAME_RE.match(name):
            names.append(name)
    return names


def compose_var_names(text: str) -> list[str]:
    """提取 compose 文件引用的全部 ``${VAR}`` 插值变量名（去重排序）。"""
    return sorted(set(_VAR_RE.findall(text)))


def check_tree(tree: Path) -> list[str]:
    """树模式三查。返回报告行（前缀 FAIL/WARN/OK）；有 FAIL 即接管前必须补齐。"""
    lines: list[str] = []

    root_env = tree / ".env"
    server_env = tree / "server" / ".env"
    compose = tree / "compose.yaml"
    example = tree / "server" / ".env.example"

    for path in (root_env, server_env, compose):
        if not path.is_file():
            lines.append(f"[FAIL] 缺文件: {path}")
    if lines:
        return lines

    var_names = compose_var_names(compose.read_text(encoding="utf-8", errors="replace"))
    root_keys = set(parse_env_names(root_env.read_text(encoding="utf-8", errors="replace")))
    missing_vars = [v for v in var_names if v not in root_keys]
    for name in missing_vars:
        lines.append(f"[FAIL] 根 .env 缺 compose 插值变量: {name}")

    server_keys = set(parse_env_names(server_env.read_text(encoding="utf-8", errors="replace")))
    for name in CRITICAL_SERVER_KEYS:
        if name not in server_keys:
            lines.append(f"[FAIL] server/.env 缺关键键: {name}")

    if example.is_file():
        example_names = parse_env_names(example.read_text(encoding="utf-8", errors="replace"))
        for name in example_names:
            if name not in server_keys:
                lines.append(f"[WARN] server/.env.example 有而 server/.env 无（建议核对）: {name}")

    if not any(line.startswith("[FAIL]") for line in lines):
        lines.append(
            f"[OK] 树检查通过：compose 插值 {len(var_names)} 变量＋关键键 "
            f"{len(CRITICAL_SERVER_KEYS)} 全在位（键值未读取）"
        )
    return lines


def build_docker_cmd(distro: str, docker_args: list[str], *, platform: str = sys.platform) -> list[str]:
    """docker 命令行装配：Windows 宿主经 wsl 发行版，其余平台直连 docker。"""
    if platform == "win32":
        return ["wsl", "-d", distro, "--", "docker", *docker_args]
    return ["docker", *docker_args]


def default_runner(distro: str, docker_args: list[str]) -> str:
    """默认执行器：跑 docker 命令并返回 stdout（失败抛 RuntimeError）。

    ``errors="replace"``：wsl 会往输出混入控制台本地编码的告警字节
    （NAT 代理提示），严格 UTF-8 解码会直接炸掉整个检查。
    """
    cmd = build_docker_cmd(distro, docker_args)
    proc = subprocess.run(
        cmd, capture_output=True, text=True, errors="replace", check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"docker 命令失败（exit={proc.returncode}）: {' '.join(docker_args)}"
        )
    return proc.stdout


def wsl_path_to_windows(path: str, *, platform: str = sys.platform) -> str:
    """WSL 侧挂载源路径 → Windows 宿主路径（``/mnt/c/x`` → ``C:\\x``）。

    docker inspect 报的挂载源是 wsl 侧视角；在 Windows 宿主上做磁盘存在性
    检查前必须翻译，否则健康挂载会被误判成僵尸挂载（实弹冒烟抓到的盲区）。
    非 ``/mnt/<盘>/`` 形态原样返回；非 Windows 平台原样返回。
    """
    if platform != "win32":
        return path
    m = re.match(r"^/mnt/([A-Za-z])/(.*)$", path)
    if not m:
        return path
    return f"{m.group(1).upper()}:{chr(92)}{m.group(2).replace('/', chr(92))}"


def run_live_checks(
    project: str,
    distro: str,
    runner=None,
    *,
    mount_exists=os.path.isdir,
    platform: str = sys.platform,
) -> list[str]:
    """live 模式两查：api 容器 migrations 挂载源在场＋容器 env 关键键在场。

    ``runner`` 缺省＝真 docker（经 build_docker_cmd 装配）；注入形态＝
    ``runner(docker_args) -> stdout``（测试用假 runner，不触真 docker）。
    """
    if runner is None:
        runner = lambda docker_args: default_runner(distro, docker_args)  # noqa: E731
    lines: list[str] = []
    api = f"{project}-api-1"

    try:
        mounts_raw = runner(["inspect", api, "--format", "{{json .Mounts}}"])
    except RuntimeError as exc:
        lines.append(f"[FAIL] live 检查不可用（api 容器 {api} 无法检视）: {exc}")
        return lines
    mount_source = ""
    mounts_json = ""
    for line in reversed(mounts_raw.strip().splitlines()):
        line = line.strip()
        if line.startswith("[") or line.startswith("{"):
            mounts_json = line
            break
    for mount in json.loads(mounts_json):
        if mount.get("Destination") == MIGRATIONS_MOUNT_DEST:
            mount_source = mount.get("Source", "")
            break
    if not mount_source:
        lines.append(f"[FAIL] api 容器无 {MIGRATIONS_MOUNT_DEST} 挂载（部署装配缺 migrations）")
    elif not mount_exists(wsl_path_to_windows(mount_source, platform=platform)):
        # 僵尸挂载：部署树已删 ⇒ 容器内 alembic current 必炸而健康端点照绿的隐蔽态。
        lines.append(f"[FAIL] migrations 挂载源已不存在（僵尸挂载）: {mount_source}")
    else:
        lines.append(f"[OK] migrations 挂载源在场: {mount_source}")

    try:
        env_raw = runner(["exec", api, "printenv"])
    except RuntimeError as exc:
        lines.append(f"[FAIL] live 检查不可用（容器 env 无法读取）: {exc}")
        return lines
    container_keys = set(parse_env_names(env_raw))
    for name in CRITICAL_SERVER_KEYS:
        if name not in container_keys:
            lines.append(f"[FAIL] 容器 env 缺关键键: {name}")

    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="接管部署树检查器（教训⑩机械闸化；只读键名，永不打印键值）")
    parser.add_argument("--tree", required=True, help="部署树根目录")
    parser.add_argument("--live", action="store_true", help="追加活体两查（migrations 挂载源＋容器 env 关键键）")
    parser.add_argument("--wsl-distro", default="Ubuntu-24.04", help="Windows 宿主经哪个 wsl 发行版跑 docker")
    parser.add_argument("--project", default="fde-workbench", help="compose 项目名（容器前缀）")
    args = parser.parse_args()

    tree = Path(args.tree)
    if not tree.is_dir():
        print(f"[FAIL] --tree 不是目录: {tree}")
        return 2

    lines = check_tree(tree)
    if args.live:
        lines.extend(run_live_checks(args.project, args.wsl_distro))

    for line in lines:
        print(line)
    if any(line.startswith("[FAIL]") for line in lines):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
