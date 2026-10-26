#!/usr/bin/env python
"""Python 类型基线检查（WP06/B2）。

规则：
  1. 用 mypy 跑一遍目标包，得到错误清单。
  2. 与基线文件 ``server/mypy-baseline.txt`` 比对：基线内的存量错误忽略，
     基线外的新增错误一律失败（非零退出）。
  3. 基线只允许「减少」（存量错误被修复后可从基线移除），不允许增长。

用法：
  python scripts/check-python-types.py            # 校验（CI 用）
  python scripts/check-python-types.py --update   # 重写基线（有意收紧时）
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
BASELINE_PATH = SERVER / "mypy-baseline.txt"
TARGETS = ["src/fde_api"]

# mypy 输出形如 "src/fde_api/x.py:12: error: message  [code]"
_LINE_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+):(?: error)?: (?P<message>.*?)(?:  \[(?P<code>[a-z0-9-]+)\])?$")


def normalize(message: str) -> str:
    """去掉行号与易变片段，只保留错误身份（文件 + 错误码 + 归一化消息）。"""
    message = re.sub(r'"[^"]*"', '"..."', message)
    message = re.sub(r"\b\d+\b", "N", message)
    return message.strip()


def run_mypy() -> tuple[int, str]:
    python = SERVER / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = SERVER / ".venv" / "bin" / "python"
    if not python.exists():
        # CI 可能直接用系统解释器装依赖（无 server/.venv），回退当前解释器
        python = Path(sys.executable)
    result = subprocess.run(
        [str(python), "-m", "mypy", *TARGETS, "--no-error-summary", "--no-pretty"],
        cwd=SERVER,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout + result.stderr


def collect(output: str) -> list[str]:
    entries: list[str] = []
    for raw in output.splitlines():
        match = _LINE_RE.match(raw.strip())
        if not match:
            continue
        file = match.group("file").replace("\\", "/")
        if "fde_api" not in file:
            continue
        code = match.group("code") or "uncategorized"
        message = normalize(match.group("message"))
        entries.append(f"{file}:{code}: {message}")
    return sorted(set(entries))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="rewrite the baseline file")
    args = parser.parse_args()

    returncode, output = run_mypy()
    if returncode == 127:
        return 127
    current = collect(output)

    baseline: set[str] = set()
    if BASELINE_PATH.exists():
        baseline = {
            line.strip()
            for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }

    if args.update:
        BASELINE_PATH.write_text(
            "\n".join(current) + ("\n" if current else ""), encoding="utf-8"
        )
        print(f"baseline written: {len(current)} known error(s) -> {BASELINE_PATH}")
        return 0

    new_errors = [entry for entry in current if entry not in baseline]
    resolved = [entry for entry in baseline if entry not in current]

    if new_errors:
        print(f"FAIL: {len(new_errors)} new type error(s) not in the baseline:")
        for entry in new_errors:
            print(f"  {entry}")
        print(
            "Fix them, or (only when the increase is intended) run "
            "`python scripts/check-python-types.py --update`."
        )
        return 1

    if resolved:
        print(
            f"NOTE: {len(resolved)} baseline error(s) are now resolved; "
            "run with --update to shrink the baseline."
        )
    print(f"OK: no new type errors (baseline {len(baseline)}, current {len(current)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
