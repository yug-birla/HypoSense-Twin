"""Verification of the immutable T/E partition against the official dataset (outcome-blind)."""

from __future__ import annotations

import json
from typing import Any

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_file
from hyposense.data.dataset import extracted_root
from hyposense.data.loader import discover_recordings
from hyposense.data.partition import PartitionIntegrityError, load_partition, partition_path
from hyposense.data.records import parse_recording_name
from hyposense.data.source import dataset_config


def verify_partition() -> dict[str, Any]:
    cfg = load_config()
    checks: dict[str, Any] = {}
    try:
        part = load_partition()
        checks["pinned_sha256"] = "PASS"
    except PartitionIntegrityError as exc:
        return {"status": "FAIL", "checks": {"pinned_sha256": f"FAIL: {exc}"}}
    prov_path = REPO_ROOT / "configs" / "partition.provenance.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8")) if prov_path.exists() else None
    checks["provenance_record"] = (
        "PASS"
        if prov
        and prov["output"]["sha256"] == sha256_file(partition_path(cfg))
        and prov["verification"]["algorithm_reproduces_source"]
        else "FAIL"
    )
    rec_dir = extracted_root() / dataset_config()["extract"]["recordings_dir"]
    data_pids = {parse_recording_name(p.name).patient_id for p in discover_recordings(rec_dir)}
    only_data, only_part = sorted(data_pids - set(part)), sorted(set(part) - data_pids)
    checks["patient_set_matches_dataset"] = (
        "PASS"
        if not only_data and not only_part
        else f"FAIL: only in data {only_data}; only in partition {only_part}"
    )
    n_t = sum(v == "T" for v in part.values())
    n_e = sum(v == "E" for v in part.values())
    exp_t = round(cfg["partition"]["frac_T"] * len(part))
    checks["counts_T_E"] = "PASS" if (n_t, n_e) == (30, 70) and abs(n_t - exp_t) <= 2 else "FAIL"
    status = "PASS" if all(v == "PASS" for v in checks.values()) else "FAIL"
    return {
        "status": status,
        "checks": checks,
        "patients": len(part),
        "T": n_t,
        "E": n_e,
        "partition_sha256": cfg["partition"]["sha256"],
        "pending_verifications": [
            "has-L1 stratum of patients 2003 and 2029 under figshare v5 (S2, label builder)",
            "treated flag vs production medication parser (S3)",
        ],
    }
