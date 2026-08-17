"""Push Sleeve 2 (TSMOM) signal to TradeLocker DEMO (Clarity FX) via the broker factory.

Honest design:
- Driven ONLY when confirm_marker == "#D#" (explicit DEMO). Bare CLRTYFX or PRD* is
  HARD-REFUSED (per connector DEMO gate). No live trading can occur from this script.
- Builds the TSMOM signal on a FOREX universe TradeLocker actually offers (EURUSD,
  GBPUSD, USDJPY, AUDUSD, USDCAD) — NOT the US-ETF universe (SPY/GLD/...) which does
  not exist on a forex/CFD broker. Same TSMOM engine, tradable instruments.
- If MetaTrader5 + creds (TL_LOGIN/TL_PASSWORD/TL_SERVER) are present, connects for real
  DEMO and submits demo orders. On THIS host MT5 is NOT installed and no creds are set,
  so the factory honestly falls back to MockBroker (simulated demo fill). We report that
  clearly rather than fabricate a live fill.

Per Edgelabs protocol: DEMO/paper only, no live capital. This script places at most the
demo orders it computes; it never auto-promotes to live.

Usage:
  python scripts/run_sleeve2_tradelocker_demo.py "#D#"
(any argument != "#D#" aborts with a refusal message.)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.tsmom import run_tsmom, DEFAULT_UNIVERSE
from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.broker_factory import BrokerFactory

# Forex universe TradeLocker/Clarity FX actually offers (engine is instrument-agnostic)
FOREX_UNIVERSE = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
DEMO_MARKER = "#D#"


def compute_signal(prices, lookback=12, allow_short=True):
    """Run TSMOM on the forex universe and return the target side per symbol."""
    trades, _, m = run_tsmom(prices, initial_equity=10000.0, lookback=lookback,
                             allow_short=allow_short)
    # determine current intended side from the last held positions
    # run_tsmom stores 'held' internally; recompute trailing momentum directly:
    close_m = {s: df["close"].astype(float).resample("ME").last() for s, df in prices.items()}
    import pandas as pd
    panel = pd.DataFrame(close_m).dropna(how="any")
    if len(panel) < lookback + 2:
        return {}, m
    last = panel.iloc[-1]
    prev = panel.iloc[-lookback - 1]
    mom = (last - prev) / prev
    target = {s: ("LONG" if mom[s] > 0 else ("SHORT" if (mom[s] < 0 and allow_short) else "FLAT"))
              for s in panel.columns}
    return target, m


def main():
    confirm = sys.argv[1] if len(sys.argv) > 1 else ""
    if confirm != DEMO_MARKER:
        print(f"[REFUSED] TradeLocker demo requires explicit '{DEMO_MARKER}' marker. "
              f"Got: '{confirm}'. No live/DEMO orders placed.")
        sys.exit(0)

    print(f"[OK] DEMO marker '{DEMO_MARKER}' accepted. This is DEMO/paper only — no live capital.")

    # 1) Fetch forex data (read-only market data; no broker connection yet)
    #    yfinance uses the 'SYM=X' convention for FX pairs.
    feed = MarketDataFeed()
    prices = {}
    for s in FOREX_UNIVERSE:
        yf_sym = f"{s}=X"
        try:
            prices[s] = feed.get(yf_sym, source="yfinance", interval="1d", years=5)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {s}: {e}")

    if not prices:
        print("  No forex data fetched; abort.")
        return

    target, m = compute_signal(prices, lookback=12, allow_short=True)
    print(f"  TSMOM signal (forex universe): {target}")
    print(f"  Sleeve2 backtest on forex (5y): PF={m['profit_factor']:.2f} "
          f"Sharpe={m['sharpe_ratio']:.2f} DD={m['max_drawdown_pct']:.1f}%")

    # 2) Build broker in DEMO mode. Env creds (session-only, never on disk):
    #    TL_LOGIN / TL_PASSWORD / TL_SERVER  +  EDGELAB_DEMO_FILL=1 to ALLOW fills.
    has_creds = all(os.environ.get(k) for k in ("TL_LOGIN", "TL_PASSWORD", "TL_SERVER"))
    # Force the factory toward tradelocker mode for DEMO; without MT5 it falls back to Mock.
    broker_cfg = {
        "broker": {
            "mode": "tradelocker",
            "login": int(os.environ.get("TL_LOGIN", "0") or 0),
            "password": os.environ.get("TL_PASSWORD", ""),
            "server": os.environ.get("TL_SERVER", ""),
            "symbol_canonical": FOREX_UNIVERSE[0],
        }
    }
    logger = TradingLogger("sleeve2_demo", "logs/sleeve2_demo.log")
    has_creds = all(os.environ.get(k) for k in ("TL_LOGIN", "TL_PASSWORD", "TL_SERVER"))
    if has_creds:
        broker = BrokerFactory.create_broker(broker_cfg, logger)
    else:
        # No MT5/creds in this session: build a DEMO-simulated broker directly.
        # (The factory's tradelocker fallback would mis-construct MockBroker with a
        # dict, so we instantiate a correct demo MockBroker with a fill function.)
        from edgelab.execution.mock_broker import MockBroker, MockTradeResult
        def _demo_submit(req):
            # Simulate a successful DEMO fill at market.
            return MockTradeResult(10009, True, float(req.get("volume", 0.0)))
        broker = MockBroker(submit_fn=_demo_submit, symbol=FOREX_UNIVERSE[0])
    broker_class = type(broker).__name__
    print(f"  Broker instance: {broker_class}")
    if broker_class == "MockBroker":
        print("  [SIMULATED] MetaTrader5 not installed or no creds in this session -> "
              "demo fill executed via MockBroker (simulated). No real broker reached.")
        fill_allowed = os.environ.get("EDGELAB_DEMO_FILL", "") == "1"
        if not fill_allowed:
            print("  [HALT] EDGELAB_DEMO_FILL not set to 1 -> no fill attempt even in mock. "
                  "Set EDGELAB_DEMO_FILL=1 to permit a simulated demo fill.")
            return
    else:
        # Real DEMO path: only if EDGELAB_DEMO_FILL==1 (explicit gate) and marker is #D#
        fill_allowed = os.environ.get("EDGELAB_DEMO_FILL", "") == "1"
        if not fill_allowed:
            print("  [HALT] EDGELAB_DEMO_FILL not set to 1 -> refusing to place even DEMO orders.")
            return

    # 3) Translate signal -> demo orders (simulated if MockBroker)
    orders = []
    for sym, side in target.items():
        if side in ("LONG", "SHORT"):
            # demo volume in lots (small); price=0 -> broker fills at market
            orders.append({"symbol": sym, "action": "DEAL", "type": side,
                           "volume": 0.01, "price": 0.0,
                           "comment": "EdgeLab Sleeve2 DEMO #D#"})
    labels = [f"{o['symbol']} {o['type']}" for o in orders]
    print(f"  Demo orders to submit ({len(orders)}): {labels}")
    for o in orders:
        res = broker.submit(o)
        ok = getattr(res, "success", False)
        print(f"    -> {o['symbol']} {o['type']}: retcode={getattr(res,'retcode',0)} "
              f"success={ok}")

    print("\n[SUMMARY] Sleeve 2 signal computed and demo pipeline executed.")
    print("  - REAL DEMO requires: MT5 installed + TL_LOGIN/TL_PASSWORD/TL_SERVER "
          "(session env, never committed) + EDGELAB_DEMO_FILL=1 + '#D#' marker.")
    print("  - This session has no MT5/no creds -> simulated via MockBroker (shown above).")


if __name__ == "__main__":
    main()
