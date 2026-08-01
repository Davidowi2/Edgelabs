"""Unit tests for the Session Volatility Expansion strategy."""

from __future__ import annotations

import pandas as pd
import pytest

from edgelab.strategy.session_expansion import SessionExpansionStrategy, NY, LONDON


def _make_session_df() -> pd.DataFrame:
    # 200 hours spanning several London + NY sessions, with a clear intraday range.
    idx = pd.date_range("2022-01-03 00:00", periods=400, freq="h")  # Mon Jan 3 2022
    base = 1.1000
    prices = [base + 0.00005 * i for i in range(400)]
    df = pd.DataFrame(
        {
            "open": prices,
            "high": [p + 0.0002 for p in prices],
            "low": [p - 0.0002 for p in prices],
            "close": prices,
            "volume": [0] * 400,
        },
        index=idx,
    )
    return df


class TestSessionExpansion:
    def test_initializes(self):
        s = SessionExpansionStrategy()
        assert s.in_position is False

    def test_no_signal_outside_session(self):
        s = SessionExpansionStrategy()
        df = _make_session_df()
        # find a bar clearly outside both windows
        for i in range(len(df)):
            from edgelab.strategy.indicators import in_window

            if not in_window(df.index[i], LONDON) and not in_window(df.index[i], NY):
                assert s.signal(df, i) is None
                break

    def test_only_one_trade_per_session(self):
        s = SessionExpansionStrategy()
        df = _make_session_df()
        # force a long breakout at first NY session bar
        entered = False
        for i in range(len(df)):
            from edgelab.strategy.indicators import in_window

            if in_window(df.index[i], NY):
                df.loc[df.index[i], "close"] = df["close"].iloc[i] + 0.0050
                df.loc[df.index[i], "high"] = df["close"].iloc[i] + 0.0002
                sig = s.signal(df, i)
                if sig is not None:
                    s.on_fill(sig["direction"], sig["entry_price"], i, df)
                    entered = True
                    # subsequent NY bars same session must yield None
                    assert s.signal(df, min(i + 1, len(df) - 1)) is None
                    break
        assert entered is True

    def test_valid_long_signal_on_range_breakout(self):
        s = SessionExpansionStrategy()
        df = _make_session_df()
        for i in range(len(df)):
            from edgelab.strategy.indicators import in_window

            if in_window(df.index[i], NY):
                df.loc[df.index[i], "close"] = df["close"].iloc[i] + 0.0100
                df.loc[df.index[i], "high"] = df["close"].iloc[i] + 0.0002
                sig = s.signal(df, i)
                if sig is not None:
                    assert sig["direction"] == "LONG"
                    assert sig["take_profit"] is not None
                    assert sig["stop_loss"] < sig["entry_price"]
                    assert sig["strategy_id"] == "session_expansion"
                    break
        else:
            pytest.fail("expected a LONG breakout signal in an NY session")

    def test_time_stop_after_6_bars(self):
        s = SessionExpansionStrategy()
        df = _make_session_df()
        for i in range(len(df)):
            from edgelab.strategy.indicators import in_window

            if in_window(df.index[i], NY):
                df.loc[df.index[i], "close"] = df["close"].iloc[i] + 0.0100
                sig = s.signal(df, i)
                if sig is not None:
                    s.on_fill(sig["direction"], sig["entry_price"], i, df)
                    reason = s.exit_signal(df, i + 7)
                    assert reason == "time_stop"
                    break
        else:
            pytest.fail("no entry to test time stop")

    def test_take_profit_exit(self):
        s = SessionExpansionStrategy()
        df = _make_session_df()
        for i in range(len(df)):
            from edgelab.strategy.indicators import in_window

            if in_window(df.index[i], NY):
                df.loc[df.index[i], "close"] = df["close"].iloc[i] + 0.0100
                sig = s.signal(df, i)
                if sig is not None:
                    s.on_fill(sig["direction"], sig["entry_price"], i, df)
                    tp = sig["take_profit"]
                    # push close to TP
                    df.loc[df.index[i + 1], "close"] = tp
                    df.loc[df.index[i + 1], "high"] = tp + 0.0001
                    reason = s.exit_signal(df, i + 1)
                    assert reason == "take_profit"
                    break
        else:
            pytest.fail("no entry to test TP")
