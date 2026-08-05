"""Alpaca paper-trading connector (Stage 2b: equities forward-test venue).

HARD GOVERNANCE (mirrors the TradeLocker connector):
  - Read-only by default. A read-only snapshot() pulls account + positions +
    orders from the PAPER endpoint only.
  - place_paper_order() requires EDGELAB_ALPACA_FILL=1 AND the paper host
    (https://paper-api.alpaca.markets). It REFUSES the live host
    (https://api.alpaca.markets) outright. Never touches a live account.
  - No scheduled/auto execution. Only invoked explicitly with the flag set.
  - Credentials come from session env (APCA_API_KEY_ID / APCA_API_SECRET_KEY),
    never written to disk or committed.

Alpaca REST (v2) order schema used:
  POST /v2/orders  {symbol, qty, side, type:"market", time_in_force:"day"}
"""
from __future__ import annotations

import os
import json
import urllib.request
import urllib.error
from typing import Optional


PAPER_HOST = "https://paper-api.alpaca.markets"
LIVE_HOST = "https://api.alpaca.markets"


def _host() -> str:
    # Force paper unless explicitly overridden; never default to live.
    return os.environ.get("ALPACA_HOST", PAPER_HOST)


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID": os.environ.get("APCA_API_KEY_ID", ""),
        "APCA-API-SECRET-KEY": os.environ.get("APCA_API_SECRET_KEY", ""),
        "Content-Type": "application/json",
    }


def snapshot() -> dict:
    """Read-only account + positions + orders snapshot (PAPER host only)."""
    host = _host()
    if LIVE_HOST in host:
        return {"connected": False, "reason": "refusing LIVE Alpaca host (paper only)"}
    key = os.environ.get("APCA_API_KEY_ID")
    if not key:
        return {"connected": False, "reason": "no APCA_API_KEY_ID in session env"}
    try:
        acc = _get(host + "/v2/account")
        positions = _get(host + "/v2/positions")
        orders = _get(host + "/v2/orders?status=all&limit=20")
        return {
            "connected": True,
            "host": host,
            "account_id": acc.get("id"),
            "account_number": acc.get("account_number"),
            "status": acc.get("status"),
            "portfolio_value": acc.get("portfolio_value"),
            "buying_power": acc.get("buying_power"),
            "cash": acc.get("cash"),
            "trading_blocked": acc.get("trading_blocked", False),
            "positions": [
                {"symbol": p.get("symbol"), "qty": p.get("qty"),
                 "side": "LONG" if float(p.get("qty", 0)) > 0 else "SHORT",
                 "avg_entry": p.get("avg_entry_price"),
                 "mkt_value": p.get("market_value")}
                for p in positions
            ],
            "orders": [
                {"id": o.get("id"), "symbol": o.get("symbol"),
                 "side": o.get("side"), "qty": o.get("qty"),
                 "status": o.get("status"), "type": o.get("type")}
                for o in orders
            ],
            "read_only": True,
        }
    except urllib.error.HTTPError as e:
        return {"connected": False, "reason": f"HTTP {e.code}: {e.read().decode()[:160]}"}
    except Exception as e:  # noqa: BLE001
        return {"connected": False, "reason": f"{type(e).__name__}: {e}"}


def is_tradable(symbol: str) -> bool:
    """Check an asset is tradable on the paper venue."""
    host = _host()
    if LIVE_HOST in host:
        return False
    try:
        a = _get(host + f"/v2/assets/{symbol}")
        return bool(a.get("tradable")) and a.get("status") == "active"
    except Exception:  # noqa: BLE001
        return False


def place_paper_order(symbol: str, qty: float, side: str = "buy") -> dict:
    """Place a PAPER order on the Alpaca paper account ONLY.

    HARD GATE: EDGELAB_ALPACA_FILL=1 AND paper host. Refuses live.
    side: 'buy' | 'sell'. qty: fractional shares supported.
    """
    if os.environ.get("EDGELAB_ALPACA_FILL", "0") != "1":
        return {"ok": False, "reason": "EDGELAB_ALPACA_FILL not set to 1; refusing (read-only mode)"}
    host = _host()
    if LIVE_HOST in host:
        return {"ok": False, "reason": "refusing LIVE Alpaca host; paper only"}
    key = os.environ.get("APCA_API_KEY_ID")
    if not key:
        return {"ok": False, "reason": "no APCA_API_KEY_ID in session env"}
    side_l = str(side).lower()
    if side_l not in ("buy", "sell"):
        return {"ok": False, "reason": f"side must be buy/sell, got {side}"}
    payload = {
        "symbol": symbol.upper(),
        "qty": str(qty),
        "side": side_l,
        "type": "market",
        "time_in_force": "day",
    }
    try:
        req = urllib.request.Request(
            host + "/v2/orders", data=json.dumps(payload).encode(),
            headers=_headers(), method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode())
        return {"ok": True, "paper": True, "symbol": symbol.upper(),
                "side": side_l, "qty": qty, "order_id": body.get("id"),
                "status": body.get("status")}
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=_headers(), method="GET")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())
