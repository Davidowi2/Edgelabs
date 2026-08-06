# Retired Hypotheses

Required by RESEARCH_PROTOCOL_v1.md §Retirement Documentation. Each entry records
why a hypothesis was retired, its metric values at failure, what we learned, and
whether retesting is permitted.

---

## HYP-007 — G10 FX Carry (12M price-return proxy)
- **test_stage:** full backtest
- **failure_reason:** Proxy (trailing 12M price return) does not capture true carry;
  strategy lost money under the honest bar.
- **metric_values:** PF=0.74, maxDD=9.17%, MC=7.3% (FAIL)
- **lessons_learned:** a price-return proxy for carry is not a stand-in; the real
  rate-differential signal was the honest upgrade path (led to H8).
- **retest_eligibility:** Not via the proxy. H8 superseded it with real rates.

## HYP-002 / 003 — Gold XAUUSD H4 (Structure Pullback family)
Three attempts on the SAME price-action design (HTF structure bias + pullback to
200-EMA + rejection candle, London/NY session filter, 1.5 ATR stop). v1/v2 only
tweaked entry cosmetics; v3 changed the bias to an EMA50 trend filter.
- **test_stage:** canonical backtest, IS/OOS split on XAUUSD_H4_raw.csv (2y, 2024-08..2026-08).
- **failure_reason:** NOT "no edge found" — the real failure is the strategy is
  **practically inert**: the session filter + tight EMA-proximity + rejection-candle
  rules are so restrictive that on H4 gold they almost never trigger.
- **metric_values (OOS / Full):**
  - v1 (structure_pullback_h4): OOS trades=0, Full trades=0 — NEVER FIRED in 2y.
  - v2 (structure_pullback_h4_h2, EMA band 0.5%->1.5%): OOS trades=0, Full trades=1
    (lost), PF=0.00, Sharpe=-0.28, MC=0% (FAIL).
  - v3 (structure_pullback_h4_h3, EMA50 trend bias): OOS trades=6 (all lost),
    PF=0.00, Sharpe=-1.51; Full trades=40, win=27.5%, PF=0.91, Sharpe=-0.06, MC=40.6% (FAIL).
  - Bar needs >=200 trades + PF>1.2 + Sharpe>0.5 + DD<5%. All three fail on trade
    COUNT alone (0 / 1 / 40 << 200) before edge is even measurable.
- **lessons_learned:**
  - The gold hypotheses were weak by construction: pure price-action with no
    fundamental anchor (real rates / DXY / inflation). They trade gold on its own
    candles, which is close to random — AND the filters made them barely trade at all.
  - "No edge found" was a mislabel; the honest finding is "too few trades to judge +
    v3 shows negative edge when it does trade." A strategy that never fires is not a
    strategy.
  - 2y H4 data also fails the 5y validation bar (data-length shortfall, reported honestly).
- **retest_eligibility:** CLOSED as designed. If revisited, must be a NEW hypothesis
  (fundamentally-anchored gold: real-rate or DXY-relative signal), NOT a v4 tweak of
  the same structure-pullback. Requires >=5y data (live FX feed, not Yahoo 2y cap).

## HYP-004 — Crypto Trend (BTC/USDT daily breakout)
- **test_stage:** canonical backtest, IS/OOS split on BTC_USDT_ccxt_1d.csv (5.5y, 2021-2026).
- **failure_reason:** Classic regime break / in-sample overfit. Fired 29 times in the
  2021-2024 bull (IS) and **0 times out-of-sample (2024-2026)**. The "close > EMA200
  + 20-bar highest-close breakout" trigger qualified constantly in the bull and never
  again after the regime changed.
- **metric_values:**
  - IS: trades=29, win=37.9%, PF=2.73, Sharpe=0.63, MC=96.9% (PASS on paper)
  - OOS: trades=0, PF=0.00 (FAIL — 0 trades)
  - Full: trades=34, win=35.3%, PF=2.50, Sharpe=0.53, MC=95.9% (PASS on paper)
  - Bar: PF>1.2 / Sharpe>0.5 / MC>=70% / OOS must trade. IS "passes" but OOS=0 -> FAIL.
- **lessons_learned:**
  - An IS-only "pass" on crypto momentum is a red flag, not a green light. The edge
    decayed to zero the moment the historical window ended. This is the textbook
    crypto problem you flagged: momentum works until everyone chases it, then doesn't.
  - Validation MUST require OOS trade activity, not just IS PF. The harness correctly
    fails it on OOS=0.
- **retest_eligibility:** CLOSED as designed. Crypto momentum is a long shot; a genuine
  new attempt would need a different signal (e.g. cross-sectional crypto momentum,
  funding-rate carry) and explicit OOS trade-count gate.

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
- **Retired (honest numbers now recorded):**
  - H7 — FX carry proxy (PF 0.74, MC 7.3%)
  - H8 — FX carry real-rate v0+v1 (best MC 69.6%, worse v1)
  - H2/H3 — Gold XAUUSD H4 structure-pullback v1/v2/v3 (0 / 1 / 40 trades — INERT)
  - H4 — Crypto BTC daily trend (IS PF 2.73 but OOS 0 trades — regime break)
- **No live capital deployed.** Executor gated behind EDGELAB_LIVE_EXEC=1 (unset).
- **The real lesson:** every non-H5 attempt failed on either (a) trade COUNT (gold:
  never fired) or (b) OOS regime break (crypto: fired only in-sample). H5 is the only
  one that trades consistently AND holds up. That is why it is the sole live strategy.
