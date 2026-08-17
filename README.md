# EdgeLabs — Multi-Component Trading Bot

A systematic, risk-bounded trading bot built on **three proven components** and
honest backtesting. It runs as a persistent background process (not a cron job)
and serves a desktop dashboard that shows **what the bot holds, why, and what
it will do next** — not just metrics.

> ⚠️ **No live capital.** Every order path is gated behind explicit demo markers.
> The bot is DESIGNED to refuse live accounts. All credentials in this repo are
> demo/paper only.

---

## What it does

| Component | Role | 5y backtest (honest) |
|-----------|------|----------------------|
| **Sleeve 1 — VT-H5** | Vol-targeted cross-sectional equity momentum (12-1) | DD 39.7%, Sharpe 0.59, PF 1.58 |
| **Sleeve 2 — TSMOM** | Time-series momentum on multi-asset (can short) | DD 8.5%, Sharpe 1.04, PF 1.44 |
| **Risk parity** | Allocates so each sleeve contributes equal risk | Sleeve1 32% / Sleeve2 68% |

**Combined engine (risk-parity blend):** Sharpe **1.10**, Profit Factor **2.24**,
Max Drawdown **6.8%**, Return **+47.6%** over 60 months. RR ≈ 1.15–1.20.

These are **backtest** numbers. A **4% daily-loss halt** + circuit breaker bound
realized risk forward (validated in code, not in live motion).

---

## Architecture

```
bot_runner.py        persistent loop (schedule lib) — monthly rebalance, daily risk check
scripts/run_dashboard.py   desktop-first monitor @ http://127.0.0.1:8080 (reasoning layer)
strategy/h5_voltarget.py    Sleeve 1
strategy/tsmom.py           Sleeve 2
strategy/risk_parity.py     allocation layer
execution/                  brokers (MT5-backed TradeLockerBroker + tradelocker_rest)
monitoring/logger.py        structured JSON logging
backtest/ + strategy/       walk-forward + Monte Carlo honesty harness
```

The bot fetches history, computes Sleeve-2 TSMOM, vol-targets, runs the daily
risk check (4% halt), and — only with authorization — submits DEMO orders.
Default mode is **signal-only** (no orders).

---

## Safety gates (read this)

- **No live capital.** The connector refuses any account marked `PRD`/live and
  any bare `CLRTYFX` without a `#D#` demo marker.
- **No order without two flags:** `EDGELAB_DEMO_FILL=1` **AND** `DEMO_CONFIRM=#D#`.
- Default shipped config places **zero orders** (signal-only). You flip fills on
  deliberately in `.env`.
- Credentials live in a **gitignored `.env`** — never committed.

---

## Quick start (local, simulated)

```bash
pip install -r requirements.txt
python scripts/bot_runner.py            # runs forever; logs to logs/
python scripts/run_dashboard.py         # http://127.0.0.1:8080
```

The dashboard shows the bot's live reasoning immediately, with no broker connected
(simulated `MockBroker`).

---

## Connect a DEMO broker (MetaTrader5)

Our TradeLocker/MT5 connector needs the **MT5 terminal app** running, logged into
your demo account.

1. Copy the env template and fill your demo creds:
   ```bash
   cp edgelab/launcher/.env.example edgelab/launcher/.env
   # edit .env: TL_LOGIN, TL_PASSWORD, TL_SERVER
   ```
2. Open the **MetaTrader 5 terminal**, log into your demo account, and keep it open.
3. Run `edgelab/launcher/bot_launcher.bat` (it starts bot + dashboard + terminal).
4. To actually place DEMO orders, set in `.env`:
   `EDGELAB_DEMO_FILL=1` and `DEMO_CONFIRM=#D#`.

> A generic `MetaQuotes-Demo` account works for connectivity; the proven
> multi-asset signal needs GLD/SPY/QQQ/TLT/IEF/DBC available on that account.
> If unavailable, the bot trades whatever the demo offers.

---

## Make it always run (Windows, not just Hermes)

Use the included Task Scheduler installer so the bot + dashboard survive Hermes
closing and auto-start at logon:

```bat
REM run once (right-click -> Run as administrator)
edgelab\launcher\install_task.bat
```

This registers task `EdgelabsBot` (`onlogon`). To start immediately:
`schtasks /run /tn "EdgelabsBot"`. Dashboard: http://127.0.0.1:8080/

---

## Dashboard

Desktop-first, professional, read-only, bound to `127.0.0.1` (no auth, no network
exposure). Panels: **What the bot is thinking** (positions + WHY), bot status,
**4% daily-loss halt** gauge, and the combined-engine stats.

---

## Research honesty

Failed hypotheses are retired, not tuned-to-pass (FX cross-sectional H9, FX TSMOM,
crypto H4). Validation uses walk-forward + Monte Carlo at a fixed OOS-trade-count
bar. See `edgelab/research/MULTICOMPONENT_DESIGN.md`.

## Disclaimer

For research/education. Not financial advice. Demo/paper only.
