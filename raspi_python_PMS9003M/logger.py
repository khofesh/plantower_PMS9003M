#!/usr/bin/env python3
"""Sample the PMS9003M and log averaged readings to SQLite.

Reads frames continuously, averages every field over a fixed window, and
writes one row per window with a timestamp. Averaging smooths the per-second
jitter that's normal for optical PM sensors.

All twelve sensor fields are stored -- not just the three PM concentrations --
so the size distribution (the particle counts) survives for later source
analysis (see aqi.py). A short warm-up period is discarded after start-up,
because the fan/laser need a few seconds to stabilise.

Usage:
    python3 logger.py [--port /dev/serial0] [--db pm25.db]
                      [--window 60] [--warmup 30] [--print]
"""

import argparse
import sqlite3
import time
from datetime import datetime, timezone

from pms9003m import open_serial, read_valid_frame

# Atmospheric PM, CF=1 PM, the six particle counts, plus the housekeeping bytes.
SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts         TEXT    NOT NULL,   -- ISO-8601 UTC, end of averaging window
    samples    INTEGER NOT NULL,   -- frames averaged into this row
    -- atmospheric environment, ug/m3 (report these)
    pm1_0      REAL    NOT NULL,
    pm2_5      REAL    NOT NULL,
    pm10       REAL    NOT NULL,
    -- standard particle (CF=1), ug/m3
    pm1_0_cf1  REAL    NOT NULL,
    pm2_5_cf1  REAL    NOT NULL,
    pm10_cf1   REAL    NOT NULL,
    -- particle counts per 0.1 L of air (cumulative: >= the named size)
    n0_3       REAL    NOT NULL,
    n0_5       REAL    NOT NULL,
    n1_0       REAL    NOT NULL,
    n2_5       REAL    NOT NULL,
    n5_0       REAL    NOT NULL,
    n10        REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(ts);
"""

# Every numeric field we average, in DB-column order.
FIELDS = ("pm1_0", "pm2_5", "pm10",
          "pm1_0_cf1", "pm2_5_cf1", "pm10_cf1",
          "n0_3", "n0_5", "n1_0", "n2_5", "n5_0", "n10")


def init_db(path: str) -> sqlite3.Connection:
    # timeout: wait (don't error) if another connection holds a lock.
    conn = sqlite3.connect(path, timeout=5.0)
    # WAL lets readers and the single writer run concurrently without blocking.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert(conn: sqlite3.Connection, ts: str, n: int, avg: dict) -> None:
    cols = "ts, samples, " + ", ".join(FIELDS)
    placeholders = ", ".join(["?"] * (2 + len(FIELDS)))
    values = [ts, n] + [avg[f] for f in FIELDS]
    conn.execute(f"INSERT INTO readings ({cols}) VALUES ({placeholders})", values)
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="Log PMS9003M readings to SQLite")
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--db", default="pm25.db")
    ap.add_argument("--window", type=float, default=60.0,
                    help="averaging window in seconds (default 60)")
    ap.add_argument("--warmup", type=float, default=30.0,
                    help="seconds of readings to discard after start (default 30)")
    ap.add_argument("--print", dest="echo", action="store_true",
                    help="also print each logged row")
    args = ap.parse_args()

    ser = open_serial(args.port)
    conn = init_db(args.db)
    print(f"Logging PMS9003M -> {args.db}, {args.window:.0f}s windows. Ctrl-C to stop.")

    # Discard the warm-up period: read and throw away until it elapses.
    if args.warmup > 0:
        print(f"warming up for {args.warmup:.0f}s...")
        warm_start = time.monotonic()
        while time.monotonic() - warm_start < args.warmup:
            read_valid_frame(ser)

    totals = {f: 0.0 for f in FIELDS}
    n = 0
    window_start = time.monotonic()

    try:
        while True:
            r = read_valid_frame(ser)
            if r is not None:
                for f in FIELDS:
                    totals[f] += getattr(r, f)
                n += 1

            if time.monotonic() - window_start >= args.window:
                ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if n > 0:
                    avg = {f: totals[f] / n for f in FIELDS}
                    insert(conn, ts, n, avg)
                    if args.echo:
                        print(f"{ts}  n={n:<3}  "
                              f"PM1.0={avg['pm1_0']:5.1f}  "
                              f"PM2.5={avg['pm2_5']:5.1f}  "
                              f"PM10={avg['pm10']:5.1f} ug/m3")
                else:
                    print(f"{ts}  no valid frames this window "
                          f"(check wiring/power)")
                totals = {f: 0.0 for f in FIELDS}
                n = 0
                window_start = time.monotonic()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        conn.close()
        ser.close()


if __name__ == "__main__":
    main()
