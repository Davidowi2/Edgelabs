# Strategy 2 (XAUUSD H4) — Backtest Result & F-02 Closure

Date: 2026-08-01. Instrument: XAUUSD H4 (the repo's actual live candidate).
Method: documented Strategy 2 rules, run UNMODIFIED through the new honest
canonical backtester (next-bar-open fills, stop-first, correct PnL) + Monte Carlo.

## Data
- Source: Yahoo Finance `GC=F` (gold futures), resampled 1h->4h.
- Coverage: 2024-08-04 .. 2026-08-04 = 3104 H4 bars (~2.0 years).
- HONEST FLAG: free H4 history is capped at ~730 days, so the 5-year
  validation bar is NOT met by available data. (F-11 data-gap, on the XAUUSD side.)

## Result (faithful, no tuning)
- In-sample trades: 0
- Out-of-sample trades: 0
- Full-sample trades: 0
- Monte Carlo: N/A (no trades)
- Validation bar (PF>1.2, DD<5%, Sharpe>0.5, 200 trades): FAIL (0 trades)

## Why zero trades — diagnostic (NOT tuning, just isolation)
Of 472 bars in the NY session window:
  - have a clean HTF bias (>=70% steps up/down): 24
  - of those, within 0.5% of 200 EMA: 1
  - of those, a rejection candle: 0
Relaxing ONE filter at a time barely helps:
  - relax bias to >=60/40%: 0
  - relax EMA proximity to 1.5%: 0
  - drop session window: 0
  - drop rejection-candle rule: 1
  - relax ALL together: 26
CONCLUSION: the documented Strategy 2 rules are individually strict AND mutually
contradictory on XAUUSD H4 — gold rarely pulls back to within 0.5% of its 200
EMA during a clean NY-session trend with a textbook rejection candle. As written,
the system is effectively non-tradeable on its own live-candidate instrument.

## Honest verdict
By the repo's OWN validation bar, Strategy 2 on XAUUSD H4 does NOT qualify for
forward testing. This is not a code bug — it is a strategy-design constraint.
The audit's F-02 prediction (the live candidate was never tested) is now resolved:
it has been tested, faithfully, and it fires ~0 times.

## Options (do NOT tune to force trades)
1. RETIRE per RESEARCH_PROTOCOL (the repo's own rule for failed hypotheses).
2. RE-SPECIFY with evidence: e.g. widen EMA proximity, use a softer bias rule,
   or test a different trigger — but each change is a NEW hypothesis requiring
   its own IS/OOS/MC/validation run (no in-place tuning of these numbers).
3. Test a DIFFERENT instrument/timeframe where the same logic may fire (e.g.
   the original EURUSD H1 proxy) — already shown marginal in STRATEGY_ANALYSIS.

## Reproduce
  python scripts/run_xauusd_h4_backtest.py
  python scripts/_diag_relax.py   (filter-isolation diagnostic)

## Files added (all new, no repo module modified)
- data/XAUUSD_H4_raw.csv
- edgelab/strategy/structure_pullback_h4.py
- scripts/_fetch_xauusd.py, scripts/run_xauusd_h4_backtest.py, scripts/_diag_relax.py
