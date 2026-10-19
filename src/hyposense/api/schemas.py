"""Typed, versioned API contracts (ADR-008). Frontend types are generated from the OpenAPI schema.
Responses carry the model status (DEVELOPMENT / CONFIRMATORY) wherever a probability appears."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

API_VERSION = "1.0.0"
STREAM_VERSION = 1


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AckReason(StrEnum):
    """Blueprint §16.4 / Table 25.1: exactly four reason codes."""

    CHECKED_GLUCOSE = "checked_glucose"
    KNOWN = "known"
    SENSOR_ISSUE = "sensor_issue"
    NOT_RELEVANT = "not_relevant"


class UserRole(StrEnum):
    NURSE = "nurse"
    PHYSICIAN = "physician"
    RESEARCHER = "researcher"


RECORDING_KEY = r"^N?[0-9]{4}_[0-9]+_[0-9]{8}$"  # N = new-data (intake) session


# ---------------------------------------------------------------- requests
class SelectRequest(Strict):
    recording_keys: list[Annotated[str, Field(max_length=32)]] = Field(min_length=1, max_length=12)


class SpeedRequest(Strict):
    speed: float = Field(ge=1, le=3600)


class StepRequest(Strict):
    n: int = Field(default=1, ge=1, le=2000)


class AdvanceRequest(Strict):
    seconds: int = Field(ge=0, le=6 * 3600)


class SeekRequest(Strict):
    offset_s: int = Field(ge=0)


class AckRequest(Strict):
    decision_id: str = Field(min_length=1, max_length=64, pattern=r"^N?[0-9_]+@[0-9]+(#e[0-9]+)?$")
    reason: AckReason
    user_role: UserRole


# ---------------------------------------------------------------- responses
class Health(Strict):
    status: str
    artifact_verified: bool
    model_version: str
    model_status: str


class DecisionView(Strict):
    decision_id: str | None
    ts: int
    state: str
    p: float | None
    p_text: str | None
    reasons: list[str]
    tags: list[str]
    notify: bool
    texts: list[str]
    model_status: str


class ForecastView(Strict):
    decision_id: str
    ts: int
    p: float
    p_text: str
    state: str
    is_current: bool  # False: older than the current decision; never shown as current


class Trend(Strict):
    rate_mgdl_per_min: float | None  # canonical cgm_slope30 at the latest reading
    category: str | None  # steady | rising | rising_fast | falling | falling_fast


class Bed(Strict):
    rank: int
    recording_key: str
    patient_key: str
    source: str = "HISTORICAL_REPLAY"  # | "NEW_DATA_SESSION"
    label: str | None = None  # pseudonymous display label of a new-data session
    now_ts: int
    last_reading_ts: int | None
    data_age_s: int | None
    stale: bool  # no reading for longer than the policy sufficiency gap (policy.current)
    cgm_low: bool  # latest observed reading below the event threshold
    cgm_mgdl: float | None  # latest observed reading (measured, never forecast)
    trend: Trend
    decision: DecisionView
    summary: str
    reason: str  # one line: policy reason or top associated factor groups
    # critical quality badges: SENSOR_FAULT_SUSPECTED, RUNNER_HALTED, INPUT_REJECTED
    badges: list[str]
    info_tags: list[str]  # informational tags (MED_TIMING_UNKNOWN:*, EVENT_REJECTED)
    unacknowledged_notifications: int


class Ward(Strict):
    session_id: str | None
    offset_s: int
    beds: list[Bed]


class FactorGroup(Strict):
    group: str
    label: str
    contribution: float  # raw-margin TreeSHAP sum (pre-calibration; associations, not causes)
    direction: str  # raises_risk | lowers_risk


class Dose(Strict):
    ts: int
    drug_class: str | None
    canonical: str | None
    route: str | None
    dose: float | None
    dose_unit: str | None


class TimelinePoint(Strict):
    decision_id: str
    ts: int
    cgm_mgdl: float
    state: str
    p: float | None
    notify: bool
    in_episode: bool  # causal episode tracker at this reading
    sensor_fault: bool
    exposure: dict[str, float]


class LedgerEntry(Strict):
    forecast_ts: int
    p: float
    p_text: str
    state: str | None
    notified: bool
    outcome: str  # LOW_FOLLOWED | NO_LOW | PENDING | OUTCOME_UNKNOWN
    resolved_ts: int | None


class Notification(Strict):
    decision_id: str
    ts: int
    acknowledged: bool
    reason: str | None


class PatientView(Strict):
    recording_key: str
    patient_key: str
    source: str = "HISTORICAL_REPLAY"  # | "NEW_DATA_SESSION"
    label: str | None = None
    now_ts: int
    model_status: str
    current: DecisionView
    summary: str
    trend: Trend
    cgm_mgdl: float | None
    data_age_s: int | None
    stale: bool  # no reading for longer than the policy sufficiency gap (policy.current)
    cgm_low: bool  # latest observed reading below the event threshold
    last_forecast: ForecastView | None
    cgm: list[tuple[int, float]]  # last 24 h
    cbg: list[tuple[int, float]]
    meals: list[int]
    doses: list[Dose]
    exposure: dict[str, float]
    exposure_ts: int | None  # evaluated at the latest processed event
    exposure_units: dict[str, str]
    timeline: list[TimelinePoint]  # last 24 h of decisions at CGM readings
    ledger_entries: list[LedgerEntry]  # most recent first
    input_rejected: bool
    medication_quality: dict[str, str]
    data_quality: list[str]
    factor_groups: list[FactorGroup]  # of the current forecast only; [] otherwise
    notifications: list[Notification]
    ledger: dict[str, int]
    rejected_events: int
    halted: bool
    caveat: str


class Case(Strict):
    recording_key: str
    patient_key: str
    days: float
    cgm_readings: int
    partition: str


class ReplayStatus(Strict):
    session_id: str | None
    recordings: list[str]
    playing: bool
    speed: float
    offset_s: int
    duration_s: int
    finished: bool
    decisions_logged: int
    source: str


# ---------------------------------------------------------------- meta / evidence (artefact views)
class Loose(BaseModel):
    """Views of canonical artefacts: fields not listed here are dropped, never invented."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class Meta(Loose):
    api_version: str
    stream_version: int
    model_version: str
    model_status: str
    level: str
    artifact_manifest_sha256: str
    compatibility: dict[str, str]
    provenance: dict[str, object]
    thresholds: dict[str, float | None]
    policy: dict[str, float]
    freeze_status: str
    data_utc_offset_s: int
    source: str
    caveat: str


class LeadTime(Loose):
    median: float | None = None
    q25: float | None = None
    q75: float | None = None
    share_ge_30: float | None = None


class NotificationCounts(Loose):
    true: int = 0
    false: int = 0
    outcome_unknown: int = 0


class OperatingPoint(Loose):
    tau: float | None = None
    episodes: int | None = None
    hits: int | None = None
    sensitivity: float | None = None
    warnable_ceiling: float | None = None
    fa_per_day: float | None = None
    alert_precision: float | None = None
    monitored_days: float | None = None
    lead_min: LeadTime | None = None
    notifications: NotificationCounts | None = None


class Calibration(Loose):
    ece: float | None = None
    slope: float | None = None
    intercept: float | None = None


class ReliabilityBin(Loose):
    n: int
    mean_p: float
    mean_y: float


class LadderModel(Loose):
    sens_at_1fa: float | None
    sens_at_1fa_ci95: list[float] | None = None
    partial_area: float | None = None
    partial_area_ci95: list[float] | None = None
    operating_point: OperatingPoint | None = None
    calibration: Calibration | None = None
    reliability: list[ReliabilityBin] | None = None
    log_loss: float | None = None


class LadderPopulation(Loose):
    patients: int | None = None
    episodes: int | None = None
    models: dict[str, LadderModel]


class Comparison(Loose):
    point: float | None
    ci95: list[float] | None = None
    excludes_zero: bool | None = None  # computed by the backend from ci95


class CurveData(Loose):
    fa_per_day: list[float]
    sensitivity: list[float]
    episodes: float | None = None


class Curves(Loose):
    run_id: str
    results_sha256: str
    treated: dict[str, CurveData]
    all: dict[str, CurveData]


class GateView(Loose):
    gate: str | None
    title: str | None
    status: str | None
    evaluated_utc: str | None
    summary: list[str]
    consequences: list[str]


class Engineering(Loose):
    run_id: str
    results_sha256: str
    commit: str | None
    parity: dict[str, int]
    determinism_identical: bool
    error_injection: dict[str, int]
    long_run: dict[str, float | int | bool]
    latency_ms: dict[str, float]


class Task(Loose):
    target: str
    horizon_min: int
    warning_window_min: list[int]
    fa_budget_per_day: float
    primary_comparison: str
    population_development: str


class ModelInfo(Loose):
    model_version: str
    status: str
    manifest_sha256: str
    compatibility: dict[str, str]
    tau_alert: float
    tau_watch: float | None


class Safeguard(Loose):
    label: str
    value: str
    source: str


class Evidence(Loose):
    status: str
    confirmatory: str
    task: Task
    run_id: str
    results_sha256: str
    commit: str | None
    ladder: dict[str, LadderPopulation]
    comparisons: dict[str, Comparison]
    curves: Curves | None
    calibration_decision: str | None  # the served (canonical) calibrator
    s6_calibrator: str | None = None  # calibrator of the S6 ladder numbers (superseded)
    canonical_calibration: dict[str, Any] | None = None  # canonical calibrator metrics on T
    gates: list[GateView]
    engineering: Engineering | None
    model: ModelInfo
    interpretation: str
    limitations: list[str]
    diagnostics: list[Safeguard]  # post-hoc development diagnostics, quoted from the S6 run
    safeguards: list[Safeguard]
    caveat: str


class AckRecord(Loose):
    decision_id: str
    recording_key: str
    decision_ts: int
    ack_offset_s: int | None  # None for a new-data session (no replay clock)
    reason: str
    user_role: str
    model_version: str
    received_utc: str


# ---------------------------------------------------------------- new-data intake
class IntakeQuestion(Strict):
    id: str
    field: str
    prompt: str
    reason: str
    kind: str  # "choice" | "text"
    options: list[tuple[str, str]]
    required: bool
    suggested: str | None = None
    answer: str | None = None
    error: str | None = None
    impact: str = ""


class IntakeFinding(Strict):
    severity: str  # "blocking" | "warning" | "info"
    code: str
    message: str
    count: int


class IntakeContextField(Strict):
    name: str
    label: str
    value: str


class IntakeDraft(Strict):
    draft_id: str
    patient_id: str
    label: str | None
    file_name: str | None
    status: str  # "BLOCKED" | "NEEDS_ANSWERS" | "READY"
    findings: list[IntakeFinding]
    questions: list[IntakeQuestion]
    mapping: list[dict[str, Any]]
    preview_headers: list[str]
    preview: list[dict[str, Any]]
    summary: dict[str, Any]
    context: list[IntakeContextField]
    notice: str


class IntakeUpload(Strict):
    file_name: Annotated[str, Field(max_length=200)]
    content_base64: Annotated[str, Field(max_length=7_000_000)]
    label: Annotated[str | None, Field(default=None, max_length=24, pattern=r"^[A-Za-z0-9 _-]*$")]


class IntakeNew(Strict):
    label: Annotated[str | None, Field(default=None, max_length=24, pattern=r"^[A-Za-z0-9 _-]*$")]


class IntakeAnswers(Strict):
    answers: dict[str, Annotated[str, Field(max_length=200)]] = {}
    context: dict[str, Annotated[str, Field(max_length=200)]] = {}


class IntakeCommitted(Strict):
    recording_key: str
    decisions: int
    states: dict[str, int]


class Observation(Strict):
    kind: str  # cgm | cbg | meal | medication
    local_time: Annotated[str, Field(max_length=16)]
    value: float | None = None
    unit: str | None = None
    text: Annotated[str | None, Field(default=None, max_length=200)]
    column: str | None = None


class ObservationResult(Strict):
    recording_key: str
    kind: str
    local_time: str
    events: int
    decisions: list[str]


class LiveSessionInfo(Strict):
    recording_key: str
    patient_key: str
    label: str | None
    origin: str
    created_utc: str
    cgm_readings: int
    last_local: str | None
    observations_added: int


class AskAnswer(Strict):
    intent: str
    question: str
    lines: list[str]


class DemoEvent(Strict):
    found: bool
    recording_key: str | None
    ts: int | None
    p_text: str | None
    offset_s: int
    finished: bool
