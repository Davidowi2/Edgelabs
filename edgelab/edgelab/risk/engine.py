"""Risk engine module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from edgelab.config import Config
from edgelab.risk.circuit_breakers import CircuitBreakers
from edgelab.risk.sizing import PositionSizing
from edgelab.state.bus import StateBus
from edgelab.state.clock import Clock


@dataclass
class TradeProposal:
    symbol: str
    direction: str
    entry_price: Decimal
    stop_loss: Decimal
    take_profit: Optional[Decimal]
    timestamp: datetime
    strategy_id: str


@dataclass
class Approval:
    approved: bool
    lot_size: Decimal
    risk_amount: Decimal
    risk_pips: float
    reason: str


class RiskEngine:
    def __init__(self, config: Config, state: StateBus) -> None:
        self.config = config
        self.state = state
        self.circuit_breakers = CircuitBreakers(config, state)
        self.sizing = PositionSizing(config)
        self.correlation_groups = config.internal_risk.get("correlation_groups", {})
        self.session_windows = config.internal_risk.get("session_filter_ny", [])
        # Pass the list through unchanged: None -> default NY windows,
        # [] -> no gate (Clock treats empty list as always in session).
        self.clock = Clock(self.session_windows)

    def evaluate(self, proposal: TradeProposal) -> Approval:
        self.state.reset_daily(proposal.timestamp)
        if self.circuit_breakers.circuit_breaker_active(proposal.strategy_id):
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Circuit breaker active")
        if self.circuit_breakers.daily_loss_lock_active(proposal.timestamp):
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Daily loss lock active")
        if self.circuit_breakers.total_dd_lock_active():
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Total drawdown lock active")
        if not self._in_session(proposal.timestamp):
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Outside session window")
        if len(self.state.open_positions) >= int(self.config.internal_risk.get("max_open_positions", 2)):
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Max positions reached")
        if self._has_correlated_position(proposal.symbol):
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Correlated position open")
        if self._would_breach_daily_loss(proposal):
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Would breach daily loss limit")
        if self._would_breach_total_dd(proposal):
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Would breach total drawdown")

        raw_stop_distance = float(abs(proposal.entry_price - proposal.stop_loss))
        if raw_stop_distance <= 0:
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Stop loss distance is zero")

        spread_pips = Decimal(str(self.config.internal_risk.get("spread_pips_per_symbol", {}).get(proposal.symbol.upper(), 0)))
        lot_size, risk_amount, risk_pips = self.sizing.calculate(
            Decimal(str(self.state.equity)),
            proposal.entry_price,
            proposal.stop_loss,
            proposal.symbol,
            spread_pips=spread_pips if spread_pips > 0 else None,
        )
        if lot_size <= 0:
            return Approval(False, Decimal("0"), Decimal("0"), 0.0, "Invalid lot size")

        return Approval(True, lot_size, risk_amount, risk_pips, "Approved")

    def _in_session(self, dt: datetime) -> bool:
        return self.clock.in_session(dt)

    def _has_correlated_position(self, symbol: str) -> bool:
        symbol = symbol.upper()
        for group in self.correlation_groups.values():
            if symbol in group:
                for position in self.state.open_positions:
                    if position.symbol.upper() in group:
                        return True
                break
        return False

    def _would_breach_daily_loss(self, proposal: TradeProposal) -> bool:
        max_loss_for_trade = Decimal(str(self.state.equity)) * Decimal(str(self.config.internal_risk.get("risk_per_trade_pct", 0.01)))
        projected = abs(Decimal(str(self.state.daily_pnl))) + max_loss_for_trade
        limit = Decimal(str(self.state.daily_start_equity)) * Decimal(str(self.config.internal_risk.get("daily_loss_lock_pct", 0.02)))
        return projected >= limit

    def _would_breach_total_dd(self, proposal: TradeProposal) -> bool:
        max_loss_for_trade = Decimal(str(self.state.equity)) * Decimal(str(self.config.internal_risk.get("risk_per_trade_pct", 0.01)))
        peak = Decimal(str(self.state.peak_equity))
        if peak == 0:
            return False
        projected_dd = (peak - (Decimal(str(self.state.equity)) - max_loss_for_trade)) / peak
        return projected_dd >= Decimal(str(self.config.internal_risk.get("total_dd_lock_pct", 0.05)))
