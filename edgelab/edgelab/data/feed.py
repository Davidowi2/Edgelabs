"""EdgeLab data feed."""

from __future__ import annotations

from typing import Iterator, NamedTuple

import pandas as pd


class Bar(NamedTuple):
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float


def stream(data: pd.DataFrame) -> pd.DataFrame:
    return data.copy()


def iter_bars(data: pd.DataFrame) -> Iterator[Bar]:
    """Yield each row of an OHLCV DataFrame as a Bar (datetime-indexed).

    Does not depend on any external class.
    """
    for timestamp, row in data.iterrows():
        yield Bar(
            timestamp=timestamp,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
