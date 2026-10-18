"""SYNTHETIC stream builders for state-engine and feature tests. No real patient data."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from hyposense.common.config import load_config
from hyposense.features.snapshot import FeatureBuilder
from hyposense.medication.dictionary import load_dictionary
from hyposense.medication.events import MedicationEvent
from hyposense.medication.parse import Context, parse_cell
from hyposense.state.context import REGIMEN_FLAGS, STATIC_FIELDS, PatientContext
from hyposense.state.events import CBGReading, CGMReading, MealEvent, StateEvent, sort_key
from hyposense.state.patient import EngineConfig, PatientState
from hyposense.state.stream import RecordingStream

CFG = load_config()
PHARMA = load_config("pharma.yaml")
D = load_dictionary()
ENGINE = EngineConfig.from_config(CFG, PHARMA)
BUILDER = FeatureBuilder(CFG)
T0 = 1_600_000_800  # 2020-09-13 20:40:00 local (+08:00)
PK, RK = "shanghai_t2dm:9001", "9001_0_20200913"


def context(
    *,
    weight: float = 70.0,
    regimen: str | None = "insulin aspart 70/30; gliclazide",
    recording_key: str = RK,
) -> PatientContext:
    from hyposense.state.context import parse_context

    row: dict[str, object] = {
        "age_y": 60,
        "sex_code": 2,
        "bmi": 24.5,
        "weight_kg": weight,
        "duration_y": 10,
        "hba1c_mmol_mol": 60.0,
        "egfr": "/",
        "c_peptide_fasting_nmol_l": 0.5,
        "prescribed_hypoglycemic_agents": regimen,
    }
    plaus = {k: (float(v[0]), float(v[1])) for k, v in CFG["features"]["static_plausible"].items()}
    return parse_context(PK, recording_key, row, D, plaus)


def blank_context() -> PatientContext:
    return PatientContext(
        PK,
        RK,
        {k: math.nan for k in STATIC_FIELDS},
        {k: math.nan for k in REGIMEN_FLAGS},
        frozenset(),
    )


def cgm(minutes_values: Iterable[tuple[float, float]], rk: str = RK) -> list[CGMReading]:
    return [
        CGMReading(rk, T0 + int(m * 60), float(v), 2 + i) for i, (m, v) in enumerate(minutes_values)
    ]


def meal(minute: float, known: bool = True, row: int = 5000) -> MealEvent:
    return MealEvent(RK, T0 + int(minute * 60), row, known)


def cbg(minute: float, value: float, row: int = 6000) -> CBGReading:
    return CBGReading(RK, T0 + int(minute * 60), value, row)


def med(value: object, column: str, minute: float, row: int = 7000) -> list[MedicationEvent]:
    ctx = Context(PK, RK, T0 + int(minute * 60), column, row, str(value))
    return list(parse_cell(value, column, ctx, D, PHARMA["formulation_rules"]).events)


def stream(events: Sequence[StateEvent], ctx: PatientContext | None = None) -> RecordingStream:
    from hyposense.data.records import parse_recording_name

    c = ctx or context()
    ident = parse_recording_name(c.recording_key + ".xlsx")
    return RecordingStream(ident, c, tuple(sorted(events, key=sort_key)), {})


def run(events: Sequence[StateEvent], ctx: PatientContext | None = None) -> list[PatientState]:
    s = PatientState.start(ctx or context(), ENGINE)
    out = []
    for e in sorted(events, key=sort_key):
        s = s.update(e)
        out.append(s)
    return out


def steady(
    start: float, stop: float, value: float = 120.0, step: float = 15
) -> list[tuple[float, float]]:
    out = []
    m = start
    while m <= stop:
        out.append((m, value))
        m += step
    return out
