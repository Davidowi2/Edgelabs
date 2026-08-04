# Hypothesis H5: Equity Cross-Sectional Momentum (monthly rebalance)

Status: NEW hypothesis — UNCORRELATED EDGE TYPE (cross-sectional / relative
value), distinct from every time-series trend strategy tested so far. This is
the classic "buy the strongest, hold a basket" momentum anomaly.

## Universe
SPY, QQQ, and a set of liquid sector ETFs (XLF, XLE, XLK, XLV, XLI, XLP, XLY,
XLB, XLU). Monthly bars.

## Rules (written before running)
1. At each month-end, rank universe by trailing 12-month return (skipping the
   most recent month — standard 12-1 momentum to avoid short-term reversal).
2. Long the TOP 3 by momentum; equal-weight.
3. Hold for 1 month; rebalance next month-end.
4. Risk: per-name 1% risk is not meaningful for a basket; instead allocate
   equal weight, full notional, and rely on monthly rebalance + diversification.
   (This is a portfolio-level hypothesis, not a single-instrument risk gate.)
5. No stop per name (monthly horizon); the rebalance IS the exit.
6. No session filter (monthly close-to-close).

## Note on the backtester
The canonical backtester is single-position, single-symbol. For H5 we need a
basket backtest. We will compute the basket return series directly from the
monthly rebalance logic (a simple, transparent portfolio simulator) and feed
the resulting equity curve + trade list into the SAME metrics + Monte Carlo
functions, so the validation bar is identical. This is honest: the trade list
is real (each monthly rotation = N entries/exits at next month open).

## Prediction (stated before running)
Cross-sectional equity momentum is one of the most replicated anomalies in
finance (strong academic backing). Expect PF > 1.2, many "trades" (monthly
rotations), modest drawdown. If PF<=1.2 or MC fails, H5 is RETIRED. Data: ~2y
of daily ETF history resampled to monthly (yfinance cap); 5y bar not met.
