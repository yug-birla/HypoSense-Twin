"""Structural audit: determinism and the aggregate-only safeguard (SYNTHETIC recordings)."""

from __future__ import annotations

from datetime import datetime, timedelta

from hyposense.audit.structural import PER_RECORDING_FIELDS, measure
from hyposense.common.hashing import sha256_json
from hyposense.data.loader import load_recording
from hyposense.data.quality import QualityThresholds
from tests.conftest import WorkbookFactory, row

T0 = datetime(2021, 1, 1, 8, 0)


def _recs(make_workbook: WorkbookFactory) -> list:  # type: ignore[type-arg]
    a = [
        row(
            T0 + timedelta(minutes=15 * k),
            120.6 - 1.8 * k,
            insulin_sc="Novolin R 4 IU" if k == 1 else None,
            oral="metformin 500 mg, acarbose 50 mg" if k == 2 else None,
            diet_en="Rice 100 g" if k == 3 else ("data not available" if k == 4 else None),
        )
        for k in range(10)
    ]
    b = [row(T0 + timedelta(minutes=15 * k + (40 if k > 5 else 0)), 90.0) for k in range(8)]
    return [
        load_recording(make_workbook("2001_0_20210101.xlsx", a)),
        load_recording(make_workbook("2001_1_20210101.xlsx", b)),
        load_recording(make_workbook("2002_0_20210101.xlsx", a)),
    ]


def test_measure_is_deterministic(make_workbook: WorkbookFactory) -> None:
    recs = _recs(make_workbook)
    thr = QualityThresholds()
    assert sha256_json(measure(recs, None, thr, 20)) == sha256_json(
        measure(list(reversed(recs)), None, thr, 20)
    )


def test_measure_counts(make_workbook: WorkbookFactory) -> None:
    m = measure(_recs(make_workbook), None, QualityThresholds(), 20)
    d = m["dataset"]
    assert (d["recordings"], d["patients"], d["cgm_readings"]) == (3, 2, 28)
    assert d["recordings_per_patient"] == {"1": 1, "2": 1}
    # recordings a (x2): 9 intervals of 15 min; b: 6 of 15 min + one of 55 min (k=5 -> 6)
    assert m["timestamps"]["interval_histogram_min"] == {"b:14-16": 24, "e:(30,60]": 1}
    assert (m["timestamps"]["gaps_gt_30_min"], m["timestamps"]["gaps_gt_60_min"]) == (1, 0)
    assert m["timestamps"]["interval_le_max_rate"] == round(24 / 25, 6)
    assert m["medication"]["columns"]["oral_agents"]["entries"] == 2
    assert m["medication"]["vocabulary"]["oral_agents"] == {"acarbose": 2, "metformin": 2}
    assert m["meals"]["diet_en_not_available"] == 2
    assert m["blueprint_definitions"]["diet_entries"] == 4


def test_per_recording_output_is_structural_only(make_workbook: WorkbookFactory) -> None:
    m = measure(_recs(make_workbook), None, QualityThresholds(), 20)
    for r in m["per_recording"]:
        assert tuple(r) == PER_RECORDING_FIELDS
    forbidden = {"cgm", "min_cgm", "n_L1", "episodes", "nadir", "label", "pct_below70"}
    assert not forbidden & set(PER_RECORDING_FIELDS)
