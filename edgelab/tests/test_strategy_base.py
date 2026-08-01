"""Tests for the strategy base interface."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytest

from edgelab.state.bus import StateBus
from edgelab.strategy.base import BaseStrategy


class TestStrategyBase:
    def test_cannot_instantiate_abstract_directly(self):
        with pytest.raises(TypeError):
            BaseStrategy(StateBus(10000.0), {})

    def test_subclass_can_implement_evaluate(self):
        class MyStrategy(BaseStrategy):
            def evaluate(self, symbol: str, now: datetime) -> Optional[dict]:
                return {"direction": "LONG", "entry_price": 1.1,
                        "stop_loss": 1.09, "take_profit": 1.12, "strategy_id": "me"}

        s = MyStrategy(StateBus(10000.0), {})
        assert s.state is not None
        result = s.evaluate("EURUSD", datetime(2026, 7, 20, 10))
        assert result["direction"] == "LONG"

    def test_subclass_without_override_cannot_instantiate(self):
        class IncompleteStrategy(BaseStrategy):
            pass

        with pytest.raises(TypeError):
            IncompleteStrategy(StateBus(10000.0), {})
