"""Scoped, manifest-verified access to the whole dataset (sealed-partition safeguard).

Every caller states why it needs the data:
- TUNING_ONLY: modelling and design work before freeze. Only patients in partition T are read.
  E files are never opened.
- AGGREGATE_AUDIT: outcome-blind integrity checks that emit aggregate reports only (approved
  P-C5). Reserved for `hyposense.audit`; a static test forbids its use elsewhere.
- ALL_AFTER_FREEZE: the confirmatory run. It refuses until the freeze machinery exists and a
  valid freeze record matches (Freeze stage).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.data.loader import discover_recordings, load_recording
from hyposense.data.manifest import read_manifest, verify_manifest
from hyposense.data.partition import load_partition
from hyposense.data.records import Recording, parse_recording_name
from hyposense.data.source import dataset_config
from hyposense.data.summary import SummaryTable, load_summary


class AccessScope(StrEnum):
    TUNING_ONLY = "tuning_only"
    AGGREGATE_AUDIT = "aggregate_audit"
    ALL_AFTER_FREEZE = "all_after_freeze"


class SealedPartitionError(PermissionError):
    """Access to sealed-evaluation (E) data was requested without authorisation."""


@dataclass(frozen=True)
class Dataset:
    scope: AccessScope
    root: Path
    manifest_files_sha256: str
    recordings: tuple[Recording, ...]
    summary: SummaryTable


@lru_cache(maxsize=1)
def _sealed_patient_ids() -> frozenset[str]:
    return frozenset(pid for pid, part in load_partition().items() if part == "E")


def assert_not_sealed(patient_id: str) -> None:
    """Defence in depth for every real-data feature path (S4 independent review): before
    freeze, refuse any record of a sealed-evaluation (E) patient, whatever the caller's
    scope. The confirmatory stage will authorise E through the freeze record (ALL_AFTER_FREEZE),
    which does not exist yet."""
    if patient_id in _sealed_patient_ids():
        raise SealedPartitionError(
            f"patient {patient_id} belongs to the sealed evaluation partition (no freeze record)"
        )


def extracted_root() -> Path:
    return Path(REPO_ROOT / dataset_config()["paths"]["extracted"])


def load_dataset(scope: AccessScope) -> Dataset:
    if scope is AccessScope.ALL_AFTER_FREEZE:
        raise SealedPartitionError(
            "E is sealed: no freeze record exists (freeze machinery is implemented at the "
            "Freeze stage)"
        )
    dcfg = dataset_config()
    cfg = load_config()
    root = extracted_root()
    manifest = read_manifest(REPO_ROOT / dcfg["paths"]["manifest_json"])
    verified = verify_manifest(root, manifest)  # refuses mismatched data
    paths = discover_recordings(root / dcfg["extract"]["recordings_dir"])
    if scope is AccessScope.TUNING_ONLY:
        partition = load_partition()
        paths = [p for p in paths if partition.get(parse_recording_name(p.name).patient_id) == "T"]
    offset = str(cfg["time"]["assumed_utc_offset"])
    recordings = tuple(load_recording(p, utc_offset=offset) for p in paths)
    summary = load_summary(root / dcfg["extract"]["summary_file"])
    keys = {r.identity.recording_key for r in recordings}
    if scope is AccessScope.TUNING_ONLY:
        summary = SummaryTable(
            summary.frame.loc[summary.frame.index.isin(keys)], summary.raw_headers
        )
    return Dataset(scope, root, str(verified["files_sha256"]), recordings, summary)
