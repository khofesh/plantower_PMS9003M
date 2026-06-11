# PM2.5 Air Quality Monitor — STM32H533RE

Firmware for the **NUCLEO-H533RE** that reads particulate-matter data from a
**Plantower PMS9003M** sensor. The sensor can be read two ways:

1. **Native UART** (recommended) — talk to the PMS9003M directly over its
   9600 baud serial protocol.
2. **DFRobot Gravity I2C adapter** (`SEN0460`) — a small board that bridges the
   PMS9003M's UART to I2C, read with the included `DFRobot_AirSensor_*` driver.

> **Note:** During bring-up the DFRobot I2C adapter on this bench was found to be
> dead (never ACKs on the bus, while other I2C devices enumerate fine). The bare
> PMS9003M was proven working over UART. If your I2C path returns all-zeros, see
> [Troubleshooting](#troubleshooting).

## Hardware

| Item | Detail |
|------|--------|
| MCU board | NUCLEO-H533RE (STM32H533RET6) |
| Sensor | Plantower PMS9003M (laser PM sensor, native UART) |
| I2C adapter (optional) | DFRobot Gravity Air Quality sensor board (SEN0460) |
| Console | ST-Link Virtual COM Port @ **115200 8N1** (USART2, PA2/PA3) |

### Wiring — native UART (recommended)

The PMS9003M streams data automatically; only its TX line is needed.

| PMS9003M pin | Connect to | Notes |
|--------------|-----------|-------|
| VCC | **5 V** | fan + laser require 5 V |
| GND | GND | common ground with the Nucleo |
| TX  | **PA10** | USART1_RX (AF7) |
| RX  | PA9 (optional) | USART1_TX, only for commands |
| SET / RESET | leave unconnected | idle high = active mode |

### Wiring — DFRobot I2C adapter (optional)

| Adapter pin | Connect to | Notes |
|-------------|-----------|-------|
| VCC | 3.3–5 V | |
| GND | GND | |
| SCL | **PB10** | I2C2_SCL (AF4) |
| SDA | **PB12** | I2C2_SDA (AF4) |

I2C requires pull-ups to 3V3. The MCU's internal pull-ups are enabled in
`stm32h5xx_hal_msp.c` (`GPIO_PULLUP`); for reliable operation add external
**4.7 kΩ** resistors on SDA and SCL. Default 7-bit address is **0x19**.

## Behaviour

On boot the firmware (`Core/Src/main.c`) prints to the console:

1. A banner.
2. An **I2C bus scan** listing every 7-bit address that ACKs.
3. Whether the DFRobot I2C adapter answered at `0x19` (non-fatal if absent).
4. A continuous loop, once per second:
   - **PMS9003M over UART** — reads one 32-byte frame, validates the checksum,
     and prints PM1.0 / PM2.5 / PM10 (atmospheric).
   - **DFRobot over I2C** — *only if the adapter was detected* — prints all six
     concentrations and the six particle counts.

Example output:

```
=== PMS9003M / DFRobot Air Quality Sensor ===

Scanning I2C bus...
  no devices found - check wiring, power and pull-ups
DFRobot I2C board not responding (addr 0x19) - testing PMS9003M over UART instead
Listening for PMS9003M UART frames on USART1 (PA10 = RX, 9600 8N1)...

[PMS9003M UART] valid frame:  PM1.0=37  PM2.5=63  PM10=77  [ug/m3]
```

## PMS9003M UART frame format

32 bytes, big-endian, sent in active mode roughly once per second:

| Offset | Field |
|--------|-------|
| 0–1   | Header `0x42 0x4D` |
| 2–3   | Frame length (`0x001C` = 28) |
| 4–9   | PM1.0 / PM2.5 / PM10, standard particle (CF=1) |
| 10–15 | PM1.0 / PM2.5 / PM10, **atmospheric environment** (reported here) |
| 16–27 | Particle counts (>0.3, 0.5, 1.0, 2.5, 5.0, 10 µm per 0.1 L) |
| 28–29 | Reserved / version + error code |
| 30–31 | Checksum = sum of bytes 0–29 |

## Project layout

```
pm25_dfrobot/
├── Core/Src/main.c                     application: I2C scan, UART + I2C reads
├── Core/Src/stm32h5xx_hal_msp.c        I2C2 pin config (PB10/PB12, pull-ups)
├── Drivers/PMS9003M/                   DFRobot I2C driver (HAL port)
│   ├── dfrobot_air_quality_sensor.c
│   └── dfrobot_air_quality_sensor.h
└── Debug/                              STM32CubeIDE build output
```

## Building & flashing

Open the project in **STM32CubeIDE** and build/flash normally (the generated
makefile uses ST's GCC, which provides the `-fcyclomatic-complexity` flag that
mainline `arm-none-eabi-gcc` does not).

View the console with any serial terminal at **115200 8N1** on the ST-Link VCP.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| All I2C values are `0.0` | DFRobot adapter not responding — reads fail and return 0. Check the I2C scan output. |
| `no devices found` in I2C scan | Missing pull-ups, wrong pins (SCL=PB10, SDA=PB12), no shared GND, or a dead adapter. |
| I2C scan empty but UART frames valid | The DFRobot I2C adapter board is faulty; the PMS9003M itself is fine — use the UART path. |
| No valid UART frames | Confirm 5 V on VCC, the fan is spinning, and sensor TX → PA10. |

## Credits

I2C driver ported from the
[DFRobot_AirQualitySensor](https://github.com/dfrobot/DFRobot_AirQualitySensor)
Arduino library.
