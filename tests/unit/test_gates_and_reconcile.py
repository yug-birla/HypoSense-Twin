"""G0/G1 logic and blueprint-reconciliation rules (pure functions, SYNTHETIC inputs)."""

from __future__ import annotations

from typing import Any

import pytest

from hyposense.audit.gates import evaluate_g0, evaluate_g1
from hyposense.audit.reconcile import EXPECTED, MATCH, UNEXPLAINED, reconcile

CRIT = {"min_cgm_parse_rate": 0.99, "min_interval_le_rate": 0.99, "max_interval_min": 20}
PINNED = {"file_id": 42966622, "md5": "m", "sha256": "s"}
RECORD = {
    "source": "figshare",
    "version": 5,
    "file_id": 42966622,
    "retrieved_utc": "t",
    "version_doi": "d",
    "md5": "m",
    "sha256": "s",
    "url": "u",
    "licence": "CC BY 4.0",
}
EXPECT = {"expected_recording_files": 109, "expected_patients": 100}


def _g1(parse: float, interval: float) -> dict[str, Any]:
    return evaluate_g1(
        measured={
            "cgm_parse_rate": parse,
            "cgm_parsed": 1,
            "cgm_cells_nonempty": 1,
            "interval_le_max_rate": interval,
            "cgm_intervals": 1,
            "timestamp_parse_rate": 1.0,
            "duplicates": {},
            "invalid_cgm": {},
            "issues": {},
        },
        criteria=CRIT,
    )


@pytest.mark.parametrize(
    ("parse", "interval", "status"),
    [
        (1.0, 1.0, "PASS"),
        (0.99, 0.99, "PASS"),
        (0.9899, 1.0, "FAIL"),
        (1.0, 0.98999, "FAIL"),
    ],
)
def test_g1_thresholds_are_inclusive_and_strict(parse: float, interval: float, status: str) -> None:
    assert _g1(parse, interval)["status"] == status


def _g0(**over: Any) -> dict[str, Any]:
    measured = {
        "recording_files": 109,
        "recordings": 109,
        "patients": 100,
        "rows": 112475,
        "cgm_readings": 112462,
        "rows_without_cgm_by_recording": {"2029_0_20210526": 13},
        "summary_present": True,
        "manifest_files_sha256": "x",
    }
    measured.update(over.pop("measured", {}))
    kw: dict[str, Any] = {
        "archive_record": RECORD,
        "pinned": PINNED,
        "canonical_version": 5,
        "archive_verified": True,
        "manifest_verified": True,
        "measured": measured,
        "expected": EXPECT,
        "published_cgm": 112475,
        "noted_recordings": ["2003_0_20210615", "2029_0_20210526"],
        "reconciliation": [{"metric": "m", "status": MATCH}],
    }
    kw.update(over)
    return evaluate_g0(**kw)


def test_g0_pass_with_explained_count() -> None:
    g = _g0()
    assert g["status"] == "PASS"
    assert (
        "Difference explained"
        in next(c for c in g["checks"] if c["id"].startswith("G0.7"))["summary"]
    )


def test_g0_pass_with_exact_count() -> None:
    assert (
        _g0(measured={"cgm_readings": 112475, "rows_without_cgm_by_recording": {}})["status"]
        == "PASS"
    )


def test_g0_partial_when_missing_cgm_rows_are_undocumented() -> None:
    g = _g0(measured={"rows_without_cgm_by_recording": {"2050_0_20210510": 13}})
    assert g["status"] == "PARTIAL"


def test_g0_partial_when_reconciliation_unexplained_or_skipped() -> None:
    assert _g0(reconciliation=[{"metric": "m", "status": UNEXPLAINED}])["status"] == "PARTIAL"
    assert _g0(reconciliation=None)["status"] == "PARTIAL"


@pytest.mark.parametrize(
    "over",
    [
        {"archive_verified": False},
        {"manifest_verified": False},
        {"measured": {"recording_files": 108}},
        {"measured": {"patients": 99}},
        {"archive_record": {**RECORD, "version": 2}},
    ],
)
def test_g0_fails_on_integrity_problems(over: dict[str, Any]) -> None:
    assert _g0(**over)["status"] == "FAIL"


REF = {"values": {"a": {"value": 10, "section": "s"}, "h": {"value": {"x": 1}, "section": "s"}}}


def _version(a: Any, files: list[str]) -> dict[str, Any]:
    return {
        "blueprint_definitions": {"a": a, "h": {"x": 1}},
        "files_differing_from_canonical": {f: {} for f in files},
        "only_in_canonical": [],
        "only_in_this_version": [],
    }


def test_reconcile_match_expected_unexplained() -> None:
    noted = ["n1"]
    rows = reconcile(REF, {"a": 10, "h": {"x": 1, "y": 0}}, {}, noted)
    assert [r["status"] for r in rows] == [MATCH, MATCH]  # missing key == 0
    rows = reconcile(REF, {"a": 11, "h": {"x": 1}}, {"v2": _version(10, ["n1"])}, noted)
    assert rows[0]["status"] == EXPECTED
    rows = reconcile(REF, {"a": 11, "h": {"x": 1}}, {"v2": _version(10, ["n1", "other"])}, noted)
    assert rows[0]["status"] == UNEXPLAINED  # undocumented file changed
    rows = reconcile(REF, {"a": 11, "h": {"x": 1}}, {"v2": _version(12, ["n1"])}, noted)
    assert rows[0]["status"] == UNEXPLAINED  # no version reproduces
