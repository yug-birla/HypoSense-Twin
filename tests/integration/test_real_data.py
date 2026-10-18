"""Integration tests on the official ShanghaiT2DM copy (figshare v5).

Marked `requires_data`; they skip cleanly when data/raw/ShanghaiT2DM is absent. Every assertion
is an AGGREGATE structural number (no patient-level values), and E data is touched only through
the approved aggregate-audit scope (P-C5).
"""

from __future__ import annotations

import pytest

from hyposense.audit.partition_check import verify_partition
from hyposense.audit.run import thresholds_from_config
from hyposense.audit.structural import measure
from hyposense.common.config import load_config
from hyposense.common.hashing import sha256_json
from hyposense.data.dataset import AccessScope, SealedPartitionError, load_dataset
from hyposense.data.partition import load_partition

pytestmark = pytest.mark.requires_data


@pytest.fixture(scope="module")
def audit_ds():  # type: ignore[no-untyped-def]
    return load_dataset(AccessScope.AGGREGATE_AUDIT)


def test_official_copy_structure(audit_ds) -> None:  # type: ignore[no-untyped-def]
    recs = audit_ds.recordings
    assert len(recs) == 109
    assert len({r.identity.patient_key for r in recs}) == 100
    assert sum(len(r.frame) for r in recs) == 112475  # published figure (rows)
    assert len(audit_ds.summary.frame) == 109
    errors = [i for r in recs for i in r.issues if i.severity == "error"]
    assert errors == []


def test_audit_is_deterministic(audit_ds) -> None:  # type: ignore[no-untyped-def]
    cfg = load_config()
    thr = thresholds_from_config(cfg)
    a = measure(audit_ds.recordings, audit_ds.summary, thr, 20)
    b = measure(audit_ds.recordings, audit_ds.summary, thr, 20)
    assert sha256_json(a) == sha256_json(b)
    assert a["dataset"]["cgm_readings"] == 112462
    assert a["blueprint_definitions"]["readings_le40"] == 329


def test_tuning_scope_never_opens_sealed_patients() -> None:
    ds = load_dataset(AccessScope.TUNING_ONLY)
    part = load_partition()
    pids = {r.identity.patient_id for r in ds.recordings}
    assert pids and all(part[p] == "T" for p in pids)
    assert len(pids) == 30
    assert all(part[k.split("_")[0]] == "T" for k in ds.summary.frame.index)


def test_all_scope_is_refused_before_freeze() -> None:
    with pytest.raises(SealedPartitionError):
        load_dataset(AccessScope.ALL_AFTER_FREEZE)


def test_partition_matches_official_patient_set() -> None:
    assert verify_partition()["status"] == "PASS"


# ------------- S2: labels and event audit on real data (aggregate assertions only) -------------
# The pinned values below are invariants of (a) the SHA-256-pinned figshare v5 copy and (b) the
# Class C label protocol locked in configs/default.yaml. They may change ONLY if the data version
# or the approved protocol changes, and then via a DECISION_LOG entry.

from hyposense.audit.events import measure_events  # noqa: E402
from hyposense.common.config import CONFIG_DIR, load_yaml  # noqa: E402
from hyposense.labels.config import LabelConfig  # noqa: E402

V5_EXPECTED = {
    "L1_episodes": 348,
    "L2_episodes": 96,
    "L1_single_reading": 430,
    "patients_with_L1": 61,
    "eligible_points_h60": 107210,
    "positive_points_h60": 1188,
    "E_L1_treated": 154,
    "E_treated_with_L1": 30,
    "episodes_with_cbg_during": 65,
    "episodes_cbg_during_lt70": 11,
    "cbg_cgm_pairs": 3269,
}


@pytest.fixture(scope="module")
def v5_events(audit_ds):  # type: ignore[no-untyped-def]
    cfg = load_config()
    return measure_events(
        audit_ds.recordings,
        LabelConfig.from_config(cfg),
        8 * 3600,
        load_partition(),
        cfg["gates"]["g3b"],
    )


def test_v5_event_counts_are_stable(v5_events) -> None:  # type: ignore[no-untyped-def]
    bd = v5_events["blueprint_definitions"]
    assert {k: bd[k] for k in V5_EXPECTED} == V5_EXPECTED
    assert v5_events["by_partition"]["E"]["L1_overlapping_sensor_floor_run"] == 0


def test_event_audit_is_deterministic(audit_ds, v5_events) -> None:  # type: ignore[no-untyped-def]
    cfg = load_config()
    again = measure_events(
        audit_ds.recordings,
        LabelConfig.from_config(cfg),
        8 * 3600,
        load_partition(),
        cfg["gates"]["g3b"],
    )
    assert sha256_json(again) == sha256_json(v5_events)


V2_ZIP = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "downloads"
    / "diabetes_datasets_v2.zip"
)


@pytest.mark.skipif(not V2_ZIP.exists(), reason="figshare v2 archive not downloaded")
def test_legacy_blueprint_event_numbers_reproduce_exactly_on_v2() -> None:
    from hyposense.audit.reconcile import equal_values
    from hyposense.audit.versions import load_version

    cfg = load_config()
    recs, _ = load_version(2, "+08:00")
    bd = measure_events(
        recs, LabelConfig.from_config(cfg), 8 * 3600, load_partition(), cfg["gates"]["g3b"]
    )["blueprint_definitions"]
    ref = load_yaml(CONFIG_DIR / "reference" / "blueprint_events.yaml")["values"]
    mismatches = {
        k: (r["value"], bd.get(k))
        for k, r in ref.items()
        if not equal_values(bd.get(k), r["value"])
    }
    assert mismatches == {}
    assert len(ref) == 48


# ------- S3: medication parsing, treated population, exposure causality (real data) -------
# Pinned values are invariants of the pinned v5 copy + versioned drug dictionary + parser. They
# change only with a dictionary/parser change, and then deliberately (DECISION_LOG).

from hyposense.audit.medication import parse_all, production_treated  # noqa: E402
from hyposense.medication.dictionary import load_dictionary  # noqa: E402
from hyposense.medication.events import ParseStatus  # noqa: E402


@pytest.fixture(scope="module")
def meds(audit_ds):  # type: ignore[no-untyped-def]
    return parse_all(
        audit_ds.recordings, load_dictionary(), load_config("pharma.yaml")["formulation_rules"]
    )


def test_every_medication_entry_is_recognised(meds) -> None:  # type: ignore[no-untyped-def]
    statuses = [en.status for m in meds.values() for en in m.entries]
    assert len(statuses) == 4653
    assert not any(s in (ParseStatus.UNPARSEABLE, ParseStatus.AMBIGUOUS) for s in statuses)


def test_production_treated_population(audit_ds, meds) -> None:  # type: ignore[no-untyped-def]
    status = production_treated(audit_ds.recordings, meds)
    treated = sorted(p for p, s in status.items() if s.treated)
    assert len(treated) == 72
    assert "2078" not in treated  # legacy rule mis-read a misplaced acarbose cell as CSII insulin
    part = load_partition()
    assert sum(part[p] == "E" for p in treated) == 50
    assert sum(part[p] == "T" for p in treated) == 22


def test_exposure_truncation_equality_on_real_tuning_records() -> None:
    import numpy as np

    from hyposense.data.loader import cgm_series
    from hyposense.medication.exposure import ExposureEngine, load_kernel_set
    from hyposense.medication.recording import parse_recording, prescribed_classes
    from hyposense.medication.timing import raw_timing

    cfg, ph = load_config(), load_config("pharma.yaml")
    ks = load_kernel_set(ph, cfg["exposure"]["timing_unknown_after_h"])
    d = load_dictionary()
    ds = load_dataset(AccessScope.TUNING_ONLY)
    rng = np.random.default_rng(2026)
    checked = 0
    for r in ds.recordings:
        m = parse_recording(r, d, ph["formulation_rules"])
        pres = prescribed_classes(
            ds.summary.frame.loc[r.identity.recording_key, "prescribed_hypoglycemic_agents"], d
        )
        ts = cgm_series(r).ts
        full = ExposureEngine(m.events, ks, pres).compute(ts)
        raw = raw_timing(m.events, ts)
        for t in rng.choice(ts, size=min(3, len(ts)), replace=False):
            past = [e for e in m.events if e.ts <= t]
            a = ExposureEngine(past, ks, pres).compute(np.array([t]))
            b = raw_timing(past, np.array([t]))
            for k, v in a.items():
                assert np.array_equal(v, full[k][ts == t], equal_nan=True), (k, r.identity)
            for k, v in b.items():
                assert np.array_equal(v, raw[k][ts == t], equal_nan=True), (k, r.identity)
            checked += 1
    assert checked > 60
