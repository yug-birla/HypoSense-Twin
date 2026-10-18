"""Recording -> ordered, typed event stream for the Patient State Engine (Blueprint Fig. 9.1:
Data Adapter -> Patient State Engine).

Sources (no row is silently dropped; every exclusion is counted in `excluded`):
- CGM: `data.loader.cgm_series` (strictly increasing; exclusions counted there).
- CBG: rows with a CBG value, a valid timestamp and not an exact duplicate (display only).
- Meals: rows with diet text in either diet column, a valid timestamp and not an exact
  duplicate. Rows sharing a timestamp form one meal. Content is unknown when every diet text
  equals the dataset's "not recorded" marker ("Data not available" / 未记录; MEASURED on T:
  the two always appear together, 201 rows).
- Medication: `medication.recording.parse_recording` (S3; duplicate and untimed rows counted
  there).

Recordings are independent streams (ANALYSIS_PLAN §0 item 10). `order_recordings` orders a
patient's recordings by first timestamp, never by recording number (S2 finding).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from hyposense.data.dataset import assert_not_sealed
from hyposense.data.loader import cgm_series
from hyposense.data.records import Recording, RecordingIdentity
from hyposense.medication.dictionary import DrugDictionary
from hyposense.medication.recording import parse_recording
from hyposense.state.context import PatientContext, parse_context
from hyposense.state.events import CBGReading, CGMReading, MealEvent, StateEvent, sort_key

MEAL_UNKNOWN_MARKERS = frozenset({"data not available", "未记录"})


@dataclass(frozen=True)
class RecordingStream:
    identity: RecordingIdentity
    context: PatientContext
    events: tuple[StateEvent, ...]  # canonical order
    excluded: dict[str, int]

    @property
    def first_ts(self) -> int | None:
        return self.events[0].ts if self.events else None


def _text(v: object) -> str | None:
    if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
        return None
    s = str(v).strip()
    return s or None


def meal_events(rec: Recording) -> tuple[list[MealEvent], dict[str, int]]:
    f = rec.frame
    key = rec.identity.recording_key
    valid = f["ts_valid"].to_numpy(bool)
    dup = f["exact_dup"].to_numpy(bool)
    en = f["diet_en"].to_numpy(dtype=object)
    cn = f["diet_cn"].to_numpy(dtype=object)
    ts = f["ts"].to_numpy(dtype="float64", na_value=np.nan)
    rows = f["source_row"].to_numpy(dtype="int64")
    by_ts: dict[int, tuple[int, bool]] = {}  # ts -> (first source row, content known)
    excluded = {"meal_untimed_row": 0, "meal_exact_duplicate_row": 0, "meal_same_ts_merged": 0}
    for i in range(len(f)):
        texts = [x for x in (_text(en[i]), _text(cn[i])) if x is not None]
        if not texts:
            continue
        if not valid[i]:
            excluded["meal_untimed_row"] += 1
            continue
        if dup[i]:
            excluded["meal_exact_duplicate_row"] += 1
            continue
        known = any(t.lower() not in MEAL_UNKNOWN_MARKERS for t in texts)
        t = int(ts[i])
        if t in by_ts:
            excluded["meal_same_ts_merged"] += 1
            first_row, k0 = by_ts[t]
            by_ts[t] = (first_row, k0 or known)
        else:
            by_ts[t] = (int(rows[i]), known)
    meals = [MealEvent(key, t, row, known) for t, (row, known) in sorted(by_ts.items())]
    return meals, excluded


def cbg_events(rec: Recording) -> tuple[list[CBGReading], dict[str, int]]:
    f = rec.frame
    has = f["cbg"].notna().to_numpy()
    ok = has & f["ts_valid"].to_numpy(bool) & ~f["exact_dup"].to_numpy(bool)
    sub = f.loc[ok, ["ts", "cbg", "source_row"]]
    key = rec.identity.recording_key
    out = [
        CBGReading(key, int(t), float(v), int(r))
        for t, v, r in zip(sub["ts"].astype("int64"), sub["cbg"], sub["source_row"], strict=True)
    ]
    return out, {"cbg_excluded_row": int(has.sum() - ok.sum())}


def recording_stream(
    rec: Recording,
    d: DrugDictionary,
    formulation_rules: dict[str, Any],
    summary_row: Mapping[str, object] | None,
    plausible: Mapping[str, tuple[float, float]],
) -> RecordingStream:
    ident = rec.identity
    assert_not_sealed(ident.patient_id)  # sealed partition: no E features before freeze
    context = parse_context(ident.patient_key, ident.recording_key, summary_row, d, plausible)
    series = cgm_series(rec)
    cgm: list[StateEvent] = [
        CGMReading(ident.recording_key, int(t), float(v), int(r))
        for t, v, r in zip(series.ts, series.value, series.source_row, strict=True)
    ]
    meals, ex_meal = meal_events(rec)
    cbg, ex_cbg = cbg_events(rec)
    meds = parse_recording(rec, d, formulation_rules)
    events: list[StateEvent] = [*cgm, *meals, *cbg, *meds.events]
    events.sort(key=sort_key)
    excluded = {f"cgm_{k}": v for k, v in series.excluded.items()}
    excluded.update(ex_meal)
    excluded.update(ex_cbg)
    excluded.update({f"medication_{k}": v for k, v in meds.skipped.items()})
    return RecordingStream(ident, context, tuple(events), {k: v for k, v in excluded.items()})


def order_recordings(streams: Sequence[RecordingStream]) -> list[RecordingStream]:
    """A patient's recordings in chronological order of their first event (never by number)."""
    return sorted(
        streams, key=lambda s: (s.first_ts if s.first_ts is not None else 2**62, s.identity.period)
    )
