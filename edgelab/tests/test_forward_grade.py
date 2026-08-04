"""Unit tests for the forward-test grader (P4). Pure logic, no network."""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from edgelab.forward.grade import grade_forward, _equity_from_rows


def _row(as_of, symbol, price, weight, sleeve="H5_equity"):
    return {"as_of": as_of, "symbol": symbol, "direction": "LONG",
            "signal_price": price, "weight": weight, "sleeve": sleeve}


def test_grade_consistent_when_profitable_and_within_dd():
    rows = [
        _row(datetime(2026, 8, 1, tzinfo=timezone.utc), "SPY", 100.0, 0.8),
        _row(datetime(2026, 9, 1, tzinfo=timezone.utc), "QQQ", 100.0, 0.8),
    ]
    marks = {"SPY": 105.0, "QQQ": 102.0}
    g = grade_forward(rows, marks, expected_annual_sign=1.0)
    assert g.verdict == "CONSISTENT"
    assert g.forward_return_pct > 0
    assert g.forward_max_dd_pct <= 4.0


def test_grade_breach_when_dd_exceeds_budget():
    rows = [_row(datetime(2026, 8, 1, tzinfo=timezone.utc), "SPY", 100.0, 1.0)]
    marks = {"SPY": 90.0}
    g = grade_forward(rows, marks, expected_annual_sign=1.0)
    assert g.verdict == "BREACH"
    assert g.forward_max_dd_pct > 4.0


def test_grade_review_when_sign_opposite():
    rows = [_row(datetime(2026, 8, 1, tzinfo=timezone.utc), "SPY", 100.0, 1.0)]
    marks = {"SPY": 92.0}
    g = grade_forward(rows, marks, expected_annual_sign=1.0, dd_budget_pct=4.0)
    assert g.verdict in ("REVIEW", "BREACH")


def test_grade_empty_rows():
    g = grade_forward([], {}, expected_annual_sign=1.0)
    assert g.verdict == "REVIEW"
    assert g.n_signals == 0


def test_equity_from_rows_monotonic_count():
    rows = [
        _row(datetime(2026, 8, 1, tzinfo=timezone.utc), "SPY", 100.0, 0.5),
        _row(datetime(2026, 9, 1, tzinfo=timezone.utc), "QQQ", 50.0, 0.5),
    ]
    marks = {"SPY": 101.0, "QQQ": 51.0}
    eq = _equity_from_rows(rows, marks)
    assert len(eq) >= 2
    assert eq.iloc[0] == 1.0
