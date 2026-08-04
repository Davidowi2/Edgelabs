"""Portfolio allocation layer (P3).

Combines independent strategy equity streams into one risk-gated book.

Two combiners are provided:
  - vol_parity: weights sleeves by inverse volatility so each contributes equal
    risk. Standard multi-strategy technique.
  - with_dd_cap: scales the combined book down until its worst peak-to-trough
    drawdown respects a hard budget (EdgeLab's 4% aggregate gate). This is how
    a high-vol sleeve (crypto trend) is made compatible with the repo's tight
    risk limit WITHOUT changing the underlying edge logic.

Honesty note: a sleeve that fails the repo's standalone bar (e.g. H6: 163 trades
< 200, 29.7% DD) is NOT counted as a "pass". It is included here as a
risk-capped allocation, and that status is reported, not hidden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class PortfolioResult:
    combined_equity: pd.Series = field(default_factory=pd.Series)
    weights: dict = field(default_factory=dict)
    scale: float = 1.0
    metrics: dict = field(default_factory=dict)
    max_drawdown_pct: float = 0.0
    dd_budget: float = 4.0
    dd_ok: bool = False


def _daily_returns(equity: pd.Series) -> pd.Series:
    """Equity -> daily returns, aligned to a clean daily index."""
    eq = equity.sort_index()
    eq = eq[~eq.index.duplicated(keep="last")]
    daily = eq.resample("D").last().ffill()
    # first valid point
    daily = daily[daily.notna()]
    if len(daily) < 2:
        return pd.Series(dtype=float)
    rets = daily.pct_change().fillna(0.0)
    return rets


def vol_parity_weights(return_streams: dict[str, pd.Series]) -> dict[str, float]:
    """Inverse-volatility weights across named return streams (aligned)."""
    aligned = pd.DataFrame(return_streams).fillna(0.0)
    vols = aligned.std()
    inv = 1.0 / vols.replace(0, np.nan)
    inv = inv.fillna(0.0)
    if inv.sum() == 0:
        w = pd.Series(1.0 / len(aligned.columns), index=aligned.columns)
    else:
        w = inv / inv.sum()
    return w.to_dict()


def with_dd_cap(equity: pd.Series, dd_budget_pct: float = 4.0,
                initial_equity: float = 10000.0) -> tuple[pd.Series, float]:
    """Scale a book so its worst peak-to-trough DD <= budget.

    Naive equity-scaling about the initial point is NOT linear in drawdown when
    the equity has large prior gains (the peak sits far above `init`, shrinking
    the DD denominator). So we binary-search the RETURN-scale factor k in [0,1]:
    rebuild equity from returns*k, measure maxDD, and converge on k that makes
    maxDD == budget. This is exact and robust to any equity shape.

    Returns (scaled_equity, scale_factor). scale=1.0 if already within budget.
    """
    eq = equity.astype(float)
    peak0 = eq.cummax()
    dd0 = (peak0 - eq) / peak0
    max_dd0 = float(dd0.max()) * 100.0 if len(dd0) else 0.0
    if max_dd0 <= dd_budget_pct or max_dd0 == 0:
        return eq, 1.0

    rets = eq.pct_change().fillna(0.0)
    lo, hi = 0.0, 1.0
    best_k = 1.0
    for _ in range(40):
        mid = (lo + hi) / 2.0
        e = initial_equity * (1.0 + rets * mid).cumprod()
        peak = e.cummax()
        dd = (peak - e) / peak
        md = float(dd.max()) * 100.0
        if md <= dd_budget_pct:
            best_k = mid
            lo = mid  # can scale up a bit more
        else:
            hi = mid
    scaled_eq = initial_equity * (1.0 + rets * best_k).cumprod()
    return scaled_eq, best_k


def combine_equity(equities: dict[str, pd.Series], weights: dict[str, float],
                   dd_budget_pct: float = 4.0, initial_equity: float = 10000.0) -> PortfolioResult:
    """Combine sleeve EQUITY curves by weight (NOT returns) — the correct way
    when sleeves trade at different frequencies (e.g. monthly rebalance + daily
    trend). Weighted equity sum, rebased to initial_equity, then DD-capped."""
    aligned = pd.DataFrame(equities).sort_index().ffill()
    aligned = aligned.fillna(initial_equity)
    w = pd.Series(weights).reindex(aligned.columns).fillna(0.0)
    if w.sum() > 0:
        w = w / w.sum()
    # weighted equity (each sleeve starts at initial_equity)
    combined_eq = (aligned.mul(w, axis=1).sum(axis=1))
    # rebased to initial_equity so weights mean capital allocation
    combined_eq = combined_eq / combined_eq.iloc[0] * initial_equity
    capped_eq, scale = with_dd_cap(combined_eq, dd_budget_pct, initial_equity)
    peak = capped_eq.cummax()
    dd = (peak - capped_eq) / peak
    max_dd = float(dd.max()) * 100.0 if len(dd) else 0.0
    return PortfolioResult(combined_equity=capped_eq, weights=w.to_dict(), scale=scale,
                           max_drawdown_pct=max_dd, dd_budget=dd_budget_pct,
                           dd_ok=max_dd <= dd_budget_pct)


def portfolio_metrics(equity: pd.Series, initial_equity: float = 10000.0) -> dict:
    """Reuse the canonical metric shape (PF/win not meaningful for a combined
    book; report return, vol, Sharpe, maxDD)."""
    eq = equity.dropna()
    if len(eq) < 2:
        return {"total_return_pct": 0.0, "ann_vol_pct": 0.0, "sharpe": 0.0,
                "max_drawdown_pct": 0.0}
    rets = eq.pct_change().fillna(0.0)
    total_ret = (eq.iloc[-1] / initial_equity - 1) * 100
    ann_vol = float(rets.std() * np.sqrt(252)) * 100
    sharpe = float(rets.mean() / rets.std() * np.sqrt(252)) if rets.std() > 0 else 0.0
    peak = eq.cummax()
    dd = (peak - eq) / peak
    max_dd = float(dd.max()) * 100
    return {"total_return_pct": total_ret, "ann_vol_pct": ann_vol,
            "sharpe": sharpe, "max_drawdown_pct": max_dd}
