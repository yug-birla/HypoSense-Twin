"""Medication Exposure State: the recording's append-only log of parsed medication events and the
S3 engines evaluated at t (Blueprint §12, Table 25.2 `exposure_at`).

Nothing here re-implements medication logic. `ExposureEngine` (M3, with quality states) and
`RawTiming` / `raw_timing` (M3r) are the S3 implementations. They are called with the events
logged so far, all of which have ts <= t by construction (asserted). S3 proved that these
engines are bitwise identical for full and truncated event lists.

The engine is built once per log length and shared by the following states until the next
medication event arrives, so a CGM-only update costs no engine rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from hyposense.medication.events import MedicationEvent
from hyposense.medication.exposure import CLASSES, ExposureEngine, KernelSet, QualityState
from hyposense.medication.timing import RawTiming
from hyposense.state.history import AppendLog


class _EngineCache:
    __slots__ = ("engine", "n", "timing")

    def __init__(self) -> None:
        self.engine: ExposureEngine | None = None
        self.timing: RawTiming | None = None
        self.n = -1


@dataclass(frozen=True)
class MedicationSnapshot:
    """S3 outputs at one time t (doses with ts <= t only)."""

    ts: int
    exposure: dict[str, float]  # ExposureEngine.compute outputs (incl. quality_* codes)
    timing: dict[str, float]  # raw_timing outputs (M3r)
    quality: dict[str, QualityState]  # per class: insulin / sulfonylurea / glinide


@dataclass(frozen=True)
class MedicationExposureState:
    kernels: KernelSet
    prescribed: frozenset[str]  # classes named in the prescribed regimen (static summary)
    events: AppendLog[MedicationEvent] = field(default_factory=AppendLog)
    _cache: _EngineCache = field(default_factory=_EngineCache, compare=False, repr=False)

    def add(self, e: MedicationEvent) -> MedicationExposureState:
        return MedicationExposureState(self.kernels, self.prescribed, self.events.append(e))

    def _engines(self) -> tuple[ExposureEngine, RawTiming]:
        c = self._cache
        if c.engine is None or c.timing is None or c.n != len(self.events):
            items = self.events.items()
            c.engine = ExposureEngine(items, self.kernels, self.prescribed)
            c.timing = RawTiming(items)
            c.n = len(self.events)
        return c.engine, c.timing

    def engine(self) -> ExposureEngine:
        return self._engines()[0]

    def at(self, t: int) -> MedicationSnapshot:
        last = self.events.last()
        if last is not None and last.ts > t:
            raise AssertionError(f"medication event at {last.ts} is after t={t}")
        times = np.array([t], dtype=np.int64)
        engine, timing = self._engines()
        exp = {k: float(v[0]) for k, v in engine.compute(times).items()}
        tim = {k: float(v[0]) for k, v in timing.compute(times).items()}
        states = list(QualityState)
        quality = {c: states[int(exp[f"quality_{c}"])] for c in CLASSES}
        return MedicationSnapshot(t, exp, tim, quality)
