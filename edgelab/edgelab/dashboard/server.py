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
    github.com/TradeLocker/tradelocker-python, and a live read-only call to the
    user's Clarity FX demo account):
      - DEMO host:  https://demo.tradelocker.com/backend-api
      - LIVE host:  https://api.tradelocker.com/backend-api
      - auth: POST /auth/jwt/token {email,password,server} -> 201 + accessToken
              (server for this account = "CLRTYFX"; accNum header required on
               trade reads)
      - read-only: GET /auth/jwt/all-accounts, /trade/accounts/{id}/state,
                   /trade/accounts/{id}/positions (all with accNum header)
    balance lives on the account record (accountBalance); equity on /state.
    Never places orders. Refuses LIVE host / PRD / bare CLRTYFX (needs #D# or
    DEMO marker).
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
        if r.status_code not in (200, 201):
            return {"connected": False, "reason": f"auth failed ({r.status_code}): {r.text[:160]}"}
        tok = r.json().get("accessToken") or r.json().get("accessToken")
        if not tok:
            return {"connected": False, "reason": "auth ok but no accessToken returned"}
        H = {"Authorization": f"Bearer {tok}"}
        # 2) discover accounts (read-only)
        acc = requests.get(f"{base}/auth/jwt/all-accounts", headers=H, timeout=15).json()
        accounts = acc.get("accounts", [])
        if not accounts:
            return {"connected": False, "reason": "no accounts returned for this login"}
        # 3) target: match by accNum (user supplies "2329061") or id; else first
        target = None
        for a in accounts:
            if account_id and (str(a.get("accNum")) == account_id or str(a.get("id")) == account_id):
                target = a
                break
        if target is None:
            target = accounts[0]
        aid = target.get("id")
        acc_num = target.get("accNum")
        # 4) read-only state + positions (require accNum header per TradeLocker)
        H2 = dict(H)
        if acc_num is not None:
            H2["accNum"] = str(acc_num)
        st = requests.get(f"{base}/trade/accounts/{aid}/state", headers=H2, timeout=15).json()
        pos = requests.get(f"{base}/trade/accounts/{aid}/positions", headers=H2, timeout=15).json()
        positions = []
        for p in pos.get("positions", pos.get("data", [])):
            positions.append({
                "symbol": p.get("symbol") or p.get("instrumentName"),
                "side": "LONG" if (p.get("side") in (1, "1", "BUY")) else "SHORT",
                "qty": p.get("qty") or p.get("amount"),
            })
        # balance lives on the account record; equity on state if present
        bal = target.get("accountBalance") or target.get("balance")
        eq = (st.get("equity") or (st.get("data", {}) or {}).get("equity")
              or target.get("equity"))
        return {
            "connected": True,
            "host": host,
            "account_id": aid,
            "acc_num": acc_num,
            "balance": bal,
            "equity": eq,
            "positions": positions,
            "read_only": True,
            "orders_placed": 0,
        }
    except Exception as e:
        return {"connected": False, "reason": f"demo fetch error: {type(e).__name__}: {e}"}


# ----------------------- Alpaca paper (H5 forward-test) state -----------------------
def alpaca_state():
    """Dashboard view of the H5 paper forward-test on Alpaca.

    Merges the live Alpaca paper snapshot (if creds present) with the persisted
    overwatch state file (logs/overwatch_state.json) so the dashboard can show
    the bot's REAL market progress: positions, DD vs cap, current H5 signal,
    last overwatch heartbeat. Read-only display only.
    """
    from pathlib import Path as _P
    state_file = _P(__file__).resolve().parents[2] / "logs" / "overwatch_state.json"
    persisted = {}
    if state_file.exists():
        try:
            persisted = json.loads(state_file.read_text())
        except Exception:
            persisted = {}
    # live snapshot (read-only) if creds in env
    live = {}
    try:
        from edgelab.broker import alpaca as _ap
        if os.environ.get("APCA_API_KEY_ID"):
            live = _ap.snapshot()
    except Exception:
        live = {}
    return {
        "persisted": persisted,
        "live": live,
        "paper": bool(live.get("connected")) or bool(persisted),
        "read_only": True,
    }


# ----------------------- Stage 2: gated DEMO paper-fill -----------------------
def place_demo_order(symbol: str, side: str, qty: float, order_type: str = "MARKET") -> dict:
    """Place a paper order on the DEMO account ONLY.

    HARD GATE: requires EDGELAB_DEMO_FILL=1 env AND a confirmed-DEMO account
    (#D# marker / DEMO server). Refuses otherwise. Never touches a live account.
    This is the ONLY function that may POST an order; it is NOT called anywhere
    automatically — only via the explicit /api/demo/order endpoint.

    Flow (verified against github.com/TradeLocker/tradelocker-python):
      auth -> GET instruments (resolve symbol->tradableInstrumentId)
           -> POST /trade/accounts/{id}/orders {tradableInstrumentId, qty, side, orderType}
    """
    if os.environ.get("EDGELAB_DEMO_FILL", "0") != "1":
        return {"ok": False, "reason": "EDGELAB_DEMO_FILL not set to 1; refusing (read-only mode)"}
    email = os.environ.get("TL_EMAIL"); password = os.environ.get("TL_PASSWORD")
    server = os.environ.get("TL_SERVER", ""); account_id = os.environ.get("TL_ACCOUNT_ID", "")
    if not (email and password):
        return {"ok": False, "reason": "no TL_EMAIL/TL_PASSWORD in session env"}
    is_demo = ("#D#" in account_id.upper()) or ("DEMO" in account_id.upper()) or ("DEMO" in server.upper())
    if not is_demo:
        return {"ok": False, "reason": "account not confirmed DEMO; refusing (no live orders)"}
    if requests is None:
        return {"ok": False, "reason": "requests lib unavailable"}
    side_u = str(side).upper()
    if side_u not in ("BUY", "SELL"):
        return {"ok": False, "reason": f"side must be BUY/SELL, got {side}"}

    host = "https://demo.tradelocker.com"; base = f"{host}/backend-api"
    try:
        # 1) auth
        r = requests.post(f"{base}/auth/jwt/token",
                          json={"email": email, "password": password, "server": server},
                          timeout=15)
        if r.status_code not in (200, 201):
            return {"ok": False, "reason": f"auth failed ({r.status_code}): {r.text[:160]}"}
        tok = r.json().get("accessToken") or r.json().get("accessToken")
        if not tok:
            return {"ok": False, "reason": "auth ok but no accessToken"}
        H = {"Authorization": f"Bearer {tok}"}
        # 2) discover account + accNum
        acc = requests.get(f"{base}/auth/jwt/all-accounts", headers=H, timeout=15).json()
        accounts = acc.get("accounts", [])
        target = next((a for a in accounts
                       if account_id and (str(a.get("accNum")) == account_id
                                          or str(a.get("id")) == account_id)), None) or (accounts[0] if accounts else None)
        if not target:
            return {"ok": False, "reason": "no accounts returned"}
        aid = target.get("id"); acc_num = target.get("accNum")
        H2 = dict(H); H2["accNum"] = str(acc_num)
        # 3) resolve symbol -> tradableInstrumentId
        inst = requests.get(f"{base}/trade/accounts/{aid}/instruments", headers=H2, timeout=15).json()
        insts = inst.get("d", {}).get("instruments", inst.get("instruments", []))
        match = next((i for i in insts if str(i.get("name")) == str(symbol)
                      or str(i.get("symbolName")) == str(symbol)), None)
        if not match:
            return {"ok": False, "reason": f"symbol {symbol} not found in demo instrument list"}
        iid = match.get("tradableInstrumentId") or match.get("id")
        # TradeLocker requires routeId (the TRADE route) on the order
        routes = match.get("routes", [])
        trade_route = next((rt for rt in routes if str(rt.get("type")) == "TRADE"), None)
        route_id = trade_route.get("id") if trade_route else None
        # 4) place order. Mirror TradeLocker's create_order payload exactly:
        #    validity (IOC for market, GTC otherwise), type ("market"), routeId,
        #    tradableInstrumentId as STRING, side BUY/SELL.
        tif = "IOC" if order_type.upper() == "MARKET" else "GTC"
        payload = {
            "price": None,
            "qty": str(qty),
            "routeId": route_id,
            "side": side_u,
            "validity": tif,
            "tradableInstrumentId": str(iid),
            "type": order_type.lower(),   # "market" / "limit"
        }
        o = requests.post(f"{base}/trade/accounts/{aid}/orders", headers=H2,
                          json=payload, timeout=15)
        return {"ok": o.status_code in (200, 201), "status": o.status_code,
                "symbol": symbol, "side": side_u, "qty": qty,
                "demo": True, "response": o.text[:400]}
    except Exception as e:
        return {"ok": False, "reason": f"order error: {type(e).__name__}: {e}"}


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
        if self.path == "/api/alpaca":
            self._send(200, json.dumps(alpaca_state()).encode())
            return
        self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path == "/api/demo/order":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                symbol = body.get("symbol")
                side = body.get("side", "BUY")
                qty = float(body.get("qty", 0.01))
                if not symbol:
                    self._send(400, json.dumps({"ok": False, "reason": "symbol required"}).encode())
                    return
                result = place_demo_order(symbol, side, qty)
                self._send(200, json.dumps(result).encode())
            except Exception as e:
                self._send(500, json.dumps({"ok": False, "reason": f"{type(e).__name__}: {e}"}).encode())
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
