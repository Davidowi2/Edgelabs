# Hypothesis H3: Structure Pullback (XAUUSD H4) — bias redefinition

Status: NEW hypothesis (3rd attempt on XAUUSD H4 trend-pullback family).
Written BEFORE running, per alpha-research discipline.

## Why H2 failed (from _diag_h2.py)
- NY session bars: 472
- + clean HTF bias (>=70% of 20 bars HH/LL): 24  <-- THE KILLER
- + within 1.5% EMA: 4
- + directional close: 2 -> 0 trades
- BUT 146/472 NY bars ARE within 1.5% of EMA200. So EMA proximity is NOT binding;
  the brittle SWING-STRUCTURE bias rule is.

## Change (principled, standard, not fitted to gold)
Replace the ">=70% of 20 bars form HH+HL / LH+LL" rule with a standard TREND
FILTER that does not require textbook swing structure:
  - TREND = (close > EMA50) for longs, (close < EMA50) for shorts
  - AND EMA50 is sloping the same way (EMA50 now > EMA50 20 bars ago)
This is a conventional, non-tuned trend definition. Everything else (1.5% EMA200
proximity, directional close trigger, 1.5 ATR stop, +1R/+2R trailing, NY session,
1% risk) is UNCHANGED from H2.

## Prediction (stated before running)
A price-vs-EMA50 trend filter will fire far more often than the swing-structure
rule (expected ~50-150 NY bars pass). Trade count should be materially higher.
PF is unknown and will be reported honestly. If PF<=1.2 OOS or MC fails, the
XAUUSD H4 trend-pullback FAMILY is RETIRED and we pivot to crypto/equity edge
classes (per project roadmap) — no 4th attempt on this family.
