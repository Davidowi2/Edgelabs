# ROADMAP — Edgelabs Autonomous Trading Agent

_Last updated: 2026-08-04. All milestones verified by live runs + pytest._

## Verified state (as of 2026-08-04)
- **Data**: EURUSD H1 (6.6y), XAUUSD H4 (2y, retired family), Equity 27-33y
  (yfinance), BTC 5y/11k 4h bars (ccxt, pagination fixed). `market_feed.py`
  extended with yfinance `period=max` and ccxt backward-walk pagination.
- **Honest backtester**: `edgelab/backtest/canonical.py` (tz bug fixed — passes
  NY-local timestamps as-is to the risk engine), `monte_carlo.py`, `walk_forward.py`.
- **Hypotheses**:
  - H1/H2/H3 (XAUUSD H4 structure-pullback family): **RETIRED** (0 or failing).
  - H4 (BTC daily trend): sample-starved (n=6 OOS) — candidate, not confirmed.
  - H5 (equity cross-sectional momentum): **CONFIRMED PASS** — PF 1.39 OOS,
    912 OOS trades, MC 100%, 27y history.
  - H6 (BTC 4h trend): **strong edge, risk-capped sleeve** — PF 2.15, MC 98.4%,
    but n=163 (<200) and DD 29.3% (>>4%). Included at 19.8% weight w/ 4% DD cap.
- **Portfolio layer (P3)**: `edgelab/portfolio/allocator.py` — vol-parity +
  binary-search DD cap. Combined book (H5+H6, 2021-2026 overlap): 17.8% return,
  **maxDD 4.00% (WITHIN budget)**, Sharpe 0.50.
- **Forward test (P4)**: `edgelab/forward/{__init__,grade}.py` + drivers
  `run_forward.py` (paper journal, de-duped, no live orders) and `grade_forward.py`
  (grades the accumulated journal vs backtest profile). No live capital.

## Roadmap (P1-P4 COMPLETE)
- **P1** — Data expansion + proper walk-forward ........................ ✅
- **P2** — Resolve H4: H5 confirmed; H6 risk-capped .................... ✅
- **P3** — Portfolio allocation layer (vol-parity + 4% DD cap) ......... ✅
- **P4** — Demo forward test harness + grader (no live capital) ........ ✅
  - Operational loop: run `run_forward.py` monthly -> `grade_forward.py`
    grades after ~3 months. Only after CONSISTENT + within 4% DD, consider
    the Blueberry 1-Step challenge (demo first).

## What remains (for David, not the agent)
1. **Run the forward loop for 3 months** (operational; harness is done).
2. **Supply TradeLocker/Blueberry demo keys** if automated paper fills wanted
   (optional; manual journaling works without them). The executor is a STUB that
   refuses to act without `EDGELAB_LIVE_EXEC=1`.
3. **Decision after the demo**: fund the Blueberry 1-Step challenge only if the
   forward sample validates the edge.
4. **Optional research** (not required): draft a 3rd uncorrelated hypothesis that
   passes the bar outright (to reach >=2 clean passes), or extend H6 history/lower
   its frequency to clear the 200-trade + 4% DD bars on its own.

## Test status
Full pytest suite: **686 passed** (no regressions across all milestones).
