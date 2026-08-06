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
- TSMOM on crypto/FX still failed on OUR data (H9) — so the TSMOM sleeve must be
  validated on its OWN cross-asset data with the OOS-trade-count gate before promotion.
  We do NOT assume it transfers; we test it the same honest bar.
- Vol-targeting changes H5's risk profile; must re-validate H5-VolTargeted through the
  full 5y bar + OOS gate (not just assert it works).
- This is a DESIGN grounded in literature + our own failure record. It is NOT yet
  coded or proven. Next step = prototype + honest backtest, one sleeve at a time.

## Blocker (cannot complete catalog step)
- User asked to also "catalog my other private repos for prior quant code to port."
  Those repos (alma-model-zero, trovi, dot-platform, llll, sentinelehr-marketing) are
  NOT cloned locally; `gh` CLI is NOT installed; no GITHUB_TOKEN in env.
  => This step is BLOCKED pending: (a) install gh + auth, or (b) user clones repos locally.
  Will NOT fake-catalog. Everything above is grounded in public literature + our own
  committed results (HYP-005 5y, H9/H2/H4/H7/H8 retirements).
