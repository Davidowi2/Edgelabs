"""Tests for the data feed (bar streaming)."""

from __future__ import annotations

import pandas as pd
import pytest

from edgelab.data.feed import Bar, iter_bars, stream


class TestStream:
    def test_stream_returns_copy(self, ohlcv_df):
        out = stream(ohlcv_df)
        assert out.equals(ohlcv_df)
        assert out is not ohlcv_df


class TestIterBars:
    def test_yields_all_rows(self, ohlcv_df):
        bars = list(iter_bars(ohlcv_df))
        assert len(bars) == len(ohlcv_df)

    def test_yields_bar_namedtuples(self, ohlcv_df):
        bars = list(iter_bars(ohlcv_df))
        assert isinstance(bars[0], Bar)
        assert bars[0].open == 1.100
        assert bars[0].high == 1.101
        assert bars[0].low == 1.099
        assert bars[0].close == 1.100
        assert bars[0].volume == 100

    def test_bar_timestamp_matches_index(self, ohlcv_df):
        bars = list(iter_bars(ohlcv_df))
        assert bars[0].timestamp == ohlcv_df.index[0]

    def test_empty_dataframe_yields_nothing(self):
        empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        assert list(iter_bars(empty)) == []

    def test_order_preserved(self, ohlcv_df):
        bars = list(iter_bars(ohlcv_df))
        closes = [b.close for b in bars]
        assert closes == ohlcv_df["close"].tolist()
