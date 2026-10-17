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
