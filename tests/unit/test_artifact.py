"""S7 strict artefact loader: every mismatch refuses inference. SYNTHETIC model and data."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from hyposense.common.hashing import sha256_bytes
from hyposense.features.snapshot import FeatureSnapshot
from hyposense.features.spec import FeatureSpecMismatch, level_names
from hyposense.models.artifact import (
    ArtifactHashMismatch,
    ArtifactIncompatible,
    ArtifactMissing,
    load_artifact,
)
from tests.unit.artifact_helpers import synthetic_artifact
from tests.unit.state_helpers import BUILDER, CFG, PHARMA, cgm, run, steady


@pytest.fixture(scope="module")
def bundle(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return synthetic_artifact(tmp_path_factory.mktemp("art") / "M1-dev")


def _copy(src: Path, tmp: Path) -> Path:
    dst = tmp / "copy"
    dst.mkdir()
    for f in src.iterdir():
        (dst / f.name).write_bytes(f.read_bytes())
    return dst


def _manifest(d: Path) -> dict:  # type: ignore[type-arg]
    return json.loads((d / "manifest.json").read_text("utf-8"))


def _write_manifest(d: Path, m: dict) -> None:  # type: ignore[type-arg]
    (d / "manifest.json").write_text(json.dumps(m), "utf-8")


def test_loads_and_predicts(bundle: Path) -> None:
    m = load_artifact(bundle, CFG, PHARMA)
    assert m.status == "DEVELOPMENT" and m.level == "M1" and m.features == level_names("M1")
    s = run(cgm(steady(0, 180)))[-1]
    snap = BUILDER.snapshot(s, "M1")
    raw, p = m.predict(snap)
    assert 0.0 <= p <= 1.0 and np.isfinite(raw)
    assert m.predict(snap) == (raw, p)  # deterministic
    with pytest.raises(FeatureSpecMismatch):
        m.predict(BUILDER.snapshot(s, "M2"))


def test_spec_hash_of_snapshot_is_checked(bundle: Path) -> None:
    m = load_artifact(bundle, CFG, PHARMA)
    snap = BUILDER.snapshot(run(cgm(steady(0, 180)))[-1], "M1")
    forged = FeatureSnapshot(
        snap.patient_key, snap.recording_key, snap.ts, "M1", snap.names, snap.values, "0" * 64, ""
    )
    with pytest.raises(FeatureSpecMismatch):
        m.predict(forged)


def test_out_of_range_inputs_are_named(bundle: Path) -> None:
    m = load_artifact(bundle, CFG, PHARMA)
    snap = BUILDER.snapshot(run(cgm(steady(0, 180, 400.0)))[-1], "M1")
    assert "cgm" in m.out_of_range(snap)


def test_tampered_file_is_refused(bundle: Path, tmp_path: Path) -> None:
    d = _copy(bundle, tmp_path)
    (d / "model.txt").write_bytes((d / "model.txt").read_bytes() + b"\n")
    with pytest.raises(ArtifactHashMismatch):
        load_artifact(d, CFG, PHARMA)


@pytest.mark.parametrize("name", ["calibrator.json", "model.txt", "manifest.json", "policy.json"])
def test_missing_file_is_refused(bundle: Path, tmp_path: Path, name: str) -> None:
    d = _copy(bundle, tmp_path)
    (d / name).unlink()
    with pytest.raises(ArtifactMissing):
        load_artifact(d, CFG, PHARMA)


@pytest.mark.parametrize(
    "key", ["feature_spec_sha256", "config_sha256", "pharma_sha256", "dictionary_sha256"]
)
def test_compatibility_mismatch_is_refused(bundle: Path, tmp_path: Path, key: str) -> None:
    d = _copy(bundle, tmp_path)
    m = _manifest(d)
    m["compatibility"][key] = "0" * 64
    _write_manifest(d, m)
    with pytest.raises(ArtifactIncompatible):
        load_artifact(d, CFG, PHARMA)


def test_running_configuration_change_is_refused(bundle: Path) -> None:
    cfg = copy.deepcopy(CFG)
    cfg["policy"]["cooldown_min"] = 30
    with pytest.raises(ArtifactIncompatible):
        load_artifact(bundle, cfg, PHARMA)
    pharma = copy.deepcopy(PHARMA)
    pharma["version"] = "9.9.9"
    with pytest.raises(ArtifactIncompatible):
        load_artifact(bundle, CFG, pharma)


def test_corrupted_content_with_consistent_hash_is_refused(bundle: Path, tmp_path: Path) -> None:
    d = _copy(bundle, tmp_path)
    bad = b"tree\nnot a lightgbm model\n"
    (d / "model.txt").write_bytes(bad)
    m = _manifest(d)
    m["files"]["model.txt"] = sha256_bytes(bad)
    _write_manifest(d, m)
    with pytest.raises(ArtifactIncompatible):
        load_artifact(d, CFG, PHARMA)


def test_level_and_feature_list_must_match_the_specification(bundle: Path, tmp_path: Path) -> None:
    d = _copy(bundle, tmp_path)
    m = _manifest(d)
    m["level"] = "M2"  # the model text still has M1 features
    m["features"] = list(level_names("M2"))
    _write_manifest(d, m)
    with pytest.raises(ArtifactIncompatible):
        load_artifact(d, CFG, PHARMA)
    m["level"] = "M9"
    _write_manifest(d, m)
    with pytest.raises(ArtifactIncompatible):
        load_artifact(d, CFG, PHARMA)


def test_pinned_manifest_and_confirmatory_label(bundle: Path, tmp_path: Path) -> None:
    sha = sha256_bytes((bundle / "manifest.json").read_bytes())
    assert load_artifact(bundle, CFG, PHARMA, sha).manifest_sha256 == sha
    with pytest.raises(ArtifactHashMismatch):
        load_artifact(bundle, CFG, PHARMA, "0" * 64)
    d = _copy(bundle, tmp_path)
    m = _manifest(d)
    m["status"] = "CONFIRMATORY"  # relabelling an unpinned artefact is refused
    _write_manifest(d, m)
    with pytest.raises(ArtifactIncompatible):
        load_artifact(d, CFG, PHARMA)
    with pytest.raises(ArtifactHashMismatch):  # and a pin of the original does not match
        load_artifact(d, CFG, PHARMA, sha)


@pytest.mark.parametrize(
    "policy",
    [
        {"tau_alert": 7.5, "tau_watch": 5.0, "strict": False},
        {"tau_alert": 0.5, "tau_watch": -0.1, "strict": False},
        {"tau_alert": 0.5, "tau_watch": 0.2, "strict": True},
        {"tau_alert": 0.2, "tau_watch": 0.5, "strict": False},
    ],
)
def test_invalid_thresholds_are_refused(
    bundle: Path,
    tmp_path: Path,
    policy: dict,  # type: ignore[type-arg]
) -> None:
    d = _copy(bundle, tmp_path)
    pol = json.loads((d / "policy.json").read_text("utf-8"))
    pol.update(policy)
    data = json.dumps(pol).encode("utf-8")
    (d / "policy.json").write_bytes(data)
    m = _manifest(d)
    m["files"]["policy.json"] = sha256_bytes(data)
    _write_manifest(d, m)
    with pytest.raises(ArtifactIncompatible):
        load_artifact(d, CFG, PHARMA)


def test_unreadable_manifest_and_wrong_status(bundle: Path, tmp_path: Path) -> None:
    d = _copy(bundle, tmp_path)
    (d / "manifest.json").write_text("{not json", "utf-8")
    with pytest.raises(ArtifactIncompatible):
        load_artifact(d, CFG, PHARMA)
    d2 = _copy(bundle, tmp_path / "x") if (tmp_path / "x").mkdir() is None else d
    m = _manifest(d2)
    m["status"] = "PRODUCTION"
    _write_manifest(d2, m)
    with pytest.raises(ArtifactIncompatible):
        load_artifact(d2, CFG, PHARMA)
