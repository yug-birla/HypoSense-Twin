"""Typed, versioned API contracts (ADR-008). Frontend types are generated from the OpenAPI schema.
Responses carry the model status (DEVELOPMENT / CONFIRMATORY) wherever a probability appears."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

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


RECORDING_KEY = r"^[0-9]{4}_[0-9]+_[0-9]{8}$"


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
    decision_id: str = Field(min_length=1, max_length=64, pattern=r"^[0-9_]+@[0-9]+(#e[0-9]+)?$")
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


class Bed(Strict):
    rank: int
    recording_key: str
    patient_key: str
    now_ts: int
    last_reading_ts: int | None
    decision: DecisionView
    badges: list[str]
    unacknowledged_notifications: int


class Ward(Strict):
    session_id: str | None
    offset_s: int
    beds: list[Bed]


class FactorGroup(Strict):
    group: str
    contribution: float  # raw-margin TreeSHAP sum (pre-calibration; associations, not causes)
    direction: str  # raises_risk | lowers_risk


class Dose(Strict):
    ts: int
    drug_class: str | None
    canonical: str | None
    route: str | None
    dose: float | None
    dose_unit: str | None


class Notification(Strict):
    decision_id: str
    ts: int
    acknowledged: bool
    reason: str | None


class PatientView(Strict):
    recording_key: str
    patient_key: str
    now_ts: int
    model_status: str
    current: DecisionView
    last_forecast: ForecastView | None
    cgm: list[tuple[int, float]]  # last 24 h
    cbg: list[tuple[int, float]]
    meals: list[int]
    doses: list[Dose]
    exposure: dict[str, float]
    exposure_ts: int | None  # evaluated at the latest processed event
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
