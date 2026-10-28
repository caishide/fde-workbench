#!/usr/bin/env bash
# ============================================================
# 代号化校验（P1 验收项；R3 缓解措施；goal-r2 WP25/H2 收紧软失败）
# ============================================================
# 干什么：证明 fde_workbench 库里没有客户明文。
#   1. 全库 dump（data-only）后正则扫：手机号 / 18 位身份证号 / 邮箱
#   2. 黑名单：leads.md 里出现过的真实企业名（「公司/集团/厂」结尾 token）
#      一个都不允许出现在库里；黑名单提取 0 条 = 扫描失效，FAIL
#   3. projects.enterprise_code 格式检查（「客户A·行业·城市」→ 两枚「·」）WARN
#   4. projects 表 0 行 = 空库扫描 = 没扫，FAIL（C-8b；CI 须先迁移+灌合成数据）
#
# 判级：
#   手机号 / 身份证 / 企业名命中 → FAIL（exit 1）
#   邮箱命中 → 按 FDE_PSEUDONYM_EMAIL_POLICY：缺省 fail（CI 从严，客户邮箱也是
#   泄漏）；设 warn 时降级为 WARN 但结论行列出命中行数（C-8f：WARN 不是 PASS 的
#   遮羞布）；取值非法 → exit 2
#   grep/psql 执行错误（退出码 ≥2）→ FAIL，不许吞成「0 行成功」（C-8c）
#
# 自测模式：--self-test 注入哨兵行（假手机号+假身份证+假邮箱），要求三个模式
#   **逐个**被抓到（抓不到哪个=哪个模式坏了，exit 2），再清理重扫。
#   「没验过的备份等于没备份」同理：没自测过的校验器等于没有校验器。
#
# 用法:
#   bash scripts/check-pseudonymization.sh              # 正常校验
#   bash scripts/check-pseudonymization.sh --self-test  # 先验证扫描器灵敏度
# ============================================================
set -uo pipefail

EMAIL_POLICY="${FDE_PSEUDONYM_EMAIL_POLICY:-fail}"
case "$EMAIL_POLICY" in
  warn | fail) ;;
  *)
    echo "FAIL FDE_PSEUDONYM_EMAIL_POLICY 取值非法：$EMAIL_POLICY（允许 warn|fail，缺省 fail）"
    exit 2
    ;;
esac

IN_WSL=0
if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null || [ -n "${WSL_DISTRO_NAME:-}" ]; then
  IN_WSL=1
fi
# I3：默认路径不写死本机盘符——按「仓库所在盘 → /mnt/<盘>/test/FDE」推导，
# 仍可用 FDE_LEADS_MD 显式指定；推导不出就用仓库相对的上级目录候选。
if [ "$IN_WSL" = "1" ]; then
  LEADS_MD="${FDE_LEADS_MD:-/mnt/d/test/FDE/leads.md}"
else
  LEADS_MD="${FDE_LEADS_MD:-/d/test/FDE/leads.md}"
fi

# B7/B1：容器与库目标全部可用环境变量覆盖——CI 用 service 容器（容器 ID 由
# docker ps 查出传入），本地保持默认不动开发库。
PG_CONTAINER="${FDE_PG_CONTAINER:-qiflow-twenty-db}"
PG_USER="${FDE_PG_USER:-twenty}"
PG_DB="${FDE_PG_DB:-fde_workbench}"

run_host() {
  if [ "$IN_WSL" = "1" ]; then
    bash -lc "$1"
  elif command -v wsl >/dev/null 2>&1; then
    # Windows 宿主：容器在 WSL 发行版里，须经 wsl.exe 中转
    wsl -e bash -lc "$1"
  else
    # Linux 宿主（CI runner）：docker 原生在 PATH 上，直接执行
    bash -c "$1"
  fi
}

# PG 里的库坑：psql 输出带 \r，统一清洗。
# 退出码经 PSQL_RC 带回（命令替换吃掉退出码）——psql 失败必须可见，H2 前这里
# 的 2>/dev/null + ${bad:-0} 把「SQL 执行失败」当成「0 行命中」（C-8c 假绿）。
PSQL_RC=0
PSQL_OUT=""
psql_exec() {
  # 结果经全局 PSQL_OUT / PSQL_RC 传出——本函数若以 `x=$(psql_exec ...)` 调用，
  # 赋值发生在命令替换子壳里，PSQL_RC 传不回父进程（H2 期间实测踩坑）。
  # 管道必须 pipefail：run_host(wsl→psql) 的非零退出码否则会被 tr 吃掉，
  # 「表不存在/连接失败」就伪装成「查询成功 0 行」（与 dump_db 同坑，C-8c）。
  local rc=0
  set -o pipefail
  PSQL_OUT=$(run_host "docker exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -t -A -c \"$1\"" 2>/dev/null | tr -d '\r') || rc=$?
  set +o pipefail
  PSQL_RC=$rc
}

extract_blacklist() {
  # 企业名提取：GNU grep 的多字节区间 [一-龥] 不可移植——UTF-8 locale 报
  # 「Invalid collation character」匹配 0 个（=黑名单静默失效，自测都发现
  # 不了，哨兵手机号照样被抓）、C locale 按字节碰巧能跑、MSYS 又是另一套
  # （实测三环境三种结果）。perl 按码位区间提取，与 locale 完全无关。
  perl -Mutf8 -CSD -ne \
    'while (/([\x{4E00}-\x{9FA5}]{2,15}(?:公司|集团|厂))/g) { print "$1\n" }' \
    "$LEADS_MD" | sort -u
}

TMP_DUMP="$(mktemp /tmp/fde_pseudonym.XXXXXX.sql)"
TMP_BLACKLIST="$(mktemp /tmp/fde_blacklist.XXXXXX.txt)"
trap 'rm -f "$TMP_DUMP" "$TMP_BLACKLIST"' EXIT

dump_db() {
  # 管道退出码必须查：run_host（pg_dump）非零 = dump 不完整——半个 dump 扫出
  # 「全库无明文」是合规假通过，比扫不出来更糟。
  set -o pipefail
  local dump_rc=0
  run_host "docker exec $PG_CONTAINER pg_dump -U $PG_USER $PG_DB --data-only --inserts" 2>/dev/null | tr -d '\r' > "$TMP_DUMP" || dump_rc=$?
  set +o pipefail
  if [ "$dump_rc" -ne 0 ]; then
    echo "FAIL pg_dump 退出码 $dump_rc（dump 不完整，拒绝扫描）"
    exit 2
  fi
  if [ ! -s "$TMP_DUMP" ]; then
    echo "FAIL 无法导出 $PG_DB（容器活着吗？）"
    exit 2
  fi
}

SELF_TEST=0
[ "${1:-}" = "--self-test" ] && SELF_TEST=1

fail=0; warn=0
HIT_PHONE=0; HIT_IDCARD=0; HIT_EMAIL=0

# grep -P -c 的退出码必须区分：1 = 无命中（正常，输出 0）；≥2 = 正则/locale/IO
# 错误——旧版 `|| true` 把错误一起吞掉，「扫描没跑成」与「扫了 0 行」不可区分
# （H2 实测：locale 坏时黑名单静默失效仍 PASS）。
grep_count() {
  local out rc=0
  out=$(grep -P -c "$1" "$TMP_DUMP" 2>/dev/null) || rc=$?
  if [ "$rc" -ge 2 ]; then
    printf 'SCANNER_ERROR'
    return
  fi
  printf '%s' "${out:-0}"
}

scan_one() { # <label> <pattern> <severity: fail|email> <hit-var-name>
  local label="$1" pattern="$2" severity="$3" hit_var="$4" count
  count=$(grep_count "$pattern")
  if [ "$count" = "SCANNER_ERROR" ]; then
    echo "FAIL ${label} 扫描器错误（正则/locale/IO）——拒绝当成 0 行（C-8c）"
    fail=1
    return
  fi
  if [ "$count" -gt 0 ]; then
    printf -v "$hit_var" 1
    if [ "$severity" = "fail" ]; then
      echo "FAIL ${label} 模式命中 ${count} 行："
    elif [ "$EMAIL_POLICY" = "fail" ]; then
      echo "FAIL ${label} 命中 ${count} 行（FDE_PSEUDONYM_EMAIL_POLICY=fail，客户邮箱也是泄漏）："
      fail=1
    else
      echo "WARN ${label} 命中 ${count} 行（策略 warn，人工复核）："
      warn=1
    fi
    grep -P -n "$pattern" "$TMP_DUMP" | head -5 | cut -c1-160
    [ "$severity" = "fail" ] && fail=1
  else
    echo "OK   ${label}：无命中"
  fi
}

scan_dump() {
  # 手机号：1[3-9]+9 位数字；前后不许贴十六进制字符或连字符（排除 uuid 误报）
  local PHONE='(?<![0-9A-Fa-f-])1[3-9][0-9]{9}(?![0-9A-Fa-f-])'
  # 18 位身份证：17 数字 + 数字/X；前后不许贴数字/X/十六进制字母——
  # 边界集不含 a-f 时，refresh_sessions 的 sha256 令牌哈希里 18 位数字段
  # （两侧贴 hex 字母）会误报成身份证（实测踩过）。
  local IDCARD='(?<![0-9A-Fa-fXx])[0-9]{17}[0-9Xx](?![0-9A-Fa-fXx])'
  local EMAIL='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'

  scan_one "手机号" "$PHONE" fail HIT_PHONE
  scan_one "身份证" "$IDCARD" fail HIT_IDCARD
  scan_one "邮箱" "$EMAIL" email HIT_EMAIL

  # 企业名黑名单：leads.md 的真实企业名一个都不许进库。
  # 提取结果 0 条 = 黑名单失效（perl 缺失/文件空）= 这条防线没跑，必须 FAIL
  # （H2 实测：本机 perl 缺失时会静默输出「0 个」仍 exit 0）。
  if [ -f "$LEADS_MD" ]; then
    extract_blacklist > "$TMP_BLACKLIST"
    local bl_count bl_hits=0 name
    bl_count=$(wc -l < "$TMP_BLACKLIST" | tr -d '[:space:]')
    if [ "${bl_count:-0}" -eq 0 ]; then
      echo "FAIL 黑名单提取 0 条（perl 缺失或 $LEADS_MD 无企业名）——黑名单失效等于没扫（C-8b）"
      fail=1
      return
    fi
    while IFS= read -r name; do
      [ -n "$name" ] || continue
      if grep -F -q "$name" "$TMP_DUMP"; then
        echo "FAIL 企业名「${name}」出现在数据库 dump 中"
        bl_hits=1; fail=1
      fi
    done < "$TMP_BLACKLIST"
    [ "$bl_hits" = "0" ] && echo "OK   企业名黑名单（leads.md ${bl_count} 个）：无命中"
  else
    # B7：黑名单是代号化验收的必要项——文件缺失必须显式 FAIL，不许静默降级。
    # CI / 新机器用 FDE_LEADS_MD 传入黑名单文件（可以是合成 fixture，每行一段
    # 含「公司/集团/厂」结尾的中文名即可），不再依赖特定机器的文件布局。
    echo "FAIL leads.md 未找到（$LEADS_MD）——企业名黑名单无法核对，拒绝静默跳过"
    echo "     请设置 FDE_LEADS_MD 指向 leads 文件（CI 可传合成黑名单 fixture）后重跑"
    fail=1
  fi
}

check_code_format() {
  local bad total
  psql_exec "select count(*) from projects where length(enterprise_code) - length(replace(enterprise_code, '·', '')) <> 2;"
  if [ "$PSQL_RC" -ne 0 ]; then
    echo "FAIL enterprise_code 格式检查 SQL 执行失败（psql 退出码 $PSQL_RC）——不许当 0 行（C-8c）"
    fail=1
    return
  fi
  bad="$PSQL_OUT"
  psql_exec "select count(*) from projects;"
  if [ "$PSQL_RC" -ne 0 ]; then
    echo "FAIL projects 计数 SQL 执行失败（psql 退出码 $PSQL_RC）——不许当 0 行（C-8c）"
    fail=1
    return
  fi
  total="$PSQL_OUT"
  # C-8b：0 行的空库等于没扫。CI 的 pseudonymization job 必须先 alembic 迁移
  # 并灌合成业务数据（I5），本机指向开发库时天然有数据。
  if [ "${total:-0}" -eq 0 ]; then
    echo "FAIL projects 表 0 行——空库扫描等于没扫（I5），先迁移并灌合成业务数据"
    fail=1
    return
  fi
  if [ "${bad:-0}" -gt 0 ]; then
    echo "WARN ${bad}/${total} 个 enterprise_code 不是「X·Y·Z」三段格式（应为「客户A·行业·城市」）"
    warn=1
  else
    echo "OK   enterprise_code 格式（${total} 行全部三段）"
  fi
}

if [ "$SELF_TEST" = "1" ]; then
  # 哨兵表会真实写入目标库——只允许 fde_workbench 系的库（CI 的
  # fde_workbench_test、本机开发库都在内）。指到别的库（twenty、postgres、
  # 同容器里别家的业务库）直接拒绝，别在别人库里留对象。
  case "$PG_DB" in
    fde_workbench*) ;;
    *)
      echo "FAIL 自测拒绝：目标库 $PG_DB 不是 fde_workbench*——哨兵表会真实写入该库"
      echo "     请用 FDE_PG_DB 指向 fde_workbench_test 等专用库后重跑"
      exit 2
      ;;
  esac
  echo "== 自测：注入哨兵（手机号+身份证+邮箱三模式应逐个被抓）=="
  psql_exec "create table if not exists __pseudonym_probe(id text);"
  psql_exec "insert into __pseudonym_probe values ('哨兵手机号13800138000身份证11010519491231002X邮箱probe@example.com结束');"
  if [ "$PSQL_RC" -ne 0 ]; then
    echo "FAIL 自测哨兵写入失败（psql 退出码 $PSQL_RC）"
    psql_exec "drop table if exists __pseudonym_probe;" >/dev/null
    exit 2
  fi
  dump_db
  scan_dump
  if [ "$HIT_PHONE" = "0" ] || [ "$HIT_IDCARD" = "0" ] || [ "$HIT_EMAIL" = "0" ]; then
    echo "FAIL 自测失败：哨兵未逐个被抓（手机号=$HIT_PHONE 身份证=$HIT_IDCARD 邮箱=$HIT_EMAIL），扫描器坏了"
    psql_exec "drop table if exists __pseudonym_probe;" >/dev/null
    exit 2
  fi
  echo "== 自测通过（三个模式都能抓），清理哨兵后重扫 =="
  psql_exec "drop table if exists __pseudonym_probe;" >/dev/null
  fail=0; warn=0
fi

dump_db
scan_dump
check_code_format

echo
if [ "$fail" = "1" ]; then
  echo "结论：FAIL —— 库里发现客户明文痕迹或扫描线自身失效，按 R3 处置：定位来源、清理数据、补防线"
  exit 1
elif [ "$warn" = "1" ]; then
  echo "结论：PASS（有 WARN：FDE_PSEUDONYM_EMAIL_POLICY=warn，上方已列出命中行数，逐条人工复核）"
  exit 0
else
  echo "结论：PASS —— 未发现客户明文"
  exit 0
fi
