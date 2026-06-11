#!/usr/bin/env python3
"""Tiny web dashboard for logged PMS9003M data.

Serves a single page that charts PM1.0/PM2.5/PM10 history, auto-refreshing.
Pure standard library on the server side; the page uses Chart.js from a CDN,
so the *browser* (not the Pi) needs internet to load the chart library.

Usage:
    python3 dashboard.py [--db pm25.db] [--host 0.0.0.0] [--port 8000]

Then browse to http://<pi-ip>:8000/
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

DB_PATH = "pm25.db"

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PM2.5 — PMS9003M</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  body { font-family: system-ui, sans-serif; margin: 1.5rem; background:#fafafa; color:#222; }
  h1 { font-size: 1.2rem; }
  .controls { margin: .5rem 0 1rem; }
  .cards { display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:1rem; }
  .card { background:#fff; border:1px solid #e3e3e3; border-radius:10px;
          padding:.8rem 1.1rem; min-width:120px; }
  .card .v { font-size:1.7rem; font-weight:600; }
  .card .l { font-size:.8rem; color:#777; }
  #wrap { background:#fff; border:1px solid #e3e3e3; border-radius:10px; padding:1rem; }
  select { padding:.3rem; }
</style>
</head>
<body>
  <h1>Particulate matter — PMS9003M</h1>
  <div class="cards">
    <div class="card"><div class="v" id="cur25">–</div><div class="l">PM2.5 µg/m³ (latest)</div></div>
    <div class="card"><div class="v" id="cur10">–</div><div class="l">PM10 µg/m³ (latest)</div></div>
    <div class="card"><div class="v" id="cur1">–</div><div class="l">PM1.0 µg/m³ (latest)</div></div>
    <div class="card"><div class="v" id="updated">–</div><div class="l">last reading (UTC)</div></div>
  </div>
  <div class="controls">
    Window:
    <select id="hours">
      <option value="1">1 h</option>
      <option value="6">6 h</option>
      <option value="24" selected>24 h</option>
      <option value="168">7 d</option>
    </select>
  </div>
  <div id="wrap"><canvas id="chart" height="110"></canvas></div>
<script>
const ctx = document.getElementById('chart');
const chart = new Chart(ctx, {
  type: 'line',
  data: { labels: [], datasets: [
    { label:'PM2.5', data:[], borderColor:'#d62728', borderWidth:2, pointRadius:0, tension:.2 },
    { label:'PM10',  data:[], borderColor:'#1f77b4', borderWidth:1.5, pointRadius:0, tension:.2 },
    { label:'PM1.0', data:[], borderColor:'#2ca02c', borderWidth:1.2, pointRadius:0, tension:.2 },
  ]},
  options: { responsive:true, interaction:{mode:'index',intersect:false},
    scales:{ y:{ beginAtZero:true, title:{display:true,text:'µg/m³'} } } }
});

async function refresh() {
  const h = document.getElementById('hours').value;
  const r = await fetch('/data.json?hours=' + h);
  const j = await r.json();
  chart.data.labels = j.t;
  chart.data.datasets[0].data = j.pm2_5;
  chart.data.datasets[1].data = j.pm10;
  chart.data.datasets[2].data = j.pm1_0;
  chart.update();
  if (j.t.length) {
    const i = j.t.length - 1;
    document.getElementById('cur25').textContent = j.pm2_5[i].toFixed(1);
    document.getElementById('cur10').textContent = j.pm10[i].toFixed(1);
    document.getElementById('cur1').textContent  = j.pm1_0[i].toFixed(1);
    document.getElementById('updated').textContent = j.t[i];
  }
}
document.getElementById('hours').addEventListener('change', refresh);
refresh();
setInterval(refresh, 30000);  // auto-refresh every 30s
</script>
</body>
</html>
"""


def query_data(hours: float) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)
             ).isoformat(timespec="seconds")
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    rows = conn.execute(
        "SELECT ts, pm1_0, pm2_5, pm10 FROM readings "
        "WHERE ts >= ? ORDER BY ts ASC",
        (since,),
    ).fetchall()
    conn.close()
    return {
        "t": [r[0].replace("T", " ").replace("+00:00", "") for r in rows],
        "pm1_0": [r[1] for r in rows],
        "pm2_5": [r[2] for r in rows],
        "pm10": [r[3] for r in rows],
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif parsed.path == "/data.json":
            try:
                hours = float(parse_qs(parsed.query).get("hours", ["24"])[0])
            except ValueError:
                hours = 24.0
            body = json.dumps(query_data(hours)).encode()
            self._send(200, body, "application/json")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args) -> None:  # quieter console
        pass


def main() -> None:
    global DB_PATH
    ap = argparse.ArgumentParser(description="PM2.5 web dashboard")
    ap.add_argument("--db", default="pm25.db")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    DB_PATH = args.db

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dashboard on http://{args.host}:{args.port}/  (db: {DB_PATH})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        server.shutdown()


if __name__ == "__main__":
    main()
