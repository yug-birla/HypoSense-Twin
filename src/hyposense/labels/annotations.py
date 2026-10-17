"""Episode annotations used by sensitivity analyses (Blueprint Table 20.3). OFFLINE.

Annotations never change the episode set. They only mark episodes for subgroup or exclusion
analyses:
- nocturnal: onset local hour in [00:00, 06:00) (§8.2; SA4 component).
- within_first_24h: onset < 24 h after the recording's first CGM reading (SA2).
- compression_candidate: nocturnal onset, short episode (<= 45 min) and a steep fall into it or
  a steep rise out of it (>= 1.5 mg/dL/min). This is the blueprint's SA4 heuristic, reproduced
  from audit2.py.
- prior_reading_lt80: the reading before onset is < 80 mg/dL (§8.2: shows why the v1 exclusion
  rule was harmful).
- sensor_floor_run: the episode overlaps a run of >= 8 consecutive CGM readings at or below the
  sensor floor (40 mg/dL), i.e. >= 2 h stuck at the floor. This is a CGM-only sensor-failure
  candidate, identified in S2 on tuning-partition data (proposal P-C8). It never changes labels.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from hyposense.labels.episodes import Episode

SA4_MAX_DURATION_MIN = 45.0
SA4_MIN_SLOPE = 1.5
NIGHT_END_HOUR = 6
FIRST_DAY_S = 24 * 3600
SENSOR_FLOOR_MGDL = 40.0
SENSOR_FLOOR_RUN_MIN_READINGS = 8  # >= 2 h at 15-min sampling
NOMINAL_INTERVAL_MIN = 15.0  # FreeStyle Libre H sampling interval (audit2.py adds one interval)


@dataclass(frozen=True)
class EpisodeAnnotation:
    nocturnal: bool
    within_first_24h: bool
    compression_candidate: bool
    prior_reading_lt80: bool
    onset_local_hour: int
    sensor_floor_run: bool


def local_hour(ts: int, utc_offset_s: int) -> int:
    return ((ts + utc_offset_s) // 3600) % 24


def floor_runs(
    ts: npt.NDArray[np.int64],
    g: npt.NDArray[np.float64],
    max_step_s: int = 1200,
    floor: float = SENSOR_FLOOR_MGDL,
    min_readings: int = SENSOR_FLOOR_RUN_MIN_READINGS,
) -> list[tuple[int, int]]:
    """Index ranges [start, end) of >= min_readings consecutive readings <= floor, where consecutive
    readings are at most max_step_s apart."""
    runs: list[tuple[int, int]] = []
    start = None
    for k in range(len(g) + 1):
        on = k < len(g) and g[k] <= floor and (start is None or ts[k] - ts[k - 1] <= max_step_s)
        if on and start is None:
            start = k
        elif not on and start is not None:
            if k - start >= min_readings:
                runs.append((start, k))
            start = k if (k < len(g) and g[k] <= floor) else None
    return runs


def annotate(
    ep: Episode,
    ts: npt.NDArray[np.int64],
    g: npt.NDArray[np.float64],
    utc_offset_s: int,
    runs: list[tuple[int, int]] | None = None,
) -> EpisodeAnnotation:
    a, bb, n = ep.onset_index, ep.end_index, len(ts)
    hour = local_hour(int(ts[a]), utc_offset_s)
    noct = hour < NIGHT_END_HOUR
    fall = (g[a - 1] - g[a]) / ((ts[a] - ts[a - 1]) / 60) if a > 0 else 0.0
    rise = (g[bb] - g[bb - 1]) / ((ts[bb] - ts[bb - 1]) / 60) if bb < n else 0.0
    dur_min = (ts[bb - 1] - ts[a]) / 60 + NOMINAL_INTERVAL_MIN  # audit2.py definition
    return EpisodeAnnotation(
        nocturnal=bool(noct),
        within_first_24h=bool(ts[a] - ts[0] < FIRST_DAY_S),
        compression_candidate=bool(
            noct
            and dur_min <= SA4_MAX_DURATION_MIN
            and (fall >= SA4_MIN_SLOPE or rise >= SA4_MIN_SLOPE)
        ),
        prior_reading_lt80=bool(a > 0 and g[a - 1] < 80),
        onset_local_hour=int(hour),
        sensor_floor_run=any(
            a < r_end and r_start < bb
            for r_start, r_end in (runs if runs is not None else floor_runs(ts, g))
        ),
    )
