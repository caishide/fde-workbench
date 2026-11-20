"""solution_repo 声明式产物校验器（AF3-WP3；design-first 规格件 §3.1）。

以 ``python -I -m fde_api.solution_repo.checkers --mode lint|contract <root>``
被 CI bundle 调用——**服务端包内模块，不在仓内取码**（D3：bundle 不执行仓内
任何解释文件入口；T5 防线）。stdout 输出 JSON（``{"checked": [...]}``）供
执行器解析成 executed_checks；违例 exit 1（red 面）。

四域 schema 为服务端内置常量（Patch 不可改——仓内 schema 文件不在信任面）：
- ontology：必备键 kind/name/version（str）
- transforms：必备键 kind/name/steps（list）
- rules：必备键 kind/name/condition（str）
- config：必备键 kind/settings（dict）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # PyYAML（workbench venv 依赖）
except ImportError:  # pragma: no cover - venv 缺依赖属环境错误
    yaml = None

CHECKED_SUFFIXES = (".yaml", ".yml", ".json")
DOMAINS = ("ontology", "transforms", "rules", "config")

# contract 模式必备键域表（内置 schema；值类型约束）
SCHEMAS: dict[str, dict[str, type]] = {
    "ontology": {"kind": str, "name": str, "version": str},
    "transforms": {"kind": str, "name": str, "steps": list},
    "rules": {"kind": str, "name": str, "condition": str},
    "config": {"kind": str, "settings": dict},
}


def check_file(path: Path, mode: str) -> tuple[bool, str]:
    """单文件校验：返回 (ok, reason)。lint＝可解析＋UTF-8＋非空；
    contract＝解析后按域 schema 判必备键与类型。"""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return False, f"读取失败：{exc}"
    if not raw.strip():
        return False, "空文件"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"非 UTF-8 编码：{exc}"
    if path.suffix.lower() in (".yaml", ".yml"):
        if yaml is None:
            return False, "PyYAML 不可用（环境错误）"
        try:
            data: Any = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            return False, f"YAML 解析失败：{exc}"
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            return False, f"JSON 解析失败：{exc}"
    if mode != "contract":
        return True, ""
    domain = path.parent.name.lower()
    schema = SCHEMAS.get(domain)
    if schema is None:
        return True, ""  # 非四域子目录的产物文件只做可解析判定
    if not isinstance(data, dict):
        return False, f"{domain} 产物须为 JSON/YAML 对象"
    missing = [key for key in schema if key not in data]
    if missing:
        return False, f"缺必备键 {missing}（{domain} schema）"
    wrong_type = [
        key for key, want in schema.items() if key in data and not isinstance(data[key], want)
    ]
    if wrong_type:
        return False, f"键类型不符 {wrong_type}（{domain} schema）"
    return True, ""


def run(mode: str, root: Path) -> int:
    """校验入口：lint/contract 两模式；违例清单 JSON 到 stdout，违例 exit 1。"""
    if mode not in ("lint", "contract"):
        print(json.dumps({"error": f"未知 mode：{mode}"}), file=sys.stderr)
        return 2
    checked: list[dict[str, Any]] = []
    files: list[Path] = []
    for domain in DOMAINS:
        base = root / domain
        if not base.is_dir():
            continue
        files.extend(
        sorted(
            p for p in base.rglob("*")
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in CHECKED_SUFFIXES
        )
    )  # 评审：symlink 过滤（checkers 不读仓外链接目标——泄露面收敛）
    for path in files:
        ok, reason = check_file(path, mode)
        rel = path.relative_to(root).as_posix()
        checked.append({"nodeid": rel, "outcome": "passed" if ok else "failed", "reason": reason})
    violations = [c for c in checked if c["outcome"] != "passed"]
    print(json.dumps({"checked": checked, "violations": len(violations)}, ensure_ascii=False))
    return 1 if violations else 0


def main(argv: list[str]) -> int:
    args = list(argv)
    mode = "lint"
    root = Path(".")
    i = 0
    while i < len(args):
        if args[i] == "--mode" and i + 1 < len(args):
            mode = args[i + 1]
            i += 2
        elif not args[i].startswith("-"):
            root = Path(args[i])
            i += 1
        else:
            i += 1
    return run(mode, root)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
