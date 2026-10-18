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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from hyposense.api import schemas as S
from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.features.snapshot import FeatureBuilder
from hyposense.features.spec import BY_NAME
from hyposense.models.artifact import RuntimeModel, load_artifact
from hyposense.policy.decide import PolicyDecision, PolicyState, current
from hyposense.policy.messages import LABEL_CAVEAT, probability_text, texts
from hyposense.replay.runner import DecisionRecord, Pipeline, TwinRunner
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
MAX_CONSECUTIVE_ERRORS = 5


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
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
    ) -> None:
        self.cfg, self.pharma = load_config(), load_config("pharma.yaml")
        self.model: RuntimeModel = load_artifact(model_dir, self.cfg, self.pharma)  # refuses
        self.pipe = Pipeline(
            EngineConfig.from_config(self.cfg, self.pharma),
            FeatureBuilder(self.cfg),
            self.model,
            MAX_CONSECUTIVE_ERRORS,
        )
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

    # ------------------------------------------------------------------ session lifecycle
    def _new_log(self) -> DecisionLog:
        self._segments += 1
        self.session_id = f"{make_run_id('replay')}-{self._segments:03d}"
        self.decisions_logged = 0
        self.acks = {}
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
            raise NotFound(f"unknown or non-permitted recording(s): {unknown}")
        self._streams = [self.catalog[k] for k in keys]
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
            raise ValueError(f"offset beyond the replay duration ({s.duration} s)")
        s.seek(offset, self._new_log())
        self.decisions_logged = sum(len(r.decisions) for r in s.runners)
        self._clock = float(s.offset)
        self.playing = False
        self.publish({"type": "session", **self.status().model_dump()})

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
            q = r.state.quality
            badges = sorted(set(d.tags) | ({"SENSOR_FAULT_SUSPECTED"} & set(d.reasons)))
            if r.halted:
                badges.append("RUNNER_HALTED")
            if (
                q is not None
                and q.sensor_fault_suspected
                and "SENSOR_FAULT_SUSPECTED" not in badges
            ):
                badges.append("SENSOR_FAULT_SUSPECTED")
            unack = sum(1 for n in self._notifications(r) if not n.acknowledged)
            key = (STATE_ORDER[d.state], -(d.p if d.p is not None else -1.0), r.recording_key)
            rows.append((key, i, r, rec, d, badges, unack))
        rows.sort(key=lambda x: x[0])
        beds = [
            S.Bed(
                rank=k + 1,
                recording_key=r.recording_key,
                patient_key=r.patient_key,
                now_ts=s.now(i),
                last_reading_ts=int(r.state.cgm.series.ts[-1]) if r.state.cgm.n else None,
                decision=decision_view(rec, d, self.model.status),
                badges=badges,
                unacknowledged_notifications=unack,
            )
            for k, (_, i, r, rec, d, badges, unack) in enumerate(rows)
        ]
        return S.Ward(session_id=self.session_id, offset_s=s.offset, beds=beds)

    def _runner(self, key: str) -> tuple[int, TwinRunner]:
        s = self._require()
        for i, r in enumerate(s.runners):
            if r.recording_key == key:
                return i, r
        raise NotFound(f"recording {key} is not in the current replay")

    def _factor_groups(self, r: TwinRunner) -> list[S.FactorGroup]:
        lf = r.last_forecast
        snap = r.last_snapshot
        if lf is None or snap is None or snap.digest != lf.input_digest:
            return []
        sums: dict[str, float] = {}
        for f, c in self.model.contributions(snap).items():
            g = BY_NAME[f].group.value
            sums[g] = sums.get(g, 0.0) + c
        top = sorted(sums.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:3]
        return [
            S.FactorGroup(
                group=g, contribution=v, direction="raises_risk" if v > 0 else "lowers_risk"
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
        return S.PatientView(
            recording_key=key,
            patient_key=r.patient_key,
            now_ts=now,
            model_status=self.model.status,
            current=decision_view(rec, d, self.model.status),
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
            medication_quality=med_q,
            data_quality=list(st.quality.reasons) if st.quality is not None else [],
            factor_groups=self._factor_groups(r),
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
            "source": SOURCE_LABEL,
            "caveat": LABEL_CAVEAT,
        }

    def evidence(self) -> dict[str, Any]:
        """DEVELOPMENT evidence (T inner CV, S6). Confirmatory evidence: PENDING (E sealed)."""
        run = self.model.manifest["provenance"].get("s6_run")
        path = REPO_ROOT / "experiments" / "runs" / str(run) / "results.json"
        doc = json.loads(path.read_text("utf-8"))
        res = doc["results"]
        lad = res["ladder"]
        return {
            "status": "DEVELOPMENT",
            "confirmatory": "PENDING (sealed evaluation partition not opened)",
            "run_id": doc["run_id"],
            "results_sha256": doc["results_sha256"],
            "provenance": {k: doc["provenance"].get(k) for k in ("git", "config_sha256")},
            "ladder": {
                pop: {
                    name: {
                        "sens_at_1fa": v["sens_at_1fa"],
                        "partial_area": v.get("partial_area"),
                    }
                    for name, v in lad[pop]["models"].items()
                }
                for pop in lad
            },
            "comparisons": lad["treated"].get("comparisons", {}),
            "interpretation": (
                "Development only. M2/M3r/M3 do not separate on T (all intervals include 0); "
                "ordering among them is uninformative (DEC-2026-10-18-I)."
            ),
        }

    # ------------------------------------------------------------------ stream
    def subscribe(self) -> asyncio.Queue[dict[str, Any] | None]:
        q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(SUBSCRIBER_QUEUE)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any] | None]) -> None:
        self.subscribers.discard(q)

    def publish(self, msg: dict[str, Any]) -> None:
        """Typed, versioned stream message. A subscriber that falls behind is disconnected (it
        reconnects and re-reads the snapshot endpoints); the replay never blocks on a client."""
        full = {"v": S.STREAM_VERSION, **msg}
        for q in list(self.subscribers):
            try:
                q.put_nowait(full)
            except asyncio.QueueFull:
                self.subscribers.discard(q)
                while not q.empty():
                    q.get_nowait()
                q.put_nowait(None)
