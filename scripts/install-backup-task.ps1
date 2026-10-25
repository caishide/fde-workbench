# ============================================================
# 把统一备份挂到 Windows 计划任务（每周日 03:00）
# ============================================================
# 用法（PowerShell，需管理员）:
#   powershell -ExecutionPolicy Bypass -File scripts\install-backup-task.ps1
#
# 为什么挂在 Windows 而不是 WSL 的 cron:
#   WSL 定时任务在 WSL 未启动时不跑；Windows 计划任务是宿主机原生，
#   唤醒时会自动拉起 WSL 并执行脚本（脚本内部已有 docker exec 调用）。
#
# 幂等：同名任务先删再建。
# ============================================================

$ErrorActionPreference = "Stop"

$TaskName = "FDE-Workbench-Backup"
$RepoDir = "D:\test\FDE\_eval\fde-workbench"
$LogDir = "D:\test\FDE\_backup\_logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd-HHmm"
$LogFile = Join-Path $LogDir "backup-$Stamp.log"

# 计划任务动作：调 bash 跑备份脚本（Git Bash 已在 PATH 的话用绝对路径更稳）
$GitBash = "C:\Program Files\Git\bin\bash.exe"
if (-not (Test-Path $GitBash)) {
    $GitBash = "C:\Users\P1\.workbuddy\binaries\PortableGit\versions\1.3.0\bin\bash.exe"
}
if (-not (Test-Path $GitBash)) {
    throw "找不到 bash.exe，请手动指定路径后重跑"
}

# 用变量拼装 Argument，避开 PowerShell 5.1 的反引号转义地狱
$bashCmd = "cd '" + $RepoDir + "' && bash scripts/backup-all.sh >> '" + $LogFile + "' 2>&1"
$Action = New-ScheduledTaskAction `
    -Execute $GitBash `
    -Argument ("-lc " + [char]34 + $bashCmd + [char]34) `
    -WorkingDirectory $RepoDir

# 触发：每周日 03:00
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 3am

# 设置：错过后补跑、最长 1 小时、不并发
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

# 最高权限（备份需读 Docker 卷）
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

# 幂等：先删同名任务
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Output "已删除旧同名任务"
}

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
    -Settings $Settings -Principal $Principal `
    -Description "FDE 工作台统一备份：PostgreSQL(Twenty+fde_workbench) + openfde 各 engagement ledger + fdeops 台账。产物在 D:\test\FDE\_backup\" | Out-Null

Write-Output "已注册计划任务: $TaskName"
Write-Output "  触发: 每周日 03:00（错过后自动补跑）"
Write-Output "  日志: $LogDir"
Write-Output ""
Write-Output "立即试跑一次:"
Write-Output "  & $GitBash -lc `"cd '$RepoDir' && bash scripts/backup-all.sh`""
Write-Output ""
Write-Output "验证恢复性（别跳过）:"
Write-Output "  & $GitBash -lc `"cd '$RepoDir' && bash scripts/backup-all.sh --verify`""
