"""Held-out replay (Blueprint §15; ANALYSIS_PLAN §5.7 item 33) on REAL tuning-partition (T)
records with SYNTHETIC fold models: every patient is scored by its own fold model, the decision
log records the fold, a tampered bundle is refused, and post-confirmation E access stays closed
while no official confirmatory run exists. E is never touched."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from hyposense.api.service import HeldOut, Service, load_tuning_streams
from hyposense.evaluation.data import GATE_CODES, replay_decisions
from hyposense.features.build import build_recording
from hyposense.features.snapshot import LEVEL_INDEX
from hyposense.models.artifact import load_artifact
from hyposense.state.stream import RecordingStream
from tests.unit.artifact_helpers import synthetic_artifact
from tests.unit.state_helpers import BUILDER, CFG, ENGINE, PHARMA


@pytest.fixture(scope="module")
def streams() -> list[RecordingStream]:
    return load_tuning_streams(CFG, PHARMA)


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory, streams: list[RecordingStream]) -> Path:
    root = tmp_path_factory.mktemp("bundle") / "M1-folds-test"
    synthetic_artifact(root / "fold-0", tau_alert=0.3, tau_watch=0.1)
    synthetic_artifact(root / "fold-1", tau_alert=0.6, tau_watch=0.2)
    patients = sorted({s.identity.patient_key for s in streams})[:4]
    fold_map = {p: i % 2 for i, p in enumerate(patients)}
    (root / "fold_map.json").write_text(json.dumps(fold_map), "utf-8")
    return root


def test_each_patient_is_scored_by_its_own_fold_model(
    bundle: Path, streams: list[RecordingStream], tmp_path: Path
) -> None:
    held = HeldOut(bundle, "T-AGG-rehearsal-test", "T")
    svc = Service(bundle / "fold-0", streams, log_root=tmp_path, held_out=held)
    fold_of = json.loads((bundle / "fold_map.json").read_text("utf-8"))
    assert {s.identity.patient_key for s in svc.catalog.values()} == set(fold_of)
    assert all(c.partition == "T" for c in svc.cases())
    assert "REHEARSAL" in svc.source and "never evidence" in svc.source
    keys = sorted(svc.catalog)[:4]
    svc.select(keys)
    s = svc.session
    assert s is not None
    s.step(10**6)
    for r in s.runners:
        k = fold_of[r.patient_key]
        model = load_artifact(bundle / f"fold-{k}", CFG, PHARMA)
        assert r.pipe.model.manifest_sha256 == model.manifest_sha256
        off = build_recording(r.stream, ENGINE, BUILDER)
        _, codes, _ = replay_decisions(r.stream, ENGINE, model.rules, {})
        q = codes == GATE_CODES[None]
        p = model.calibrator.apply(
            model.booster.predict(off.X[:, LEVEL_INDEX[model.level]], num_threads=1)
        )
        live = np.array([np.nan if x.decision.p is None else x.decision.p for x in r.decisions])
        assert np.array_equal(live[q], p[q])  # bitwise: the fold model, not the display model
    assert s.log is not None
    header = json.loads((s.log.directory / "session.json").read_text("utf-8"))
    assert header["fold_of"] == {r.recording_key: fold_of[r.patient_key] for r in s.runners}
    s.log.close()


def test_tampered_fold_bundle_is_refused(
    bundle: Path, streams: list[RecordingStream], tmp_path: Path
) -> None:
    good = load_artifact(bundle / "fold-0", CFG, PHARMA).manifest["files"]
    bad = {"0": good, "1": good}  # fold-1 files do not match the record
    with pytest.raises(ValueError, match="fold-1"):
        Service(
            bundle / "fold-0",
            streams,
            log_root=tmp_path,
            held_out=HeldOut(bundle, "x", "T", bad),
        )


def test_presentation_access_refused_without_an_official_run() -> None:
    from hyposense.data.dataset import SealedPartitionError, unlock_for_presentation
    from hyposense.freeze import (
        FreezeVerificationError,
        VerifiedConfirmation,
        official_confirm_runs,
        verify_confirmation,
    )

    with pytest.raises(SealedPartitionError):
        unlock_for_presentation({"record_sha256": "forged"})
    with pytest.raises(FreezeVerificationError):
        VerifiedConfirmation(object(), "x", "y", {})
    if not official_confirm_runs():
        with pytest.raises(FreezeVerificationError):
            verify_confirmation()


def test_confirmatory_view_is_pending_without_an_official_run(
    bundle: Path, streams: list[RecordingStream], tmp_path: Path
) -> None:
    from hyposense.freeze import official_confirm_runs

    svc = Service(bundle / "fold-0", streams, log_root=tmp_path)
    if not official_confirm_runs():
        assert svc.confirmatory()["status"] == "PENDING"


def test_confirmatory_view_only_selects_frozen_numbers() -> None:
    """SYNTHETIC results document: every displayed number is copied, none is computed."""
    from hyposense.reporting.confirm_view import ANALYSES, confirmatory_view

    def iv(x: float) -> dict[str, object]:
        return {"point": x, "ci95": [x - 0.1, x + 0.1], "undefined_resamples": 0}

    ev = {
        "intervals": {"M2:sens1": iv(0.8), "M3:sens1": iv(0.9), "M2:logloss": iv(0.03)},
        "comparisons": {"preview_M3-M2:sens1": iv(0.1), "preview_M3-M2:logloss": iv(-0.001)},
        "patients": 3,
        "episodes": 9,
    }
    doc = {
        "run_id": "SYNTHETIC",
        "results_sha256": "x",
        "results": {
            "status": "REHEARSAL (development; never evidence)",
            "population": {},
            "primary": {"h1_supported": False},
            "evaluations": {"primary": ev, "R3": ev},
            "S2_matched_sensitivity_fa_delta": iv(0.0),
            "model_selection": {"selected": "M3"},
            "interpretation_table_20_4": [],
            "deployed_operating_point": {"M3": {"sensitivity": 0.5, "lead_min": {"median": 30}}},
            "demo_cases": {},
        },
    }
    v = confirmatory_view(doc)
    assert v["status"].startswith("REHEARSAL")
    rows = {r["key"]: r for r in v["analyses"]}
    assert len(rows) == len(ANALYSES)
    assert rows["R3"]["M3_sens1"] == 0.9 and rows["R3"]["delta_ci95"] == [0.0, 0.2]
    assert rows["SA8"]["available"] is False  # missing analyses are shown as missing
    assert v["ladder"]["M2"]["logloss"] == 0.03 and v["ladder"]["M0"]["sens1"] is None
    assert v["deployed_operating_point"]["M3"]["lead_median_min"] == 30
