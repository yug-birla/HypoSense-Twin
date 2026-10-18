"""Causal feature snapshots (Blueprint Table 25.2 `snapshot(state, static, level) ->
FeatureSnapshot`; ADR-004).

ONE implementation serves offline training-matrix generation and live / replay inference.
`FeatureBuilder.union(inputs)` computes every feature of every level at the state's current
reading. A level's snapshot is a fixed selection of that union, in the order of
`artifacts/features/feature_spec.json`. Offline generation (`features.build`) calls exactly
the same method after each CGM reading of an event-by-event replay.

The builder reads ONLY `FeatureInputs` (context, CGM state, meals, medication state). It has no
access to the forecast state or outcome ledger, or to the label builder (static test).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from hyposense.features.cgm import CGMFeatureConfig, cgm_features
from hyposense.features.context import meal_features, static_features
from hyposense.features.medication import exposure_features, flag_features, raw_timing_features
from hyposense.features.spec import (
    LEVELS,
    UNION_NAMES,
    FeatureSpecMismatch,
    level_names,
    spec_sha256,
)
from hyposense.state.cgm import CGMState
from hyposense.state.context import PatientContext
from hyposense.state.events import MealEvent
from hyposense.state.history import AppendLog
from hyposense.state.medication import MedicationExposureState
from hyposense.state.patient import PatientState, StateError

_UNION_INDEX = {n: i for i, n in enumerate(UNION_NAMES)}
LEVEL_INDEX: dict[str, npt.NDArray[np.intp]] = {
    lvl: np.array([_UNION_INDEX[n] for n in level_names(lvl)], dtype=np.intp) for lvl in LEVELS
}


@dataclass(frozen=True)
class FeatureInputs:
    """The only state blocks the feature builder may read."""

    context: PatientContext
    cgm: CGMState
    meals: AppendLog[MealEvent]
    medication: MedicationExposureState

    @classmethod
    def of(cls, state: PatientState) -> FeatureInputs:
        if state.error is not None:
            raise StateError(f"no snapshot of a SYSTEM_ERROR state ({state.error})")
        if not state.at_cgm_reading:
            raise StateError("snapshots are taken at CGM readings (decision times) only")
        return cls(state.context, state.cgm, state.meals, state.medication)


@dataclass(frozen=True)
class FeatureSnapshot:
    patient_key: str
    recording_key: str
    ts: int
    level: str
    names: tuple[str, ...]
    values: npt.NDArray[np.float64]
    spec_sha256: str
    digest: str  # sha256 of level, names, values and spec hash


def _digest(level: str, names: tuple[str, ...], values: npt.NDArray[np.float64], spec: str) -> str:
    h = hashlib.sha256()
    h.update(f"{level}|{spec}|{','.join(names)}|".encode())
    h.update(np.ascontiguousarray(values, dtype=np.float64).tobytes())
    return h.hexdigest()


class FeatureBuilder:
    def __init__(self, cfg: dict[str, Any]) -> None:
        f = cfg["features"]
        self.cgm_cfg = CGMFeatureConfig.from_config(cfg)
        self.meal_cap_min = float(f["meal_min_since_cap_min"])
        self.meal_recent_s = int(f["meal_recent_window_min"]) * 60
        self.spec_version = str(f["spec_version"])
        self.spec_sha256 = spec_sha256(f)

    def union_dict(self, x: FeatureInputs) -> dict[str, float]:
        ts, g = x.cgm.series.ts, x.cgm.series.values
        t = int(ts[-1])
        out = cgm_features(ts, g, x.cgm.tracker.n_onsets, x.cgm.last_low_ts, self.cgm_cfg)
        out.update(static_features(x.context))
        out.update(
            meal_features(
                x.meals.items(),
                t,
                self.meal_cap_min,
                self.meal_recent_s,
                self.cgm_cfg.utc_offset_s,
            )
        )
        med = x.medication.at(t)
        out.update(raw_timing_features(med))
        out.update(flag_features(med))
        out.update(exposure_features(med, x.context.values["weight_kg"]))
        return out

    def union(self, x: FeatureInputs) -> npt.NDArray[np.float64]:
        d = self.union_dict(x)
        if len(d) != len(UNION_NAMES) or set(d) != set(UNION_NAMES):
            raise FeatureSpecMismatch(
                f"computed {sorted(set(d) ^ set(UNION_NAMES))} differ from the specification"
            )
        v = np.array([d[n] for n in UNION_NAMES], dtype=np.float64)
        v[np.isnan(v)] = math.nan  # one canonical NaN bit pattern (bitwise comparisons)
        return v

    def snapshot(self, state: PatientState, level: str) -> FeatureSnapshot:
        names = level_names(level)
        values = self.union(FeatureInputs.of(state))[LEVEL_INDEX[level]]
        values.flags.writeable = False
        assert state.ts is not None
        return FeatureSnapshot(
            state.patient_key,
            state.recording_key,
            state.ts,
            level,
            names,
            values,
            self.spec_sha256,
            _digest(level, names, values, self.spec_sha256),
        )
