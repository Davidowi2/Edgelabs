# Monitoring Dashboard (P5) — read-only, localhost only

_Date: 2026-08-04. Verified by live run + tests this session._

## What it is
A **mobile-first monitoring dashboard** for the Edgelabs agent. No password to
view it; it serves on `127.0.0.1` (localhost) only and is **read-only** — it
never places orders.

## Run it
```
cd edgelab
python scripts/run_dashboard.py          # http://127.0.0.1:8765
```
Optional env (TradeLocker DEMO read-only feed; NOT required for local panels):
```
TL_EMAIL=...  TL_PASSWORD=...  TL_SERVER=DEMO-SERVER  (never committed)
```
The dashboard's own panels (combined book, DD gauge, H5/H6 sleeves, journal,
grader verdict) need **no credentials** — they read local data.

## Panels
- **Combined Book**: 4% DD-budget gauge (how much of the 4% risk budget the
  forward book has used), grader verdict, forward return, journal signal count.
- **H5 Equity** (PROVEN) / **H6 Crypto** (RISK-CAPPED) sleeve cards: live paper
  positions from the proven H5 + risk-capped H6 logic.
- **Forward Journal**: last signals (symbol / sleeve / direction).
- **TradeLocker Demo**: read-only snapshot button. The connector is a
  fail-safe DEMO gate — it **refuses any server that is not confirmed DEMO**
  (e.g. `CLRTYFX` was refused as "not confirmed DEMO"). It never sends orders.

## Safety
- Binds to `127.0.0.1` only — not reachable from the network.
- No auth on the dashboard (per request), but the TradeLocker feed is gated by
  the DEMO assertion and is read-only by construction (the response dict has no
  `order`/`execute`/`place` fields; tested).
- The order executor remains gated behind `EDGELAB_LIVE_EXEC=1` (never set).

## Tests
`tests/test_dashboard.py` (5 tests): state shape, DEMO gate refuses missing
creds / production server / unknown server, and asserts no order-placement
fields. Full suite: **691 passed**.

## Note on the demo account
The user's demo account is `CLRTYFX#D#2329061` (Clarity FX, **DEMO** — the `#D#`
segment confirms it). The gate accepts IDs/servers carrying an explicit
DEMO/`#D#` marker and refuses bare `CLRTYFX` or anything `PRD*` (production).
With the correct `#D#` ID the panel passes the gate; the live snapshot still
needs the **verified TradeLocker REST endpoints** (no API-key feature exists) to
return real positions. Until those are wired, the panel reports a read-only
scaffold notice. No live account is touched.
