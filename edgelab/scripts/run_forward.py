"""P4: Demo forward-test harness (NO LIVE CAPITAL).

Generates today's paper book from the proven H5 sleeve + risk-capped H6 sleeve,
journals it to data/forward_journal.csv, and prints the live signals the combined
book would hold.

The TradeLocker executor is a STUB: it does NOT place orders. To go live (even
demo) you must supply API keys and uncomment the executor section — which is gated
behind an explicit env flag so it can never run by accident.
"""
from __future__ import annotations
import sys, os, warnings, csv
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.equity_xsmom import UNIVERSE
from edgelab.forward import (build_forward_book, current_h5_positions,
                             current_h6_position, JournalEntry)

JOURNAL = Path(__file__).resolve().parents[1] / "data" / "forward_journal.csv"
LIVE_FLAG = os.environ.get("EDGELAB_LIVE_EXEC", "").lower() in ("1", "true", "yes")


def main():
    feed = MarketDataFeed()
    prices = {s: feed.get(s, source="yfinance", interval="1d", years=10) for s in UNIVERSE}
    btc = feed.get("BTC/USDT", source="ccxt", interval="4h", years=5)

    # vol-parity weights from P3 (H5 80.2% / H6 19.8% over the overlap)
    weights = {"H5_equity": 0.802, "H6_crypto": 0.198}

    as_of = datetime.now(timezone.utc)
    h5_pos = current_h5_positions(prices, top_n=3)
    h6_pos = current_h6_position(btc)

    # last prices for unit sizing
    px_last = {s: float(df["close"].iloc[-1]) for s, df in prices.items()}
    px_last["BTC/USDT"] = float(btc["close"].iloc[-1])

    book = build_forward_book(as_of, h5_pos, h6_pos, weights, px_last)

    print(f"=== P4 FORWARD BOOK (paper) as_of {as_of.date()} ===")
    for e in book.entries:
        print(f"  {e.sleeve:10s} {e.symbol:10s} {e.direction:5s} "
              f"signal@{e.signal_price:.2f} weight={e.weight:.3f} units={e.units}")
    if not book.entries:
        print("  (flat — no active signals)")
    print(f"  note: {book.note}")
    print(f"  LIVE_EXEC={LIVE_FLAG} -> {'would place orders' if LIVE_FLAG else 'paper only, no orders sent'}")

    # journal to CSV (append, but de-dup same-day runs so re-running the
    # harness doesn't inflate the forward sample with identical snapshots)
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    today = as_of.date().isoformat()
    write_header = not JOURNAL.exists()
    existing_today = False
    if not write_header:
        import csv as _csv
        with open(JOURNAL, "r", newline="") as _f:
            _rows = list(_csv.DictReader(_f))
        existing_today = any(r["as_of"][:10] == today for r in _rows)
    if existing_today:
        print(f"  journal already has an entry for {today} -> skipping append "
              f"(re-run same day does not inflate the sample)")
    else:
        with open(JOURNAL, "a", newline="") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["as_of", "sleeve", "symbol", "direction", "signal_price",
                            "weight", "units", "live_fill_price", "live_fill_time", "status"])
            for e in book.entries:
                w.writerow([e.as_of.isoformat(), e.sleeve, e.symbol, e.direction,
                            e.signal_price, e.weight, e.units, "", "", e.status])
        print(f"  journaled -> {JOURNAL}")

    # STUB executor: never runs unless explicitly enabled. Demo only.
    if LIVE_FLAG:
        raise RuntimeError(
            "EDGELAB_LIVE_EXEC set: live execution stub reached. Wire TradeLocker "
            "demo API here with your own keys. Not implemented to avoid silent "
            "order placement.")


if __name__ == "__main__":
    main()
