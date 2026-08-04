# P3 Milestone — Portfolio Allocation Layer

_Date: 2026-08-04. All numbers from live runs this session._

## What was built
`edgelab/portfolio/allocator.py` — a multi-strategy allocation layer:
- `vol_parity_weights`: inverse-vol weights (standard multi-strategy technique).
- `with_dd_cap`: binary-searches the return-scale factor so the book's worst
  peak-to-trough drawdown hits the repo's 4% budget exactly (robust to any
  equity shape; naive equity-scaling about init is non-linear when there are
  large prior gains — see below).
- `combine_equity`: combines sleeve EQUITY curves by weight (NOT returns — the
  correct method when sleeves trade at different frequencies, e.g. H5 monthly
  rebalance + H6 4h trend).

Driver: `scripts/run_portfolio.py` (builds H5 + H6 equity streams, weights them,
caps DD, prints per-sleeve and combined metrics).

## Combined book (H5 + H6, overlap 2021-09..2026-07, 1782 days)
| Metric | Combined | H5 alone | H6 alone |
|--------|----------|----------|----------|
| Weight (vol-parity) | 80.2% / 19.8% | 100% | 100% |
| Total return (overlap) | **17.8%** | 874%* | 233.6% |
| Max drawdown | **4.00% (capped)** | 53.1% | 29.3% |
| Sharpe | 0.50 | 0.47 | 0.56 |
| Scale (DD cap) | 0.069 | — | — |

\* H5's 874% is over its full 27y history; on the 5y overlap it is far smaller.
The combined 17.8% is the honest, DD-capped result: you cannot keep H6's 233%
return AND stay under 4% DD — the cap necessarily dampens returns. That is
correct risk management, not a bug.

## Verdict
- **H5 is the proven sleeve** (passes the repo bar: PF 1.39 OOS, 912 trades,
  MC 100%).
- **H6 is a risk-capped sleeve** — its edge is real (PF 2.15, MC 98.4%) but it
  fails the standalone bar on trade-count (163 < 200) and DD (29.3% >> 4%). It is
  included at 19.8% weight with the 4% DD cap, NOT counted as a "pass".
- The combined book is **risk-gated to 4% DD** and is the deployable artifact.
  Per protocol, it goes to DEMO forward-testing only (no live capital).

## Bugs fixed getting here (legitimate, not tuning)
1. Vol-parity on daily returns gave H6 weight 1.0 / H5 0.0 — H5's monthly
   rebalances made its daily-return std≈0. Fixed by computing vol on a COMMON
   monthly frequency for both sleeves.
2. Combining sparse monthly P&L with daily returns via additive returns produced
   a -100% crash (H5's month-end P&L spike became a ±5% daily return). Fixed by
   combining EQUITY curves, not returns.
3. `with_dd_cap` initially scaled returns → under-corrected long drawdowns
   ((1+k)^N). Then scaled equity about init → non-linear when gains present.
   Final: binary-search the return-scale factor until maxDD == budget exactly.

Full pytest suite: **676 passed** (no regressions from any P3 change).

## Next (P4)
Demo forward test per protocol: configure TradeLocker demo ($10k, 1% risk),
run 3-month forward test, compare live fills vs backtest assumptions. Only
AFTER the demo proves the edge, consider the Blueberry 1-Step challenge.
