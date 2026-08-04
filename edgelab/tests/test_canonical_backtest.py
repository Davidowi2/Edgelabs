"""Tests for the canonical backtester + Monte Carlo (Phase 0 fixes)."""

from __future__ import annotations

import pandas as pd
import pytest

from edgelab.backtest.canonical import run_canonical_backtest, _pnl
from edgelab.backtest.monte_carlo import run_monte_carlo


# ---- strategy helpers ----
class OneShotStrategy:
    """Enters LONG on bar `on_bar` with given sl/tp; exits via tp/sl only."""
    def __init__(self, on_bar, entry, sl, tp):
        self.on_bar = on_bar; self.entry = entry; self.sl = sl; self.tp = tp
        self.in_pos = False
    def signal(self, df, i):
        if i == self.on_bar and not self.in_pos:
            return {"direction": "LONG", "entry_price": self.entry,
                    "stop_loss": self.sl, "take_profit": self.tp,
                    "strategy_id": "t"}
        return None
    def exit_signal(self, df, i):
        return None  # handled by touch logic in runner
    def on_fill(self, d, p, i, df):
        self.in_pos = True
    def on_exit(self):
        self.in_pos = False


def make_df(prices):
    idx = pd.date_range("2026-01-01 13:00", periods=len(prices), freq="h")
    # each bar: open=close=price for simplicity; high/low straddle by 0.001
    rows = []
    for p in prices:
        rows.append({"open": p, "high": p + 0.001, "low": p - 0.001,
                     "close": p, "volume": 100})
    return pd.DataFrame(rows, index=idx)


def test_pnl_contract_multiplier():
    # 100 pip move on EURUSD, 0.1 lot -> 0.01 * 0.1 * 100000 = 100.0
    p = _pnl("LONG", 1.1000, 1.1100, 0.1)
    assert abs(p - 100.0) < 1e-6


def test_entry_fills_next_bar_not_signal_bar():
    # signal on bar 0 at 1.100; TP at 1.110. Bar 1 must be where fill happens.
    df = make_df([1.100, 1.115, 1.115, 1.115])
    s = OneShotStrategy(0, 1.100, 1.090, 1.110)
    res = run_canonical_backtest(df, s, initial_equity=10000.0, symbol="EURUSD",
                                 spread_pips=0.0, slippage_pips=0.0,
                                 session_windows=[])
    assert len(res.trades) == 1
    # fill at next bar open = 1.115 (no spread/slip); TP 1.110 is BELOW fill,
    # so on bar 1 the high (1.116) >= TP? high=1.115+0.001=1.116 >= 1.110 -> TP hit
    t = res.trades[0]
    assert abs(t.entry_price - 1.115) < 1e-9
    assert t.exit_reason == "take_profit"
    # pnl = (1.110 - 1.115) * 0.1 * 100000 = -500 (filled worse than TP level)
    assert t.pnl < 0


def test_stop_first_on_conflicting_bar():
    # bar 1 touches both SL (1.090) and TP (1.110). Stop-first -> loss.
    df = make_df([1.100, 1.100, 1.100, 1.100])
    # make bar 1's high/low span both: high=1.111, low=1.089
    df.loc[df.index[1], "high"] = 1.111
    df.loc[df.index[1], "low"] = 1.089
    s = OneShotStrategy(0, 1.100, 1.090, 1.110)
    res = run_canonical_backtest(df, s, initial_equity=10000.0, symbol="EURUSD",
                                 spread_pips=0.0, slippage_pips=0.0,
                                 session_windows=[])
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.exit_reason == "stop_loss"
    assert t.pnl < 0


def test_no_trade_when_session_gate_blocks():
    # 03:00 UTC = outside NY 08-11 (13-16 UTC). No session override -> gate active.
    idx = pd.date_range("2026-01-01 03:00", periods=3, freq="h")
    df = pd.DataFrame({"open": [1.1]*3, "high": [1.101]*3,
                       "low": [1.099]*3, "close": [1.1]*3, "volume": [100]*3}, index=idx)
    s = OneShotStrategy(0, 1.100, 1.090, 1.110)
    res = run_canonical_backtest(df, s, initial_equity=10000.0, symbol="EURUSD",
                                 spread_pips=0.0, slippage_pips=0.0)
    # default config session gate (8-11 NY) blocks 03:00 UTC
    assert len(res.trades) == 0


def test_risk_gate_blocks_oversized_proposal():
    # entry_price == stop_loss -> zero stop distance -> engine rejects
    df = make_df([1.100, 1.100, 1.100])
    s = OneShotStrategy(0, 1.100, 1.100, 1.110)  # sl == entry
    res = run_canonical_backtest(df, s, initial_equity=10000.0, symbol="EURUSD",
                                 spread_pips=0.0, slippage_pips=0.0,
                                 session_windows=[])
    assert len(res.trades) == 0


def test_monte_carlo_all_wins_passes():
    # every trade +10 -> 100% profitable
    r = run_monte_carlo([10.0, 10.0, 10.0], initial_equity=1000.0,
                        n_simulations=200, min_profitable_pct=70.0, seed=1)
    assert r.profitable_pct == 100.0
    assert r.passed is True


def test_monte_carlo_all_losses_fails():
    r = run_monte_carlo([-10.0, -5.0, -3.0], initial_equity=1000.0,
                        n_simulations=200, min_profitable_pct=70.0, seed=1)
    assert r.profitable_pct == 0.0
    assert r.passed is False


def test_monte_carlo_reproducible_with_seed():
    pnls = [12.0, -5.0, 8.0, -3.0, 20.0, -8.0]
    a = run_monte_carlo(pnls, n_simulations=300, seed=42)
    b = run_monte_carlo(pnls, n_simulations=300, seed=42)
    assert a.profitable_pct == b.profitable_pct
    assert a.median_return_pct == b.median_return_pct
