"""Execution gateway for EdgeLab (Phase 8, Module 4).

The COMPOSITION of RetryExecutor + CircuitBreaker + submission safety +
SpreadGuard. This is the single entry point the signal pipeline (Phase 7)
calls. It hides retry/circuit/safety complexity from the signal layer. No
broker connection; all broker I/O goes through BrokerInterface. Pure standard
library only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

from edgelab.execution.spread_guard import SpreadGuard, SpreadSnapshot
from edgelab.execution.retry_executor import (
    RetryExecutor, RetryConfig, RetryOutcome, MockTradeResult, exponential_backoff_delay,
)
from edgelab.execution.circuit_breaker import (
    CircuitBreaker, CircuitConfig, CircuitState,
)


class GatewayResult(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED_TRANSIENT = "FAILED_TRANSIENT"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    DUPLICATE_BLOCKED = "DUPLICATE_BLOCKED"
    SPREAD_BLOCKED = "SPREAD_BLOCKED"


class BrokerInterface(ABC):
    @abstractmethod
    def submit(self, request: dict) -> MockTradeResult:
        ...

    @abstractmethod
    def get_open_positions(self) -> List[dict]:
        ...

    @abstractmethod
    def get_pending_market_orders(self) -> List[dict]:
        ...

    @abstractmethod
    def get_current_spread(self) -> float:
        ...

    @abstractmethod
    def get_symbol(self) -> str:
        ...


# Re-export for convenience (tests import MockBroker from gateway).
from edgelab.execution.retry_executor import MockTradeResult  # noqa: E402,F401
from edgelab.execution.mock_broker import MockBroker  # noqa: E402,F401


class ExecutionGateway:
    def __init__(self, config: dict, broker: BrokerInterface, logger,
                 retry_exec: Optional[RetryExecutor] = None,
                 circuit_br: Optional[CircuitBreaker] = None,
                 spread_guard: Optional[SpreadGuard] = None) -> None:
        cfg = config or {}
        self._logger = logger
        self._broker = broker
        self.max_position_count = int(cfg.get("max_position_count", 1))
        self.magic_number = int(cfg.get("magic_number", 0))

        self._spread_guard = spread_guard or SpreadGuard(cfg, logger)
        self._circuit = circuit_br or CircuitBreaker(CircuitConfig(), logger)
        self._retry = retry_exec or RetryExecutor(RetryConfig(), logger)

    # ---------- main entry ----------
    def submit_order(self, request: dict) -> GatewayResult:
        symbol = request.get("symbol", self._broker.get_symbol())

        # Step 1: spread guard (cheap filter first)
        spread = self._broker.get_current_spread()
        snap = self._spread_guard.check_spread(spread, self._now())
        if self._spread_guard.is_blocked(snap):
            self._logger.warning("gateway: spread blocked", symbol=symbol, verdict=snap.verdict.value)
            return GatewayResult.SPREAD_BLOCKED

        # Step 2: submission safety (no duplicate positions)
        if not self.is_submission_safe(symbol):
            self._logger.warning("gateway: duplicate blocked", symbol=symbol)
            return GatewayResult.DUPLICATE_BLOCKED

        # Step 3: circuit breaker
        if not self._circuit.allow_request():
            self._logger.warning("gateway: circuit open", symbol=symbol)
            return GatewayResult.CIRCUIT_OPEN

        # Step 4: retry-wrapped broker call
        result = self._retry.execute(lambda: self._broker.submit(request))

        # Step 5: map outcome
        outcome = result.outcome
        if outcome == RetryOutcome.SUCCESS:
            self._circuit.record_success()
            return GatewayResult.SUCCESS
        if outcome == RetryOutcome.PARTIAL:
            # partial fills still count as a success toward the circuit
            self._circuit.record_success()
            return GatewayResult.PARTIAL
        if outcome == RetryOutcome.FAILED_PERMANENT:
            # EA logic error -> does NOT count toward broker degradation
            return GatewayResult.FAILED_PERMANENT
        # FAILED_TRANSIENT -> broker degradation -> count it
        self._circuit.record_failure()
        return GatewayResult.FAILED_TRANSIENT

    # ---------- submission safety ----------
    def is_submission_safe(self, symbol: str) -> bool:
        # open positions matching symbol + magic
        for pos in self._broker.get_open_positions():
            if pos.get("symbol") == symbol and int(pos.get("magic", -1)) == self.magic_number:
                return False
        # pending market orders matching symbol + magic with no position id
        for ord_ in self._broker.get_pending_market_orders():
            if ord_.get("symbol") == symbol and int(ord_.get("magic", -1)) == self.magic_number:
                # a pending market order with position_id == 0 (unfilled) is a
                # duplicate in-flight order; a set position_id means it is a
                # pending SL/TP modification, which is safe to ignore
                if int(ord_.get("position_id", 0)) == 0:
                    return False
        return True

    # ---------- passthroughs ----------
    def get_spread_snapshot(self) -> SpreadSnapshot:
        return self._spread_guard.check_spread(self._broker.get_current_spread(), self._now())

    def get_circuit_state(self) -> CircuitState:
        return self._circuit.get_state()

    def reset_circuit(self) -> None:
        self._circuit.reset()

    def _now(self):
        from datetime import datetime, timezone
        return datetime.now(timezone.utc)
