#!/usr/bin/env python3
"""Plot logged PMS9003M readings to a PNG.

Usage:
    python3 plot.py [--db pm25.db] [--out pm25.png] [--hours 24]

Requires matplotlib:  pip install matplotlib   (or apt install python3-matplotlib)
"""

import argparse
import sqlite3
from datetime import datetime, timedelta, timezone


def main() -> None:
    ap = argparse.ArgumentParser(description="Plot PM readings to PNG")
    ap.add_argument("--db", default="pm25.db")
    ap.add_argument("--out", default="pm25.png")
    ap.add_argument("--hours", type=float, default=24.0,
                    help="window to plot, in hours (default 24)")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")  # headless: no display needed on the Pi
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    since = (datetime.now(timezone.utc) - timedelta(hours=args.hours)
             ).isoformat(timespec="seconds")
    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        "SELECT ts, pm1_0, pm2_5, pm10 FROM readings "
        "WHERE ts >= ? ORDER BY ts ASC",
        (since,),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"no rows in the last {args.hours:g}h -- nothing to plot")
        return

    times = [datetime.fromisoformat(r[0]) for r in rows]
    pm1 = [r[1] for r in rows]
    pm25 = [r[2] for r in rows]
    pm10 = [r[3] for r in rows]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(times, pm25, label="PM2.5", color="#d62728", linewidth=1.8)
    ax.plot(times, pm10, label="PM10", color="#1f77b4", linewidth=1.2)
    ax.plot(times, pm1, label="PM1.0", color="#2ca02c", linewidth=1.0, alpha=0.8)

    # WHO 24h PM2.5 guideline reference line.
    ax.axhline(15, color="grey", linestyle="--", linewidth=0.8,
               label="WHO 24h PM2.5 (15)")

    ax.set_title(f"Particulate matter — last {args.hours:g}h (UTC)")
    ax.set_ylabel("µg/m³")
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(args.out, dpi=110)
    print(f"wrote {args.out} ({len(rows)} points)")


if __name__ == "__main__":
    main()
