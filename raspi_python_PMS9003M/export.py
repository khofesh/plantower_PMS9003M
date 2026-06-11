#!/usr/bin/env python3
"""Export logged PMS9003M readings to CSV.

Usage:
    python3 export.py [--db pm25.db] [--out pm25.csv] [--hours N]
    python3 export.py --hours 24 --out today.csv

Without --hours, exports the whole table. Writes to stdout if --out is "-".
"""

import argparse
import csv
import sqlite3
import sys
from datetime import datetime, timedelta, timezone


def main() -> None:
    ap = argparse.ArgumentParser(description="Export PM readings to CSV")
    ap.add_argument("--db", default="pm25.db")
    ap.add_argument("--out", default="pm25.csv", help='output file, or "-" for stdout')
    ap.add_argument("--hours", type=float, default=None,
                    help="only the last N hours (default: all)")
    args = ap.parse_args()

    cols = ("ts, samples, pm1_0, pm2_5, pm10, pm1_0_cf1, pm2_5_cf1, pm10_cf1, "
            "n0_3, n0_5, n1_0, n2_5, n5_0, n10")
    query = f"SELECT {cols} FROM readings"
    params: tuple = ()
    if args.hours is not None:
        since = (datetime.now(timezone.utc) - timedelta(hours=args.hours)
                 ).isoformat(timespec="seconds")
        query += " WHERE ts >= ?"
        params = (since,)
    query += " ORDER BY ts ASC"

    conn = sqlite3.connect(args.db, timeout=5.0)
    rows = conn.execute(query, params).fetchall()
    conn.close()

    out = sys.stdout if args.out == "-" else open(args.out, "w", newline="")
    try:
        w = csv.writer(out)
        w.writerow(["ts", "samples", "pm1_0", "pm2_5", "pm10",
                    "pm1_0_cf1", "pm2_5_cf1", "pm10_cf1",
                    "n0_3", "n0_5", "n1_0", "n2_5", "n5_0", "n10"])
        w.writerows(rows)
    finally:
        if out is not sys.stdout:
            out.close()
            print(f"wrote {len(rows)} rows to {args.out}")


if __name__ == "__main__":
    main()
