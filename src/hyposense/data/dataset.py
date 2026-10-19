"""Scoped, manifest-verified access to the whole dataset (sealed-partition safeguard).

Every caller states why it needs the data:
- TUNING_ONLY: modelling and design work before freeze. Only patients in partition T are read.
  E files are never opened.
- AGGREGATE_AUDIT: outcome-blind integrity checks that emit aggregate reports only (approved
  P-C5). Reserved for `hyposense.audit`; a static test forbids its use elsewhere.
- ALL_AFTER_FREEZE: the confirmatory run (S9). It refuses unless `unlock_sealed_partition` was
  called with a `VerifiedFreeze` produced by `hyposense.freeze.verify_freeze_record` (hashes of
  code tree, configs, data, partition, analysis plan, locks and the candidate artefact all match
  the freeze record). Nothing else can unlock E.
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


_UNLOCKED: dict[str, str] = {}


def unlock_sealed_partition(verified: object) -> str:
    """Unlock E for this process. Accepts ONLY a VerifiedFreeze (re-verified here)."""
    from hyposense.freeze import FREEZE_JSON, VerifiedFreeze, verify_freeze_record

    if not isinstance(verified, VerifiedFreeze):
        raise SealedPartitionError("E can only be unlocked by a verified freeze record")
    again = verify_freeze_record(FREEZE_JSON)
    if again.record_sha256 != verified.record_sha256:
        raise SealedPartitionError("freeze record changed since verification")
    _UNLOCKED["record_sha256"] = again.record_sha256
    return again.record_sha256


def unlock_for_presentation(verified: object) -> str:
    """READ-ONLY presentation access to E after the official confirmatory run (ANALYSIS_PLAN
    §5.7 item 33: replay of held-out patients with their own fold models, reports). Accepts ONLY
    a VerifiedConfirmation (re-verified here). Modelling stays impossible: the confirmatory
    runner refuses once an official run exists."""
    from hyposense.freeze import FREEZE_JSON, VerifiedConfirmation, verify_confirmation

    if not isinstance(verified, VerifiedConfirmation):
        raise SealedPartitionError("presentation access needs a verified confirmation")
    again = verify_confirmation(FREEZE_JSON)
    if again.record_sha256 != verified.record_sha256:
        raise SealedPartitionError("freeze record changed since verification")
    _UNLOCKED["record_sha256"] = again.record_sha256
    _UNLOCKED["purpose"] = f"presentation after {again.confirm_run}"
    return again.record_sha256


def sealed_unlocked() -> bool:
    return "record_sha256" in _UNLOCKED


@lru_cache(maxsize=1)
def _sealed_patient_ids() -> frozenset[str]:
    return frozenset(pid for pid, part in load_partition().items() if part == "E")


def assert_not_sealed(patient_id: str) -> None:
    """Defence in depth for every real-data feature path (S4 independent review): before
    freeze, refuse any record of a sealed-evaluation (E) patient, whatever the caller's
    scope. The confirmatory stage will authorise E through the freeze record (ALL_AFTER_FREEZE),
    which does not exist yet."""
    if patient_id in _sealed_patient_ids() and not sealed_unlocked():
        raise SealedPartitionError(
            f"patient {patient_id} belongs to the sealed evaluation partition (no freeze record)"
        )


def partition_labels(ds: Dataset) -> dict[str, str]:
    """patient_key -> 'T' | 'E' for the patients of a loaded dataset only. The scope check
    already ran when `ds` was loaded, so this never reveals labels of patients outside it."""
    part = load_partition()
    keys = {r.identity.patient_key: r.identity.patient_id for r in ds.recordings}
    return {k: part[pid] for k, pid in sorted(keys.items())}


def extracted_root() -> Path:
    return Path(REPO_ROOT / dataset_config()["paths"]["extracted"])


def load_dataset(scope: AccessScope) -> Dataset:
    if scope is AccessScope.ALL_AFTER_FREEZE and not sealed_unlocked():
        raise SealedPartitionError(
            "E is sealed: ALL_AFTER_FREEZE requires unlock_sealed_partition(verify_freeze_record())"
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


@dataclass(frozen=True)
class LegacyTuning:
    """A pre-2023 figshare version's TUNING recordings (reconciliation copy), for reproducing
    blueprint numbers (S5 Table A.2). E files are never opened."""

    version: int
    root: Path
    files_sha256: dict[str, str]
    recordings: tuple[Recording, ...]
    summary: SummaryTable | None


def load_legacy_tuning(version: int) -> LegacyTuning:
    """TUNING-only recordings of an extracted reconciliation version
    (data/raw/reconciliation/v<N>/, created and MD5-checked by `hyposense audit events`)."""
    from hyposense.common.hashing import sha256_file

    dcfg = dataset_config()
    cfg = load_config()
    root = REPO_ROOT / "data" / "raw" / "reconciliation" / f"v{version}"
    rec_dir = root / dcfg["extract"]["recordings_dir"]
    if not rec_dir.is_dir():
        raise FileNotFoundError(
            f"{rec_dir} missing: run `hyposense audit events` to extract v{version}"
        )
    partition = load_partition()
    paths = [
        p
        for p in discover_recordings(rec_dir)
        if partition.get(parse_recording_name(p.name).patient_id) == "T"
    ]
    offset = str(cfg["time"]["assumed_utc_offset"])
    recordings = tuple(load_recording(p, utc_offset=offset) for p in paths)
    hashes = {p.name: sha256_file(p) for p in paths}
    summary_path = root / dcfg["extract"]["summary_file"]
    summary = None
    if summary_path.exists():
        full = load_summary(summary_path)
        keys = {r.identity.recording_key for r in recordings}
        summary = SummaryTable(full.frame.loc[full.frame.index.isin(keys)], full.raw_headers)
    return LegacyTuning(version, root, hashes, recordings, summary)
