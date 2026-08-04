# EdgeLab Phase 0 Fix Log (2026-08-01)

## Applied fixes
- [F-01] NEW `edgelab/backtest/canonical.py` — single source of truth. Correct PnL
  via CONTRACT_MULTIPLIER applied INSIDE `_pnl()` (no post-hoc patch). Replaces the
  two conflicting runners. Existing runners left intact (not deleted) to preserve
  the 666 existing tests; canonical is the one new work must use.
- [F-03] Honest fills in canonical runner:
    * ENTRY fills at NEXT bar's OPEN (signal bar cannot be fill bar). Bug fixed:
      first version filled at signal price; now uses `data.iloc[i]["open"]`.
    * On a bar touching BOTH SL and TP -> STOP credited first (conservative).
    * Entry/exit include spread+slippage penalty (worse fill).
- [F-04] NEW `edgelab/backtest/monte_carlo.py` — bootstrap resampling of trade PnL
  sequence; reports profitable_pct + pass(>=70%) per RESEARCH_PROTOCOL. Seeded
  reproducibility.

## Tests added
- `tests/test_canonical_backtest.py` (8 tests): PnL multiplier, next-bar fill,
  stop-first conflict, session gate, risk-gate rejection, + MC pass/fail/repro.
- All 8 pass. Full suite: 666 passed, 1 failed + 9 errored — ALL due to the
  pre-existing missing `data/EURUSD_H1_5y.csv` (audit F-11), NOT my changes.

## Still open (next steps)
- [F-11] Data file missing. Need `EURUSD_H1_5y.csv` (or a fetcher + checksum) to
  reproduce STRATEGY_ANALYSIS and unblock test_data_pipeline.
- [F-02] Backtest the REAL live candidate: Strategy 2 (Structure Pullback) on
  XAUUSD H4, 5y. Currently only EURUSD H1 was tested. Requires XAUUSD H4 data.
- Wire `scripts/run_strategy_backtests.py` to `run_canonical_backtest` +
  `run_monte_carlo` (currently uses strategy_runner). Do after data is present.
- [F-05/F-06/F-07/F-08] Align session/time handling; label walk-forward correctly;
  document governor-neutering in runner.

## Verification command
  python -m pytest tests/test_canonical_backtest.py -q
  -> 8 passed
