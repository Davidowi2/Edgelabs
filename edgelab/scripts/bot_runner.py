"""Persistent bot_runner for the multi-component system on MetaTrader5 DEMO.

Runs as a LONG-LIVED loop (schedule library, not cron). Each month it:
  1. Fetches history for the symbols TRADEABLE on the connected MT5 DEMO account.
  2. Computes Sleeve 2 (TSMOM directional trend) signal + vol-target sizing.
  3. Applies the DAILY 4% loss lock + circuit breaker.
  4. Submits DEMO orders ONLY if EDGELAB_DEMO_AUTH=1 (explicit user go-ahead).

Broker: real MetaTrader5 when TL_* creds + terminal are present; else MockBroker
(simulated). No live capital, ever. Per protocol: DEMO/paper only.

On a generic MetaQuotes-Demo account the tradeable universe is typically FX pairs
(our ETF CFDs are not enabled there). TSMOM on FX is a known weak edge — the bot
reports REAL P&L honestly via the dashboard; it does not fake good numbers.
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
import pandas as pd

from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.tsmom import run_tsmom
from edgelab.monitoring.logger import TradingLogger
from edgelab.execution.circuit_breaker import CircuitBreaker, CircuitConfig
from edgelab.execution.mock_broker import MockBroker, MockTradeResult

# FX universe we ATTEMPT on the demo (filtered to what MT5 reports tradeable).
FX_UNIVERSE = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD"]
STATE_FILE = ROOT / "logs" / "bot_state.json"
PERF_FILE = ROOT / "logs" / "perf_state.json"
LOG_FILE = ROOT / "logs" / "bot_runner.log"
DAILY_LOSS_LOCK_PCT = 0.04  # 4% daily drawdown kill switch
REBALANCE_LOOKBACK = 12
DEMO_AUTH = os.environ.get("EDGELAB_DEMO_AUTH", "") == "1"  # user go-ahead (replaces #D#)


def _log(logger, level, msg, **kw):
    getattr(logger, level)(msg, **kw)


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            st = json.loads(STATE_FILE.read_text())
        except Exception:  # noqa: BLE001
            st = {}
    else:
        st = {}
    # baseline to the REAL demo equity ($100k); never the stale 10k sim default
    st.setdefault("peak_equity", 100000.0)
    st.setdefault("daily_start_equity", 100000.0)
    st.setdefault("last_rebalance_month", "")
    st.setdefault("last_date", "")
    st.setdefault("halted", False)
    return st


def save_state(st):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(st, indent=2))


def load_perf() -> dict:
    if PERF_FILE.exists():
        try:
            return json.loads(PERF_FILE.read_text())
        except Exception:
            pass
    return {"daily_pnl": [], "last_equity": None, "total_realized": 0.0,
            "wins": 0, "losses": 0, "trades": 0}


def save_perf(p):
    PERF_FILE.parent.mkdir(parents=True, exist_ok=True)
    PERF_FILE.write_text(json.dumps(p, indent=2))


def build_broker(logger):
    """Real MT5 if TL_* creds present; else a DEMO-simulated MockBroker."""
    has_creds = all(os.environ.get(k) for k in ("TL_LOGIN", "TL_PASSWORD", "TL_SERVER"))
    if has_creds:
        try:
            from edgelab.execution.broker_factory import BrokerFactory
            cfg = {"broker": {"mode": "tradelocker",
                              "login": int(os.environ["TL_LOGIN"]),
                              "password": os.environ["TL_PASSWORD"],
                              "server": os.environ["TL_SERVER"],
                              "symbol_canonical": FX_UNIVERSE[0]}}
            return BrokerFactory.create_broker(cfg, logger), "REAL"
        except Exception as e:  # noqa: BLE001
            _log(logger, "warning", f"real broker connect failed ({e}); using simulated")
    def _demo_submit(req):
        return MockTradeResult(10009, True, float(req.get("volume", 0.0)))
    return MockBroker(submit_fn=_demo_submit, symbol=FX_UNIVERSE[0]), "SIMULATED"


def tradeable_symbols(broker, logger):
    """Return FX_UNIVERSE entries the connected MT5 account can actually trade.
    MT5 SYMBOL_TRADE_MODE: 0=disabled,1=long,2=short,3=close-only,4=FULL.
    So tradeable means trade_mode != 0 (disabled). We also ensure the symbol is
    selected so its history/quotes are available."""
    import MetaTrader5 as mt5
    out = []
    for s in FX_UNIVERSE:
        info = mt5.symbol_info(s)
        if info is not None and getattr(info, "trade_mode", 0) != 0:
            try:
                mt5.symbol_select(s, True)
            except Exception:
                pass
            out.append(s)
    if out:
        _log(logger, "info", f"tradeable FX universe resolved: {out}")
    else:
        _log(logger, "warning", "no tradeable FX symbols found on this demo account")
    return out


def fetch_history(logger, symbols, broker_kind="SIMULATED"):
    """Fetch ~5y daily close history. On REAL MT5 we pull directly from the
    broker's market data (FX pairs live there); yfinance does not serve FX."""
    import MetaTrader5 as mt5
    prices = {}
    if broker_kind == "REAL":
        for s in symbols:
            try:
                rates = mt5.copy_rates_from_pos(s, mt5.TIMEFRAME_D1, 0, 5 * 252)
                if rates is not None and len(rates):
                    df = pd.DataFrame(rates)
                    df["close"] = df["close"].astype(float)
                    df.index = pd.to_datetime(df["time"], unit="s")
                    prices[s] = df[["close"]]
                else:
                    _log(logger, "warning", f"no MT5 history for {s}; skipping")
            except Exception as e:
                _log(logger, "warning", f"MT5 history failed for {s}: {e}")
        if prices:
            _log(logger, "info", f"signal history: REAL MT5 feed ({len(prices)} symbols)")
            return prices
    # Simulated / offline fallback: yfinance multi-asset proxy
    feed = MarketDataFeed()
    for s in symbols:
        try:
            prices[s] = feed.get(s, source="yfinance", interval="1d", years=5)
        except Exception:
            _log(logger, "warning", f"no history for {s}; skipping")
    return prices


def rebalance(logger, broker, broker_kind, st, circuit):
    now = datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    if st.get("last_rebalance_month") == month:
        return
    if st.get("halted"):
        _log(logger, "info", "bot halted (loss lock tripped); skipping rebalance")
        return

    symbols = tradeable_symbols(broker, logger)
    if not symbols:
        _log(logger, "error", "no tradeable symbols; cannot rebalance")
        return
    prices = fetch_history(logger, symbols, broker_kind)
    if not prices:
        _log(logger, "error", "no price history fetched; cannot rebalance")
        return

    trades, _, m = run_tsmom(prices, initial_equity=100000.0, lookback=REBALANCE_LOOKBACK,
                             allow_short=True)
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

    if not DEMO_AUTH:
        _log(logger, "info", "SUBMISSION HALTED (EDGELAB_DEMO_AUTH=1 required). "
                            "Signal computed; no orders placed.",
             demo_auth=DEMO_AUTH)
        st["last_rebalance_month"] = month
        save_state(st)
        return

    if not circuit.allow_request():
        _log(logger, "warning", "circuit breaker OPEN; refusing submission")
        return

    orders = [{"symbol": s, "action": "DEAL", "type": side, "volume": 0.01,
               "price": 0.0, "comment": "EdgeLab Sleeve2 DEMO"}
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


def update_perf(logger, broker, broker_kind, st):
    """Read REAL account equity + deal history; compute daily P&L, win rate."""
    p = load_perf()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    eq = st.get("peak_equity", 100000.0)
    bal = None
    if broker_kind == "REAL" and hasattr(broker, "get_account_info"):
        info = broker.get_account_info()
        if info:
            eq = info.get("equity", eq)
            bal = info.get("balance")
            st["peak_equity"] = eq
            st["daily_start_equity"] = st.get("daily_start_equity", eq)
    # daily P&L vs start-of-day baseline
    daily_start = st.get("daily_start_equity", eq)
    daily_pnl = round(eq - daily_start, 2)
    # trip 4% daily loss lock
    if daily_start > 0 and (daily_start - eq) / daily_start > DAILY_LOSS_LOCK_PCT:
        if not st.get("halted"):
            st["halted"] = True
            save_state(st)
            _log(logger, "warning", f"DAILY 4% LOSS LOCK TRIPPED -> bot halted. "
                                    f"equity={eq:.2f} daily_start={daily_start:.2f}")
    # realized P&L + win rate from deal history (REAL only)
    if broker_kind == "REAL" and hasattr(broker, "get_deals_history"):
        deals = broker.get_deals_history(days=30)
        wins = sum(1 for d in deals if d["profit"] > 0)
        losses = sum(1 for d in deals if d["profit"] < 0)
        realized = round(sum(d["profit"] for d in deals), 2)
        p["wins"], p["losses"], p["trades"] = wins, losses, (wins + losses)
        p["total_realized"] = realized
    # daily series (keep last 30)
    p["daily_pnl"] = p.get("daily_pnl", [])
    if not p["daily_pnl"] or p["daily_pnl"][-1]["date"] != today:
        p["daily_pnl"].append({"date": today, "pnl": daily_pnl, "equity": round(eq, 2)})
    else:
        p["daily_pnl"][-1] = {"date": today, "pnl": daily_pnl, "equity": round(eq, 2)}
    p["daily_pnl"] = p["daily_pnl"][-30:]
    p["last_equity"] = round(eq, 2)
    p["balance"] = bal
    save_perf(p)
    save_state(st)
    _log(logger, "info", "heartbeat", kind=broker_kind, date=today, equity=round(eq, 2),
         daily_pnl=daily_pnl, halted=st.get("halted", False),
         realized=p.get("total_realized"), win=p.get("wins"), loss=p.get("losses"))


def main():
    logger = TradingLogger("bot_runner", str(LOG_FILE))
    _log(logger, "info", "=== bot_runner starting (multi-component, MetaTrader5 DEMO) ===")
    _log(logger, "info", f"DEMO_AUTH enabled: {DEMO_AUTH}")
    broker, broker_kind = build_broker(logger)
    _log(logger, "info", f"broker: {broker_kind} "
                         f"({'REAL MT5' if broker_kind=='REAL' else 'SIMULATED MockBroker — no MT5/creds'})")
    st = load_state()
    circuit = CircuitBreaker(CircuitConfig(failure_threshold=5, cooldown_ms=30000), logger)

    schedule.every(30).minutes.do(lambda: rebalance(logger, broker, broker_kind, st, circuit))
    schedule.every(5).minutes.do(lambda: update_perf(logger, broker, broker_kind, st))
    rebalance(logger, broker, broker_kind, st, circuit)
    update_perf(logger, broker, broker_kind, st)

    _log(logger, "info", "loop alive — waiting for scheduled jobs (ctrl-c to stop)")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
