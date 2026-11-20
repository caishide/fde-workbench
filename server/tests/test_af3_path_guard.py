"""AF3-WP1：仓工具面路径白名单四拒＋符号链接逃逸＋超大 Patch（20 号 §3 WP1；
04 §3.3 A1 原文：「路径白名单显式拒绝 ``.git/**``、hooks 目录、
``.github/workflows/**``（Patch 能写 hook = 下一次人工 git 操作替 Agent 执行
代码），每项各配负向测试钉死」）。

S-AF3 负向变体对齐（docs/ai-fde/_af3-wp0-design.md §3 登记位；05 §4 收录
随 WP5 汇总）：S-AF3-01~07 在本文件落纯函数钉——

- S-AF3-01 写 ``.git/**``（普通文件）      → 拒绝
- S-AF3-02 写 ``.git/hooks/pre-commit``    → 拒绝（hook 注入）
- S-AF3-03 写 ``.github/workflows/ci.yml`` → 拒绝
- S-AF3-04 路径穿越（``..``/绝对路径/盘符/反斜杠）→ 拒绝
- S-AF3-05 符号链接逃逸（服务面 fs 级）    → 拒绝
- S-AF3-06 超大 Patch 三上限逐项           → 拒绝
- S-AF3-07 allow_roots 外路径（越界）      → 拒绝

D-C 已批默认参数（P1 2026-11-20「全部批准」）：单 Patch ≤512KB／≤100 文件／
≤2 万变更行；参数真身＝``solution_repo/whitelist.json``（FROZEN v1.0.0）。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch as mock_patch

import pytest

from fde_api.solution_repo import snapshot as snapshot_module
from fde_api.solution_repo.path_guard import (
    PatchEntry,
    check_patch,
    check_path,
    check_path_fs,
)
from fde_api.solution_repo.snapshot import load_whitelist

ALLOW_ROOTS = ("ontology/", "transforms/", "rules/", "tests/", "config/")


def _symlink(link: Path, target: Path) -> None:
    """建 symlink；Windows 无特权（WinError 1314）时显式 skip——CI（ubuntu-24.04）
    实跑，本机开发者模式开启时亦实跑。skipif 藏烂是平台能力缺席，非断言缺席：
    四拒字符串形状面（TestProtectedPaths/TestTraversalForms）不受此影响照常钉。"""
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink 特权缺失（{exc}）——CI ubuntu-24.04 实跑")


# ---- ① 快照真身（D-C 参数逐值） ------------------------------------------------


class TestWhitelistSnapshot:
    def test_snapshot_matches_decision_anchor(self) -> None:
        """仓内快照锚：v1.0.0 / D-C 三上限 / agent_allowed 闭集——白名单升 v2
        时此钉显式翻新（防快照静默漂移；沿 test_ae_connector_allowlist 锚钉形态）。"""
        snap = load_whitelist()
        assert snap["version"] == "1.0.0"
        rules = snap["path_rules"]
        assert rules["allow_roots"] == ["ontology/", "transforms/", "rules/", "tests/", "config/"]
        assert rules["max_patch_bytes"] == 524288
        assert rules["max_patch_files"] == 100
        assert rules["max_patch_changed_lines"] == 20000
        assert rules["deny_absolute"] is True
        assert rules["deny_dotdot"] is True
        assert rules["deny_symlink_escape"] is True
        # D2：Agent 可触发面闭集——patch_apply 归 WP2 类型化 adapter 接线，
        # push/merge 永不入 agent 面（human_only）。
        assert snap["git_ops"]["agent_allowed"] == ["status", "read_file", "diff", "log", "branch_create"]
        assert "push" in snap["git_ops"]["human_only"]
        assert "merge" in snap["git_ops"]["human_only"]
        assert "patch_apply" in snap["git_ops"]["human_only"]

    def test_load_missing_file_fails_closed(self, tmp_path: Path) -> None:
        with mock_patch.object(snapshot_module, "SNAPSHOT_PATH", tmp_path / "absent.json"):
            with pytest.raises(FileNotFoundError):
                load_whitelist()

    def test_load_corrupt_file_fails_closed(self, tmp_path: Path) -> None:
        bad = tmp_path / "whitelist.json"
        bad.write_text("{not json", encoding="utf-8")
        with mock_patch.object(snapshot_module, "SNAPSHOT_PATH", bad):
            with pytest.raises(ValueError):
                load_whitelist()


# ---- ② S-AF3-01/02：.git/** 与 hooks 目录 ---------------------------------------


class TestProtectedPaths:
    @pytest.mark.parametrize(
        "raw",
        [
            ".git/config",                      # S-AF3-01 根级 .git
            "tests/.git/objects/ab/cdef",       # 任意深度嵌套 .git
            ".git/hooks/pre-commit",            # S-AF3-02 hook 注入（根 .git/hooks）
            "ontology/.git/hooks/pre-commit",   # S-AF3-02 任意深度 hooks
            "config/hooks/post-checkout",       # 宽拒绝：任意 hooks 目录（受控仓 fail-closed）
        ],
    )
    def test_git_and_hooks_paths_rejected(self, raw: str) -> None:
        verdict = check_path(raw, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is False, raw
        assert verdict.code == "protected_path", raw

    @pytest.mark.parametrize(
        "raw",
        [
            ".github/workflows/ci.yml",        # S-AF3-03 根级 workflows
            "tests/.github/workflows/nightly.yml",  # 任意深度
            ".github/workflows/a/b/c.yml",     # 子目录
        ],
    )
    def test_workflow_paths_rejected(self, raw: str) -> None:
        verdict = check_path(raw, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is False, raw
        assert verdict.code == "protected_path", raw

    @pytest.mark.parametrize(
        "raw",
        [
            "ontology/equipment.yaml",
            "transforms/mapping/a.json",
            "rules/quality.json",
            "tests/test_a.json",
            "config/settings.json",
        ],
    )
    def test_allow_roots_paths_accepted(self, raw: str) -> None:
        verdict = check_path(raw, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is True, raw


# ---- ③ S-AF3-04：路径穿越四形态 -------------------------------------------------


class TestTraversalForms:
    @pytest.mark.parametrize(
        "raw",
        [
            "../outside.yaml",          # .. 开头
            "ontology/../../escape.yaml",   # 中段 ..
            "/etc/passwd",              # 绝对路径
            "C:/Windows/system32/config.sys",   # 盘符
            "ontology\\equipment.yaml",     # 反斜杠分隔
            "",                          # 空路径
            "ontology//x.yaml",          # 空部件
        ],
    )
    def test_traversal_forms_rejected(self, raw: str) -> None:
        verdict = check_path(raw, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is False, raw
        assert verdict.code == "path_escape", raw


# ---- ④ S-AF3-07：越界路径（allow_roots 外） --------------------------------------


class TestOutsideAllowRoots:
    @pytest.mark.parametrize(
        "raw",
        [
            "README.md",
            "src/app.py",
            "docs/guide.md",
            "vendor/lib/x.py",
        ],
    )
    def test_outside_allow_roots_rejected(self, raw: str) -> None:
        verdict = check_path(raw, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is False, raw
        assert verdict.code == "outside_allow_roots", raw


# ---- ⑤ S-AF3-05：符号链接逃逸（fs 级实探） ----------------------------------------


class TestSymlinkEscape:
    def test_symlink_target_inside_accepted(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        (workspace / "ontology").mkdir(parents=True)
        (workspace / "shared").mkdir()
        (workspace / "shared" / "real.yaml").write_text("x", encoding="utf-8")
        _symlink(workspace / "ontology" / "link.yaml", workspace / "shared" / "real.yaml")
        verdict = check_path_fs(
            Path("ontology/link.yaml"),
            workspace_root=workspace,
            allow_roots=ALLOW_ROOTS,
        )
        assert verdict.ok is True

    def test_symlink_escape_rejected(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        (workspace / "ontology").mkdir(parents=True)
        outside = tmp_path / "outside-secret.yaml"
        outside.write_text("secret", encoding="utf-8")
        _symlink(workspace / "ontology" / "evil.yaml", outside)
        verdict = check_path_fs(
            Path("ontology/evil.yaml"),
            workspace_root=workspace,
            allow_roots=ALLOW_ROOTS,
        )
        assert verdict.ok is False
        assert verdict.code == "symlink_escape"

    def test_symlink_parent_directory_escape_rejected(self, tmp_path: Path) -> None:
        """中间目录为 symlink 逃逸（不只检查叶子）：ontology/link/ 指向仓外目录。"""
        workspace = tmp_path / "ws"
        (workspace / "ontology").mkdir(parents=True)
        outside_dir = tmp_path / "outside-dir"
        outside_dir.mkdir()
        _symlink(workspace / "ontology" / "link", outside_dir)
        verdict = check_path_fs(
            Path("ontology/link/x.yaml"),
            workspace_root=workspace,
            allow_roots=ALLOW_ROOTS,
        )
        assert verdict.ok is False
        assert verdict.code == "symlink_escape"

    def test_string_shape_checked_before_fs(self, tmp_path: Path) -> None:
        """fs 实探前先过字符串形状（穿越形态不必触盘即拒）。"""
        verdict = check_path_fs(
            Path("../escape.yaml"),
            workspace_root=tmp_path,
            allow_roots=ALLOW_ROOTS,
        )
        assert verdict.ok is False
        assert verdict.code == "path_escape"


# ---- ⑥ S-AF3-06：超大 Patch 三上限逐项 ------------------------------------------


def _entry(path: str = "ontology/a.yaml", size: int = 10, lines: int = 1) -> PatchEntry:
    return PatchEntry(path=path, new_bytes=size, changed_lines=lines)


class TestPatchLimits:
    def test_normal_patch_accepted(self) -> None:
        entries = tuple(_entry(f"ontology/f{i}.yaml") for i in range(5))
        verdict = check_patch(entries, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is True

    def test_oversize_bytes_rejected(self) -> None:
        big = _entry("ontology/big.yaml", size=524289)  # 512KB + 1
        verdict = check_patch((big,), allow_roots=ALLOW_ROOTS)
        assert verdict.ok is False
        assert verdict.code == "oversize_patch"
        assert "bytes" in verdict.reason

    def test_oversize_file_count_rejected(self) -> None:
        entries = tuple(_entry(f"ontology/f{i}.yaml") for i in range(101))  # 100 + 1
        verdict = check_patch(entries, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is False
        assert verdict.code == "oversize_patch"
        assert "files" in verdict.reason

    def test_oversize_changed_lines_rejected(self) -> None:
        entries = (
            _entry("ontology/a.yaml", lines=10000),
            _entry("ontology/b.yaml", lines=10001),  # 累计 20001 > 20000
        )
        verdict = check_patch(entries, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is False
        assert verdict.code == "oversize_patch"
        assert "lines" in verdict.reason

    def test_limits_exactly_at_boundary_accepted(self) -> None:
        entries = (
            _entry("ontology/a.yaml", size=262144, lines=10000),
            _entry("ontology/b.yaml", size=262144, lines=10000),  # 524288 B / 20000 行 / 2 文件
        )
        verdict = check_patch(entries, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is True

    def test_patch_entry_with_protected_path_rejected(self) -> None:
        entries = (_entry(".git/hooks/pre-commit"),)
        verdict = check_patch(entries, allow_roots=ALLOW_ROOTS)
        assert verdict.ok is False
        assert verdict.code == "protected_path"

    def test_patch_whitelist_params_from_snapshot(self) -> None:
        """check_patch 参数可从冻结快照直接取（防调用方另传放宽数值）。"""
        snap = load_whitelist()
        rules = snap["path_rules"]
        entries = (_entry("ontology/big.yaml", size=rules["max_patch_bytes"] + 1),)
        verdict = check_patch(
            entries,
            allow_roots=tuple(rules["allow_roots"]),
            max_bytes=rules["max_patch_bytes"],
            max_files=rules["max_patch_files"],
            max_lines=rules["max_patch_changed_lines"],
        )
        assert verdict.ok is False
