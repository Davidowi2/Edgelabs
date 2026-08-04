"""Launch the Edgelabs monitoring dashboard (read-only, localhost only)."""
from __future__ import annotations
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from edgelab.dashboard.server import main

if __name__ == "__main__":
    main(int(os.environ.get("DASH_PORT", "8765")))
