"""Typed ingestion contracts: recording identity, load issues, loaded recordings, CGM series.

Row-level data is held in a pandas DataFrame whose columns are documented in
`RECORDING_FRAME_COLUMNS` and checked by `check_frame`. Per-row Pydantic objects would cost too
much on the batch path. Boundaries are typed by the frozen dataclasses below.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Literal

import numpy as np
import numpy.typing as npt
import pandas as pd

from hyposense.data.columns import CANONICAL_COLUMNS, NUMERIC_COLUMNS

PATIENT_KEY_PREFIX = "shanghai_t2dm:"
RECORDING_NAME_RE = re.compile(r"^(?P<pid>\d{4})_(?P<period>\d+)_(?P<date>\d{8})\.(?P<ext>xlsx?)$")

Severity = Literal["error", "warning", "info"]


class InvalidRecordingNameError(ValueError):
    """A file name does not follow <patient>_<period>_<YYYYMMDD>.xls[x]."""


@dataclass(frozen=True)
class RecordingIdentity:
    recording_key: str  # "2001_0_20201102"
    patient_id: str  # "2001" (file-name prefix; 109 recordings belong to 100 patients)
    patient_key: str  # "shanghai_t2dm:2001" — the ONLY key used for grouping
    period: int  # 0, 1, 2 … (recording index within patient)
    nominal_start: date  # date encoded in the file name
    file_name: str
    file_format: str  # "xls" | "xlsx"


def parse_recording_name(file_name: str) -> RecordingIdentity:
    m = RECORDING_NAME_RE.match(file_name)
    if not m:
        raise InvalidRecordingNameError(f"unexpected recording file name: {file_name!r}")
    d = m.group("date")
    try:
        nominal = date(int(d[:4]), int(d[4:6]), int(d[6:]))
    except ValueError as exc:
        raise InvalidRecordingNameError(f"invalid date in file name {file_name!r}") from exc
    pid = m.group("pid")
    return RecordingIdentity(
        recording_key=file_name.rsplit(".", 1)[0],
        patient_id=pid,
        patient_key=PATIENT_KEY_PREFIX + pid,
        period=int(m.group("period")),
        nominal_start=nominal,
        file_name=file_name,
        file_format=m.group("ext"),
    )


class IssueCode(StrEnum):
    SHEET_NAME_MISMATCH = "sheet_name_mismatch"
    COLUMN_ABSENT = "column_absent"
    UNITLESS_HEADER = "unitless_header"
    NOMINAL_START_MISMATCH = "nominal_start_mismatch"
    TIMESTAMP_MISSING = "timestamp_missing"
    TIMESTAMP_UNPARSEABLE = "timestamp_unparseable"
    TIMESTAMP_SUBSECOND = "timestamp_subsecond"
    TIMESTAMP_HAS_SECONDS = "timestamp_has_seconds"
    TIMESTAMP_NON_MONOTONE = "timestamp_non_monotone"
    DUPLICATE_TIMESTAMP = "duplicate_timestamp"
    EXACT_DUPLICATE_ROW = "exact_duplicate_row"
    VALUE_UNPARSEABLE = "value_unparseable"
    NUMERIC_AS_TEXT = "numeric_as_text"
    NUMERIC_IN_TEXT_COLUMN = "numeric_in_text_column"
    CGM_OUT_OF_RANGE = "cgm_out_of_range"
    EMPTY_ROW = "empty_row"


@dataclass(frozen=True)
class LoadIssue:
    code: IssueCode
    severity: Severity
    recording_key: str
    source_row: int | None = None  # 1-based spreadsheet row (header = row 1)
    column: str | None = None
    detail: str = ""


# Frame columns produced by the loader (sorted by ts_local, NaT last, then source_row).
FLAG_COLUMNS = ("ts_valid", "ts_non_monotone", "dup_ts", "exact_dup")
RECORDING_FRAME_COLUMNS: tuple[str, ...] = (
    "source_row",
    *CANONICAL_COLUMNS,
    "ts",
    *(f"raw_{c}" for c in NUMERIC_COLUMNS),
    *FLAG_COLUMNS,
)


@dataclass(frozen=True)
class Recording:
    identity: RecordingIdentity
    frame: pd.DataFrame
    header_variant: str
    sheet_name: str
    unitless_columns: tuple[str, ...]
    absent_columns: tuple[str, ...]
    issues: tuple[LoadIssue, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CGMSeries:
    """Strictly increasing CGM readings of one recording, with an explicit exclusion account."""

    recording_key: str
    ts: npt.NDArray[np.int64]  # UTC epoch seconds
    value: npt.NDArray[np.float64]  # mg/dL
    source_row: npt.NDArray[np.int64]
    excluded: dict[str, int]  # reason -> count (no silent drops)


def check_frame(frame: pd.DataFrame) -> None:
    """Contract check for loader output; raises AssertionError on violation."""
    assert tuple(frame.columns) == RECORDING_FRAME_COLUMNS, list(frame.columns)
    assert frame["source_row"].is_unique
    for c in NUMERIC_COLUMNS:
        assert frame[c].dtype == np.float64, (c, frame[c].dtype)
    assert str(frame["ts"].dtype) == "Int64"
    valid = frame["ts_valid"].to_numpy(bool)
    ts = frame.loc[valid, "ts"].to_numpy(np.int64)
    assert np.all(np.diff(ts) >= 0), "frame not sorted by timestamp"
