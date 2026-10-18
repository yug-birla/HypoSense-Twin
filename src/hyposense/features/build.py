"""Offline feature generation: replay each recording event by event through `PatientState.update`
and call `FeatureBuilder.union` after every CGM reading. This is the inference path, run over a
whole recording (ADR-004); there is no separate batch implementation.

Scope guard (sealed partition, ADR-011 / P-C5): before freeze, features can be generated only
from a `TUNING_ONLY` dataset. Any other scope raises `SealedPartitionError`.

Per reading, the output also carries non-feature METADATA: sufficiency flags, the P-C8 causal
sensor-fault flag and the causal episode status. The policy (S7) and the S6 development masks
(P-B6 / SA9) use them. They are never model inputs.
"""

from __future__ import annotations

import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from hyposense.data.dataset import AccessScope, Dataset, SealedPartitionError
from hyposense.features.snapshot import FeatureBuilder, FeatureInputs
from hyposense.features.spec import UNION_NAMES
from hyposense.medication.dictionary import DrugDictionary
from hyposense.state.events import CGMReading, StateEvent
from hyposense.state.patient import EngineConfig, PatientState
from hyposense.state.stream import RecordingStream, order_recordings, recording_stream

META_COLUMNS = (
    "sufficient",
    "gap_before",
    "floor",
    "rapid_change",
    "warmup",
    "history_ok",
    "sensor_fault_suspected",
    "in_episode_causal",
)


@dataclass(frozen=True)
class RecordingFeatures:
    patient_key: str
    recording_key: str
    ts: npt.NDArray[np.int64]
    meta: dict[str, npt.NDArray[np.bool_]]
    X: npt.NDArray[np.float64]  # (readings, len(UNION_NAMES))
    seconds: dict[str, float] = field(default_factory=dict)  # update / feature wall time


def replay(
    stream: RecordingStream, engine: EngineConfig
) -> Iterator[tuple[StateEvent, PatientState]]:
    """Deterministic event-by-event replay of one recording (a fresh state per recording)."""
    state = PatientState.start(stream.context, engine)
    for e in stream.events:
        state = state.update(e)
        yield e, state


def build_recording(
    stream: RecordingStream, engine: EngineConfig, builder: FeatureBuilder
) -> RecordingFeatures:
    ts: list[int] = []
    rows: list[npt.NDArray[np.float64]] = []
    meta: dict[str, list[bool]] = {k: [] for k in META_COLUMNS}
    t_update = t_feat = 0.0
    state = PatientState.start(stream.context, engine)
    for e in stream.events:
        a = time.perf_counter()
        state = state.update(e)
        b = time.perf_counter()
        t_update += b - a
        if not isinstance(e, CGMReading):
            continue
        rows.append(builder.union(FeatureInputs.of(state)))
        t_feat += time.perf_counter() - b
        q = state.quality
        assert q is not None
        ts.append(e.ts)
        meta["sufficient"].append(q.sufficient)
        meta["gap_before"].append(q.gap_before)
        meta["floor"].append(q.floor)
        meta["rapid_change"].append(q.rapid_change)
        meta["warmup"].append(q.warmup)
        meta["history_ok"].append(q.history_ok)
        meta["sensor_fault_suspected"].append(q.sensor_fault_suspected)
        meta["in_episode_causal"].append(state.cgm.tracker.in_episode)
    X = np.vstack(rows) if rows else np.zeros((0, len(UNION_NAMES)))
    return RecordingFeatures(
        stream.context.patient_key,
        stream.context.recording_key,
        np.array(ts, dtype=np.int64),
        {k: np.array(v, dtype=bool) for k, v in meta.items()},
        X,
        {"update": t_update, "features": t_feat, "events": float(len(stream.events))},
    )


def tuning_streams(
    ds: Dataset,
    d: DrugDictionary,
    formulation_rules: dict[str, Any],
    plausible: Mapping[str, tuple[float, float]],
) -> list[RecordingStream]:
    if ds.scope is not AccessScope.TUNING_ONLY:
        raise SealedPartitionError(
            f"feature generation before freeze is restricted to TUNING_ONLY (got {ds.scope})"
        )
    frame = ds.summary.frame
    streams = []
    for rec in ds.recordings:
        key = rec.identity.recording_key
        row = {str(c): v for c, v in frame.loc[key].items()} if key in frame.index else None
        streams.append(recording_stream(rec, d, formulation_rules, row, plausible))
    by_patient: dict[str, list[RecordingStream]] = {}
    for s in streams:
        by_patient.setdefault(s.identity.patient_key, []).append(s)
    return [s for p in sorted(by_patient) for s in order_recordings(by_patient[p])]


def to_frame(parts: list[RecordingFeatures]) -> pd.DataFrame:
    """One row per CGM reading: identifiers, metadata, then the union features in spec order."""
    frames = []
    for p in parts:
        df = pd.DataFrame(p.X, columns=list(UNION_NAMES))
        df.insert(0, "ts", p.ts)
        df.insert(0, "recording_key", p.recording_key)
        df.insert(0, "patient_key", p.patient_key)
        for i, k in enumerate(META_COLUMNS):
            df.insert(3 + i, k, p.meta[k])
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
