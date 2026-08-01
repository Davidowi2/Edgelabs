"""Strategy-aware backtest runner.

This is a NEW module (does not modify the existing run_backtest). It exists
because the documented strategies require dynamic exits that a fixed
stop/take-profit model cannot express: Turtle exit-on-breakout, trailing stops,
and session time stops.

Design:
  - Each strategy object exposes: signal(df, i) -> Optional[dict] for ENTRY,
    exit_signal(df, i) -> Optional[str] for EXIT reason, on_fill(...), on_exit().
  - Entries are routed through the RiskEngine for sizing + spread + zero-stop
    rejection (faithful to the brief's risk rules). Portfolio circuit-breaker
    locks are neutralized via a per-strategy config so the measured drawdown is
    the STRATEGY's own edge (not the governor capping it), per the brief's intent
    to "test them as specified."
  - Exits are evaluated bar-by-bar against the strategy's own state, then applied
    to the StateBus at the bar close (close-price exit) — conservative and clean.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

import pandas as pd

from edgelab.config import Config
from edgelab.risk.engine import RiskEngine, TradeProposal
from edgelab.risk.sizing import PositionSizing
from edgelab.state.bus import Position, StateBus


# Standard FX lot = 100,000 units. StateBus._calculate_pnl multiplies
# (exit-entry)*lot_size WITHOUT this multiplier, so we apply it at the runner
# level to recover correct monetary PnL (we do not modify the shared bus).
CONTRACT_MULTIPLIER = 100_000.0


@dataclass
class TradeRecord:
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
class StrategyBacktestResult:
    trades: list[TradeRecord]
    equity_curve: list[tuple[datetime, float]]
    metrics: dict


def _bar_ts(bar: pd.Series) -> datetime:
    name = getattr(bar, "name", None)
    if name is None:
        return datetime.min
    return name.to_pydatetime() if hasattr(name, "to_pydatetime") else datetime.min


def _neutral_config(base: Config, session_windows: Optional[list] = None) -> Config:
    """Copy base config but neutralize portfolio locks and set the strategy's
    own session window so RiskEngine gates only what the strategy intends."""
    cfg = copy.deepcopy(base)
    cfg._data["internal_risk"]["daily_loss_lock_pct"] = 1.0
    cfg._data["internal_risk"]["total_dd_lock_pct"] = 1.0
    cfg._data["internal_risk"]["daily_loss_lock_hours"] = 0
    cfg._data["internal_risk"]["max_open_positions"] = 1
    if session_windows is not None:
        # Strategy defines its own session window -> engine gates to it.
        cfg._data["internal_risk"]["session_filter_ny"] = session_windows
    else:
        # Strategy has NO session filter -> empty list makes Clock._in_session
        # return True for all bars (no gate). Passing None would let Clock fall
        # back to the constitution's default windows, wrongly rejecting entries.
        cfg._data["internal_risk"]["session_filter_ny"] = []
    # risk_per_trade handled per-call via a sizing override below
    return cfg

def run_strategy_backtest(
    data: pd.DataFrame,
    strategy,
    initial_equity: float = 10000.0,
    symbol: str = "EURUSD",
    base_config: Optional[Config] = None,
    session_windows: Optional[list] = None,
    risk_per_trade: float = 0.01,
    spread_pips: float = 0.8,
    slippage_pips: float = 0.5,
) -> StrategyBacktestResult:
    if base_config is None:
        base_config = Config()
    cfg = _neutral_config(base_config, session_windows)
    cfg._data["internal_risk"]["risk_per_trade_pct"] = risk_per_trade
    cfg._data["internal_risk"]["spread_pips_per_symbol"] = {symbol: spread_pips}
    state = StateBus(float(initial_equity))
    engine = RiskEngine(cfg, state)
    sizing = PositionSizing(cfg)

    trades: list[TradeRecord] = []
    first_ts = _bar_ts(data.iloc[0])
    equity_curve = [(first_ts, float(state.equity))]
    pip_size = 0.0001 if "JPY" not in symbol.upper() else 0.01

    for i in range(len(data)):
        bar = data.iloc[i]
        ts = _bar_ts(bar)
        close = float(bar["close"])

        # --- EXITS: evaluate strategy exit state against current bar ---
        if state.open_positions:
            reason = strategy.exit_signal(data, i)
            if reason:
                pos = state.open_positions[0]
                exit_price = close
                # apply slippage on exit for filled, non-time-stop exits
                if reason != "time_stop":
                    slip = slippage_pips * pip_size
                    exit_price = exit_price - slip if pos.direction.upper() == "LONG" else exit_price + slip
                closed = state.close_position(pos.trade_id, exit_price, ts)
                if closed:
                    # NOTE: StateBus._calculate_pnl omits the FX contract multiplier
                    # (standard lot = 100,000 units), so its pnl/equity are 100,000x
                    # too small. We correct equity and the recorded PnL here in this
                    # new module without modifying the shared bus (rule 4).
                    raw_pnl = closed.pnl if closed.pnl is not None else 0.0
                    true_pnl = raw_pnl * CONTRACT_MULTIPLIER
                    state.equity = (state.equity - raw_pnl) + true_pnl
                    if state.equity > state.peak_equity:
                        state.peak_equity = state.equity
                    trades.append(
                        TradeRecord(
                            trade_id=pos.trade_id,
                            symbol=pos.symbol,
                            direction=pos.direction,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            lot_size=pos.lot_size,
                            entry_time=pos.entry_time,
                            exit_time=ts,
                            pnl=true_pnl,
                            exit_reason=reason,
                        )
                    )
                    strategy.on_exit()

        # --- ENTRIES: only if flat ---
        if not state.open_positions:
            sig = strategy.signal(data, i)
            if sig:
                direction = sig["direction"]
                entry = float(sig["entry_price"])
                stop = float(sig["stop_loss"])
                # Entry spread/slippage: fill worse by (spread+slippage) pips.
                fill_adj = (spread_pips + slippage_pips) * pip_size
                fill_price = entry + fill_adj if direction == "LONG" else entry - fill_adj
                tp = sig.get("take_profit")
                # The engine's Clock.in_session() converts tz-AWARE times to NY but
                # treats NAIVE times as NY wall-clock. Our data timestamps are naive
                # UTC, so we must pass a tz-aware UTC timestamp so the session gate
                # evaluates the correct NY hour (8-11 NY == 13-16 UTC). This fixes
                # the gate in the runner without modifying the shared clock module.
                ts_aware = ts.replace(tzinfo=timezone.utc)
                proposal = TradeProposal(
                    symbol=symbol,
                    direction=direction,
                    entry_price=Decimal(str(fill_price)),
                    stop_loss=Decimal(str(stop)),
                    take_profit=Decimal(str(tp)) if tp is not None else None,
                    timestamp=ts_aware,
                    strategy_id=sig.get("strategy_id", "strategy"),
                )
                approval = engine.evaluate(proposal)
                if approval.approved and approval.lot_size > 0:
                    state.add_position(
                        Position(
                            symbol=symbol,
                            direction=direction,
                            entry_price=fill_price,
                            stop_loss=stop,
                            take_profit=float(tp) if tp is not None else None,
                            lot_size=float(approval.lot_size),
                            entry_time=ts,
                            trade_id=f"T{i}",
                        )
                    )
                    strategy.on_fill(direction, fill_price, i, data)

        equity_curve.append((ts, float(state.equity)))

    metrics = _compute_metrics(equity_curve, trades, initial_equity)
    return StrategyBacktestResult(trades=trades, equity_curve=equity_curve, metrics=metrics)


def _compute_metrics(equity_curve, trades, initial_equity):
    import numpy as np

    equity = np.array([e for _, e in equity_curve])
    if len(equity) < 2 or not trades:
        return {
            "total_trades": len(trades),
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "total_return_pct": 0.0,
            "avg_rr": 0.0,
            "avg_holding_bars": 0.0,
        }
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
    win_rate = len(wins) / len(trades) if trades else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    avg_rr = avg_win / avg_loss if avg_loss > 0 else float("inf") if avg_win > 0 else 0.0
    # holding bars from entry/exit times (1h bars)
    holding = []
    for t in trades:
        try:
            bars = max(1, int((t.exit_time - t.entry_time).total_seconds() // 3600))
        except Exception:
            bars = 0
        holding.append(bars)
    avg_holding = sum(holding) / len(holding) if holding else 0.0
    return {
        "total_trades": len(trades),
        "win_rate": win_rate,
        "profit_factor": pf,
        "sharpe_ratio": sharpe,
        "max_drawdown_pct": max_dd_pct,
        "total_return_pct": total_return_pct,
        "avg_rr": avg_rr,
        "avg_holding_bars": avg_holding,
    }
