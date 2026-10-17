"""figshare version reconciliation (Gate G0 evidence).

Earlier figshare versions are used ONLY to explain differences between the blueprint's mirror
audit and the canonical copy. They are never analysis data. Each archive is MD5-verified, its
T2DM members are extracted to data/raw/reconciliation/v<N>/, and it is measured with the same
production loader and `measure()`. Per-file row and CGM counts are then compared with the
canonical version.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

from hyposense.audit.structural import measure
from hyposense.common.config import REPO_ROOT
from hyposense.data.loader import cgm_series, discover_recordings, load_recording
from hyposense.data.quality import QualityThresholds
from hyposense.data.records import Recording
from hyposense.data.source import (
    allowed_member,
    archive_path,
    archive_spec,
    dataset_config,
    detect_wrapper,
    verify_archive,
)
from hyposense.data.summary import load_summary


def extract_version(version: int) -> Path:
    cfg = dataset_config()
    spec = archive_spec(version, cfg)
    src = archive_path(spec, cfg)
    if not src.exists():
        raise FileNotFoundError(f"{src} missing; run `hyposense data fetch --version {version}`")
    verify_archive(src, spec)
    out = REPO_ROOT / "data" / "raw" / "reconciliation" / f"v{version}"
    if out.exists():
        shutil.rmtree(out)
    with zipfile.ZipFile(src) as zf:
        wrapper = detect_wrapper(zf.namelist(), cfg)
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            rel = allowed_member(info.filename, cfg, wrapper)
            if rel is None:
                continue
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as fin, target.open("wb") as fout:
                shutil.copyfileobj(fin, fout)
    return out


def load_version(version: int, utc_offset: str) -> tuple[list[Recording], Any]:
    cfg = dataset_config()
    root = extract_version(version)
    recs = [
        load_recording(p, utc_offset=utc_offset)
        for p in discover_recordings(root / cfg["extract"]["recordings_dir"])
    ]
    summary_path = root / cfg["extract"]["summary_file"]
    summary = load_summary(summary_path) if summary_path.exists() else None
    return recs, summary


def per_file_counts(recs: list[Recording]) -> dict[str, dict[str, int]]:
    return {
        r.identity.recording_key: {"rows": len(r.frame), "cgm": len(cgm_series(r).ts)} for r in recs
    }


def reconcile_versions(
    canonical: list[Recording],
    versions: tuple[int, ...],
    utc_offset: str,
    thresholds: QualityThresholds,
    max_interval_min: float,
) -> dict[str, Any]:
    base = per_file_counts(canonical)
    out: dict[str, Any] = {}
    for v in versions:
        recs, summary = load_version(v, utc_offset)
        counts = per_file_counts(recs)
        diffs = {
            k: {
                "rows": base[k]["rows"] - counts[k]["rows"],
                "cgm": base[k]["cgm"] - counts[k]["cgm"],
            }
            for k in sorted(set(base) & set(counts))
            if base[k] != counts[k]
        }
        m = measure(recs, summary, thresholds, max_interval_min)
        out[f"v{v}"] = {
            "recordings": len(recs),
            "only_in_canonical": sorted(set(base) - set(counts)),
            "only_in_this_version": sorted(set(counts) - set(base)),
            "files_differing_from_canonical": diffs,
            "total_rows": m["dataset"]["rows"],
            "total_cgm_readings": m["dataset"]["cgm_readings"],
            "blueprint_definitions": m["blueprint_definitions"],
        }
    return out
