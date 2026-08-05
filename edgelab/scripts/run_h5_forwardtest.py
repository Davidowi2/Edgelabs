"""H5 forward-test on Alpaca paper (Stage 2b).

Read-only by default: prints the CURRENT H5 signal (top-3 momentum ETFs) and
whether each is tradable on the Alpaca paper venue. With EDGELAB_ALPACA_FILL=1
it places equal-weight paper MARKET orders for the selected basket.

This is the honest "test in the market" step for the one proven edge (H5):
run it on a schedule, let paper fills accumulate, then compare OOS P&L to the
backtest (PF 1.39). It does NOT auto-trade live capital.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.data.market_feed import MarketDataFeed          # noqa: E402
from edgelab.strategy.equity_xsmom import (UNIVERSE,         # noqa: E402
                                            current_signal)  # noqa: E402
from edgelab.broker import alpaca                            # noqa: E402


def main() -> int:
    feed = MarketDataFeed()
    print("== fetching H5 universe (live, force refresh) ==")
    prices = {}
    for sym in UNIVERSE:
        try:
            prices[sym] = feed.get(sym, source="yfinance", interval="1d",
                                   years=5, force=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! {sym} fetch failed: {e}")
    if not prices:
        print("no price data; abort")
        return 1

    sig = current_signal(prices, top_n=3)
    print(f"== H5 current signal (as of {sig['as_of']}) ==")
    if sig["reason"]:
        print("  ", sig["reason"]); return 1
    for s, m in sig["ranked"]:
        mark = " <-- HOLD" if s in sig["selected"] else ""
        print(f"   {s:5s} mom={m*100:6.2f}%{mark}")

    print("== Alpaca paper tradability ==")
    snap = alpaca.snapshot()
    if not snap.get("connected"):
        print("  not connected:", snap.get("reason")); return 1
    print(f"  account {snap['account_number']} PV=${snap['portfolio_value']} "
          f"BP=${snap['buying_power']} positions={len(snap['positions'])}")

    selected = sig["selected"]
    plan = []
    for s in selected:
        tradable = alpaca.is_tradable(s)
        print(f"   {s:5s} tradable={tradable}")
        if tradable:
            plan.append(s)

    fill = os.environ.get("EDGELAB_ALPACA_FILL", "0") == "1"
    if not fill:
        print("\n[READ-ONLY] set EDGELAB_ALPACA_FILL=1 to place paper orders for:",
              plan)
        return 0

    # Place equal-weight paper MARKET orders (~1/3 of equity each, fractional).
    pv = float(snap.get("portfolio_value") or 100000)
    per = pv / 3.0
    print("\n== PLACING PAPER ORDERS (Alpaca) ==")
    for s in plan:
        # size via latest close
        px = float(prices[s]["close"].dropna().iloc[-1])
        qty = round(per / px, 4)
        res = alpaca.place_paper_order(s, qty, "buy")
        print(f"   {s}: {res}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
