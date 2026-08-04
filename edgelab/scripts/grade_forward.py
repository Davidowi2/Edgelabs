"""P4 grader driver: read the forward journal, pull live marks, grade.

No live capital, no orders. Pure reporting so the 3-month forward test can be
judged against the backtest profile. Run after the journal has accumulated
(monthly run_forward.py entries).
"""
from __future__ import annotations
import sys, os, warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from edgelab.data.market_feed import MarketDataFeed
from edgelab.forward.grade import grade_forward

JOURNAL = Path(__file__).resolve().parents[1] / "data" / "forward_journal.csv"
# H5 (equity momentum) is structurally net-long-positive; H6 (crypto trend) too.
EXPECTED_SIGN = {"H5_equity": 1.0, "H6_crypto": 1.0}


def _parse_rows():
    if not JOURNAL.exists():
        return []
    df = pd.read_csv(JOURNAL)
    rows = []
    for _, r in df.iterrows():
        rows.append({
            "as_of": pd.to_datetime(r["as_of"], utc=True),
            "symbol": str(r["symbol"]),
            "direction": str(r["direction"]),
            "signal_price": float(r["signal_price"]),
            "weight": float(r["weight"]),
            "sleeve": str(r.get("sleeve", "")),
        })
    return rows


def main():
    rows = _parse_rows()
    if not rows:
        print("No journal rows. Run scripts/run_forward.py to seed the paper book.")
        return
    # latest marks for all symbols seen
    feed = MarketDataFeed()
    syms = {r["symbol"] for r in rows}
    marks = {}
    for s in syms:
        try:
            if s == "BTC/USDT":
                d = feed.get(s, source="ccxt", interval="4h", years=5)
            else:
                d = feed.get(s, source="yfinance", interval="1d", years=1)
            marks[s] = float(d["close"].iloc[-1])
        except Exception as e:
            marks[s] = None
            print(f"  (mark fetch failed for {s}: {e})")
    # grade per sleeve + combined
    for sleeve in ("H5_equity", "H6_crypto"):
        srows = [r for r in rows if r.get("sleeve") == sleeve]
        if not srows:
            continue
        smarks = {r["symbol"]: marks.get(r["symbol"]) or r["signal_price"] for r in srows}
        g = grade_forward(srows, smarks, expected_annual_sign=EXPECTED_SIGN[sleeve])
        print(f"=== {sleeve} forward grade ===")
        print(f"  signals={g.n_signals} window={g.window_start.date()}..{g.window_end.date()}")
        print(f"  forward return={g.forward_return_pct:.2f}%  maxDD={g.forward_max_dd_pct:.2f}%")
        print(f"  verdict: {g.verdict} -- {g.detail}")
    # combined book grade (all rows together, weights already net)
    allmarks = {r["symbol"]: marks.get(r["symbol"]) or r["signal_price"] for r in rows}
    g = grade_forward(rows, allmarks, expected_annual_sign=1.0)
    print(f"=== COMBINED forward grade ===")
    print(f"  signals={g.n_signals}  return={g.forward_return_pct:.2f}%  maxDD={g.forward_max_dd_pct:.2f}%")
    print(f"  verdict: {g.verdict} -- {g.detail}")


if __name__ == "__main__":
    main()
