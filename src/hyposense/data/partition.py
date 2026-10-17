"""Patient-level tuning (T) / sealed evaluation (E) partition.

The official project split is `configs/partition.csv` (patient_id, partition). Its SHA-256 is
pinned in configs/default.yaml `partition.sha256` and checked on every load, so the split cannot
be edited or regenerated silently (DECISION_LOG ADR-016).

Provenance: imported verbatim from the blueprint author's audit (`audit2.py`), which split
patients within strata (treated x has-L1) with numpy `default_rng(2026)` and frac_T = 0.30.
`reproduce_audit2_split` re-implements that algorithm exactly, so the import can be verified.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

import numpy as np

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_file

PARTITIONS = ("T", "E")


class PartitionIntegrityError(RuntimeError):
    """The partition file does not match its pinned hash or is malformed."""


def partition_path(cfg: Mapping[str, object] | None = None) -> Path:
    cfg = cfg or load_config()
    part = cfg["partition"]
    assert isinstance(part, dict)
    return REPO_ROOT / str(part["file"])


def load_partition(path: Path | None = None, expected_sha256: str | None = None) -> dict[str, str]:
    """patient_id -> 'T' | 'E', after verifying the pinned SHA-256."""
    cfg = load_config()
    path = path or partition_path(cfg)
    expected = expected_sha256 if expected_sha256 is not None else cfg["partition"].get("sha256")
    if not expected:
        raise PartitionIntegrityError("no pinned partition sha256 in configs/default.yaml")
    actual = sha256_file(path)
    if actual != expected:
        raise PartitionIntegrityError(f"{path}: sha256 {actual} != pinned {expected}")
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or set(rows[0]) != {"patient_id", "partition"}:
        raise PartitionIntegrityError(f"{path}: expected columns patient_id, partition")
    mapping: dict[str, str] = {}
    for r in rows:
        pid, part = r["patient_id"].strip(), r["partition"].strip()
        if part not in PARTITIONS or pid in mapping:
            raise PartitionIntegrityError(f"{path}: bad row {r}")
        mapping[pid] = part
    return mapping


def reproduce_audit2_split(strata: Mapping[str, int], seed: int, frac_t: float) -> dict[str, str]:
    """Exact re-implementation of the blueprint audit's split (audit2.py, lines 14-20).

    Patients are sorted by string id within ascending stratum. One shared Generator shuffles each
    stratum's list in turn, and the first int(round(frac_t * n)) go to T. Python's round() (banker's
    rounding) is used deliberately, to match the original.
    """
    rng = np.random.default_rng(seed)
    tune: set[str] = set()
    for s in sorted(set(strata.values())):
        ids = sorted(pid for pid, st in strata.items() if st == s)
        rng.shuffle(ids)
        k = round(frac_t * len(ids))  # Python round(): banker's rounding
        tune.update(ids[:k])
    return {pid: ("T" if pid in tune else "E") for pid in sorted(strata)}
