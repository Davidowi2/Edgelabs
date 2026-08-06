"""Risk-parity allocation layer for the multi-component system.

Given the equity curves / monthly returns of two or more sleeves (e.g. Sleeve 1 =
vol-targeted H5, Sleeve 2 = TSMOM), size each so it contributes EQUAL RISK
(volatility), not equal capital. This is the "all-weather" backbone: no single
sleeve dominates, so one bad regime in one sleeve can't sink the book.

Risk parity here = inverse-vol weighting across sleeves (the standard, robust form):
  w_i = (1 / vol_i) / sum_j(1 / vol_j)
If a sleeve has ~0 vol (flat), we floor the allocation to avoid divide-by-zero and
renormalize. A max-weight cap prevents concentration.

Input: dict sleeve_name -> list of monthly returns (fractional). Returns weights.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np


def risk_parity_weights(returns: Dict[str, List[float]], max_weight: float = 0.75) -> Dict[str, float]:
    """Inverse-vol (risk-parity) weights across sleeves.

    returns: {sleeve: [monthly fractional returns]}. All sleeves must share length.
    max_weight: cap so no single sleeve exceeds this (default 0.75).
    Returns {sleeve: weight} summing to 1.0.
    """
    names = list(returns.keys())
    if not names:
        return {}
    n = len(returns[names[0]])
    vols = {}
    for s in names:
        arr = np.array(returns[s][:n], dtype=float)
        vols[s] = float(np.std(arr, ddof=1)) if len(arr) > 1 and np.std(arr) > 1e-9 else 0.0
    # inverse-vol, floor zero-vol sleeves to 0 (they add no risk, get no weight)
    inv = {s: (1.0 / v if v > 1e-6 else 0.0) for s, v in vols.items()}
    total = sum(inv.values())
    if total <= 0:
        # all flat: equal weight
        w = {s: 1.0 / len(names) for s in names}
    else:
        w = {s: inv[s] / total for s in names}
    # apply max-weight cap, renormalize
    capped = {s: min(w[s], max_weight) for s in names}
    csum = sum(capped.values())
    if csum <= 0:
        capped = {s: 1.0 / len(names) for s in names}
    else:
        capped = {s: capped[s] / csum for s in names}
    return capped


def combine_sleeves(returns: Dict[str, List[float]], max_weight: float = 0.75,
                    initial_equity: float = 10_000.0) -> dict:
    """Allocate across sleeves by risk parity and build the combined equity curve.

    returns: {sleeve: [monthly fractional returns]}.
    Returns {weights, equity_curve, metrics_summary}.
    """
    weights = risk_parity_weights(returns, max_weight=max_weight)
    n = len(next(iter(returns.values())))
    # combined monthly return = sum(weight_i * return_i)
    combined = [0.0] * n
    for s, rs in returns.items():
        w = weights.get(s, 0.0)
        for i in range(n):
            combined[i] += w * rs[i]
    eq = [initial_equity]
    for r in combined:
        eq.append(eq[-1] * (1.0 + r))
    eq_curve = list(zip(range(n + 1), eq))
    eq_arr = np.array(eq)
    total_return_pct = (eq_arr[-1] - initial_equity) / initial_equity * 100
    peak = np.maximum.accumulate(eq_arr)
    dd = (peak - eq_arr) / np.where(peak == 0, 1, peak)
    max_dd = float(np.max(dd)) * 100
    ret_arr = np.diff(eq_arr)
    sharpe = float(np.mean(ret_arr) / np.std(ret_arr)) * np.sqrt(12) if np.std(ret_arr) > 0 else 0.0
    return {
        "weights": weights,
        "combined_monthly_returns": combined,
        "equity_curve": eq_curve,
        "total_return_pct": total_return_pct,
        "max_drawdown_pct": max_dd,
        "sharpe_ratio": sharpe,
        "n_months": n,
    }
