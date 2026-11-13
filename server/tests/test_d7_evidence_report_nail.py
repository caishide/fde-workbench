"""D7 四口径运行证据复审报告防预支与对账静态钉（goal-sprint r4，2026-11-13）。

守三条硬约束（见 `docs/goal-sprint-上线冲刺-任务书.md` §3 r4 行、§6 防作弊条款、§9 硬指标 3）：
1. 复审报告按 `D4-D7人工项推进包` §4 骨架完整落盘，七项必填元数据与四口径段落齐全；
2. 拍板权归蔡工本人——在「蔡工签字」栏仍是占位符期间，「拍板值」栏严禁预支任何数字；
3. `v3-p3-评估报告-有限自动执行-v1.md` §5 解冻判定表在阈值未拍板、同类样本未达标前维持全 `PROPOSED`（闸态变更数 = 0）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPO_ROOT / "docs" / "audit" / "D7-四口径运行证据复审报告-2026-11-13.md"
PACKAGE_PATH = REPO_ROOT / "docs" / "audit" / "D4-D7人工项推进包-2026-11-07.md"
V3_P3_REPORT_PATH = REPO_ROOT / "docs" / "implementation" / "v3-p3-评估报告-有限自动执行-v1.md"

_REQUIRED_REPORT_ANCHORS = (
    "## 1. 复审轮七项必填元数据",
    "## 2. 四口径实测总表",
    "## 3. 活库逐行证据与旁证面核实",
    "## 4. r1 遗留问题专项裁决",
    "## 5. 各候选开放档位的证据对照",
    "## 6. D7 阈值拍板位",
    "HAS_RUN_EVIDENCE",
    "insufficient_for_unfreeze",
    "approval_not_executable",
)

_UNSIGNED_PLACEHOLDERS = ("待蔡工签字", "（待填）", "待填")


def _extract_section(markdown: str, heading_prefix: str) -> str:
    lines = markdown.splitlines()
    captured: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith(heading_prefix):
            in_section = True
            captured.append(line)
            continue
        if in_section and line.startswith("## "):
            break
        if in_section:
            captured.append(line)
    assert captured, f"missing section starting with {heading_prefix!r}"
    return "\n".join(captured)


def _markdown_table_rows(section_text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for raw in section_text.splitlines():
        stripped = raw.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows


def test_d7_report_exists_and_contains_required_sections() -> None:
    assert REPORT_PATH.is_file(), f"D7 复审报告缺失: {REPORT_PATH}"
    content = REPORT_PATH.read_text(encoding="utf-8")
    missing = [anchor for anchor in _REQUIRED_REPORT_ANCHORS if anchor not in content]
    assert not missing, f"D7 复审报告缺少必填锚点: {missing}"


def test_d7_decision_slots_forbid_unsigned_numeric_preallocation() -> None:
    """未有蔡工签字前，D7 拍板值栏严禁预支任何阿拉伯数字（防作弊条款 §6）。"""
    content = REPORT_PATH.read_text(encoding="utf-8")
    sec6 = _extract_section(content, "## 6. D7 阈值拍板位")
    rows = _markdown_table_rows(sec6)
    assert len(rows) >= 3, "§6 阈值拍板表至少包含表头 + D7-1 + D7-2 两行"
    header, data_rows = rows[0], rows[1:]
    assert "拍板状态" in header[2] and "拍板值" in header[3] and "签字" in header[4]

    for row in data_rows:
        item_name, _anchor, status_cell, value_cell, sign_cell = row[:5]
        unsigned = any(tok in sign_cell for tok in _UNSIGNED_PLACEHOLDERS) or not sign_cell
        if unsigned:
            assert "待蔡工拍板" in status_cell, (
                f"{item_name}: 未签字时拍板状态必须明示『待蔡工拍板』，实际={status_cell!r}"
            )
            digits = re.findall(r"\d+", value_cell)
            assert not digits, (
                f"{item_name}: 蔡工未签字前严禁在拍板值栏预支任何数字，发现 {digits} in {value_cell!r}"
            )
        else:
            assert "已拍板" in status_cell, (
                f"{item_name}: 已签字行拍板状态须更新为『已拍板』，实际={status_cell!r}"
            )

    pkg_sec4 = _extract_section(PACKAGE_PATH.read_text(encoding="utf-8"), "## 4. D7 ·")
    assert "D7-四口径运行证据复审报告-2026-11-13.md" in pkg_sec4
    assert "待蔡工拍板" in pkg_sec4


def test_v3_p3_unfreeze_table_remains_all_proposed_while_d7_unsigned() -> None:
    """D7 未签字放行前，v3-p3 §5 解冻判定表标题必须维持『全 PROPOSED——本表不解冻任何东西』且表内零已解冻标记。"""
    report_sec6 = _extract_section(REPORT_PATH.read_text(encoding="utf-8"), "## 6. D7 阈值拍板位")
    still_unsigned = any(tok in report_sec6 for tok in _UNSIGNED_PLACEHOLDERS)

    v3_p3 = V3_P3_REPORT_PATH.read_text(encoding="utf-8")
    sec5 = _extract_section(v3_p3, "## 5. 解冻判定表")
    heading_line = sec5.splitlines()[0]
    rows = _markdown_table_rows(sec5)
    assert len(rows) == 7, f"v3-p3 §5 解冻判定表行数预期 7（表头 + 6 行），实际={len(rows)}"
    if still_unsigned:
        assert "全 PROPOSED——本表不解冻任何东西" in heading_line, (
            f"D7 尚未签字拍板，v3-p3 §5 标题不得解除全 PROPOSED 声明：{heading_line!r}"
        )
        forbidden_unfreeze_tokens = ("已解冻", "已开放", "UNFROZEN", "APPROVED")
        for row in rows[1:]:
            row_joined = " | ".join(row)
            hit = [tok for tok in forbidden_unfreeze_tokens if tok in row_joined]
            assert not hit, f"D7 尚未签字拍板，v3-p3 §5 行不得出现解冻标记 {hit}：{row_joined}"
