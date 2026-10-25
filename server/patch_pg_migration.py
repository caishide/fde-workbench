#!/usr/bin/env python3
"""
D2: MySQL -> PostgreSQL 代码级迁移补丁（幂等）
=================================================
依据：《迁移方案裁决-B-PG-vs-C-SQLite-v1.0.md》方案 B + Party Mode 五席裁决

改动点：
  1. auth/models.py  UTCTimestamp: mysql.TIMESTAMP(fsp=6) -> TIMESTAMP(timezone=True) on PG
  2. auth/models.py  UTC_TIMESTAMP_SQL: text("UTC_TIMESTAMP(6)") -> func.now()
  3. auth/models.py  CURRENT_TIMESTAMP_SQL -> func.now()
  4. workbench/models.py TimestampMixin: server_onupdate -> onupdate=func.now()
     （PG 无 ON UPDATE CURRENT_TIMESTAMP；不改则 updated_at 冻结 —— 架构师席点名的最大隐性坑）
  5. 两处 Boolean server_default="0" -> server_default=false（PG 拒绝字符串 "0"）
  6. users/service.py: MySQL 错误码 1062/1213 -> PG 适配（psycopg UniqueViolation / DeadlockDetected）

不改：
  - db.ping()：PG 同样支持
  - server_default=text("1")/text("0")：那些是 Integer 列（risk_level/attempt 等），PG 兼容
  - JSON 列：SQLAlchemy 通用 JSON 类型，方言自动映射
  - with_for_update：PG 全支持

用法: python patch_pg_migration.py
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "fde_api"

PATCHES: list[tuple[Path, str, str, str]] = []


def add(rel: str, old: str, new: str, tag: str) -> None:
    PATCHES.append((SRC / rel, old, new, tag))


# ---------- 1+2+3: auth/models.py 时间戳 ----------
add(
    "auth/models.py",
    "from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, text\nfrom sqlalchemy.dialects import mysql\n",
    "from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func, text\n",
    "P1-去 mysql 方言 import",
)

add(
    "auth/models.py",
    '''class UTCTimestamp(UTCDateTime):
    """Use MySQL's UTC-normalized TIMESTAMP storage for auto-updated values."""

    impl = mysql.TIMESTAMP
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        return dialect.type_descriptor(mysql.TIMESTAMP(fsp=6))''',
    '''class UTCTimestamp(UTCDateTime):
    """Portable UTC-normalized TIMESTAMP storage.

    v0.2 (PG 迁移): 原实现硬依赖 MySQL 的 TIMESTAMP(fsp=6)。改为在
    PostgreSQL 上使用 TIMESTAMP(timezone=True)，其他方言回落原生 TIMESTAMP。
    """

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(DateTime(timezone=True))
        return dialect.type_descriptor(DateTime())''',
    "P2-UTCTimestamp 去 mysql",
)

add(
    "auth/models.py",
    'UTC_TIMESTAMP_SQL = text("UTC_TIMESTAMP(6)")\nCURRENT_TIMESTAMP_SQL = text("CURRENT_TIMESTAMP(6)")',
    "# v0.2 (PG 迁移): MySQL 的 UTC_TIMESTAMP(6) 在 PG 不存在，改用 func.now()（PG 返回带时区）。\nUTC_TIMESTAMP_SQL = func.now()\nCURRENT_TIMESTAMP_SQL = func.now()",
    "P3-时间戳常量",
)

# ---------- 4: workbench/models.py TimestampMixin ----------
add(
    "workbench/models.py",
    """    updated_at: Mapped[datetime] = mapped_column(
        UTCTimestamp(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_SQL,
        server_onupdate=CURRENT_TIMESTAMP_SQL,
    )""",
    """    # v0.2 (PG 迁移): PG 没有 ON UPDATE CURRENT_TIMESTAMP，server_onupdate 在 PG 上不生效，
    # 会导致 updated_at 永远冻结。改为 ORM 层 onupdate=func.now()（跨方言通用）。
    updated_at: Mapped[datetime] = mapped_column(
        UTCTimestamp(),
        nullable=False,
        server_default=CURRENT_TIMESTAMP_SQL,
        onupdate=func.now(),
    )""",
    "P4-server_onupdate→onupdate",
)

add(
    "workbench/models.py",
    """from sqlalchemy import (
    Boolean,""",
    """from sqlalchemy import (
    Boolean,
    func,""",
    "P5-workbench 引入 func",
)

# ---------- 5: Boolean server_default ----------
add(
    "control/chat.py",
    'deep_thinking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")',
    "# v0.2 (PG 迁移): PG 的 BOOLEAN DEFAULT 不接受字符串 '0'，改用 text('false')。\n    deep_thinking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text('false'))",
    "P6-chat Boolean default",
)

add(
    "research/models.py",
    'ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")',
    "# v0.2 (PG 迁移): PG 的 BOOLEAN DEFAULT 不接受字符串 '0'，改用 text('false')。\n    ai_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text('false'))",
    "P7-research Boolean default",
)

# ---------- 6: MySQL 错误码 -> PG ----------
# 真 bug（源码实测）：_database_error_code 只返回 int，
# 而 psycopg 的错误码是字符串（'23505' / '40P01'）→ 原实现会丢弃 PG 错误码，
# 导致唯一约束冲突不再被识别为「用户名重复」，误报 503 user_creation_failed。
# 修法：让判定函数同时接受 int 与 str，并把调用点改成语义化判定。
add(
    "users/service.py",
    """MYSQL_DUPLICATE_ENTRY = 1062
MYSQL_DEADLOCK = 1213""",
    """# v0.2 (PG 迁移): 原为 MySQL 错误码。改为跨方言：
#   MySQL 1062 = duplicate entry   / 1213 = deadlock
#   PG  23505 = unique_violation   / 40P01 = deadlock_detected
MYSQL_DUPLICATE_ENTRY = 1062
MYSQL_DEADLOCK = 1213
PG_DUPLICATE_ENTRY = "23505"
PG_DEADLOCK = "40P01\"""",
    "P8a-错误码常量",
)

add(
    "users/service.py",
    """def _database_error_code(error: SQLAlchemyError) -> int | None:
    original = getattr(error, "orig", None)
    arguments = getattr(original, "args", ())
    return arguments[0] if arguments and isinstance(arguments[0], int) else None""",
    """def _database_error_code(error: SQLAlchemyError) -> int | str | None:
    \"\"\"跨方言取原始驱动错误码。

    v0.2 (PG 迁移): 原实现只认 int（MySQL）。psycopg 的 SQLSTATE 是字符串，
    原实现会静默丢弃 → PG 上唯一约束冲突不再被识别为「用户名重复」。
    \"\"\"
    original = getattr(error, "orig", None)
    arguments = getattr(original, "args", ())
    if not arguments:
        return None
    code = arguments[0]
    return code if isinstance(code, (int, str)) else None


def _is_duplicate_entry(error: SQLAlchemyError) -> bool:
    \"\"\"唯一约束冲突（MySQL 1062 / PG 23505）。\"\"\"
    code = _database_error_code(error)
    return code == MYSQL_DUPLICATE_ENTRY or code == PG_DUPLICATE_ENTRY


def _is_deadlock(error: SQLAlchemyError) -> bool:
    \"\"\"死锁（MySQL 1213 / PG 40P01）。\"\"\"
    code = _database_error_code(error)
    return code == MYSQL_DEADLOCK or code == PG_DEADLOCK""",
    "P8b-错误码取值函数跨方言",
)

add(
    "users/service.py",
    "            if _database_error_code(error) == MYSQL_DUPLICATE_ENTRY and _confirmed_username_winner(",
    "            if _is_duplicate_entry(error) and _confirmed_username_winner(",
    "P8c-唯一冲突判定",
)

add(
    "users/service.py",
    "            if _database_error_code(error) == MYSQL_DEADLOCK:",
    "            if _is_deadlock(error):",
    "P8d-死锁判定",
)


def main() -> None:
    applied, skipped = 0, 0
    for path, old, new, tag in PATCHES:
        if not path.is_file():
            print(f"[MISS] {tag}: 文件不存在 {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if new in text:
            print(f"[SKIP] {tag}: 已是目标状态")
            skipped += 1
            continue
        if old not in text:
            print(f"[FAIL] {tag}: 锚点未命中 {path.name}")
            continue
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        print(f"[OK]   {tag}: {path.name}")
        applied += 1
    print(f"\napplied={applied} skipped={skipped} total={len(PATCHES)}")


if __name__ == "__main__":
    main()
