# Hypothesis H7 — G10 FX Carry (uncorrelated sleeve candidate)

_Drafted 2026-08-04 to pursue the >=2-strategy portfolio bar (P3). NOT yet
validated. H5 (equity cross-sectional momentum) is the only proven edge; H6
(crypto 4h) is risk-capped. A second UNCORRELATED, validated edge is required
before the portfolio layer is "real" per RESEARCH_PROTOCOL_v1._

## Rationale for FX carry
- **Uncorrelated to H5**: H5 is equity cross-sectional momentum (long winners /
  short losers within equities). G10 FX carry (long high-yield / short low-yield
  currencies) is driven by rate differentials + risk sentiment, not equity
  momentum. Historical equity–FX-carry correlation is low/negative in stress.
- **Capacity & cost**: FX is deep, liquid, low-fee — suitable for the vol-parity
  allocation framework already built.
- **Data availability**: yfinance/ccxt can supply daily FX (e.g. AUDJPY, NZDUSD,
  USDCHF, EURUSD) and central-bank rate proxies.

## Proposed spec (to be validated honestly, not tuned to pass)
- Universe: liquid G10 pairs with clean rate differential (AUD, NZD, NOK long vs
  JPY, CHF, EUR short).
- Signal: rank by 3-month rate-differential carry; hold top decile long, bottom
  decile short, monthly rebalance.
- Risk: per-pair vol target; sleeve capped so total book stays within 4% DD
  budget (reuse the harness from H5/H6).
- Validation bar (same as H5): PF > 1.2 OOS, >= 200 trades, >= 70% Monte Carlo
  profitable, < 4% max DD. Walk-forward (NOT the mislabeled OOS we replaced).
- **Retire if it fails the bar** — no tuning-to-pass. Carry can suffer sharp
  drawdowns in risk-off regimes; that is exactly what the bar is designed to
  catch.

## Next
1. Implement `edgelab/strategy/fx_carry.py` (data via existing feed).
2. Run `scripts/run_walk_forward.py` with H7; compare to H5 correlation.
3. If CONSISTENT + uncorrelated (|rho| < 0.5 to H5) + passes bar -> promote to
   portfolio; else retire and draft H8.

## Status
DRAFT. Not yet implemented or validated.
