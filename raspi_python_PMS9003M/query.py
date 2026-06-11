#!/usr/bin/env python3
"""Quick look at logged PMS9003M data.

Usage:
    python3 query.py [--db pm25.db] [--last 20]
"""

import argparse
import sqlite3


def main() -> None:
    ap = argparse.ArgumentParser(description="Show recent PM readings")
    ap.add_argument("--db", default="pm25.db")
    ap.add_argument("--last", type=int, default=20, help="rows to show")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    rows = conn.execute(
        "SELECT ts, samples, pm1_0, pm2_5, pm10 FROM readings "
        "ORDER BY ts DESC LIMIT ?",
        (args.last,),
    ).fetchall()
    conn.close()

    print(f"{'timestamp (UTC)':<22}{'n':>4}  {'PM1.0':>6}{'PM2.5':>7}{'PM10':>7}")
    for ts, n, pm1, pm25, pm10 in reversed(rows):
        print(f"{ts:<22}{n:>4}  {pm1:6.1f}{pm25:7.1f}{pm10:7.1f}")


if __name__ == "__main__":
    main()
