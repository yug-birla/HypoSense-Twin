"""Recording-level medication parsing and the production treated-status definition.

Rows flagged `exact_dup` by the loader are skipped, and the skip is counted. Rows without a valid
timestamp cannot be timed: they are counted as TIMING_UNKNOWN entries and produce no events,
because administration times are never fabricated.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from hyposense.data.records import Recording
from hyposense.medication.dictionary import DrugDictionary, normalise_text
from hyposense.medication.events import EntryParse, MedicationEvent
from hyposense.medication.parse import Context, parse_cell

MED_COLUMNS = ("insulin_sc", "oral_agents", "insulin_iv", "csii_bolus", "csii_basal")
TARGET_CLASSES = ("insulin", "sulfonylurea", "glinide")


@dataclass(frozen=True)
class RecordingMedication:
    recording_key: str
    patient_key: str
    entries: tuple[EntryParse, ...]
    events: tuple[MedicationEvent, ...]  # sorted by (ts, source_row, column order)
    skipped: dict[str, int]  # reason -> cells not parsed (duplicate rows, untimed rows)


def _cells(f: pd.DataFrame, col: str) -> list[tuple[int, Any, bool, bool]]:
    """(row position, value, ts_valid, exact_dup) for non-missing cells of a column."""
    values = f[col].to_numpy(dtype=object)
    raw = f[f"raw_{col}"].to_numpy(dtype=object) if f"raw_{col}" in f else None
    valid = f["ts_valid"].to_numpy(dtype=bool)
    dup = f["exact_dup"].to_numpy(dtype=bool)
    out = []
    for pos in range(len(f)):
        v = values[pos]
        if raw is not None and pd.notna(raw[pos]) and pd.isna(v):
            v = raw[pos]  # text in a numeric CSII column
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        out.append((pos, v, bool(valid[pos]), bool(dup[pos])))
    return out


def parse_recording(
    rec: Recording, d: DrugDictionary, formulation_rules: dict[str, Any]
) -> RecordingMedication:
    f = rec.frame
    ts_arr = f["ts"].to_numpy(dtype="float64", na_value=np.nan)  # NA only on untimed rows (skipped)
    rows = f["source_row"].to_numpy(dtype="int64")
    entries: list[EntryParse] = []
    skipped = {"exact_duplicate_row": 0, "untimed_row": 0}
    for col_order, col in enumerate(MED_COLUMNS):
        for pos, value, ts_ok, dup in _cells(f, col):
            if dup:
                skipped["exact_duplicate_row"] += 1
                continue
            if not ts_ok:
                skipped["untimed_row"] += 1
                continue
            ctx = Context(
                patient_key=rec.identity.patient_key,
                recording_key=rec.identity.recording_key,
                ts=int(ts_arr[pos]),
                source_column=col,
                source_row=int(rows[pos]),
                raw_text=str(value),
            )
            entries.append(parse_cell(value, col, ctx, d, formulation_rules))
            _ = col_order
    order = {c: k for k, c in enumerate(MED_COLUMNS)}
    events = sorted(
        (e for en in entries for e in en.events),
        key=lambda e: (e.ts, e.source_row, order[e.source_column]),
    )
    return RecordingMedication(
        rec.identity.recording_key, rec.identity.patient_key, tuple(entries), tuple(events), skipped
    )


@dataclass(frozen=True)
class TreatmentStatus:
    insulin: bool
    sulfonylurea: bool
    glinide: bool

    @property
    def treated(self) -> bool:
        """Blueprint Table 5.1: >= 1 logged insulin (any route), sulfonylurea or glinide."""
        return self.insulin or self.sulfonylurea or self.glinide


def treatment_status(meds: Sequence[RecordingMedication]) -> TreatmentStatus:
    """Patient-level status over all of the patient's recordings (population definition only;
    never a model input)."""
    logged = {e.drug_class for m in meds for e in m.events if e.is_target_administration}
    return TreatmentStatus("insulin" in logged, "sulfonylurea" in logged, "glinide" in logged)


def prescribed_classes(text: object, d: DrugDictionary) -> frozenset[str]:
    """Drug classes named in the summary's prescribed-regimen text (static context)."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return frozenset()
    norm = normalise_text(str(text))
    classes: set[str] = set()
    for m in d.alias_regex.finditer(norm):
        e = d.lookup(m.group(1))
        classes.update(d.by_canonical(c).drug_class for c in e.components)
    return frozenset(classes)
