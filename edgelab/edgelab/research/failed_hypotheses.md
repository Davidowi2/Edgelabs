# Retired Hypotheses

Required by RESEARCH_PROTOCOL_v1.md §Retirement Documentation. Each entry records
why a hypothesis was retired, its metric values at failure, what we learned, and
whether retesting is permitted.

---

## HYP-007 — G10 FX Carry (12M price-return proxy)
- **test_stage:** full backtest
- **failure_reason:** Proxy (trailing 12M price return) does not capture true carry;
  strategy lost money under the honest bar.
- **metric_values:** trades=?, win=?, PF=0.74, Sharpe=?, maxDD=9.17%, MC=7.3% (FAIL)
- **lessons_learned:** a price-return proxy for carry is not a stand-in; the real
  rate-differential signal was the honest upgrade path (led to H8).
- **retest_eligibility:** Not via the proxy. H8 superseded it with real rates.

## HYP-008 — G10 FX Carry (real rate-differential, monthly)
- **test_stage:** full backtest (v0 static snapshot + v1 time-varying rates)
- **failure_reason:** No tradable edge in the 2024-2026 broad rate-CUTTING regime.
  v0 was a marginal fail (MC 69.6%, 0.4% short); v1 (time-varying + inverse-vol
  sizing) was a CLEAR fail and strictly worse than v0. Not tuned to pass.
- **metric_values:**
  - v0: trades=138, win=51.4%, PF=1.11, Sharpe=0.34, maxDD=2.91%, ret=2.24%, RR=1.04, MC=69.6% (FAIL)
  - v1: trades=138, win=50.0%, PF=1.03, Sharpe=0.06, maxDD=5.08% (breaches 4% gate), ret=0.61%, RR=1.03, MC=54.2% (FAIL)
  - Bar: PF>1.2 / Sharpe>0.5 / MC>=70% / DD<4%. v1 fails all four.
- **lessons_learned:**
  - FX carry needs a *rising* or *stable* rate-differential regime to pay; the
    2024-2026 synchronized global cuts compressed every differential and the
    time-varying signal rotated into losing positions.
  - Inverse-vol sizing did not rescue it (FX vol was broadly elevated).
  - A static snapshot can accidentally look more stable than reality in a trending
    rate regime — another reason v0 beat v1 here, not evidence of edge.
- **retest_eligibility:** CLOSED. Do not retest without (a) new evidence, or
  (b) a materially different rate regime / market structure, or (c) a genuinely
  new carry design (e.g. EM carry, vol-targeted, or a live FRED rate series with a
  cost model). Casual retesting is not allowed.

---

## Status summary
- **Proven / live:** H5 (equity cross-sectional momentum) — Alpaca paper forward-test.
- **Retired:** H7 (FX carry proxy), H8 (FX carry real-rate), H2 (gold XAUUSD).
- **Failed bar, not promoted:** H4/H6 (crypto trend).
- **No live capital deployed.** Executor gated behind EDGELAB_LIVE_EXEC=1 (unset).
