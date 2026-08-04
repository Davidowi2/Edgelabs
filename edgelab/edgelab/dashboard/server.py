"""Edgelabs monitoring dashboard server (read-only, localhost only).

Serves a mobile-first dashboard that shows:
  - the combined paper book + 4% DD-budget gauge,
  - H5 (proven) / H6 (risk-capped) sleeve cards,
  - the forward journal,
  - a TradeLocker DEMO panel (read-only; credentials from session env only).

No authentication on the dashboard itself (per request: monitor with no
password). It binds to 127.0.0.1 only and never exposes itself to the network.
The TradeLocker connector is READ-ONLY: it never places orders. The order
executor remains gated behind EDGELAB_LIVE_EXEC=1 (never set here).

Run:  python scripts/run_dashboard.py   (or: python edgelab/dashboard/server.py)
"""
from __future__ import annotations
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    import requests
except Exception:  # pragma: no cover - optional dep
    requests = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edgelab.forward import current_h5_positions, current_h6_position
from edgelab.forward.grade import grade_forward

HERE = Path(__file__).resolve().parent
# server.py lives in edgelab/edgelab/dashboard; the data dir is edgelab/edgelab/data
JOURNAL = Path(__file__).resolve().parents[2] / "data" / "forward_journal.csv"
DD_BUDGET = 4.0

# --- lightweight TTL cache so we don't hit market APIs every refresh ---
_CACHE = {"ts": 0.0, "book": None}
_CACHE_TTL = 300.0  # seconds


def _read_journal_rows():
    if not JOURNAL.exists():
        return []
    rows = []
    with open(JOURNAL, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "as_of": r["as_of"], "sleeve": r.get("sleeve", ""), "symbol": r["symbol"],
                "direction": r["direction"], "signal_price": float(r["signal_price"]),
                "weight": float(r["weight"]), "units": float(r.get("units", 0) or 0),
            })
    return rows


def _current_book():
    now = time.time()
    if _CACHE["book"] and now - _CACHE["ts"] < _CACHE_TTL:
        return _CACHE["book"]
    try:
        from edgelab.data.market_feed import MarketDataFeed
        from edgelab.strategy.equity_xsmom import UNIVERSE
        feed = MarketDataFeed()
        prices = {s: feed.get(s, source="yfinance", interval="1d", years=10) for s in UNIVERSE}
        btc = feed.get("BTC/USDT", source="ccxt", interval="4h", years=5)
        h5 = current_h5_positions(prices, top_n=3)
        h6 = current_h6_position(btc)
    except Exception:
        h5, h6 = [], []  # offline fallback: empty book
    book = {"H5_equity": h5, "H6_crypto": h6}
    _CACHE.update(ts=now, book=book)
    return book


def build_state():
    rows = _read_journal_rows()
    # grader on the journal using entry prices as marks (day-0 view); the
    # live-mark grading is available via scripts/grade_forward.py.
    marks = {r["symbol"]: r["signal_price"] for r in rows}
    g = grade_forward(rows, marks, expected_annual_sign=1.0)
    return {
        "updated": datetime.now(timezone.utc).isoformat(),
        "dd_budget_pct": DD_BUDGET,
        "journal_rows": len(rows),
        "sleeves": _current_book(),
        "grader": {
            "verdict": g.verdict,
            "return_pct": round(g.forward_return_pct, 2),
            "max_dd_pct": round(g.forward_max_dd_pct, 2),
        },
    }


# ----------------------- TradeLocker read-only connector -----------------------
def tradelocker_demo_snapshot():
    """Read-only DEMO snapshot. Credentials from session env ONLY.
    Uses the OFFICIAL TradeLocker REST API (verified 2026-08-04 against
    github.com/TradeLocker/tradelocker-python):
      - DEMO host:  https://demo.tradelocker.com/backend-api
      - LIVE host:  https://api.tradelocker.com/backend-api
      - auth: POST /auth/jwt/token {email,password,server} -> accessToken
      - read-only: /auth/jwt/all-accounts, /trade/accounts/{id}/positions,
                   /trade/accounts/{id}/state, /trade/accounts/{id}/executions
    Never places orders. Refuses LIVE host (api.tradelocker.com) outright.
    """
    email = os.environ.get("TL_EMAIL")
    password = os.environ.get("TL_PASSWORD")
    server = os.environ.get("TL_SERVER", "")        # broker name, e.g. "Clarity FX"
    account_id = os.environ.get("TL_ACCOUNT_ID", "")  # e.g. "CLRTYFX#D#2329061"
    if not (email and password):
        return {"connected": False, "reason": "no TL_EMAIL/TL_PASSWORD in session env"}
    # --- fail-safe DEMO assertion -------------------------------------------
    # Accept ONLY an explicit DEMO marker. The real demo ID "CLRTYFX#D#..."
    # (the "#D#" segment) or the demo host confirms it. Bare "CLRTYFX" (no
    # "#D#") is NOT accepted; the LIVE host / any "PRD" tag is refused.
    acct_u = account_id.upper()
    srv_u = server.upper()
    is_demo = ("#D#" in acct_u) or ("DEMO" in acct_u) or ("DEMO" in srv_u)
    looks_prod = ("PRD" in acct_u) or ("PRD" in srv_u)
    if looks_prod:
        return {"connected": False,
                "reason": f"account/server '{account_id or server}' looks PRODUCTION (PRD); refusing (no live accounts)"}
    if not is_demo:
        return {"connected": False,
                "reason": f"account/server '{account_id or server}' not confirmed DEMO (need '#D#' marker); refusing"}

    # VERIFIED DEMO host (authoritative from TradeLocker's own Python lib).
    host = "https://demo.tradelocker.com"
    base = f"{host}/backend-api"
    if requests is None:
        return {"connected": False, "reason": "requests lib unavailable; cannot reach TradeLocker"}
    try:
        # 1) login (password -> JWT). Read-only: we never call order endpoints.
        r = requests.post(f"{base}/auth/jwt/token",
                          json={"email": email, "password": password, "server": server},
                          timeout=15)
        if r.status_code != 200:
            return {"connected": False, "reason": f"auth failed ({r.status_code}): {r.text[:160]}"}
        tok = r.json().get("accessToken") or r.json().get("accessToken")
        if not tok:
            return {"connected": False, "reason": "auth ok but no accessToken returned"}
        H = {"Authorization": f"Bearer {tok}"}
        # 2) discover accounts (read-only)
        acc = requests.get(f"{base}/auth/jwt/all-accounts", headers=H, timeout=15).json()
        accounts = acc.get("accounts", [])
        # 3) target the demo account id if supplied, else first
        target = next((a for a in accounts if account_id and str(a.get("id")) == account_id),
                      accounts[0] if accounts else None)
        if not target:
            return {"connected": False, "reason": "no accounts returned for this login"}
        aid = target.get("id")
        # 4) read-only positions + state
        pos = requests.get(f"{base}/trade/accounts/{aid}/positions", headers=H, timeout=15).json()
        st = requests.get(f"{base}/trade/accounts/{aid}/state", headers=H, timeout=15).json()
        positions = []
        for p in pos.get("positions", pos.get("data", [])):
            positions.append({
                "symbol": p.get("symbol") or p.get("instrumentName"),
                "side": "LONG" if (p.get("side") in (1, "1", "BUY")) else "SHORT",
                "qty": p.get("qty") or p.get("amount"),
            })
        bal = (st.get("accountBalance") or st.get("balance")
               or (st.get("data", {}) or {}).get("accountBalance"))
        eq = (st.get("equity") or (st.get("data", {}) or {}).get("equity"))
        return {
            "connected": True,
            "host": host,
            "account_id": aid,
            "balance": bal,
            "equity": eq,
            "positions": positions,
            "read_only": True,
            "orders_placed": 0,
        }
    except Exception as e:
        return {"connected": False, "reason": f"demo fetch error: {type(e).__name__}: {e}"}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (HERE / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if self.path == "/api/state":
            self._send(200, json.dumps(build_state()).encode())
            return
        if self.path == "/api/demo":
            self._send(200, json.dumps(tradelocker_demo_snapshot()).encode())
            return
        self._send(404, b'{"error":"not found"}')

    def log_message(self, *args):
        pass  # quiet


def main(port: int = 8765):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Edgelabs monitor: http://127.0.0.1:{port}  (localhost only, read-only)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main(int(os.environ.get("DASH_PORT", "8765")))
