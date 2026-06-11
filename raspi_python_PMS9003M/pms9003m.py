#!/usr/bin/env python3
"""Frame reader for the Plantower PMS9003M particulate sensor.

The PMS9003M streams 32-byte frames over UART at 9600 baud, big-endian,
starting with the header 0x42 0x4D. This module syncs on that header,
validates the checksum, and returns a decoded reading.
"""

import struct
from dataclasses import dataclass

import serial

HEADER = b"\x42\x4d"
FRAME_LEN = 32          # full frame including the 2 header bytes
BODY_LEN = FRAME_LEN - 2


@dataclass
class Reading:
    # CF=1 ("standard particle") concentrations, ug/m3
    pm1_0_cf1: int
    pm2_5_cf1: int
    pm10_cf1: int
    # Atmospheric-environment concentrations, ug/m3 -- report these
    pm1_0: int
    pm2_5: int
    pm10: int
    # Raw particle counts per 0.1 L of air
    n0_3: int
    n0_5: int
    n1_0: int
    n2_5: int
    n5_0: int
    n10: int


def open_serial(port: str = "/dev/serial0", baud: int = 9600,
                timeout: float = 2.0) -> serial.Serial:
    return serial.Serial(port, baud, timeout=timeout)


def read_frame(ser: serial.Serial) -> Reading | None:
    """Read one valid frame. Returns None on timeout/short read."""
    # Sync on the 2-byte header one byte at a time.
    if ser.read(1) != HEADER[0:1]:
        return None
    deadline_bytes = 64  # bound how far we scan for the second header byte
    while True:
        b = ser.read(1)
        if not b:
            return None
        if b == HEADER[1:2]:
            break
        if b != HEADER[0:1]:
            deadline_bytes -= 1
            if deadline_bytes <= 0:
                return None

    body = ser.read(BODY_LEN)
    if len(body) != BODY_LEN:
        return None

    frame = HEADER + body
    # Checksum = sum of the first 30 bytes, compared to the last 2.
    if sum(frame[:30]) != struct.unpack(">H", frame[30:32])[0]:
        return None

    # body[0:2] is the frame length field (0x001C). Data starts at body[2].
    v = struct.unpack(">13H", body[2:28])
    return Reading(
        pm1_0_cf1=v[0], pm2_5_cf1=v[1], pm10_cf1=v[2],
        pm1_0=v[3], pm2_5=v[4], pm10=v[5],
        n0_3=v[6], n0_5=v[7], n1_0=v[8],
        n2_5=v[9], n5_0=v[10], n10=v[11],
    )


def read_valid_frame(ser: serial.Serial, retries: int = 10) -> Reading | None:
    """Keep reading until a valid frame is decoded or retries run out."""
    for _ in range(retries):
        r = read_frame(ser)
        if r is not None:
            return r
    return None


if __name__ == "__main__":
    ser = open_serial()
    print("Reading PMS9003M on", ser.port, "(Ctrl-C to stop)")
    while True:
        r = read_valid_frame(ser)
        if r is None:
            print("no valid frame")
            continue
        print(f"PM1.0={r.pm1_0:>4}  PM2.5={r.pm2_5:>4}  PM10={r.pm10:>4} ug/m3")
