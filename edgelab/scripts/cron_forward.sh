#!/usr/bin/env bash
# Monthly forward-test journal job (no_agent cron target).
# Journals the current H5+H6 paper book to data/forward_journal.csv.
# De-duped per day inside run_forward.py, so one snapshot per monthly run.
# NO live capital: the executor stub refuses to act without EDGELAB_LIVE_EXEC=1.
set -u
PY="C:/Users/Legacy/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"
cd "C:/Users/Legacy/Edgelabs/edgelab" || { echo "edgelab dir missing"; exit 1; }
"$PY" scripts/run_forward.py 2>&1
