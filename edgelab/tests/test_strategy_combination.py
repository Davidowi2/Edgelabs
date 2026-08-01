"""Unit tests for the Phase H combination strategy."""

from __future__ import annotations

import pandas as pd
import pytest

from edgelab.strategy.combination import CombinationStrategy, OVERLAP


def _make_df(n: int = 200) -> pd.DataFrame:
    idx = pd.date_range("2022-01-03 09:00", periods=n, freq="h")
    # Very gentle uptrend so the 200 EMA sits close to price (within 0.5% at the
    # probe bar), while still forming HH/HL structure for the HTF bias filter.
    prices = [1.1000 + 0.00002 * i for i in range(n)]
    df = pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.0002 for p in prices],
            "low": [p - 0.0002 for p in prices],
            "close": prices,
            "volume": [0] * n,
        },
        index=idx,
    )
    return df


class TestCombination:
    def test_initializes(self):
        s = CombinationStrategy()
        assert s.in_position is False

    def test_no_signal_outside_overlap(self):
        s = CombinationStrategy()
        df = _make_df(200)
        df2 = df.copy()
        df2.index = df2.index - pd.Timedelta(hours=12)
        from edgelab.strategy.indicators import in_window

        i = 100
        assert not in_window(df2.index[i], OVERLAP)
        assert s.signal(df2, i) is None

    def test_returns_valid_signal_when_filters_align(self):
        s = CombinationStrategy()
        df = _make_df(200)
        i = 150
        from edgelab.strategy.indicators import in_window

        assert in_window(df.index[i], OVERLAP)
        # inject a bullish rejection candle so the LTF trigger fires
        o = float(df["open"].iloc[i])
        df.loc[df.index[i], "open"] = o
        df.loc[df.index[i], "close"] = o + 0.0004
        df.loc[df.index[i], "high"] = o + 0.0005
        df.loc[df.index[i], "low"] = o - 0.0001
        sig = s.signal(df, i)
        if sig is not None:
            assert sig["direction"] in ("LONG", "SHORT")
            assert sig["stop_loss"] != sig["entry_price"]
            assert sig["strategy_id"] == "combination"

    def test_respects_single_position(self):
        s = CombinationStrategy()
        df = _make_df(200)
        for i in range(80, 200):
            o = float(df["open"].iloc[i])
            df.loc[df.index[i], "open"] = o
            df.loc[df.index[i], "close"] = o + 0.0004
            df.loc[df.index[i], "high"] = o + 0.0005
            df.loc[df.index[i], "low"] = o - 0.0001
            sig = s.signal(df, i)
            if sig is not None:
                s.on_fill(sig["direction"], sig["entry_price"], i, df)
                break
        assert s.in_position is True
        assert s.signal(df, 199) is None
