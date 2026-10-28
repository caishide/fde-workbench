#!/usr/bin/env bash
# ============================================================
# AI 外贸获客系统 · 三库补齐备份
# ============================================================
# 为什么需要：backup-all.sh 覆盖的是 FDE 工作台侧四类数据
#   （Twenty+fde_workbench PG / openfde SQLite / fdeops .fde/ / leads.md），
#   但**没有覆盖 AI 获客系统自己那三个状态点**：
#
#   1. n8n 库（PostgreSQL）—— 工作流定义 + 执行收据链（execution_data）
#   2. Mautic 库（MySQL）  —— 联系人 / 段成员 / 培育配置
#   3. openoutfind SQLite  —— 发现层线索池 + credits 余额
#
# 漏一个的后果各不相同：
#   · n8n 执行数据默认 14 天后被裁（EXECUTIONS_DATA_MAX_AGE=336），
#     收据链断裂后无法回溯"这次执行到底产出了什么"；
#   · Mautic 丢了 = 培育历史与段成员归零，重新养线索成本极高；
#   · openoutfind 丢了 = 池子与余额归零，BetterContact 按次计费会重复扣。
#
# 用法:
#   bash scripts/backup-pipeline.sh            # 正常备份
#   bash scripts/backup-pipeline.sh --verify   # 只校验最近一次备份可恢复性
#
# 产物: /mnt/d/test/FDE/_backup/pipeline-YYYYMMDD-HHMM/
# ⚠️ 必须落在 /mnt/d（Windows 盘）—— WSL 虚拟磁盘不是安全介质。
# ============================================================
set -euo pipefail

# --- 运行环境适配 ---
IN_WSL=0
if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null || [ -n "${WSL_DISTRO_NAME:-}" ]; then
  IN_WSL=1
fi
if [ "$IN_WSL" = "1" ]; then
  DROOT="/mnt/d/test/FDE"
else
  DROOT="/d/test/FDE"
fi

BACKUP_ROOT="${FDE_BACKUP_ROOT:-$DROOT/_backup}"
STAMP="$(date +%Y%m%d-%H%M)"
OUT="$BACKUP_ROOT/pipeline-$STAMP"

# 容器名（来自 /home/caishide/qiflow-outbound/docker-compose.yml）
N8N_DB_CONTAINER="qiflow-n8n-db"
N8N_DB_USER="n8n"
N8N_DB_NAME="n8n"
MAUTIC_DB_CONTAINER="qiflow-mautic-db"
MAUTIC_DB_USER="mautic"
MAUTIC_DB_NAME="mautic"
# mautic 业务账号没有 CREATE DATABASE 权限 → 探针库必须用 root 建，再 GRANT 给业务账号
OPENOUTFIND_CONTAINER="qiflow-openoutfind"
OPENOUTFIND_DATA="/data"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

run_wsl() {
  if [ "$IN_WSL" = "1" ]; then
    bash -lc "$1"
  else
    wsl -e bash -lc "$1"
  fi
}

# ---------------------------------------------------------------
# --verify：活体验证，不是"文件存在即通过"
# ---------------------------------------------------------------
if [ "${1:-}" = "--verify" ]; then
  LATEST="$(ls -1dt "$BACKUP_ROOT"/pipeline-*/ 2>/dev/null | head -1)"
  [ -n "$LATEST" ] || { echo "没有可校验的备份"; exit 1; }
  log "校验最近备份: $LATEST"
  ok=0

  # 1. n8n 库：灌进临时库后数表 + 数执行行
  if [ -s "$LATEST/n8n.sql" ]; then
    if ! tail -c 300 "$LATEST/n8n.sql" | grep -qi "dump complete"; then
      log "  FAIL n8n.sql 缺少收尾标记（dump 截断？）"; ok=1
    fi
    run_wsl "docker exec $N8N_DB_CONTAINER psql -U $N8N_DB_USER -d postgres -c 'DROP DATABASE IF EXISTS _n8n_probe;' -c 'CREATE DATABASE _n8n_probe;'" >/dev/null 2>&1
    if run_wsl "docker exec -i $N8N_DB_CONTAINER psql -U $N8N_DB_USER -d _n8n_probe -v ON_ERROR_STOP=1" < "$LATEST/n8n.sql" >/dev/null 2>&1; then
      T=$(run_wsl "docker exec $N8N_DB_CONTAINER psql -U $N8N_DB_USER -d _n8n_probe -t -A -c \"select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema');\"" 2>/dev/null | tr -d '\000\r\n ')
      E=$(run_wsl "docker exec $N8N_DB_CONTAINER psql -U $N8N_DB_USER -d _n8n_probe -t -A -c 'select count(*) from execution_entity;'" 2>/dev/null | tr -d '\000\r\n ')
      if [ "${T:-0}" -ge 10 ]; then
        log "  OK   n8n 库可恢复（${T} 张表，${E:-?} 条执行记录）"
      else
        log "  FAIL n8n 库恢复后仅 ${T:-0} 张表（期望 ≥10）"; ok=1
      fi
    else
      log "  FAIL n8n 库恢复失败"; ok=1
    fi
    run_wsl "docker exec $N8N_DB_CONTAINER psql -U $N8N_DB_USER -d postgres -c 'DROP DATABASE IF EXISTS _n8n_probe;'" >/dev/null 2>&1
  else
    log "  FAIL n8n.sql 缺失或为空"; ok=1
  fi

  # 2. Mautic 库：灌进临时库后数 leads / lead_lists_leads
  if [ -s "$LATEST/mautic.sql" ]; then
    # 探针库必须用 root 建（mautic 业务账号无 CREATE DATABASE 权限）
    run_wsl "docker exec $MAUTIC_DB_CONTAINER mysql -uroot -p$MAUTIC_ROOT_PASS -e 'DROP DATABASE IF EXISTS _mautic_probe; CREATE DATABASE _mautic_probe; GRANT ALL ON _mautic_probe.* TO \"$MAUTIC_DB_USER\"@\"%\"; FLUSH PRIVILEGES;'" >/dev/null 2>&1
    if run_wsl "docker exec -i $MAUTIC_DB_CONTAINER mysql -u$MAUTIC_DB_USER -p$MAUTIC_DB_PASS _mautic_probe" < "$LATEST/mautic.sql" >/dev/null 2>&1; then
      L=$(run_wsl "docker exec $MAUTIC_DB_CONTAINER mysql -u$MAUTIC_DB_USER -p$MAUTIC_DB_PASS _mautic_probe -N -e 'SELECT COUNT(*) FROM leads;'" 2>/dev/null | tr -d '\000\r\n ')
      S=$(run_wsl "docker exec $MAUTIC_DB_CONTAINER mysql -u$MAUTIC_DB_USER -p$MAUTIC_DB_PASS _mautic_probe -N -e 'SELECT COUNT(*) FROM lead_lists_leads;'" 2>/dev/null | tr -d '\000\r\n ')
      if [ "${L:-0}" -ge 0 ] && [ -n "$L" ]; then
        log "  OK   Mautic 库可恢复（${L} 条 leads，${S:-?} 条段成员）"
      else
        log "  FAIL Mautic 恢复后数不到 leads"; ok=1
      fi
    else
      log "  FAIL Mautic 库恢复失败"; ok=1
    fi
    run_wsl "docker exec $MAUTIC_DB_CONTAINER mysql -uroot -p$MAUTIC_ROOT_PASS -e 'DROP DATABASE IF EXISTS _mautic_probe;'" >/dev/null 2>&1
  else
    log "  FAIL mautic.sql 缺失或为空"; ok=1
  fi

  # 3. openoutfind SQLite：拷出来跑 quick_check
  # ⚠️ 用 find 不用 ls：ls 多个 glob 时只要有一个无匹配就返回非零，会把整个 if 判假
  #    （真实文件名是 db.sqlite3，不是 .db）
  OF_DBS="$(find "$LATEST/openoutfind" -maxdepth 1 -type f \( -name '*.sqlite3' -o -name '*.db' \) 2>/dev/null)"
  if [ -n "$OF_DBS" ]; then
    for DB in $OF_DBS; do
      WDB="${DB/\/d\//\/mnt\/d/}"
      if run_wsl "python3 -c 'import sqlite3,sys; exit(0 if sqlite3.connect(sys.argv[1]).execute(\"PRAGMA quick_check\").fetchone()[0]==\"ok\" else 1)' \"$WDB\"" >/dev/null 2>&1; then
        log "  OK   $(basename "$DB") quick_check 通过"
      else
        log "  FAIL $(basename "$DB") quick_check 不通过"; ok=1
      fi
    done
  else
    log "  WARN openoutfind/ 无 db 文件（首次运行可能还没有状态库）"
  fi

  echo
  [ $ok -eq 0 ] && log "全部通过" || log "存在失败项"
  exit $ok
fi

# ---------------------------------------------------------------
# 正常备份
# ---------------------------------------------------------------
mkdir -p "$OUT"
log "备份目标: $OUT"

# ---- 1. n8n 库（工作流定义 + 执行收据链）----
log "1/3 备份 n8n 库（PostgreSQL）"
if run_wsl "docker exec $N8N_DB_CONTAINER pg_dump -U $N8N_DB_USER -d $N8N_DB_NAME" > "$OUT/n8n.sql" 2>/tmp/n8n_dump.err; then
  [ -s "$OUT/n8n.sql" ] && log "  n8n.sql ($(du -h "$OUT/n8n.sql" | cut -f1))" || { log "  FAIL n8n.sql 为空"; exit 2; }
else
  log "  FAIL n8n dump 失败（错误在 WSL /tmp/n8n_dump.err）"; exit 2
fi

# ---- 2. Mautic 库（联系人 + 段成员 + 培育配置）----
log "2/3 备份 Mautic 库（MySQL）"
if run_wsl "docker exec $MAUTIC_DB_CONTAINER mysqldump -u$MAUTIC_DB_USER -p$MAUTIC_DB_PASS --single-transaction --routines --triggers $MAUTIC_DB_NAME" > "$OUT/mautic.sql" 2>/tmp/mautic_dump.err; then
  [ -s "$OUT/mautic.sql" ] && log "  mautic.sql ($(du -h "$OUT/mautic.sql" | cut -f1))" || { log "  FAIL mautic.sql 为空"; exit 2; }
else
  log "  FAIL Mautic dump 失败（错误在 WSL /tmp/mautic_dump.err）"; exit 2
fi

# ---- 3. openoutfind 状态库（线索池 + credits 余额）----
log "3/3 备份 openoutfind 状态库（SQLite）"
mkdir -p "$OUT/openoutfind"
FOUND=0
# 实际状态库是 /data/db.sqlite3（.openoutfind/ 下只有 onnxruntime 缓存，不是业务库）
# ⚠️ 路径是**容器内**路径，宿主侧不存在 → 存在性检查必须在容器内做，
#    否则 [ -f ] 永远为假，备份会静默跳过（这正是第一次跑没拷到的原因）。
for db in "$OPENOUTFIND_DATA/db.sqlite3" "$OPENOUTFIND_DATA"/*.sqlite3 "$OPENOUTFIND_DATA"/*.db; do
  if ! run_wsl "docker exec $OPENOUTFIND_CONTAINER test -f '$db'" >/dev/null 2>&1; then
    continue
  fi
  base="$(basename "$db")"
  if ! run_wsl "docker cp $OPENOUTFIND_CONTAINER:$db /mnt/d/test/FDE/_backup/.tmp_of_$base" >/dev/null 2>&1; then
    log "  WARN 拷贝失败: $db"
    continue
  fi
  FOUND=1
  mv "$DROOT/_backup/.tmp_of_$base" "$OUT/openoutfind/$base"
  log "  $base ($(du -h "$OUT/openoutfind/$base" | cut -f1))"
done
if [ "$FOUND" = "0" ]; then
  log "  WARN 未找到 openoutfind 状态库（首次运行可能还没有）"
fi

# ---- 留存策略：只留最近 N 份，避免 D 盘被撑爆 ----
KEEP="${PIPELINE_BACKUP_KEEP:-8}"
log "清理旧备份（只留最近 $KEEP 份）"
ls -1dt "$BACKUP_ROOT"/pipeline-*/ 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
  rm -rf "$old"
  log "  已删除 $(basename "$old")"
done

log "完成：$OUT"
exit 0
