"""Intake draft: validation findings → deterministic clarification questions → canonical parse.

Flow: UPLOAD → DETECT ISSUES → QUESTIONS → ANSWERS → REVALIDATE → ACCEPT / REFUSE.

Every question is triggered by a concrete finding, is linked to one schema field, and is
answered from a fixed option list (or, for medication text, by replacement text that the
canonical parser must accept). Unanswered OPTIONAL questions leave the data as recorded, with
the canonical missing / unknown semantics. Unanswered REQUIRED questions block the session.
Nothing is guessed: no unit is inferred from magnitudes, no time zone is assumed, no
formulation or dose is invented.

Clock encoding (DECISION_LOG DEC-2026-10-19-P). The model's time-of-day features read
`time.assumed_utc_offset` (+08:00, the dataset's clock). New data are therefore stored as the
PATIENT-LOCAL wall-clock time encoded at that reference offset, so the features see the
patient's own local hour. UTC exports are first converted to local wall time with the stated
patient offset. Displayed times are the patient's local clock.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from hyposense.common.config import load_config
from hyposense.data.columns import HEADER_VARIANTS, UNITS, normalise_header
from hyposense.data.loader import parse_recording_frame
from hyposense.data.records import Recording, RecordingIdentity
from hyposense.medication.dictionary import DrugDictionary, load_dictionary
from hyposense.medication.events import Flag, ParseStatus
from hyposense.medication.recording import parse_recording
from hyposense.state.context import STATIC_FIELDS, parse_context
from hyposense.state.stream import RecordingStream, recording_stream

INTAKE_PREFIX = "intake:"
MMOL_TO_MGDL = 18.016  # glucose molar mass 180.16 g/mol: 1 mmol/L = 18.016 mg/dL
UNIT_CHECK_MGDL = (40.0, 400.0)  # median CGM after conversion must fall here, else refuse
LOCAL_FMT = "%Y-%m-%d %H:%M:%S"

# canonical column -> (official dataset header written to the canonical parser, display label)
CANONICAL: dict[str, tuple[str, str]] = {
    "ts_local": ("Date", "Date and time of the observation"),
    "cgm": ("CGM (mg / dl)", "CGM glucose"),
    "cbg": ("CBG (mg / dl)", "Capillary (finger-stick) glucose"),
    "ketone": ("Blood Ketone (mmol / L)", "Blood ketone (mmol/L)"),
    "diet_en": ("Dietary intake", "Meal description"),
    "insulin_sc": ("Insulin dose - s.c.", "Subcutaneous insulin (drug and dose)"),
    "oral_agents": ("Non-insulin hypoglycemic agents", "Non-insulin agents (drug and dose)"),
    "insulin_iv": ("Insulin dose - i.v.", "Intravenous insulin"),
    "csii_bolus": ("CSII - bolus insulin (Novolin R, IU)", "Insulin pump bolus (IU)"),
    "csii_basal": ("CSII - basal insulin (Novolin R, IU / H)", "Insulin pump basal rate (IU/h)"),
}
OFFICIAL_ONLY = {"diet_cn": "饮食"}  # mapped from known headers only, never offered
GLUCOSE = ("cgm", "cbg")
PUMP = ("csii_bolus", "csii_basal")
MED_PROBLEM_FLAGS = frozenset({Flag.DOSE_UNKNOWN, Flag.FORMULATION_UNKNOWN, Flag.UNIT_MISSING})
UTC_OFFSETS = tuple(
    f"{'+' if m >= 0 else '-'}{abs(m) // 60:02d}:{abs(m) % 60:02d}"
    for m in sorted({h * 60 for h in range(-12, 15)} | {330, 345, 570, 630, -210, 270, 390, 525})
)
CONTEXT_FIELDS: dict[str, tuple[str, str]] = {
    # form field -> (summary column read by state.context, label with unit)
    "age_y": ("age_y", "Age (years)"),
    "sex": ("sex_code", "Sex"),
    "bmi": ("bmi", "BMI (kg/m²)"),
    "weight_kg": ("weight_kg", "Weight (kg)"),
    "diabetes_duration_y": ("duration_y", "Diabetes duration (years)"),
    "hba1c_mmol_mol": ("hba1c_mmol_mol", "HbA1c (mmol/mol)"),
    "egfr": ("egfr", "eGFR (mL/min/1.73 m²)"),
    "c_peptide_fasting_nmol_l": ("c_peptide_fasting_nmol_l", "Fasting C-peptide (nmol/L)"),
    "prescribed_agents": ("prescribed_hypoglycemic_agents", "Prescribed glucose-lowering agents"),
}
SEX_CODES = {"female": 1, "male": 2}  # dataset coding (state.context: 1 → 0, 2 → 1)
assert set(STATIC_FIELDS.values()) <= {c for c, _ in CONTEXT_FIELDS.values()}

_TZ_RE = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")
_NAIVE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
)


@dataclass(frozen=True)
class Question:
    id: str
    field: str  # schema field the answer sets
    prompt: str
    reason: str  # the finding that triggered it
    kind: str  # "choice" | "text"
    options: tuple[tuple[str, str], ...]  # (value, label)
    required: bool
    suggested: str | None = None
    answer: str | None = None
    error: str | None = None  # the last answer was not accepted (why)

    @property
    def impact(self) -> str:
        """What happens if the user cannot answer (shown next to every question)."""
        if self.id.startswith("column:"):
            return "If unsure, choose “Ignore this column”: it is then not used."
        if self.id.startswith("unit:"):
            return "Required: without the unit these readings cannot be used."
        if self.id in ("clock", "patient_utc_offset"):
            return "Required: without it the times of day would be wrong."
        if self.id == "pump_insulin":
            return "If it is another insulin, the pump columns are ignored."
        if self.id.startswith("med:"):
            return (
                "Optional: if kept as recorded, whatever cannot be read is treated as unknown — "
                "never guessed."
            )
        return ""


@dataclass(frozen=True)
class Finding:
    severity: str  # "blocking" | "warning" | "info"
    code: str
    message: str
    count: int = 1


@dataclass
class DraftResult:
    status: str  # "BLOCKED" | "NEEDS_ANSWERS" | "READY"
    findings: list[Finding]
    questions: list[Question]
    mapping: list[dict[str, Any]]
    preview: list[dict[str, Any]]
    summary: dict[str, Any] = field(default_factory=dict)
    recording: Recording | None = None
    stream: RecordingStream | None = None
    summary_row: dict[str, object] | None = None
    frame: pd.DataFrame | None = None  # canonical-header frame (session source)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


def _missing(v: object) -> bool:
    return (
        v is None
        or v is pd.NaT
        or (isinstance(v, float) and math.isnan(v))
        or (isinstance(v, str) and not v.strip())
    )


def _explicit_unit(header: str) -> str | None:
    h = header.lower().replace(" ", "")
    if "mmol/l" in h:
        return "mmol/L"
    if "mg/dl" in h:
        return "mg/dL"
    return None


def _suggest_column(header: str) -> str | None:
    h = header.lower()
    for words, canon in (
        (("time", "date"), "ts_local"),
        (("cgm", "sensor", "interstitial"), "cgm"),
        (("capillary", "finger", "cbg", "smbg"), "cbg"),
        (("meal", "diet", "food", "carb"), "diet_en"),
    ):
        if any(w in h for w in words):
            return canon
    return None


def _parse_offset(tz: str) -> int:
    if tz == "Z":
        return 0
    sign = 1 if tz[0] == "+" else -1
    digits = tz[1:].replace(":", "")
    return sign * (int(digits[:2]) * 3600 + int(digits[2:]) * 60)


def _classify_ts(v: object) -> tuple[str, datetime | None, int | None]:
    """("naive" | "aware" | "invalid" | "missing", wall time, offset s)."""
    if _missing(v):
        return "missing", None, None
    if isinstance(v, pd.Timestamp):
        if v.tzinfo is not None:
            off = v.utcoffset()
            return (
                "aware",
                v.tz_localize(None).to_pydatetime(),
                int(off.total_seconds()) if off else 0,
            )
        return "naive", v.to_pydatetime(), None
    if isinstance(v, datetime):
        if v.tzinfo is not None:
            off = v.utcoffset()
            return "aware", v.replace(tzinfo=None), int(off.total_seconds()) if off else 0
        return "naive", v, None
    if isinstance(v, str):
        s = v.strip()
        m = _TZ_RE.search(s)
        if m and ("T" in s or " " in s):
            base = s[: m.start()].strip()
            for fmt in _NAIVE_FORMATS:
                try:
                    return "aware", datetime.strptime(base, fmt), _parse_offset(m.group(1))
                except ValueError:
                    continue
            return "invalid", None, None
        for fmt in _NAIVE_FORMATS:
            try:
                return "naive", datetime.strptime(s, fmt), None
            except ValueError:
                continue
    return "invalid", None, None  # Excel serial numbers and anything else are not guessed


def _number(v: object) -> float | None:
    if _missing(v):
        return None
    try:
        f = float(str(v).strip())
    except ValueError:
        return None
    return f if math.isfinite(f) else None


class Draft:
    """One intake draft (in memory). `answers` maps question id → answer value."""

    def __init__(
        self,
        draft_id: str,
        patient_id: str,
        raw: pd.DataFrame | None,
        file_name: str | None,
        label: str | None = None,
    ) -> None:
        self.draft_id = draft_id
        self.patient_id = patient_id  # pseudonym "N0001"; never a name
        self.raw = raw
        self.file_name = file_name
        self.label = label
        self.answers: dict[str, str] = {}
        self.context: dict[str, str] = {}
        self._d: DrugDictionary = load_dictionary()
        cfg = load_config()
        self._pharma = load_config("pharma.yaml")
        self._plaus = {
            k: (float(v[0]), float(v[1])) for k, v in cfg["features"]["static_plausible"].items()
        }
        self._reference_offset = str(cfg["time"]["assumed_utc_offset"])

    # ------------------------------------------------------------------ helpers
    @property
    def patient_key(self) -> str:
        return INTAKE_PREFIX + self.patient_id

    def identity(self, first_local: date) -> RecordingIdentity:
        key = f"{self.patient_id}_0_{first_local:%Y%m%d}"
        return RecordingIdentity(
            recording_key=key,
            patient_id=self.patient_id,
            patient_key=self.patient_key,
            period=0,
            nominal_start=first_local,
            file_name=f"{key}.intake",
            file_format="intake",
        )

    def summary_row(self) -> tuple[dict[str, object] | None, list[Finding]]:
        """Context form → the summary-row mapping read by `state.context.parse_context`."""
        if not any(v.strip() for v in self.context.values()):
            return None, [
                Finding(
                    "info",
                    "CONTEXT_ABSENT",
                    "No patient context given: every context feature is treated as missing "
                    "(never zero). Context is optional.",
                )
            ]
        row: dict[str, object] = {}
        out: list[Finding] = []
        for name, (col, label) in CONTEXT_FIELDS.items():
            v = (self.context.get(name) or "").strip()
            if not v:
                continue
            if name == "sex":
                if v not in SEX_CODES:
                    out.append(Finding("warning", "CONTEXT_INVALID", f"{label}: '{v}' ignored"))
                    continue
                row[col] = SEX_CODES[v]
            else:
                row[col] = v
        ctx = parse_context(self.patient_key, "", row, self._d, self._plaus)
        for issue in ctx.issues:
            fld, why = issue.split(":", 1)
            if why.strip() == "missing":
                continue
            out.append(Finding("warning", "CONTEXT_INVALID", f"{fld}: {why.strip()} → missing"))
        return row, out

    # ------------------------------------------------------------------ evaluation
    def evaluate(self) -> DraftResult:
        if self.raw is None:
            return self._evaluate_empty()
        findings: list[Finding] = []
        questions: list[Question] = []
        headers = [str(c) for c in self.raw.columns]
        to_canon: dict[str, str] = {}
        unit_of: dict[str, str | None] = {}
        mapping_rows: list[dict[str, Any]] = []
        for i, h in enumerate(headers):
            key = normalise_header(h)
            if key in HEADER_VARIANTS:
                canon, explicit = HEADER_VARIANTS[key]
                source = "recognised header"
                unit = UNITS.get(canon) if explicit else _explicit_unit(h)
            else:
                qid = f"column:{i}"
                taken = {c for c in to_canon.values()}
                free = [(c, lbl) for c, (_, lbl) in CANONICAL.items() if c not in taken]
                opts = (("ignore", "Ignore this column"), *free)
                ans = self.answers.get(qid)
                err = None
                if ans is not None and ans not in {o[0] for o in opts}:
                    err, ans = "not an available option", None
                questions.append(
                    Question(
                        qid,
                        f"column[{h}]",
                        f"What does the column “{h}” contain?",
                        "We don't recognise this column name, and we won't guess what it holds.",
                        "choice",
                        tuple(opts),
                        True,
                        _suggest_column(h),
                        ans,
                        err,
                    )
                )
                if ans is None or ans == "ignore":
                    mapping_rows.append(
                        {"header": h, "canonical": None, "label": "ignored" if ans else "?"}
                    )
                    continue
                canon, source, unit = ans, "your answer", _explicit_unit(h)
            if canon in to_canon.values():
                findings.append(
                    Finding("blocking", "COLUMN_CONFLICT", f"Two columns map to {canon}.")
                )
                continue
            to_canon[h] = canon
            unit_of[canon] = unit
            label = CANONICAL.get(canon, (canon, "Meal description (Chinese)"))[1]
            mapping_rows.append({"header": h, "canonical": canon, "label": label, "source": source})
        mapped = set(to_canon.values())
        has_data = {
            c: any(not _missing(v) for v in self.raw[h].tolist()) for h, c in to_canon.items()
        }
        for req, lbl in (("ts_local", "date/time"), ("cgm", "CGM glucose")):
            if req not in mapped:
                findings.append(
                    Finding(
                        "blocking",
                        "REQUIRED_COLUMN_MISSING",
                        f"No {lbl} column identified yet: answer the column questions.",
                    )
                )

        # ---- glucose units (never inferred from magnitudes)
        for g in GLUCOSE:
            if g in mapped and unit_of.get(g) is None and has_data.get(g, False):
                qid = f"unit:{g}"
                ans = self.answers.get(qid)
                ok = ans in ("mg/dL", "mmol/L")
                questions.append(
                    Question(
                        qid,
                        f"{g}.unit",
                        f"Which unit are the {CANONICAL[g][1]} values in?",
                        "We need the unit to read the values correctly; it cannot safely be "
                        "assumed from the size of the numbers.",
                        "choice",
                        (("mg/dL", "mg/dL"), ("mmol/L", "mmol/L")),
                        True,
                        None,
                        ans if ok else None,
                        None if ans is None or ok else "not an available option",
                    )
                )
                unit_of[g] = ans if ok else None

        # ---- pump insulin (the canonical CSII columns are regular human insulin)
        pump_ok = True
        if any(has_data.get(c, False) for c in PUMP):
            qid = "pump_insulin"
            ans = self.answers.get(qid)
            opts = (
                ("regular_human", "Regular human insulin (e.g. Novolin R)"),
                ("other", "Another insulin: pump columns are not supported and will be ignored"),
            )
            questions.append(
                Question(
                    qid,
                    "csii.insulin",
                    "Which insulin is delivered by the insulin pump?",
                    "Pump data can only be modelled for regular human insulin.",
                    "choice",
                    opts,
                    True,
                    None,
                    ans if ans in ("regular_human", "other") else None,
                )
            )
            pump_ok = ans == "regular_human"
            if ans == "other":
                findings.append(
                    Finding(
                        "warning", "PUMP_IGNORED", "Pump columns ignored (unsupported insulin)."
                    )
                )

        # ---- timestamps and clock
        ts_header = next((h for h, c in to_canon.items() if c == "ts_local"), None)
        local: list[str | None] = []
        if ts_header is not None:
            kinds = [_classify_ts(v) for v in self.raw[ts_header].tolist()]
            offsets = {o for k, _, o in kinds if k == "aware"}
            n_aware = sum(k == "aware" for k, _, _ in kinds)
            n_naive = sum(k == "naive" for k, _, _ in kinds)
            n_bad = sum(k == "invalid" for k, _, _ in kinds)
            if n_bad:
                findings.append(
                    Finding(
                        "warning",
                        "TIMESTAMP_UNPARSEABLE",
                        "Rows with an unreadable date/time are kept as untimed and not used.",
                        n_bad,
                    )
                )
            clock: str | None = None
            patient_offset: int | None = None
            if n_aware and (n_naive or len(offsets) > 1):
                findings.append(
                    Finding(
                        "blocking",
                        "MIXED_TIME_ZONES",
                        "Timestamps mix time zones or zone-less values; export one consistent "
                        "clock.",
                    )
                )
            elif n_aware and offsets == {0}:
                clock = "utc"
                findings.append(Finding("info", "TIMESTAMPS_UTC", "Timestamps are marked as UTC."))
            elif n_aware:
                clock = "aware_local"
                findings.append(
                    Finding(
                        "info",
                        "TIMESTAMPS_OFFSET",
                        "Timestamps carry a UTC offset; the written wall-clock time is used as "
                        "the patient's local time.",
                    )
                )
            else:
                qid = "clock"
                ans = self.answers.get(qid)
                ok = ans in ("local", "utc")
                questions.append(
                    Question(
                        qid,
                        "ts_local.clock",
                        "Which clock were these date/time values recorded in?",
                        "Forecasts use the patient's local time of day, and the file does not "
                        "say which clock was used.",
                        "choice",
                        (("local", "The patient's local clock time"), ("utc", "UTC")),
                        True,
                        None,
                        ans if ok else None,
                    )
                )
                clock = ans if ok else None
            if clock == "utc":
                qid = "patient_utc_offset"
                ans = self.answers.get(qid)
                ok = ans in UTC_OFFSETS
                questions.append(
                    Question(
                        qid,
                        "patient.utc_offset",
                        "What was the patient's local UTC offset during this recording?",
                        "UTC times must be converted to the patient's local clock.",
                        "choice",
                        tuple((o, f"UTC{o}") for o in UTC_OFFSETS),
                        True,
                        None,
                        ans if ok else None,
                    )
                )
                patient_offset = _parse_offset(ans) if ok and ans else None
            for k, wall, off in kinds:
                if k not in ("naive", "aware") or wall is None:
                    local.append(None)
                elif clock == "utc":
                    if patient_offset is None:
                        local.append(None)
                    else:
                        utc_wall = wall - timedelta(seconds=off or 0)
                        local.append(
                            (utc_wall + timedelta(seconds=patient_offset)).strftime(LOCAL_FMT)
                        )
                else:
                    local.append(wall.strftime(LOCAL_FMT))

        blocking = [f for f in findings if f.severity == "blocking"]
        unanswered = [q for q in questions if q.required and q.answer is None]
        preview_src = self.raw.head(8)
        preview = [
            {h: (None if _missing(v) else str(v)) for h, v in zip(headers, row, strict=True)}
            for row in preview_src.itertuples(index=False)
        ]
        if blocking or unanswered:
            return DraftResult(
                "BLOCKED" if blocking else "NEEDS_ANSWERS",
                findings,
                questions,
                mapping_rows,
                preview,
            )

        # ---- canonical frame (official headers), unit conversion, unit plausibility
        out: dict[str, list[object]] = {}
        for h, canon in to_canon.items():
            if canon in PUMP and not pump_ok:
                continue
            if canon == "ts_local":
                out[CANONICAL["ts_local"][0]] = list(local)
                continue
            vals = self.raw[h].tolist()
            if canon in GLUCOSE and unit_of.get(canon) == "mmol/L":
                conv: list[object] = []
                for v in vals:
                    n = _number(v)
                    conv.append(v if n is None else round(n * MMOL_TO_MGDL, 1))
                vals = conv
            header = CANONICAL[canon][0] if canon in CANONICAL else OFFICIAL_ONLY[canon]
            out[header] = vals
        frame = pd.DataFrame(out, dtype=object)
        cgm_num = [x for x in (_number(v) for v in frame[CANONICAL["cgm"][0]]) if x is not None]
        if not cgm_num:
            findings.append(Finding("blocking", "NO_CGM_VALUES", "No numeric CGM value found."))
        else:
            med = float(np.median(cgm_num))
            lo, hi = UNIT_CHECK_MGDL
            if not lo <= med <= hi:
                findings.append(
                    Finding(
                        "blocking",
                        "UNIT_IMPLAUSIBLE",
                        f"The median CGM value ({med:.1f} mg/dL after the stated unit) is "
                        "implausible; check the unit. The data are not accepted.",
                    )
                )
        valid_local = [x for x in local if x is not None]
        if not valid_local:
            findings.append(Finding("blocking", "NO_TIMESTAMPS", "No readable date/time value."))
        if any(f.severity == "blocking" for f in findings):
            return DraftResult("BLOCKED", findings, questions, mapping_rows, preview)

        # ---- medication clarification (re-parsed by the canonical parser)
        first = min(datetime.strptime(x, LOCAL_FMT) for x in valid_local).date()
        ident = self.identity(first)
        med_questions, frame = self._medication_questions(frame, ident)
        questions += med_questions
        rec = parse_recording_frame(
            frame, ident, ident.recording_key, utc_offset=self._reference_offset
        )
        row, ctx_findings = self.summary_row()
        findings += ctx_findings
        stream = recording_stream(rec, self._d, self._pharma["formulation_rules"], row, self._plaus)
        findings += self._recording_findings(rec, stream)
        unanswered = [q for q in questions if q.required and q.answer is None]
        status = "NEEDS_ANSWERS" if unanswered else "READY"
        return DraftResult(
            status,
            findings,
            questions,
            mapping_rows,
            preview,
            self._summary(rec, stream),
            rec,
            stream,
            row,
            frame,
        )

    def _parse(self, frame: pd.DataFrame, ident: RecordingIdentity) -> Recording:
        return parse_recording_frame(
            frame, ident, ident.recording_key, utc_offset=self._reference_offset
        )

    def _evaluate_empty(self) -> DraftResult:
        """Mode B: a new patient with no file yet (observations are added afterwards)."""
        row, findings = self.summary_row()
        findings.append(
            Finding(
                "info",
                "NO_OBSERVATIONS",
                "No observations yet. More recent CGM history is required before a forecast "
                "is available.",
            )
        )
        return DraftResult("READY", findings, [], [], [], {"cgm_readings": 0}, None, None, row)

    def _medication_questions(
        self, frame: pd.DataFrame, ident: RecordingIdentity
    ) -> tuple[list[Question], pd.DataFrame]:
        """Entries the parser cannot resolve → optional questions. An accepted replacement is
        written into the canonical frame (the original text is kept in the audit trail)."""
        questions: list[Question] = []
        frame = frame.copy()
        probe_ident = ident
        rec = parse_recording_frame(
            frame, probe_ident, ident.recording_key, utc_offset=self._reference_offset
        )
        meds = parse_recording(rec, self._d, self._pharma["formulation_rules"])
        seen: set[tuple[str, str]] = set()
        for en in meds.entries:
            flags = {f for e in en.events for f in e.flags}
            problem = en.status in (ParseStatus.UNPARSEABLE, ParseStatus.AMBIGUOUS) or bool(
                flags & MED_PROBLEM_FLAGS
            )
            if not problem or (en.source_column, en.raw_text) in seen:
                continue
            seen.add((en.source_column, en.raw_text))
            qid = f"med:{en.source_column}:{_sha(en.raw_text)}"
            why = (
                en.status.value
                if not flags & MED_PROBLEM_FLAGS
                else ", ".join(sorted(f.value for f in flags & MED_PROBLEM_FLAGS))
            )
            ans = self.answers.get(qid)
            err = None
            accepted = None
            if ans is not None and ans != "keep":
                text = ans.removeprefix("replace:").strip()
                ok, msg = self._check_replacement(text, en.source_column, ident)
                if ok:
                    accepted = text
                else:
                    err, ans = msg, None
            questions.append(
                Question(
                    qid,
                    f"{en.source_column}[{en.raw_text}]",
                    f"“{en.raw_text}” ({CANONICAL[en.source_column][1].lower()}): which drug "
                    "and dose was given?",
                    f"We could not fully read this entry ({why.lower().replace('_', ' ')}).",
                    "text",
                    (("keep", "Keep as recorded (treated as unknown where not interpretable)"),),
                    False,
                    None,
                    ans,
                    err,
                )
            )
            if accepted is not None:
                header = CANONICAL[en.source_column][0]
                col = frame[header].astype(object)
                frame[header] = [
                    accepted if (str(v).strip() == en.raw_text.strip()) else v for v in col
                ]
        return questions, frame

    def _check_replacement(
        self, text: str, column: str, ident: RecordingIdentity
    ) -> tuple[bool, str]:
        from hyposense.medication.parse import Context, parse_cell

        if not text:
            return False, "empty replacement"
        ctx = Context(
            patient_key=ident.patient_key,
            recording_key=ident.recording_key,
            ts=0,
            source_column=column,
            source_row=0,
            raw_text=text,
        )
        en = parse_cell(text, column, ctx, self._d, self._pharma["formulation_rules"])
        flags = {f for e in en.events for f in e.flags}
        if (
            en.status in (ParseStatus.UNPARSEABLE, ParseStatus.AMBIGUOUS)
            or flags & MED_PROBLEM_FLAGS
        ):
            return False, f"still not interpretable ({en.status.value}); keep as recorded instead"
        return True, ""

    @staticmethod
    def _recording_findings(rec: Recording, stream: RecordingStream) -> list[Finding]:
        counts: dict[tuple[str, str], int] = {}
        for i in rec.issues:
            if i.code.value in ("column_absent", "sheet_name_mismatch", "nominal_start_mismatch"):
                continue
            k = (i.severity, i.code.value)
            counts[k] = counts.get(k, 0) + 1
        out = [
            Finding(
                "warning" if sev != "info" else "info", code.upper(), _ISSUE_TEXT.get(code, code), n
            )
            for (sev, code), n in sorted(counts.items(), key=lambda kv: kv[0][1])
        ]
        excl = {k: v for k, v in stream.excluded.items() if v}
        if excl:
            out.append(
                Finding(
                    "info",
                    "ROWS_EXCLUDED",
                    "Rows not used as events (counted, never deleted): "
                    + ", ".join(f"{k} {v}" for k, v in sorted(excl.items())),
                    sum(excl.values()),
                )
            )
        return out

    @staticmethod
    def _summary(rec: Recording, stream: RecordingStream) -> dict[str, Any]:
        from hyposense.medication.events import MedicationEvent
        from hyposense.state.events import CBGReading, CGMReading, MealEvent

        ev = stream.events
        cgm = [e for e in ev if isinstance(e, CGMReading)]
        span = (cgm[-1].ts - cgm[0].ts) / 3600 if len(cgm) > 1 else 0.0
        meds = [e for e in ev if isinstance(e, MedicationEvent)]
        return {
            "rows": len(rec.frame),
            "cgm_readings": len(cgm),
            "cgm_span_h": round(span, 1),
            "capillary_readings": sum(isinstance(e, CBGReading) for e in ev),
            "meals": sum(isinstance(e, MealEvent) for e in ev),
            "medication_events": len(meds),
            "target_administrations": sum(e.is_target_administration for e in meds),
            "first_local": None if not cgm else local_text(cgm[0].ts),
            "last_local": None if not cgm else local_text(cgm[-1].ts),
        }


def local_text(ts: int) -> str:
    from hyposense.common.timeconv import parse_utc_offset

    off = parse_utc_offset(str(load_config()["time"]["assumed_utc_offset"]))
    return datetime.fromtimestamp(ts + off, tz=UTC).strftime("%Y-%m-%d %H:%M")


_ISSUE_TEXT = {
    "duplicate_timestamp": "Rows share a timestamp (kept and flagged; CGM keeps the first)",
    "exact_duplicate_row": "Exact duplicate rows (not used twice)",
    "timestamp_non_monotone": "Rows out of time order (re-ordered; flagged)",
    "timestamp_missing": "Rows without a date/time (not used)",
    "timestamp_unparseable": "Unreadable date/time values (not used)",
    "cgm_out_of_range": "CGM values outside 20 to 600 mg/dL (not used)",
    "value_unparseable": "Non-numeric values in numeric columns (kept as text)",
    "empty_row": "Rows with a time but no observation",
    "timestamp_has_seconds": "Timestamps with seconds",
    "timestamp_subsecond": "Timestamps with fractions of a second (rounded)",
    "unitless_header": "Header without a unit",
    "numeric_as_text": "Numbers stored as text (read as numbers)",
    "numeric_in_text_column": "Numbers in a text column (kept as text)",
}
