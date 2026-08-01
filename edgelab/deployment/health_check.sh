#!/usr/bin/env bash
# ============================================================================
# health_check.sh — Phase 9a VPS deployment (Linux)
#
# Reports the VPS / MT5 health as HEALTHY / DEGRADED / CRITICAL and exits with
# a code suitable for external monitoring (0 healthy, 1 degraded, 2 critical).
#
# Checks: terminal process alive, recent log activity, disk space, and that
# the Edgelab EA log has recent entries.
# ============================================================================
set -uo pipefail

MT5_LOG="${MT5_LOG:-$HOME/mt5/MT5_Instance1/MQL5/Files/Edgelab/ea.log}"
WATCHDOG_LOG="${WATCHDOG_LOG:-$HOME/mt5/watchdog.log}"
DISK_PATH="${DISK_PATH:-$HOME}"
MIN_FREE_GB="${MIN_FREE_GB:-2}"
FRESHNESS_MIN="${FRESHNESS_MIN:-15}"

status=0
lines=()

check() {
    local name="$1"; local ok="$2"; local detail="$3"
    if [[ "$ok" == "1" ]]; then
        lines+=("OK   | $name | $detail")
    else
        lines+=("FAIL | $name | $detail")
        if [[ "$name" == "process" || "$name" == "disk" ]]; then
            status=2
        else
            [[ "$status" -lt 1 ]] && status=1
        fi
    fi
}

# 1) process
if pgrep -f "terminal64.exe" >/dev/null 2>&1; then
    check "process" 1 "terminal64.exe running"
else
    check "process" 0 "terminal64.exe not running"
fi

# 2) recent EA log activity
if [[ -f "$MT5_LOG" ]]; then
    # minutes since last modification
    age_min=$(( ( $(date +%s) - $(stat -c %Y "$MT5_LOG") ) / 60 ))
    if [[ "$age_min" -le "$FRESHNESS_MIN" ]]; then
        check "log_fresh" 1 "ea.log updated ${age_min}m ago"
    else
        check "log_fresh" 0 "ea.log stale (${age_min}m old)"
    fi
else
    check "log_fresh" 0 "ea.log missing"
fi

# 3) disk space
free_gb=$(df -P "$DISK_PATH" 2>/dev/null | awk 'NR==2 {print int($4/1024/1024)}')
if [[ -n "${free_gb:-}" && "$free_gb" -ge "$MIN_FREE_GB" ]]; then
    check "disk" 1 "${free_gb}GB free"
else
    check "disk" 0 "${free_gb:-?}GB free (need >=${MIN_FREE_GB}GB)"
fi

# 4) watchdog log present
if [[ -f "$WATCHDOG_LOG" ]]; then
    check "watchdog" 1 "watchdog.log present"
else
    check "watchdog" 0 "watchdog.log missing"
fi

echo "=== EdgeLab VPS health: $( [[ $status -eq 0 ]] && echo HEALTHY || ( [[ $status -eq 1 ]] && echo DEGRADED || echo CRITICAL ) ) ==="
printf '%s\n' "${lines[@]}"
exit $status
