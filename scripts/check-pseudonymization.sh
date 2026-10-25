#!/usr/bin/env bash
# ============================================================
# 代号化校验（P1 验收项；R3 缓解措施）
# ============================================================
# 干什么：证明 fde_workbench 库里没有客户明文。
#   1. 全库 dump（data-only）后正则扫：手机号 / 18 位身份证号 / 邮箱
#   2. 黑名单：leads.md 里出现过的真实企业名（「公司/集团/厂」结尾 token）
#      一个都不允许出现在库里
#   3. projects.enterprise_code 格式检查（「客户A·行业·城市」→ 两枚「·」）WARN
#
# 判级：
#   手机号 / 身份证 / 企业名命中 → FAIL（exit 1）
#   邮箱命中 → WARN（可能是自己人账号，人工复核；客户邮箱也算泄漏，别放过）
#
# 自测模式：--self-test 先注入哨兵行（假手机号+假邮箱），
#   要求扫描器必须抓到（抓不到=扫描器坏了，exit 2），再清理重扫。
#   「没验过的备份等于没备份」同理：没自测过的校验器等于没有校验器。
#
# 用法:
#   bash scripts/check-pseudonymization.sh              # 正常校验
#   bash scripts/check-pseudonymization.sh --self-test  # 先验证扫描器灵敏度
# ============================================================
set -uo pipefail

IN_WSL=0
if grep -qiE '(microsoft|wsl)' /proc/version 2>/dev/null || [ -n "${WSL_DISTRO_NAME:-}" ]; then
  IN_WSL=1
fi
if [ "$IN_WSL" = "1" ]; then
  LEADS_MD="${FDE_LEADS_MD:-/mnt/d/test/FDE/leads.md}"
else
  LEADS_MD="${FDE_LEADS_MD:-/d/test/FDE/leads.md}"
fi

PG_CONTAINER="qiflow-twenty-db"
PG_USER="twenty"
PG_DB="fde_workbench"

run_wsl() {
  if [ "$IN_WSL" = "1" ]; then
    bash -lc "$1"
  else
    wsl -e bash -lc "$1"
  fi
}

# PG 里的库坑：psql 输出带 \r，统一清洗
psql_exec() {
  run_wsl "docker exec $PG_CONTAINER psql -U $PG_USER -d $PG_DB -t -A -c \"$1\"" 2>/dev/null | tr -d '\r'
}

TMP_DUMP="$(mktemp /tmp/fde_pseudonym.XXXXXX.sql)"
trap 'rm -f "$TMP_DUMP"' EXIT

dump_db() {
  run_wsl "docker exec $PG_CONTAINER pg_dump -U $PG_USER $PG_DB --data-only --inserts" 2>/dev/null | tr -d '\r' > "$TMP_DUMP"
  if [ ! -s "$TMP_DUMP" ]; then
    echo "FAIL 无法导出 $PG_DB（容器活着吗？）"
    exit 2
  fi
}

SELF_TEST=0
[ "${1:-}" = "--self-test" ] && SELF_TEST=1

fail=0; warn=0

scan_dump() {
  # 手机号：1[3-9]+9 位数字；前后不许贴十六进制字符或连字符（排除 uuid 误报）
  PHONE='(?<![0-9A-Fa-f-])1[3-9][0-9]{9}(?![0-9A-Fa-f-])'
  # 18 位身份证：17 数字 + 数字/X；前后不许贴数字或 X/x
  IDCARD='(?<![0-9Xx])[0-9]{17}[0-9Xx](?![0-9Xx])'
  EMAIL='[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'

  hits=$(grep -P -c "$PHONE" "$TMP_DUMP" 2>/dev/null || true)
  if [ "${hits:-0}" -gt 0 ]; then
    echo "FAIL 手机号模式命中 ${hits} 行："
    grep -P -n "$PHONE" "$TMP_DUMP" | head -5 | cut -c1-160
    fail=1
  else
    echo "OK   手机号：无命中"
  fi

  hits=$(grep -P -c "$IDCARD" "$TMP_DUMP" 2>/dev/null || true)
  if [ "${hits:-0}" -gt 0 ]; then
    echo "FAIL 身份证模式命中 ${hits} 行："
    grep -P -n "$IDCARD" "$TMP_DUMP" | head -5 | cut -c1-160
    fail=1
  else
    echo "OK   身份证：无命中"
  fi

  hits=$(grep -P -c "$EMAIL" "$TMP_DUMP" 2>/dev/null || true)
  if [ "${hits:-0}" -gt 0 ]; then
    echo "WARN 邮箱命中 ${hits} 行（人工复核：客户邮箱也是泄漏，自己人账号可忽略）："
    grep -P -n "$EMAIL" "$TMP_DUMP" | head -5 | cut -c1-160
    warn=1
  else
    echo "OK   邮箱：无命中"
  fi

  # 企业名黑名单：leads.md 的真实企业名一个都不许进库
  if [ -f "$LEADS_MD" ]; then
    bl_hits=0
    while IFS= read -r name; do
      [ -n "$name" ] || continue
      if grep -F -q "$name" "$TMP_DUMP"; then
        echo "FAIL 企业名「${name}」出现在数据库 dump 中"
        bl_hits=1; fail=1
      fi
    done < <(grep -oE '[一-龥]{2,15}(公司|集团|厂)' "$LEADS_MD" | sort -u)
    [ "$bl_hits" = "0" ] && echo "OK   企业名黑名单（leads.md $(grep -oE '[一-龥]{2,15}(公司|集团|厂)' "$LEADS_MD" | sort -u | wc -l) 个）：无命中"
  else
    echo "WARN leads.md 未找到（$LEADS_MD），跳过企业名黑名单"
    warn=1
  fi
}

check_code_format() {
  bad=$(psql_exec "select count(*) from projects where length(enterprise_code) - length(replace(enterprise_code, '·', '')) <> 2;")
  total=$(psql_exec "select count(*) from projects;")
  if [ "${bad:-0}" -gt 0 ]; then
    echo "WARN ${bad}/${total} 个 enterprise_code 不是「X·Y·Z」三段格式（应为「客户A·行业·城市」）"
    warn=1
  else
    echo "OK   enterprise_code 格式（${total:-0} 行全部三段）"
  fi
}

if [ "$SELF_TEST" = "1" ]; then
  echo "== 自测：注入哨兵（应被抓到）=="
  psql_exec "create table if not exists __pseudonym_probe(id text);" >/dev/null
  psql_exec "insert into __pseudonym_probe values ('哨兵手机号13800138000邮箱probe@example.com结束');" >/dev/null
  dump_db
  scan_dump
  if [ "$fail" = "0" ]; then
    echo "FAIL 自测失败：哨兵没被抓到，扫描器坏了"
    psql_exec "drop table if exists __pseudonym_probe;" >/dev/null
    exit 2
  fi
  echo "== 自测通过（扫描器能抓），清理哨兵后重扫 =="
  psql_exec "drop table if exists __pseudonym_probe;" >/dev/null
  fail=0; warn=0
fi

dump_db
scan_dump
check_code_format

echo
if [ "$fail" = "1" ]; then
  echo "结论：FAIL —— 库里发现客户明文痕迹，按 R3 处置：定位来源、清理数据、补防线"
  exit 1
elif [ "$warn" = "1" ]; then
  echo "结论：PASS（有 WARN，逐条人工复核）"
  exit 0
else
  echo "结论：PASS —— 未发现客户明文"
  exit 0
fi
