"""Live twin runner for ONE recording (Blueprint Fig. 9.1 / 14.1; ARCHITECTURE §4.10):

    event -> input validation -> PatientState.try_update -> [CGM reading]
          -> policy gate -> FeatureBuilder.snapshot -> model + calibrator -> policy.decide
          -> forecast ledger -> DecisionRecord

The runner orchestrates canonical modules only; it contains no feature, exposure, risk or policy
rule of its own (CLAUDE.md §26). Offline (`features.build`, `evaluation.data.replay_decisions`)
and live use the same state engine, feature builder and policy gate.

Error handling and recovery (S7; CLAUDE.md §29; Table 14.1 priority 1):
- A rejected event (malformed, out of order, duplicate, wrong recording, implausible value)
  produces a SYSTEM_ERROR decision at the event time and is quarantined. The PatientState is
  immutable and `try_update` returns the PREVIOUS valid state, so the rejected event cannot
  corrupt later state. Processing resumes with the next event (recovery).
- After a rejected dose, meal or CBG event, forecasts carry the tag EVENT_REJECTED for the
  medication timing-unknown window (36 h): the exposure state may be incomplete.
- An exception in the gate, feature snapshot or inference is SYSTEM_ERROR for that reading; no
  previous probability is reused. The next reading is decided afresh.
- After `max_consecutive_errors` rejected events in a row the runner HALTS (circuit breaker):
  every later event is refused and the state stays SYSTEM_ERROR until the replay is reset.
- The current decision is always the latest one. The last decision with a probability is kept
  separately (`last_forecast`) and is only ever displayed with its own time stamp.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from hyposense.features.snapshot import FeatureBuilder
from hyposense.medication.events import MedicationEvent
from hyposense.medication.exposure import QualityState
from hyposense.models.artifact import RuntimeModel
from hyposense.policy.decide import (
    PolicyDecision,
    PolicyState,
    decide,
    gate,
    system_error,
)
from hyposense.state.events import CBGReading, CGMReading, MealEvent, StateEvent
from hyposense.state.ledger import Forecast
from hyposense.state.patient import EngineConfig, PatientState
from hyposense.state.stream import RecordingStream

PLAUSIBLE_MGDL = (20.0, 600.0)  # Blueprint Table 25.1 Observation invariant


class ImplausibleInputError(ValueError):
    pass


@dataclass(frozen=True)
class Pipeline:
    engine: EngineConfig
    builder: FeatureBuilder
    model: RuntimeModel
    max_consecutive_errors: int = 5

    @property
    def rejected_tag_s(self) -> int:
        return self.engine.kernels.timing_unknown_s


@dataclass(frozen=True)
class DecisionRecord:
    seq: int  # index of the triggering event in the recording's stream
    decision_id: str
    patient_key: str
    recording_key: str
    decision: PolicyDecision
    raw: float | None = None
    input_digest: str | None = None
    quality: tuple[str, ...] = ()
    error: str | None = None  # exception type for SYSTEM_ERROR (never a stack trace)

    def log(self, model: RuntimeModel) -> dict[str, Any]:
        """The decisions.jsonl record (Blueprint §14.3). Deterministic: no wall-clock field."""
        d = self.decision
        comp = model.manifest["compatibility"]
        return {
            "decision_id": self.decision_id,
            "seq": self.seq,
            "ts": d.ts,
            "patient_key": self.patient_key,
            "recording_key": self.recording_key,
            "model_version": model.model_version,
            "model_status": model.status,
            "config_sha256": comp["config_sha256"],
            "feature_spec_sha256": comp["feature_spec_sha256"],
            "p": d.p,
            "raw": self.raw,
            "tau_alert": model.thresholds.tau_alert,
            "tau_watch": model.thresholds.tau_watch,
            "state": d.state.value,
            "reasons": list(d.reasons),
            "tags": list(d.tags),
            "notify": d.notify,
            "quality": list(self.quality),
            "input_digest": self.input_digest,
            "error": self.error,
        }


def check_input(e: StateEvent) -> None:
    """Live-boundary plausibility (the offline loader enforces the same through the data audit)."""
    if isinstance(e, CGMReading | CBGReading):
        v = e.value_mgdl
        if not (math.isfinite(v) and PLAUSIBLE_MGDL[0] <= v <= PLAUSIBLE_MGDL[1]):
            raise ImplausibleInputError(f"glucose value {v} outside {PLAUSIBLE_MGDL}")
    if not isinstance(e.ts, int) or isinstance(e.ts, bool):
        raise ImplausibleInputError("event time must be an integer epoch second")


@dataclass
class TwinRunner:
    stream: RecordingStream
    pipe: Pipeline
    state: PatientState = field(init=False)
    decisions: list[DecisionRecord] = field(default_factory=list, init=False)
    rejected: list[dict[str, Any]] = field(default_factory=list, init=False)
    consecutive_errors: int = field(default=0, init=False)
    halted: bool = field(default=False, init=False)
    rejected_until: int | None = field(default=None, init=False)
    last_snapshot: Any = field(default=None, init=False)
    unknown_outcomes: int | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.state = PatientState.start(self.stream.context, self.pipe.engine)

    # ------------------------------------------------------------------ inspection
    @property
    def recording_key(self) -> str:
        return self.stream.identity.recording_key

    @property
    def patient_key(self) -> str:
        return self.stream.identity.patient_key

    @property
    def current(self) -> DecisionRecord | None:
        return self.decisions[-1] if self.decisions else None

    @property
    def last_forecast(self) -> DecisionRecord | None:
        for r in reversed(self.decisions):
            if r.decision.p is not None:
                return r
        return None

    # ------------------------------------------------------------------ processing
    def _record(self, seq: int, d: PolicyDecision, **kw: Any) -> DecisionRecord:
        suffix = "" if d.state is not PolicyState.SYSTEM_ERROR else f"#e{seq}"
        rec = DecisionRecord(
            seq,
            f"{self.recording_key}@{d.ts}{suffix}",
            self.patient_key,
            self.recording_key,
            d,
            **kw,
        )
        self.decisions.append(rec)
        return rec

    def feed(self, seq: int, e: StateEvent) -> DecisionRecord | None:
        """Process one event. Never raises. Returns the decision it produced, if any."""
        if self.halted:
            self.rejected.append({"seq": seq, "ts": e.ts, "error": "RunnerHalted"})
            return None
        try:
            check_input(e)
            new = self.state.try_update(e)
            error = new.error
        except Exception as exc:  # defensive: try_update never raises
            error = f"{type(exc).__name__}: {exc}"
        if error is not None:
            return self._reject(seq, e, error)
        self.consecutive_errors = 0
        self.state = new
        if not isinstance(e, CGMReading):
            return None
        return self._decide(seq, e)

    def _reject(self, seq: int, e: StateEvent, error: str) -> DecisionRecord:
        kind = error.split(":", 1)[0]
        self.rejected.append({"seq": seq, "ts": e.ts, "event": type(e).__name__, "error": kind})
        self.consecutive_errors += 1
        if isinstance(e, MedicationEvent | MealEvent | CBGReading):
            # window from the processing time (a rejected late event carries an old ts)
            start = max(e.ts, self.state.ts) if self.state.ts is not None else e.ts
            self.rejected_until = start + self.pipe.rejected_tag_s
        reason = "EVENT_REJECTED"
        if self.consecutive_errors >= self.pipe.max_consecutive_errors:
            self.halted = True
            reason = "RUNNER_HALTED"
        ts = e.ts if isinstance(e.ts, int) else (self.state.ts or 0)
        return self._record(seq, system_error(ts, reason), error=kind)

    def _decide(self, seq: int, e: CGMReading) -> DecisionRecord:
        m = self.pipe.model
        s = self.state
        t = e.ts
        raw = p = None
        digest = None
        tags: list[str] = []
        error = None
        try:
            g = gate(s, m.rules)
            if g.queries_model:
                snap = self.pipe.builder.snapshot(s, m.level)
                self.last_snapshot = snap
                digest = snap.digest
                raw, p = m.predict(snap)
                if m.out_of_range(snap):
                    tags.append("LOW_CONFIDENCE")
                med_q = s.medication.at(t).quality
                tags += [
                    f"MED_TIMING_UNKNOWN:{c}"
                    for c, q in sorted(med_q.items())
                    if q is QualityState.TIMING_UNKNOWN
                ]
                if self.rejected_until is not None and t <= self.rejected_until:
                    tags.append("EVENT_REJECTED")
            d = decide(g, p, t, s.forecast.last_notification_ts, m.rules, m.thresholds, tuple(tags))
        except Exception as exc:
            d = system_error(t, "INFERENCE_ERROR")
            raw = None
            error = type(exc).__name__
        if d.p is None:
            raw = None
        q = s.quality.reasons if s.quality is not None else ()
        try:
            s = s.record_forecast(Forecast(t, m.level, m.model_version, d.p))
            if d.notify:
                s = s.record_notification(t)
            self.state = s
        except Exception as exc:  # ledger failure must not hide the decision
            d = system_error(t, "LEDGER_ERROR")
            error = type(exc).__name__
        return self._record(seq, d, raw=raw, input_digest=digest, quality=q, error=error)

    def finish(self) -> None:
        """Recording end: pending forecasts are reconciled or OUTCOME-UNKNOWN (§2 item 4)."""
        if self.unknown_outcomes is not None or not self.state.cgm.n:
            return
        ledger, unknown = self.state.ledger.finalize(int(self.state.cgm.series.ts[-1]))
        from dataclasses import replace

        self.state = replace(self.state, ledger=ledger)
        self.unknown_outcomes = len(unknown)
