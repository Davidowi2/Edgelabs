"""Desktop-first monitoring dashboard for the multi-component bot.

Reads the bot's REAL artifacts (no stale modules):
  - logs/bot_state.json   (persisted risk state: halt flag, equity, last rebalance)
  - logs/edgelab_YYYY-MM-DD.log  (JSON lines; latest 'rebalance signal',
    broker mode, 'loop alive', 'SUBMISSION HALTED')

Renders the REASONING layer the user asked for: what the bot holds, WHY,
next rebalance, and the 4% daily halt status. Desktop-first, professional.
Binds 127.0.0.1 only. No auth (monitor-only, per prior convention).

Run:  python scripts/run_dashboard.py   (optional DASH_PORT env)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LOG_DIR = REPO / "logs"
STATE_FILE = LOG_DIR / "bot_state.json"

# Combined engine measured stats (from MULTICOMPONENT_DESIGN.md, honest backtest)
ENGINE_STATS = {
    "sharpe": 1.10,
    "profit_factor": 2.24,
    "max_dd_pct": 6.8,
    "total_return_pct": 47.6,
    "rr": "~1.15-1.20",
    "sleeve1": {"name": "VT-H5 (equity momentum, vol-targeted)", "dd": 39.7, "sharpe": 0.59, "pf": 1.58},
    "sleeve2": {"name": "TSMOM (multi-asset trend, can short)", "dd": 8.5, "sharpe": 1.04, "pf": 1.44},
    "weights": {"Sleeve1": "32%", "Sleeve2": "68%"},
}

_DD_BUDGET = 4.0  # % daily loss halt


def _today_log_path() -> Path:
    d = datetime.now(timezone.utc)
    return LOG_DIR / f"edgelab_{d:%Y-%m-%d}.log"


def _read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _parse_log() -> dict:
    """Extract the latest meaningful events from today's JSON log."""
    out = {"last_signal": None, "broker_mode": None, "loop_alive": None,
           "last_halt": None, "proxy": None, "last_ts": None}
    p = _today_log_path()
    if not p.exists():
        return out
    try:
        lines = p.read_text().splitlines()
    except Exception:
        return out
    for raw in lines:
        try:
            e = json.loads(raw)
        except Exception:
            continue
        msg = e.get("message", "")
        ts = e.get("timestamp_utc")
        if ts:
            out["last_ts"] = ts
        if msg == "rebalance signal":
            out["last_signal"] = e
        elif msg.startswith("broker:"):
            out["broker_mode"] = msg
        elif "loop alive" in msg:
            out["loop_alive"] = ts
        elif "SUBMISSION HALTED" in msg:
            out["last_halt"] = {"ts": ts, "msg": msg}
        elif "PROXY" in msg:
            out["proxy"] = msg
    return out


def build_state() -> dict:
    st = _read_state()
    log = _parse_log()
    sig = log.get("last_signal") or {}
    target = sig.get("target", {})  # symbol -> LONG/SHORT
    positions = []
    for sym, side in target.items():
        positions.append({"symbol": sym, "side": side})
    # next rebalance = 1st of next month (monthly cadence)
    now = datetime.now(timezone.utc)
    first_next = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    halted = bool(st.get("halted", False))
    peak = float(st.get("peak_equity", 10000.0))
    daily_start = float(st.get("daily_start_equity", peak))
    # daily loss vs budget (proxy; real equity feed would refine)
    daily_loss_pct = 0.0
    if daily_start:
        daily_loss_pct = max(0.0, (daily_start - peak) / daily_start * 100.0)
    return {
        "updated": now.isoformat(),
        "bot_alive": log.get("loop_alive") is not None,
        "last_heartbeat": log.get("loop_alive"),
        "broker_mode": log.get("broker_mode"),
        "data_mode": "PROXY multi-asset (GLD/SPY/QQQ/TLT/IEF/DBC)" if log.get("proxy") else "real CFD feed (pending MT5/REST)",
        "last_rebalance_month": st.get("last_rebalance_month"),
        "next_rebalance": first_next.strftime("%Y-%m-%d"),
        "halted": halted,
        "daily_loss_pct": round(daily_loss_pct, 2),
        "dd_budget_pct": _DD_BUDGET,
        "positions": positions,
        "sleeve2_pf": sig.get("sleeve2_pf"),
        "last_halt": log.get("last_halt"),
        "engine": ENGINE_STATS,
        "narrative": _narrative(positions, halted, daily_loss_pct),
    }


def _narrative(positions, halted, daily_loss_pct) -> str:
    if not positions:
        return ("No active signal this month yet. The bot rebalances monthly; "
                "on each rebalance it computes a time-series momentum (trend) "
                "signal across the multi-asset universe and sizes sleeves by risk parity.")
    longs = [p["symbol"] for p in positions if p["side"] == "LONG"]
    shorts = [p["symbol"] for p in positions if p["side"] == "SHORT"]
    parts = []
    if longs:
        parts.append("holding LONG " + ", ".join(longs))
    if shorts:
        parts.append("holding SHORT " + ", ".join(shorts))
    hold = "; ".join(parts)
    why = ("Why: Sleeve 2 is time-series momentum — go LONG assets in an uptrend, "
           "SHORT those in a downtrend (can short, unlike the equity sleeve). "
           "Sleeve 1 (vol-targeted equity momentum) is the core; risk parity "
           "weights Sleeve 2 heavier (68%) because it has lower volatility.")
    halt = (f" Daily loss guard: {daily_loss_pct:.2f}% used of {_DD_BUDGET:.1f}% budget"
            + (" — HALTED" if halted else " — within budget."))
    return f"Currently {hold}. {why}{halt}"


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>EdgeLabs — Multi-Component Bot Monitor</title>
<style>
  :root{
    --bg:#0f1419; --panel:#1a2230; --panel2:#222c3c; --ink:#e6edf3; --muted:#8b98a9;
    --long:#2ea043; --short:#f85149; --accent:#58a6ff; --warn:#d29922; --ok:#3fb950;
    --border:#2d3748; --mono:'SF Mono',Consolas,Menlo,monospace;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;}
  header{display:flex;align-items:center;justify-content:space-between;padding:14px 22px;border-bottom:1px solid var(--border);background:var(--panel);}
  header h1{font-size:16px;margin:0;letter-spacing:.3px;font-weight:600}
  .tag{font-size:12px;color:var(--muted);font-family:var(--mono)}
  .wrap{max-width:1180px;margin:0 auto;padding:20px;display:grid;grid-template-columns:1.4fr 1fr;gap:16px;}
  .panel{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:16px 18px;}
  .panel h2{margin:0 0 12px;font-size:13px;text-transform:uppercase;letter-spacing:1px;color:var(--muted);font-weight:600}
  .full{grid-column:1 / -1}
  .row{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--panel2);font-size:14px}
  .row:last-child{border-bottom:none}
  .k{color:var(--muted)} .v{font-family:var(--mono);font-weight:600}
  .status-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:middle}
  .on{background:var(--ok)} .off{background:var(--short)} .warn{background:var(--warn)}
  .pos-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;margin-top:4px}
  .pos{background:var(--panel2);border-radius:8px;padding:12px;text-align:center;border:1px solid var(--border)}
  .pos .sym{font-family:var(--mono);font-weight:700;font-size:15px}
  .pos .side{font-size:12px;font-weight:700;margin-top:4px}
  .long{color:var(--long)} .short{color:var(--short)}
  .narr{font-size:14px;line-height:1.55;color:var(--ink)}
  .metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
  .metric{background:var(--panel2);border-radius:8px;padding:12px;text-align:center}
  .metric .num{font-family:var(--mono);font-size:20px;font-weight:700}
  .metric .lbl{font-size:11px;color:var(--muted);margin-top:3px}
  .gauge{height:10px;background:var(--panel2);border-radius:6px;overflow:hidden;margin-top:8px}
  .gauge > div{height:100%;background:linear-gradient(90deg,var(--ok),var(--warn),var(--short))}
  .footer{color:var(--muted);font-size:11px;text-align:center;padding:14px}
  code{background:var(--panel2);padding:1px 5px;border-radius:4px;font-family:var(--mono);font-size:12px}
  .pill{display:inline-block;padding:2px 9px;border-radius:20px;font-size:11px;font-weight:600}
  .pill.sim{background:#3a2c12;color:var(--warn)} .pill.demo{background:#0d2f1a;color:var(--ok)}
  .pill.real{background:#0d2438;color:var(--accent)}
</style>
</head>
<body>
<header>
  <h1>EdgeLabs — Multi-Component Bot Monitor</h1>
  <span class="tag" id="updated">—</span>
</header>

<div class="wrap">
  <!-- REASONING LAYER (the key panel) -->
  <div class="panel full">
    <h2>What the bot is thinking</h2>
    <div class="narr" id="narrative">Loading…</div>
    <div class="pos-grid" id="positions" style="margin-top:14px"></div>
  </div>

  <!-- Status -->
  <div class="panel">
    <h2>Bot status</h2>
    <div class="row"><span class="k">Alive</span><span class="v" id="alive">—</span></div>
    <div class="row"><span class="k">Last heartbeat</span><span class="v" id="hb">—</span></div>
    <div class="row"><span class="k">Broker mode</span><span class="v"><span id="broker" class="pill sim">—</span></span></div>
    <div class="row"><span class="k">Data feed</span><span class="v" id="data">—</span></div>
    <div class="row"><span class="k">Last rebalance</span><span class="v" id="lrb">—</span></div>
    <div class="row"><span class="k">Next rebalance</span><span class="v" id="nrb">—</span></div>
    <div class="row"><span class="k">Last action</span><span class="v" id="halt">—</span></div>
  </div>

  <!-- 4% halt -->
  <div class="panel">
    <h2>Daily loss guard (4% halt)</h2>
    <div class="row"><span class="k">Status</span><span class="v" id="haltstat">—</span></div>
    <div class="row"><span class="k">Used today</span><span class="v" id="ddused">—</span></div>
    <div class="row"><span class="k">Budget</span><span class="v" id="ddbudget">4.0%</span></div>
    <div class="gauge"><div id="ddbar" style="width:0%"></div></div>
    <div class="narr" style="margin-top:10px;color:var(--muted);font-size:12px">
      If realized loss hits 4% in a day, the bot HALTS all new orders until the next session.
    </div>
  </div>

  <!-- Engine stats -->
  <div class="panel full">
    <h2>Combined engine (5y honest backtest)</h2>
    <div class="metrics">
      <div class="metric"><div class="num" id="m_sharpe">—</div><div class="lbl">Sharpe</div></div>
      <div class="metric"><div class="num" id="m_pf">—</div><div class="lbl">Profit Factor</div></div>
      <div class="metric"><div class="num" id="m_dd">—</div><div class="lbl">Max DD %</div></div>
      <div class="metric"><div class="num" id="m_ret">—</div><div class="lbl">Return %</div></div>
    </div>
    <div class="row" style="margin-top:12px"><span class="k">Risk:Reward</span><span class="v" id="m_rr">—</span></div>
    <div class="row"><span class="k">Sleeve 1 (VT-H5)</span><span class="v" id="m_s1">—</span></div>
    <div class="row"><span class="k">Sleeve 2 (TSMOM)</span><span class="v" id="m_s2">—</span></div>
    <div class="row"><span class="k">Risk-parity weights</span><span class="v" id="m_w">—</span></div>
  </div>
</div>

<div class="footer">
  Desktop monitor · localhost only · read-only · no orders placed without <code>#D#</code> + <code>EDGELAB_DEMO_FILL=1</code>
</div>

<script>
function esc(s){return (s==null?'':String(s)).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
async function refresh(){
  try{
    const r = await fetch('/api/state'); const d = await r.json();
    document.getElementById('updated').textContent = 'updated ' + new Date(d.updated).toLocaleTimeString();
    document.getElementById('alive').innerHTML = d.bot_alive
      ? '<span class="status-dot on"></span>RUNNING' : '<span class="status-dot off"></span>DOWN';
    document.getElementById('hb').textContent = d.last_heartbeat ? d.last_heartbeat.slice(11,19) + ' UTC' : '—';
    const bm = d.broker_mode || '';
    const pill = document.getElementById('broker');
    if(/SIMULATED/.test(bm)){pill.className='pill sim';pill.textContent='SIMULATED';}
    else if(/DEMO/.test(bm)){pill.className='pill demo';pill.textContent='DEMO';}
    else if(/real/i.test(bm)){pill.className='pill real';pill.textContent='REAL';}
    else {pill.className='pill sim';pill.textContent='SIMULATED';}
    document.getElementById('data').textContent = d.data_mode || '—';
    document.getElementById('lrb').textContent = d.last_rebalance_month || '—';
    document.getElementById('nrb').textContent = d.next_rebalance || '—';
    const halt = d.last_halt ? d.last_halt.msg : 'no fills yet (signal-only)';
    document.getElementById('halt').textContent = halt.slice(0,60) + (halt.length>60?'…':'');
    document.getElementById('narrative').textContent = d.narrative || '—';
    const pg = document.getElementById('positions'); pg.innerHTML='';
    (d.positions||[]).forEach(p=>{
      const div=document.createElement('div'); div.className='pos';
      div.innerHTML='<div class="sym">'+esc(p.symbol)+'</div><div class="side '+(p.side==='LONG'?'long':'short')+'">'+esc(p.side)+'</div>';
      pg.appendChild(div);
    });
    if(!d.positions||!d.positions.length) pg.innerHTML='<span class="k">No open positions this month (rebalances monthly).</span>';
    const hs=document.getElementById('haltstat');
    if(d.halted){hs.innerHTML='<span class="status-dot off"></span>HALTED';}
    else {hs.innerHTML='<span class="status-dot on"></span>ARMED';}
    document.getElementById('ddused').textContent = (d.daily_loss_pct||0).toFixed(2)+'%';
    document.getElementById('ddbar').style.width = Math.min(100,(d.daily_loss_pct||0)/(d.dd_budget_pct||4)*100)+'%';
    const e=d.engine||{};
    document.getElementById('m_sharpe').textContent=e.sharpe??'—';
    document.getElementById('m_pf').textContent=e.profit_factor??'—';
    document.getElementById('m_dd').textContent=(e.max_dd_pct??'—')+'%';
    document.getElementById('m_ret').textContent=(e.total_return_pct??'—')+'%';
    document.getElementById('m_rr').textContent=e.rr??'—';
    document.getElementById('m_s1').textContent=e.sleeve1?e.sleeve1.name+' · DD '+e.sleeve1.dd+'% · Sharpe '+e.sleeve1.sharpe:'';
    document.getElementById('m_s2').textContent=e.sleeve2?e.sleeve2.name+' · DD '+e.sleeve2.dd+'% · Sharpe '+e.sleeve2.sharpe:'';
    document.getElementById('m_w').textContent=e.weights?('Sleeve1 '+e.weights.Sleeve1+' / Sleeve2 '+e.weights.Sleeve2):'';
  }catch(err){ /* keep last good render */ }
}
refresh(); setInterval(refresh, 5000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/api/state":
            self._send(200, json.dumps(build_state()).encode())
            return
        if self.path == "/api/health":
            self._send(200, json.dumps({"ok": True}).encode())
            return
        self._send(404, b'{"error":"not found"}')

    def log_message(self, *a):
        pass


def main(port: int = 8765):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"EdgeLabs monitor: http://127.0.0.1:{port}  (localhost only, read-only)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main(int(os.environ.get("DASH_PORT", "8765")))
