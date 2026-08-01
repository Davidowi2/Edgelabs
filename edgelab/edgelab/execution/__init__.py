"""EdgeLab execution quality package (Phase 8).

Composition of the four production-layer modules:

  * SpreadGuard       -> spread shock / baseline-relative guard
  * RetryExecutor     -> transient vs permanent error classification + backoff
  * CircuitBreaker    -> CLOSED/OPEN/HALF_OPEN failure-state machine
  * ExecutionGateway  -> the single entry point composing all of the above
  * MockBroker        -> injectable broker for tests (no real connection)
"""

from edgelab.execution.spread_guard import (
    SpreadGuard, SpreadSnapshot, SpreadVerdict,
)
from edgelab.execution.retry_executor import (
    RetryExecutor, RetryConfig, RetryOutcome, MockTradeResult,
    exponential_backoff_delay,
)
from edgelab.execution.circuit_breaker import (
    CircuitBreaker, CircuitConfig, CircuitState,
)
from edgelab.execution.gateway import (
    ExecutionGateway, GatewayResult, BrokerInterface,
)
from edgelab.execution.mock_broker import MockBroker
from edgelab.execution.symbol_resolver import (
    SymbolResolver, SymbolNotFoundError,
)
from edgelab.execution.tradelocker_broker import (
    TradeLockerBroker, MT5NotAvailableError,
)
from edgelab.execution.broker_factory import BrokerFactory

__all__ = [
    "SpreadGuard", "SpreadSnapshot", "SpreadVerdict",
    "RetryExecutor", "RetryConfig", "RetryOutcome", "MockTradeResult",
    "exponential_backoff_delay",
    "CircuitBreaker", "CircuitConfig", "CircuitState",
    "ExecutionGateway", "GatewayResult", "BrokerInterface", "MockBroker",
    "SymbolResolver", "SymbolNotFoundError",
    "TradeLockerBroker", "MT5NotAvailableError",
    "BrokerFactory",
]
