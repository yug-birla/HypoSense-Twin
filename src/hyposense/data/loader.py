"""Production loader for ShanghaiT2DM recording workbooks (Blueprint §10.1, Table 25.2).

Guarantees:
- Deterministic discovery: file names must match <pid>_<period>_<YYYYMMDD>.xls[x]; anything
  else in the recordings directory is an error.
- Cells are read raw (``dtype=object``) and parsed explicitly. pandas' type inference is not
  trusted, because an empty dose column would otherwise come back as float64.
- No row is ever deleted. Problems become per-row flags plus `LoadIssue` records. Exclusions
  happen only in explicit accessors (`cgm_series`), which count every excluded row by reason.
- Timestamps: naive local → UTC epoch seconds with the configured fixed offset (ASSUMPTION +08:00).

This module knows nothing about labels, features, models or policy.
"""

from __future__ import annotations

import math
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from hyposense.common.timeconv import local_naive_to_epoch_s, parse_utc_offset
from hyposense.data.columns import (
    CANONICAL_COLUMNS,
    NUMERIC_COLUMNS,
    TEXT_COLUMNS,
    SchemaError,
    map_columns,
)
from hyposense.data.records import (
    RECORDING_FRAME_COLUMNS,
    CGMSeries,
    InvalidRecordingNameError,
    IssueCode,
    LoadIssue,
    Recording,
    Severity,
    check_frame,
    parse_recording_name,
)

DEFAULT_UTC_OFFSET = "+08:00"
GLUCOSE_COLUMNS = frozenset({"cgm", "cbg"})
CGM_PLAUSIBLE_RANGE = (20.0, 600.0)  # Blueprint Table 25.1 invariant for Observation.value
_TS_TEXT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M")


def discover_recordings(recordings_dir: Path) -> list[Path]:
    """Sorted recording files. Raises on any unexpected entry (strict, deterministic)."""
    if not recordings_dir.is_dir():
        raise FileNotFoundError(f"recordings directory not found: {recordings_dir}")
    paths = sorted(recordings_dir.iterdir(), key=lambda p: p.name)
    bad = [p.name for p in paths if not p.is_file()]
    if bad:
        raise InvalidRecordingNameError(f"unexpected non-file entries: {bad}")
    for p in paths:
        parse_recording_name(p.name)  # raises InvalidRecordingNameError
    keys = [p.name.rsplit(".", 1)[0] for p in paths]
    dupes = [k for k, n in Counter(keys).items() if n > 1]
    if dupes:
        raise InvalidRecordingNameError(f"recording keys present in more than one format: {dupes}")
    return paths


def read_workbook(path: Path) -> tuple[str, pd.DataFrame]:
    """Return (sheet name, raw object frame). Exactly one worksheet is required."""
    sheets = pd.read_excel(path, sheet_name=None, dtype=object, header=0)
    if len(sheets) != 1:
        raise SchemaError(f"{path.name}: expected exactly one worksheet, found {list(sheets)}")
    name, frame = next(iter(sheets.items()))
    return str(name), frame


def _is_missing(v: object) -> bool:
    return v is None or v is pd.NaT or (isinstance(v, float) and math.isnan(v))


def _parse_ts(v: object) -> tuple[np.datetime64 | None, IssueCode | None]:
    if _is_missing(v):
        return None, IssueCode.TIMESTAMP_MISSING
    if isinstance(v, pd.Timestamp):
        return v.to_datetime64().astype("datetime64[us]"), None
    if isinstance(v, datetime):
        return np.datetime64(v, "us"), None
    if isinstance(v, str):
        s = v.strip()
        for fmt in _TS_TEXT_FORMATS:
            try:
                return np.datetime64(datetime.strptime(s, fmt), "us"), None
            except ValueError:
                continue
    # Excel serial numbers and anything else are not guessed.
    return None, IssueCode.TIMESTAMP_UNPARSEABLE


def _parse_number(v: object) -> tuple[float, IssueCode | None]:
    if _is_missing(v):
        return math.nan, None
    if isinstance(v, bool):
        return math.nan, IssueCode.VALUE_UNPARSEABLE
    if isinstance(v, int | float | np.integer | np.floating):
        return float(v), None
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return math.nan, None
        try:
            f = float(s)
        except ValueError:
            return math.nan, IssueCode.VALUE_UNPARSEABLE
        return (
            (f, IssueCode.NUMERIC_AS_TEXT)
            if math.isfinite(f)
            else (math.nan, IssueCode.VALUE_UNPARSEABLE)
        )
    return math.nan, IssueCode.VALUE_UNPARSEABLE


def _text_cell(v: object) -> tuple[str | None, IssueCode | None]:
    if _is_missing(v):
        return None, None
    if isinstance(v, str):
        return (v, None) if v.strip() else (None, None)
    if isinstance(v, int | float | np.integer | np.floating) and not isinstance(v, bool):
        f = float(v)
        return (str(int(f)) if f.is_integer() else repr(f)), IssueCode.NUMERIC_IN_TEXT_COLUMN
    return str(v), IssueCode.NUMERIC_IN_TEXT_COLUMN


_SEVERITY: dict[IssueCode, Severity] = {
    IssueCode.TIMESTAMP_MISSING: "error",
    IssueCode.TIMESTAMP_UNPARSEABLE: "error",
    IssueCode.VALUE_UNPARSEABLE: "error",
    IssueCode.TIMESTAMP_SUBSECOND: "warning",
    IssueCode.TIMESTAMP_NON_MONOTONE: "warning",
    IssueCode.DUPLICATE_TIMESTAMP: "warning",
    IssueCode.EXACT_DUPLICATE_ROW: "warning",
    IssueCode.CGM_OUT_OF_RANGE: "warning",
    IssueCode.SHEET_NAME_MISMATCH: "warning",
    IssueCode.NOMINAL_START_MISMATCH: "warning",
    IssueCode.TIMESTAMP_HAS_SECONDS: "info",
    IssueCode.NUMERIC_AS_TEXT: "info",
    IssueCode.NUMERIC_IN_TEXT_COLUMN: "info",
    IssueCode.COLUMN_ABSENT: "info",
    IssueCode.UNITLESS_HEADER: "info",
    IssueCode.EMPTY_ROW: "info",
}


def load_recording(
    path: Path,
    *,
    utc_offset: str = DEFAULT_UTC_OFFSET,
    cgm_range: tuple[float, float] = CGM_PLAUSIBLE_RANGE,
) -> Recording:
    identity = parse_recording_name(path.name)
    key = identity.recording_key
    offset_s = parse_utc_offset(utc_offset)
    issues: list[LoadIssue] = []

    def add(
        code: IssueCode, row: int | None = None, column: str | None = None, detail: str = ""
    ) -> None:
        severity = _SEVERITY[code]
        if code is IssueCode.VALUE_UNPARSEABLE and column not in GLUCOSE_COLUMNS:
            # Text in a medication column (e.g. "temporarily suspend insulin delivery") is kept
            # verbatim in raw_<col> for the medication parser (S3); it is not a glucose defect.
            severity = "warning"
        issues.append(LoadIssue(code, severity, key, row, column, detail))

    sheet, raw = read_workbook(path)
    if sheet != key:
        add(IssueCode.SHEET_NAME_MISMATCH, detail=f"sheet {sheet!r} != file {key!r}")
    cmap = map_columns(list(raw.columns))
    df = raw.rename(columns=cmap.to_canonical)
    for c in cmap.absent:
        df[c] = None
        add(IssueCode.COLUMN_ABSENT, column=c)
    for c in cmap.unitless:
        add(IssueCode.UNITLESS_HEADER, column=c, detail="unit assumed from canonical schema")

    n = len(df)
    source_row = np.arange(2, n + 2, dtype=np.int64)
    out: dict[str, object] = {"source_row": source_row}

    # --- timestamps ---
    ts_local = np.full(n, np.datetime64("NaT"), dtype="datetime64[us]")
    for i, v in enumerate(df["ts_local"].tolist()):
        parsed, problem = _parse_ts(v)
        if problem is not None:
            add(problem, int(source_row[i]), "ts_local", repr(v)[:80])
            continue
        assert parsed is not None
        ts_local[i] = parsed
        us = int(parsed.astype(np.int64))
        if us % 1_000_000:
            add(IssueCode.TIMESTAMP_SUBSECOND, int(source_row[i]), "ts_local", str(parsed))
        elif (us // 1_000_000) % 60:
            add(IssueCode.TIMESTAMP_HAS_SECONDS, int(source_row[i]), "ts_local", str(parsed))
    ts_valid = ~np.isnat(ts_local)
    # Sub-second parts (float drift, e.g. 09:28:59.985 in 2029_0's device-change rows) are
    # rounded to the nearest second, not truncated; each such row is flagged above.
    us = ts_local[ts_valid].astype(np.int64)
    ts_local[ts_valid] = ((us + 500_000) // 1_000_000 * 1_000_000).astype("datetime64[us]")
    ts = np.zeros(n, dtype=np.int64)
    ts[ts_valid] = local_naive_to_epoch_s(ts_local[ts_valid], offset_s)
    out["ts_local"] = ts_local

    # --- numeric columns (raw text preserved when not a clean number) ---
    raw_cols: dict[str, list[str | None]] = {}
    for c in NUMERIC_COLUMNS:
        vals = np.full(n, np.nan)
        raw_keep: list[str | None] = [None] * n
        for i, v in enumerate(df[c].tolist()):
            f, problem = _parse_number(v)
            vals[i] = f
            if problem is not None:
                raw_keep[i] = str(v)
                add(problem, int(source_row[i]), c, repr(v)[:80])
        out[c] = vals
        raw_cols[c] = raw_keep
    lo, hi = cgm_range
    cgm_vals = out["cgm"]
    assert isinstance(cgm_vals, np.ndarray)
    for i in np.flatnonzero(np.isfinite(cgm_vals) & ((cgm_vals < lo) | (cgm_vals > hi))).tolist():
        add(IssueCode.CGM_OUT_OF_RANGE, int(source_row[i]), "cgm", str(cgm_vals[i]))

    # --- text columns (verbatim; whitespace-only cells are missing) ---
    for c in TEXT_COLUMNS:
        cells: list[str | None] = []
        for i, v in enumerate(df[c].tolist()):
            s, problem = _text_cell(v)
            cells.append(s)
            if problem is not None:
                add(problem, int(source_row[i]), c, repr(v)[:80])
        out[c] = pd.array(cells, dtype=object)

    # --- ordering, duplicates, monotonicity (flags only; nothing removed) ---
    non_mono = np.zeros(n, dtype=bool)
    running = None
    for i in np.flatnonzero(ts_valid).tolist():
        if running is not None and ts[i] < running:
            non_mono[i] = True
            add(IssueCode.TIMESTAMP_NON_MONOTONE, int(source_row[i]), "ts_local")
        running = ts[i] if running is None else max(running, ts[i])
    dup_ts = np.zeros(n, dtype=bool)
    if ts_valid.any():
        counts = Counter(ts[ts_valid].tolist())
        dup_ts = ts_valid & np.array([counts.get(int(t), 0) > 1 for t in ts])
        for i in np.flatnonzero(dup_ts).tolist():
            add(IssueCode.DUPLICATE_TIMESTAMP, int(source_row[i]), "ts_local")
    content = pd.DataFrame({c: out[c] for c in CANONICAL_COLUMNS})
    exact_dup = content.astype(str).duplicated(keep="first").to_numpy() & ts_valid
    for i in np.flatnonzero(exact_dup).tolist():
        add(IssueCode.EXACT_DUPLICATE_ROW, int(source_row[i]))
    other = [c for c in CANONICAL_COLUMNS if c != "ts_local"]
    empty = ts_valid & content[other].isna().all(axis=1).to_numpy()
    for i in np.flatnonzero(empty).tolist():
        add(IssueCode.EMPTY_ROW, int(source_row[i]))
    if ts_valid.any():
        first = pd.Timestamp(ts_local[ts_valid].min()).date()
        if first != identity.nominal_start:
            add(
                IssueCode.NOMINAL_START_MISMATCH,
                detail=f"first timestamp {first} vs file-name date {identity.nominal_start}",
            )

    frame = pd.DataFrame(
        {
            "source_row": source_row,
            **{c: out[c] for c in CANONICAL_COLUMNS},
            "ts": pd.array(np.where(ts_valid, ts, 0), dtype="Int64"),
            **{f"raw_{c}": pd.array(raw_cols[c], dtype=object) for c in NUMERIC_COLUMNS},
            "ts_valid": ts_valid,
            "ts_non_monotone": non_mono,
            "dup_ts": dup_ts,
            "exact_dup": exact_dup,
        }
    )
    frame.loc[~ts_valid, "ts"] = pd.NA
    sort_key = np.where(ts_valid, ts, np.iinfo(np.int64).max)
    order = np.lexsort((source_row, sort_key))
    frame = frame.iloc[order].reset_index(drop=True)[list(RECORDING_FRAME_COLUMNS)]
    check_frame(frame)
    return Recording(
        identity=identity,
        frame=frame,
        header_variant=cmap.variant_id,
        sheet_name=sheet,
        unitless_columns=cmap.unitless,
        absent_columns=cmap.absent,
        issues=tuple(issues),
    )


def cgm_series(rec: Recording) -> CGMSeries:
    """Strictly increasing CGM readings. Every excluded reading is counted by reason."""
    f = rec.frame
    has = f["cgm"].notna().to_numpy()
    valid = f["ts_valid"].to_numpy(bool)
    excluded: Counter[str] = Counter()
    excluded["invalid_timestamp"] = int((has & ~valid).sum())
    exact = f["exact_dup"].to_numpy(bool)
    excluded["exact_duplicate_row"] = int((has & valid & exact).sum())
    keep = has & valid & ~exact
    sub = f.loc[keep, ["ts", "cgm", "source_row"]]
    ts = sub["ts"].to_numpy(np.int64)
    val = sub["cgm"].to_numpy(np.float64)
    row = sub["source_row"].to_numpy(np.int64)
    first = np.ones(len(ts), dtype=bool)
    first[1:] = ts[1:] != ts[:-1]  # frame is sorted by (ts, source_row): keep first row
    if not first.all():
        dropped = np.flatnonzero(~first)
        conflicting = int(sum(val[i] != val[i - 1] for i in dropped))
        excluded["duplicate_timestamp_conflicting_value"] = conflicting
        excluded["duplicate_timestamp_same_value"] = len(dropped) - conflicting
    return CGMSeries(
        recording_key=rec.identity.recording_key,
        ts=ts[first],
        value=val[first],
        source_row=row[first],
        excluded={k: v for k, v in sorted(excluded.items()) if v},
    )
