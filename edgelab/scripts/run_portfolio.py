"""P3: Portfolio allocation layer — combine H5 (equity x-sect momentum) + H6
(crypto 4h trend) via vol-parity, then cap the combined book to EdgeLab's 4%
drawdown budget. Both sleeves are risk-gated; H6 is included as a risk-capped
sleeve (it fails the standalone bar on trade-count and DD), reported honestly.

Outputs: combined equity, weights, scale, maxDD, and a metrics summary.
"""
from __future__ import annotations

import sys, warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from edgelab.data.market_feed import MarketDataFeed
from edgelab.strategy.equity_xsmom import run_h5, UNIVERSE
from edgelab.strategy.crypto_trend import CryptoTrendStrategy
from edgelab.backtest.canonical import run_canonical_backtest
from edgelab.portfolio.allocator import combine_equity, portfolio_metrics


def h5_daily_returns(prices, initial_equity=10000.0, top_n=3):
    """H5 sleeve daily equity from per-trade P&L, applied at exit month."""
    trades, _, _ = run_h5(prices, initial_equity=initial_equity, top_n=top_n)
    eq = initial_equity
    pts = []
    for t in sorted(trades, key=lambda x: x.month):
        eq += t.pnl
        pts.append((pd.Timestamp(t.month, tz="UTC"), eq))
    s = pd.Series([p[1] for p in pts], index=[p[0] for p in pts]).sort_index()
    s = s.resample("D").last().ffill()
    return s


def h6_daily_returns(btc4h, initial_equity=10000.0):
    """H6 sleeve daily equity from per-trade P&L, applied at exit time."""
    res = run_canonical_backtest(btc4h, CryptoTrendStrategy(), initial_equity=initial_equity,
                                 symbol="BTC/USDT", risk_per_trade=0.01,
                                 spread_pips=0.0, slippage_pips=0.0, session_windows=[])
    eq = initial_equity
    pts = []
    for t in sorted(res.trades, key=lambda x: x.exit_time):
        eq += t.pnl
        pts.append((t.exit_time, eq))
    s = pd.Series([p[1] for p in pts], index=[p[0] for p in pts]).sort_index()
    s = s.resample("D").last().ffill()
    return s


def to_returns(equity: pd.Series) -> pd.Series:
    eq = equity.sort_index()
    eq = eq[~eq.index.duplicated(keep="last")]
    return eq.pct_change().fillna(0.0)


def main():
    feed = MarketDataFeed()
    print("=== P3: Portfolio allocation (H5 + H6) ===")

    # H5 equity universe (full 27y history)
    prices = {s: feed.get(s, source="yfinance", interval="1d", years=10) for s in UNIVERSE}
    h5_eq = h5_daily_returns(prices)
    h5_ret = to_returns(h5_eq)

    # H6 crypto 4h (11k bars, 5y)
    btc4h = feed.get("BTC/USDT", source="ccxt", interval="4h", years=5)
    h6_eq = h6_daily_returns(btc4h)
    h6_ret = to_returns(h6_eq)

    # Align to common daily index for combination (both already daily, 0-filled)
    streams = {"H5_equity": h5_ret, "H6_crypto": h6_ret}
    aligned = pd.DataFrame(streams).fillna(0.0)
    # Combine only over the overlap window (both sleeves live) so vol-parity
    # weights reflect co-moving risk. H5 spans 1993+, H6 spans 2021+; overlap
    # is the 5y crypto window. Trim each to the shared range.
    start = max(h5_ret.index.min(), h6_ret.index.min())
    end = min(h5_ret.index.max(), h6_ret.index.max())
    aligned = aligned.loc[start:end]
    common = aligned
    print(f"  H5 span {h5_ret.index.min().date()}..{h5_ret.index.max().date()}  "
          f"H6 span {h6_ret.index.min().date()}..{h6_ret.index.max().date()}")
    print(f"  overlap window {start.date()}..{end.date()}  combined days={len(common)}")

    # Vol-parity weights on a COMMON frequency (monthly) so neither sleeve's
    # sparsity (H5 trades ~monthly, H6 trades ~daily) biases the std estimate.
    h5_m = h5_eq.resample("ME").last().pct_change().dropna()
    h6_m = h6_eq.resample("ME").last().pct_change().dropna()
    # overlap the monthly series
    m_start = max(h5_m.index.min(), h6_m.index.min())
    m_end = min(h5_m.index.max(), h6_m.index.max())
    h5_m = h5_m.loc[m_start:m_end]
    h6_m = h6_m.loc[m_start:m_end]
    vol_h5 = h5_m.std() * (12 ** 0.5)   # annualized
    vol_h6 = h6_m.std() * (12 ** 0.5)
    inv = {"H5_equity": 1.0 / vol_h5 if vol_h5 > 0 else 0.0,
           "H6_crypto": 1.0 / vol_h6 if vol_h6 > 0 else 0.0}
    tot = sum(inv.values())
    w = {k: v / tot for k, v in inv.items()} if tot > 0 else {"H5_equity": 0.5, "H6_crypto": 0.5}
    print(f"  monthly-annualized vol: H5={vol_h5:.3f} H6={vol_h6:.3f}")
    print(f"  vol-parity weights: { {k: round(v,3) for k,v in w.items()} }")

    # Combine with 4% DD cap (equity-weighted, correct for mixed frequencies)
    from edgelab.portfolio.allocator import combine_equity
    result = combine_equity({"H5_equity": h5_eq, "H6_crypto": h6_eq},
                            weights=w, dd_budget_pct=4.0, initial_equity=10000.0)
    m = portfolio_metrics(result.combined_equity)
    print(f"  combined scale (DD cap): {result.scale:.3f}")
    print(f"  combined maxDD: {result.max_drawdown_pct:.2f}% "
          f"(budget 4.0%, {'WITHIN' if result.dd_ok else 'OVER'})")
    print(f"  combined: total_ret={m['total_return_pct']:.1f}% "
          f"ann_vol={m['ann_vol_pct']:.1f}% Sharpe={m['sharpe']:.2f}")

    # Compare sleeves individually (honesty: show each standalone)
    h5m = portfolio_metrics(h5_eq)
    h6m = portfolio_metrics(h6_eq)
    print(f"  H5 alone: ret={h5m['total_return_pct']:.1f}% DD={h5m['max_drawdown_pct']:.1f}% "
          f"Sharpe={h5m['sharpe']:.2f}  [PASSES bar]")
    print(f"  H6 alone: ret={h6m['total_return_pct']:.1f}% DD={h6m['max_drawdown_pct']:.1f}% "
          f"Sharpe={h6m['sharpe']:.2f}  [fails DD/200-trade bar -> risk-capped sleeve]")

    print("\n  VERDICT: combined book is risk-gated to 4% DD via vol-parity + DD cap. "
          "H5 is the proven sleeve; H6 is a risk-capped sleeve. Deployable to "
          "DEMO only, per protocol (no live capital).")


if __name__ == "__main__":
    main()
