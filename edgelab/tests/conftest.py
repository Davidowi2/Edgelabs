"""Shared pytest fixtures for the EdgeLab test suite."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from edgelab.config import Config
from edgelab.risk.engine import TradeProposal
from edgelab.state.bus import Position, StateBus


@pytest.fixture
def config() -> Config:
    return Config()


@pytest.fixture
def state() -> StateBus:
    return StateBus(10000.0)


@pytest.fixture
def ny_session_time() -> datetime:
    # 2026-07-25 is a Saturday; use an explicit NY-session wall-clock time.
    # Hour 10:00 falls inside the first NY window [8:00, 11:00].
    return datetime(2026, 7, 20, 10, 0)


@pytest.fixture
def outside_session_time() -> datetime:
    # Hour 03:00 is outside both NY windows.
    return datetime(2026, 7, 20, 3, 0)


@pytest.fixture
def sample_proposal(ny_session_time) -> TradeProposal:
    return TradeProposal(
        symbol="EURUSD",
        direction="LONG",
        entry_price=Decimal("1.1000"),
        stop_loss=Decimal("1.0950"),
        take_profit=Decimal("1.1100"),
        timestamp=ny_session_time,
        strategy_id="s1",
    )


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    idx = pd.date_range("2026-01-01 10:00", periods=6, freq="h")
    return pd.DataFrame(
        {
            "open": [1.100, 1.101, 1.102, 1.103, 1.000, 1.120],
            "high": [1.101, 1.102, 1.103, 1.104, 1.115, 1.125],
            "low": [1.099, 1.100, 1.101, 1.102, 0.950, 1.118],
            "close": [1.100, 1.101, 1.102, 1.103, 1.120, 1.124],
            "volume": [100, 100, 100, 100, 100, 100],
        },
        index=idx,
    )


@pytest.fixture
def sample_position() -> Position:
    return Position(
        symbol="EURUSD",
        direction="LONG",
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        lot_size=0.10,
        entry_time=datetime(2026, 7, 20, 10, 0),
        trade_id="T1",
    )
