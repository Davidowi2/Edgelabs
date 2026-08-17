"""EdgeLabs launcher entry point (robust, Task-Scheduler safe).

Why this exists: Task Scheduler / cmd.exe `.bat` `for /f` env parsing is
fragile with special characters (e.g. an MT5 password containing `*`). This
script loads `.env` in pure Python (handles comments, quotes, special chars),
then spawns the bot + dashboard as DETACHED pythonw processes so they keep
running after Hermes / the launching shell closes.

Run directly:
    pythonw.exe "C:\...\launcher\run.py"
or via the .bat wrappers / Task Scheduler task "EdgelabsBot".
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict

LAUNCHER_DIR = Path(__file__).resolve().parent          # .../edgelab/launcher
REPO = LAUNCHER_DIR.parent                              # .../edgelab
VENV_PY = Path(r"C:/Users/Legacy/AppData/Local/hermes/hermes-agent/venv/Scripts/pythonw.exe")
BOT = REPO / "scripts" / "bot_runner.py"
DASH = REPO / "scripts" / "run_dashboard.py"
LOGDIR = REPO / "logs"
ENV_FILE = LAUNCHER_DIR / ".env"


def load_env(path: Path) -> Dict[str, str]:
    """Parse KEY=VALUE, skipping '#' comments and blank lines.
    Strips surrounding single/double quotes. No fragile shell parsing."""
    out: Dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if len(key) < 1:
            continue
        # strip surrounding quotes
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        out[key] = val
    return out


def main() -> int:
    LOGDIR.mkdir(parents=True, exist_ok=True)
    env = load_env(ENV_FILE)
    # inject into the environment our children inherit
    for k, v in env.items():
        os.environ[k] = v

    if not VENV_PY.exists():
        sys.stderr.write(f"FATAL: venv pythonw not found at {VENV_PY}\n")
        return 2
    if not BOT.exists() or not DASH.exists():
        sys.stderr.write("FATAL: bot_runner.py / run_dashboard.py not found\n")
        return 2

    creationflags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NO_WINDOW
    procs = []
    for name, script, logname in (("bot", BOT, "launcher_bot.log"),
                                   ("dash", DASH, "launcher_dash.log")):
        log = LOGDIR / logname
        try:
            with open(log, "ab") as lf:
                p = subprocess.Popen(
                    [str(VENV_PY), str(script)],
                    cwd=str(REPO),
                    env=os.environ.copy(),
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                    close_fds=True,
                )
            procs.append((name, p.pid))
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"FATAL: failed to launch {name}: {e}\n")
            return 1

    dash_port = env.get("DASH_PORT", "8080")
    msg = (f"EdgeLabs launched: {procs}. "
           f"Dashboard: http://127.0.0.1:{dash_port}/  "
           f"Bot is running on MT5 DEMO (or simulated if no creds).\n")
    sys.stdout.write(msg)
    # write a tiny marker so we can confirm the launcher ran
    (LOGDIR / "launcher_ran.log").write_text(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
