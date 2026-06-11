#!/usr/bin/env python3
"""Sample the PMS9003M and log averaged readings to SQLite.

Reads frames continuously, averages them over a fixed window, and writes
one row per window with a timestamp. Averaging smooths the per-second
jitter that's normal for optical PM sensors.

Usage:
    python3 logger.py [--port /dev/serial0] [--db pm25.db]
                      [--window 60] [--print]
"""

import argparse
import sqlite3
import time
from datetime import datetime, timezone

from pms9003m import open_serial, read_valid_frame

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    ts        TEXT    NOT NULL,   -- ISO-8601 UTC, end of averaging window
    samples   INTEGER NOT NULL,   -- frames averaged into this row
    pm1_0     REAL    NOT NULL,   -- atmospheric, ug/m3
    pm2_5     REAL    NOT NULL,
    pm10      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings(ts);
"""


def init_db(path: str) -> sqlite3.Connection:
    # timeout: wait (don't error) if another connection holds a lock.
    conn = sqlite3.connect(path, timeout=5.0)
    # WAL lets readers and the single writer run concurrently without blocking.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def insert(conn: sqlite3.Connection, ts: str, n: int,
           pm1_0: float, pm2_5: float, pm10: float) -> None:
    conn.execute(
        "INSERT INTO readings (ts, samples, pm1_0, pm2_5, pm10) "
        "VALUES (?, ?, ?, ?, ?)",
        (ts, n, pm1_0, pm2_5, pm10),
    )
    conn.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="Log PMS9003M readings to SQLite")
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--db", default="pm25.db")
    ap.add_argument("--window", type=float, default=60.0,
                    help="averaging window in seconds (default 60)")
    ap.add_argument("--print", dest="echo", action="store_true",
                    help="also print each logged row")
    args = ap.parse_args()

    ser = open_serial(args.port)
    conn = init_db(args.db)
    print(f"Logging PMS9003M -> {args.db}, {args.window:.0f}s windows. Ctrl-C to stop.")

    s1 = s25 = s10 = 0.0
    n = 0
    window_start = time.monotonic()

    try:
        while True:
            r = read_valid_frame(ser)
            if r is not None:
                s1 += r.pm1_0
                s25 += r.pm2_5
                s10 += r.pm10
                n += 1

            if time.monotonic() - window_start >= args.window:
                ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
                if n > 0:
                    pm1_0, pm2_5, pm10 = s1 / n, s25 / n, s10 / n
                    insert(conn, ts, n, pm1_0, pm2_5, pm10)
                    if args.echo:
                        print(f"{ts}  n={n:<3}  "
                              f"PM1.0={pm1_0:5.1f}  PM2.5={pm2_5:5.1f}  "
                              f"PM10={pm10:5.1f} ug/m3")
                else:
                    print(f"{ts}  no valid frames this window "
                          f"(check wiring/power)")
                s1 = s25 = s10 = 0.0
                n = 0
                window_start = time.monotonic()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        conn.close()
        ser.close()


if __name__ == "__main__":
    main()
