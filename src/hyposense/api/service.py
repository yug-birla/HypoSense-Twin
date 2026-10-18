"""Replay service behind the API: orchestration only (CLAUDE.md §26). The artefact is verified at
construction; an ArtifactError propagates and the server does not start (Blueprint §18).

Data scope: TUNING partition (T) only before freeze (ARCHITECTURE §4.10; sealed E is refused by
`features.build.tuning_streams` and `state.stream.recording_stream`). Every view is labelled
with the model status.
"""

from __future__ import annotations

import asyncio
import json
import math
import re
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from hyposense.api import schemas as S
from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.features.cgm import CGMFeatureConfig, trend_slope
from hyposense.features.snapshot import FeatureBuilder
from hyposense.features.spec import BY_NAME
from hyposense.models.artifact import RuntimeModel, load_artifact
from hyposense.policy.decide import PolicyDecision, PolicyState, current
from hyposense.policy.messages import (
    GROUP_LABEL,
    LABEL_CAVEAT,
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
STATE_ORDER = {
    PolicyState.SYSTEM_ERROR: 0,
    PolicyState.LOW_NOW: 1,
    PolicyState.ALERT: 2,
    PolicyState.WATCH: 3,
    PolicyState.INSUFFICIENT_DATA: 4,
    PolicyState.NO_ALERT: 5,
}
TRACE_S = 24 * 3600
SUBSCRIBER_QUEUE = 1000
MAX_SUBSCRIBERS = 16
PC10_MODES = ("system_error", "badge")  # P-C10 PENDING: system_error = current behaviour
INFO_TAG_PREFIXES = ("LOW_CONFIDENCE", "MED_TIMING_UNKNOWN", "EVENT_REJECTED")
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


class Service:
    def __init__(
        self,
        model_dir: Path,
        streams: Sequence[RecordingStream] | None = None,
        log_root: Path = LOG_ROOT,
        expected_manifest_sha256: str | None = None,
        pc10_mode: str = "system_error",
    ) -> None:
        if pc10_mode not in PC10_MODES:
            raise ValueError(f"pc10_mode must be one of {PC10_MODES}")
        self.pc10_mode = pc10_mode
        self.cfg, self.pharma = load_config(), load_config("pharma.yaml")
        self.model: RuntimeModel = load_artifact(  # refuses on any mismatch
            model_dir, self.cfg, self.pharma, expected_manifest_sha256
        )
        self.pipe = Pipeline(
            EngineConfig.from_config(self.cfg, self.pharma),
            FeatureBuilder(self.cfg),
            self.model,
            MAX_CONSECUTIVE_ERRORS,
            reject_non_cgm_as_error=pc10_mode == "system_error",
        )
        self.cgm_cfg = CGMFeatureConfig.from_config(self.cfg)
        if streams is None:
            streams = load_tuning_streams(self.cfg, self.pharma)
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
            "source": SOURCE_LABEL,
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
        self.session = ReplaySession(self._streams, self.pipe, log)
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
        s = self._require()
        for i, r in enumerate(s.runners):
            rec, d = self._shown(i, r)
            did = rec.decision_id if rec is not None and rec.decision is d else None
            key = (d.state.value, d.p, did)
            if self._shown_last.get(r.recording_key) != key:
                self._shown_last[r.recording_key] = key
                self.publish(
                    {
                        "type": "bed_state",
                        "recording_key": r.recording_key,
                        "now_ts": s.now(i),
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
            source=SOURCE_LABEL,
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
                    partition="T",
                )
            )
        return out

    def _shown(self, i: int, r: TwinRunner) -> tuple[DecisionRecord | None, PolicyDecision]:
        s = self._require()
        now = s.now(i)
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
        if s is None:
            return S.Ward(session_id=None, offset_s=0, beds=[])
        rows = []
        for i, r in enumerate(s.runners):
            rec, d = self._shown(i, r)
            unack = sum(1 for n in self._notifications(r) if not n.acknowledged)
            key = (STATE_ORDER[d.state], -(d.p if d.p is not None else -1.0), r.recording_key)
            rows.append((key, i, r, rec, d, unack))
        rows.sort(key=lambda x: x[0])
        beds = []
        for k, (_, i, r, rec, d, unack) in enumerate(rows):
            now = s.now(i)
            last = int(r.state.cgm.series.ts[-1]) if r.state.cgm.n else None
            groups = [g.group for g in self._factor_groups(r, d)] if d.p is not None else []
            beds.append(
                S.Bed(
                    rank=k + 1,
                    recording_key=r.recording_key,
                    patient_key=r.patient_key,
                    now_ts=now,
                    last_reading_ts=last,
                    data_age_s=None if last is None else now - last,
                    cgm_mgdl=self._cgm_now(r, d),
                    trend=self._trend(r, d),
                    decision=decision_view(rec, d, self.model.status),
                    summary=summary(d, self._since(r, d), groups, self.cgm_cfg.utc_offset_s),
                    reason=reason_line(d, groups),
                    badges=self._badges(r, d, now),
                    info_tags=[t for t in d.tags if t.startswith(INFO_TAG_PREFIXES)],
                    unacknowledged_notifications=unack,
                )
            )
        return S.Ward(session_id=self.session_id, offset_s=s.offset, beds=beds)

    # ------------------------------------------------------------------ display helpers
    def _current_reading(self, r: TwinRunner, d: PolicyDecision) -> bool:
        """The latest reading is the displayed decision's reading (not stale, not an error)."""
        return r.state.cgm.n > 0 and int(r.state.cgm.series.ts[-1]) == d.ts

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

    def _runner(self, key: str) -> tuple[int, TwinRunner]:
        s = self._require()
        for i, r in enumerate(s.runners):
            if r.recording_key == key:
                return i, r
        raise NotFound(f"recording {key} is not in the current replay")

    def _factor_groups(self, r: TwinRunner, shown: PolicyDecision) -> list[S.FactorGroup]:
        """Explanation of the CURRENT forecast only; none for a non-forecast or stale state."""
        lf = r.last_forecast
        snap = r.last_snapshot
        if lf is None or lf.decision is not shown:
            return []
        if snap is None or snap.digest != lf.input_digest:
            return []
        return self._groups(snap)

    def _groups(self, snap: Any) -> list[S.FactorGroup]:
        sums: dict[str, float] = {}
        for f, c in self.model.contributions(snap).items():
            g = BY_NAME[f].group.value
            sums[g] = sums.get(g, 0.0) + c
        top = sorted(sums.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:3]
        return [
            S.FactorGroup(
                group=g,
                label=GROUP_LABEL.get(g, g),
                contribution=v,
                direction="raises_risk" if v > 0 else "lowers_risk",
            )
            for g, v in top
        ]

    def patient(self, key: str) -> S.PatientView:
        i, r = self._runner(key)
        rec, d = self._shown(i, r)
        st = r.state
        now = self._require().now(i)
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
            now_ts=now,
            model_status=self.model.status,
            current=decision_view(rec, d, self.model.status),
            summary=summary(
                d, self._since(r, d), [g.group for g in groups], self.cgm_cfg.utc_offset_s
            ),
            trend=self._trend(r, d),
            cgm_mgdl=self._cgm_now(r, d),
            data_age_s=None if not st.cgm.n else now - int(st.cgm.series.ts[-1]),
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
        s = self._require()
        found = None
        for r in s.runners:
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
            "ack_offset_s": s.offset,
            "reason": req.reason.value,
            "user_role": req.user_role.value,
            "model_version": self.model.model_version,
            "received_utc": utc_now_iso(),
        }
        self.acks[req.decision_id] = rec
        if s.log is not None:
            s.log.write("acks", rec)
        self.publish({"type": "acknowledgement", **rec})
        return rec

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
            "freeze_status": "NOT FROZEN (development)",
            "data_utc_offset_s": self.cgm_cfg.utc_offset_s,
            "pc10_mode": {
                "value": self.pc10_mode,
                "status": "PENDING owner decision (P-C10); system_error = current specification",
            },
            "source": SOURCE_LABEL,
            "caveat": LABEL_CAVEAT,
        }

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
            "confirmatory": "PENDING (sealed evaluation partition not opened)",
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
            "comparisons": comps,
            "curves": curves,
            "calibration_decision": res.get("pb1_calibration", {}).get("decision"),
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
                "Research prototype; not a medical device; not clinically validated.",
                "Development evidence only: tuning partition, internal cross-validation. The "
                "evaluation partition is sealed.",
                "The target is a CGM-detected low; CGM and capillary glucose often disagree "
                "(gate G3b TRIGGERED). The supported action is capillary confirmation.",
                "Medication exposure is estimated from logged doses with fixed population-level "
                "kernels.",
                "No dose or treatment recommendations are made.",
            ],
            "caveat": LABEL_CAVEAT,
        }

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
