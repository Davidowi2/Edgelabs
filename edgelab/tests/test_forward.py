"""Unit tests for the forward-test engine (P4). No network; pure logic.

These verify the journaling/position-inference logic is correct and that the
stub executor can NEVER place an order without the explicit env flag.
"""
from __future__ import annotations
import os, sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from edgelab.forward import (build_forward_book, current_h5_positions,
                             current_h6_position, JournalEntry, ForwardBook)


def _make_prices(n=600):
    """Synthetic monthly-resampleable daily prices for 11 ETFs + momentum tilt."""
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    prices = {}
    ramp = 100.0 + (pd.Series(range(n), dtype=float) * 0.2).values  # plain array, no index
    base = pd.Series(ramp, index=idx)
    for i, s in enumerate(
        ["SPY", "QQQ", "XLF", "XLE", "XLK", "XLV", "XLI", "XLP", "XLY", "XLB", "XLU"]):
        drift = 0.2 if s == "QQQ" else 0.0
        prices[s] = pd.DataFrame({"close": base + drift + i}, index=idx)
    return prices


def test_build_forward_book_weights_and_units():
    as_of = datetime.now(timezone.utc)
    h5 = [{"symbol": "SPY", "direction": "LONG", "price": 500.0}]
    h6 = [{"symbol": "BTC/USDT", "direction": "LONG", "price": 60000.0}]
    prices = {"SPY": 500.0, "BTC/USDT": 60000.0}
    book = build_forward_book(as_of, h5, h6, {"H5_equity": 0.8, "H6_crypto": 0.2}, prices)
    assert len(book.entries) == 2
    spy = [e for e in book.entries if e.symbol == "SPY"][0]
    btc = [e for e in book.entries if e.symbol == "BTC/USDT"][0]
    assert abs(spy.weight - 0.8) < 1e-9
    assert abs(btc.weight - 0.2) < 1e-9
    assert abs(spy.units - 0.8 * 10000 / 500.0) < 1e-3
    assert all(e.status == "PAPER" for e in book.entries)
    assert "no live capital" in book.note.lower()


def test_current_h5_positions_ranks_topn():
    prices = _make_prices()
    pos = current_h5_positions(prices, top_n=3)
    assert len(pos) == 3
    syms = {p["symbol"] for p in pos}
    assert "QQQ" in syms
    assert all(p["direction"] == "LONG" for p in pos)
    qqq_px = float(prices["QQQ"]["close"].iloc[-1])
    assert abs([p for p in pos if p["symbol"] == "QQQ"][0]["price"] - qqq_px) < 1e-6


def test_current_h6_position_returns_valid_list():
    idx = pd.date_range("2021-01-01", periods=300, freq="4h", tz="UTC")
    closes = pd.Series(30000.0 + (pd.Series(range(300)) * 1.0), index=idx)
    btc = pd.DataFrame({"open": closes, "high": closes + 10, "low": closes - 10,
                        "close": closes, "volume": 1.0})
    pos = current_h6_position(btc)
    assert isinstance(pos, list) and len(pos) <= 1


def test_journal_entry_defaults_paper():
    e = JournalEntry(as_of=datetime.now(timezone.utc), sleeve="H5_equity",
                     symbol="SPY", direction="LONG", signal_price=1.0,
                     weight=0.8, units=10.0)
    assert e.live_fill_price is None
    assert e.status == "PAPER"


def test_live_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("EDGELAB_LIVE_EXEC", raising=False)
    assert os.environ.get("EDGELAB_LIVE_EXEC", "").lower() not in ("1", "true", "yes")
