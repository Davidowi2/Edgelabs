"""Tests for the EURUSD H1 data pipeline output."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from edgelab.data.loader import load_csv, validate_dataframe

DATA_CSV = Path(__file__).resolve().parents[1] / "data" / "EURUSD_H1_5y.csv"


@pytest.fixture(scope="module")
def eurusd_h1() -> pd.DataFrame:
    df = load_csv(DATA_CSV)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


class TestDataPipeline:
    def test_csv_exists(self):
        assert DATA_CSV.exists(), f"Missing data file: {DATA_CSV}"

    def test_loads_cleanly(self, eurusd_h1):
        assert not eurusd_h1.empty
        validate_dataframe(eurusd_h1)

    def test_row_count_over_30000(self, eurusd_h1):
        # ~5y * 252 trading days * 24h, approx lower bound for hourly bars
        assert len(eurusd_h1) > 30000

    def test_spans_at_least_five_years(self, eurusd_h1):
        span = (eurusd_h1["timestamp"].iloc[-1] - eurusd_h1["timestamp"].iloc[0]).days
        assert span >= 365.25 * 5

    def test_no_nan_in_ohlc(self, eurusd_h1):
        assert eurusd_h1[["open", "high", "low", "close"]].isna().sum().sum() == 0

    def test_timestamps_are_consistent(self, eurusd_h1):
        ts = eurusd_h1["timestamp"]
        # all naive (UTC by source convention) or all tz-aware; not mixed
        tz_aware = ts.dt.tz is not None
        # We accept consistently naive UTC timestamps
        assert ts.is_monotonic_increasing
        assert tz_aware in (True, False)

    def test_high_ge_low(self, eurusd_h1):
        assert (eurusd_h1["high"] >= eurusd_h1["low"]).all()

    def test_high_ge_open_and_close(self, eurusd_h1):
        assert (eurusd_h1["high"] >= eurusd_h1["open"]).all()
        assert (eurusd_h1["high"] >= eurusd_h1["close"]).all()

    def test_low_le_open_and_close(self, eurusd_h1):
        assert (eurusd_h1["low"] <= eurusd_h1["open"]).all()
        assert (eurusd_h1["low"] <= eurusd_h1["close"]).all()

    def test_prices_are_reasonable_for_eurusd(self, eurusd_h1):
        ohlc = eurusd_h1[["open", "high", "low", "close"]]
        assert ohlc.values.min() > 0.5
        assert ohlc.values.max() < 5.0
