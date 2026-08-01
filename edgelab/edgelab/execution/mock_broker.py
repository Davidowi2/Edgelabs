"""Shared MockBroker for EdgeLab execution tests (Phase 8).

Implements BrokerInterface with injectable behaviors so the gateway can be
tested without any real broker. Pure standard library only.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from edgelab.execution.gateway import BrokerInterface, MockTradeResult


class MockBroker(BrokerInterface):
    def __init__(self, submit_fn: Optional[Callable[[dict], MockTradeResult]] = None,
                 get_positions_fn: Optional[Callable[[], List[dict]]] = None,
                 get_pending_fn: Optional[Callable[[], List[dict]]] = None,
                 get_spread_fn: Optional[Callable[[], float]] = None,
                 symbol: str = "XAUUSD") -> None:
        self._submit_fn = submit_fn or (lambda r: MockTradeResult(0, True, 0.1))
        self._positions_fn = get_positions_fn or (lambda: [])
        self._pending_fn = get_pending_fn or (lambda: [])
        self._spread_fn = get_spread_fn or (lambda: 10.0)
        self._symbol = symbol
        self.submit_calls = 0

    def submit(self, request: dict) -> MockTradeResult:
        self.submit_calls += 1
        return self._submit_fn(request)

    def get_open_positions(self) -> List[dict]:
        return self._positions_fn()

    def get_pending_market_orders(self) -> List[dict]:
        return self._pending_fn()

    def get_current_spread(self) -> float:
        return self._spread_fn()

    def get_symbol(self) -> str:
        return self._symbol
