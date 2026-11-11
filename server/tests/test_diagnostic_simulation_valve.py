"""污染单向阀静态钉（L 线 L1 轮；设计稿 §2.1 核心裁定的机械承载）。

裁定：诊断评测集的判卷基准**允许**进训练场 DB 的 judge 参考面（judge ≠ 生成器；
泄漏自检在位），但**禁止任何从训练场 reference 流向诊断生成器提示词/few-shot
的路径**。本钉双向封面：

1. **生成器面**：``server/src/fde_api/diagnostics/**`` 不得 import ``simulation``
   包（绝对/相对/子模块任一形态）——生成器提示词装配面从结构上接触不到场景
   reference；
2. **评测脚本面**：``scripts/diagnostic_eval/**`` 对 simulation 包的导入只许
   judge（``fde_api.simulation.diagnostic_judge`` 白名单）——判卷侧是合法消费
   方，其余任何 simulation 面（尤其 reference/loader）出现即红。

AST 扫描（非文本 grep）；断言扫描面非空（空面 = 假绿，同污染钉家族纪律）。
任务书：``docs/audit/交付案例学习闭环-L1任务书-2026-11-12.md``。
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SERVER_DIR = TESTS_DIR.parent
REPO_ROOT = SERVER_DIR.parent

DIAGNOSTICS_DIR = SERVER_DIR / "src" / "fde_api" / "diagnostics"
DIAGNOSTIC_EVAL_DIR = REPO_ROOT / "scripts" / "diagnostic_eval"

# 评测脚本面唯一放行目标：judge（判卷侧合法消费方）
JUDGE_ALLOWLIST_PREFIX = "fde_api.simulation.diagnostic_judge"


def _import_targets(tree: ast.AST) -> set[str]:
    """提取一个模块的全部导入目标（绝对模块、from-import 展开名、相对导入点号形态）。"""
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                targets.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level > 0:
                # 相对导入：level=1 "./"，level=2 "../"……（scripts 非包，此形态出现即异常目标）
                targets.add("." * node.level + module)
            else:
                targets.add(module)
                for alias in node.names:
                    targets.add(f"{module}.{alias.name}" if module else alias.name)
    return targets


def _is_simulation_target(target: str) -> bool:
    return (
        target == "fde_api.simulation"
        or target.startswith("fde_api.simulation.")
        # 相对导入形态：from ..simulation import x / from .simulation import x
        or target.lstrip(".") == "simulation"
        or target.lstrip(".").startswith("simulation.")
    )


def _python_files(root: Path) -> list[Path]:
    assert root.exists(), f"扫描面不存在（钉面失效）：{root}"
    files = sorted(root.rglob("*.py"))
    assert files, f"扫描面为空（空面 = 假绿）：{root}"
    return files


def test_diagnostics_package_never_imports_simulation() -> None:
    offenders: list[str] = []
    scanned = 0
    for path in _python_files(DIAGNOSTICS_DIR):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scanned += 1
        for target in _import_targets(tree):
            if _is_simulation_target(target):
                offenders.append(f"{path.name}: {target}")
    assert scanned >= 1
    assert not offenders, f"诊断生成器面出现 simulation 导入（单向阀被穿）：{offenders}"


def test_diagnostic_eval_scripts_only_import_judge_from_simulation() -> None:
    offenders: list[str] = []
    scanned = 0
    simulation_imports = 0
    for path in _python_files(DIAGNOSTIC_EVAL_DIR):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scanned += 1
        for target in _import_targets(tree):
            if _is_simulation_target(target):
                simulation_imports += 1
                if not (
                    target == JUDGE_ALLOWLIST_PREFIX
                    or target.startswith(JUDGE_ALLOWLIST_PREFIX + ".")
                ):
                    offenders.append(f"{path.name}: {target}")
    assert scanned >= 1
    # 判卷侧至少有一条 judge 导入在位（现状语义；若日后重构移走，须同步修订本钉并留痕）
    assert simulation_imports >= 1, "评测脚本面未发现任何 judge 导入——白名单语义与现状脱节，须复核本钉"
    assert not offenders, f"评测脚本面出现 judge 之外的 simulation 导入（单向阀被穿）：{offenders}"
