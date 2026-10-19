"""Evaluation input contract (OFFLINE; ANALYSIS_PLAN §2). Model-agnostic.

One `EvalRecording` per recording. Arrays are aligned with the recording's CGM readings, which
are the policy decision times:
- `queried`  the policy requests a forecast here (gate state None: sufficient data, CGM >= 70,
             not causally LOW NOW). Computed by `policy.decide.gate` on the S4 state replay, the
             same function the live system uses.
- `score`    the model's score (higher = riskier). It is only used where `queried`.
- `eligible` label-eligible prediction time (S2 label builder; hits are counted only here).
- `onsets`   L1 episode onsets (S2 label builder); `warnable` per onset (S2 definition).
- `first_ts`, `last_ts`: the monitored span (first to last CGM reading; ANALYSIS_PLAN §2.5).

Any model plugs in by supplying scores at the readings. M0 scores come from the state
(`models.m0`); learned models (S6) supply predictions joined on (recording_key, ts).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace

import numpy as np
import numpy.typing as npt

from hyposense.data.records import Recording
from hyposense.labels.build import label_recording
from hyposense.labels.config import LabelConfig
from hyposense.labels.eligibility import warnable_onsets
from hyposense.policy.decide import PolicyRules, PolicyState, gate
from hyposense.state.events import CGMReading
from hyposense.state.patient import EngineConfig, PatientState
from hyposense.state.stream import RecordingStream

GATE_CODES = {
    None: 0,
    PolicyState.LOW_NOW: 1,
    PolicyState.INSUFFICIENT_DATA: 2,
    PolicyState.SYSTEM_ERROR: 3,
}
Scorer = Callable[[PatientState], float]


@dataclass(frozen=True)
class EvalRecording:
    patient_key: str
    recording_key: str
    ts: npt.NDArray[np.int64]
    gate_code: npt.NDArray[np.int8]  # GATE_CODES
    eligible: npt.NDArray[np.bool_]
    onsets: npt.NDArray[np.int64]
    warnable: npt.NDArray[np.bool_]
    first_ts: int
    last_ts: int
    scores: dict[str, npt.NDArray[np.float64]] = field(default_factory=dict)
    # S9 sensitivity variants only (ANALYSIS_PLAN §5.7 items 18-19); None = canonical behaviour.
    # notif_onsets: onsets used to classify notifications when `onsets` holds a subset
    # (excluded episodes leave the sensitivity denominator but still make a notification TRUE).
    notif_onsets: npt.NDArray[np.int64] | None = None
    # notif_exclude: (start, end) windows; notifications whose (t, t + H] overlaps one are removed
    # from all notification classes (SA9-ii).
    notif_exclude: tuple[tuple[int, int], ...] | None = None

    @property
    def queried(self) -> npt.NDArray[np.bool_]:
        out: npt.NDArray[np.bool_] = self.gate_code == 0
        return out

    @property
    def days(self) -> float:
        return (self.last_ts - self.first_ts) / 86400.0

    def with_scores(self, name: str, values: npt.NDArray[np.float64]) -> EvalRecording:
        if len(values) != len(self.ts):
            raise ValueError("scores must align with the recording's readings")
        return replace(self, scores={**self.scores, name: np.asarray(values, dtype=np.float64)})


def replay_decisions(
    stream: RecordingStream,
    engine: EngineConfig,
    rules: PolicyRules,
    scorers: Mapping[str, Scorer],
) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int8], dict[str, npt.NDArray[np.float64]]]:
    """Causal replay: at every CGM reading, the policy gate and each scorer's score."""
    s = PatientState.start(stream.context, engine)
    ts: list[int] = []
    codes: list[int] = []
    sc: dict[str, list[float]] = {k: [] for k in scorers}
    for e in stream.events:
        s = s.update(e)
        if not isinstance(e, CGMReading):
            continue
        ts.append(e.ts)
        codes.append(GATE_CODES[gate(s, rules).state])
        for k, f in scorers.items():
            sc[k].append(f(s))
    return (
        np.array(ts, dtype=np.int64),
        np.array(codes, dtype=np.int8),
        {k: np.array(v, dtype=np.float64) for k, v in sc.items()},
    )


def build_eval_recording(
    rec: Recording,
    stream: RecordingStream,
    engine: EngineConfig,
    rules: PolicyRules,
    lc: LabelConfig,
    scorers: Mapping[str, Scorer],
) -> EvalRecording:
    ts, codes, scores = replay_decisions(stream, engine, rules, scorers)
    lab = label_recording(rec, lc)
    if not np.array_equal(lab.series.ts, ts):
        raise AssertionError(f"{rec.identity.recording_key}: label and state readings differ")
    onsets = np.array(sorted(e.onset_ts for e in lab.l1), dtype=np.int64)
    warn = warnable_onsets(lab.prediction, onsets, lc)
    return EvalRecording(
        patient_key=rec.identity.patient_key,
        recording_key=rec.identity.recording_key,
        ts=ts,
        gate_code=codes,
        eligible=lab.prediction.eligible.copy(),
        onsets=onsets,
        warnable=warn,
        first_ts=int(ts[0]),
        last_ts=int(ts[-1]),
        scores=scores,
    )


def as_label_eligible_decisions(recs: Sequence[EvalRecording]) -> list[EvalRecording]:
    """LEGACY REPRODUCTION ONLY (blueprint executable spec audit2.py): forecasts are made and
    notifications issued at label-eligible times only. The canonical protocol (§2) uses the
    policy gate instead. Only the decision-time set changes; every metric function is the same."""
    out = []
    for r in recs:
        codes = np.where(r.eligible, 0, 2).astype(np.int8)
        out.append(replace(r, gate_code=codes))
    return out
