"""Strategy base interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from edgelab.state.bus import StateBus


class BaseStrategy(ABC):
    def __init__(self, state: StateBus, config: dict) -> None:
        self.state = state
        self.config = config

    @abstractmethod
    def evaluate(self, symbol: str, now: datetime) -> Optional[dict]:
        ...
