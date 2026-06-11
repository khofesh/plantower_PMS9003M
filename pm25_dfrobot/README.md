# PM2.5 Air Quality Monitor — STM32H533RE

Firmware for the **NUCLEO-H533RE** that reads particulate-matter data from a
**Plantower PMS9003M** sensor over its native UART, using a small DMA-driven
driver (`Drivers/PMS9003M/pms9003m.{c,h}`).

Reception is fully interrupt/DMA driven: the UART idle line delimits each
32-byte frame, the RX-event callback validates the checksum and decodes it, and
the application just polls `PMS9003M_HasNewData()`.

> **History:** This project originally read the sensor through a **DFRobot
> Gravity I2C adapter** (`SEN0460`). That adapter's UART→I2C bridge was found
> dead during bring-up (never ACKed on the bus, while other I2C devices
> enumerated fine), whereas the bare PMS9003M worked perfectly over UART. The
> I2C path has since been removed in favour of talking to the sensor directly.

## Hardware

| Item | Detail |
|------|--------|
| MCU board | NUCLEO-H533RE (STM32H533RET6) |
| Sensor | Plantower PMS9003M (laser PM sensor, native UART) |
| Console | ST-Link Virtual COM Port @ **115200 8N1** (USART2, PA2/PA3) |
| Sensor link | USART1 + GPDMA1 Channel 0, **9600 8N1** |

### Wiring

The PMS9003M streams data automatically; only its TX line is needed.

| PMS9003M pin | Connect to | Notes |
|--------------|-----------|-------|
| VCC | **5 V** | fan + laser require 5 V |
| GND | GND | common ground with the Nucleo |
| TX  | **PA10** | USART1_RX (AF7) |
| RX  | PA9 (optional) | USART1_TX, only needed to send commands |
| SET / RESET | leave unconnected | idle high = active mode |

## Behaviour

On boot the firmware (`Core/Src/main.c`) initialises the driver and then, once
per validated frame, prints to the console:

```
=== PMS9003M Air Quality Sensor ===
PMS9003M ready on USART1 (PA10 = RX, 9600 8N1, DMA)

--- Air quality reading (frame #5) ---
PM concentration (atmospheric) [ug/m3]:  PM1.0=37  PM2.5=63  PM10=77
PM concentration (standard)    [ug/m3]:  PM1.0=40  PM2.5=66  PM10=80
Particle count [per 0.1L]: 0.3um=... 0.5um=... 1.0um=... 2.5um=... 5.0um=... 10um=...
```

## Driver API (`pms9003m.h`)

```c
PMS9003M_t pms;

PMS9003M_Init(&pms);                          // USART1 + GPDMA, starts RX
if (PMS9003M_HasNewData(&pms)) {              // true once per new valid frame
    const PMS9003M_Data_t *d = PMS9003M_GetData(&pms);
    // d->pm2_5_atm, d->n0_3, d->version, ...
}
```

The two interrupt trampolines `PMS9003M_USART1_IRQHandler()` and
`PMS9003M_GPDMA1_Channel0_IRQHandler()` are invoked from `USART1_IRQHandler`
and `GPDMA1_Channel0_IRQHandler` in `Core/Src/stm32h5xx_it.c`.

## PMS9003M UART frame format

32 bytes, big-endian, sent in active mode roughly once per second:

| Offset | Field |
|--------|-------|
| 0–1   | Header `0x42 0x4D` |
| 2–3   | Frame length (`0x001C` = 28) |
| 4–9   | PM1.0 / PM2.5 / PM10, standard particle (CF=1) |
| 10–15 | PM1.0 / PM2.5 / PM10, atmospheric environment |
| 16–27 | Particle counts (>0.3, 0.5, 1.0, 2.5, 5.0, 10 µm per 0.1 L) |
| 28    | Version |
| 29    | Error code |
| 30–31 | Checksum = sum of bytes 0–29 |

All fields are decoded into `PMS9003M_Data_t`.

## Project layout

```
pm25_dfrobot/
├── Core/Src/main.c                 application: init + print loop
├── Core/Src/stm32h5xx_it.c         USART1 / GPDMA1 Ch0 IRQ trampolines
├── Drivers/PMS9003M/
│   ├── pms9003m.c                  DMA-based PMS9003M UART driver
│   └── pms9003m.h
└── Debug/                          STM32CubeIDE build output
```

## Building & flashing

Open the project in **STM32CubeIDE** and build/flash normally (the generated
makefile uses ST's GCC, which provides the `-fcyclomatic-complexity` flag that
mainline `arm-none-eabi-gcc` does not).

> After pulling these changes, let CubeIDE refresh the project so the build
> picks up `pms9003m.c` and drops the removed DFRobot driver (right-click the
> project → Refresh, then Build). The I2C2 peripheral is still initialised by
> CubeMX but is now unused; you can remove it from the `.ioc` if you like.

View the console with any serial terminal at **115200 8N1** on the ST-Link VCP.

## Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| No readings at all | Confirm 5 V on VCC, the fan is spinning, and sensor TX → PA10. |
| Garbled values | Wrong baud (must be 9600 8N1) or a bad TX→PA10 connection. |
| Init fails | USART1 / GPDMA1 Ch0 clock or NVIC not available — check no other peripheral claims them. |
