"""Circuit breakers (daily loss + total drawdown locks)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from edgelab.config import Config
from edgelab.state.bus import StateBus


class CircuitBreakers:
    def __init__(self, config: Config, state: StateBus) -> None:
        self.config = config
        self.state = state
        self.circuit_breaker_active_status: dict[str, bool] = {}

    def daily_loss_lock_active(self, now: datetime) -> bool:
        return self.state.daily_pnl <= 0 and abs(self.state.daily_pnl) >= float(self.config.internal_risk.get("daily_loss_lock_pct", 0.02)) * float(self.state.daily_start_equity)

    def total_dd_lock_active(self) -> bool:
        max_dd_lock_pct = self.config.internal_risk.get("total_dd_lock_pct", 0.05)
        peak_equity = Decimal(str(self.state.peak_equity))
        if peak_equity == 0:
            return False
        return (peak_equity - Decimal(str(self.state.equity))) / peak_equity >= Decimal(str(max_dd_lock_pct))

    def circuit_breaker_active(self, key: str) -> bool:
        return bool(self.circuit_breaker_active_status.get(key))
