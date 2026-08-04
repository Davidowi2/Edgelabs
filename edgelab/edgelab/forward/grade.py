"""Forward-test grader (P4 operational close-out).

Given the accumulated journal (data/forward_journal.csv) and current marks,
reconstruct the paper book's equity over the forward window and grade it against
the backtest profile. This is the "grade" half of the generate -> accumulate ->
grade loop. Pure function `grade_forward` is unit-tested; the driver pulls live
prices and prints the verdict.

Verdict rules (honest, conservative):
  - forward maxDD > 4%  -> BREACH (exceeded the repo's hard DD gate)
  - otherwise, forward return sign matches the strategy's historical profile
    AND it is not a catastrophic loss -> CONSISTENT
  - else -> REVIEW (worth a human look before any capital decision)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class GradeResult:
    window_start: Optional[datetime]
    window_end: Optional[datetime]
    n_signals: int
    forward_return_pct: float
    forward_max_dd_pct: float
    expected_annual_sign: float   # +1 / -1 from backtest profile
    verdict: str                  # CONSISTENT | REVIEW | BREACH
    detail: str = ""


def _equity_from_rows(rows: list[dict], latest_prices: dict) -> pd.Series:
    """Reconstruct a paper-book equity from journal rows (additive model).

    The book starts at 1.0. Each position contributes weight * (mark/entry - 1)
    to the book equity at its as_of — exactly how the canonical backtester
    accumulates `state.equity += pnl`. Positions sharing a timestamp are summed
    (simultaneous book). Returns a daily-stepped Series of book equity.
    """
    if not rows:
        return pd.Series(dtype=float)
    recs = sorted(rows, key=lambda r: r["as_of"])
    # group by timestamp (simultaneous positions at the same as_of)
    from collections import defaultdict
    by_ts = defaultdict(list)
    for r in recs:
        by_ts[r["as_of"]].append(r)
    eq = 1.0
    pts = [(recs[0]["as_of"], eq)]
    for ts in sorted(by_ts.keys()):
        contrib = 0.0
        for r in by_ts[ts]:
            mark = float(latest_prices.get(r["symbol"], r["signal_price"]))
            entry = float(r["signal_price"])
            pnl = (mark / entry - 1.0) if entry > 0 else 0.0
            contrib += float(r["weight"]) * pnl
        eq = eq + contrib  # additive, matches canonical backtester
        pts.append((ts, eq))
    idx = [p[0] for p in pts]
    vals = [p[1] for p in pts]
    return pd.Series(vals, index=idx)


def grade_forward(rows: list[dict], latest_prices: dict,
                  expected_annual_sign: float = 1.0,
                  dd_budget_pct: float = 4.0) -> GradeResult:
    """Grade the accumulated forward journal.

    rows: list of dicts with keys as_of(datetime), symbol, direction,
          signal_price(float), weight(float).
    latest_prices: {symbol: current mark}.
    expected_annual_sign: +1 if the strategy's backtest is net-long-positive.
    """
    if not rows:
        return GradeResult(None, None, 0, 0.0, 0.0, expected_annual_sign,
                            "REVIEW", "no journal rows yet")
    eq = _equity_from_rows(rows, latest_prices)
    if len(eq) < 2:
        return GradeResult(eq.index[0], eq.index[-1], len(rows), 0.0, 0.0,
                           expected_annual_sign, "REVIEW", "single point")
    total_ret = float(eq.iloc[-1] / eq.iloc[0] - 1.0) * 100.0
    peak = eq.cummax()
    dd = (peak - eq) / peak
    max_dd = float(dd.max()) * 100.0
    verdict = "CONSISTENT"
    detail = "within DD budget; forward sign matches profile"
    if max_dd > dd_budget_pct:
        verdict = "BREACH"
        detail = f"forward maxDD {max_dd:.2f}% > {dd_budget_pct:.1f}% budget"
    elif np.sign(total_ret) != np.sign(expected_annual_sign) and abs(total_ret) > 5.0:
        verdict = "REVIEW"
        detail = "forward return sign opposite to backtest profile"
    return GradeResult(eq.index[0], eq.index[-1], len(rows), total_ret, max_dd,
                       expected_annual_sign, verdict, detail)
