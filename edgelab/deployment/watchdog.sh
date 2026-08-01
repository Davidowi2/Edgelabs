#!/usr/bin/env bash
# ============================================================================
# watchdog.sh — Phase 9a VPS deployment (Linux)
#
# Keeps the MT5 terminal alive. Checks if terminal64.exe is running (via Wine)
# and restarts it if dead. Designed to run from cron every 5 minutes.
#
# Env overrides:
#   WATCHDOG_INTERVAL_SEC  (informational only; cron controls frequency)
#   WATCHDOG_LOG           log file path
#   WATCHDOG_ALERT_ON_RESTART  set to "1" to emit an alert line
#   MT5_TERMINAL_EXE       full path to terminal64.exe
#   MT5_LAUNCH_CMD         command used to (re)start the terminal
# ============================================================================
set -uo pipefail

WATCHDOG_LOG="${WATCHDOG_LOG:-$HOME/mt5/watchdog.log}"
MT5_TERMINAL_EXE="${MT5_TERMINAL_EXE:-$HOME/mt5/MT5_Instance1/terminal64.exe}"
MT5_LAUNCH_CMD="${MT5_LAUNCH_CMD:-wine "$MT5_TERMINAL_EXE"}"
ALERT_ON_RESTART="${WATCHDOG_ALERT_ON_RESTART:-0}"

mkdir -p "$(dirname "$WATCHDOG_LOG")"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

running=0
if pgrep -f "terminal64.exe" >/dev/null 2>&1; then
    running=1
fi

if [[ "$running" -eq 1 ]]; then
    echo "$(ts) HEALTHY: terminal64.exe is running" >> "$WATCHDOG_LOG"
    exit 0
fi

echo "$(ts) DEGRADED: terminal64.exe NOT running — restarting" >> "$WATCHDOG_LOG"
# Attempt restart
( nohup $MT5_LAUNCH_CMD >/dev/null 2>&1 & ) || true
sleep 3

if pgrep -f "terminal64.exe" >/dev/null 2>&1; then
    echo "$(ts) RECOVERED: terminal64.exe restarted" >> "$WATCHDOG_LOG"
    if [[ "$ALERT_ON_RESTART" == "1" ]]; then
        echo "$(ts) ALERT: MT5 was down and has been restarted" >> "$WATCHDOG_LOG"
    fi
    exit 0
else
    echo "$(ts) CRITICAL: terminal64.exe failed to restart" >> "$WATCHDOG_LOG"
    if [[ "$ALERT_ON_RESTART" == "1" ]]; then
        echo "$(ts) ALERT: MT5 restart FAILED — operator intervention required" >> "$WATCHDOG_LOG"
    fi
    exit 2
fi
