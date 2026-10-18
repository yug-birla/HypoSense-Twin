"""Per-reading CGM quality flags (Blueprint §10.1). Flags annotate; they never delete data.

The thresholds come from configs/default.yaml `policy` (max_gap_min, floor_mgdl,
max_rate_mgdl_per_min, warmup_min). The policy's sufficiency rule (S7) consumes these flags. It
does not re-implement them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from hyposense.data.records import CGMSeries


@dataclass(frozen=True)
class QualityThresholds:
    max_gap_min: float = 20.0
    floor_mgdl: float = 40.0
    max_rate_mgdl_per_min: float = 4.0
    warmup_min: float = 120.0


@dataclass(frozen=True)
class CGMQualityFlags:
    gap_before: npt.NDArray[
        np.bool_
    ]  # interval to previous reading > max_gap_min (first reading: False)
    floor: npt.NDArray[np.bool_]  # value <= floor (sensor floor)
    rapid_change: npt.NDArray[np.bool_]  # |dG/dt| from previous reading > max rate
    warmup: npt.NDArray[np.bool_]  # within warmup_min of the recording's first reading


def cgm_quality_flags(series: CGMSeries, thr: QualityThresholds) -> CGMQualityFlags:
    ts, g = series.ts, series.value
    n = len(ts)
    gap = np.zeros(n, dtype=bool)
    rate = np.zeros(n, dtype=bool)
    if n > 1:
        dt_min = np.diff(ts) / 60.0
        gap[1:] = dt_min > thr.max_gap_min
        slope = np.abs(np.diff(g)) / dt_min
        rate[1:] = slope > thr.max_rate_mgdl_per_min
    warm = (ts - ts[0]) < thr.warmup_min * 60 if n else np.zeros(0, dtype=bool)
    return CGMQualityFlags(
        gap_before=gap, floor=g <= thr.floor_mgdl, rapid_change=rate, warmup=warm
    )


SENSOR_FAULT_RUN_READINGS = 8  # approved P-C8a: >= 8 consecutive readings <= floor (~2 h)


def sensor_fault_suspected(
    series: CGMSeries,
    thr: QualityThresholds,
    min_readings: int = SENSOR_FAULT_RUN_READINGS,
    max_step_s: int = 1200,
) -> npt.NDArray[np.bool_]:
    """CAUSAL live flag (approved P-C8a/b): True at reading t if the readings ending at t form a run
    of >= `min_readings` consecutive values <= floor, each <= max_step_s apart. It uses only data
    up to t. It is a data-quality warning ("SENSOR FAULT SUSPECTED"): it never changes labels and
    never replaces LOW NOW (P-C1). The offline SA9 annotation (labels.annotations.floor_runs)
    flags whole runs in hindsight, including their first 7 readings."""
    ts, g = series.ts, series.value
    out = np.zeros(len(g), dtype=bool)
    run = 0
    for k in range(len(g)):
        contiguous = k > 0 and ts[k] - ts[k - 1] <= max_step_s
        run = (run + 1 if contiguous else 1) if g[k] <= thr.floor_mgdl else 0
        out[k] = run >= min_readings
    return out
