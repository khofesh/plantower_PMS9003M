# PMS9003M → Raspberry Pi 4 (DietPi) PM2.5 logger

Reads the Plantower **PMS9003M** particulate sensor over the Pi's GPIO UART,
averages the readings, and logs them to a local SQLite database. No broker,
no microcontroller — the sensor talks straight to the idle Pi.

All twelve sensor fields are stored (the three atmospheric PM concentrations,
the three CF=1 concentrations, and the six particle-size counts), so the data
can be turned into a verdict: `aqi.py` computes the **US EPA Air Quality Index**
from the concentrations and guesses the particle **source** from the size
distribution (fine/sub-micron → combustion/smoke; a coarse tail → dust/pollen).
`query.py` and the dashboard surface that verdict directly.

## Hardware

| PMS9003M         | Raspberry Pi 4                                     |
| ---------------- | -------------------------------------------------- |
| VCC (5V)         | 5V (pin 2/4)                                       |
| GND              | GND (pin 6)                                        |
| TXD (3.3V logic) | RXD / GPIO15 (pin 10)                              |
| RXD              | TXD / GPIO14 (pin 8) — optional, only for commands |

The sensor's data line is 3.3V logic, so sensor-TX → Pi-RX is safe directly.

## One-time setup on DietPi

1. Enable the UART and free it from the login console:

   ```bash
   dietpi-config
   ```

   → **Advanced Options** → **Serial/UART** → enable the GPIO UART, and
   disable the serial login console.

2. Confirm the console getty isn't holding the port:

   ```bash
   sudo systemctl disable --now serial-getty@ttyAMA0.service
   sudo systemctl disable --now serial-getty@serial0.service
   ```

3. Verify raw frames arrive (look for `42 4d` / `BM` headers):

   ```bash
   sudo xxd /dev/serial0 | head
   ```

4. Install the dependency:
   ```bash
   sudo apt install -y python3-serial   # or: pip install -r requirements.txt
   ```

## Usage

Live print (sanity check):

```bash
python3 pms9003m.py
```

Log averaged readings to SQLite (60s windows, after a 30s sensor warm-up that
is discarded):

```bash
python3 logger.py --print
python3 logger.py --window 60 --warmup 30   # explicit defaults
```

Inspect what's been logged, with an AQI + source verdict for the latest row:

```bash
python3 query.py --last 30
```

```
Latest (2026-06-11T10:00:00+00:00):
  health : AQI 153 (Unhealthy), driven by PM2.5 -- everyone may begin to feel effects
  source : fine-dominated, ~no coarse particles -- likely combustion/smoke (...)
  detail : PM2.5/PM10=0.81, coarse(>=2.5um) share=0.231%
```

The scoring lives in `aqi.py` and is reusable on its own:

```bash
python3 -c "import aqi; print(aqi.summarize(58, 72, counts=(3031,2832,628,7,0,0)))"
```

## Viewing & exporting data

**CSV export** (whole table, or just the last N hours):

```bash
python3 export.py --out pm25.csv            # everything
python3 export.py --hours 24 --out today.csv
python3 export.py --hours 6 --out -          # to stdout
```

**PNG plot** (needs matplotlib: `sudo apt install -y python3-matplotlib`):

```bash
python3 plot.py --hours 24 --out pm25.png
```

**Web dashboard** — auto-refreshing chart in the browser, pure stdlib server:

```bash
python3 dashboard.py --port 8000
# then open http://<pi-ip>:8000/
```

Pick the window (1 h / 6 h / 24 h / 7 d) from the dropdown; it refreshes every
30 s. The page pulls Chart.js from a CDN, so the **browser** needs internet —
the Pi itself does not. To run it on boot, copy `pms9003m-dashboard.service`
the same way as the logger service below.

## Run on boot (systemd)

Edit `pms9003m-logger.service` (user + paths), then:

```bash
sudo cp pms9003m-logger.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pms9003m-logger.service
journalctl -u pms9003m-logger -f
```

## Frame format (reference)

32-byte frame, big-endian, 9600 baud:

| Bytes | Field                                            |
| ----- | ------------------------------------------------ |
| 0–1   | header `0x42 0x4D`                               |
| 2–3   | frame length (`0x001C`)                          |
| 4–9   | PM1.0 / PM2.5 / PM10, CF=1 (standard particle)   |
| 10–15 | PM1.0 / PM2.5 / PM10, **atmospheric** ← reported |
| 16–27 | particle counts for 0.3/0.5/1.0/2.5/5.0/10 µm    |
| 28    | version                                          |
| 29    | error code                                       |
| 30–31 | checksum = sum of bytes 0–29                     |

The **atmospheric** values (bytes 10–15) are what `logger.py` records as
µg/m³. Note a freshly powered sensor needs ~30s of fan runtime to settle.

## Data schema (`readings` table)

| column                           | meaning                                         |
| -------------------------------- | ----------------------------------------------- |
| ts                               | ISO-8601 UTC, end of averaging window           |
| samples                          | number of frames averaged into the row          |
| pm1_0 / pm2_5 / pm10             | mean PM (µg/m³, **atmospheric** — report these) |
| pm1_0_cf1 / pm2_5_cf1 / pm10_cf1 | mean PM (µg/m³, CF=1 standard particle)         |
| n0_3 … n10                       | mean particle counts per 0.1 L (≥ named size)   |

All columns are stored as the per-window mean. The CF=1 trio and the counts are
what `aqi.py` needs for the source classification, so they are kept even though
only the atmospheric PM is "reported" for health.

> **Schema change:** earlier versions stored only `pm1_0/pm2_5/pm10`. A database
> created by the old logger lacks the new columns; start a fresh `pm25.db` (or
> `ALTER TABLE` to add them) when upgrading.

## Concurrency & data safety

It is safe to **read and write the database at the same time** — e.g. the
logger appending a row while the dashboard, `query.py`, or `export.py` read it.
This setup is the normal case, and it is handled deliberately.

### The model: one writer, many readers

SQLite allows **at most one writer but any number of concurrent readers**.

- `logger.py` is the **single writer**. Run only one instance per database
  file. Two loggers on the same `pm25.db` is the one thing to avoid.
- `dashboard.py`, `query.py`, `export.py`, `plot.py` are **read-only**. Run as
  many of them as you like, whenever you like, while the logger runs.

### What makes concurrent access safe here

`logger.py` configures the database on startup (`init_db`):

| Setting                         | Effect                                                                                                                                    |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `PRAGMA journal_mode=WAL`       | Write-Ahead Logging: readers and the writer no longer block each other. A reader sees a consistent snapshot while a write is in progress. |
| `PRAGMA synchronous=NORMAL`     | Safe under WAL, with far fewer fsyncs — easier on the Pi's SD card.                                                                       |
| `timeout=5.0` (all connections) | If a lock is ever briefly held, callers **wait up to 5 s** instead of raising `database is locked`.                                       |

WAL mode is a persistent property of the database file, so once the logger has
created it, every reader automatically benefits — no per-reader configuration
needed beyond the busy timeout, which all scripts already set.

### WAL sidecar files

In WAL mode SQLite keeps two extra files next to the database:

```
pm25.db        pm25.db-wal        pm25.db-shm
```

This is normal. Leave them in place; they are part of the database. If you copy
or back up the DB, either stop the logger first or copy all three together (or
use `sqlite3 pm25.db ".backup backup.db"`, which is safe while running).

### The serial port is _not_ shared

Separately from the database: only **one process may open `/dev/serial0`**.
The logger owns the sensor; the dashboard and the other tools never touch the
port — they only read the database. Do not run a second program that opens the
UART while the logger is running, or the two will steal each other's bytes and
both will see corrupt frames.
