"""Live new-data session: one patient twin that is updated in place, append-only.

The session keeps the canonical-header frame of everything accepted so far. An appended
observation becomes one more row; the WHOLE frame is re-parsed by the canonical modules
(`parse_recording_frame` → `recording_stream`), and the new event stream must extend the old one
exactly (prefix check). Only the new events are fed to the existing TwinRunner, so no other
patient and no earlier state is rebuilt, and an appended observation follows exactly the same
validation path as an uploaded one.

Ordering: an observation must be strictly later than the latest event already in the twin. The
twin is causal and append-only; it never rewrites the past. Earlier observations belong in an
upload.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from hyposense.common.config import load_config
from hyposense.common.provenance import utc_now_iso
from hyposense.common.timeconv import parse_utc_offset
from hyposense.data.loader import CGM_PLAUSIBLE_RANGE, parse_recording_frame
from hyposense.data.records import RecordingIdentity
from hyposense.intake.draft import CANONICAL, LOCAL_FMT, MMOL_TO_MGDL
from hyposense.medication.dictionary import load_dictionary
from hyposense.replay.runner import DecisionRecord, Pipeline, TwinRunner
from hyposense.replay.session import DecisionLog
from hyposense.state.stream import RecordingStream, recording_stream

KINDS = ("cgm", "cbg", "meal", "medication")
MED_COLUMNS_ALLOWED = ("insulin_sc", "oral_agents")


class ObservationRejected(ValueError):
    """The observation is not accepted; the message is shown to the user."""


@dataclass
class LiveSession:
    identity: RecordingIdentity
    label: str | None
    origin: str  # "upload" | "manual"
    frame: pd.DataFrame  # canonical headers
    summary_row: dict[str, object] | None
    runner: TwinRunner
    log: DecisionLog | None
    audit: list[dict[str, Any]] = field(default_factory=list)
    created_utc: str = field(default_factory=utc_now_iso)

    @property
    def key(self) -> str:
        return self.identity.recording_key

    @property
    def now(self) -> int:
        """Data time of the twin: the latest processed event (0 before any)."""
        ts = self.runner.state.ts
        return int(ts) if ts is not None else 0


def _parse(frame: pd.DataFrame, ident: RecordingIdentity, summary_row: Any) -> RecordingStream:
    cfg, pharma = load_config(), load_config("pharma.yaml")
    plaus = {k: (float(v[0]), float(v[1])) for k, v in cfg["features"]["static_plausible"].items()}
    rec = parse_recording_frame(
        frame, ident, ident.recording_key, utc_offset=str(cfg["time"]["assumed_utc_offset"])
    )
    return recording_stream(rec, load_dictionary(), pharma["formulation_rules"], summary_row, plaus)


def start_session(
    identity: RecordingIdentity,
    label: str | None,
    origin: str,
    frame: pd.DataFrame | None,
    summary_row: dict[str, object] | None,
    pipe: Pipeline,
    log: DecisionLog | None,
    audit: list[dict[str, Any]],
) -> tuple[LiveSession, list[DecisionRecord]]:
    """Build the twin from the accepted frame, processing every event in canonical order."""
    if frame is None:
        frame = pd.DataFrame({h: pd.Series(dtype=object) for h, _ in CANONICAL.values()})
    stream = _parse(frame, identity, summary_row)
    runner = TwinRunner(stream, pipe)
    s = LiveSession(identity, label, origin, frame, summary_row, runner, log, list(audit))
    return s, _feed(s, 0)


def _feed(s: LiveSession, start: int) -> list[DecisionRecord]:
    out = []
    r = s.runner
    for j in range(start, len(r.stream.events)):
        before = len(r.rejected)
        rec = r.feed(j, r.stream.events[j])
        if s.log is not None:
            if rec is not None:
                s.log.write("decisions", rec.log(r.pipe.model))
            for x in r.rejected[before:]:
                s.log.write("rejected", {"recording_key": s.key, **x})
        if rec is not None:
            out.append(rec)
    return out


def _value(raw: Any, unit: str | None) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError) as exc:
        raise ObservationRejected("the glucose value must be a number") from exc
    if not math.isfinite(v):
        raise ObservationRejected("the glucose value must be finite")
    if unit not in ("mg/dL", "mmol/L"):
        raise ObservationRejected("state the glucose unit (mg/dL or mmol/L)")
    mgdl = round(v * MMOL_TO_MGDL, 1) if unit == "mmol/L" else v
    lo, hi = CGM_PLAUSIBLE_RANGE
    if not lo <= mgdl <= hi:
        raise ObservationRejected(f"{mgdl:g} mg/dL is outside the accepted {lo:g}-{hi:g} range")
    return mgdl


def append_observation(s: LiveSession, obs: dict[str, Any]) -> dict[str, Any]:
    """Validate one observation, extend the canonical frame, re-parse, feed the new events."""
    kind = obs.get("kind")
    if kind not in KINDS:
        raise ObservationRejected(f"unknown observation type {kind!r}")
    try:
        when = datetime.strptime(str(obs.get("local_time", "")).strip(), "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise ObservationRejected("time must be YYYY-MM-DD HH:MM (patient local clock)") from exc
    if when.date() < date(2000, 1, 1):
        raise ObservationRejected("implausible date")
    cfg = load_config()
    off = parse_utc_offset(str(cfg["time"]["assumed_utc_offset"]))
    epoch = int((when - datetime(1970, 1, 1)).total_seconds()) - off
    latest = s.runner.state.ts
    if latest is not None and epoch <= latest:
        raise ObservationRejected(
            "the observation must be later than the latest observation in the twin; the twin is "
            "append-only (include earlier observations in an upload instead)"
        )
    row: dict[str, object] = {h: None for h in s.frame.columns}
    row[CANONICAL["ts_local"][0]] = when.strftime(LOCAL_FMT)
    if kind in ("cgm", "cbg"):
        row[CANONICAL[kind][0]] = _value(obs.get("value"), obs.get("unit"))
    elif kind == "meal":
        text = str(obs.get("text") or "").strip()
        row[CANONICAL["diet_en"][0]] = text[:200] if text else "meal (content not described)"
    else:
        col = obs.get("column")
        if col not in MED_COLUMNS_ALLOWED:
            raise ObservationRejected("medication type must be insulin_sc or oral_agents")
        text = str(obs.get("text") or "").strip()
        if not text:
            raise ObservationRejected("enter the drug and dose as administered")
        row[CANONICAL[col][0]] = text[:200]
    new_frame = pd.concat([s.frame, pd.DataFrame([row], dtype=object)], ignore_index=True)
    old = s.runner.stream
    new = _parse(new_frame, s.identity, s.summary_row)
    if len(new.events) <= len(old.events):
        raise ObservationRejected("the observation produced no usable event (see data quality)")
    if new.events[: len(old.events)] != old.events:
        raise ObservationRejected(
            "the observation is not later than the data already in the twin; the twin is "
            "append-only (include earlier observations in an upload instead)"
        )
    first_new = new.events[len(old.events)].ts
    if s.runner.state.ts is not None and first_new <= s.runner.state.ts:
        raise ObservationRejected(
            "the observation must be later than the latest observation in the twin"
        )
    s.frame = new_frame
    s.runner.stream = new
    decisions = _feed(s, len(old.events))
    entry = {
        "at_utc": utc_now_iso(),
        "kind": kind,
        "local_time": when.strftime("%Y-%m-%d %H:%M"),
        "events": len(new.events) - len(old.events),
        "decisions": [r.decision.state.value for r in decisions],
    }
    s.audit.append(entry)  # in-memory audit trail (no values; deleted with the session)
    return entry
