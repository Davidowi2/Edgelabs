#!/usr/bin/env python3
"""Dashboard supervisor (robustness): keeps the monitor alive + auto-restarts.

The old monitor was a hand-started server that died silently if it crashed. This
supervisor runs it as a child process, health-checks /api/health every 15s, and
restarts it if it stops or becomes unresponsive. Logs to logs/supervisor.log.

Run:  python scripts/run_dashboard_supervisor.py
Env:  same as run_dashboard.py (TL_*, APCA_*, EDGELAB_*).
Localhost only. No network exposure.
"""
from __future__ import annotations
import os, sys, time, subprocess, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LOG = ROOT / "logs"
LOG.mkdir(parents=True, exist_ok=True)
SLOG = LOG / "supervisor.log"
PORT = int(os.environ.get("DASH_PORT", "8765"))
HEALTH = f"http://127.0.0.1:{PORT}/api/health"
CHILD = [sys.executable, str(HERE / "run_dashboard.py")]


def log(line: str):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with SLOG.open("a") as f:
        f.write(f"{ts} {line}\n")


def healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    proc = None
    log("supervisor start")
    try:
        while True:
            if proc is None or proc.poll() is not None:
                if proc is not None:
                    log(f"child exited (rc={proc.returncode}); restarting")
                log("starting monitor")
                proc = subprocess.Popen(CHILD)
                time.sleep(3)
            if not healthy():
                log("health check FAILED; killing child")
                proc.kill()
                proc = None
                time.sleep(2)
                continue
            time.sleep(15)
    except KeyboardInterrupt:
        log("supervisor stop (keyboard interrupt)")
        if proc:
            proc.kill()


if __name__ == "__main__":
    main()
