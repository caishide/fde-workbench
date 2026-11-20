"""Git 受控执行器（AF3-WP1；离线本地 Git 先通）。

安全面（红线：Agent 禁任意 Shell）：
- 固定 ``git`` 可执行 + **argv 列表构造**（``shell=False`` 恒定）——参数不经过
  shell 解释，注入面收敛到 git 自身语义；
- **清 GIT_* 环境**：子进程 env 白名单重建，防外部 ``GIT_EXEC_PATH``/
  ``GIT_ALTERNATE_OBJECT_DIRECTORIES``/``GIT_CONFIG`` 等环境注入；
- 超时 30s＋``-c core.hooksPath=/dev/null`` 类封锁不做——绑定仓是受控示例仓，
  hook 防护由路径白名单（写 .git/hooks 拒）＋human_only（hooks_path_config 拒）
  承担，执行层不静默改写仓配置。
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

GIT_TIMEOUT_SECONDS = 30

# 子进程 env 白名单：PATH/HOME/系统locale 足够 git CLI 运行；任何 GIT_*/SSH_*
# 全部剥离（环境注入面收敛）。
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
        return subprocess.run(  # noqa: S603 — argv 列表构造，禁 shell=True
            ["git", *args],
            cwd=str(self._root),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            env=self._safe_env(),
            check=False,
        )

    @staticmethod
    def _safe_env() -> dict[str, str]:
        env = {key: value for key, value in os.environ.items() if key in _ENV_KEEP}
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)
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
