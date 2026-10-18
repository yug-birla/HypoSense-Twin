"""G3 gate logic and the medication audit on SYNTHETIC recordings."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from hyposense.audit.gates import evaluate_g3
from hyposense.audit.medication import inventory, measure_medication, parse_all
from hyposense.common.config import load_config
from hyposense.data.loader import load_recording
from hyposense.data.summary import SummaryTable
from hyposense.medication.dictionary import load_dictionary
from hyposense.medication.exposure import load_kernel_set
from tests.conftest import WorkbookFactory, row

CRIT = {
    "min_parse_rate": 0.90,
    "min_day_coverage": 0.80,
    "max_timing_resolution_min": 15,
    "min_treated_E_patients_with_variation": 20,
}


def _g3(**over: object) -> str:
    m = {
        "parse_rate": 0.95,
        "day_coverage_median": 0.9,
        "timing_resolution_min": 15,
        "timing_on_grid_rate": 0.999,
        "treated_E_patients_with_exposure_variation": 25,
    }
    m.update(over)
    return str(evaluate_g3(measured=m, criteria=CRIT)["status"])


@pytest.mark.parametrize(
    ("over", "status"),
    [
        ({}, "PASS"),
        ({"parse_rate": 0.90}, "PASS"),
        ({"parse_rate": 0.8999}, "FAIL"),
        ({"day_coverage_median": 0.79}, "FAIL"),
        ({"timing_resolution_min": 30}, "FAIL"),
        ({"timing_on_grid_rate": 0.95}, "FAIL"),
        ({"treated_E_patients_with_exposure_variation": 19}, "FAIL"),
    ],
)
def test_g3_thresholds(over: dict[str, object], status: str) -> None:
    assert _g3(**over) == status


T0 = datetime(2021, 3, 1, 6, 0)


def test_measure_medication_on_synthetic_recordings(make_workbook: WorkbookFactory) -> None:
    d = load_dictionary()
    ph = load_config("pharma.yaml")
    ks = load_kernel_set(ph, 36)
    a_rows = [
        row(
            T0 + timedelta(minutes=15 * k),
            120.0,
            insulin_sc="insulin aspart 70/30, 14 IU" if k % 48 == 0 else None,
            oral="metformin 0.5 g" if k % 48 == 4 else None,
        )
        for k in range(200)
    ]
    b_rows = [
        row(
            T0 + timedelta(minutes=15 * k),
            120.0,
            oral="acarbose 50 mg" if k % 48 == 4 else None,
            csii_bolus="acarbose 50 mg" if k == 10 else None,
        )
        for k in range(200)
    ]
    recs = [
        load_recording(make_workbook("2001_0_20210301.xlsx", a_rows)),
        load_recording(make_workbook("2002_0_20210301.xlsx", b_rows)),
    ]
    summary = SummaryTable(
        pd.DataFrame(
            {"prescribed_hypoglycemic_agents": ["insulin aspart 70/30", "acarbose"]},
            index=["2001_0_20210301", "2002_0_20210301"],
        ),
        (),
    )
    meds = parse_all(recs, d, ph["formulation_rules"])
    part = {"2001": "T", "2002": "E"}
    m = measure_medication(recs, summary, meds, part, d, ks, {"2001": True, "2002": True})
    assert m["entries"]["unrecognised_or_ambiguous"] == 0
    assert m["rates"]["insulin_sc_entries_parsed_to_drug_and_dose"] == [5, 5]
    assert m["treated"]["by_partition"]["ALL"]["treated"] == 1
    assert m["treated"]["differs_from_legacy"] == [
        {"patient_id": "2002", "partition": "E", "legacy": True, "production": False}
    ]
    assert m["g3_inputs"]["parse_rate"] == 1.0
    assert m["day_coverage_treated_recordings"]["target_admin_q1_median"][1] == 1.0
    inv = inventory(recs, meds, part)
    misplaced = next(i for i in inv if i["column"] == "csii_bolus")
    assert misplaced["components"][0]["canonical"] == "acarbose"
    assert "MISPLACED_COLUMN" in misplaced["components"][0]["flags"]
    assert {i["n_T"] + i["n_E"] for i in inv} <= {1, 4, 5}
