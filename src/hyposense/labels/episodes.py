"""CGM-detected hypoglycaemia episodes (Blueprint Table 5.1; ANALYSIS_PLAN §0).

OFFLINE label code: it uses the whole recording, including the future, and must never be
imported by the live path (enforced by tests/leakage/test_import_boundaries.py).

Rules for one recording's strictly increasing CGM series (L1: threshold 70; L2: 54):
- A reading is **low** iff value < threshold. A value equal to the threshold is not low.
- **Onset** at reading i: low(i) and the next (min_run - 1) readings are also low, each within
  `max_step_s` (20 min) of its predecessor. min_run = 2 is the primary rule; min_run = 1 is the
  single-reading sensitivity rule (SA1).
- **End**, scanning j = i+1, i+2, ...:
  1. GAP if t(j) - t(j-1) > `max_gap_s` (30 min). The episode ends at reading j, the first after
     the gap.
  2. RECOVERED if not low(j), not low(j+1) and t(j+1) - t(j) <= `max_step_s`. The episode ends
     at reading j, the first of the two recovery readings.
  3. RECORD_END if the series ends first (a final lone non-low reading cannot confirm recovery).
- After an episode ending at reading j, scanning resumes at j. After RECORD_END it stops.

The recovery pair must satisfy the same 20-min spacing as the onset pair. This is how the
blueprint's executable specification (audit.py) reads "consecutive"; see ANALYSIS_PLAN §0. The
`end_index` is exclusive: readings [onset_index, end_index) belong to the episode.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import numpy.typing as npt


class EndReason(StrEnum):
    RECOVERED = "recovered"
    GAP = "gap"
    RECORD_END = "record_end"


@dataclass(frozen=True)
class Episode:
    level: str  # "L1" | "L2" | "L1_single"
    onset_index: int
    end_index: int  # exclusive; == len(series) for RECORD_END
    onset_ts: int  # epoch s of the onset reading
    end_ts: int | None  # epoch s of the reading at end_index; None for RECORD_END
    last_ts: int  # epoch s of the last reading inside the episode
    end_reason: EndReason
    nadir_mgdl: float
    n_readings: int

    @property
    def duration_s(self) -> int:
        """Onset to end reading (RECOVERED/GAP) or to the last reading (RECORD_END)."""
        return (self.end_ts if self.end_ts is not None else self.last_ts) - self.onset_ts


def validate_series(ts: npt.NDArray[np.int64], values: npt.NDArray[np.float64]) -> None:
    if ts.ndim != 1 or values.ndim != 1 or len(ts) != len(values):
        raise ValueError("ts and values must be 1-D arrays of equal length")
    if len(ts) > 1 and not np.all(np.diff(ts) > 0):
        raise ValueError("timestamps must be strictly increasing (use data.loader.cgm_series)")
    if not np.all(np.isfinite(values)):
        raise ValueError("CGM values must be finite")


def build_episodes(
    ts: npt.NDArray[np.int64],
    values: npt.NDArray[np.float64],
    threshold: float,
    *,
    min_run: int,
    max_step_s: int,
    max_gap_s: int,
    level: str,
) -> tuple[Episode, ...]:
    validate_series(ts, values)
    if min_run < 1:
        raise ValueError("min_run must be >= 1")
    n = len(ts)
    t = ts.tolist()
    g = values.tolist()

    def low(k: int) -> bool:
        return bool(g[k] < threshold)

    def onset_confirmed(i: int) -> bool:
        for k in range(i + 1, i + min_run):
            if k >= n or not low(k) or t[k] - t[k - 1] > max_step_s:
                return False
        return True

    def find_end(i: int) -> tuple[int, EndReason]:
        j = i + 1
        while j < n:
            if t[j] - t[j - 1] > max_gap_s:
                return j, EndReason.GAP
            if not low(j) and j + 1 < n and not low(j + 1) and t[j + 1] - t[j] <= max_step_s:
                return j, EndReason.RECOVERED
            j += 1
        return n, EndReason.RECORD_END

    episodes: list[Episode] = []
    i = 0
    while i < n:
        if not (low(i) and onset_confirmed(i)):
            i += 1
            continue
        end, reason = find_end(i)
        episodes.append(
            Episode(
                level=level,
                onset_index=i,
                end_index=end,
                onset_ts=t[i],
                end_ts=None if reason is EndReason.RECORD_END else t[end],
                last_ts=t[end - 1],
                end_reason=reason,
                nadir_mgdl=float(min(g[i:end])),
                n_readings=end - i,
            )
        )
        i = end
    return tuple(episodes)
