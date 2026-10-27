# ============================================================
# 把「AI 获客系统三库补齐备份」挂到 Windows 计划任务
# ============================================================
# 为什么挂在 Windows 而不是 WSL cron:
#   WSL 定时任务在 WSL 未启动时不跑；Windows 计划任务是宿主机原生，
#   唤醒时会自动拉起 WSL 并执行脚本。
#
# 与 backup-all.sh 的分工:
#   backup-all.sh       → 每周日 03:00，覆盖 FDE 工作台侧四类数据
#   backup-pipeline.sh  → 每天 03:30，覆盖 AI 获客系统三个状态点
#                          （n8n 库 / Mautic 库 / openoutfind SQLite）
#
# 频率不同是刻意的:
#   · n8n 执行收据链每天都在长，且默认 14 天后被裁 → 必须每日备份
#   · Mautic 培育进度按天演进 → 每日
#   · openoutfind 线索池 + BetterContact 余额按次消耗 → 每日
#
# 幂等：同名任务先删再建。
# ============================================================

$ErrorActionPreference = "Stop"

$TaskName = "FDE-Pipeline-Backup"
$RepoDir = "D:\test\fde-workbench"
$LogDir = "D:\test\FDE\_backup\_logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd-HHmm"
$LogFile = Join-Path $LogDir "backup-pipeline-$Stamp.log"

$GitBash = "C:\Program Files\Git\bin\bash.exe"
if (-not (Test-Path $GitBash)) {
    $GitBash = "C:\Users\P1\.workbuddy\binaries\PortableGit\versions\1.3.0\bin\bash.exe"
}
if (-not (Test-Path $GitBash)) {
    throw "找不到 bash.exe，请手动指定路径后重跑"
}

# 用变量拼装 Argument，避开 PowerShell 5.1 的反引号转义地狱
$bashCmd = "cd '" + $RepoDir + "' && bash scripts/backup-pipeline.sh >> '" + $LogFile + "' 2>&1"
$Action = New-ScheduledTaskAction `
    -Execute $GitBash `
    -Argument ("-lc " + [char]34 + $bashCmd + [char]34) `
    -WorkingDirectory $RepoDir

# 触发：每天 03:30（错开 backup-all.sh 的周日 03:00）
$Trigger = New-ScheduledTaskTrigger -Daily -At 3:30am

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew `
    -DontStopIfGoingOnBatteries `
    -AllowStartIfOnBatteries

# 先删同名任务（幂等）
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "已删除旧任务: $TaskName"
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "AI 获客系统三库补齐备份：n8n(PostgreSQL) + Mautic(MySQL) + openoutfind(SQLite)。与 FDE-Pipeline-Backup 同名会覆盖。" `
    -Force | Out-Null

Write-Host "已注册任务: $TaskName"
Write-Host "  频率: 每天 03:30"
Write-Host "  日志: $LogDir\backup-pipeline-*.log"
Write-Host "  产物: D:\test\FDE\_backup\pipeline-YYYYMMDD-HHMM\"
Write-Host ""
Write-Host "手动验证: bash scripts/backup-pipeline.sh --verify"
