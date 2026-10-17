"""Recording identity, deterministic discovery and column-schema tests (SYNTHETIC fixtures)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from hyposense.data.columns import HEADER_VARIANTS, SchemaError, map_columns, normalise_header
from hyposense.data.loader import discover_recordings
from hyposense.data.records import InvalidRecordingNameError, parse_recording_name
from tests.conftest import STANDARD_HEADERS, WorkbookFactory, row


@pytest.mark.parametrize(
    ("name", "pid", "period", "start", "fmt"),
    [
        ("2001_0_20201102.xlsx", "2001", 0, date(2020, 11, 2), "xlsx"),
        ("2069_2_20210825.xls", "2069", 2, date(2021, 8, 25), "xls"),
    ],
)
def test_parse_recording_name(name: str, pid: str, period: int, start: date, fmt: str) -> None:
    ident = parse_recording_name(name)
    assert ident.patient_id == pid
    assert ident.patient_key == f"shanghai_t2dm:{pid}"
    assert ident.period == period and ident.nominal_start == start
    assert ident.file_format == fmt
    assert ident.recording_key == name.rsplit(".", 1)[0]


@pytest.mark.parametrize(
    "bad",
    [
        "2001_0_20201102.csv",
        "2001_20201102.xlsx",
        "x001_0_20201102.xlsx",
        "2001_0_20211301.xlsx",
        "._2001_0_20201102.xlsx",
        "2001_0_20201102.xlsx.bak",
    ],
)
def test_invalid_recording_names_raise(bad: str) -> None:
    with pytest.raises(InvalidRecordingNameError):
        parse_recording_name(bad)


def test_multiple_recordings_share_patient_key() -> None:
    a = parse_recording_name("2069_0_20210621.xls")
    b = parse_recording_name("2069_1_20210705.xls")
    assert a.patient_key == b.patient_key and a.recording_key != b.recording_key


def test_discovery_is_sorted_and_strict(tmp_path: Path, make_workbook: WorkbookFactory) -> None:
    d = tmp_path / "recs"
    for n in ("2003_0_20210615.xlsx", "2001_1_20201117.xlsx", "2001_0_20201102.xlsx"):
        make_workbook(n, [row(datetime(2021, 1, 1), 100.0)], directory=d)
    assert [p.name for p in discover_recordings(d)] == [
        "2001_0_20201102.xlsx",
        "2001_1_20201117.xlsx",
        "2003_0_20210615.xlsx",
    ]
    (d / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(InvalidRecordingNameError):
        discover_recordings(d)


def test_discovery_rejects_same_key_in_two_formats(
    tmp_path: Path, make_workbook: WorkbookFactory
) -> None:
    d = tmp_path / "recs"
    make_workbook("2001_0_20201102.xlsx", [row(datetime(2021, 1, 1), 100.0)], directory=d)
    (d / "2001_0_20201102.xls").write_bytes(b"")
    with pytest.raises(InvalidRecordingNameError):
        discover_recordings(d)


def test_all_observed_header_variants_map() -> None:
    observed = [
        STANDARD_HEADERS,
        (
            "Date",
            "CGM ",
            "CBG ",
            "Blood Ketone ",
            "Dietary intake",
            "饮食",
            "Insulin dose - s.c.",
            "Non-insulin hypoglycemic agents",
            "CSII - bolus insulin ",
            "CSII - basal insulin ",
            "Insulin dose - i.v.",
        ),
        (
            "Date",
            "CGM (mg / dl)",
            "CBG (mg / dl)",
            "Blood Ketone (mmol / L)",
            "Dietary intake",
            "进食量",
            "Insulin dose - s.c.",
            "Non-insulin hypoglycemic agents",
            "CSII - bolus insulin (Novolin R, IU)",
            "CSII - basal insulin (Novolin R, IU / H)",
            "Insulin dose - i.v.",
        ),
        (
            "Date",
            "CGM (mg / dl)",
            "CBG (mg / dl)",
            "Blood Ketone (mmol / L)",
            "Dietary intake",
            "饮食",
            "Insulin dose - s.c.",
            "Non-insulin hypoglycemic agents",
            "CSII - bolus insulin (Novolin R  IU)",
            "CSII - basal insulin (Novolin R  IU / H)",
            "Insulin dose - i.v.",
        ),
        (
            "Date",
            "CGM (mg / dl)",
            "CBG (mg / dl)",
            "Blood Ketone (mmol / L)",
            "Dietary intake",
            "饮食",
            "Insulin dose - s.c.",
            "Non-insulin hypoglycemic agents",
            "CSII - bolus insulin (Novolin R, IU)",
            "胰岛素泵基础量 (Novolin R, IU / H)",
            "Insulin dose - i.v.",
        ),
    ]
    for headers in observed:
        m = map_columns(headers)
        assert m.absent == ()
        assert len(set(m.to_canonical.values())) == 11


def test_unitless_headers_are_reported() -> None:
    m = map_columns(("Date", "CGM ", "CBG "))
    assert set(m.unitless) == {"cgm", "cbg"}


def test_schema_errors() -> None:
    with pytest.raises(SchemaError):
        map_columns(("Date", "CGM (mg / dl)", "CGM "))  # two map to cgm
    with pytest.raises(SchemaError):
        map_columns(("Date", "CBG (mg / dl)"))  # required cgm missing
    with pytest.raises(SchemaError):
        map_columns(("Date", "CGM", "Glucose (mmol/L)"))  # unknown header


def test_header_normalisation() -> None:
    assert (
        normalise_header("  CSII - bolus insulin (Novolin R  IU) ")
        == "CSII - bolus insulin (Novolin R IU)"
    )
    assert all(normalise_header(k) == k for k in HEADER_VARIANTS)
