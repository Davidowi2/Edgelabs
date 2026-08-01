# ============================================================================
# watchdog.ps1 — Phase 9a VPS deployment (Windows)
#
# Keeps the MT5 terminal alive on Windows. Checks if terminal64.exe is running
# and restarts it if dead. Designed to run via Task Scheduler every 5 minutes.
#
# Parameters (override via -Name Value):
#   CheckIntervalSec  (informational; Task Scheduler controls frequency)
#   LogFile           path to watchdog log
#   AlertOnRestart    [switch] emit an alert line on restart
#   TerminalExe       full path to terminal64.exe
# ============================================================================

[CmdletBinding()]
param(
    [int]   $CheckIntervalSec = 300,
    [string]$LogFile = "$env:USERPROFILE\mt5\watchdog.log",
    [string]$TerminalExe = "$env:USERPROFILE\mt5\MT5_Instance1\terminal64.exe",
    [switch]$AlertOnRestart
)

$ErrorActionPreference = 'SilentlyContinue'
$ts = { Get-Date -Format 'yyyy-MM-dd HH:mm:ss' }

# ensure log dir
$logDir = Split-Path $LogFile -Parent
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }

$running = Get-Process -Name 'terminal64' -ErrorAction SilentlyContinue
if ($running) {
    Add-Content $LogFile "$(& $ts) HEALTHY: terminal64.exe is running"
    exit 0
}

Add-Content $LogFile "$(& $ts) DEGRADED: terminal64.exe NOT running - restarting"
Start-Process -FilePath $TerminalExe -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3

$running = Get-Process -Name 'terminal64' -ErrorAction SilentlyContinue
if ($running) {
    Add-Content $LogFile "$(& $ts) RECOVERED: terminal64.exe restarted"
    if ($AlertOnRestart) { Add-Content $LogFile "$(& $ts) ALERT: MT5 was down and has been restarted" }
    exit 0
} else {
    Add-Content $LogFile "$(& $ts) CRITICAL: terminal64.exe failed to restart"
    if ($AlertOnRestart) { Add-Content $LogFile "$(& $ts) ALERT: MT5 restart FAILED - operator intervention required" }
    exit 2
}
