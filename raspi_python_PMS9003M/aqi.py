#!/usr/bin/env python3
"""Turn raw PMS9003M numbers into a verdict.

Two independent things are derived here:

  * Health  -- US EPA Air Quality Index from the PM2.5 / PM10 concentrations,
               with the category label ("Moderate", "Unhealthy", ...).
  * Source  -- a coarse guess at *what* the particles are, from the particle
               counts and the PM2.5/PM10 split: fine/sub-micron loads point at
               combustion (cooking, candles, tobacco, exhaust, smoke), a
               coarse tail points at dust / pollen / mechanical sources.

The AQI breakpoints are the US EPA values revised in May 2024 for PM2.5
(the PM10 table is unchanged). AQI is defined on 24-hour averages; applying
it to a short window gives a "nowcast"-style indication, not an official AQI.
"""

from dataclasses import dataclass

# (C_lo, C_hi, I_lo, I_hi) breakpoints. Concentration is truncated before use:
# PM2.5 to 0.1 ug/m3, PM10 to the integer, per EPA's method.
_PM25_BP = [
    (0.0,   9.0, 0,   50),
    (9.1,  35.4, 51,  100),
    (35.5, 55.4, 101, 150),
    (55.5, 125.4, 151, 200),
    (125.5, 225.4, 201, 300),
    (225.5, 325.4, 301, 500),
]
_PM10_BP = [
    (0,   54,  0,   50),
    (55,  154, 51,  100),
    (155, 254, 101, 150),
    (255, 354, 151, 200),
    (355, 424, 201, 300),
    (425, 604, 301, 500),
]

# Lower AQI bound of each category -> (name, short advice).
_CATEGORIES = [
    (0,   "Good", "air quality is satisfactory"),
    (51,  "Moderate", "acceptable; very sensitive people may notice effects"),
    (101, "Unhealthy for Sensitive Groups",
          "sensitive groups should limit prolonged exertion"),
    (151, "Unhealthy", "everyone may begin to feel effects; sensitive groups more so"),
    (201, "Very Unhealthy", "health alert: everyone may feel serious effects"),
    (301, "Hazardous", "emergency conditions: avoid all outdoor exertion"),
]


def _category(aqi: int) -> tuple[str, str]:
    name, advice = _CATEGORIES[0][1], _CATEGORIES[0][2]
    for lo, n, a in _CATEGORIES:
        if aqi >= lo:
            name, advice = n, a
    return name, advice


def _index(conc: float, table: list[tuple], trunc: float) -> int | None:
    """Piecewise-linear AQI from a concentration, or None if off-scale."""
    # Truncate to the table's resolution, as EPA specifies.
    c = int(conc / trunc) * trunc
    for c_lo, c_hi, i_lo, i_hi in table:
        if c_lo <= c <= c_hi:
            return round((i_hi - i_lo) / (c_hi - c_lo) * (c - c_lo) + i_lo)
    return None  # above the highest breakpoint


@dataclass
class AQIResult:
    aqi: int | None            # overall AQI (max of the pollutant sub-indices)
    category: str
    advice: str
    pm2_5_aqi: int | None
    pm10_aqi: int | None
    dominant: str              # which pollutant set the overall AQI


def aqi_from_pm(pm2_5: float, pm10: float) -> AQIResult:
    """Overall AQI = the worse of the PM2.5 and PM10 sub-indices."""
    a25 = _index(pm2_5, _PM25_BP, 0.1)
    a10 = _index(pm10, _PM10_BP, 1.0)

    # A None sub-index means the concentration is above the top breakpoint,
    # i.e. *worse* than any in-range value -- not missing. Such a pollutant
    # dominates and the overall AQI is reported as beyond the scale (>500).
    off_scale = [p for a, p in ((a25, "PM2.5"), (a10, "PM10"))
                 if a is None and (pm2_5 if p == "PM2.5" else pm10) > 0]
    if off_scale:
        return AQIResult(None, "Beyond AQI (>500)",
                         "hazardous: emergency conditions",
                         a25, a10, off_scale[0])

    candidates = [(a, p) for a, p in ((a25, "PM2.5"), (a10, "PM10")) if a is not None]
    if not candidates:
        return AQIResult(None, "No data", "no concentration to score", a25, a10, "—")

    aqi, dominant = max(candidates, key=lambda x: x[0])
    name, advice = _category(aqi)
    return AQIResult(aqi, name, advice, a25, a10, dominant)


# --- source attribution from particle counts ----------------------------

@dataclass
class SourceResult:
    label: str                 # one-line human verdict
    pm_ratio: float | None     # PM2.5 / PM10  (high -> fine/combustion)
    coarse_count_frac: float | None  # share of counted particles >= 2.5 um
    monotonic: bool            # counts decrease with size, as a valid frame must
    per_bin: dict              # per-size-band counts (de-cumulated)


def classify_source(n0_3: float, n0_5: float, n1_0: float,
                    n2_5: float, n5_0: float, n10: float,
                    pm2_5: float = 0.0, pm10: float = 0.0) -> SourceResult:
    """Guess the particle source from the count distribution.

    The Plantower count fields are *cumulative* ("particles >= X um per 0.1 L"),
    so they must be non-increasing with size; we de-cumulate into per-band
    counts and look at how much sits in the coarse (>= 2.5 um) tail.
    """
    counts = [n0_3, n0_5, n1_0, n2_5, n5_0, n10]
    monotonic = all(counts[i] >= counts[i + 1] for i in range(len(counts) - 1))

    per_bin = {
        "0.3-0.5": max(n0_3 - n0_5, 0.0),
        "0.5-1.0": max(n0_5 - n1_0, 0.0),
        "1.0-2.5": max(n1_0 - n2_5, 0.0),
        "2.5-5.0": max(n2_5 - n5_0, 0.0),
        "5.0-10":  max(n5_0 - n10, 0.0),
        ">=10":    max(n10, 0.0),
    }

    pm_ratio = (pm2_5 / pm10) if pm10 > 0 else None
    # Fraction of all counted particles that are coarse (>= 2.5 um).
    coarse_count_frac = (n2_5 / n0_3) if n0_3 > 0 else None

    # Thresholds are deliberately loose: < ~0.5% of counts in the >= 2.5 um
    # tail is "essentially no coarse" for an indoor optical sensor.
    if n0_3 <= 0:
        label = "no particles counted (sensor warming up or air is very clean)"
    elif pm2_5 < 5 and pm10 < 10:
        label = "very low particle load -- clean air; source not meaningful"
    elif coarse_count_frac is not None and coarse_count_frac < 0.005 \
            and (pm_ratio is None or pm_ratio > 0.5):
        label = ("fine-dominated, ~no coarse particles -- likely combustion/smoke "
                 "(cooking, candles, tobacco, exhaust, wildfire)")
    elif (coarse_count_frac is not None and coarse_count_frac > 0.02) \
            or (pm_ratio is not None and pm_ratio < 0.4):
        label = ("notable coarse fraction -- likely dust / pollen / "
                 "mechanically generated particles")
    else:
        label = "mixed fine and coarse particles"

    if not monotonic:
        label += "  [warning: non-monotonic counts -- suspect frame]"

    return SourceResult(label, pm_ratio, coarse_count_frac, monotonic, per_bin)


def summarize(pm2_5: float, pm10: float,
              counts: tuple | None = None) -> str:
    """One compact human-readable line, like the console interpretation."""
    a = aqi_from_pm(pm2_5, pm10)
    aqi_txt = a.category if a.aqi is None else f"AQI {a.aqi} ({a.category})"
    line = f"PM2.5={pm2_5:.0f} PM10={pm10:.0f} ug/m3 -> {aqi_txt}, driven by {a.dominant}"
    if counts is not None:
        s = classify_source(*counts, pm2_5=pm2_5, pm10=pm10)
        line += f"; {s.label}"
    return line


if __name__ == "__main__":
    # Sanity check against the reading I interpreted earlier (frame #483).
    print(summarize(58, 72, counts=(3031, 2832, 628, 7, 0, 0)))
