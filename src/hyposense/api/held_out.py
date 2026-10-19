"""Held-out replay setup (Blueprint §15; ANALYSIS_PLAN §5.7 item 33).

Official: only after the confirmatory run. `freeze.verify_confirmation` must pass (the freeze
record is intact, exactly one official run is bound to it, data and partition are unchanged).
Then E is opened READ-ONLY for presentation, and every evaluation patient is replayed with the
fold model that never saw that patient. Nothing here fits, tunes or selects anything.

Rehearsal: the same on T from a T-AGG-rehearsal-* run (development; never evidence). It exercises
the identical code path before freeze.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hyposense.api.service import HeldOut
from hyposense.common.config import REPO_ROOT, load_config
from hyposense.state.stream import RecordingStream

RUNS = REPO_ROOT / "experiments" / "runs"


def _bundle(results: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The selected level's fold bundle. If M0 was selected (no learned final model), the M3
    bundle is shown and labelled as not the selected model by the caller."""
    fm = results["final_model"]
    bundles = fm.get("fold_bundles") or {}
    level = fm["selected"] if fm["selected"] in bundles else "M3"
    if level not in bundles:
        raise ValueError("the confirmatory run has no fold bundle to replay")
    return level, bundles[level]


def _streams(ds: Any, patients: set[str]) -> list[RecordingStream]:
    """Live-path stream construction (same modules as `api.service.load_tuning_streams`)."""
    from hyposense.medication.dictionary import load_dictionary
    from hyposense.state.stream import order_recordings, recording_stream

    cfg, pharma, d = load_config(), load_config("pharma.yaml"), load_dictionary()
    plaus = {k: (float(v[0]), float(v[1])) for k, v in cfg["features"]["static_plausible"].items()}
    frame = ds.summary.frame
    by_patient: dict[str, list[RecordingStream]] = {}
    for rec in ds.recordings:
        if rec.identity.patient_key not in patients:
            continue
        key = rec.identity.recording_key
        row = {str(c): v for c, v in frame.loc[key].items()} if key in frame.index else None
        s = recording_stream(rec, d, pharma["formulation_rules"], row, plaus)
        by_patient.setdefault(s.identity.patient_key, []).append(s)
    return [s for p in sorted(by_patient) for s in order_recordings(by_patient[p])]


def held_out_setup(
    rehearsal_run: str | None = None,
) -> tuple[Path, list[RecordingStream], HeldOut, str]:
    """(final-model directory, streams of the held-out patients, HeldOut, replayed level)."""
    from hyposense.data.dataset import AccessScope, load_dataset

    if rehearsal_run is None:
        from hyposense.data.dataset import unlock_for_presentation
        from hyposense.freeze import verify_confirmation

        verified = verify_confirmation()  # BEFORE any E access
        unlock_for_presentation(verified)
        results, run_id, partition = verified.results, verified.confirm_run, "E"
        ds = load_dataset(AccessScope.ALL_AFTER_FREEZE)
    else:
        doc = json.loads((RUNS / rehearsal_run / "results.json").read_text("utf-8"))
        if not str(doc["status"]).startswith("REHEARSAL"):
            raise ValueError(f"{rehearsal_run} is not a rehearsal run")
        results, run_id, partition = doc["results"], rehearsal_run, "T"
        ds = load_dataset(AccessScope.TUNING_ONLY)
    level, b = _bundle(results)
    bundle_dir = REPO_ROOT / b["directory"]
    fold_of = json.loads((bundle_dir / "fold_map.json").read_text("utf-8"))
    final = results["final_model"].get("final")
    model_dir = REPO_ROOT / (final["directory"] if final else f"{b['directory']}/fold-0")
    held = HeldOut(
        bundle_dir, run_id, partition, b["fold_files"], results["final_model"]["selected"]
    )
    return model_dir, _streams(ds, set(fold_of)), held, level
