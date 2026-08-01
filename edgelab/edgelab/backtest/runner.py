"""Backtest runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

import pandas as pd

from edgelab.backtest.metrics import calculate_metrics, summarize_trades
from edgelab.config import Config
from edgelab.risk.engine import RiskEngine, TradeProposal
from edgelab.state.bus import Position, StateBus


@dataclass
class TradeRecord:
    trade_id: str
    symbol: str
    direction: str
    entry_price: Decimal
    exit_price: Decimal
    lot_size: Decimal
    entry_time: datetime
    exit_time: datetime
    pnl: Decimal
    status: str
    exit_reason: str


@dataclass
class BacktestResult:
    trades: list[TradeRecord]
    equity_curve: list[tuple[datetime, Decimal]]
    metrics: dict


def _bar_timestamp(bar: pd.Series) -> datetime:
    name = getattr(bar, "name", None)
    if name is None:
        return datetime.min
    return name.to_pydatetime() if hasattr(name, "to_pydatetime") else datetime.min


def run_backtest(
    data: pd.DataFrame,
    strategy: Callable[[pd.DataFrame, int, StateBus], Optional[dict]],
    risk_engine: RiskEngine,
    initial_equity: Decimal,
    symbol: str,
) -> BacktestResult:
    state = StateBus(float(initial_equity))
    trades: list[TradeRecord] = []
    first_ts = _bar_timestamp(data.iloc[0])
    equity_curve = [(first_ts, initial_equity)]

    for i in range(len(data)):
        bar = data.iloc[i]
        timestamp = _bar_timestamp(bar)
        for position in list(state.open_positions):
            if position.direction.upper() == "LONG":
                stop_hit = bar.low <= position.stop_loss
                tp_hit = position.take_profit is not None and bar.high >= position.take_profit
            else:
                stop_hit = bar.high >= position.stop_loss
                tp_hit = position.take_profit is not None and bar.low <= position.take_profit

            if stop_hit or tp_hit:
                exit_price = position.stop_loss if stop_hit else float(position.take_profit)
                closed = state.close_position(position.trade_id, exit_price, timestamp)
                if closed:
                    trades.append(
                        TradeRecord(
                            trade_id=position.trade_id,
                            symbol=position.symbol,
                            direction=position.direction,
                            entry_price=Decimal(str(position.entry_price)),
                            exit_price=Decimal(str(closed.exit_price)),
                            lot_size=Decimal(str(position.lot_size)),
                            entry_time=position.entry_time,
                            exit_time=timestamp,
                            pnl=Decimal(str(closed.pnl)) if closed.pnl is not None else Decimal("0"),
                            status="closed",
                            exit_reason="stop_loss" if stop_hit else "take_profit",
                        )
                    )

        proposal_data = strategy(data, i, state)
        if proposal_data:
            proposal = TradeProposal(
                symbol=symbol,
                direction=proposal_data["direction"],
                entry_price=Decimal(str(proposal_data["entry_price"])),
                stop_loss=Decimal(str(proposal_data["stop_loss"])),
                take_profit=Decimal(str(proposal_data["take_profit"])) if proposal_data.get("take_profit") is not None else None,
                timestamp=timestamp,
                strategy_id=proposal_data.get("strategy_id", "unknown"),
            )
            approval = risk_engine.evaluate(proposal)
            if approval.approved:
                state.add_position(
                    Position(
                        symbol=symbol,
                        direction=proposal.direction,
                        entry_price=float(proposal.entry_price),
                        stop_loss=float(proposal.stop_loss),
                        take_profit=float(proposal.take_profit) if proposal.take_profit is not None else None,
                        lot_size=float(approval.lot_size),
                        entry_time=timestamp,
                        trade_id=f"T{i}",
                    )
                )
        equity_curve.append((timestamp, Decimal(str(state.equity))))

    metrics = calculate_metrics(equity_curve, trades)
    return BacktestResult(trades=trades, equity_curve=equity_curve, metrics=metrics)
