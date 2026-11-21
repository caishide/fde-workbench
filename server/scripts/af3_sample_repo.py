"""AF3-WP3 任务集材料制备生成器（规格件 §5 W-E；P1 推荐案）。

生成受控示例仓（solution repo 基线）：四域声明式产物＋基线测试集＋**T4 预置
失败断言三类**（lint 失败/单测失败/契约失败——05 §5 AF3 行「≥3 类构建失败
可修复」的验收锚种子；「失败→修复→复测」轨迹由 WP4 修复闭环跑出）。

用法（P1/评测侧，仓外运行）：
    python server/scripts/af3_sample_repo.py --out D:/path/to/sample-repo

材料纪律：任务材料**禁含评分预期注释头**（AF1 G1 教训）——本生成器产出的是
「仓初始状态」而非任务指令；任务指令/断言检查器随任务集 v1.0 冻结批次落
（20 号 §3 WP6），不在本件。

与 tests/test_af3_ci_bundle.py::TestBundleExecution 行内 fixture 同源语义
（fixture 为简版；本生成器为完整版＝评测运行用真身）。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PRODUCTS = {
    "ontology/equipment.yaml": "kind: ontology\nname: equipment\nversion: 1.0.0\n",
    "transforms/pipe.yaml": "kind: transform\nname: pipe\nsteps:\n  - select: [a, b]\n",
    "rules/quality.json": '{"kind": "rule", "name": "quality", "condition": "a > 1"}\n',
    "config/settings.json": '{"kind": "config", "settings": {"threshold": 3}}\n',
    # T4 失败种子③（lint 类）：坏 YAML——lint bundle 红；修复＝合法化该文件
    "ontology/broken-seed.yaml": "kind: [unclosed\n",
    # T4 失败种子②（契约类）：缺 kind——contract schema 必备键；修复＝补 kind
    "config/missing-kind-seed.json": '{"settings": {"threshold": 1}}\n',
}
BASELINE_TESTS = {
    "tests/test_sample.py": "def test_baseline_passes():\n    assert 1 + 1 == 2\n",
    "tests/transforms/test_pipe.py": "def test_transform_baseline():\n    assert True\n",
    # T4 失败种子②（单测类）：断言产物值——产物修复后绿
    "tests/test_failing_assertion.py": (
        'def test_product_value():\n'
        '    text = open("ontology/equipment.yaml", encoding="utf-8").read()\n'
        '    assert "version: 2.0.0" in text, "产物版本须为 2.0.0"\n'
    ),
}


def build(out: Path) -> Path:
    for d in ("ontology", "transforms", "rules", "config", "tests", "tests/transforms"):
        (out / d).mkdir(parents=True, exist_ok=True)
    for rel, content in PRODUCTS.items():
        (out / rel).write_text(content, encoding="utf-8", newline="\n")
    for rel, content in BASELINE_TESTS.items():
        (out / rel).write_text(content, encoding="utf-8", newline="\n")
    subprocess.run(["git", "init"], cwd=out, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=out, capture_output=True, check=True)
    subprocess.run(
        ["git", "-c", "user.email=af3@test.local", "-c", "user.name=AF3 Materials", "commit", "-m", "baseline"],
        cwd=out,
        capture_output=True,
        check=True,
    )
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="AF3 受控示例仓基线生成器（T4 失败种子三类）")
    parser.add_argument("--out", required=True, help="输出目录（须在 solution_repo_base 围栏内）")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.exists() and not out.is_dir():
        print(f"--out is a file, not a directory: {out}", file=sys.stderr)
        return 2
    if out.exists() and any(out.iterdir()):
        print(f"输出目录非空：{out}", file=sys.stderr)
        return 2
    build(out)
    print(f"受控示例仓已生成：{out}")
    print("T4 失败种子：① lint（ontology/broken-seed.yaml 坏 YAML）② 单测（tests/test_failing_assertion.py 产物值断言）③ 契约（config/missing-kind-seed.json 缺 kind——contract schema 必备键）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
