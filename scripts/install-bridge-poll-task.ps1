# FDE-Bridge-Poll 计划任务安装器（P2 集成桥·采集节奏 4 小时；2026-10-25 用户裁决放宽，原 15 min）
# 隐藏运行：动作是 wscript 启动 run-bridge-poll.vbs（GUI 宿主 + Run 隐藏），终端不再弹窗；
# 采集输出落 logs/bridge-poll.log（VBS 内自带 1MB 轮转）。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install-bridge-poll-task.ps1
# 卸载：schtasks /Delete /TN FDE-Bridge-Poll /F

$ErrorActionPreference = "Stop"
$wscript = Join-Path $env:WINDIR "System32\wscript.exe"   # GUI 子系统宿主，无控制台
$launcher = Join-Path $PSScriptRoot "run-bridge-poll.vbs"
if (-not (Test-Path $wscript)) { throw "wscript.exe 不存在：$wscript" }
if (-not (Test-Path $launcher)) { throw "run-bridge-poll.vbs 不存在：$launcher" }

$action = New-ScheduledTaskAction -Execute $wscript -Argument "//B //nologo `"$launcher`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Hours 4)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "FDE-Bridge-Poll" -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "已安装 FDE-Bridge-Poll（每 4 小时，wscript 隐藏运行，错过补跑）。手动验证：schtasks /Run /TN FDE-Bridge-Poll"
