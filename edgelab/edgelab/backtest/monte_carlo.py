"""Monte Carlo simulation for trade sequences (Phase 0 fix, F-04).

REQUIRED by RESEARCH_PROTOCOL_v1.md: 1000 simulations, 70% profitable threshold.
Also required by ARCHITECTURE_v1.md validation_bar (monte_carlo_simulations: 1000,
monte_carlo_min_profitable_pct: 70).

Method: bootstrap resampling (with replacement) of the observed trade-PnL
sequence. We preserve the EMPIRICAL distribution of outcomes (not a fitted
normal), which is the honest approach for short, fat-tailed trade histories.
Each simulation draws `len(trades)` samples and sums them to a final equity
delta. We report the distribution of outcomes and the fraction profitable.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional, Sequence


@dataclass
class MonteCarloResult:
    n_sims: int
    n_trades_per_sim: int
    profitable_pct: float          # % of sims with net profit > 0
    mean_return_pct: float
    median_return_pct: float
    p5_return_pct: float           # 5th percentile (downside)
    p95_return_pct: float          # 95th percentile (upside)
    max_drawdown_pct_median: float
    pass_threshold_pct: float      # the 70% bar
    passed: bool                   # profitable_pct >= pass_threshold


def run_monte_carlo(
    trade_pnls: Sequence[float],
    initial_equity: float = 10_000.0,
    n_simulations: int = 1000,
    min_profitable_pct: float = 70.0,
    per_trade_cost: float = 0.0,   # optional fixed cost per trade (commission)
    seed: Optional[int] = None,
) -> MonteCarloResult:
    if not trade_pnls or len(trade_pnls) < 2:
        return MonteCarloResult(
            n_sims=0, n_trades_per_sim=0, profitable_pct=0.0,
            mean_return_pct=0.0, median_return_pct=0.0, p5_return_pct=0.0,
            p95_return_pct=0.0, max_drawdown_pct_median=0.0,
            pass_threshold_pct=min_profitable_pct, passed=False,
        )

    rng = random.Random(seed)
    pnls = list(trade_pnls)
    k = len(pnls)
    returns = []      # % return per sim
    max_dds = []      # max DD per sim

    for _ in range(n_simulations):
        equity = initial_equity
        peak = initial_equity
        max_dd = 0.0
        for _ in range(k):
            p = rng.choice(pnls) - per_trade_cost
            equity += p
            if equity > peak:
                peak = equity
            if peak > 0:
                dd = (peak - equity) / peak
                if dd > max_dd:
                    max_dd = dd
        ret = (equity - initial_equity) / initial_equity * 100.0
        returns.append(ret)
        max_dds.append(max_dd * 100.0)

    returns.sort()
    profitable = sum(1 for r in returns if r > 0)
    prof_pct = 100.0 * profitable / n_simulations
    median = returns[n_simulations // 2]
    p5 = returns[max(0, int(0.05 * n_simulations))]
    p95 = returns[min(n_simulations - 1, int(0.95 * n_simulations))]
    mean = sum(returns) / n_simulations
    median_dd = sorted(max_dds)[len(max_dds) // 2]

    return MonteCarloResult(
        n_sims=n_simulations,
        n_trades_per_sim=k,
        profitable_pct=prof_pct,
        mean_return_pct=mean,
        median_return_pct=median,
        p5_return_pct=p5,
        p95_return_pct=p95,
        max_drawdown_pct_median=median_dd,
        pass_threshold_pct=min_profitable_pct,
        passed=prof_pct >= min_profitable_pct,
    )
