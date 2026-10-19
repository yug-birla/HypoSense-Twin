"""Population assembly for the confirmatory run (S9) and its T-only rehearsal (ANALYSIS_PLAN §5.7).

One table row per CGM reading of every patient in the run, built with the canonical modules only
(`recording_stream`, `features.build.build_recording`, `evaluation.data.build_eval_recording`,
`labels`), so the S9 features, labels and policy decisions are exactly those of S4-S7.

E records are read only after `data.dataset.unlock_sealed_partition` accepted a verified freeze
record (official mode). Streams are built in the main process (the seal check runs there);
workers receive finished streams and records.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from hyposense.common.config import load_config
from hyposense.data.loader import cgm_series
from hyposense.data.records import Recording
from hyposense.evaluation.data import EvalRecording, build_eval_recording, replay_decisions
from hyposense.evaluation.devdata import (
    CBG_PAIR_S,
    DevData,
    _y,
    cbg_contradicted,
    pb6_window_mask,
)
from hyposense.evaluation.m0_run import MODEL as M0
from hyposense.evaluation.m0_run import treated_patient_keys
from hyposense.features.build import RecordingFeatures, build_recording
from hyposense.features.cgm import CGMFeatureConfig
from hyposense.features.snapshot import FeatureBuilder
from hyposense.features.spec import UNION_NAMES
from hyposense.labels.annotations import floor_runs
from hyposense.labels.config import LabelConfig
from hyposense.labels.validity import cbg_series, pair_cbg_cgm
from hyposense.medication.dictionary import load_dictionary
from hyposense.medication.events import MedicationEvent
from hyposense.models.m0 import M0Scorer
from hyposense.policy.decide import PolicyRules
from hyposense.state.events import CGMReading, StateEvent, sort_key
from hyposense.state.patient import EngineConfig
from hyposense.state.stream import RecordingStream, recording_stream

ID_COLUMNS = ["patient_key", "recording_key", "ts", "eligible", "y", "treated", "pb6_exclude"]


@dataclass(frozen=True)
class Population:
    mode: str  # "official" | "rehearsal"
    dev: DevData  # canonical table + eval recordings (S5/S6 harness input)
    evaluation_patients: tuple[str, ...]  # E (official) or T (rehearsal)
    always_train: frozenset[str]  # T in official mode; empty in rehearsal
    streams: dict[str, RecordingStream]
    records: dict[str, Recording]


# ---------------------------------------------------------------- workers
_W: dict[str, Any] = {}


def _engine_builder(pharma: dict[str, Any]) -> tuple[EngineConfig, FeatureBuilder]:
    cfg = load_config()
    return EngineConfig.from_config(cfg, pharma), FeatureBuilder(cfg)


def _init(pharma: dict[str, Any]) -> None:
    from hyposense.common.runtime import disable_power_throttling

    disable_power_throttling()
    cfg = load_config()
    _W["engine"], _W["builder"] = _engine_builder(pharma)
    _W["rules"] = PolicyRules.from_config(cfg)
    _W["lc"] = LabelConfig.from_config(cfg)
    _W["m0"] = M0Scorer(CGMFeatureConfig.from_config(cfg))


def _task_full(args: tuple[Recording, RecordingStream]) -> tuple[RecordingFeatures, EvalRecording]:
    rec, stream = args
    feats = build_recording(stream, _W["engine"], _W["builder"])
    er = build_eval_recording(rec, stream, _W["engine"], _W["rules"], _W["lc"], {M0: _W["m0"]})
    return feats, er


def _task_features(stream: RecordingStream) -> RecordingFeatures:
    return build_recording(stream, _W["engine"], _W["builder"])


def _task_reduced(stream: RecordingStream) -> tuple[RecordingFeatures, Any, Any]:
    """R2: features, (ts, gate codes) and M0 scores of a reduced stream."""
    feats = build_recording(stream, _W["engine"], _W["builder"])
    ts, codes, sc = replay_decisions(stream, _W["engine"], _W["rules"], {M0: _W["m0"]})
    return feats, (ts, codes), sc[M0]


def _pool(workers: int, pharma: dict[str, Any]) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(workers, initializer=_init, initargs=(pharma,))


# ---------------------------------------------------------------- assembly
def streams_for(
    records: Sequence[Recording], summary: Any, pharma: dict[str, Any]
) -> dict[str, RecordingStream]:
    cfg = load_config()
    d = load_dictionary()
    plaus = {k: (float(v[0]), float(v[1])) for k, v in cfg["features"]["static_plausible"].items()}
    out = {}
    for rec in records:
        key = rec.identity.recording_key
        frame = summary.frame
        row = {str(c): v for c, v in frame.loc[key].items()} if key in frame.index else None
        out[key] = recording_stream(rec, d, pharma["formulation_rules"], row, plaus)
    return out


def assemble(
    records: Sequence[Recording],
    summary: Any,
    partition_of: Mapping[str, str],
    mode: str,
    workers: int,
) -> Population:
    if mode not in ("official", "rehearsal"):
        raise ValueError(mode)
    cfg, pharma = load_config(), load_config("pharma.yaml")
    recs_sorted = sorted(records, key=lambda r: r.identity.recording_key)
    streams = streams_for(recs_sorted, summary, pharma)
    with _pool(workers, pharma) as pool:
        out = list(
            pool.map(_task_full, [(r, streams[r.identity.recording_key]) for r in recs_sorted])
        )
    h = int(cfg["event"]["horizon_min"]) * 60
    treated = treated_patient_keys()
    parts, offsets, start = [], {}, 0
    eval_recs: list[EvalRecording] = []
    for rec, (feats, er) in zip(recs_sorted, out, strict=True):
        if not np.array_equal(feats.ts, er.ts):
            raise AssertionError(f"{er.recording_key}: features and labels misaligned")
        y = _y(er.ts, er.onsets, h)
        s = cgm_series(rec)
        bounds = [(int(s.ts[a]), int(s.ts[b - 1])) for a, b in floor_runs(s.ts, s.value)]
        ex = pb6_window_mask(er.ts, er.eligible, bounds, h)
        cb, cg = pair_cbg_cgm(cbg_series(rec), s.ts, s.value, CBG_PAIR_S)
        if cbg_contradicted(cb, cg):
            ex[:] = True
        df = pd.DataFrame(feats.X, columns=list(UNION_NAMES))
        df.insert(0, "pb6_exclude", ex)
        df.insert(0, "treated", er.patient_key in treated)
        df.insert(0, "y", y)
        df.insert(0, "eligible", er.eligible)
        df.insert(0, "ts", er.ts)
        df.insert(0, "recording_key", er.recording_key)
        df.insert(0, "patient_key", er.patient_key)
        parts.append(df)
        offsets[er.recording_key] = (start, start + len(df))
        start += len(df)
        eval_recs.append(er)
    table = pd.concat(parts, ignore_index=True)[ID_COLUMNS + list(UNION_NAMES)]
    has_l1: dict[str, bool] = {}
    for er in eval_recs:
        has_l1[er.patient_key] = has_l1.get(er.patient_key, False) or len(er.onsets) > 0
    strata = {p: int(p in treated) * 2 + int(v) for p, v in has_l1.items()}
    want = "E" if mode == "official" else "T"
    eval_patients = tuple(sorted(p for p in strata if partition_of[p] == want))
    always = (
        frozenset(p for p in strata if partition_of[p] == "T")
        if mode == "official"
        else frozenset()
    )
    dev = DevData(table, eval_recs, offsets, strata, treated, {"mode": mode}, {})
    return Population(
        mode,
        dev,
        eval_patients,
        always,
        streams,
        {r.identity.recording_key: r for r in recs_sorted},
    )


def rebuild_features(pop: Population, pharma: dict[str, Any], workers: int) -> pd.DataFrame:
    """The population table with every feature recomputed under another pharma config (SA6)."""
    keys = sorted(pop.streams)
    with _pool(workers, pharma) as pool:
        feats = list(pool.map(_task_features, [pop.streams[k] for k in keys]))
    table = pop.dev.table.copy()
    for k, f in zip(keys, feats, strict=True):
        a, b = pop.dev.offsets[k]
        if not np.array_equal(table["ts"].to_numpy()[a:b], f.ts):
            raise AssertionError(f"{k}: rebuilt features misaligned")
        table.iloc[a:b, len(ID_COLUMNS) :] = f.X
    return table


def scaled_pharma(factor: float) -> dict[str, Any]:
    """SA6 (§5.7 item 20): insulin `t_dur_min` and secretagogue `t_half_min` x factor."""
    import copy

    pharma = copy.deepcopy(load_config("pharma.yaml"))
    for group, key in (("insulin", "t_dur_min"), ("secretagogue", "t_half_min")):
        for spec in pharma[group].values():
            if isinstance(spec, dict) and isinstance(spec.get(key), dict):
                spec[key]["value"] = float(spec[key]["value"]) * factor
    return pharma


# ---------------------------------------------------------------- perturbations (R1, R2)
def jitter_doses(stream: RecordingStream, minutes: float, seed: int) -> RecordingStream:
    """R1: every medication event time + U(-minutes, +minutes) (whole seconds)."""
    rng = np.random.default_rng(seed)
    events: list[StateEvent] = []
    for e in stream.events:
        if isinstance(e, MedicationEvent):
            shift = round(float(rng.uniform(-minutes, minutes)) * 60)
            e = dataclasses.replace(e, ts=e.ts + shift)
        events.append(e)
    events.sort(key=sort_key)
    return dataclasses.replace(stream, events=tuple(events))


def drop_cgm(stream: RecordingStream, share: float, blocks: bool, seed: int) -> RecordingStream:
    """R2: remove `share` of the CGM readings, at random or as U(60, 120)-min blocks."""
    rng = np.random.default_rng(seed)
    cgm_idx = [i for i, e in enumerate(stream.events) if isinstance(e, CGMReading)]
    n = len(cgm_idx)
    target = int(np.ceil(share * n))
    drop: set[int] = set()
    if not blocks:
        drop = set(rng.choice(n, size=target, replace=False).tolist()) if target else set()
    else:
        ts = np.array([stream.events[i].ts for i in cgm_idx])
        while len(drop) < target and n:
            start = int(rng.integers(0, n))
            length = float(rng.uniform(60, 120)) * 60
            hit = np.flatnonzero((ts >= ts[start]) & (ts < ts[start] + length))
            drop.update(hit.tolist())
    removed = {cgm_idx[k] for k in drop}
    events = tuple(e for i, e in enumerate(stream.events) if i not in removed)
    return dataclasses.replace(stream, events=events)


def rebuild_streams(
    streams: Mapping[str, RecordingStream], workers: int, reduced: bool
) -> dict[str, Any]:
    keys = sorted(streams)
    pharma = load_config("pharma.yaml")
    with _pool(workers, pharma) as pool:
        if reduced:
            res = list(pool.map(_task_reduced, [streams[k] for k in keys]))
        else:
            res = [(f, None, None) for f in pool.map(_task_features, [streams[k] for k in keys])]
    return dict(zip(keys, res, strict=True))


def default_workers() -> int:
    return max(1, min(4, (os.cpu_count() or 2) - 1))


def as_bool(a: npt.NDArray[Any]) -> npt.NDArray[np.bool_]:
    out: npt.NDArray[np.bool_] = np.asarray(a, dtype=bool)
    return out
