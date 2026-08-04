# XAUUSD H4 Trend-Pullback Family — Final Verdict

Three hypotheses tested on the repo's live-candidate instrument (XAUUSD H4),
all through the honest canonical backtester + Monte Carlo. Data: ~2y
(Yahoo GC=F cap; 5y bar NOT met by available free data).

| Hyp | Bias rule | EMA band | Trigger | Trades (FULL) | PF OOS | MC OOS | Result |
|-----|-----------|----------|---------|---------------|--------|--------|--------|
| v1  | swing 70% | 0.5%     | rejection candle | 0 | n/a | n/a | RETIRED (0 trades) |
| H2  | swing 70% | 1.5%     | directional close | 0 | n/a | n/a | RETIRED (0 trades) |
| H3  | EMA50 trend | 1.5%   | directional close | 40 | 0.00 | 0.0% | RETIRED (fails bar) |

## Conclusion
The XAUUSD H4 trend-pullback FAMILY has no edge under honest measurement.
Root cause of v1/H2 zero-trades: gold H4 rarely forms textbook swing structure
within 1.5% of its 200 EMA during the NY session. H3 (loose EMA50 trend filter)
fires 40 trades but PF<1 and MC 0% — a net-losing approach on this instrument.

Per RESEARCH_PROTOCOL and the project roadmap, the family is RETIRED. No 4th
attempt. Pivot to UNCORRELATED edge classes: crypto trend/carry (ccxt) and
equity cross-sectional momentum (yfinance), per the skill-library framework.

## Bug fixed during this work (important)
Discovered and fixed a timezone bug in the canonical runner (commit-level):
  - runner did `ts.replace(tzinfo=timezone.utc)`, corrupting NY-local bar
    timestamps into UTC, so the RiskEngine's session gate rejected EVERY
    proposal. Symptom: 55 valid signals -> 0 trades.
  - Fix: pass the bar timestamp as-is (already NY-local tz-aware).
  - Also fixed Clock/engine to honor `session_windows=[]` as "no gate"
    (previously coerced to default windows), restoring 2 unit tests.
Full suite: 676 passed after fixes.
