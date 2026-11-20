"""Git 受控执行器（AF3-WP1；离线本地 Git 先通）。

安全面（红线：Agent 禁任意 Shell；评审 G2 沙箱化）：
- 固定 ``git`` 可执行 + **argv 列表构造**（``shell=False`` 恒定）——参数不经过
  shell 解释，注入面收敛到 git 自身语义；
- **子命令前强制封锁参数**（评审 G2，RCE 面封堵）：``-c core.fsmonitor=false``
  （绑定仓 ``.git/config`` 若被写入 fsmonitor 命令，``git status`` 会执行它）＋
  ``-c core.hooksPath=``（空＝禁 hooks 执行）；这两项与路径白名单（写
  ``.git/**`` 拒）互为纵深——config 可由绑定者可控，封锁不依赖仓可信度；
- **清 GIT_* 环境＋隔离全局配置**：子进程 env 白名单重建＋
  ``GIT_CONFIG_GLOBAL=<os.devnull>``＋``GIT_CONFIG_NOSYSTEM=1``——宿主全局
  ``~/.gitconfig`` 的 ``core.hooksPath``/``url.*.insteadOf``/``credential.helper``
  对绑定仓内调用一律失效（评审 G2：HOME 保留导致的全局 config 注入面）；
- 超时 30s；``OSError``（git 缺失/仓被删）与 ``TimeoutExpired`` 统一折算为
  ``GitFailed``（评审 G5：不逃出域错误信封）；stdout/stderr 固定 utf-8 解码
  （评审 G5：Windows 默认 cp936 会把 git utf-8 输出炸成 UnicodeDecodeError）。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

GIT_TIMEOUT_SECONDS = 30

# 子命令前强制封锁参数（任意 run/run_ok 都带上；与仓内 config 无关地生效）
_FORCE_CONFIG = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=",
)

# 子进程 env 白名单：PATH/HOME/系统路径足够 git CLI 运行；任何 GIT_*/SSH_*
# 全部剥离（环境注入面收敛）；全局/系统 git 配置经 GIT_CONFIG_GLOBAL/
# GIT_CONFIG_NOSYSTEM 隔离（评审 G2）。
_ENV_KEEP = ("PATH", "HOME", "SYSTEMROOT", "COMSPEC", "PATHEXT", "TMP", "TEMP", "LANG", "LC_ALL")


class GitRunner:
    """绑定级受控 git 执行器（cwd 固定为绑定 repo_root；在线程面调用）。"""

    def __init__(self, repo_root: Path):
        self._root = Path(repo_root)

    def run(self, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> str:
        """执行只读/受控 git 子命令，返回 stdout（strip）；失败抛 ``GitFailed``。"""
        proc = self._spawn(*args, timeout=timeout)
        if proc.returncode != 0:
            raise GitFailed(" ".join(args), proc.returncode, (proc.stderr or proc.stdout or "").strip()[:500])
        return (proc.stdout or "").strip()

    def run_ok(self, *args: str, timeout: int = GIT_TIMEOUT_SECONDS) -> str | None:
        """探测性执行：退码非零返回 ``None``（不抛）——用于 ``rev-parse --verify``
        分支存在性探测（探测不到＝业务态，非执行失败）。"""
        proc = self._spawn(*args, timeout=timeout)
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()

    def _spawn(self, *args: str, timeout: int) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(  # noqa: S603 — argv 列表构造，禁 shell=True
                ["git", *_FORCE_CONFIG, *args],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False,
                env=self._safe_env(),
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise GitFailed(" ".join(args), -1, f"timeout after {timeout}s") from None
        except OSError as exc:
            # git 可执行缺失 / cwd 被删等执行环境失败——统一折算 GitFailed
            # （评审 G5：FileNotFoundError 不得逃出域错误信封）。
            raise GitFailed(" ".join(args), -1, str(exc)) from None

    @staticmethod
    def _safe_env() -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if key in _ENV_KEEP}
        env["GIT_CONFIG_GLOBAL"] = os.devnull  # 全局 ~/.gitconfig 失效（insteadOf/credential/hooksPath）
        env["GIT_CONFIG_NOSYSTEM"] = "1"  # 系统 /etc/gitconfig 失效
        return env


class GitFailed(Exception):
    """Git 执行层失败（退码＋stderr 截断；500 git_operation_failed 的载体）。"""

    def __init__(self, args: str, returncode: int, stderr: str):
        super().__init__(f"git {args} → 退码 {returncode}: {stderr}")
        self.args_str = args
        self.returncode = returncode
        self.stderr = stderr

    def to_details(self) -> dict[str, Any]:
        return {"args": self.args_str, "returncode": self.returncode, "stderr": self.stderr}
