"""PatientState: the per-recording digital twin (Blueprint §9, Table 25.2; ARCHITECTURE §4.4).

    PatientState
    ├── context      PatientContext           static summary row (allow-listed)
    ├── cgm          CGMState                 reading history + causal episode tracker
    ├── quality      DataQualityState         sufficiency flags at the latest reading
    ├── medication   MedicationExposureState  medication log + S3 engines evaluated at t
    ├── meals        AppendLog[MealEvent]
    ├── cbg          AppendLog[CBGReading]    display only (never a feature)
    ├── forecast     ForecastState            display / policy only (never a feature)
    └── ledger       OutcomeLedger            display / audit only (never a feature)

`update(event)` returns a NEW immutable state. It is deterministic, and it accepts events only in
the canonical order (ts, then dose -> meal -> cgm -> cbg, then source row). It uses nothing but
the previous state and the event, so a state at t can never depend on a later event.

**Recording boundary.** A state belongs to exactly one recording. Recordings are independent
streams (ANALYSIS_PLAN §0 item 10): CGM history, episodes, warm-up, meals, medication and
static context never carry over from another recording, even of the same patient. S2 found that
recording numbers are not always chronological. A new recording therefore always starts from
`PatientState.start(...)`, and an event of another recording is refused.

**Failures.** `update` raises a typed error on a contract violation (offline: fail loudly).
`try_update` (live path) returns the previous state tagged SYSTEM_ERROR. Snapshots of a tagged
state are refused, so a stale state is never presented as current (CLAUDE.md §29).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from typing import Any

from hyposense.common.hashing import sha256_json
from hyposense.data.quality import QualityThresholds
from hyposense.medication.events import MedicationEvent
from hyposense.medication.exposure import KernelSet, load_kernel_set
from hyposense.state.cgm import CGMState, EpisodeRule
from hyposense.state.context import PatientContext
from hyposense.state.events import (
    CBGReading,
    CGMReading,
    MealEvent,
    StateEvent,
    rank,
    validate,
)
from hyposense.state.history import AppendLog
from hyposense.state.ledger import Forecast, ForecastState, OutcomeLedger
from hyposense.state.medication import MedicationExposureState
from hyposense.state.quality import DataQualityState, SufficiencyRule, assess


class StateError(RuntimeError):
    """Base class of state-engine contract violations."""


class OutOfOrderEventError(StateError):
    pass


class RecordingBoundaryError(StateError):
    pass


@dataclass(frozen=True)
class EngineConfig:
    episode: EpisodeRule
    thresholds: QualityThresholds
    sufficiency: SufficiencyRule
    kernels: KernelSet
    horizon_s: int

    @classmethod
    def from_config(cls, cfg: dict[str, Any], pharma: dict[str, Any]) -> EngineConfig:
        ev, el, po = cfg["event"], cfg["eligibility"], cfg["policy"]
        if int(ev["min_run"]) != 2:
            raise ValueError("the causal episode tracker implements min_run = 2 (Table 5.1)")
        restart = el.get("warmup_restart_after_gap_min")
        return cls(
            episode=EpisodeRule(
                float(ev["threshold_mgdl"]),
                int(ev["max_step_min"]) * 60,
                int(ev["max_gap_min"]) * 60,
            ),
            thresholds=QualityThresholds(
                float(po["max_gap_min"]),
                float(po["floor_mgdl"]),
                float(po["max_rate_mgdl_per_min"]),
                float(po["warmup_min"]),
            ),
            sufficiency=SufficiencyRule(
                history_s=int(el["history_min"]) * 60,
                min_readings_in_history=int(el["min_readings_in_history"]),
                warmup_s=int(el["min_time_since_start_min"]) * 60,
                warmup_restart_after_gap_s=None if restart is None else int(restart) * 60,
                sensor_fault_max_step_s=int(ev["max_step_min"]) * 60,
            ),
            kernels=load_kernel_set(pharma, float(cfg["exposure"]["timing_unknown_after_h"])),
            horizon_s=int(ev["horizon_min"]) * 60,
        )


@dataclass(frozen=True)
class PatientState:
    patient_key: str
    recording_key: str
    config: EngineConfig = field(repr=False)
    context: PatientContext
    cgm: CGMState
    medication: MedicationExposureState
    meals: AppendLog[MealEvent] = field(default_factory=AppendLog)
    cbg: AppendLog[CBGReading] = field(default_factory=AppendLog)
    quality: DataQualityState | None = None  # at the latest CGM reading
    forecast: ForecastState = field(default_factory=ForecastState)
    ledger: OutcomeLedger = field(default_factory=OutcomeLedger)
    ts: int | None = None  # time of the latest processed event
    last_rank: int = -1
    n_events: int = 0
    error: str | None = None  # SYSTEM_ERROR tag (live path)

    @classmethod
    def start(cls, context: PatientContext, config: EngineConfig) -> PatientState:
        return cls(
            patient_key=context.patient_key,
            recording_key=context.recording_key,
            config=config,
            context=context,
            cgm=CGMState.empty(config.episode),
            medication=MedicationExposureState(config.kernels, context.prescribed_classes),
            ledger=OutcomeLedger(horizon_s=config.horizon_s),
        )

    # ------------------------------------------------------------------ transitions
    def update(self, e: StateEvent) -> PatientState:
        if self.error is not None:
            raise StateError(f"state is in SYSTEM_ERROR ({self.error}); start a new state")
        validate(e)
        if e.recording_key != self.recording_key:
            raise RecordingBoundaryError(
                f"event of recording {e.recording_key!r} sent to state of {self.recording_key!r}"
            )
        r = int(rank(e))
        if self.ts is not None and (e.ts < self.ts or (e.ts == self.ts and r < self.last_rank)):
            raise OutOfOrderEventError(
                f"event (ts={e.ts}, rank={r}) after (ts={self.ts}, rank={self.last_rank})"
            )
        base = replace(self, ts=e.ts, last_rank=r, n_events=self.n_events + 1)
        if isinstance(e, MedicationEvent):
            return replace(base, medication=self.medication.add(e))
        if isinstance(e, MealEvent):
            return replace(base, meals=self.meals.append(e))
        if isinstance(e, CBGReading):
            return replace(base, cbg=self.cbg.append(e))
        assert isinstance(e, CGMReading)
        if self.cgm.n and e.ts == int(self.cgm.series.ts[-1]):
            raise OutOfOrderEventError(f"second CGM reading at ts={e.ts}")
        before = self.cgm.tracker.n_onsets
        cgm = self.cgm.add(e.ts, e.value_mgdl)
        new_onset = cgm.tracker.onset_ts if cgm.tracker.n_onsets > before else None
        quality = assess(
            cgm.series,
            self.quality,
            self.config.thresholds,
            self.config.sufficiency,
            self.recording_key,
        )
        return replace(
            base,
            cgm=cgm,
            quality=quality,
            ledger=self.ledger.reconcile(e.ts, new_onset),
        )

    def try_update(self, e: StateEvent) -> PatientState:
        """Live-path update: never raises. On failure the PREVIOUS state comes back tagged
        SYSTEM_ERROR, and snapshots of it are refused."""
        try:
            return self.update(e)
        except Exception as exc:
            return replace(self, error=f"{type(exc).__name__}: {exc}")

    def record_forecast(self, f: Forecast) -> PatientState:
        """Ledger a forecast made at the current reading (display / audit only)."""
        if self.ts is None or f.ts != self.ts:
            raise StateError("a forecast must be made at the current state time")
        return replace(
            self,
            forecast=replace(self.forecast, last_forecast=f),
            ledger=self.ledger.add(f),
        )

    # ------------------------------------------------------------------ inspection
    @property
    def at_cgm_reading(self) -> bool:
        """True if the latest CGM reading is the state time (a decision time)."""
        return self.cgm.n > 0 and self.ts == int(self.cgm.series.ts[-1])

    def digest(self) -> str:
        """Content hash of the full state (for replay determinism tests)."""
        h = hashlib.sha256()
        h.update(self.cgm.series.ts.tobytes())
        h.update(self.cgm.series.values.tobytes())
        doc = {
            "patient_key": self.patient_key,
            "recording_key": self.recording_key,
            "ts": self.ts,
            "last_rank": self.last_rank,
            "n_events": self.n_events,
            "cgm_series": h.hexdigest(),
            "tracker": repr(self.cgm.tracker),
            "last_low_ts": self.cgm.last_low_ts,
            "quality": repr(self.quality),
            "medication": [repr(m) for m in self.medication.events],
            "meals": [repr(m) for m in self.meals],
            "cbg": [repr(c) for c in self.cbg],
            "forecast": repr(self.forecast),
            "ledger_pending": [repr(f) for f in self.ledger.pending],
            "ledger_resolved": [repr(x) for x in self.ledger.resolved],
            "context": repr(self.context),
            "error": self.error,
        }
        return sha256_json(doc)
