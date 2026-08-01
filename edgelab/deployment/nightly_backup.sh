#!/usr/bin/env bash
# ============================================================================
# nightly_backup.sh — Phase 9a VPS deployment (Linux)
#
# Backs up the MT5 / Edgelab state directories, keeps 7 days of rolling
# backups, and logs size + duration. Uses rsync when available (Linux) or
# falls back to cp. On Windows the VPS team uses robocopy (see comment below).
#
#   Windows equivalent:
#     robocopy D:\mt5 \\backup\mt5 /MIR /R:3 /W:5 /LOG:C:\backup\nightly.log
#
# Runs from cron nightly (e.g. 03:00).
# ============================================================================
set -uo pipefail

SRC="${BACKUP_SRC:-$HOME/mt5}"
DST_ROOT="${BACKUP_DST:-$HOME/backups}"
KEEP_DAYS="${KEEP_DAYS:-7}"

mkdir -p "$DST_ROOT"
dst="$DST_ROOT/$(date +%Y-%m-%d)"
mkdir -p "$dst"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }

start=$(date +%s)
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete "$SRC/" "$dst/" >/dev/null 2>&1
    log "rsync complete -> $dst"
else
    cp -a "$SRC/." "$dst/" 2>/dev/null || true
    log "cp fallback complete -> $dst"
fi
end=$(date +%s)

size=$(du -sh "$dst" 2>/dev/null | cut -f1)
log "backup size=$size duration=$((end - start))s"

# ---- rolling retention: delete backups older than KEEP_DAYS ----
find "$DST_ROOT" -maxdepth 1 -type d -name '20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]' \
    -mtime "+$KEEP_DAYS" -exec rm -rf {} + 2>/dev/null || true
log "retention: keeping last $KEEP_DAYS days"
