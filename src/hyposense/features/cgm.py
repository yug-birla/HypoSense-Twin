"""CGM feature groups G1-G4 (App. D). Pure functions of the recording's readings up to t.

`ts`/`g` are the state's history arrays. Their last element IS the reading at t, so no later
reading can be seen. Windows are half-open (t - D, t] (§25.1). Sums are exact (`math.fsum`), so a
value depends only on the window's contents, never on how it was obtained.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from hyposense.common.timeconv import parse_utc_offset


@dataclass(frozen=True)
class CGMFeatureConfig:
    lags_s: tuple[int, ...]
    lag_tol_s: float
    trend_tol_s: int
    slope_windows_s: tuple[int, ...]
    slope_min_readings: int
    projections_min: tuple[int, ...]
    stat_windows: tuple[tuple[int, str], ...]  # (seconds, label)
    below_mgdl: float
    interval_min: float
    low_mgdl: float
    low_cap_min: float
    pct_min_history_s: int
    night_hours: tuple[int, int]
    max_step_s: int
    utc_offset_s: int

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> CGMFeatureConfig:
        f = cfg["features"]
        labels = {120: "2h", 360: "6h", 1440: "24h"}
        return cls(
            lags_s=tuple(int(x) * 60 for x in f["lags_min"]),
            lag_tol_s=float(f["lag_tolerance_min"]) * 60,
            trend_tol_s=int(f["trend_window_tolerance_min"]) * 60,
            slope_windows_s=tuple(int(x) * 60 for x in f["slope_windows_min"]),
            slope_min_readings=int(f["slope_min_readings"]),
            projections_min=tuple(int(x) for x in f["m0_projections_min"]),
            stat_windows=tuple((int(w) * 60, labels[int(w)]) for w in f["stat_windows_min"]),
            below_mgdl=float(f["below_threshold_mgdl"]),
            interval_min=float(f["cgm_nominal_interval_min"]),
            low_mgdl=float(cfg["event"]["threshold_mgdl"]),
            low_cap_min=float(f["min_since_low_cap_min"]),
            pct_min_history_s=int(f["own_percentile_min_history_h"]) * 3600,
            night_hours=(int(f["night_hours"][0]), int(f["night_hours"][1])),
            max_step_s=int(cfg["event"]["max_step_min"]) * 60,
            utc_offset_s=parse_utc_offset(str(cfg["time"]["assumed_utc_offset"])),
        )


def ls_slope(ts: npt.NDArray[np.int64], g: npt.NDArray[np.float64]) -> float:
    """Least-squares slope (mg/dL per min) with exact sums; NaN for < 2 points."""
    n = len(ts)
    if n < 2:
        return math.nan
    x = ((ts - ts[-1]) / 60.0).tolist()
    y = g.tolist()
    xm = math.fsum(x) / n
    ym = math.fsum(y) / n
    sxx = math.fsum((a - xm) * (a - xm) for a in x)
    if sxx == 0.0:
        return math.nan
    return math.fsum((a - xm) * (b - ym) for a, b in zip(x, y, strict=True)) / sxx


def window_start(ts: npt.NDArray[np.int64], t: int, span_s: float) -> int:
    """Index of the first reading in (t - span_s, t]."""
    return int(np.searchsorted(ts, t - span_s, side="right"))


def trend_slope(
    ts: npt.NDArray[np.int64], g: npt.NDArray[np.float64], window_s: int, c: CGMFeatureConfig
) -> float:
    t = int(ts[-1])
    lo = window_start(ts, t, window_s + c.trend_tol_s)
    if len(ts) - lo < c.slope_min_readings:
        return math.nan
    return ls_slope(ts[lo:], g[lo:])


def nearest_lag(
    ts: npt.NDArray[np.int64], g: npt.NDArray[np.float64], lag_s: int, tol_s: float
) -> float:
    target = int(ts[-1]) - lag_s
    lo = int(np.searchsorted(ts, target - tol_s, side="left"))
    hi = int(np.searchsorted(ts, target + tol_s, side="right"))
    if hi <= lo:
        return math.nan
    dist = np.abs(ts[lo:hi] - target)
    return float(g[lo + int(np.argmin(dist))])  # argmin -> first (earlier) on ties


def cgm_features(
    ts: npt.NDArray[np.int64],
    g: npt.NDArray[np.float64],
    n_onsets: int,
    last_low_ts: int | None,
    c: CGMFeatureConfig,
) -> dict[str, float]:
    t = int(ts[-1])
    gt = float(g[-1])
    out: dict[str, float] = {"cgm": gt}
    # G1 level
    for lag in c.lags_s:
        v = nearest_lag(ts, g, lag, c.lag_tol_s)
        out[f"cgm_lag{lag // 60}"] = v
    slopes = {w // 60: trend_slope(ts, g, w, c) for w in c.slope_windows_s}
    for h in c.projections_min:
        out[f"cgm_m0_proj{h}"] = gt + h * slopes[30] if math.isfinite(slopes[30]) else math.nan
    for lag in c.lags_s:
        out[f"cgm_lag{lag // 60}_missing"] = float(math.isnan(out[f"cgm_lag{lag // 60}"]))
    # G2 trend
    for w, s in slopes.items():
        out[f"cgm_slope{w}"] = s
    out["cgm_accel"] = slopes[30] - slopes[60]  # NaN if either is NaN
    k = len(g) - 1
    falling = 0
    while k >= 1 and g[k] < g[k - 1] and ts[k] - ts[k - 1] <= c.max_step_s:
        falling += 1
        k -= 1
    out["cgm_n_falling"] = float(falling)
    out["cgm_slope30_missing"] = float(math.isnan(slopes[30]))
    out["cgm_slope60_missing"] = float(math.isnan(slopes[60]))
    # G3 variability and personal history
    for w, lab in c.stat_windows:
        win = g[window_start(ts, t, w) :].tolist()
        n = len(win)
        mean = math.fsum(win) / n
        out[f"cgm_min_{lab}"] = min(win)
        out[f"cgm_mean_{lab}"] = mean
        out[f"cgm_sd_{lab}"] = (
            math.sqrt(math.fsum((v - mean) ** 2 for v in win) / (n - 1)) if n > 1 else math.nan
        )
    out["cgm_cv_24h"] = out["cgm_sd_24h"] / out["cgm_mean_24h"]
    w24 = g[window_start(ts, t, 86400) :]
    out["cgm_min_below80_24h"] = float(np.count_nonzero(w24 < c.below_mgdl)) * c.interval_min
    out["cgm_prior_l1_onsets"] = float(n_onsets)
    out["cgm_min_since_low70"] = (
        min((t - last_low_ts) / 60.0, c.low_cap_min) if last_low_ts is not None else math.nan
    )
    span = t - int(ts[0])
    if span >= c.pct_min_history_s:
        below = np.count_nonzero(g < gt)
        equal = np.count_nonzero(g == gt)
        out["cgm_pct_own"] = 100.0 * (below + 0.5 * equal) / len(g)
    else:
        out["cgm_pct_own"] = math.nan
    out["sensor_day"] = float(span // 86400 + 1)
    out["cgm_min_since_low70_missing"] = float(last_low_ts is None)
    out["cgm_pct_own_missing"] = float(math.isnan(out["cgm_pct_own"]))
    # G4 time (local clock)
    sod = (t + c.utc_offset_s) % 86400
    hour = sod / 3600.0
    out["hour_sin"] = math.sin(2.0 * math.pi * hour / 24.0)
    out["hour_cos"] = math.cos(2.0 * math.pi * hour / 24.0)
    lo_h, hi_h = c.night_hours
    out["night"] = float(lo_h <= int(hour) < hi_h)
    return out
