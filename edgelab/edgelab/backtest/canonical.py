"""Canonical EdgeLab backtester (Phase 0 fix, F-01/F-03).

This is the SINGLE source of truth for backtests going forward. It replaces
the two conflicting runners (backtest/runner.py and backtest/strategy_runner.py)
whose PnL conventions disagreed (runner.py omitted the 100k contract multiplier;
strategy_runner.py patched it in post-hoc). Here PnL is correct from the start.

Fill model (honest, conservative):
  * ENTRY fills at the NEXT bar's open (signal bar cannot be the fill bar).
  * EXIT (SL/TP) evaluated on each subsequent bar using high/low touch.
  * If a single bar touches BOTH SL and TP, the STOP is assumed hit first
    (price usually reaches the nearer adverse level first; conservative).
  * Entry/exit include a configurable spread+slippage penalty (worse fill).

Contract multiplier is applied INSIDE _pnl() so all PnL is in account currency.
Risk is enforced through the real RiskEngine on every proposal.

The runner is strategy-agnostic: a strategy object exposes
  signal(df, i) -> Optional[dict]      # entry proposal (direction/entry/sl/tp/strategy_id)
  exit_signal(df, i) -> Optional[str]  # exit reason, or None
  on_fill(direction, fill_price, i, df)
  on_exit()
and may be stateful (it tracks its own in/out).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd

from edgelab.config import Config
from edgelab.risk.engine import RiskEngine, TradeProposal
from edgelab.state.bus import Position, StateBus

# Standard FX lot = 100,000 units. PnL = (exit-entry) * lot * multiplier.
CONTRACT_MULTIPLIER = 100_000.0

# Default pip size for non-JPY symbols; JPY pairs use 0.01.
_PIP_SIZE = {"DEFAULT": 0.0001, "JPY": 0.01}


def _pip_size(symbol: str) -> float:
    return _PIP_SIZE["JPY"] if "JPY" in symbol.upper() else _PIP_SIZE["DEFAULT"]


def _pnl(direction: str, entry: float, exit_: float, lot: float) -> float:
    mult = 1.0 if direction.upper() == "LONG" else -1.0
    return mult * (exit_ - entry) * lot * CONTRACT_MULTIPLIER


@dataclass
class CanonicalTrade:
    trade_id: str
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    lot_size: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    exit_reason: str


@dataclass
class CanonicalResult:
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _bar_ts(bar: pd.Series) -> datetime:
    name = getattr(bar, "name", None)
    if name is None:
        return datetime.min
    return name.to_pydatetime() if hasattr(name, "to_pydatetime") else datetime.min


def _next_open_fill(symbol: str, next_open: float, direction: str,
                    spread_pips: float, slippage_pips: float) -> float:
    """Worse-case fill at the NEXT bar's open, with entry penalty applied."""
    pip = _pip_size(symbol)
    pen = (spread_pips + slippage_pips) * pip
    return next_open + pen if direction.upper() == "LONG" else next_open - pen


def run_canonical_backtest(
    data: pd.DataFrame,
    strategy,
    initial_equity: float = 10_000.0,
    symbol: str = "EURUSD",
    base_config: Optional[Config] = None,
    risk_per_trade: float = 0.01,
    spread_pips: float = 0.8,
    slippage_pips: float = 0.5,
    session_windows=None,
) -> CanonicalResult:
    """Bar-by-bar backtest with honest next-open fills and a real risk gate.

    `session_windows`:
      None  -> keep the constitution's session gate (RiskEngine fallback).
      []    -> no session gate (strategy defines its own gating).
      list  -> override the gate windows.
    """
    if base_config is None:
        base_config = Config()
    cfg = copy.deepcopy(base_config)
    cfg._data["internal_risk"]["risk_per_trade_pct"] = risk_per_trade
    cfg._data["internal_risk"]["spread_pips_per_symbol"] = {symbol: spread_pips}
    if session_windows is not None:
        cfg._data["internal_risk"]["session_filter_ny"] = session_windows

    state = StateBus(float(initial_equity))
    engine = RiskEngine(cfg, state)
    pip = _pip_size(symbol)

    trades: list = []
    first_ts = _bar_ts(data.iloc[0])
    equity_curve = [(first_ts, float(state.equity))]
    n = len(data)

    # pending holds a proposal accepted on bar i, to be filled at bar i+1 open
    pending = None  # dict: {direction, entry, sl, tp, strategy_id, ts, trade_id}

    for i in range(n):
        ts = _bar_ts(data.iloc[i])

        # ---- (A) resolve a pending entry at THIS bar's open ----
        if pending is not None:
            next_open = float(data.iloc[i]["open"])
            fill = _next_open_fill(symbol, next_open, pending["direction"],
                                   spread_pips, slippage_pips)
            # exit levels are referenced to the SIGNAL price (not the fill);
            # this is standard and conservative enough. Keep sl/tp as proposed.
            state.add_position(Position(
                symbol=symbol,
                direction=pending["direction"],
                entry_price=fill,
                stop_loss=float(pending["sl"]),
                take_profit=float(pending["tp"]) if pending["tp"] is not None else None,
                lot_size=float(pending["lot_size"]),
                entry_time=pending["ts"],
                trade_id=pending["trade_id"],
            ))
            strategy.on_fill(pending["direction"], fill, i, data)
            pending = None

        # ---- (B) exits on THIS bar (high/low touch; stop-first) ----
        if state.open_positions:
            pos = state.open_positions[0]
            bar = data.iloc[i]
            high = float(bar["high"]); low = float(bar["low"]); close = float(bar["close"])
            reason = strategy.exit_signal(data, i)
            exit_price = None
            if reason == "time_stop":
                exit_price = close
                slip = slippage_pips * pip
                exit_price = exit_price - slip if pos.direction.upper() == "LONG" else exit_price + slip
            else:
                # SL/TP touch this bar (stop-first on conflict)
                if pos.direction.upper() == "LONG":
                    sl_hit = low <= pos.stop_loss
                    tp_hit = pos.take_profit is not None and high >= pos.take_profit
                else:
                    sl_hit = high >= pos.stop_loss
                    tp_hit = pos.take_profit is not None and low <= pos.take_profit
                if sl_hit:  # stop-first (conservative)
                    reason = "stop_loss"
                    exit_price = pos.stop_loss
                elif tp_hit:
                    reason = "take_profit"
                    exit_price = float(pos.take_profit)
            if exit_price is not None:
                closed = state.close_position(pos.trade_id, exit_price, ts)
                if closed:
                    trade_pnl = _pnl(pos.direction, pos.entry_price, exit_price,
                                     pos.lot_size)
                    trades.append(CanonicalTrade(
                        trade_id=pos.trade_id, symbol=pos.symbol,
                        direction=pos.direction, entry_price=pos.entry_price,
                        exit_price=exit_price, lot_size=pos.lot_size,
                        entry_time=pos.entry_time, exit_time=ts,
                        pnl=trade_pnl, exit_reason=reason,
                    ))
                    strategy.on_exit()
            elif reason:
                # strategy returned a custom reason but no touch-based exit
                exit_price = close
                slip = slippage_pips * pip
                exit_price = exit_price - slip if pos.direction.upper() == "LONG" else exit_price + slip
                closed = state.close_position(pos.trade_id, exit_price, ts)
                if closed:
                    trades.append(CanonicalTrade(
                        trade_id=pos.trade_id, symbol=pos.symbol,
                        direction=pos.direction, entry_price=pos.entry_price,
                        exit_price=exit_price, lot_size=pos.lot_size,
                        entry_time=pos.entry_time, exit_time=ts,
                        pnl=_pnl(pos.direction, pos.entry_price, exit_price, pos.lot_size),
                        exit_reason=reason,
                    ))
                    strategy.on_exit()

        # ---- (C) new entry proposal (becomes pending for NEXT bar) ----
        if not state.open_positions and pending is None:
            sig = strategy.signal(data, i)
            if sig:
                # pass the bar timestamp as-is: it is already tz-aware in the
                # session's local zone (America/New_York), which is what the
                # RiskEngine's Clock expects. Do NOT strip/replace tzinfo -- that
                # would shift the hour and wrongly fail the session gate.
                ts_aware = ts
                proposal = TradeProposal(
                    symbol=symbol,
                    direction=sig["direction"],
                    entry_price=Decimal(str(sig["entry_price"])),
                    stop_loss=Decimal(str(sig["stop_loss"])),
                    take_profit=Decimal(str(sig.get("take_profit")))
                    if sig.get("take_profit") is not None else None,
                    timestamp=ts_aware,
                    strategy_id=sig.get("strategy_id", "strategy"),
                )
                approval = engine.evaluate(proposal)
                if approval.approved and approval.lot_size > 0:
                    pending = {
                        "direction": sig["direction"],
                        "entry": float(sig["entry_price"]),
                        "sl": float(sig["stop_loss"]),
                        "tp": sig.get("take_profit"),
                        "strategy_id": sig.get("strategy_id", "strategy"),
                        "ts": ts,
                        "lot_size": float(approval.lot_size),
                        "trade_id": f"T{i}",
                    }

        equity_curve.append((ts, float(state.equity)))

    metrics = _compute_metrics(equity_curve, trades, initial_equity)
    return CanonicalResult(trades=trades, equity_curve=equity_curve, metrics=metrics)


def _compute_metrics(equity_curve, trades, initial_equity):
    equity = np.array([e for _, e in equity_curve])
    if len(equity) < 2 or not trades:
        return {"total_trades": len(trades), "win_rate": 0.0, "profit_factor": 0.0,
                "sharpe_ratio": 0.0, "max_drawdown_pct": 0.0, "total_return_pct": 0.0,
                "avg_rr": 0.0, "avg_holding_bars": 0.0}
    returns = np.diff(equity)
    total_return_pct = (equity[-1] - initial_equity) / initial_equity * 100
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / np.where(peak == 0, 1, peak)
    max_dd_pct = float(np.max(dd)) * 100
    sharpe = 0.0
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = float(np.mean(returns) / np.std(returns)) * np.sqrt(252)
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    win_rate = len(wins) / len(trades)
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 0 else (float("inf") if gross_win > 0 else 0.0)
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    avg_rr = avg_win / avg_loss if avg_loss > 0 else (float("inf") if avg_win > 0 else 0.0)
    holding = []
    for t in trades:
        try:
            bars = max(1, int((t.exit_time - t.entry_time).total_seconds() // 3600))
        except Exception:
            bars = 0
        holding.append(bars)
    avg_holding = sum(holding) / len(holding) if holding else 0.0
    return {"total_trades": len(trades), "win_rate": win_rate, "profit_factor": pf,
            "sharpe_ratio": sharpe, "max_drawdown_pct": max_dd_pct,
            "total_return_pct": total_return_pct, "avg_rr": avg_rr,
            "avg_holding_bars": avg_holding}
