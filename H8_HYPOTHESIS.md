# Hypothesis H8 — True FX Carry via policy-rate differentials (DRAFT)

_Drafted 2026-08-04 after H7 (12M price-return proxy) was RETIRED. NOT yet
implemented or validated. Addresses H7's specific weakness: H7 used a price
proxy; H8 uses a REAL interest-rate time series so the carry signal is genuine._

## The fix for H7's failure
H7 failed because its signal was a 12M spot-return proxy, which collapsed (PF
0.74, MC 7.3%). The honest carry edge needs actual rate differentials. Source:
FRED policy-rate / short-rate series per currency (e.g. FEDFUNDS US, and foreign
3M/2Y yields), assembled into a per-pair differential, rebalanced monthly.

## Proposed spec (to be validated honestly, not tuned to pass)
- Universe: G10 pairs as in H7.
- Signal: rank pairs by (foreign 3M yield - US 3M yield); long top-N highest
  differential, short bottom-N lowest; monthly rebalance; equal weight.
- Risk: per-leg vol target; sleeve capped to 4% DD budget (reuse H5/H6 harness).
- Validation bar (same as H5/H7): PF > 1.2, Sharpe > 0.5, >= 70% MC profitable,
  < 4% max DD. Walk-forward (not a single split).
- **Retire if it fails** — no tuning-to-pass.

## Blocker / decision needed
- Needs `fredapi` (or `pandas_datareader`) + a free FRED API key (keyless works
  for many series but is rate-limited). Neither lib is installed in the venv.
- **Requires user go-ahead to install a package and supply/approve a FRED key**
  (or approve keyless FRED). Until then H8 stays a DRAFT.

## Alternative if FX-carry is exhausted
If even true carry fails (carry has been structurally weak post-2008), pivot H8
to a DIFFERENT uncorrelated asset class: **commodity term-structure / roll-yield
carry** (GLD/SLV/DBC futures vs spot, or cross-commodity momentum) via yfinance/
ccxt — genuinely distinct from equity momentum.

## Status
DRAFT. Blocked on package install + FRED key decision. H5 remains the ONLY proven
edge; portfolio layer (P3) still short of the >=2-strategy bar.
