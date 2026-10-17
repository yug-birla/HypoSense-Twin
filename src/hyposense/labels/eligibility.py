"""Label-eligible prediction times and future-onset labels.

Blueprint Table 5.1; ANALYSIS_PLAN §0 and §2.

OFFLINE label code. It uses the future (episode ends, follow-up, upcoming onsets).

Two concepts are kept distinct (ANALYSIS_PLAN §2):
- POLICY DECISION TIME: every CGM reading. The live policy decides at each one (S5/S7, causal).
- LABEL-ELIGIBLE TIME: a reading at which a forecast is evaluated or trained (this module).

A reading at time t is label-eligible iff all of the following hold. The first failing rule,
in this order, is recorded as the reason:
1. LOW_CGM                 value(t) >= 70 mg/dL. A current low is a LOW NOW state, never a
                           forecasting target.
2. IN_EPISODE              t is not inside an L1 episode, i.e. not in [onset, end) by reading
                           index. Record-end episodes run to the last reading.
3. REFRACTORY              t is not in [end_ts, end_ts + 60 min) of any L1 episode with an end
                           reading (RECOVERED or GAP).
4. INSUFFICIENT_HISTORY    t - warm-up anchor >= 120 min AND >= 7 readings in (t - 120 min, t].
                           The anchor is the recording's first reading. The P-C7 hook
                           `warmup_restart_after_gap_s` (pending approval) also re-anchors after
                           any gap longer than that.
5. INSUFFICIENT_FOLLOW_UP  last reading - t >= 60 min, OR an L1 onset in (t, t + 60 min].

Label y(t) = 1 iff an L1 onset lies in (t, t + 60 min], else 0; y = -1 at non-eligible readings.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum

import numpy as np
import numpy.typing as npt

from hyposense.labels.config import LabelConfig
from hyposense.labels.episodes import Episode, validate_series


class Ineligibility(IntEnum):
    ELIGIBLE = 0
    LOW_CGM = 1
    IN_EPISODE = 2
    REFRACTORY = 3
    INSUFFICIENT_HISTORY = 4
    INSUFFICIENT_FOLLOW_UP = 5


@dataclass(frozen=True)
class PredictionLabels:
    ts: npt.NDArray[np.int64]
    value: npt.NDArray[np.float64]
    reason: npt.NDArray[np.int8]  # Ineligibility code per reading
    eligible: npt.NDArray[np.bool_]
    y: npt.NDArray[np.int8]  # 1 / 0 at eligible readings, -1 elsewhere
    seconds_to_next_onset: npt.NDArray[
        np.float64
    ]  # to the first L1 onset strictly after t; NaN if none


def in_episode_mask(n: int, episodes: Sequence[Episode]) -> npt.NDArray[np.bool_]:
    mask = np.zeros(n, dtype=bool)
    for e in episodes:
        mask[e.onset_index : e.end_index] = True
    return mask


def refractory_mask(
    ts: npt.NDArray[np.int64], episodes: Sequence[Episode], refractory_s: int
) -> npt.NDArray[np.bool_]:
    mask = np.zeros(len(ts), dtype=bool)
    for e in episodes:
        if e.end_ts is not None:
            mask |= (ts >= e.end_ts) & (ts < e.end_ts + refractory_s)
    return mask


def warmup_anchor(
    ts: npt.NDArray[np.int64], restart_after_gap_s: int | None
) -> npt.NDArray[np.int64]:
    """Per reading, the time from which warm-up is measured (recording start; P-C7 hook)."""
    anchor = np.full(len(ts), ts[0] if len(ts) else 0, dtype=np.int64)
    if restart_after_gap_s is not None and len(ts) > 1:
        current = int(ts[0])
        for k in range(1, len(ts)):
            if ts[k] - ts[k - 1] > restart_after_gap_s:
                current = int(ts[k])
            anchor[k] = current
    return anchor


def history_mask(ts: npt.NDArray[np.int64], cfg: LabelConfig) -> npt.NDArray[np.bool_]:
    anchor = warmup_anchor(ts, cfg.warmup_restart_after_gap_s)
    since_anchor = (ts - anchor) >= cfg.min_time_since_start_s
    # readings in the half-open window (t - history, t]: index(t) + 1 - #readings <= t - history
    upto = np.arange(1, len(ts) + 1)
    before = np.searchsorted(ts, ts - cfg.history_s, side="right")
    count = upto - before
    return since_anchor & (count >= cfg.min_readings_in_history)


def seconds_to_next_onset(
    ts: npt.NDArray[np.int64], onsets: npt.NDArray[np.int64]
) -> npt.NDArray[np.float64]:
    out = np.full(len(ts), np.nan)
    if len(onsets):
        idx = np.searchsorted(onsets, ts, side="right")  # first onset strictly after t
        has = idx < len(onsets)
        out[has] = (onsets[idx[has]] - ts[has]).astype(np.float64)
    return out


def build_prediction_labels(
    ts: npt.NDArray[np.int64],
    values: npt.NDArray[np.float64],
    l1_episodes: Sequence[Episode],
    cfg: LabelConfig,
) -> PredictionLabels:
    validate_series(ts, values)
    n = len(ts)
    onsets = np.array(sorted(e.onset_ts for e in l1_episodes), dtype=np.int64)
    to_next = seconds_to_next_onset(ts, onsets)
    onset_in_horizon = np.nan_to_num(to_next, nan=np.inf) <= cfg.horizon_s
    follow_up = (ts[-1] - ts >= cfg.follow_up_s) | onset_in_horizon if n else np.zeros(0, bool)

    checks = (
        (Ineligibility.LOW_CGM, values < cfg.l1_threshold_mgdl),
        (Ineligibility.IN_EPISODE, in_episode_mask(n, l1_episodes)),
        (Ineligibility.REFRACTORY, refractory_mask(ts, l1_episodes, cfg.refractory_s)),
        (Ineligibility.INSUFFICIENT_HISTORY, ~history_mask(ts, cfg)),
        (Ineligibility.INSUFFICIENT_FOLLOW_UP, ~follow_up),
    )
    reason = np.full(n, Ineligibility.ELIGIBLE, dtype=np.int8)
    for code, failed in checks:  # first failing rule wins
        reason[(reason == Ineligibility.ELIGIBLE) & failed] = code
    eligible = reason == Ineligibility.ELIGIBLE
    y = np.where(eligible, onset_in_horizon.astype(np.int8), np.int8(-1)).astype(np.int8)
    return PredictionLabels(
        ts=ts, value=values, reason=reason, eligible=eligible, y=y, seconds_to_next_onset=to_next
    )


def warnable_onsets(
    labels: PredictionLabels, onsets: npt.NDArray[np.int64], cfg: LabelConfig
) -> npt.NDArray[np.bool_]:
    """Episode warnable iff some label-eligible t lies in [onset - horizon, onset - min_lead]
    (closed both ends; Blueprint Table 5.1 'correct warning'). This is the ceiling on episode
    sensitivity."""
    t = labels.ts[labels.eligible]
    out = np.zeros(len(onsets), dtype=bool)
    for k, o in enumerate(onsets.tolist()):
        out[k] = bool(np.any((t >= o - cfg.horizon_s) & (t <= o - cfg.min_lead_s)))
    return out
