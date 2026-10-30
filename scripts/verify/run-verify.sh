#!/usr/bin/env bash
# 用途：跨库只读验证固化（G8）——Twenty persons 指标 / n8n 最近执行状态与耗时。
#       供重复手工验证场景（线索进站核对、管道健康巡检）一键执行。
# 用法（仓库根，宿主 Git Bash 或 WSL 内均可）：
#   bash scripts/verify/run-verify.sh
#   VERIFY_WINDOW_DAYS=7 VERIFY_EXEC_HOURS=24 bash scripts/verify/run-verify.sh
# 连接参数（全部环境变量，可覆盖；默认值与本机 qiflow compose 一致）：
#   VERIFY_TWENTY_CONTAINER=qiflow-twenty-db   VERIFY_TWENTY_USER=twenty   VERIFY_TWENTY_DB=twenty
#   VERIFY_TWENTY_SCHEMA=workspace_14g3g9n62pbz9hxhq9x42rwlo
#   VERIFY_N8N_CONTAINER=qiflow-n8n-db         VERIFY_N8N_USER=n8n         VERIFY_N8N_DB=n8n
#   VERIFY_WINDOW_DAYS=7（Twenty 新增窗口）    VERIFY_EXEC_HOURS=24（n8n 回看窗口）
#   WSL_DISTRO=Ubuntu-24.04（仅 Windows 宿主经 wsl 调 docker 时用）
# 密钥：脚本不持任何口令——psql 在 db 容器内走本地 socket 免密；也绝不读 .env。
# 只读保证：两个 .sql 均显式 BEGIN; SET TRANSACTION READ ONLY; … ROLLBACK;。
# 首跑记录（2026-10-30，本机实跑，仅计数）：见 docs/验证脚本-G8.md。

set -euo pipefail
cd "$(dirname "$0")"

VERIFY_TWENTY_CONTAINER="${VERIFY_TWENTY_CONTAINER:-qiflow-twenty-db}"
VERIFY_TWENTY_USER="${VERIFY_TWENTY_USER:-twenty}"
VERIFY_TWENTY_DB="${VERIFY_TWENTY_DB:-twenty}"
VERIFY_TWENTY_SCHEMA="${VERIFY_TWENTY_SCHEMA:-workspace_14g3g9n62pbz9hxhq9x42rwlo}"
VERIFY_N8N_CONTAINER="${VERIFY_N8N_CONTAINER:-qiflow-n8n-db}"
VERIFY_N8N_USER="${VERIFY_N8N_USER:-n8n}"
VERIFY_N8N_DB="${VERIFY_N8N_DB:-n8n}"
VERIFY_WINDOW_DAYS="${VERIFY_WINDOW_DAYS:-7}"
VERIFY_EXEC_HOURS="${VERIFY_EXEC_HOURS:-24}"
WSL_DISTRO="${WSL_DISTRO:-Ubuntu-24.04}"

# psql 一律经 stdin 喂 SQL（-f -），SQL 文件内容不走 argv——中文不经 Git Bash→WSL→容器 argv。
run_psql() {
  local container="$1" user="$2" db="$3" file="$4"
  shift 4
  local vars=() v
  for v in "$@"; do vars+=( -v "$v" ); done
  if command -v wsl.exe >/dev/null 2>&1; then
    MSYS_NO_PATHCONV=1 wsl.exe -d "$WSL_DISTRO" -- docker exec -i "$container" \
      psql -U "$user" -d "$db" -v ON_ERROR_STOP=1 "${vars[@]}" -f - < "$file"
  else
    docker exec -i "$container" \
      psql -U "$user" -d "$db" -v ON_ERROR_STOP=1 "${vars[@]}" -f - < "$file"
  fi
}

echo "#### Twenty（容器 $VERIFY_TWENTY_CONTAINER，schema $VERIFY_TWENTY_SCHEMA，窗口 ${VERIFY_WINDOW_DAYS}d）"
run_psql "$VERIFY_TWENTY_CONTAINER" "$VERIFY_TWENTY_USER" "$VERIFY_TWENTY_DB" \
  verify-twenty-persons.sql "ws_schema=$VERIFY_TWENTY_SCHEMA" "window_days=$VERIFY_WINDOW_DAYS"

echo "#### n8n（容器 $VERIFY_N8N_CONTAINER，回看 ${VERIFY_EXEC_HOURS}h）"
run_psql "$VERIFY_N8N_CONTAINER" "$VERIFY_N8N_USER" "$VERIFY_N8N_DB" \
  verify-n8n-executions.sql "exec_hours=$VERIFY_EXEC_HOURS"

echo "#### 完成：全程 READ ONLY，无写入。"
