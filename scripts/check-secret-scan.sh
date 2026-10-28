#!/usr/bin/env bash
# 秘密扫描门禁（goal-r2 WP22 / G3）。
#
# 用法：
#   bash scripts/check-secret-scan.sh              # 扫描 git 泄漏面（tracked + 未忽略
#                                                  # untracked =「git 可能带走的一切」），
#                                                  # 任何命中即非零退出
#   bash scripts/check-secret-scan.sh --self-test  # 哨兵自测：低熵 hex 探针必须被
#                                                  # fde-credential-var-literal 规则抓住
#                                                  # （默认 generic-api-key 规则因 ≈3.7 熵阈值
#                                                  #  会漏抓这种形态，是 2f90484 口令漏报的根因，
#                                                  #  见 .gitleaks.toml 头注）；阴性对照不得命中
#
# 运行器按序探测：本机 gitleaks 二进制 → Linux 本机 docker → Windows 宿主经
# WSL 的 docker。可用 FDE_GITLEAKS_IMAGE 覆盖镜像。
#
# Windows 宿主实现说明：wsl-docker 模式下扫描载荷先拷进 WSL 原生 /tmp staging
# 再挂载进容器——直接挂 /mnt/c（drvfs/9p）有目录一致性滞后，容器会看到刚创建
# 文件的旧视图（实测：毫秒级 cp→docker run 序列扫到 0 字节或缺 .gitleaks.toml）。
#
# 已知边界（G5 交接）：本脚本的默认模式只扫工作树泄漏面，不扫 git 历史；
# 全历史扫描由 CI（gitleaks-action）承担。在人工完成 G5 历史清理前，CI 全历史
# 扫描会持续命中 2f90484 引入的两条 Mautic 口令（脚本已从工作树删除，历史仍在）
# —— 那是扫描器恢复灵敏度的正确行为，禁止用 allowlist 压制。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${FDE_GITLEAKS_IMAGE:-zricethezav/gitleaks:latest}"
RULE_ID="fde-credential-var-literal"
WORK_DIR=""
# $$ 全脚本不变，故 staging 名在启动时即可确定（stage_in 会在命令替换子壳里运行，
# 子壳内的赋值传不回父进程，必须用全局常量而不是在子壳里赋值）
STAGE_DIR="/tmp/fde-secret-scan.$$"

log() { printf '[check-secret-scan] %s\n' "$*"; }
die() { log "FAIL: $*"; exit 1; }

cleanup_all() {
  [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR"
  if [ -n "$STAGE_DIR" ]; then
    if [ "$RUNNER_KIND" = wsl-docker ]; then
      wsl -e bash -lc "rm -rf '$STAGE_DIR'" || true
    else
      rm -rf "$STAGE_DIR"
    fi
  fi
}

host_kind="$(uname -s)"
case "$host_kind" in
  MINGW* | MSYS* | CYGWIN*) HOST_KIND=msys ;;
  Linux) HOST_KIND=linux ;;
  *) HOST_KIND=other ;;
esac

if command -v gitleaks >/dev/null 2>&1; then
  RUNNER_KIND=native
elif [ "$HOST_KIND" = linux ] && command -v docker >/dev/null 2>&1; then
  RUNNER_KIND=docker-linux
elif command -v wsl >/dev/null 2>&1 || command -v wsl.exe >/dev/null 2>&1; then
  RUNNER_KIND=wsl-docker
else
  die "no gitleaks runner available (native binary / linux docker / wsl docker)"
fi
log "runner=$RUNNER_KIND image=$IMAGE"

# 把宿主路径翻译成 gitleaks 引擎可见路径（Git Bash 宿主 + WSL docker 时 D:/x → /mnt/d/x）。
# 盘符必须小写：WSL 的挂载点是 /mnt/c、/mnt/d，大小写敏感，/mnt/C 是不存在的空目录。
engine_path() {
  local p="$1"
  if [ "$RUNNER_KIND" = wsl-docker ] && [ "$HOST_KIND" = msys ]; then
    local w drive
    w="$(cygpath -m "$p")"
    drive="$(printf '%s' "${w:0:1}" | tr 'A-Z' 'a-z')"
    printf '/mnt/%s%s' "$drive" "${w:2}"
  else
    printf '%s' "$p"
  fi
}

# 把宿主目录同步进引擎可见的扫描目录。wsl-docker 时落到 WSL 原生 ext4 staging；
# 其它运行器原目录直用。回显实际扫描目录（宿主侧报告经 stage_out_report 取回）。
stage_in() {
  local host_dir="$1" e_dir
  if [ "$RUNNER_KIND" != wsl-docker ]; then
    printf '%s' "$host_dir"
    return
  fi
  e_dir="$(engine_path "$host_dir")"
  wsl -e bash -lc "rm -rf '$STAGE_DIR' && mkdir -p '$STAGE_DIR' && cp -a '$e_dir/.' '$STAGE_DIR/'" ||
    die "staging copy into WSL failed"
  printf '%s' "$STAGE_DIR"
}

stage_out_report() {
  local scan_dir="$1" host_dest="$2" e_dest
  if [ "$RUNNER_KIND" != wsl-docker ]; then
    cp "$scan_dir/report.json" "$host_dest"
    return
  fi
  e_dest="$(engine_path "$host_dest")"
  wsl -e bash -lc "cp '$STAGE_DIR/report.json' '$e_dest'" || die "report copy-out failed"
}

# gitleaks_detect <scan_dir>；报告固定写 <scan_dir>/report.json。退出码即 gitleaks 退出码。
gitleaks_detect() {
  local scan_dir="$1"
  case "$RUNNER_KIND" in
    native)
      gitleaks detect --no-git -s "$scan_dir" --no-banner --redact \
        --report-format json --report-path "$scan_dir/report.json"
      ;;
    docker-linux)
      docker run --rm -v "$scan_dir:$scan_dir" -w "$scan_dir" "$IMAGE" \
        detect --no-git -s "$scan_dir" --no-banner --redact \
        --report-format json --report-path "$scan_dir/report.json"
      ;;
    wsl-docker)
      wsl -e bash -lc "docker run --rm -v '$scan_dir:$scan_dir' -w '$scan_dir' '$IMAGE' \
        detect --no-git -s '$scan_dir' --no-banner --redact \
        --report-format json --report-path '$scan_dir/report.json'"
      ;;
  esac
}

# 从报告里提取 <RuleID, File, StartLine>（绝不输出 Match/Secret 字段）。
# gitleaks 报告是 pretty JSON（冒号后带空格），模式必须空白容忍。
dump_findings() {
  local report="$1"
  grep -o '"RuleID": *"[^"]*"\|"File": *"[^"]*"\|"StartLine": *[0-9]*' "$report" |
    tr '\n' ' ' | sed 's/"RuleID"/\n  RuleID/g'
  printf '\n'
}

cmd_self_test() {
  WORK_DIR="$(mktemp -d)"
  trap cleanup_all EXIT

  # 探针 1：低熵 hex + KEY 名。熵 ≈2.75，默认 generic-api-key（熵阈值 ≈3.7）漏抓，
  # 只有本仓库的自定义规则（无熵要求）能抓 —— 钉死「熵盲区」。
  local low_entropy_hex random_hex
  low_entropy_hex="$(printf 'ab%.0s' $(seq 1 24))"
  printf 'FDE_SCAN_PROBE_KEY="%s"\n' "$low_entropy_hex" > "$WORK_DIR/probe-low-entropy.env"
  # 探针 2：随机 hex + PASS 名。generic-api-key 对 *_PASS= 形态整体失配（2f90484
  # 两条真实口令漏报的根因），自定义规则必须兜住 —— 钉死「名字盲区」。
  random_hex="$(head -c24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  printf 'MAUTIC_DB_PASS="%s"\n' "$random_hex" > "$WORK_DIR/probe-pass-name.env"
  # 阴性对照：正常的环境变量取用与对象存储路径都不得命中
  # （防规则过宽把「从环境读口令」当泄漏、把 storage 路径当凭据）
  printf 'db_password = os.environ["FDE_DB_PASSWORD"]\napi_key = load_key_from_file()\nstorage_key="projects/p1/attachments/f1/versions/v1/x.exe"\n' > "$WORK_DIR/negative.py"
  cp "$REPO_ROOT/.gitleaks.toml" "$WORK_DIR/.gitleaks.toml"

  log "self-test: probing $(find "$WORK_DIR" -type f | wc -l) file(s)"
  local scan_dir rc=0
  scan_dir="$(stage_in "$WORK_DIR")"
  gitleaks_detect "$scan_dir" || rc=$?
  # gitleaks 无命中（rc=0）时不写报告文件，必须先判 rc 再取报告
  if [ "$rc" -eq 0 ]; then
    die "sentinel NOT caught (exit 0) — scanner is insensitive, the secret scan line is ineffective (C-7c)"
  fi
  if [ "$rc" -gt 1 ]; then
    die "gitleaks exited $rc (unexpected error, not a leak verdict)"
  fi
  stage_out_report "$scan_dir" "$WORK_DIR/report.json"
  # 两个探针必须都由自定义规则命中，且报告里不存在任何其它发现
  # （两个探针对 generic-api-key 各有一个盲区，若 generic 也命中说明钉不住盲区）
  local mine total
  mine="$(grep -c "\"RuleID\": *\"$RULE_ID\"" "$WORK_DIR/report.json")"
  total="$(grep -c '"RuleID":' "$WORK_DIR/report.json")"
  if [ "$mine" -lt 2 ] || [ "$total" -ne "$mine" ]; then
    die "expected exactly 2 findings both from $RULE_ID (got mine=$mine total=$total) — rule regressed or blind-zone pinning void"
  fi
  if grep -q 'negative\.py' "$WORK_DIR/report.json"; then
    die "negative control (env-var reads / storage paths) was flagged — rule is over-broad, tighten before trusting positives"
  fi
  log "self-test OK: both probes caught by $RULE_ID (generic-api-key caught none), negatives clean"
}

cmd_scan_surface() {
  WORK_DIR="$(mktemp -d)"
  trap cleanup_all EXIT

  local surface="$WORK_DIR/surface"
  mkdir -p "$surface"
  cd "$REPO_ROOT"
  local n=0 f
  while IFS= read -rd '' f; do
    mkdir -p "$surface/$(dirname "$f")"
    cp "$f" "$surface/$f" || die "copy failed: $f"
    n=$((n + 1))
  done < <(git ls-files --cached --others --exclude-standard -z)
  # C-8b：扫描目标集合必须非空，否则「0 个文件 0 命中」是假绿
  [ "$n" -gt 0 ] || die "git leak surface is empty (0 files) — refusing to pass an empty scan"
  cp "$REPO_ROOT/.gitleaks.toml" "$surface/.gitleaks.toml"

  log "scanning $n file(s) of git leak surface"
  local scan_dir rc=0
  scan_dir="$(stage_in "$surface")"
  gitleaks_detect "$scan_dir" || rc=$?
  stage_out_report "$scan_dir" "$WORK_DIR/report.json"

  if [ "$rc" -eq 1 ]; then
    log "findings (RuleID/File/StartLine only):"
    dump_findings "$WORK_DIR/report.json"
    die "leaks found in git leak surface — remove them from the tree; values must be rotated (C-7b)"
  fi
  [ "$rc" -eq 0 ] || die "gitleaks exited $rc (unexpected error)"
  log "OK: 0 findings across $n file(s)"
}

case "${1:-}" in
--self-test) cmd_self_test ;;
"") cmd_scan_surface ;;
*) die "usage: check-secret-scan.sh [--self-test]" ;;
esac
