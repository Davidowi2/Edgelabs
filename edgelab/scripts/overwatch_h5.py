"""H5 overwatch (Stage 2b autonomous monitor + rebalancer).

Reads Alpaca paper positions + the live H5 signal, enforces the 4% DD gate,
and (if EDGELAB_ALPACA_FILL=1) rebalances the paper book to match the signal.
Alerts on anomalies. Skips when the market is closed (no spam).

Modes:
  --status-only   report only, never trade (used by the fill-confirm cron)
  (default)       trade if EDGELAB_ALPACA_FILL=1, else report intended actions

Paper only. Live host is hard-refused by edgelab.broker.alpaca. No live capital.
"""
from __future__ import annotations

import os
import sys
import json
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.data.market_feed import MarketDataFeed          # noqa: E402
from edgelab.strategy.equity_xsmom import (UNIVERSE,         # noqa: E402
                                            current_signal)  # noqa: E402
from edgelab.broker import alpaca                            # noqa: E402

DD_CAP_PCT = 4.0          # hard risk gate from RESEARCH_PROTOCOL_v1
INITIAL_EQUITY = 100_000  # Alpaca paper start

LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = LOG_DIR / "overwatch_state.json"
LOG_FILE = LOG_DIR / "overwatch.log"


def _write_state(state: dict) -> None:
    """Persist the latest overwatch snapshot so the dashboard can show it."""
    try:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def _log(line: str) -> None:
    try:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with LOG_FILE.open("a") as f:
            f.write(f"{ts} {line}\n")
    except Exception:
        pass


def _market_open() -> bool:
    try:
        req = urllib.request.Request(
            "https://paper-api.alpaca.markets/v2/clock",
            headers={"APCA-API-KEY-ID": os.environ.get("APCA_API_KEY_ID", ""),
                     "APCA-API-SECRET-KEY": os.environ.get("APCA_API_SECRET_KEY", "")},
            method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            return bool(json.loads(r.read().decode()).get("is_open"))
    except Exception:
        return False


def main() -> int:
    status_only = "--status-only" in sys.argv
    fill = (not status_only) and os.environ.get("EDGELAB_ALPACA_FILL", "0") == "1"

    # Skip when closed (no spam) but still heartbeat so the dashboard knows
    # the watcher is alive and why nothing is happening.
    if not _market_open():
        _write_state({"market_open": False, "status": "closed",
                      "note": "US market closed — watcher idle, no action"})
        _log("closed — idle")
        return 0

    snap = alpaca.snapshot()
    if not snap.get("connected"):
        print("OVERWATCH: Alpaca not connected:", snap.get("reason"))
        _write_state({"market_open": True, "connected": False,
                      "reason": snap.get("reason")})
        _log(f"not connected: {snap.get('reason')}")
        return 0

    # live H5 signal (cached feed; monthly signal doesn't need force refresh)
    feed = MarketDataFeed()
    prices = {}
    for sym in UNIVERSE:
        try:
            prices[sym] = feed.get(sym, source="yfinance", interval="1d", years=5)
        except Exception:
            pass
    sig = current_signal(prices, top_n=3) if prices else {"selected": [], "reason": "no data"}
    desired = set(sig.get("selected", []))

    positions = snap.get("positions", [])
    held = {p["symbol"] for p in positions}
    pv = float(snap.get("portfolio_value") or INITIAL_EQUITY)

    # ---- DD gate ----
    upl = sum(float(p.get("unrealized_pl") or 0) for p in positions)
    dd_pct = (upl / INITIAL_EQUITY) * 100 if INITIAL_EQUITY else 0.0
    breach = dd_pct <= -DD_CAP_PCT

    lines = []
    lines.append(f"OVERWATCH {snap['account_number']} PV=${pv:,.0f} uPnL=${upl:,.2f} DD={dd_pct:.2f}%")
    lines.append(f"  H5 signal({sig.get('as_of')}): {sorted(desired)}")
    lines.append(f"  held: {sorted(held)}")

    if breach:
        lines.append(f"  *** DD BREACH ({dd_pct:.2f}% <= -{DD_CAP_PCT}%) — HALT, no trades, alert ***")
        print("\n".join(lines))
        _write_state({"market_open": True, "connected": True, "dd_breach": True,
                      "dd_pct": round(dd_pct, 2), "dd_cap": DD_CAP_PCT,
                      "portfolio_value": pv, "unrealized_pl": upl,
                      "signal": sorted(desired), "held": sorted(held),
                      "status": "HALTED (DD breach)"})
        _log(f"BREACH dd={dd_pct:.2f}% — halted")
        return 0

    # ---- rebalance ----
    sell_list = sorted(held - desired)
    buy_list = sorted(desired - held)
    if not sell_list and not buy_list:
        lines.append("  in balance — no action")
        print("\n".join(lines))
        _write_state({"market_open": True, "connected": True, "dd_breach": False,
                      "dd_pct": round(dd_pct, 2), "dd_cap": DD_CAP_PCT,
                      "portfolio_value": pv, "unrealized_pl": upl,
                      "signal": sorted(desired), "held": sorted(held),
                      "status": "in balance — no action", "mode": "trade" if fill else "read-only"})
        _log("in balance — no action")
        return 0

    lines.append(f"  rebalance: sell={sell_list} buy={buy_list}")
    if not fill:
        lines.append("  [READ-ONLY] set EDGELAB_ALPACA_FILL=1 to execute")
        print("\n".join(lines))
        _write_state({"market_open": True, "connected": True, "dd_breach": False,
                      "dd_pct": round(dd_pct, 2), "dd_cap": DD_CAP_PCT,
                      "portfolio_value": pv, "unrealized_pl": upl,
                      "signal": sorted(desired), "held": sorted(held),
                      "status": "rebalance pending (read-only)", "mode": "read-only",
                      "rebalance": {"sell": sell_list, "buy": buy_list}})
        _log(f"rebalance pending (read-only): sell={sell_list} buy={buy_list}")
        return 0

    # execute (paper)
    for s in sell_list:
        p = next(p for p in positions if p["symbol"] == s)
        res = alpaca.place_paper_order(s, float(p["qty"]), "sell")
        lines.append(f"  SELL {s} {res}")
    per = pv / 3.0
    for s in buy_list:
        px = float(prices[s]["close"].dropna().iloc[-1])
        qty = round(per / px, 4)
        res = alpaca.place_paper_order(s, qty, "buy")
        lines.append(f"  BUY {s} {qty} @~{px:.2f} {res}")
    print("\n".join(lines))
    _write_state({"market_open": True, "connected": True, "dd_breach": False,
                  "dd_pct": round(dd_pct, 2), "dd_cap": DD_CAP_PCT,
                  "portfolio_value": pv, "unrealized_pl": upl,
                  "signal": sorted(desired), "held": sorted(desired),
                  "status": "rebalanced", "mode": "trade",
                  "rebalance": {"sell": sell_list, "buy": buy_list}})
    _log(f"rebalanced: sell={sell_list} buy={buy_list}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
