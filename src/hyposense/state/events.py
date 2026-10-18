"""Typed inputs of the Patient State Engine (Blueprint Table 25.1: Observation, DoseEvent,
MealEvent).

Every event belongs to exactly one recording and carries its source row for audit. Medication
events are the S3 `MedicationEvent` contract, unchanged.

Deterministic order within one timestamp (ARCHITECTURE §3): dose -> meal -> cgm -> cbg, then
source row, then source column. A dose or meal charted at t is therefore known when the CGM
reading at t is processed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import IntEnum

from hyposense.medication.events import MedicationEvent


class EventRank(IntEnum):
    DOSE = 0
    MEAL = 1
    CGM = 2
    CBG = 3


@dataclass(frozen=True)
class CGMReading:
    recording_key: str
    ts: int  # UTC epoch s
    value_mgdl: float
    source_row: int


@dataclass(frozen=True)
class CBGReading:
    """Capillary glucose. Display and audit only: never a feature input (App. D)."""

    recording_key: str
    ts: int
    value_mgdl: float
    source_row: int


@dataclass(frozen=True)
class MealEvent:
    recording_key: str
    ts: int
    source_row: int
    content_known: bool  # False when the diet cell carries no description of what was eaten


StateEvent = CGMReading | CBGReading | MealEvent | MedicationEvent

_COLUMN_ORDER = {
    "insulin_sc": 0,
    "oral_agents": 1,
    "insulin_iv": 2,
    "csii_bolus": 3,
    "csii_basal": 4,
}


class MalformedEventError(ValueError):
    """An event violates its contract (non-finite value, wrong type)."""


def rank(e: StateEvent) -> EventRank:
    if isinstance(e, MedicationEvent):
        return EventRank.DOSE
    if isinstance(e, MealEvent):
        return EventRank.MEAL
    if isinstance(e, CGMReading):
        return EventRank.CGM
    if isinstance(e, CBGReading):
        return EventRank.CBG
    raise MalformedEventError(f"not a state event: {type(e).__name__}")


def sort_key(e: StateEvent) -> tuple[int, int, int, int]:
    col = _COLUMN_ORDER.get(e.source_column, 9) if isinstance(e, MedicationEvent) else 0
    return (e.ts, int(rank(e)), e.source_row, col)


def validate(e: StateEvent) -> None:
    rank(e)
    if isinstance(e, CGMReading | CBGReading) and not math.isfinite(e.value_mgdl):
        raise MalformedEventError(f"non-finite glucose value at ts={e.ts}")
