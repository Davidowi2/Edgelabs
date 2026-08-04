# Hypothesis H6: Crypto Trend on 4h (BTC/USDT) — sample-size fix for H4

Status: NEW hypothesis, redesign of H4 on a finer timeframe. Written BEFORE running.

## Why
H4 (daily BTC trend-breakout) walk-forward showed a positive direction (PF 2.69,
MC 73.9% PASS) but only **6 OOS trades** across 5.47y — far below the 200-trade
validation bar. Daily breakouts are rare. The EDGE LOGIC is unchanged from H4
(EMA200 trend filter + 20-bar highest-close breakout + 2×ATR stop + EMA50/30-bar
exit); only the TIMEFRAME changes from 1d to 4h to achieve an adequate sample.
This is a legitimate instrument/timeframe redesign, NOT parameter tuning to pass.

## Prediction (stated before running)
4h BTC over 5y yields ~10x the bars of daily, so the breakout logic should fire
hundreds of times → enough trades to satisfy the 200+ bar. Expect the same
positive PF direction as H4's daily result. If 4h PF<=1.2 or MC fails or N<200,
H6 is RETIRED (and H4 family is closed as unconfirmable on available data).

## Discipline note
If H6 passes, it is counted as the SECOND independent strategy (alongside H5)
needed before the portfolio layer. H4 (daily) is NOT double-counted — it is the
same edge class on a coarser timeframe; only H6 (4h) carries the validation.
