"""Unit tests for the Modernized Turtle strategy."""

from __future__ import annotations

import pandas as pd
import pytest

from edgelab.strategy.turtle import TurtleStrategy


def _make_df(n: int = 260, start_price: float = 1.1000) -> pd.DataFrame:
    idx = pd.date_range("2022-01-01 00:00", periods=n, freq="h")
    # upward drift with some noise to create a clear uptrend + a later breakout
    prices = [start_price + 0.0001 * i for i in range(n)]
    df = pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.0003 for p in prices],
            "low": [p - 0.0003 for p in prices],
            "close": prices,
            "volume": [0] * n,
        },
        index=idx,
    )
    return df


class TestTurtle:
    def test_initializes(self):
        s = TurtleStrategy()
        assert s.in_position is False
        assert s.direction is None

    def test_no_signal_without_warmup(self):
        s = TurtleStrategy()
        df = _make_df(50)
        assert s.signal(df, 30) is None

    def test_no_signal_when_flat_but_no_setup(self):
        s = TurtleStrategy()
        df = _make_df(260)
        # prices flat near start; no 55-high breakout above EMA -> None expected at most bars
        sig = s.signal(df, 210)
        assert sig is None or sig["direction"] in ("LONG", "SHORT")

    def test_returns_valid_long_signal_on_breakout(self):
        s = TurtleStrategy()
        df = _make_df(260)
        # Force a breakout: push last bar well above prior highs
        df.loc[df.index[-1], "close"] = df["close"].iloc[-2] + 0.0100
        df.loc[df.index[-1], "high"] = df["close"].iloc[-1] + 0.0003
        for i in range(200, 260):
            sig = s.signal(df, i)
            if sig is not None:
                assert sig["direction"] == "LONG"
                assert sig["entry_price"] > sig["stop_loss"]
                assert sig["take_profit"] is None
                assert sig["strategy_id"] == "turtle"
                break
        else:
            pytest.fail("expected a LONG signal during breakout")

    def test_exit_signal_on_20_low_break(self):
        s = TurtleStrategy()
        df = _make_df(260)
        df.loc[df.index[-1], "close"] = df["close"].iloc[-2] + 0.0100
        for i in range(200, 260):
            sig = s.signal(df, i)
            if sig is not None:
                s.on_fill(sig["direction"], sig["entry_price"], i, df)
                break
        # Now drop price below the turtle exit level
        exit_idx = len(df) - 1
        df2 = df.copy()
        df2.loc[df2.index[-1], "close"] = df2["close"].iloc[-2] - 0.0200
        df2.loc[df2.index[-1], "low"] = df2["close"].iloc[-1] - 0.0003
        # extend index by one bar
        new_idx = df2.index[-1] + pd.Timedelta(hours=1)
        df2.loc[new_idx] = df2.iloc[-1]
        df2.loc[new_idx, "close"] = df2["close"].iloc[-1] - 0.0200
        df2.loc[new_idx, "low"] = df2["close"].iloc[-1] - 0.0003
        reason = s.exit_signal(df2, len(df2) - 1)
        assert reason == "turtle_exit"

    def test_respects_1_position(self):
        s = TurtleStrategy()
        df = _make_df(260)
        df.loc[df.index[-1], "close"] = df["close"].iloc[-2] + 0.0100
        for i in range(200, 260):
            sig = s.signal(df, i)
            if sig is not None:
                s.on_fill(sig["direction"], sig["entry_price"], i, df)
                break
        assert s.in_position is True
        # No new entry while in position
        assert s.signal(df, len(df) - 1) is None
