#!/usr/bin/env bash
# ============================================================
# 统一备份脚本：一次备份本机全部三类持久化数据
# ============================================================
# 为什么需要：v0.2 PG 迁移后机器上有 3 个数据点，备份不能各记各的
#   （漏一个 = 静默丢数据）。本脚本把三处收敛成一次执行 + 一个校验口径。
#
#   1. PostgreSQL（Twenty 库 + fde_workbench 库，同一实例）
#   2. SQLite（openfde 知识轨）
#   3. 目录文件（fdeops 流程轨 .fde/ + fde-storage）
#
# 用法:
#   bash scripts/backup-all.sh            # 正常备份
#   bash scripts/backup-all.sh --verify   # 只校验最近一次备份可恢复性
#
# 产物: /mnt/d/test/FDE/_backup/YYYYMMDD-HHMM/
# ⚠️ 必须落在 /mnt/d（Windows 盘）或网盘 —— WSL 虚拟磁盘不是安全介质，
#    WSL 重装/系统重装会连数据一起没。没验过的备份等于没备份。
# ============================================================
set -euo pipefail

BACKUP_ROOT="${FDE_BACKUP_ROOT:-/mnt/d/test/FDE/_backup}"
STAMP="$(date +%Y%m%d-%H%M)"
OUT="$BACKUP_ROOT/$STAMP"
PG_CONTAINER="qiflow-twenty-db"
PG_USER="twenty"
# openfde 不是单一 sqlite 文件：每个 engagement 一个 ledger.db
# 真身在 D 盘（D://test//FDE//engagements//openfde），C 盘 \.openfde 是 symlink 指针
OPENFDE_ROOT="/d/test/FDE/engagements/openfde/engagements"
FDEOPS_ROOT="/d/test/FDE/engagements/fdeops"
FDE_STORAGE="/mnt/d/test/FDE/_eval/fde-workbench/server/.fde-storage"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

if [ "${1:-}" = "--verify" ]; then
  LATEST="$(ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | head -1)"
  [ -n "$LATEST" ] || { echo "没有可校验的备份"; exit 1; }
  log "校验最近备份: $LATEST"
  ok=0
  for f in pg_all.sql; do
    if [ -s "$LATEST/$f" ]; then
      log "  OK   $f ($(du -h "$LATEST/$f" | cut -f1))"
    else
      log "  FAIL $f 缺失或为空"; ok=1
    fi
  done
  if [ -d "$LATEST/openfde" ] && [ -n "$(ls -A "$LATEST/openfde" 2>/dev/null)" ]; then
    log "  OK   openfde/ ($(ls -1 "$LATEST/openfde" | wc -l) 个 engagement 库)"
  else
    log "  FAIL openfde/ 为空"; ok=1
  fi
  if [ -d "$LATEST/fdeops" ] && [ -n "$(ls -A "$LATEST/fdeops" 2>/dev/null)" ]; then
    log "  OK   fdeops/ ($(find "$LATEST/fdeops" -type f | wc -l) 个文件)"
  else
    log "  FAIL fdeops/ 为空"; ok=1
  fi
  echo
  # 真恢复性验证：pg_dumpall 是全实例 dump（含 CREATE DATABASE 与 \connect），
  # 直接灌进已建好的临时库会因为库已存在而报错。改为：
  #   1) 灌进 postgres 库（让 dump 自带的 CREATE DATABASE 生效）
  #   2) 再逐库查表数量
  log "恢复性验证：pg_dumpall 灌入实例（含 CREATE DATABASE）"
  wsl -e bash -lc "docker exec $PG_CONTAINER psql -U $PG_USER -d postgres -c 'DROP DATABASE IF EXISTS _restore_probe;'" >/dev/null 2>&1
  # 把 dump 里的库名改成探针名，避免覆盖真实库
  sed -e 's/\\connect twenty/\\connect _restore_probe/g' \
      -e 's/\\connect fde_workbench/\\connect _restore_probe/g' \
      -e 's/CREATE DATABASE twenty/CREATE DATABASE _restore_probe/g' \
      -e 's/CREATE DATABASE fde_workbench/CREATE DATABASE _restore_probe/g' \
      "$LATEST/pg_all.sql" > "$LATEST/.pg_probe.sql"
  if wsl -e bash -lc "docker exec -i $PG_CONTAINER psql -U $PG_USER -d postgres" < "$LATEST/.pg_probe.sql" >/dev/null 2>&1; then
    TABLES=$(wsl -e bash -lc "docker exec $PG_CONTAINER psql -U $PG_USER -d _restore_probe -t -c \"select count(*) from information_schema.tables where table_schema='public';\"" 2>/dev/null | tr -d '\000\r\n ')
    log "  OK   pg_all.sql 可恢复，_restore_probe public schema 有 ${TABLES} 张表"
    if [ "${TABLES:-0}" -lt 60 ]; then
      log "  WARN 期望 >=60 张表（实测 66），恢复内容可能不完整"; ok=1
    fi
  else
    log "  FAIL pg_all.sql 恢复失败"; ok=1
  fi
  wsl -e bash -lc "docker exec $PG_CONTAINER psql -U $PG_USER -d postgres -c 'DROP DATABASE IF EXISTS _restore_probe;'" >/dev/null 2>&1
  rm -f "$LATEST/.pg_probe.sql"
  exit $ok
fi

mkdir -p "$OUT"
log "备份目标: $OUT"

# ---- 1. PostgreSQL：Twenty 库 + fde_workbench 库（同一实例，一次 pg_dumpall 更稳）----
log "1/4 备份 PostgreSQL（Twenty + fde_workbench）"
wsl -e bash -lc "docker exec $PG_CONTAINER pg_dumpall -U $PG_USER" > "$OUT/pg_all.sql" 2>/tmp/pg_dumpall.err || {
  log "pg_dumpall 失败，改为分库 dump"
  wsl -e bash -lc "docker exec $PG_CONTAINER pg_dump -U $PG_USER twenty" > "$OUT/pg_twenty.sql"
  wsl -e bash -lc "docker exec $PG_CONTAINER pg_dump -U $PG_USER fde_workbench" > "$OUT/pg_fde_workbench.sql"
}
[ -s "$OUT/pg_all.sql" ] && log "  pg_all.sql ($(du -h "$OUT/pg_all.sql" | cut -f1))"

# ---- 2. SQLite：openfde 知识轨 ----
log "2/4 备份 SQLite（openfde 每 engagement 一个 ledger.db）"
if [ -d "$OPENFDE_ROOT" ]; then
  mkdir -p "$OUT/openfde"
  for db in "$OPENFDE_ROOT"/*/ledger.db; do
    [ -f "$db" ] || continue
    slug="$(basename "$(dirname "$db")")"
    cp "$db" "$OUT/openfde/$slug.db"
    log "  $slug.db ($(du -h "$OUT/openfde/$slug.db" | cut -f1))"
  done
else
  log "  跳过：$OPENFDE_ROOT 未找到（openfde 真身路径可能已变）"
fi

# ---- 3. 目录：fdeops 流程轨 ----
log "3/4 备份目录（fdeops .fde/）"
if [ -d "$FDEOPS_ROOT" ]; then
  mkdir -p "$OUT/fdeops"
  # 排除 .git（体积大且可重建），保留全部台账正文
  (cd "$FDEOPS_ROOT" && tar -czf "$OUT/fdeops/fdeops-ledger.tgz" --exclude='.git' .)
  log "  fdeops-ledger.tgz ($(du -h "$OUT/fdeops/fdeops-ledger.tgz" | cut -f1))"
else
  log "  跳过：$FDEOPS_ROOT 未找到"
fi

# ---- 4. fde-storage（上传件与生成物）----
log "4/4 备份 fde-storage"
if [ -d "$FDE_STORAGE" ]; then
  (cd "$FDE_STORAGE" && tar -czf "$OUT/fde-storage.tgz" . 2>/dev/null) || log "  跳过：存储目录读取异常"
  log "  fde-storage.tgz"
fi

# ---- 清单 ----
cat > "$OUT/MANIFEST.txt" <<EOF
backup_stamp: $STAMP
created_at:   $(date -Is)
host:         $(hostname)
pg_container: $PG_CONTAINER
pg_dbs:       twenty, fde_workbench
sqlite:       openfde/engagements/*/ledger.db（每 engagement 一个）
dirs:         fdeops (.fde), fde-storage
note:         Redis 不入备份（队列是易态数据，job 真身在 PG 的 background_jobs 表）
EOF

log "完成: $OUT"
log "下一步：bash scripts/backup-all.sh --verify  （验证可恢复性，别跳过）"
