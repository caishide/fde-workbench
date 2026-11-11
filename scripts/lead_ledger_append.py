#!/usr/bin/env python3
"""获客诊断 T-11：把已生效的认领**落账**到本地线索台账（``leads.md``）。

**为什么是宿主侧脚本**：台账真相层在 ``D:\\test\\FDE\\leads.md``——**在容器
之外**。服务端刻意**不碰真相层文件**（容器里没有真相层，也不该有）；它只生成
**待落账的台账行**（代号化九字段）并留在库里，落账由本脚本在宿主侧完成，
回执（行指纹 + 时刻）写回库。

**纪律**：

- **只插不改**：新行插到 §一 线索登记表的最后一行之后；找不到表 ⇒ **fail-closed**
  （不猜位置、不乱写）；
- **幂等**：同一 ``L-YYYYMMDD-NN`` 已存在 ⇒ 不重复追加，只补回执；
- **原子写**：先写临时文件再 ``os.replace``（同卷原子替换）；
- **零手工记账**：落账内容全部来自服务端生成的台账行，脚本**不改一字**。

用法（宿主，仓库根目录）::

    export FDE_DATABASE_URL='postgresql+psycopg://fde:<pw>@127.0.0.1:15432/fde_workbench'
    python scripts/lead_ledger_append.py --ledger 'D:\\test\\FDE\\leads.md' --dry-run
    python scripts/lead_ledger_append.py --ledger 'D:\\test\\FDE\\leads.md'

退出码：0 = 全部落账（或无待落账行）；1 = 冲突/失败（**不写半截**）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# 台账列序（**必须与** ``fde_api.diagnostics.claim_service.LEDGER_COLUMNS``
# 一致——``server/tests/test_diagnostics_lead_claims.py`` 有机械钉防漂移）。
LEDGER_COLUMNS = (
    "线索号",
    "#",
    "来源",
    "行业",
    "联系人角色",
    "痛点一句话",
    "资格五问得分",
    "下一步动作+日期",
    "①状态",
    "②来源人/报备到期日",
    "③回访触发日",
    "④资料索引",
)

# 线索登记行的行首（``| L-<YYYYMMDD>-<NN> | ...``）
_ROW_PATTERN = re.compile(r"^\|\s*(L-\d{8}-\d{2})\s\|")


def _cell(value: object) -> str:
    """单元格转义：竖线转义、换行压平、空白收敛。"""
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\\\").replace("|", "\\|")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _row_line(row: dict) -> str:
    """生成台账表的一行（列序＝``LEDGER_COLUMNS``）。"""
    missing = [column for column in LEDGER_COLUMNS if column not in row]
    if missing:
        raise SystemExit(f"台账行缺列：{missing}")
    return "| " + " | ".join(_cell(row[column]) for column in LEDGER_COLUMNS) + " |"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fetch_pending(engine) -> list[dict]:
    """取待落账的生效认领（按台账日期 ＋ 序号排序）。"""
    from sqlalchemy import text

    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, ledger_line_no, ledger_row FROM lead_diagnostic_claims "
                "WHERE status = 'accepted' AND ledger_written_at IS NULL "
                "ORDER BY ledger_date, ledger_seq"
            )
        ).fetchall()
    return [
        {
            "id": row[0],
            "line_no": row[1],
            "row": json.loads(row[2]) if isinstance(row[2], str) else dict(row[2]),
        }
        for row in rows
    ]


def _mark_written(engine, claim_id: str, digest: str) -> None:
    from sqlalchemy import text

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE lead_diagnostic_claims "
                "SET ledger_hash = :digest, ledger_written_at = now() WHERE id = :id"
            ),
            {"digest": digest, "id": claim_id},
        )


def _existing_rows(content: str) -> dict[str, str]:
    """台账里已有的线索号 → 原始行文本（幂等与回执指纹都用它）。"""
    found: dict[str, str] = {}
    for line in content.splitlines():
        match = _ROW_PATTERN.match(line)
        if match:
            found[match.group(1)] = line
    return found


def _insert_rows(content: str, new_lines: list[str]) -> str:
    """把新行插到 §一 登记表最后一行之后（找不到表 ⇒ fail-closed）。"""
    lines = content.splitlines()
    last_index = None
    for index, line in enumerate(lines):
        if _ROW_PATTERN.match(line):
            last_index = index
    if last_index is None:
        raise SystemExit(
            "台账里找不到线索登记行（形如 `| L-YYYYMMDD-NN | ...`）——"
            "**不猜位置**，请人工确认 leads.md 结构后再跑。"
        )
    return "\n".join(lines[: last_index + 1] + new_lines + lines[last_index + 1 :]) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把已生效认领落账到本地线索台账")
    parser.add_argument(
        "--ledger",
        default=r"D:\test\FDE\leads.md",
        help="线索台账路径（默认 D:\\test\\FDE\\leads.md）",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("FDE_DATABASE_URL", ""),
        help="数据库 URL（默认取环境变量 FDE_DATABASE_URL）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印要落账的行，不写文件")
    args = parser.parse_args(argv)

    if not args.database_url:
        raise SystemExit("缺少数据库 URL：请设置 FDE_DATABASE_URL 或 --database-url")

    ledger_path = Path(args.ledger)
    if not ledger_path.exists():
        raise SystemExit(f"台账文件不存在：{ledger_path}（真相层不新建，避免误建空台账）")

    from sqlalchemy import create_engine

    engine = create_engine(args.database_url)
    try:
        pending = _fetch_pending(engine)
    finally:
        engine.dispose()
    if not pending:
        print("没有待落账的生效认领（nothing to append）")
        return 0

    content = ledger_path.read_text(encoding="utf-8")
    existing = _existing_rows(content)

    new_lines: list[str] = []
    receipts: list[tuple[str, str]] = []
    for item in pending:
        line_no = item["line_no"]
        line = _row_line(item["row"])
        if line_no in existing:
            # 幂等：行已在台账里（上次追加成功、回执写失败）⇒ 只补回执
            receipts.append((item["id"], _sha256(existing[line_no])))
            print(f"[skip] {line_no} 已存在于台账（只补回执）")
            continue
        new_lines.append(line)
        receipts.append((item["id"], _sha256(line)))
        print(f"[plan] {line_no} → {ledger_path}")

    if args.dry_run:
        print("dry-run：未写文件")
        for line in new_lines:
            print(line)
        return 0

    if new_lines:
        updated = _insert_rows(content, new_lines)
        tmp_path = ledger_path.with_suffix(ledger_path.suffix + ".tmp")
        tmp_path.write_text(updated, encoding="utf-8")
        os.replace(tmp_path, ledger_path)

    engine = create_engine(args.database_url)
    try:
        for claim_id, digest in receipts:
            _mark_written(engine, claim_id, digest)
    finally:
        engine.dispose()
    print(f"落账完成：{len(new_lines)} 行新写，{len(receipts)} 条回执")
    return 0


if __name__ == "__main__":
    sys.exit(main())
