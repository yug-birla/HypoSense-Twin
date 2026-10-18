"""Typed medication contracts (Blueprint Table 25.1 DoseEvent, extended for S3).

One raw medication cell produces one `EntryParse` holding one or more `MedicationEvent`s, one per
component. Nothing is dropped: every component carries a `ParseStatus`, and the raw text and
source column are preserved for audit.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ParseStatus(StrEnum):
    PARSED = "PARSED"  # target drug, dose and unit parsed, no warnings
    PARSED_WITH_WARNING = "PARSED_WITH_WARNING"  # target drug recognised; see flags
    AMBIGUOUS = "AMBIGUOUS"  # recognised, but the quantity cannot be resolved uniquely
    NON_TARGET_MEDICATION = "NON_TARGET_MEDICATION"  # recognised non-target drug or i.v. fluid
    NON_MEDICATION = "NON_MEDICATION"  # recognised non-drug text (pump status, header artefact)
    UNPARSEABLE = "UNPARSEABLE"  # not recognised


class EventKind(StrEnum):
    ADMINISTRATION = "administration"  # a dose given at ts (s.c., oral, CSII bolus, i.v. bag)
    PUMP_BASAL_RATE = "pump_basal_rate"  # CSII basal rate (IU/h) programmed from ts
    PUMP_SUSPEND = "pump_suspend"  # CSII delivery suspended at ts
    IV_FLUID = "iv_fluid"  # non-insulin i.v. component (saline, glucose, KCl)
    NON_MEDICATION_TEXT = "non_medication_text"
    UNRECOGNISED = "unrecognised"


class Flag(StrEnum):
    DOSE_UNKNOWN = "DOSE_UNKNOWN"
    DOSE_IMPLAUSIBLE = "DOSE_IMPLAUSIBLE"  # outside the dictionary's plausible range (value kept)
    ZERO_DOSE = "ZERO_DOSE"
    MULTIPLE_DOSE_CANDIDATES = "MULTIPLE_DOSE_CANDIDATES"
    UNIT_MISSING = "UNIT_MISSING"
    FORMULATION_INFERRED = "FORMULATION_INFERRED"  # e.g. gliclazide 15 mg -> half 30 mg MR tablet
    FORMULATION_UNKNOWN = "FORMULATION_UNKNOWN"
    MISPLACED_COLUMN = "MISPLACED_COLUMN"  # content contradicts the source column
    COMBINATION_PRODUCT = "COMBINATION_PRODUCT"
    RATE_UNKNOWN = "RATE_UNKNOWN"  # i.v. insulin: amount in bag only
    HEADER_ARTEFACT = "HEADER_ARTEFACT"
    UNRECOGNISED_TEXT = "UNRECOGNISED_TEXT"
    GLUCOSE_INFUSION = "GLUCOSE_INFUSION"  # confounder flag (S3.6)


@dataclass(frozen=True)
class MedicationEvent:
    patient_key: str
    recording_key: str
    ts: int  # UTC epoch s (the row timestamp; administration-time ASSUMPTION, Blueprint R4)
    source_column: str
    source_row: int
    raw_text: str  # the whole raw cell
    component_text: str  # the part of the cell this event was parsed from
    kind: EventKind
    parse_status: ParseStatus
    canonical: str | None = None
    drug_class: str | None = None  # insulin | sulfonylurea | glinide | biguanide | ...
    subclass: str | None = None
    route: str | None = None  # sc | oral | csii | iv
    formulation: str | None = None
    formulation_basis: str | None = None  # DICTIONARY | DOSE_RULE | INFERRED | UNKNOWN
    dose: float | None = None
    dose_unit: str | None = None  # IU | mg | IU/h | ml
    concentration_pct: float | None = None  # i.v. fluids
    target: bool = False  # insulin / sulfonylurea / glinide
    exposure_family: str | None = None
    kernel_components: str | None = None
    flags: tuple[Flag, ...] = ()

    @property
    def is_target_administration(self) -> bool:
        """A logged administration that counts toward 'treated' (Table 5.1)."""
        if self.parse_status not in (ParseStatus.PARSED, ParseStatus.PARSED_WITH_WARNING):
            return False
        if not self.target:
            return False
        if self.kind is EventKind.ADMINISTRATION:
            return Flag.ZERO_DOSE not in self.flags
        if self.kind is EventKind.PUMP_BASAL_RATE:
            return (self.dose or 0.0) > 0
        return False


@dataclass(frozen=True)
class EntryParse:
    raw_text: str
    source_column: str
    events: tuple[MedicationEvent, ...]

    @property
    def status(self) -> ParseStatus:
        """Worst component status (UNPARSEABLE > AMBIGUOUS > warning > others)."""
        order = [
            ParseStatus.UNPARSEABLE,
            ParseStatus.AMBIGUOUS,
            ParseStatus.PARSED_WITH_WARNING,
            ParseStatus.PARSED,
            ParseStatus.NON_TARGET_MEDICATION,
            ParseStatus.NON_MEDICATION,
        ]
        present = {e.parse_status for e in self.events}
        return next(s for s in order if s in present)
