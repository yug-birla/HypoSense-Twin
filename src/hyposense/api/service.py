"""Replay service behind the API: orchestration only (CLAUDE.md §26). The artefact is verified at
construction; an ArtifactError propagates and the server does not start (Blueprint §18).

Data scope: TUNING partition (T) only before freeze (ARCHITECTURE §4.10; sealed E is refused by
`features.build.tuning_streams` and `state.stream.recording_stream`). Every view is labelled
with the model status.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import math
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import numpy as np

from hyposense.api import schemas as S
from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.features.cgm import CGMFeatureConfig, trend_slope
from hyposense.features.snapshot import FeatureBuilder
from hyposense.features.spec import BY_NAME
from hyposense.intake.draft import Draft
from hyposense.intake.session import LiveSession
from hyposense.models.artifact import RuntimeModel, load_artifact
from hyposense.policy.decide import PolicyDecision, PolicyState, current
from hyposense.policy.messages import (
    GROUP_LABEL,
    LABEL_CAVEAT,
    REASON_TEXT,
    clock_text,
    probability_text,
    reason_line,
    summary,
    texts,
    trend_category,
)
from hyposense.replay.runner import EXPOSURE_DISPLAY, DecisionRecord, Pipeline, TwinRunner
from hyposense.replay.session import DecisionLog, Emitted, ReplaySession
from hyposense.state.patient import EngineConfig
from hyposense.state.stream import RecordingStream

LOG_ROOT = REPO_ROOT / "logs" / "replay"
SOURCE_LABEL = "Replay of TUNING-partition (T) records; DEVELOPMENT model; not held-out evidence"
HELD_OUT_LABEL = (
    "Held-out replay: each patient is scored by the fold model that never saw that patient "
    "(run {run}); {status}"
)
STATE_ORDER = {
    PolicyState.SYSTEM_ERROR: 0,
    PolicyState.LOW_NOW: 1,
    PolicyState.ALERT: 2,
    PolicyState.WATCH: 3,
    PolicyState.INSUFFICIENT_DATA: 4,
    PolicyState.NO_ALERT: 5,
}
TRACE_S = 24 * 3600
_CTX_LABEL = {
    "age_y": "age",
    "sex_male": "sex",
    "bmi": "BMI",
    "weight_kg": "weight",
    "diabetes_duration_y": "diabetes duration",
    "hba1c_mmol_mol": "HbA1c",
    "egfr": "eGFR",
    "c_peptide_fasting_nmol_l": "fasting C-peptide",
}
REPLAY = "HISTORICAL_REPLAY"
NEW_DATA = "NEW_DATA_SESSION"
SUBSCRIBER_QUEUE = 1000
MAX_SUBSCRIBERS = 16
INFO_TAG_PREFIXES = ("MED_TIMING_UNKNOWN", "EVENT_REJECTED")
LEDGER_ROWS = 50
S6_RUN_ID = re.compile(r"^T-AGG-dev-s6-\d{8}T\d{6}Z$")
MAX_CONSECUTIVE_ERRORS = 5


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


class InvalidRequest(ValueError):
    """A request that is well-formed but not applicable (422). Other ValueErrors are internal."""


class Busy(RuntimeError):
    pass


def load_tuning_streams(cfg: dict[str, Any], pharma: dict[str, Any]) -> list[RecordingStream]:
    from hyposense.data.dataset import AccessScope, load_dataset
    from hyposense.features.build import tuning_streams
    from hyposense.medication.dictionary import load_dictionary

    plaus = {k: (float(v[0]), float(v[1])) for k, v in cfg["features"]["static_plausible"].items()}
    ds = load_dataset(AccessScope.TUNING_ONLY)
    return tuning_streams(ds, load_dictionary(), pharma["formulation_rules"], plaus)


def decision_view(rec: DecisionRecord | None, d: PolicyDecision, status: str) -> S.DecisionView:
    return S.DecisionView(
        decision_id=rec.decision_id if rec is not None and rec.decision is d else None,
        ts=d.ts,
        state=d.state.value,
        p=d.p,
        p_text=probability_text(d.p),
        reasons=list(d.reasons),
        tags=list(d.tags),
        notify=d.notify,
        texts=list(texts(d)),
        model_status=status,
    )


@dataclass(frozen=True)
class HeldOut:
    """Held-out replay (Blueprint §15; ANALYSIS_PLAN §5.7 item 33): the fold bundle of a
    confirmatory run (or its T-only rehearsal) and the partition its patients belong to."""

    bundle_dir: Path  # <level>-folds-<ts>/ with fold-<k>/ artefacts and fold_map.json
    run_id: str
    partition: str  # "E" (official) or "T" (rehearsal)
    fold_files: dict[str, Any] | None = None  # from results.json; verified when given
    selected: str = ""  # §6 selected model; "" if unknown


class Service:
    def __init__(
        self,
        model_dir: Path,
        streams: Sequence[RecordingStream] | None = None,
        log_root: Path = LOG_ROOT,
        expected_manifest_sha256: str | None = None,
        held_out: HeldOut | None = None,
    ) -> None:
        self.cfg, self.pharma = load_config(), load_config("pharma.yaml")
        self.model: RuntimeModel = load_artifact(  # refuses on any mismatch
            model_dir, self.cfg, self.pharma, expected_manifest_sha256
        )
        self.pipe = Pipeline(
            EngineConfig.from_config(self.cfg, self.pharma),
            FeatureBuilder(self.cfg),
            self.model,
            MAX_CONSECUTIVE_ERRORS,
        )
        self.cgm_cfg = CGMFeatureConfig.from_config(self.cfg)
        if streams is None:
            if held_out is not None:
                raise ValueError("held-out replay needs explicitly loaded streams")
            streams = load_tuning_streams(self.cfg, self.pharma)
        self.held_out = held_out
        self.source = SOURCE_LABEL
        self.partition = "T"
        self.fold_of: dict[str, int] = {}
        self.fold_pipes: dict[int, Pipeline] = {}
        if held_out is not None:
            self._load_folds(held_out)
            streams = [s for s in streams if s.identity.patient_key in self.fold_of]
            if not streams:
                raise ValueError("no recording belongs to a held-out patient of the bundle")
        self.catalog = {s.identity.recording_key: s for s in streams}
        self._streams: list[RecordingStream] = []
        self.log_root = log_root
        self.session: ReplaySession | None = None
        self.session_id: str | None = None
        self._segments = 0
        self.playing = False
        self.speed = 120.0  # ARCHITECTURE §4.10 default
        self._clock = 0.0  # fractional clock offset carried between ticks
        self.acks: dict[str, dict[str, Any]] = {}
        self.decisions_logged = 0
        self.subscribers: set[asyncio.Queue[dict[str, Any] | None]] = set()
        self._shown_last: dict[str, tuple[str, float | None, str | None]] = {}
        self._confirm_view: dict[str, Any] | None = None
        # new-data intake (memory only; never research data; deleted on request or on exit)
        self.drafts: dict[str, Draft] = {}
        self.live: dict[str, LiveSession] = {}
        self._intake_seq = 0

    def _load_folds(self, h: HeldOut) -> None:
        self.fold_of = {
            str(p): int(k)
            for p, k in json.loads((h.bundle_dir / "fold_map.json").read_text("utf-8")).items()
        }
        for k in sorted(set(self.fold_of.values())):
            m = load_artifact(h.bundle_dir / f"fold-{k}", self.cfg, self.pharma)
            if h.fold_files is not None and m.manifest["files"] != h.fold_files[str(k)]:
                raise ValueError(f"fold-{k} artefact differs from the confirmatory record")
            self.fold_pipes[k] = dataclasses.replace(self.pipe, model=m)
        self.partition = h.partition
        status = (
            "CONFIRMATORY held-out scores"
            if h.partition == "E"
            else "REHEARSAL on T (development; never evidence)"
        )
        self.source = HELD_OUT_LABEL.format(run=h.run_id, status=status)
        lvl = next(iter(self.fold_pipes.values())).model.level
        if h.selected and h.selected != lvl:
            self.source += f"; replayed level {lvl} is NOT the selected model ({h.selected})"

    def _pipe_for(self, s: RecordingStream) -> Pipeline:
        return self.fold_pipes[self.fold_of[s.identity.patient_key]]

    # ------------------------------------------------------------------ session lifecycle
    def _new_log(self) -> DecisionLog:
        self._segments += 1
        self.session_id = f"{make_run_id('replay')}-{self._segments:03d}"
        self.decisions_logged = 0
        header = {
            "session_id": self.session_id,
            "created_utc": utc_now_iso(),
            "recordings": [s.identity.recording_key for s in self._streams],
            "model_version": self.model.model_version,
            "model_status": self.model.status,
            "artifact_manifest_sha256": self.model.manifest_sha256,
            "source": self.source,
            "fold_of": {
                s.identity.recording_key: self.fold_of[s.identity.patient_key]
                for s in self._streams
            }
            if self.held_out is not None
            else None,
        }
        return DecisionLog(self.log_root / self.session_id, header)

    def select(self, keys: Sequence[str]) -> None:
        unknown = [k for k in keys if k not in self.catalog]
        if unknown:
            raise NotFound(f"{len(unknown)} unknown or non-permitted recording key(s)")
        if len(set(keys)) != len(keys):
            raise InvalidRequest("a recording may be selected once")
        self._streams = [self.catalog[k] for k in keys]
        self.acks = {}  # acknowledgements persist across seek within one selection
        self._shown_last = {}
        if self.session is not None and self.session.log is not None:
            self.session.log.close()
        log = self._new_log()
        self.session = ReplaySession(
            self._streams, self.pipe, log, None if self.held_out is None else self._pipe_for
        )
        self.playing = False
        self._clock = 0.0
        self.publish({"type": "session", **self.status().model_dump()})

    def _require(self) -> ReplaySession:
        if self.session is None:
            raise Conflict("no replay selected")
        return self.session

    def _emit(self, out: list[Emitted]) -> None:
        s = self._require()
        for em in out:
            if em.record is None:
                continue
            self.decisions_logged += 1
            r = em.record
            d = r.decision
            msg = {
                "type": "error" if d.state is PolicyState.SYSTEM_ERROR else "decision",
                "recording_key": r.recording_key,
                "decision_id": r.decision_id,
                "ts": d.ts,
                "offset_s": em.offset,
                "state": d.state.value,
                "p": d.p,
                "p_text": probability_text(d.p),
                "reasons": list(d.reasons),
                "tags": list(d.tags),
                "notify": d.notify,
                "model_status": self.model.status,
            }
            self.publish(msg)
            if d.notify:
                self.publish({**msg, "type": "notification"})
        if s.finished:
            self.playing = False
        self._publish_bed_states()

    def _publish_bed_states(self) -> None:
        """Push every change of the DISPLAYED state (incl. staleness via policy.current), so a
        stream client never shows an expired decision as current (no UI-side policy logic)."""
        for r, now, _ in self._all_runners():
            rec, d = self._shown(r, now)
            did = rec.decision_id if rec is not None and rec.decision is d else None
            key = (d.state.value, d.p, did)
            if self._shown_last.get(r.recording_key) != key:
                self._shown_last[r.recording_key] = key
                self.publish(
                    {
                        "type": "bed_state",
                        "recording_key": r.recording_key,
                        "now_ts": now,
                        **decision_view(rec, d, self.model.status).model_dump(),
                    }
                )

    def step(self, n: int) -> None:
        self._emit(self._require().step(n))

    def advance(self, seconds: float) -> None:
        s = self._require()
        self._clock = max(self._clock, float(s.offset)) + seconds
        self._emit(s.advance_to(int(self._clock)))
        self.publish({"type": "tick", "offset_s": s.offset, "finished": s.finished})

    def advance_until_notification(self, max_events: int = 500_000) -> S.DemoEvent:
        """Guided demo: process the REAL replay event by event until the next ALERT notification
        (the first one in the fixed replay order; nothing is searched, skipped or staged)."""
        s = self._require()
        self.playing = False
        out: list[Emitted] = []
        found: DecisionRecord | None = None
        while not s.finished and len(out) < max_events:
            step = s.step(1)
            out += step
            rec = step[0].record if step else None
            if rec is not None and rec.decision.notify:
                found = rec
                break
        self._clock = float(s.offset)
        self._emit(out)
        self.publish({"type": "tick", "offset_s": s.offset, "finished": s.finished})
        return S.DemoEvent(
            found=found is not None,
            recording_key=None if found is None else found.recording_key,
            ts=None if found is None else found.decision.ts,
            p_text=None if found is None else probability_text(found.decision.p),
            offset_s=s.offset,
            finished=s.finished,
        )

    def seek(self, offset: int) -> None:
        s = self._require()
        if offset > s.duration:
            raise InvalidRequest(f"offset beyond the replay duration ({s.duration} s)")
        s.seek(offset, self._new_log())
        self.decisions_logged = sum(len(r.decisions) for r in s.runners)
        self._clock = float(s.offset)
        self.playing = False
        self._shown_last = {}
        self.publish({"type": "session", **self.status().model_dump()})
        self._publish_bed_states()

    def reset(self) -> None:
        self.seek(0)

    # ------------------------------------------------------------------ views
    def status(self) -> S.ReplayStatus:
        s = self.session
        return S.ReplayStatus(
            session_id=self.session_id,
            recordings=[] if s is None else [x.identity.recording_key for x in s.streams],
            playing=self.playing,
            speed=self.speed,
            offset_s=0 if s is None else s.offset,
            duration_s=0 if s is None else s.duration,
            finished=False if s is None else s.finished,
            decisions_logged=self.decisions_logged,
            source=self.source,
        )

    def cases(self) -> list[S.Case]:
        out = []
        for k, st in sorted(self.catalog.items()):
            ts = [e.ts for e in st.events]
            n = sum(1 for e in st.events if type(e).__name__ == "CGMReading")
            out.append(
                S.Case(
                    recording_key=k,
                    patient_key=st.identity.patient_key,
                    days=round((max(ts) - min(ts)) / 86400, 2) if ts else 0.0,
                    cgm_readings=n,
                    partition=self.partition,
                )
            )
        return out

    def _all_runners(self) -> list[tuple[TwinRunner, int, str]]:
        """(runner, data time now, source) for every bed: replay beds, then new-data sessions."""
        out: list[tuple[TwinRunner, int, str]] = []
        if self.session is not None:
            out += [(r, self.session.now(i), REPLAY) for i, r in enumerate(self.session.runners)]
        out += [(ls.runner, ls.now, NEW_DATA) for _, ls in sorted(self.live.items())]
        return out

    def _shown(self, r: TwinRunner, now: int) -> tuple[DecisionRecord | None, PolicyDecision]:
        rec = r.current
        if rec is None:
            return None, PolicyDecision(now, PolicyState.INSUFFICIENT_DATA, None, ("NO_READING",))
        return rec, current(rec.decision, now, self.model.rules)

    def _notifications(self, r: TwinRunner) -> list[S.Notification]:
        return [
            S.Notification(
                decision_id=x.decision_id,
                ts=x.decision.ts,
                acknowledged=x.decision_id in self.acks,
                reason=self.acks.get(x.decision_id, {}).get("reason"),
            )
            for x in r.decisions
            if x.decision.notify
        ]

    def ward(self) -> S.Ward:
        s = self.session
        rows = []
        for r, now, source in self._all_runners():
            rec, d = self._shown(r, now)
            unack = sum(1 for n in self._notifications(r) if not n.acknowledged)
            key = (STATE_ORDER[d.state], -(d.p if d.p is not None else -1.0), r.recording_key)
            rows.append((key, now, source, r, rec, d, unack))
        rows.sort(key=lambda x: x[0])
        beds = []
        for k, (_, now, source, r, rec, d, unack) in enumerate(rows):
            last = int(r.state.cgm.series.ts[-1]) if r.state.cgm.n else None
            groups = [g.group for g in self._factor_groups(r, d)] if d.p is not None else []
            beds.append(
                S.Bed(
                    rank=k + 1,
                    recording_key=r.recording_key,
                    patient_key=r.patient_key,
                    source=source,
                    label=self._label(r.recording_key),
                    now_ts=now,
                    last_reading_ts=last,
                    data_age_s=None if last is None else now - last,
                    stale=last is None or now - last > self.model.rules.max_gap_s,
                    cgm_low=self._is_low(self._cgm_now(r, d)),
                    cgm_mgdl=self._cgm_now(r, d),
                    trend=self._trend(r, d),
                    decision=decision_view(rec, d, self.model.status),
                    summary=summary(d, self._since(r, d), groups, self.cgm_cfg.utc_offset_s),
                    reason=reason_line(d, groups),
                    badges=self._badges(r, d, now),
                    info_tags=[t for t in d.tags if t.startswith(INFO_TAG_PREFIXES)],
                    unacknowledged_notifications=unack,
                    spark=self._spark(r, now),
                    delta_2h=self._delta_2h(r),
                    treated=self._treated(r),
                )
            )
        return S.Ward(
            session_id=self.session_id,
            offset_s=0 if s is None else s.offset,
            beds=beds,
            events=self._events(),
        )

    # ------------------------------------------------------------------ display-only views
    def _spark(self, r: TwinRunner, now: int) -> list[tuple[int, float]]:
        ts, vals = r.state.cgm.series.ts, r.state.cgm.series.values
        keep = ts >= now - 7200
        return [(int(a), float(b)) for a, b in zip(ts[keep], vals[keep], strict=True)]

    @staticmethod
    def _delta_2h(r: TwinRunner) -> float | None:
        ts, vals = r.state.cgm.series.ts, r.state.cgm.series.values
        if not len(ts):
            return None
        target = int(ts[-1]) - 7200
        i = int(np.searchsorted(ts, target))
        if i >= len(ts) or abs(int(ts[i]) - target) > 900:
            return None
        return round(float(vals[-1] - vals[i]), 1)

    @staticmethod
    def _treated(r: TwinRunner) -> bool | None:
        reg = r.stream.context.regimen
        flags = [reg.get(k) for k in ("rx_insulin", "rx_su", "rx_glinide")]
        if all(f is None or f != f for f in flags):  # regimen unknown (NaN)
            return None
        return any(f == 1.0 for f in flags)

    def _events(self, limit: int = 8) -> list[S.WardEvent]:
        out: list[tuple[int, S.WardEvent]] = []
        for r, now, _ in self._all_runners():
            prev: str | None = None
            changes = []
            for x in r.decisions:
                st = x.decision.state.value
                if x.decision.notify or st != prev:
                    changes.append(x)
                prev = st
            for x in changes[-limit:]:
                age = now - x.decision.ts
                out.append(
                    (
                        age,
                        S.WardEvent(
                            recording_key=r.recording_key,
                            label=self._label(r.recording_key),
                            ts=x.decision.ts,
                            age_s=age,
                            kind="notification" if x.decision.notify else "state",
                            state=x.decision.state.value,
                            p_text=probability_text(x.decision.p),
                            cgm_mgdl=x.cgm_mgdl,
                        ),
                    )
                )
        out.sort(key=lambda t: (t[0], t[1].recording_key))
        return [e for _, e in out[:limit]]

    def _profile(self, r: TwinRunner, now: int) -> dict[str, Any]:
        ctx = r.stream.context
        v = {k: x for k, x in ctx.values.items() if x == x}  # drop NaN (missing)
        first = r.stream.first_ts
        out: dict[str, Any] = {
            "age_y": v.get("age_y"),
            "sex": None if "sex_male" not in v else ("male" if v["sex_male"] == 1.0 else "female"),
            "diabetes_duration_y": v.get("diabetes_duration_y"),
            "bmi": v.get("bmi"),
            "hba1c_mmol_mol": v.get("hba1c_mmol_mol"),
            "prescribed_classes": sorted(ctx.prescribed_classes),
            "treated": self._treated(r),
            "days_monitored": None if first is None else round(max(0, now - first) / 86400, 1),
        }
        return {k: x for k, x in out.items() if x is not None}

    _TWIN_FEATURES: ClassVar[dict[str, tuple[str, ...]]] = {
        "glucose": (
            "cgm",
            "cgm_slope30",
            "cgm_sd_2h",
            "cgm_min_2h",
            "cgm_mean_24h",
            "cgm_cv_24h",
            "cgm_min_since_low70",
            "cgm_prior_l1_onsets",
        ),
        "medication": (
            "act_insulin_total",
            "iob_insulin",
            "act_basal",
            "act_prandial",
            "act_su",
            "act_glinide",
            "min_since_insulin",
            "min_since_su",
            "min_since_glinide",
        ),
        "data_quality": ("sensor_day",),
        "meals": ("meal_min_since", "meal_last_3h", "meals_today", "hour_sin", "night"),
    }

    def _twin(self, r: TwinRunner, now: int) -> dict[str, Any]:
        """The four state blocks, read from the canonical feature builder at the twin's
        current state (display only; nothing new is computed or decided here)."""
        st = r.state
        vals: dict[str, float] = {}
        if st.cgm.n:
            try:
                snap = self.pipe.builder.snapshot(st, "M3")
                vals = {n: float(x) for n, x in zip(snap.names, snap.values, strict=True) if x == x}
            except Exception:  # display only: never fail the view
                vals = {}
        pick = {
            w: {n: round(vals[n], 3) for n in names if n in vals}
            for w, names in self._TWIN_FEATURES.items()
        }
        ts = st.cgm.series.ts
        recent = int((ts > now - 7200).sum()) if len(ts) else 0
        led = st.ledger
        resolved = [x for x in led.resolved.items() if x.forecast.p is not None]
        notes = [x for x in r.decisions if x.decision.notify]
        med_q = {}
        if st.ts is not None:
            med_q = {c: q.value for c, q in sorted(st.medication.at(st.ts).quality.items())}
        return {
            "glucose": pick["glucose"],
            "meals": pick["meals"],
            "medication": {**pick["medication"], "quality": med_q},
            "data_quality": {
                **pick["data_quality"],
                "readings_last_2h": recent,
                "expected_readings_2h": 8,  # 15-min sampling (ShanghaiT2DM)
                "conditions": list(st.quality.reasons) if st.quality is not None else [],
                "rejected_inputs": len(r.rejected),
                "halted": r.halted,
            },
            "memory": {
                "forecasts_pending": sum(1 for f in led.pending if f.p is not None),
                "followed_by_low": sum(1 for x in resolved if x.outcome == 1),
                "not_followed_by_low": sum(1 for x in resolved if x.outcome == 0),
                "outcome_unknown": r.unknown_outcomes or 0,
                "notifications": len(notes),
                "unacknowledged": sum(1 for x in notes if x.decision_id not in self.acks),
                "low_episodes_so_far": int(vals.get("cgm_prior_l1_onsets", 0)),
            },
        }

    # ------------------------------------------------------------------ display helpers
    def _current_reading(self, r: TwinRunner, d: PolicyDecision) -> bool:
        """The latest reading is the displayed decision's reading (not stale, not an error)."""
        return r.state.cgm.n > 0 and int(r.state.cgm.series.ts[-1]) == d.ts

    def _is_low(self, v: float | None) -> bool:
        return v is not None and v < self.model.rules.low_mgdl

    def _cgm_now(self, r: TwinRunner, d: PolicyDecision) -> float | None:
        return float(r.state.cgm.series.values[-1]) if self._current_reading(r, d) else None

    def _trend(self, r: TwinRunner, d: PolicyDecision) -> S.Trend:
        if not self._current_reading(r, d):
            return S.Trend(rate_mgdl_per_min=None, category=None)
        sr = r.state.cgm.series
        rate = trend_slope(sr.ts, sr.values, 1800, self.cgm_cfg)  # canonical cgm_slope30
        ok = rate == rate
        return S.Trend(rate_mgdl_per_min=rate if ok else None, category=trend_category(rate))

    def _since(self, r: TwinRunner, d: PolicyDecision) -> int | None:
        """Start of the current run of the displayed state (consecutive decisions)."""
        if not r.decisions or r.decisions[-1].decision is not d:
            return None
        since = d.ts
        for x in reversed(r.decisions):
            if x.decision.state is not d.state:
                break
            since = x.decision.ts
        return since

    def _badges(self, r: TwinRunner, d: PolicyDecision, now: int) -> list[str]:
        out = []
        q = r.state.quality
        if "SENSOR_FAULT_SUSPECTED" in d.reasons or (q is not None and q.sensor_fault_suspected):
            out.append("SENSOR_FAULT_SUSPECTED")
        if r.halted:
            out.append("RUNNER_HALTED")
        recent = any((x.get("at") or 0) >= now - 3600 for x in r.rejected)
        if recent or (r.rejected_until is not None and now <= r.rejected_until and r.rejected):
            out.append("INPUT_REJECTED")
        return out

    def _runner(self, key: str) -> tuple[TwinRunner, int, str]:
        for r, now, source in self._all_runners():
            if r.recording_key == key:
                return r, now, source
        raise NotFound(f"recording {key} is not in the current replay or a new-data session")

    def _label(self, key: str) -> str | None:
        ls = self.live.get(key)
        return None if ls is None else ls.label

    def _factor_groups(self, r: TwinRunner, shown: PolicyDecision) -> list[S.FactorGroup]:
        """Explanation of the CURRENT forecast only; none for a non-forecast or stale state."""
        lf = r.last_forecast
        snap = r.last_snapshot
        if lf is None or lf.decision is not shown:
            return []
        if snap is None or snap.digest != lf.input_digest:
            return []
        return self._groups(snap, r.pipe.model)

    def _all_groups(self, r: TwinRunner, shown: PolicyDecision) -> list[S.FactorGroup]:
        lf = r.last_forecast
        snap = r.last_snapshot
        if lf is None or lf.decision is not shown or snap is None or snap.digest != lf.input_digest:
            return []
        return self._groups(snap, r.pipe.model, None)

    def _groups(self, snap: Any, model: RuntimeModel, top: int | None = 3) -> list[S.FactorGroup]:
        """Contributions of the model that actually scored the recording (its fold model in
        held-out replay)."""
        sums: dict[str, float] = {}
        for f, c in model.contributions(snap).items():
            g = BY_NAME[f].group.value
            sums[g] = sums.get(g, 0.0) + c
        ranked = sorted(sums.items(), key=lambda kv: (-abs(kv[1]), kv[0]))
        top_groups = ranked if top is None else ranked[:top]
        return [
            S.FactorGroup(
                group=g,
                label=GROUP_LABEL.get(g, g),
                contribution=v,
                direction="raises_risk" if v > 0 else "lowers_risk",
            )
            for g, v in top_groups
        ]

    def patient(self, key: str) -> S.PatientView:
        r, now, source = self._runner(key)
        rec, d = self._shown(r, now)
        st = r.state
        lo = now - TRACE_S
        ts, vals = st.cgm.series.ts, st.cgm.series.values
        keep = ts >= lo
        lf = r.last_forecast
        exposure: dict[str, float] = {}
        med_q: dict[str, str] = {}
        if st.ts is not None:
            m = st.medication.at(st.ts)
            exposure = {
                k: float(v) for k, v in sorted(m.exposure.items()) if not k.startswith("quality_")
            }
            exposure = {k: v for k, v in exposure.items() if math.isfinite(v)}
            med_q = {c: q.value for c, q in sorted(m.quality.items())}
        led = st.ledger
        resolved = [x for x in led.resolved.items() if x.forecast.p is not None]
        groups = self._factor_groups(r, d)
        by_ts = {
            x.decision.ts: x
            for x in r.decisions
            if x.decision.state is not PolicyState.SYSTEM_ERROR
        }
        entries: list[S.LedgerEntry] = []
        for f in [x for x in led.pending if x.p is not None]:
            entries.append(self._ledger_row(f.ts, f.p, by_ts.get(f.ts), "PENDING", None))
        for f in [x for x in r.unknown_forecasts if x.p is not None]:
            entries.append(self._ledger_row(f.ts, f.p, by_ts.get(f.ts), "OUTCOME_UNKNOWN", None))
        for x in reversed(resolved[-LEDGER_ROWS:]):
            dec = by_ts.get(x.forecast.ts)
            outcome = "LOW_FOLLOWED" if x.outcome == 1 else "NO_LOW"
            entries.append(
                self._ledger_row(x.forecast.ts, x.forecast.p, dec, outcome, x.resolved_ts)
            )
        entries.sort(key=lambda e: -e.forecast_ts)
        timeline = [
            S.TimelinePoint(
                decision_id=x.decision_id,
                ts=x.decision.ts,
                cgm_mgdl=x.cgm_mgdl,
                state=x.decision.state.value,
                p=x.decision.p,
                notify=x.decision.notify,
                in_episode=x.in_episode,
                sensor_fault="SENSOR_FAULT_SUSPECTED" in x.decision.reasons
                or "SENSOR_FAULT_SUSPECTED" in x.quality,
                exposure=dict(x.exposure),
            )
            for x in r.decisions
            if x.cgm_mgdl is not None and x.decision.ts >= lo
        ]
        return S.PatientView(
            recording_key=key,
            patient_key=r.patient_key,
            source=source,
            label=self._label(key),
            now_ts=now,
            model_status=self.model.status,
            current=decision_view(rec, d, self.model.status),
            summary=summary(
                d, self._since(r, d), [g.group for g in groups], self.cgm_cfg.utc_offset_s
            ),
            trend=self._trend(r, d),
            cgm_mgdl=self._cgm_now(r, d),
            data_age_s=None if not st.cgm.n else now - int(st.cgm.series.ts[-1]),
            stale=not st.cgm.n or now - int(st.cgm.series.ts[-1]) > self.model.rules.max_gap_s,
            cgm_low=self._is_low(self._cgm_now(r, d)),
            exposure_units={k: BY_NAME[k].unit for k in EXPOSURE_DISPLAY if k in BY_NAME},
            timeline=timeline,
            ledger_entries=entries[:LEDGER_ROWS],
            input_rejected="INPUT_REJECTED" in self._badges(r, d, now),
            last_forecast=None
            if lf is None or lf.decision.p is None
            else S.ForecastView(
                decision_id=lf.decision_id,
                ts=lf.decision.ts,
                p=lf.decision.p,
                p_text=probability_text(lf.decision.p) or "",
                state=lf.decision.state.value,
                is_current=rec is lf and d is lf.decision,
            ),
            cgm=[(int(a), float(b)) for a, b in zip(ts[keep], vals[keep], strict=True)],
            cbg=[(c.ts, c.value_mgdl) for c in st.cbg.items() if c.ts >= lo],
            meals=[m.ts for m in st.meals.items() if m.ts >= lo],
            doses=[
                S.Dose(
                    ts=e.ts,
                    drug_class=e.drug_class,
                    canonical=e.canonical,
                    route=e.route,
                    dose=e.dose,
                    dose_unit=e.dose_unit,
                )
                for e in st.medication.events.items()
                if e.ts >= lo
            ],
            exposure=exposure,
            exposure_ts=st.ts,
            medication_quality=med_q,
            data_quality=list(st.quality.reasons) if st.quality is not None else [],
            factor_groups=groups,
            notifications=self._notifications(r),
            ledger={
                "pending": sum(1 for f in led.pending if f.p is not None),
                "resolved_low": sum(1 for x in resolved if x.outcome == 1),
                "resolved_no_low": sum(1 for x in resolved if x.outcome == 0),
                "outcome_unknown": r.unknown_outcomes or 0,
            },
            rejected_events=len(r.rejected),
            halted=r.halted,
            caveat=LABEL_CAVEAT,
            profile=self._profile(r, now),
            twin=self._twin(r, now),
            contributions=self._all_groups(r, d),
        )

    def _ledger_row(
        self,
        ts: int,
        p: float | None,
        dec: DecisionRecord | None,
        outcome: str,
        resolved_ts: int | None,
    ) -> S.LedgerEntry:
        assert p is not None
        return S.LedgerEntry(
            forecast_ts=ts,
            p=p,
            p_text=probability_text(p) or "",
            state=None if dec is None else dec.decision.state.value,
            notified=False if dec is None else dec.decision.notify,
            outcome=outcome,
            resolved_ts=resolved_ts,
        )

    # ------------------------------------------------------------------ acknowledgement
    def acknowledge(self, req: S.AckRequest) -> dict[str, Any]:
        s = self.session
        found = None
        for r, _, _ in self._all_runners():
            for x in r.decisions:
                if x.decision_id == req.decision_id:
                    found = x
        if found is None:
            raise NotFound("unknown decision")
        if not found.decision.notify:
            raise Conflict("only notifications are acknowledged (Blueprint §16.4)")
        if req.decision_id in self.acks:
            raise Conflict("this notification is already acknowledged")
        rec = {
            "decision_id": req.decision_id,
            "recording_key": found.recording_key,
            "decision_ts": found.decision.ts,
            "ack_offset_s": None if s is None or found.recording_key in self.live else s.offset,
            "reason": req.reason.value,
            "user_role": req.user_role.value,
            "model_version": self.model.model_version,
            "received_utc": utc_now_iso(),
        }
        self.acks[req.decision_id] = rec
        ls = self.live.get(found.recording_key)
        log = ls.log if ls is not None else (None if s is None else s.log)
        if log is not None:
            log.write("acks", rec)
        self.publish({"type": "acknowledgement", **rec})
        return rec

    # ------------------------------------------------------------------ ask about this patient
    ASK_INTENTS: ClassVar[dict[str, str]] = {
        "why_state": "Why is this patient showing this status?",
        "no_forecast": "Why is there (or isn't there) a forecast?",
        "current": "Are the glucose readings current?",
        "changed": "What changed since the previous reading?",
        "after_alert": "What happened after the last alert?",
        "medications": "Which medication entries are recorded (last 24 h)?",
        "quality": "What do the data-quality warnings mean?",
        "missing": "What information is missing?",
        "evidence": "What evidence supports this display?",
    }

    def ask(self, key: str, intent: str) -> S.AskAnswer:
        """Fixed intents answered ONLY from fields the twin already holds (no free text, no
        generated prose, no diagnosis, dose or treatment advice)."""
        if intent not in self.ASK_INTENTS:
            raise InvalidRequest(f"unsupported question; choose one of {sorted(self.ASK_INTENTS)}")
        r, now, source = self._runner(key)
        _, d = self._shown(r, now)
        st = r.state
        off = self.cgm_cfg.utc_offset_s
        lines: list[str] = []
        if intent == "why_state":
            lines.append(f"Current state: {d.state.value.replace('_', ' ')}.")
            lines += list(texts(d))
            if d.p is not None:
                lines.append(
                    f"Estimated risk of a CGM-detected low within 60 min: {probability_text(d.p)}."
                )
                groups = self._factor_groups(r, d)
                if groups:
                    lines.append(
                        "Factor groups most associated with this forecast (statistical "
                        "associations, not causes): "
                        + ", ".join(f"{g.label} ({g.direction.replace('_', ' ')})" for g in groups)
                        + "."
                    )
            else:
                lines.append("No risk estimate is shown for this state.")
        elif intent == "no_forecast":
            if d.p is not None:
                lines.append(
                    f"A forecast is available: estimated risk {probability_text(d.p)} that a new "
                    "CGM-detected low begins within 60 minutes."
                )
            else:
                lines.append("No forecast is shown now, because:")
                lines += list(texts(d)) or ["the current status does not allow one."]
                lines.append(
                    "Low risk and missing information are different: no forecast is never shown "
                    "as low risk."
                )
        elif intent == "current":
            if not st.cgm.n:
                lines.append("There is no CGM reading yet.")
            else:
                last = int(st.cgm.series.ts[-1])
                age_min = (now - last) / 60
                limit = self.model.rules.max_gap_s / 60
                ok = now - last <= self.model.rules.max_gap_s
                lines.append(
                    f"The latest CGM reading is {age_min:.0f} min old at the current clock "
                    f"({clock_text(last, off)}); readings older than {limit:.0f} min are not "
                    f"current. Status: {'current' if ok else 'NOT current'}."
                )
                recent = int((st.cgm.series.ts > now - 7200).sum())
                lines.append(f"{recent} CGM reading(s) in the last 2 hours.")
        elif intent == "after_alert":
            notified = [x for x in r.decisions if x.decision.notify]
            if not notified:
                lines.append("There has been no alert notification for this patient yet.")
            else:
                last_n = notified[-1]
                t0 = last_n.decision.ts
                lines.append(
                    f"Last alert notification: {clock_text(t0, off)}, estimated risk "
                    f"{probability_text(last_n.decision.p)}."
                )
                res = [x for x in st.ledger.resolved.items() if x.forecast.ts == t0]
                if res:
                    x = res[0]
                    what = (
                        "a CGM-detected low followed"
                        if x.outcome == 1
                        else "no CGM-detected low followed"
                    )
                    lines.append(
                        f"Within the next 60 minutes, {what} "
                        f"(known at {clock_text(x.resolved_ts, off)})."
                    )
                elif any(f.ts == t0 for f in st.ledger.pending):
                    lines.append(
                        "The 60-minute window after it is not complete yet, so the outcome "
                        "is not known."
                    )
                else:
                    lines.append("The outcome of that alert is unknown (the recording ended).")
                ack = self.acks.get(last_n.decision_id)
                lines.append(
                    "It was acknowledged (" + str(ack["reason"]).replace("_", " ") + ")."
                    if ack
                    else "It has not been acknowledged."
                )
        elif intent == "missing":
            if not st.cgm.n:
                lines.append("No CGM reading yet: a forecast needs recent CGM history.")
            if st.quality is not None and st.quality.reasons:
                lines += [
                    "Data-quality condition now: " + REASON_TEXT.get(x, x).rstrip(".") + "."
                    for x in st.quality.reasons
                ]
            if st.ts is not None:
                q = st.medication.at(st.ts).quality
                unk = [c for c, v in sorted(q.items()) if v.value != "OK"]
                for c in unk:
                    lines.append(
                        f"Medication record for {c}: {q[c].value.replace('_', ' ').lower()}."
                    )
            ctx = r.stream.context
            miss = sorted(_CTX_LABEL.get(k, k) for k, v in ctx.values.items() if v != v)  # NaN
            if miss:
                lines.append(
                    "Patient context not available (treated as missing): " + ", ".join(miss) + "."
                )
            if all(v != v for v in ctx.regimen.values()):
                lines.append("Prescribed regimen not available.")
            if not lines:
                lines.append("No required information is missing for the current display.")
        elif intent == "changed":
            recs = [x for x in r.decisions if x.cgm_mgdl is not None]
            if len(recs) < 2:
                lines.append("There is no previous reading to compare with.")
            else:
                a_, b_ = recs[-2], recs[-1]
                lines.append(
                    f"Reading {clock_text(a_.decision.ts, off)} → "
                    f"{clock_text(b_.decision.ts, off)}: "
                    f"CGM {a_.cgm_mgdl:g} → {b_.cgm_mgdl:g} mg/dL."
                )
                lines.append(
                    f"State {a_.decision.state.value.replace('_', ' ')} → "
                    f"{b_.decision.state.value.replace('_', ' ')}; risk "
                    f"{probability_text(a_.decision.p) or 'none'} → "
                    f"{probability_text(b_.decision.p) or 'none'}."
                )
                between = [
                    e
                    for e in r.stream.events[a_.seq + 1 : b_.seq]
                    if type(e).__name__ != "CGMReading"
                ]
                kinds: dict[str, int] = {}
                for e in between:
                    kinds[type(e).__name__] = kinds.get(type(e).__name__, 0) + 1
                lines.append(
                    "Other entries in between: "
                    + (", ".join(f"{n} {k}" for k, n in sorted(kinds.items())) or "none")
                    + "."
                )
        elif intent == "medications":
            items = [e for e in st.medication.events.items() if e.ts >= now - TRACE_S]
            if not items:
                lines.append("No medication entry was recorded in the last 24 h.")
            for e in items[-20:]:
                dose = (
                    "dose unknown" if e.dose is None else f"{e.dose:g} {e.dose_unit or ''}".strip()
                )
                lines.append(
                    f"{clock_text(e.ts, off)} · {e.canonical or 'unrecognised entry'} · {dose}"
                    f" · {e.route or 'route unknown'}"
                    f" (as recorded; parse {e.parse_status.value.lower()})"
                )
        elif intent == "quality":
            reasons = list(st.quality.reasons) if st.quality is not None else []
            lines += [REASON_TEXT.get(x, x) for x in reasons] or ["No data-quality condition now."]
            if r.rejected:
                lines.append(f"{len(r.rejected)} input event(s) were rejected and not used.")
            if r.halted:
                lines.append("Processing halted after repeated errors: no current state is shown.")
        else:
            lines.append(
                f"Model {self.model.model_version} ({self.model.status}); thresholds and policy "
                "frozen in the model artefact."
            )
            lines.append(
                "Evidence is development evidence on the tuning partition; the confirmatory "
                f"result is {self._confirm_label().split(' ')[0]} (see Evidence)."
            )
            if source == NEW_DATA:
                lines.append(
                    "This patient is a new-data session: the model was not trained or evaluated "
                    "on these data, and no accuracy claim applies to them."
                )
        lines.append("This is research decision support: no diagnosis, dose or treatment advice.")
        return S.AskAnswer(intent=intent, question=self.ASK_INTENTS[intent], lines=lines)

    # ------------------------------------------------------------------ new-data intake
    INTAKE_NOTICE = (
        "New data are a separate DEVELOPMENT session: never training data, never part of the "
        "research partitions, kept in memory only and deleted when the session is removed or the "
        "server stops. Forecasts use the DEVELOPMENT research model and are not clinically "
        "validated."
    )
    MAX_DRAFTS = 8
    MAX_LIVE = 8

    def _new_patient_id(self) -> str:
        self._intake_seq += 1
        return f"N{self._intake_seq:04d}"

    def _draft(self, draft_id: str) -> Draft:
        d = self.drafts.get(draft_id)
        if d is None:
            raise NotFound("unknown or expired intake draft")
        return d

    def _draft_view(self, d: Draft) -> S.IntakeDraft:
        from hyposense.intake.draft import CONTEXT_FIELDS

        r = d.evaluate()
        headers = [] if d.raw is None else [str(c) for c in d.raw.columns]
        return S.IntakeDraft(
            draft_id=d.draft_id,
            patient_id=d.patient_id,
            label=d.label,
            file_name=d.file_name,
            status=r.status,
            findings=[S.IntakeFinding(**vars(f)) for f in r.findings],
            questions=[
                S.IntakeQuestion(
                    **{**vars(q), "options": [tuple(o) for o in q.options], "impact": q.impact}
                )
                for q in r.questions
            ],
            mapping=r.mapping,
            preview_headers=headers,
            preview=r.preview,
            summary=r.summary,
            context=[
                S.IntakeContextField(name=n, label=lbl, value=d.context.get(n, ""))
                for n, (_, lbl) in CONTEXT_FIELDS.items()
            ],
            notice=self.INTAKE_NOTICE,
        )

    def _admit_draft(self) -> None:
        if len(self.drafts) >= self.MAX_DRAFTS:
            raise Busy("too many open intake drafts; discard one first")

    def intake_upload(self, req: S.IntakeUpload) -> S.IntakeDraft:
        import base64
        import binascii

        from hyposense.intake.upload import UploadRejected, read_upload

        self._admit_draft()
        try:
            content = base64.b64decode(req.content_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise InvalidRequest("the upload is not valid base64") from exc
        try:
            table = read_upload(req.file_name, content)
        except UploadRejected as exc:
            raise InvalidRequest(str(exc)) from exc
        pid = self._new_patient_id()
        label = (req.label or "").strip() or None
        d = Draft(f"draft-{pid}", pid, table.frame, table.file_name, label)
        self.drafts[d.draft_id] = d
        return self._draft_view(d)

    def intake_new(self, req: S.IntakeNew) -> S.IntakeDraft:
        self._admit_draft()
        pid = self._new_patient_id()
        d = Draft(f"draft-{pid}", pid, None, None, (req.label or "").strip() or None)
        self.drafts[d.draft_id] = d
        return self._draft_view(d)

    def intake_get(self, draft_id: str) -> S.IntakeDraft:
        return self._draft_view(self._draft(draft_id))

    def intake_answer(self, draft_id: str, req: S.IntakeAnswers) -> S.IntakeDraft:
        from hyposense.intake.draft import CONTEXT_FIELDS

        d = self._draft(draft_id)
        unknown = set(req.context) - set(CONTEXT_FIELDS)
        if unknown:
            raise InvalidRequest(f"unknown context field(s): {sorted(unknown)}")
        for k, v in req.answers.items():
            if v == "":
                d.answers.pop(k, None)
            else:
                d.answers[k] = v
        d.context.update(req.context)
        return self._draft_view(d)

    def intake_discard(self, draft_id: str) -> None:
        self.drafts.pop(draft_id, None)

    def intake_commit(self, draft_id: str) -> S.IntakeCommitted:
        from datetime import date

        from hyposense.intake.session import start_session

        d = self._draft(draft_id)
        if len(self.live) >= self.MAX_LIVE:
            raise Busy("too many new-data sessions; remove one first")
        r = d.evaluate()
        if r.status != "READY":
            raise Conflict(f"the draft is not ready ({r.status}); resolve the open items first")
        ident = r.stream.identity if r.stream is not None else d.identity(date.today())
        audit = [
            {
                "at_utc": utc_now_iso(),
                "kind": "intake",
                "file_type": None if d.file_name is None else d.file_name.rsplit(".", 1)[-1],
                "answers": sorted(d.answers),  # question ids only (no values, no file content)
                "context_fields": sorted(k for k, v in d.context.items() if v.strip()),
            }
        ]
        log = DecisionLog(
            self.log_root / "intake" / f"{make_run_id('intake')}-{d.patient_id}",
            {
                "session": ident.recording_key,
                "source": NEW_DATA,
                "model_version": self.model.model_version,
                "model_status": self.model.status,
                "artifact_manifest_sha256": self.model.manifest_sha256,
                "created_utc": utc_now_iso(),
            },
        )
        ls, decisions = start_session(
            ident,
            d.label,
            "upload" if d.raw is not None else "manual",
            r.frame,
            r.summary_row,
            self.pipe,
            log,
            audit,
        )
        self.live[ls.key] = ls
        del self.drafts[draft_id]
        states: dict[str, int] = {}
        for x in decisions:
            states[x.decision.state.value] = states.get(x.decision.state.value, 0) + 1
        self._publish_bed_states()
        return S.IntakeCommitted(recording_key=ls.key, decisions=len(decisions), states=states)

    def live_sessions(self) -> list[S.LiveSessionInfo]:
        from hyposense.intake.draft import local_text

        out = []
        for k, ls in sorted(self.live.items()):
            st = ls.runner.state
            out.append(
                S.LiveSessionInfo(
                    recording_key=k,
                    patient_key=ls.identity.patient_key,
                    label=ls.label,
                    origin=ls.origin,
                    created_utc=ls.created_utc,
                    cgm_readings=st.cgm.n,
                    last_local=None if not st.cgm.n else local_text(int(st.cgm.series.ts[-1])),
                    observations_added=sum(1 for a in ls.audit if a["kind"] != "intake"),
                )
            )
        return out

    def observe(self, key: str, obs: S.Observation) -> S.ObservationResult:
        from hyposense.intake.session import ObservationRejected, append_observation

        ls = self.live.get(key)
        if ls is None:
            raise NotFound("observations can only be added to a new-data session")
        try:
            entry = append_observation(ls, obs.model_dump())
        except ObservationRejected as exc:
            raise InvalidRequest(str(exc)) from exc
        self._publish_bed_states()
        return S.ObservationResult(
            recording_key=key,
            kind=entry["kind"],
            local_time=entry["local_time"],
            events=entry["events"],
            decisions=entry["decisions"],
        )

    def delete_session(self, key: str) -> None:
        """Remove a new-data session from memory and delete its decision log."""
        import shutil

        ls = self.live.pop(key, None)
        if ls is None:
            raise NotFound("unknown new-data session")
        if ls.log is not None:
            ls.log.close()
            shutil.rmtree(ls.log.directory, ignore_errors=True)
        self._shown_last.pop(key, None)
        self.publish({"type": "session_removed", "recording_key": key})

    # ------------------------------------------------------------------ evidence / meta
    def meta(self) -> dict[str, Any]:
        m = self.model
        return {
            "api_version": S.API_VERSION,
            "stream_version": S.STREAM_VERSION,
            "model_version": m.model_version,
            "model_status": m.status,
            "level": m.level,
            "artifact_manifest_sha256": m.manifest_sha256,
            "compatibility": m.manifest["compatibility"],
            "provenance": {
                k: m.manifest["provenance"].get(k)
                for k in ("git", "s6_run", "s6_results_sha256", "calibrator", "created_utc")
            },
            "thresholds": {
                "tau_alert": m.thresholds.tau_alert,
                "tau_watch": m.thresholds.tau_watch,
            },
            "policy": {
                "cooldown_s": m.rules.cooldown_s,
                "low_mgdl": m.rules.low_mgdl,
                "post_episode_s": m.rules.post_episode_s,
                "max_gap_s": m.rules.max_gap_s,
            },
            "freeze_status": "NOT FROZEN (development)"
            if self.held_out is None or self.held_out.partition != "E"
            else "FROZEN; confirmatory run executed",
            "data_utc_offset_s": self.cgm_cfg.utc_offset_s,
            "source": self.source,
            "held_out": None
            if self.held_out is None
            else {
                "run_id": self.held_out.run_id,
                "partition": self.held_out.partition,
                "bundle": self.held_out.bundle_dir.name,
                "folds": {
                    str(k): p.model.manifest_sha256 for k, p in sorted(self.fold_pipes.items())
                },
            },
            "caveat": LABEL_CAVEAT,
        }

    def confirmatory(self) -> dict[str, Any]:
        """The confirmatory (S9) result for the Evidence View: PENDING until exactly one official
        run exists and passes `freeze.verify_confirmation`; then its frozen numbers, unchanged.
        A rehearsal run is never shown here."""
        from hyposense.freeze import (
            FreezeVerificationError,
            official_confirm_runs,
            verify_confirmation,
        )
        from hyposense.reporting.confirm_view import confirmatory_view, pending_view

        if not official_confirm_runs():
            return pending_view()
        if self._confirm_view is None:
            try:
                v = verify_confirmation()  # refuses a tampered record or results document
            except FreezeVerificationError as exc:  # shown, never hidden or replaced
                return {"status": "INTEGRITY FAILURE", "note": str(exc)}
            doc = json.loads(
                (REPO_ROOT / "experiments" / "runs" / v.confirm_run / "results.json").read_text(
                    "utf-8"
                )
            )
            self._confirm_view = confirmatory_view(doc)
        return self._confirm_view

    def _confirm_label(self) -> str:
        c = self.confirmatory()
        if c["status"] == "PENDING":
            return "PENDING (sealed evaluation partition not opened)"
        return f"{c['status']} {c.get('run_id', '')}".strip()

    def evidence(self) -> dict[str, Any]:
        """Evidence View content, assembled from canonical artefacts only (no computation):
        S6 development results, the aggregate curve artefact, gate files, S7 engineering runs
        and the model manifest. Status DEVELOPMENT; confirmatory PENDING (E sealed)."""
        run = str(self.model.manifest["provenance"].get("s6_run"))
        if not S6_RUN_ID.fullmatch(run):
            raise NotFound("no development evidence is linked to this model")
        runs = REPO_ROOT / "experiments" / "runs"
        doc = json.loads((runs / run / "results.json").read_text("utf-8"))
        res = doc["results"]
        lad = res["ladder"]
        comps = lad["treated"].get("comparisons", {})
        ladder_keys = ("C1_", "C2a_", "C2b_", "preview_")
        sens = {
            k: v for k, v in comps.items() if k.endswith(":sens1") and k.startswith(ladder_keys)
        }
        separate = sorted(k for k, v in sens.items() if not v["ci95"][0] <= 0.0 <= v["ci95"][1])
        ladder: dict[str, Any] = {}
        for pop, block in lad.items():
            iv = block.get("intervals", {})
            ladder[pop] = {
                "patients": block.get("patients"),
                "episodes": block.get("episodes"),
                "models": {
                    name: {
                        "sens_at_1fa": v["sens_at_1fa"],
                        "sens_at_1fa_ci95": iv.get(f"{name}:sens1", {}).get("ci95"),
                        "partial_area": v.get("partial_area"),
                        "partial_area_ci95": iv.get(f"{name}:area", {}).get("ci95"),
                        "operating_point": v.get("operating_point"),
                        "calibration": v.get("calibration"),
                        "reliability": v.get("reliability"),
                        "log_loss": (v.get("window") or {}).get("log_loss"),
                    }
                    for name, v in block["models"].items()
                },
            }
        curves = None
        for d in sorted(runs.glob("T-AGG-dev-evidence-*"), reverse=True):
            ev = json.loads((d / "results.json").read_text("utf-8"))
            if ev["results"].get("source_run") == run:
                curves = {
                    "run_id": ev["run_id"],
                    "results_sha256": ev["results_sha256"],
                    **ev["results"]["curves"],
                }
                break
        gates = []
        for g in sorted((REPO_ROOT / "artifacts" / "gates").glob("G*.json")):
            gd = json.loads(g.read_text("utf-8"))
            gates.append(
                {
                    "gate": gd.get("gate"),
                    "title": gd.get("title"),
                    "status": gd.get("status"),
                    "evaluated_utc": gd.get("evaluated_utc"),
                    "summary": [c.get("summary") for c in gd.get("checks", []) if c.get("summary")][
                        :3
                    ],
                    "consequences": gd.get("consequences_applied") or [],
                }
            )
        engineering = None
        for d in sorted(runs.glob("T-AGG-s7-engineering-*"), reverse=True):
            en = json.loads((d / "results.json").read_text("utf-8"))
            if en["provenance"]["git"].get("dirty") is False and "error_injection" in en["results"]:
                r = en["results"]
                if r["error_injection"].get("later_decisions_changed") == 0:
                    engineering = {
                        "run_id": en["run_id"],
                        "results_sha256": en["results_sha256"],
                        "commit": en["provenance"]["git"].get("commit"),
                        "parity": r["parity"],
                        "determinism_identical": r["determinism"]["identical"],
                        "error_injection": r["error_injection"],
                        "long_run": r["long_run"],
                        "latency_ms": en["timing"]["per_reading_end_to_end"],
                    }
                    break
        ev_cfg = self.cfg["event"]
        m = self.model
        return {
            "status": "DEVELOPMENT",
            "confirmatory": self._confirm_label(),
            "task": {
                "target": f"CGM-detected L1 episode (CGM < {ev_cfg['threshold_mgdl']:g} mg/dL)",
                "horizon_min": ev_cfg["horizon_min"],
                "warning_window_min": [-int(ev_cfg["horizon_min"]), -int(ev_cfg["min_lead_min"])],
                "fa_budget_per_day": self.cfg["policy"]["fa_budget_alert"],
                "primary_comparison": "M3 vs M2, sens@1FA, treated patients (sealed partition)",
                "population_development": "tuning partition T, nested patient-grouped CV",
            },
            "run_id": doc["run_id"],
            "results_sha256": doc["results_sha256"],
            "commit": doc["provenance"].get("git", {}).get("commit"),
            "ladder": ladder,
            "comparisons": {
                k: {
                    **v,
                    "excludes_zero": None
                    if not v.get("ci95")
                    else not v["ci95"][0] <= 0.0 <= v["ci95"][1],
                }
                for k, v in comps.items()
            },
            "diagnostics": [
                {
                    "label": (
                        f"CGM-level reference, POST-HOC DEVELOPMENT REFERENCE "
                        f"({k.split(':')[0]} patients)"
                    ),
                    "value": (
                        f"sens@1FA {v['sens_at_1fa']:.3f} "
                        f"(alerts when CGM < {-v['tau_alert']:g} mg/dL)"
                    ),
                    "source": run,
                }
                for k, v in res.get("diagnostic_simple_rules", {}).items()
                if k.split(":")[1].startswith("level_")
            ],
            "curves": curves,
            "calibration_decision": self.model.calibrator.method,  # served (canonical)
            "s6_calibrator": res.get("pb1_calibration", {}).get("decision"),
            "canonical_calibration": self._canonical_calibration(),
            "gates": gates,
            "engineering": engineering,
            "model": {
                "model_version": m.model_version,
                "status": m.status,
                "manifest_sha256": m.manifest_sha256,
                "compatibility": m.manifest["compatibility"],
                "tau_alert": m.thresholds.tau_alert,
                "tau_watch": m.thresholds.tau_watch,
            },
            "interpretation": (
                "Development only (T). "
                + (
                    "No C1/C2a/C2b/M3-M2 sens@1FA interval excludes 0; the ordering among "
                    "M1-M3 is uninformative on T."
                    if not separate
                    else f"Intervals excluding 0 on T: {separate} (development only)."
                )
            ),
            "safeguards": self._safeguards(),
            "limitations": [
                "C0 (M1 vs the M0 trend rule) overstates the value of learning: a post-hoc "
                "CGM-level reference (alert at CGM < 81 mg/dL) matches the learned models on T. "
                "It was added after development analysis and is not a pre-specified confirmatory "
                "comparator (P-C9).",
                "Research prototype; not a medical device; not clinically validated.",
                "Development evidence only: tuning partition, internal cross-validation. The "
                "evaluation partition is sealed.",
                "The target is a CGM-detected low; CGM and capillary glucose often disagree "
                "(gate G3b TRIGGERED). The supported action is capillary confirmation.",
                "Medication exposure is estimated from logged doses with fixed population-level "
                "kernels."
                + (
                    ""
                    if self.pharma.get("reviewed_by")
                    else " Kernel parameters: clinical-pharmacist review PENDING."
                ),
                "No dose or treatment recommendations are made.",
            ],
            "caveat": LABEL_CAVEAT,
        }

    def _canonical_calibration(self) -> dict[str, Any] | None:
        """ECE / slope / log-loss of the CANONICAL calibrator on T (latest clean freeze-candidate
        run). The S6 ladder values above were computed with the superseded `isotonic_interp`."""
        runs = REPO_ROOT / "experiments" / "runs"
        for d in sorted(runs.glob("T-AGG-candidate-*"), reverse=True):
            doc = json.loads((d / "results.json").read_text("utf-8"))
            if doc["provenance"]["git"].get("dirty") is not False:
                continue
            ev = doc["results"]["evaluation"]
            return {
                "run_id": doc["run_id"],
                "results_sha256": doc["results_sha256"],
                "calibrator": doc["results"]["canonical"]["calibrator"],
                **{
                    pop: {
                        m: {k: ev[pop][m]["candidate"][k] for k in ("ece", "slope", "log_loss")}
                        for m in ("M1", "M2", "M3r", "M3")
                    }
                    for pop in ("treated", "all")
                },
            }
        return None

    def _safeguards(self) -> list[dict[str, str]]:
        """Leakage and separation controls, quoted from their audit artefacts (no recomputation)."""
        runs = REPO_ROOT / "experiments" / "runs"
        out: list[dict[str, str]] = []
        for d in sorted(runs.glob("T-AGG-audit-features-*"), reverse=True):
            f = d / "audit_features.json"
            if not f.is_file():
                continue
            a = json.loads(f.read_text("utf-8"))
            if a.get("provenance", {}).get("git", {}).get("dirty") is not False:
                continue
            det = a["deterministic"]
            tr, pa = det["truncation"], det["parity"]
            pert = det["perturbation"]
            n_p = sum(v["comparisons"] for v in pert.values())
            m_p = sum(v["mismatches"] for v in pert.values())
            src = a["run_id"]
            out += [
                {
                    "label": "Truncation equality (features at t: full vs truncated record)",
                    "value": f"{tr['comparisons']:,} comparisons, {tr['mismatches']} mismatches",
                    "source": src,
                },
                {
                    "label": "Future-perturbation test (CGM, medication, meals, outcomes after t)",
                    "value": f"{n_p:,} comparisons, {m_p} mismatches",
                    "source": src,
                },
                {
                    "label": "Offline / replay feature parity",
                    "value": f"{pa['comparisons']:,} comparisons, {pa['mismatches']} mismatches",
                    "source": src,
                },
            ]
            break
        part = self.cfg["partition"]
        out += [
            {
                "label": "Patient-level partition (development T vs sealed evaluation E)",
                "value": f"fixed file {str(part['sha256'])[:12]}…; E never loaded before freeze",
                "source": "configs/partition.csv",
            },
            {
                "label": "Nested patient-grouped cross-validation",
                "value": "tuning, calibration and thresholds use training patients only",
                "source": str(self.model.manifest["provenance"].get("s6_run")),
            },
        ]
        return out

    # ------------------------------------------------------------------ stream
    def subscribe(self) -> asyncio.Queue[dict[str, Any] | None]:
        if len(self.subscribers) >= MAX_SUBSCRIBERS:
            raise Busy("too many stream subscribers")
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(SUBSCRIBER_QUEUE)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any] | None]) -> None:
        self.subscribers.discard(q)

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called from the event-loop thread before any service access."""
        self._loop = loop
        self._loop_thread = threading.get_ident()

    def publish(self, msg: dict[str, Any]) -> None:
        """Typed, versioned stream message. Thread-safe: mutations run in a worker thread, and
        delivery is handed to the event loop in FIFO order. A subscriber that falls behind is
        disconnected (it reconnects and re-reads the snapshot endpoints); the replay never blocks
        on a client."""
        full = {"v": S.STREAM_VERSION, **msg}
        loop = getattr(self, "_loop", None)
        off_loop = threading.get_ident() != getattr(self, "_loop_thread", None)
        if loop is not None and off_loop and loop.is_running():
            loop.call_soon_threadsafe(self._deliver, full)
        else:
            self._deliver(full)

    def _deliver(self, full: dict[str, Any]) -> None:
        for q in list(self.subscribers):
            try:
                q.put_nowait(full)
            except asyncio.QueueFull:
                self.subscribers.discard(q)
                while not q.empty():
                    q.get_nowait()
                q.put_nowait(None)
