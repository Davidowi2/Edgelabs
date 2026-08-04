# Hypothesis H2: Structure Pullback (XAUUSD H4) — Re-specification

Status: NEW hypothesis (replaces the failing documented Strategy 2). Written
BEFORE running, per alpha-research discipline (no in-place tuning of the old
numbers).

## Why the prior version failed (from XAUUSD_H4_RESULT.md diagnostic)
Of 472 NY-session bars: only 24 had clean HTF bias, 1 was within 0.5% of the
200 EMA, 0 formed a rejection candle -> 0 trades. The binding constraints were
the EMA-proximity band (too tight for gold's volatility) and the strict
rejection-candle rule (almost never co-occurs with a near-EMA pullback).

## Changes (principled, not fitted to results)
1. EMA proximity: 0.5% -> 1.5% (standard "near MA" band for high-vol instruments;
   gold ATR ~ 1.5-3% per 4h bar historically).
2. Trigger candle: strict rejection (close>open, body>50% range) -> directional
   close in bias direction (close > open for longs, < open for shorts). The
   *intent* is "buyers won the bar", not "textbook pinbar".
3. HTF bias rule: UNCHANGED (>=70% steps up/down). Diagnostic showed relaxing it
   did not help, so we do not tune a non-binding parameter.
4. Session filter (NY overlap 08:00-11:00): UNCHANGED (liquidity defense).
5. Stop: 1.5 x ATR(20) beyond the trigger bar extreme (unchanged).
6. Trailing: +1R -> breakeven, +2R -> trail 1R (unchanged).
7. Risk 1% (unchanged).

## Validation gate (repo bar, must all hold on OOS)
- total_trades >= 200  (NOTE: 2y data may not reach 200; report honestly)
- profit_factor > 1.2
- max_drawdown_pct < 5.0
- sharpe_ratio > 0.5
- Monte Carlo (1000 sims, >=70% profitable) -> PASS

## Prediction (stated before running)
Gold trend-pullback edges typically show PF 1.1-1.4 and modest trade counts
(~30-80 over 2y at H4). I expect MORE trades than v1 (due to wider band + looser
trigger) but cannot predict PF without the run. If PF<=1.2 OOS or MC fails, the
hypothesis is RETIRED per RESEARCH_PROTOCOL — not patched.
