# FDE-Bridge-Poll 计划任务安装器（P2 集成桥·采集节奏 15 min）
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-bridge-poll-task.ps1
# 卸载：schtasks /Delete /TN FDE-Bridge-Poll /F

$ErrorActionPreference = "Stop"
$node = "D:\software\nodejs\node.exe"   # A3/R6：Node 24 固定路径，不信 PATH
$script = Join-Path $PSScriptRoot "bridge-poll.mjs"
if (-not (Test-Path $node)) { throw "node.exe 不存在：$node" }
if (-not (Test-Path $script)) { throw "bridge-poll.mjs 不存在：$script" }

$action = New-ScheduledTaskAction -Execute $node -Argument "`"$script`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 15)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "FDE-Bridge-Poll" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "已安装 FDE-Bridge-Poll（每 15 分钟，错过补跑）。手动验证：schtasks /Run /TN FDE-Bridge-Poll"
