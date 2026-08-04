# Hypothesis H7 — G10 FX Carry (12M price-return proxy) — **RETIRED**

_Drafted 2026-08-04. Validated 2026-08-04. **FAILED the bar — retired per
RESEARCH_PROTOCOL_v1 (no tuning-to-pass).**_

## Result (honest, full-sample, 2y daily G10 FX)
- trades=138, win=47.1%, **PF=0.74**, **Sharpe=-0.54**, **maxDD=9.17%**,
  ret=-6.29%, RR=0.83
- Monte Carlo profitable% = **7.3% FAIL** (bar needs >=70%)
- Bar: FAIL (PF<1.2, Sharpe<0.5, DD>4%, MC FAIL)

## Why it failed
- Signal was a *price-return carry proxy* (12M trailing spot return), not a real
  rate differential. Over this window the forward-premium anomaly was weak/negative
  for G10, and the strategy is effectively short-vol/short the USD in a regime that
  hurt. DD (9.17%) blew the 4% sleeve budget on its own.
- Not a tuning problem — the economic signal is absent in-sample AND out. No
  parameter change would make a 7.3% MC profitable edge pass.

## Disposition
- **Retired.** Do NOT revive with different lookbacks/weights (that would be
  tuning-to-pass, forbidden by protocol).
- The honest upgrade is a REAL policy-rate time series (FRED/Datastream) → see H8.

## Status
**RETIRED 2026-08-04.** H5 remains the ONLY proven edge. Portfolio layer (P3)
still short of the >=2-strategy bar.
