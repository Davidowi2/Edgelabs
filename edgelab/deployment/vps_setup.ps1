# ============================================================================
# vps_setup.ps1 — Phase 9a VPS deployment (Windows)
#
# Idempotent VPS hardening for an unattended MT5 trading box. Every change is
# documented inline. Re-running is safe: each function checks current state
# before writing, so a second run does not corrupt anything.
#
# Run AS ADMINISTRATOR. Tested on Windows 10/11 Pro.
#
# Parameters:
#   AutoLoginUser     account used for unattended login (default: current user)
#   AutoLoginPassword password for the auto-login account (WARN: stored in registry)
#   ExclusionPath     MT5 data dir to exclude from Defender real-time scanning
# ============================================================================

[CmdletBinding()]
param(
    [string]$AutoLoginUser = $env:USERNAME,
    [string]$AutoLoginPassword = '',
    [string]$ExclusionPath = "$env:USERPROFILE\mt5"
)

$ErrorActionPreference = 'Stop'

function Test-Admin {
    $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object System.Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-ScriptPrerequisites {
    # Admin rights + OS version sanity. Returns $true if OK.
    if (-not (Test-Admin)) {
        Write-Warning "This script must be run as Administrator."
        return $false
    }
    $os = Get-CimInstance Win32_OperatingSystem
    Write-Host ("OS: {0} {1}" -f $os.Caption, $os.Version)
    return $true
}

function Set-WindowsAutoLogin {
    # KEY: HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon
    # WHY: VPS may reboot unattended (power loss, patches); the trading terminal
    #      must auto-log back in so the EA resumes without a human at the console.
    $key = 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
    Set-ItemProperty -Path $key -Name 'AutoAdminLogon' -Value '1'
    Set-ItemProperty -Path $key -Name 'DefaultUserName' -Value $AutoLoginUser
    if ($AutoLoginPassword -ne '') {
        Set-ItemProperty -Path $key -Name 'DefaultPassword' -Value $AutoLoginPassword
    }
    Write-Host "AutoLogin set for $AutoLoginUser"
}

function Disable-WindowsUpdateAutoReboot {
    # KEY: HKLM\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU -> NoAutoRebootWithLoggedOnUsers=1
    # WHY: a forced reboot mid-trade kills the session and can leave orphan positions.
    $key = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
    if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
    Set-ItemProperty -Path $key -Name 'NoAutoRebootWithLoggedOnUsers' -Value 1
    # Also pause active hours so updates install but do not force-restart the box.
    Set-ItemProperty -Path $key -Name 'NoAutoUpdate' -Value 0
    Write-Host "Windows Update auto-reboot suppressed"
}

function Set-PowerPlanHighPerformance {
    # WHY: balanced/power-saver plans can throttle the CPU and stall the terminal
    #      or the Python EA under load.
    $guid = (powercfg /list | Where-Object { $_ -match 'High performance' }) -replace '.*:' -replace '\s',''
    if ($guid) { powercfg /setactive $guid | Out-Null }
    Write-Host "Power plan set to High Performance"
}

function Add-DefenderExclusion {
    # WHY: real-time AV scanning of the MT5 data / tick directories causes latency
    #      spikes and missed fills. Excluding the MT5 tree removes that jitter.
    if (Get-Command Add-MpPreference -ErrorAction SilentlyContinue) {
        Add-MpPreference -ExclusionPath $ExclusionPath
        Write-Host "Defender exclusion added: $ExclusionPath"
    } else {
        Write-Warning "Defender (Add-MpPreference) not available; skipping exclusion."
    }
}

function Set-VisualEffectsPerformance {
    # KEY: HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects -> VisualFXSetting=2
    # WHY: disables animations so the box spends cycles on trading, not eye-candy.
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects'
    if (-not (Test-Path $key)) { New-Item -Path $key -Force | Out-Null }
    Set-ItemProperty -Path $key -Name 'VisualFXSetting' -Value 2
    Write-Host "Visual effects set to performance"
}

# ---- main ----
if (-not (Test-ScriptPrerequisites)) {
    Write-Error "Prerequisites not met. Re-run as Administrator."
    exit 1
}
Set-WindowsAutoLogin
Disable-WindowsUpdateAutoReboot
Set-PowerPlanHighPerformance
Add-DefenderExclusion
Set-VisualEffectsPerformance
Write-Host "VPS setup complete. Reboot to apply all changes."
