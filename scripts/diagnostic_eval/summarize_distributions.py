"""诊断评测·分数面分布 CLI（T-09 读数规则：同考卷同生成器多 run → 噪声带底册）。

跑法（宿主 Windows，同 run_eval：主树 server/ 目录跑，代码走 worktree src）：

```bash
PYTHONPATH=<worktree>/server/src python <worktree>/scripts/diagnostic_eval/summarize_distributions.py \
    --out <真相层>/eval-runs/distributions/<stamp>.json
```

**纪律**：分布底册（只有数字与 run id，零报告正文零答案材料）落真相层（E-2）；
仓库侧只存汇总+指针（曲线/审计文档引用 markdown 由本命令打印、人工誊入文档）。
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

SERVER_SRC = Path(__file__).resolve().parents[2] / "server" / "src"
sys.path.insert(0, str(SERVER_SRC))

import eval_lib  # noqa: E402  (scripts 同目录直import)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

DISTRIBUTIONS_DIRNAME = "distributions"


def main() -> int:
    parser = argparse.ArgumentParser(description="诊断评测·分数面分布底册（读数规则）")
    parser.add_argument(
        "--min-runs",
        type=int,
        default=eval_lib.MIN_DISTRIBUTION_RUNS,
        help=f"每组最少样本数（缺省 {eval_lib.MIN_DISTRIBUTION_RUNS}；n 不足=insufficient_data）",
    )
    parser.add_argument(
        "--out",
        default="",
        help="真相层输出路径（缺省=eval-runs/distributions/<UTC戳>.json）",
    )
    args = parser.parse_args()

    root = eval_lib.truth_root()
    runs = eval_lib.aggregate_runs(root)
    summary = eval_lib.score_distributions(runs, min_runs=args.min_runs)

    out = Path(args.out) if args.out else (
        root / eval_lib.RUNS_DIRNAME / DISTRIBUTIONS_DIRNAME
        / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    payload = dict(summary)
    payload["created_at"] = datetime.now(UTC).isoformat()
    payload["source_runs"] = [item["run_id"] for item in runs]
    eval_lib.write_json(out, payload)
    print(f"DISTRIBUTIONS_OK {out} runs={len(runs)}")
    sys.stdout.write(eval_lib.render_distribution_md(summary))
    usable_groups = len(summary.get("case_groups") or {})
    anchor_groups = len(summary.get("anchor_groups") or {})
    print(f"case_groups={usable_groups} anchor_groups={anchor_groups}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
