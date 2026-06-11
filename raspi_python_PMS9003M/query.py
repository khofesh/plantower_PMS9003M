#!/usr/bin/env python3
"""Quick look at logged PMS9003M data, with an AQI + source verdict.

Usage:
    python3 query.py [--db pm25.db] [--last 20]
"""

import argparse
import sqlite3

from aqi import aqi_from_pm, classify_source


def main() -> None:
    ap = argparse.ArgumentParser(description="Show recent PM readings")
    ap.add_argument("--db", default="pm25.db")
    ap.add_argument("--last", type=int, default=20, help="rows to show")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db, timeout=5.0)
    rows = conn.execute(
        "SELECT ts, samples, pm1_0, pm2_5, pm10, "
        "n0_3, n0_5, n1_0, n2_5, n5_0, n10 FROM readings "
        "ORDER BY ts DESC LIMIT ?",
        (args.last,),
    ).fetchall()
    conn.close()

    if not rows:
        print("no rows yet")
        return

    print(f"{'timestamp (UTC)':<22}{'n':>4}  {'PM1.0':>6}{'PM2.5':>7}{'PM10':>7}"
          f"  {'AQI':>4}  category")
    for ts, n, pm1, pm25, pm10, *_ in reversed(rows):
        a = aqi_from_pm(pm25, pm10)
        aqi = "-" if a.aqi is None else str(a.aqi)
        print(f"{ts:<22}{n:>4}  {pm1:6.1f}{pm25:7.1f}{pm10:7.1f}"
              f"  {aqi:>4}  {a.category}")

    # Verdict for the most recent row, using the particle counts too.
    latest = rows[0]
    ts, _, pm1, pm25, pm10, n0_3, n0_5, n1_0, n2_5, n5_0, n10 = latest
    a = aqi_from_pm(pm25, pm10)
    s = classify_source(n0_3, n0_5, n1_0, n2_5, n5_0, n10, pm2_5=pm25, pm10=pm10)
    aqi_txt = a.category if a.aqi is None else f"AQI {a.aqi} ({a.category})"
    print(f"\nLatest ({ts}):")
    print(f"  health : {aqi_txt}, driven by {a.dominant} -- {a.advice}")
    print(f"  source : {s.label}")
    if s.pm_ratio is not None:
        print(f"  detail : PM2.5/PM10={s.pm_ratio:.2f}, "
              f"coarse(>=2.5um) share={s.coarse_count_frac:.3%}")


if __name__ == "__main__":
    main()
