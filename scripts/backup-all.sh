#!/usr/bin/env bash
# ============================================================
# 统一备份脚本：一次备份本机全部四类持久化数据
# ============================================================
# 为什么需要：v0.2 PG 迁移后机器上有 4 个数据点，备份不能各记各的
#   （漏一个 = 静默丢数据）。本脚本把四处收敛成一次执行 + 一个校验口径。
#
#   1. PostgreSQL（Twenty 库 + fde_workbench 库，同一实例）
#   2. SQLite（openfde 知识轨）
#   3. 目录文件（fdeops 流程轨 .fde/ + fde-storage）
#   4. leads.md（根目录线索唯一真相——不入 git，只能靠备份）
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

# --- 运行环境适配 ---
# 脚本可能从 Windows（Git Bash）或 WSL 内部被调用。
# WSL 内部调用时不能再套 `wsl -e bash -lc`（会报 command not found，退出码 127）。
IN_WSL=0
if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null || [ -n "${WSL_DISTRO_NAME:-}" ]; then
  IN_WSL=1
fi
# 路径按运行环境切换：Windows Git Bash 用 /d/...，WSL 内部用 /mnt/d/...
if [ "$IN_WSL" = "1" ]; then
  DROOT="/mnt/d/test/FDE"
else
  DROOT="/d/test/FDE"
fi

BACKUP_ROOT="${FDE_BACKUP_ROOT:-$DROOT/_backup}"
STAMP="$(date +%Y%m%d-%H%M)"
OUT="$BACKUP_ROOT/$STAMP"
PG_CONTAINER="qiflow-twenty-db"
PG_USER="twenty"
# openfde 不是单一 sqlite 文件：每个 engagement 一个 ledger.db
# 真身在 D 盘（D:\test\FDE\engagements\openfde），C 盘 ~/.openfde 是 symlink 指针
OPENFDE_ROOT="$DROOT/engagements/openfde/engagements"
FDEOPS_ROOT="$DROOT/engagements/fdeops"
LEADS_MD="$DROOT/leads.md"
LEADS_DIR="$DROOT/leads"
# fde-storage 在本仓库（脚本随仓库走，按脚本位置定位，不写死绝对路径）
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FDE_STORAGE="$REPO_ROOT/server/.fde-storage"

log() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

# run_wsl <cmd>：在 WSL 内部直接跑，在 Windows 侧则套一层 wsl -e bash -lc
# （IN_WSL 判定见文件上方）
run_wsl() {
  if [ "$IN_WSL" = "1" ]; then
    bash -lc "$1"
  else
    wsl -e bash -lc "$1"
  fi
}



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
  if [ -s "$LATEST/leads.md" ]; then
    log "  OK   leads.md ($(wc -l < "$LATEST/leads.md" | tr -d ' ') 行)"
  else
    log "  WARN leads.md 缺失（2026-10-25 之前的旧备份无此项属正常）"
  fi
  # leads/ 售前资料层：解包后数文件（不是"文件在就算过"）
  if [ -s "$LATEST/leads-dir.tgz" ]; then
    if tar -tzf "$LATEST/leads-dir.tgz" >/dev/null 2>&1; then
      NF=$(tar -tzf "$LATEST/leads-dir.tgz" | grep -vc '/$' || true)
      log "  OK   leads-dir.tgz 可解包（${NF:-?} 个文件）"
    else
      log "  FAIL leads-dir.tgz 解包失败"; ok=1
    fi
  else
    log "  WARN leads-dir.tgz 缺失（2026-10-27 之前的旧备份无此项属正常）"
  fi
  # --- AI 获客系统三库（本卡 (b) 项：backup-all.sh 自己也要覆盖）---
  # n8n PG 库：灌进临时库后数表 + 数执行行
  if [ -s "$LATEST/n8n.sql" ]; then
    if ! tail -c 300 "$LATEST/n8n.sql" | grep -qi "dump complete"; then
      log "  FAIL n8n.sql 缺少收尾标记（dump 截断？）"; ok=1
    fi
    run_wsl "docker exec qiflow-n8n-db psql -U n8n -d postgres -c 'DROP DATABASE IF EXISTS _n8n_probe;' -c 'CREATE DATABASE _n8n_probe;'" >/dev/null 2>&1
    if run_wsl "docker exec -i qiflow-n8n-db psql -U n8n -d _n8n_probe -v ON_ERROR_STOP=1" < "$LATEST/n8n.sql" >/dev/null 2>&1; then
      T=$(run_wsl "docker exec qiflow-n8n-db psql -U n8n -d _n8n_probe -t -A -c \"select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema');\"" 2>/dev/null | tr -d '\000\r\n ')
      E=$(run_wsl "docker exec qiflow-n8n-db psql -U n8n -d _n8n_probe -t -A -c 'select count(*) from execution_entity;'" 2>/dev/null | tr -d '\000\r\n ')
      if [ "${T:-0}" -ge 10 ]; then
        log "  OK   n8n 库可恢复（${T} 张表，${E:-?} 条执行记录）"
      else
        log "  FAIL n8n 库恢复后仅 ${T:-0} 张表（期望 ≥10）"; ok=1
      fi
    else
      log "  FAIL n8n 库恢复失败"; ok=1
    fi
    run_wsl "docker exec qiflow-n8n-db psql -U n8n -d postgres -c 'DROP DATABASE IF EXISTS _n8n_probe;'" >/dev/null 2>&1
  else
    log "  FAIL n8n.sql 缺失或为空"; ok=1
  fi
  # Mautic MySQL 库：灌进临时库后数 leads / lead_lists_leads
  if [ -s "$LATEST/mautic.sql" ]; then
    # 探针库必须用 root 建（mautic 业务账号无 CREATE DATABASE 权限）
    run_wsl "docker exec qiflow-mautic-db mysql -uroot -pc35dd8a933a1fc7b7b6a49906e68abb223456550f2843899 -e 'DROP DATABASE IF EXISTS _mautic_probe; CREATE DATABASE _mautic_probe; GRANT ALL ON _mautic_probe.* TO \"mautic\"@\"%\"; FLUSH PRIVILEGES;'" >/dev/null 2>&1
    if run_wsl "docker exec -i qiflow-mautic-db mysql -umautic -p672a9e548886b70aa564c97756d4d72f1fdb1ff4b9fb7366 _mautic_probe" < "$LATEST/mautic.sql" >/dev/null 2>&1; then
      L=$(run_wsl "docker exec qiflow-mautic-db mysql -umautic -p672a9e548886b70aa564c97756d4d72f1fdb1ff4b9fb7366 _mautic_probe -N -e 'SELECT COUNT(*) FROM leads;'" 2>/dev/null | tr -d '\000\r\n ')
      S=$(run_wsl "docker exec qiflow-mautic-db mysql -umautic -p672a9e548886b70aa564c97756d4d72f1fdb1ff4b9fb7366 _mautic_probe -N -e 'SELECT COUNT(*) FROM lead_lists_leads;'" 2>/dev/null | tr -d '\000\r\n ')
      if [ -n "$L" ]; then
        log "  OK   Mautic 库可恢复（${L} 条 leads，${S:-?} 条段成员）"
      else
        log "  FAIL Mautic 恢复后数不到 leads"; ok=1
      fi
    else
      log "  FAIL Mautic 库恢复失败"; ok=1
    fi
    run_wsl "docker exec qiflow-mautic-db mysql -uroot -pc35dd8a933a1fc7b7b6a49906e68abb223456550f2843899 -e 'DROP DATABASE IF EXISTS _mautic_probe;'" >/dev/null 2>&1
  else
    log "  FAIL mautic.sql 缺失或为空"; ok=1
  fi
  # openoutfind SQLite：quick_check
  # ⚠️ 用 find 不用 ls：ls 多个 glob 时只要有一个无匹配就返回非零，会把整个 if 判假
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
  # 真恢复性验证（活体：灌进本实例的探针库再数表）。
  # 三条口令纪律，缺一就是「假通过」：
  #   1) psql 带 -v ON_ERROR_STOP=1——否则 dump 中段损坏 psql 照样退出 0，
  #      老校验就是这么年复一年「通过」的；
  #   2) 按 \connect 分段、每库灌各的探针库——fde fork 与 twenty 同源有同名表
  #      （ai_chat_turns），合灌同一个探针库必撞 already-exists；
  #   3) 剔除角色 DDL——CREATE ROLE 撞活实例已存在角色。代价：验证聚焦
  #      schema+data 可恢复性，角色完整性由 dump-complete 收尾标记兜底。
  log "恢复性验证：按库分段灌探针（ON_ERROR_STOP）"
  if [ -s "$LATEST/pg_all.sql" ]; then
    # dump 收尾标记：截断的 dump（磁盘满/中途中死）没有这行
    if ! tail -c 200 "$LATEST/pg_all.sql" | grep -q "PostgreSQL database dump complete"; then
      log "  FAIL pg_all.sql 缺少收尾标记（dump 截断？）"; ok=1
    fi
    SPLIT="$LATEST/.pg_split"
    rm -rf "$SPLIT"; mkdir -p "$SPLIT"
    # 用字符串比较不用正则：\connect 的反斜杠在 Git Bash awk / gawk / busybox awk
    # 三家的正则转义行为不一致（\\c 在 MSYS awk 会告警不匹配），substr 判前缀最稳。
    awk -v dir="$SPLIT" '
      {
        if (substr($0, 1, 9) == "\\connect ") {
          name = substr($0, 10)
          if (name == "twenty" || name == "fde_workbench") { sec = name; next }
          sec = ""  # template1/postgres 等中间分段（含 CREATE DATABASE 行）不采集
          next
        }
        if (sec != "") print > (dir "/" sec ".sql")
      }
    ' "$LATEST/pg_all.sql"
    for DBNAME in twenty fde_workbench; do
      SEC="$SPLIT/$DBNAME.sql"
      if [ ! -s "$SEC" ]; then
        log "  FAIL dump 里没有 $DBNAME 分段"; ok=1; continue
      fi
      # ⚠️ ALTER DATABASE 有坑：dump 里除了主库，还可能残留测试库语句
      #   （实测 `ALTER DATABASE fde_workbench_test OWNER TO fde;`）
      #   旧的 sed 前缀替换会把它改成 `ALTER DATABASE _restore_probe_test`，
      #   而探针库里没有这个库 → ON_ERROR_STOP 直接中止，整个分段判失败。
      # 处置：探针恢复不需要改库属主，全部剥离（角色完整性由 dump 收尾标记兜底）。
      grep -vE '^(CREATE ROLE |ALTER ROLE |COMMENT ON ROLE |CREATE DATABASE )' "$SEC" \
        | sed -e 's/^ALTER DATABASE .* OWNER TO .*;$/-- ALTER DATABASE OWNER stripped (probe restore)/' \
            -e "s/ON DATABASE $DBNAME/ON DATABASE _restore_probe/g" \
            -e "s/ALTER DATABASE $DBNAME/ALTER DATABASE _restore_probe/g" \
        > "$SEC.probe"
      run_wsl "docker exec $PG_CONTAINER psql -U $PG_USER -d postgres -c 'DROP DATABASE IF EXISTS _restore_probe;' -c 'CREATE DATABASE _restore_probe;'" >/dev/null 2>&1
      if run_wsl "docker exec -i $PG_CONTAINER psql -U $PG_USER -d _restore_probe -v ON_ERROR_STOP=1" < "$SEC.probe" 2> "$SPLIT/$DBNAME.restore.err" >/dev/null; then
        TABLES=$(run_wsl "docker exec $PG_CONTAINER psql -U $PG_USER -d _restore_probe -t -A -c \"select count(*) from information_schema.tables where table_schema not in ('pg_catalog','information_schema');\"" 2>/dev/null | tr -d '\000\r\n ')
        case "$DBNAME" in
          twenty)        FLOOR=100 ;;
          fde_workbench) FLOOR=60  ;;
        esac
        if [ "${TABLES:-0}" -ge "$FLOOR" ]; then
          log "  OK   $DBNAME 分段可恢复（${TABLES} 张表）"
        else
          log "  WARN $DBNAME 恢复后仅 ${TABLES:-0} 张表（期望 ≥$FLOOR），内容可能不完整"; ok=1
        fi
      else
        log "  FAIL $DBNAME 分段恢复失败（ON_ERROR_STOP 中止），首条错误："
        # -a + 去 NUL：psql 报错夹着中文数据字节时 grep 会当二进制拒读
        tr -d '\000' < "$SPLIT/$DBNAME.restore.err" | grep -a -m 3 '^ERROR' | while IFS= read -r line; do log "    $line"; done
        ok=1
      fi
      rm -f "$SEC.probe" "$SPLIT/$DBNAME.restore.err"
    done
    rm -rf "$SPLIT"
  elif [ -s "$LATEST/pg_fde_workbench.sql" ]; then
    # 分库 fallback 布局：逐库验证（pg_dump 纯 schema+data，直接灌探针库）
    for DBNAME in twenty fde_workbench; do
      DUMP="$LATEST/pg_$DBNAME.sql"
      [ -s "$DUMP" ] || { log "  FAIL pg_$DBNAME.sql 缺失"; ok=1; continue; }
      run_wsl "docker exec $PG_CONTAINER psql -U $PG_USER -d postgres -c 'DROP DATABASE IF EXISTS _restore_probe;' -c 'CREATE DATABASE _restore_probe;'" >/dev/null 2>&1
      if run_wsl "docker exec -i $PG_CONTAINER psql -U $PG_USER -d _restore_probe -v ON_ERROR_STOP=1" < "$DUMP" >/dev/null 2>&1; then
        log "  OK   pg_$DBNAME.sql 可恢复"
      else
        log "  FAIL pg_$DBNAME.sql 恢复失败"; ok=1
      fi
    done
  else
    log "  FAIL 没有 PG dump 可验证（pg_all.sql 与分库文件都缺失）"; ok=1
  fi
  run_wsl "docker exec $PG_CONTAINER psql -U $PG_USER -d postgres -c 'DROP DATABASE IF EXISTS _restore_probe;'" >/dev/null 2>&1
  # SQLite 备份件完整性：每个 ledger.db 跑 quick_check
  if [ -d "$LATEST/openfde" ] && [ -n "$(ls -A "$LATEST/openfde" 2>/dev/null)" ]; then
    for DB in "$LATEST"/openfde/*.db; do
      WDB="${DB/\/d\//\/mnt\/d/}"
      if run_wsl "python3 -c 'import sqlite3,sys; exit(0 if sqlite3.connect(sys.argv[1]).execute(\"PRAGMA quick_check\").fetchone()[0]==\"ok\" else 1)' \"$WDB\"" >/dev/null 2>&1; then
        log "  OK   $(basename "$DB") quick_check 通过"
      else
        log "  FAIL $(basename "$DB") quick_check 不通过"; ok=1
      fi
    done
  fi
  exit $ok
fi

mkdir -p "$OUT"
log "备份目标: $OUT"

# ---- 1. PostgreSQL：Twenty 库 + fde_workbench 库（同一实例，一次 pg_dumpall 更稳）----
log "1/6 备份 PostgreSQL（Twenty + fde_workbench）"
run_wsl "docker exec $PG_CONTAINER pg_dumpall -U $PG_USER" > "$OUT/pg_all.sql" 2>/tmp/pg_dumpall.err || {
  log "pg_dumpall 失败（错误在 WSL /tmp/pg_dumpall.err），改为分库 dump"
  run_wsl "docker exec $PG_CONTAINER pg_dump -U $PG_USER twenty" > "$OUT/pg_twenty.sql" || { log "  FAIL pg_dump twenty"; exit 2; }
  run_wsl "docker exec $PG_CONTAINER pg_dump -U $PG_USER fde_workbench" > "$OUT/pg_fde_workbench.sql" || { log "  FAIL pg_dump fde_workbench"; exit 2; }
}
[ -s "$OUT/pg_all.sql" ] && log "  pg_all.sql ($(du -h "$OUT/pg_all.sql" | cut -f1))"

# ---- 2. SQLite：openfde 知识轨 ----
log "2/6 备份 SQLite（openfde 每 engagement 一个 ledger.db）"
SQLITE_FAIL=0
if [ -d "$OPENFDE_ROOT" ]; then
  mkdir -p "$OUT/openfde"
  # 走 Windows-native python 做在线备份：WSL 的 DrvFS 文件系统层给不了 SQLite
  # 在线备份所需的文件锁语义，经 WSL python 调 .backup() 会间歇性失败（即便源库
  # quick_check 通过）。Windows-native python 直接开 NTFS 文件则稳定成功。
  # 把 ledger.db 备份成 <engagement>.db，放在 $OUT/openfde/ 下（与原布局一致）。
  # 路径转换交给 helper（Python）处理：WSL 可能把 D: 挂成 /mnt/d/ 或 /d/，
  # bash sed 的 \U 对 /d/ 形态会吞掉前导斜杠，故不在 shell 层做转换。
  if run_wsl "cmd.exe /c python3 D:/test/FDE/scripts/backup_openfde_ledger.py \"$OPENFDE_ROOT\" \"$OUT/openfde\""; then
    log "  openfde 知识轨: $(du -sh "$OUT/openfde" | cut -f1)"
  else
    log "  FAIL openfde 知识轨在线备份失败（可能被写锁占用，继续）"; SQLITE_FAIL=1
  fi
  # 兼容：若上面的 helper 因 cmd.exe 不可用而失败，回退到 WSL python 逐库备份
  if [ "$SQLITE_FAIL" != "0" ]; then
    SQLITE_FAIL=0
    for db in "$OPENFDE_ROOT"/*/ledger.db; do
      [ -f "$db" ] || continue
      slug="$(basename "$(dirname "$db")")"
      WDB="${db/\/d\//\/mnt\/d/}"
      WOUT="${OUT/\/d\//\/mnt\/d/}"
      rm -f "$OUT/openfde/$slug.db"   # 先清掉可能残留的 0 字节文件
      if run_wsl "python3 -c 'import sqlite3,sys; sqlite3.connect(sys.argv[1]).backup(sqlite3.connect(sys.argv[2]))' \"$WDB\" \"$WOUT/openfde/$slug.db\"" \
         && [ -s "$OUT/openfde/$slug.db" ]; then
        log "  $slug.db ($(du -h "$OUT/openfde/$slug.db" | cut -f1))"
      else
        log "  FAIL $slug.db 在线备份失败（可能被写锁占用，继续）"; SQLITE_FAIL=1
      fi
    done
  fi
  # 不中断：继续跑完剩下的步骤，最后统一以非零码退出（若确有失败）
  if [ "$SQLITE_FAIL" != "0" ]; then
    log "  WARN 有 SQLite 备份失败，MANIFEST 已记录 sqlite_fail=$SQLITE_FAIL"
  fi
else
  log "  跳过：$OPENFDE_ROOT 未找到（openfde 真身路径可能已变）"
fi

# ---- 3. 目录：fdeops 流程轨 ----
log "3/6 备份目录（fdeops .fde/）"
if [ -d "$FDEOPS_ROOT" ]; then
  mkdir -p "$OUT/fdeops"
  # 排除 .git（体积大且可重建），保留全部台账正文
  (cd "$FDEOPS_ROOT" && tar -czf "$OUT/fdeops/fdeops-ledger.tgz" --exclude='.git' .)
  log "  fdeops-ledger.tgz ($(du -h "$OUT/fdeops/fdeops-ledger.tgz" | cut -f1))"
else
  log "  跳过：$FDEOPS_ROOT 未找到"
fi

# ---- 4. fde-storage（上传件与生成物）----
log "4/6 备份 fde-storage"
if [ -d "$FDE_STORAGE" ]; then
  (cd "$FDE_STORAGE" && tar -czf "$OUT/fde-storage.tgz" . 2>/dev/null) || log "  跳过：存储目录读取异常"
  log "  fde-storage.tgz"
fi

# ---- 5. leads.md（线索唯一真相：不入 git，丢了没处找）----
# 2026-10-27 补：leads/ 目录（售前资料层：forms/ 结构化表单 + raw/ 企业问卷原件）
# 也在备份范围内。leads.md 只是索引，真需求卡七项、问卷原件都在 leads/ 里，
# 只备份 leads.md = 备份了目录没备份内容（静默丢数据）。
log "5/6 备份 leads.md"
if [ -f "$LEADS_MD" ]; then
  cp "$LEADS_MD" "$OUT/leads.md"
  log "  leads.md ($(du -h "$OUT/leads.md" | cut -f1))"
else
  log "  跳过：$LEADS_MD 未找到"
fi

log "5b/6 备份 leads/ 目录（售前资料层）"
if [ -d "$LEADS_DIR" ]; then
  (cd "$LEADS_DIR" && tar -czf "$OUT/leads-dir.tgz" . 2>/dev/null) && \
    log "  leads-dir.tgz ($(du -h "$OUT/leads-dir.tgz" | cut -f1), $(find "$LEADS_DIR" -type f | wc -l) 个文件)" || \
    log "  WARN leads/ 打包失败"
else
  log "  跳过：$LEADS_DIR 未找到（S0-S2 无售前资料时属正常）"
fi

# ---- 6. AI 获客系统三库（n8n PG / Mautic MySQL / openoutfind SQLite）----
# 这三处是「AI 外贸获客工作台」自己的状态点，不属于 FDE 工作台，
# 但它们是同一条业务链上的下游 —— 漏掉 = 获客系统整体回退到零。
#   · n8n 库   → 工作流定义 + 执行收据链（execution_data）
#   · Mautic   → 联系人 / 段成员 / 培育配置
#   · openoutfind → 线索池 + BetterContact 余额
# 逐项失败不阻断整体备份（备份脚本要能带伤跑完），但会写进 MANIFEST 供 --verify 查。
log "6/6 备份 AI 获客系统三库（n8n / Mautic / openoutfind）"
PIPELINE_FAIL=0
N8N_DB_CONTAINER="qiflow-n8n-db"
N8N_DB_USER="n8n"
MAUTIC_DB_CONTAINER="qiflow-mautic-db"
MAUTIC_DB_USER="mautic"
MAUTIC_DB_NAME="mautic"
OPENOUTFIND_CONTAINER="qiflow-openoutfind"

if run_wsl "docker exec $N8N_DB_CONTAINER pg_dump -U $N8N_DB_USER -d n8n" > "$OUT/n8n.sql" 2>/dev/null && [ -s "$OUT/n8n.sql" ]; then
  log "  n8n.sql ($(du -h "$OUT/n8n.sql" | cut -f1))"
else
  log "  FAIL n8n 库备份失败"; PIPELINE_FAIL=1
fi

if run_wsl "docker exec $MAUTIC_DB_CONTAINER mysqldump -u$MAUTIC_DB_USER -p$MAUTIC_DB_PASS --single-transaction $MAUTIC_DB_NAME" > "$OUT/mautic.sql" 2>/dev/null && [ -s "$OUT/mautic.sql" ]; then
  log "  mautic.sql ($(du -h "$OUT/mautic.sql" | cut -f1))"
else
  log "  FAIL Mautic 库备份失败"; PIPELINE_FAIL=1
fi

mkdir -p "$OUT/openoutfind"
OF_FOUND=0
for db in /data/db.sqlite3 /data/*.sqlite3; do
  # 路径是**容器内**路径，宿主侧不存在 → 存在性检查必须在容器内做
  run_wsl "docker exec $OPENOUTFIND_CONTAINER test -f '$db'" >/dev/null 2>&1 || continue
  base="$(basename "$db")"
  if run_wsl "docker cp $OPENOUTFIND_CONTAINER:$db /mnt/d/test/FDE/_backup/.tmp_of_$base" >/dev/null 2>&1; then
    mv "$DROOT/_backup/.tmp_of_$base" "$OUT/openoutfind/$base"
    log "  openoutfind/$base ($(du -h "$OUT/openoutfind/$base" | cut -f1))"
    OF_FOUND=1
  fi
done
[ "$OF_FOUND" = "0" ] && log "  WARN openoutfind 状态库未找到（首次运行可能还没有）"

# ---- 清单 ----
cat > "$OUT/MANIFEST.txt" <<EOF
backup_stamp: $STAMP
created_at:   $(date -Is)
host:         $(hostname)
pg_container: $PG_CONTAINER
pg_dbs:       twenty, fde_workbench, n8n
mysql:        mautic (AI 获客系统联系人/段成员/培育配置)
sqlite:       openfde/engagements/*/ledger.db（每 engagement 一个）,
              openoutfind/db.sqlite3（AI 获客线索池 + credits 余额）
dirs:         fdeops (.fde), fde-storage
files:        leads.md（根仓线索唯一真相，不入 git）
pipeline_fail: $PIPELINE_FAIL（0=三库全备份成功；1=有失败项，查 --verify）
sqlite_fail:  $SQLITE_FAIL（0=openfde 全库备份成功；1=有失败项，多为写锁占用，重跑 backup-pipeline.sh 或等锁释放后重跑本脚本）
note:         Redis 不入备份（队列是易态数据，job 真身在 PG 的 background_jobs 表）
EOF

log "完成: $OUT"
log "下一步：bash scripts/backup-all.sh --verify  （验证可恢复性，别跳过）"

# 全部步骤跑完后才以非零码收口：带伤跑完比中途夭折好
FINAL_RC=0
[ "$PIPELINE_FAIL" = "0" ] || FINAL_RC=2
[ "$SQLITE_FAIL" = "0" ] || FINAL_RC=2
if [ "$FINAL_RC" != "0" ]; then
  log "存在失败项（见上），已把本次产物保留在 $OUT"
fi
exit $FINAL_RC
