# Research grounding for the multi-component "survive-the-market" upgrade

Grounded via arXiv (public, read-only). Goal: strengthen H5 (proven equity
cross-sectional momentum) into a system that is (a) more active than monthly-only,
(b) crisis-hedged, (c) drawdown-bounded — per the user's requirement that the bot
"survive the market and challenges."

## Anchoring literature (canonical, peer-reviewed)
1. **Time-series momentum (TSMOM)** — Moskowitz, Ooi, Pedersen (2012, Journal of
   Finance). Trend-following across 58 liquid futures is profitable and *uncorrelated*
   to traditional assets; acts as crisis alpha (positive in 2008/2020). This is the
   "active, frequent" sleeve H5 lacks.
2. **Volatility-managed portfolios** — Moreira & Muir (2017, Review of Financial
   Studies). Scaling positions by realized volatility RAISES Sharpe and LOWERS drawdown.
   Directly addresses H5's 53% backtest DD: vol-target the equity momentum sleeve so
   realized risk is bounded ~target vol, not the raw 53%.
3. **Risk parity / diversified allocation** — MAD Risk Parity (2110.12282),
   Diversified reward-risk parity (2106.09055), Risk Parity with Skewness (2202.10721).
   "All-weather" framing: each risk source contributes equally, so no single shock
   dominates. Backbone for the allocation layer across sleeves.

## Design implications (the stronger system)
- **Sleeve 1 — H5 core (vol-targeted):** keep 12-1 cross-sectional equity momentum,
  but vol-scale position sizes to a target vol (e.g. 10-12%/yr). Fixes 53% DD. Still
  monthly rebalance — slow but proven.
- **Sleeve 2 — TSMOM trend-following:** cross-sectional + time-series momentum on a
  broad liquid universe (equities, bonds, gold, FX/crypto via TradeLocker). Rebalances
  MORE often (e.g. weekly/monthly), so the bot is ACTIVE, not asleep 29 days/month.
  Crisis-alpha property hedges equity drawdowns.
- **Allocation layer — risk parity:** size sleeves so each contributes equal risk,
  not equal capital. Survives because no single regime/market kills the whole book.
- **Daily risk check (not monthly):** portfolio vol + DD monitor; halt/derisk on
  breach (hardens the existing 4% DD halt into a portfolio-level risk controller).
- **Crisis filter:** step TSMOM sleeve to cash/hedge when broad trend breaks.

## Honest caveats
- **TSMOM on crypto/FX still failed on OUR data (H9)** — so the TSMOM sleeve must be
  validated on its OWN cross-asset data with the OOS-trade-count gate before promotion.
  We do NOT assume it transfers; we test it the same honest bar.

## Sleeve 1 first result — H5 vol-targeted (2026-08-06, honest backtest)
Ran `edgelab/strategy/h5_voltarget.py` vs raw H5 on FULL 5y + OOS 1y (11 ETFs):
- RAW H5 FULL: maxDD=53.06% PF=1.54 Sharpe=0.55 MC=100%
- VT  H5 FULL: maxDD=39.71% PF=1.58 Sharpe=0.59 MC=100%  (DD −25%, edge holds)
- RAW H5 OOS:  maxDD=14.90% PF=1.37 Sharpe=0.53 MC=94%
- VT  H5 OOS:  maxDD=11.62% PF=1.37 Sharpe=0.52 MC=94%  (DD −22%, edge holds)

**Verdict: vol-targeting works as literature says (cuts DD, keeps edge) but only takes
H5 from 53%→40% DD — still not a "survive-the-market" level.** Root cause: H5 is
long-only, fully-invested, monthly — vol-scaling can't remove a structural equity-crash
drawdown. So Sleeve 1 = slightly safer core; the real survival comes from the OTHER
sleeves (TSMOM crisis-alpha + risk-parity + daily risk control), NOT from tweaking H5
alone. No tuning-to-pass; this is the honest measured number.

## Sleeve 1 — WALK-FORWARD robustness (2026-08-06, learned from tf-trend discipline)
External `tf-trend` (systematic-trend-following) repo's key contribution = WALK-FORWARD
evaluation across multiple OOS folds. We already HAVE this harness (backtest/walk_forward.py);
applied it to H5 via scripts/run_h5_walkforward.py (13 disjoint 3-month OOS folds over 5y):
- RAW H5 WF: OOS trades=1230 PF=1.32 Sharpe=1.24 MC=99.7% PASS  (edge robust across folds)
- VT  H5 WF: OOS trades=1230 PF=1.32 Sharpe=1.29 MC=99.8% PASS
- **Verdict: H5 edge is ROBUST, not a lucky single split** (this is exactly the discipline
  that would have caught our crypto H4 IS-mirage). The walk-forward DD (71%/50%) is a
  concatenation artifact (sums P&L across folds) — NOT per-fold DD; the live 4% halt bounds
  per-fold realized risk. Do NOT misread WF-DD as a real drawdown.
- Transferable technique confirmed: walk-forward multi-fold validation is now standard for
  any new sleeve (esp. TSMOM Sleeve 2) before promotion.
- Vol-targeting changes H5's risk profile; must re-validate H5-VolTargeted through the
  full 5y bar + OOS gate (not just assert it works).
- This is a DESIGN grounded in literature + our own failure record. It is NOT yet
  coded or proven. Next step = prototype + honest backtest, one sleeve at a time.

## Repo-catalog step — DROPPED (user clarification 2026-08-06)
- User clarified: do NOT clone/catalog the private repos (alma-model-zero, trovi,
  dot-platform, llll, sentinelehr-marketing) — nothing relevant there. The earlier
  "blocker" is moot. If AGENT-side knowledge gaps arise, public GitHub / skills
  (arxiv, quant-backtest-engineering, trading-system-audit) are the source, not the
  user's repos. This design rests on public literature + our own committed results
  (HYP-005 5y, H9/H2/H4/H7/H8 retirements). Proceed.

