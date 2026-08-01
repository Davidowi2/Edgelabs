"""Shared technical-indicator helpers for EdgeLab strategies.

Pure pandas/numpy implementations so strategies stay dependency-light and
fully reproducible. Timezone handling uses zoneinfo (std lib, py3.9+).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pandas as pd

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - fallback for old interpreters
    ZoneInfo = None  # type: ignore


NY_TZ = "America/New_York"


def atr(df: pd.DataFrame, period: int = 20, ema: bool = True) -> pd.Series:
    """Average True Range.

    ema=True -> Wilder-style EMA smoothing (matches 'exponential moving average'
    ATR wording in the turtle spec). ema=False -> simple SMA.
    """
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    tr = tr.fillna(high - low)  # first row
    if ema:
        return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    return tr.rolling(period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.astype(float).ewm(span=period, adjust=False).mean()


def rolling_high(df: pd.DataFrame, period: int) -> pd.Series:
    return df["high"].astype(float).rolling(period, min_periods=period).max()


def rolling_low(df: pd.DataFrame, period: int) -> pd.Series:
    return df["low"].astype(float).rolling(period, min_periods=period).min()


def to_ny(dt: datetime) -> datetime:
    """Convert a (possibly naive) UTC timestamp to America/New_York local time.

    Source data is naive UTC. We treat naive input as UTC, then localize to NY
    (DST-aware). Returns an aware datetime in NY.
    """
    if ZoneInfo is None:
        return dt
    tz_ny = ZoneInfo(NY_TZ)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz_ny)


def ny_minutes(dt: datetime) -> int:
    local = to_ny(dt)
    return local.hour * 60 + local.minute


def in_window(dt: datetime, window: tuple[int, int, int, int]) -> bool:
    """window = (start_h, start_m, end_h, end_m) in NY time."""
    cur = ny_minutes(dt)
    start = window[0] * 60 + window[1]
    end = window[2] * 60 + window[3]
    return start <= cur <= end


def session_bars(df: pd.DataFrame, window: tuple[int, int, int, int]) -> pd.Series:
    """Boolean mask over df.index: True for bars inside the NY session window."""
    return pd.Series([in_window(ts, window) for ts in df.index], index=df.index)
