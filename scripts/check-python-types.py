#!/usr/bin/env python
"""Python 类型基线检查（WP06/B2 引入；WP24/H1 改为计数法并纳入 tests）。

规则：
  1. 用 mypy 跑一遍目标包（src/fde_api + tests），得到错误清单。
  2. 与基线文件 ``server/mypy-baseline.txt`` 按**多重集**比较：同一
     （文件, 错误码, 归一化消息）条目在当前的出现次数不得超过基线记录的次数。
     同类新增（同文件同错误码同归一化消息、不同行）计一次新增 —— 旧版按
     ``sorted(set(...))`` 去重会把这类新增静默放行（C-8d 假绿灯，已修）。
  3. 基线只允许「减少」（存量错误被修复后用 --update 收缩），不允许增长。

用法：
  python scripts/check-python-types.py            # 校验（CI 用）
  python scripts/check-python-types.py --update   # 重写基线（有意收紧时；须在干净树执行）
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
BASELINE_PATH = SERVER / "mypy-baseline.txt"
TARGETS = ["src/fde_api", "tests"]

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


def collect(output: str) -> Counter[str]:
    """多重集：一条基线行 = 「文件:错误码: 归一化消息」的一次出现。"""
    entries: list[str] = []
    for raw in output.splitlines():
        match = _LINE_RE.match(raw.strip())
        if not match:
            continue
        file = match.group("file").replace("\\", "/")
        if not (file.startswith("src/") or file.startswith("tests/")):
            continue
        code = match.group("code") or "uncategorized"
        message = normalize(match.group("message"))
        entries.append(f"{file}:{code}: {message}")
    return Counter(entries)


def read_baseline() -> Counter[str]:
    if not BASELINE_PATH.exists():
        return Counter()
    lines = [
        line.strip()
        for line in BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return Counter(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="rewrite the baseline file")
    args = parser.parse_args()

    returncode, output = run_mypy()
    if returncode == 127:
        return 127
    current = collect(output)
    baseline = read_baseline()

    if args.update:
        lines = sorted(current.elements())
        BASELINE_PATH.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        print(f"baseline written: {len(lines)} entries -> {BASELINE_PATH}")
        return 0

    new_errors = current - baseline
    resolved = baseline - current

    if new_errors:
        total_extra = sum(new_errors.values())
        print(f"FAIL: {total_extra} new type error occurrence(s) not covered by the baseline:")
        for entry, count in sorted(new_errors.items()):
            print(f"  x{count} {entry}")
        print(
            "Fix them, or (only when the increase is intended) run "
            "`python scripts/check-python-types.py --update`."
        )
        return 1

    if resolved:
        print(
            f"NOTE: {sum(resolved.values())} baseline occurrence(s) are now resolved; "
            "run with --update to shrink the baseline."
        )
    print(
        f"OK: no new type errors (baseline {sum(baseline.values())} occurrences / "
        f"{len(baseline)} distinct, current {sum(current.values())})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
