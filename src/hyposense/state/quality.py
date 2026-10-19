"""Data-quality state at the latest CGM reading (Blueprint Table 10.1, Table 14.1 priority 2;
ANALYSIS_PLAN §0 item 5, §0c).

The per-reading flags are not re-implemented here. They come from the authoritative functions in
`hyposense.data.quality`, applied to the minimal causal tail:
- gap / floor / rapid-change: the last 2 readings (`cgm_quality_flags`);
- P-C8 sensor-fault suspicion: the last 8 readings (`sensor_fault_suspected`). The flag at
  reading k depends only on readings k-7 .. k, so the tail gives the identical value.

Warm-up is measured from an anchor, which is the recording's first reading. P-C7 (approved,
DEC-2026-10-19-M; `policy.warmup_restart_after_gap_min` = 120) re-anchors the POLICY warm-up at
the first reading after a CGM gap > 120 min (strict). Labels are not re-anchored
(ANALYSIS_PLAN §0 item 5), so the two anchors differ only after such a gap.

Sufficiency means a forecast may be requested: no gap > 20 min before t, >= 7 readings in
(t - 120 min, t], warm-up over, and the reading not flagged (floor, rapid change). It is a
state property consumed by the policy (S7). It is never a feature, and it never decides label
eligibility, which is the offline label builder's job.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from hyposense.data.quality import (
    SENSOR_FAULT_RUN_READINGS,
    QualityThresholds,
    cgm_quality_flags,
    sensor_fault_suspected,
)
from hyposense.data.records import CGMSeries
from hyposense.state.history import SeriesLog


@dataclass(frozen=True)
class SufficiencyRule:
    history_s: int = 7200
    min_readings_in_history: int = 7
    warmup_s: int = 7200
    warmup_restart_after_gap_s: int | None = None  # P-C7 (approved; set from policy config)
    sensor_fault_max_step_s: int = 1200


@dataclass(frozen=True)
class DataQualityState:
    ts: int
    gap_before: bool  # > max_gap_min since the previous reading
    floor: bool  # value <= floor (40 mg/dL)
    rapid_change: bool  # |dG/dt| > 4 mg/dL/min vs the previous reading
    warmup_anchor_ts: int
    warmup: bool  # t - anchor < warm-up period
    n_history: int  # readings in (t - 120 min, t]
    history_ok: bool
    sensor_fault_suspected: bool  # P-C8a causal flag (annotation; never changes labels)

    @property
    def reasons(self) -> tuple[str, ...]:
        """Reasons the reading at t is not sufficient for a forecast (empty = sufficient)."""
        out = []
        if self.gap_before:
            out.append("AFTER_GAP")
        if not self.history_ok:
            out.append("INSUFFICIENT_HISTORY")
        if self.warmup:
            out.append("WARM_UP")
        if self.floor:
            out.append("SENSOR_FLOOR")
        if self.rapid_change:
            out.append("RAPID_CHANGE")
        if self.sensor_fault_suspected:
            out.append("SENSOR_FAULT_SUSPECTED")
        return tuple(out)

    @property
    def sufficient(self) -> bool:
        return not self.reasons


def assess(
    series: SeriesLog,
    prev: DataQualityState | None,
    thr: QualityThresholds,
    rule: SufficiencyRule,
    recording_key: str,
) -> DataQualityState:
    """Quality of the latest reading in `series` (uses readings <= t only)."""
    ts_all, g_all = series.ts, series.values
    n = len(ts_all)
    t = int(ts_all[-1])

    def tail(k: int) -> CGMSeries:
        lo = max(0, n - k)
        return CGMSeries(recording_key, ts_all[lo:], g_all[lo:], np.zeros(n - lo, np.int64), {})

    flags = cgm_quality_flags(tail(2), thr)
    gap = bool(flags.gap_before[-1])
    if prev is None or (
        rule.warmup_restart_after_gap_s is not None
        and t - prev.ts > (rule.warmup_restart_after_gap_s)
    ):
        anchor = t
    else:
        anchor = prev.warmup_anchor_ts
    n_hist = n - int(np.searchsorted(ts_all, t - rule.history_s, side="right"))
    fault = sensor_fault_suspected(
        tail(SENSOR_FAULT_RUN_READINGS), thr, max_step_s=rule.sensor_fault_max_step_s
    )
    return DataQualityState(
        ts=t,
        gap_before=gap,
        floor=bool(flags.floor[-1]),
        rapid_change=bool(flags.rapid_change[-1]),
        warmup_anchor_ts=anchor,
        warmup=(t - anchor) < rule.warmup_s,
        n_history=n_hist,
        history_ok=n_hist >= rule.min_readings_in_history,
        sensor_fault_suspected=bool(fault[-1]),
    )
