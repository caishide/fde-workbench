# -*- coding: utf-8 -*-
"""训练场分布读数底册 CLI（L 线 L2 轮，2026-11-12）。

读批跑器 JSONL（真相层），按 run_distributions 语义聚合分布并出判定，
汇总 JSON 写回真相层 ``--out``；stdout 出 markdown 底册（仓库侧只存汇总＋
指针＋sha256，零报告正文零答案材料）。输出落本仓内即拒。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import run_distributions  # noqa: E402


def _refuse_inside_repo(out_path: Path) -> None:
    root = out_path.resolve().parent
    for p in (root, *root.parents):
        if (p / ".git").exists():
            raise SystemExit(f"输出落在本仓内，拒绝（真相层专用）：{out_path.resolve()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="训练场 run 分布读数底册（L2）")
    parser.add_argument("--runs-file", required=True, help="批跑 JSONL（真相层）")
    parser.add_argument("--anchor-keys", default="", help="逗号分隔锚点场景业务键")
    parser.add_argument("--layer", default="model", choices=run_distributions.VALID_LAYERS)
    parser.add_argument("--min-runs", type=int, default=run_distributions.MIN_DISTRIBUTION_RUNS)
    parser.add_argument("--out", required=True, help="汇总 JSON 输出路径（真相层，仓内即拒）")
    args = parser.parse_args()

    runs_file = Path(args.runs_file)
    if not runs_file.is_file():
        raise SystemExit(f"批跑 JSONL 不在场：{runs_file}")
    out_path = Path(args.out)
    _refuse_inside_repo(out_path)

    records = [
        json.loads(line)
        for line in runs_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    anchor_keys = [key.strip() for key in args.anchor_keys.split(",") if key.strip()]

    summary = run_distributions.collect_distributions(
        records,
        anchor_keys=anchor_keys,
        layer=args.layer,
        min_runs=args.min_runs,
    )
    verdicts = run_distributions.decide_against_anchor(summary, min_runs=args.min_runs)
    payload = {
        **summary,
        "runs_file": str(runs_file.resolve()),
        "runs_sha256": hashlib.sha256(runs_file.read_bytes()).hexdigest(),
        "verdicts": verdicts,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sys.stdout.write(run_distributions.render_summary_md(summary, verdicts))
    print(f"[done] 汇总 -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
