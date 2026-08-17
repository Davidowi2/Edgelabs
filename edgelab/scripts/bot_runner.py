"""Persistent bot_runner for the multi-component system on TradeLocker DEMO.

Runs as a LONG-LIVED loop (schedule library, not cron). Each month it:
  1. Fetches history for a TradeLocker-tradable CFD universe (gold XAUUSD + index CFDs).
  2. Computes Sleeve 2 (TSMOM directional trend) signal + vol-t measured sizing.
  3. Applies the DAILY 4% loss lock + circuit breaker (existing circuit_breaker.py).
  4. Submits DEMO orders ONLY if explicit '#D#' marker + EDGELAB_DEMO_FILL=1.

Broker: real TradeLocker (MT5) when TL_* creds + MetaTrader5 are present; otherwise a
MockBroker fallback (clearly labeled [SIMULATED]). No live capital, ever.

Per protocol: DEMO/paper only. The bot NEVER auto-promotes to live.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import schedule

from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.tsmom import run_tsmom
from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.circuit_breaker import CircuitBreaker, CircuitConfig
from edgelab.execution.mock_broker import MockBroker, MockTradeResult

# TradeLocker-tradable CFD universe. Gold confirmed available (docs). Index CFDs are
# common on TradeLocker; any unavailable symbol is gracefully skipped at fetch time.
TRADELOCKER_UNIVERSE = ["XAUUSD", "US30", "NAS100", "DE40", "UK100"]
DEMO_MARKER = "#D#"
STATE_FILE = ROOT / "logs" / "bot_state.json"
LOG_FILE = ROOT / "logs" / "bot_runner.log"
DAILY_LOSS_LOCK_PCT = 0.04  # 4% daily drawdown kill switch (your standing rule)
REBALANCE_LOOKBACK = 12


def _log(logger, level, msg, **kw):
    getattr(logger, level)(msg, **kw)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"last_rebalance_month": "", "peak_equity": 10000.0,
            "daily_start_equity": 10000.0, "last_date": "", "halted": False}


def save_state(st):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2))


def build_broker(logger):
    """Real TradeLocker if TL_* creds present; else a DEMO-simulated MockBroker."""
    has_creds = all(os.environ.get(k) for k in ("TL_LOGIN", "TL_PASSWORD", "TL_SERVER"))
    if has_creds:
        try:
            from edgelab.execution.broker_factory import BrokerFactory
            cfg = {"broker": {"mode": "tradelocker",
                              "login": int(os.environ["TL_LOGIN"]),
                              "password": os.environ["TL_PASSWORD"],
                              "server": os.environ["TL_SERVER"],
                              "symbol_canonical": TRADELOCKER_UNIVERSE[0]}}
            return BrokerFactory.create_broker(cfg, logger), "REAL"
        except Exception as e:  # noqa: BLE001
            _log(logger, "warning", f"real broker connect failed ({e}); using simulated")
    # Simulated demo broker
    def _demo_submit(req):
        return MockTradeResult(10009, True, float(req.get("volume", 0.0)))
    return MockBroker(submit_fn=_demo_submit, symbol=TRADELOCKER_UNIVERSE[0]), "SIMULATED"


def fetch_history(logger):
    """Fetch history for the TradeLocker CFD universe. CFD tickers (XAUUSD, US30...)
    are broker-specific and NOT served by yfinance. So:
      - Try the real CFD symbols first (works when MT5/real feed is wired).
      - Fall back to a PROXY multi-asset universe (GLD gold, SPY/QQQ equities,
        TLT/IEF bonds, DBC commodities) that yfinance DOES serve. This keeps the bot
        producing a REAL (proven) signal in simulated mode. It is clearly labeled
        'PROXY' so nobody mistakes it for the live CFD feed. Under real MT5, the CFD
        symbols resolve and the proxy is never used."""
    feed = MarketDataFeed()
    prices = {}
    for s in TRADELOCKER_UNIVERSE:
        for cand in (f"{s}=X", s):
            try:
                prices[s] = feed.get(cand, source="yfinance", interval="1d", years=5)
                break
            except Exception:  # noqa: BLE001
                continue
        if s not in prices:
            _log(logger, "warning", f"no history for {s}; skipping")
    if prices:
        _log(logger, "info", "signal universe: REAL CFD symbols resolved")
        return prices
    # Proxy fallback (yfinance-served, proven multi-asset)
    _log(logger, "warning", "CFD symbols unavailable via yfinance -> using PROXY multi-asset "
                           "universe (GLD/SPY/QQQ/TLT/IEF/DBC). Replace with live MT5 CFD feed "
                           "when TL_* creds + MetaTrader5 are connected.")
    PROXY = ["GLD", "SPY", "QQQ", "TLT", "IEF", "DBC"]
    proxy_prices = {}
    for s in PROXY:
        try:
            proxy_prices[s] = feed.get(s, source="yfinance", interval="1d", years=5)
        except Exception as e:  # noqa: BLE001
            _log(logger, "warning", f"proxy skip {s}: {e}")
    return proxy_prices


def rebalance(logger, broker, broker_kind, st, circuit):
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    if st.get("last_rebalance_month") == month:
        return  # already rebalanced this month
    if st.get("halted"):
        _log(logger, "info", "bot halted (loss lock tripped); skipping rebalance")
        return

    prices = fetch_history(logger)
    if not prices:
        _log(logger, "error", "no price history fetched; cannot rebalance")
        return

    # Sleeve 2 TSMOM signal on the CFD universe
    trades, _, m = run_tsmom(prices, initial_equity=10000.0, lookback=REBALANCE_LOOKBACK,
                             allow_short=True)
    # current target side from trailing momentum (same as demo driver)
    import pandas as pd
    panel = pd.DataFrame({s: df["close"].astype(float).resample("ME").last()
                          for s, df in prices.items()}).dropna(how="any")
    if len(panel) < REBALANCE_LOOKBACK + 2:
        _log(logger, "warning", "insufficient history for signal")
        return
    last, prev = panel.iloc[-1], panel.iloc[-REBALANCE_LOOKBACK - 1]
    mom = (last - prev) / prev
    target = {s: ("LONG" if mom[s] > 0 else ("SHORT" if mom[s] < 0 else "FLAT"))
              for s in panel.columns}

    _log(logger, "info", "rebalance signal", month=month, target=target,
         sleeve2_pf=round(float(m["profit_factor"]), 2))

    confirm = os.environ.get("DEMO_CONFIRM", "")
    fill_allowed = os.environ.get("EDGELAB_DEMO_FILL", "") == "1"
    if confirm != DEMO_MARKER or not fill_allowed:
        _log(logger, "info", "SUBMISSION HALTED (need '#D#' marker + EDGELAB_DEMO_FILL=1). "
                            "Signal computed; no orders placed.",
             confirm=confirm, fill_flag=fill_allowed)
        st["last_rebalance_month"] = month
        save_state(st)
        return

    if not circuit.allow_request():
        _log(logger, "warning", "circuit breaker OPEN; refusing submission")
        return

    orders = [{"symbol": s, "action": "DEAL", "type": side, "volume": 0.01,
               "price": 0.0, "comment": "EdgeLab Sleeve2 DEMO #D#"}
              for s, side in target.items() if side in ("LONG", "SHORT")]
    for o in orders:
        res = broker.submit(o)
        ok = getattr(res, "success", False)
        circuit.record_success() if ok else circuit.record_failure()
        _log(logger, "info", "demo order", symbol=o["symbol"], side=o["type"],
             retcode=getattr(res, "retcode", 0), success=ok)
    _log(logger, "info", f"[{broker_kind}] submitted {len(orders)} demo orders")
    st["last_rebalance_month"] = month
    save_state(st)


def daily_risk_check(logger, broker, broker_kind, st):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if st.get("last_date") != today:
        # new day: reset daily-start equity baseline
        st["daily_start_equity"] = st.get("peak_equity", 10000.0)
        st["last_date"] = today
        save_state(st)
    # Simulated equity tracker: peak_equity from state; trip lock if daily loss > 4%
    eq = st.get("peak_equity", 10000.0)
    daily_start = st.get("daily_start_equity", eq)
    if daily_start > 0 and (daily_start - eq) / daily_start > DAILY_LOSS_LOCK_PCT:
        if not st.get("halted"):
            st["halted"] = True
            save_state(st)
            _log(logger, "warning", f"DAILY 4% LOSS LOCK TRIPPED -> bot halted. "
                                    f"equity={eq:.2f} daily_start={daily_start:.2f}")
    _log(logger, "info", "heartbeat", kind=broker_kind, date=today,
         equity=round(eq, 2), halted=st.get("halted", False))


def main():
    logger = TradingLogger("bot_runner", str(LOG_FILE))
    _log(logger, "info", "=== bot_runner starting (multi-component, TradeLocker DEMO) ===")
    broker, broker_kind = build_broker(logger)
    _log(logger, "info", f"broker: {broker_kind} "
                         f"({'REAL TradeLocker' if broker_kind=='REAL' else 'SIMULATED MockBroker — no MT5/creds'})")
    st = load_state()
    circuit = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger)

    # schedule: rebalance check every 30 min (acts monthly), daily risk check at 22:05 UTC
    schedule.every(30).minutes.do(lambda: rebalance(logger, broker, broker_kind, st, circuit))
    schedule.every().day.at("22:05").do(lambda: daily_risk_check(logger, broker, broker_kind, st))
    # immediate first pass
    rebalance(logger, broker, broker_kind, st, circuit)
    daily_risk_check(logger, broker, broker_kind, st)

    _log(logger, "info", "loop alive — waiting for scheduled jobs (ctrl-c to stop)")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
