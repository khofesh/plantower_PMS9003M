# PMS9003M → Raspberry Pi 4 (DietPi) PM2.5 logger

Reads the Plantower **PMS9003M** particulate sensor over the Pi's GPIO UART,
averages the readings, and logs them to a local SQLite database. No broker,
no microcontroller — the sensor talks straight to the idle Pi.

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

Log averaged readings to SQLite (60s windows by default):

```bash
python3 logger.py --print
```

Inspect what's been logged:

```bash
python3 query.py --last 30
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
| 28–29 | reserved                                         |
| 30–31 | checksum = sum of bytes 0–29                     |

The **atmospheric** values (bytes 10–15) are what `logger.py` records as
µg/m³. Note a freshly powered sensor needs ~30s of fan runtime to settle.

## Data schema (`readings` table)

| column  | meaning                                |
| ------- | -------------------------------------- |
| ts      | ISO-8601 UTC, end of averaging window  |
| samples | number of frames averaged into the row |
| pm1_0   | mean PM1.0 (µg/m³, atmospheric)        |
| pm2_5   | mean PM2.5                             |
| pm10    | mean PM10                              |
