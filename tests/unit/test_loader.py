"""Loader tests on SYNTHETIC workbooks (no real patient data)."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from hyposense.data.columns import SchemaError
from hyposense.data.loader import cgm_series, load_recording
from hyposense.data.records import RECORDING_FRAME_COLUMNS, IssueCode, check_frame
from tests.conftest import WorkbookFactory, row

T0 = datetime(2020, 11, 2, 9, 40)
NAME = "2001_0_20201102.xlsx"


def _codes(rec: object) -> list[str]:
    return [i.code.value for i in rec.issues]  # type: ignore[attr-defined]


def _clean_rows(n: int = 6) -> list[list[object]]:
    return [row(T0 + timedelta(minutes=15 * k), 100.8 - 1.8 * k) for k in range(n)]


def test_clean_recording_contract_and_epoch(make_workbook: WorkbookFactory) -> None:
    rec = load_recording(make_workbook(NAME, _clean_rows()))
    assert tuple(rec.frame.columns) == RECORDING_FRAME_COLUMNS
    check_frame(rec.frame)
    assert rec.issues == ()
    # 2020-11-02 09:40 at +08:00 == 2020-11-02 01:40 UTC
    expected = int(pd.Timestamp("2020-11-02 01:40", tz="UTC").timestamp())
    assert int(rec.frame["ts"].iloc[0]) == expected
    assert rec.identity.patient_key == "shanghai_t2dm:2001"
    assert rec.identity.recording_key == "2001_0_20201102"


def test_utc_offset_is_configurable(make_workbook: WorkbookFactory) -> None:
    p = make_workbook(NAME, _clean_rows(2))
    a = load_recording(p, utc_offset="+08:00").frame["ts"].iloc[0]
    b = load_recording(p, utc_offset="+00:00").frame["ts"].iloc[0]
    assert int(b) - int(a) == 8 * 3600


def test_text_cells_preserved_verbatim(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(3)
    rows[1] = row(
        T0 + timedelta(minutes=15),
        99.0,
        diet_en="Boiled egg 40 g \nCucumber 100 g",
        diet_cn="白煮蛋40g\n黄瓜100g",
        insulin_sc="Humulin 70/30  8 IU",
        oral="metformin 850 mg",
    )
    rec = load_recording(make_workbook(NAME, rows))
    r = rec.frame.iloc[1]
    assert r["diet_en"] == "Boiled egg 40 g \nCucumber 100 g"
    assert r["diet_cn"] == "白煮蛋40g\n黄瓜100g"
    assert r["insulin_sc"] == "Humulin 70/30  8 IU"
    assert r["oral_agents"] == "metformin 850 mg"


def test_unparseable_cgm_is_kept_flagged_and_raw_preserved(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(4)
    rows[2] = row(T0 + timedelta(minutes=30), "HI")
    rec = load_recording(make_workbook(NAME, rows))
    assert len(rec.frame) == 4  # no row deletion
    bad = rec.frame[rec.frame["source_row"] == 4].iloc[0]
    assert np.isnan(bad["cgm"]) and bad["raw_cgm"] == "HI"
    issue = next(i for i in rec.issues if i.code is IssueCode.VALUE_UNPARSEABLE)
    assert issue.severity == "error" and issue.column == "cgm" and issue.source_row == 4


def test_medication_text_in_numeric_column_is_a_warning(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(3)
    rows[1] = row(
        T0 + timedelta(minutes=15), 99.0, csii_basal="temporarily suspend insulin delivery"
    )
    rec = load_recording(make_workbook(NAME, rows))
    issue = next(i for i in rec.issues if i.code is IssueCode.VALUE_UNPARSEABLE)
    assert issue.severity == "warning"
    assert rec.frame.iloc[1]["raw_csii_basal"] == "temporarily suspend insulin delivery"


def test_numeric_text_and_number_in_text_column(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(3)
    rows[0] = row(T0, " 102.6 ", insulin_sc=8)
    rec = load_recording(make_workbook(NAME, rows))
    assert rec.frame.iloc[0]["cgm"] == pytest.approx(102.6)
    assert rec.frame.iloc[0]["insulin_sc"] == "8"
    codes = _codes(rec)
    assert "numeric_as_text" in codes and "numeric_in_text_column" in codes


def test_missing_and_text_timestamps(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(3)
    rows.insert(1, row(None, 120.0))
    rows.append(row("2020-11-02 10:40", 90.0))
    rows.append(row("not a date", 91.0))
    rec = load_recording(make_workbook(NAME, rows))
    f = rec.frame
    assert len(f) == 6
    assert int(f["ts_valid"].sum()) == 4  # text date parsed; 2 invalid
    assert not f["ts_valid"].iloc[-1] and not f["ts_valid"].iloc[-2]  # invalid sorted last
    codes = _codes(rec)
    assert codes.count("timestamp_missing") == 1 and codes.count("timestamp_unparseable") == 1
    s = cgm_series(rec)
    assert s.excluded == {"invalid_timestamp": 2}
    assert len(s.ts) == 4


def test_non_monotone_rows_are_flagged_and_sorted(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(4)
    rows[1], rows[2] = rows[2], rows[1]
    rec = load_recording(make_workbook(NAME, rows))
    assert "timestamp_non_monotone" in _codes(rec)
    assert int(rec.frame["ts_non_monotone"].sum()) == 1
    assert np.all(np.diff(rec.frame["ts"].to_numpy(np.int64)) > 0)
    assert len(rec.frame) == 4


def test_duplicate_timestamps(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(4)
    rows.append(list(rows[1]))  # exact duplicate
    rows.append(row(T0 + timedelta(minutes=30), 55.5))  # conflicting duplicate of row 3
    rec = load_recording(make_workbook(NAME, rows))
    f = rec.frame
    assert len(f) == 6
    assert int(f["exact_dup"].sum()) == 1
    s = cgm_series(rec)
    assert s.excluded == {"exact_duplicate_row": 1, "duplicate_timestamp_conflicting_value": 1}
    assert len(s.ts) == 4 and np.all(np.diff(s.ts) > 0)
    # first source row wins for the conflicting timestamp
    assert s.value[2] == pytest.approx(100.8 - 3.6)


def test_subsecond_timestamp_rounds_to_nearest_second(make_workbook: WorkbookFactory) -> None:
    rows = [
        row(datetime(2021, 6, 3, 9, 28, 59, 985000), 100.0),
        row(datetime(2021, 6, 3, 9, 44, 0), 101.0),
    ]
    rec = load_recording(make_workbook("2029_0_20210603.xlsx", rows))
    assert pd.Timestamp(rec.frame["ts_local"].iloc[0]) == pd.Timestamp("2021-06-03 09:29:00")
    assert "timestamp_subsecond" in _codes(rec)


def test_out_of_range_cgm_is_flagged_not_removed(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(3)
    rows[1] = row(T0 + timedelta(minutes=15), 700.0)
    rec = load_recording(make_workbook(NAME, rows))
    assert "cgm_out_of_range" in _codes(rec)
    assert len(cgm_series(rec).ts) == 3


def test_empty_row_and_identity_issues(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(3)
    rows.append(row(T0 + timedelta(minutes=45)))
    rec = load_recording(make_workbook("2001_1_20201105.xlsx", rows, sheet_name="2001_9_20990101"))
    codes = _codes(rec)
    assert "empty_row" in codes
    assert "sheet_name_mismatch" in codes
    assert "nominal_start_mismatch" in codes


def test_multiple_sheets_rejected(make_workbook: WorkbookFactory) -> None:
    with pytest.raises(SchemaError):
        load_recording(make_workbook(NAME, _clean_rows(2), extra_sheets=("other",)))


def test_unknown_column_rejected(make_workbook: WorkbookFactory) -> None:
    headers = ("Date", "CGM (mg / dl)", "Mystery column")
    with pytest.raises(SchemaError):
        load_recording(make_workbook(NAME, [[T0, 100.0, 1]], headers=headers))


def test_absent_optional_columns_are_added_and_reported(make_workbook: WorkbookFactory) -> None:
    rec = load_recording(
        make_workbook(
            NAME, [[T0, 100.0], [T0 + timedelta(minutes=15), 99.0]], headers=("Date", "CGM ")
        )
    )
    assert tuple(rec.frame.columns) == RECORDING_FRAME_COLUMNS
    assert "cbg" in rec.absent_columns and "cgm" in rec.unitless_columns
    assert rec.frame["insulin_sc"].isna().all()


def test_loading_is_deterministic(make_workbook: WorkbookFactory) -> None:
    rows = _clean_rows(5)
    rows.append(list(rows[0]))
    p = make_workbook(NAME, rows)
    a, b = load_recording(p), load_recording(p)
    pd.testing.assert_frame_equal(a.frame, b.frame)
    assert a.issues == b.issues
