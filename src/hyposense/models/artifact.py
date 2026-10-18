"""Deployable model artefact: write, verify, load (Blueprint §18 Table 18.1; ADR-009, no pickle).

A bundle directory holds:

    model.txt          LightGBM native text model
    calibrator.json    {method, params}                     (calibration.methods.Calibrator)
    policy.json        thresholds + policy rules             (policy.decide)
    feature_range.json development 0.5th-99.5th percentiles  (LOW CONFIDENCE tag, Table 14.1)
    manifest.json      SHA-256 of every file + compatibility hashes + provenance + status

`load_artifact` REFUSES (raises ArtifactError) unless every file exists and matches its hash,
and the compatibility hashes equal the running code/configuration:
- feature-spec hash (features/spec.py + config `features`);
- configuration hash (parsed configs/default.yaml);
- pharma.yaml hash (kernels) and drug-dictionary hash;
- model level and feature names equal the specification of that level.
There is no fallback: the service does not start on a mismatch (§18 "API refuses to start").

`status` is DEVELOPMENT (fitted on T, before freeze) or CONFIRMATORY. The service treats both
identically; the status is shown wherever a prediction is shown.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from hyposense.calibration.methods import Calibrator
from hyposense.common.config import config_hash
from hyposense.common.hashing import sha256_bytes, sha256_file, sha256_json
from hyposense.features.snapshot import FeatureSnapshot
from hyposense.features.spec import BY_NAME, FeatureSpecMismatch, level_names, spec_sha256
from hyposense.medication.dictionary import DICTIONARY_PATH
from hyposense.policy.decide import PolicyRules, Thresholds

FILES = ("model.txt", "calibrator.json", "policy.json", "feature_range.json")
STATUSES = ("DEVELOPMENT", "CONFIRMATORY")
FORMAT_VERSION = "1.0.0"
POLICY_VERSION = "1.0.0"
RANGE_DTYPES = ("float", "count")  # binary / categorical inputs have no "range"


class ArtifactError(RuntimeError):
    """The artefact cannot be used. Inference must not start."""


class ArtifactMissing(ArtifactError):
    pass


class ArtifactHashMismatch(ArtifactError):
    pass


class ArtifactIncompatible(ArtifactError):
    pass


def compatibility(cfg: dict[str, Any], pharma: dict[str, Any]) -> dict[str, str]:
    """Hashes of everything the artefact's meaning depends on, from the RUNNING code/config."""
    return {
        "feature_spec_sha256": spec_sha256(cfg["features"]),
        "config_sha256": config_hash(cfg),
        "pharma_sha256": sha256_json(pharma),
        "dictionary_sha256": sha256_file(DICTIONARY_PATH),
    }


def _dump(obj: Any) -> bytes:
    return (json.dumps(obj, indent=1, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def write_artifact(
    out: Path,
    *,
    level: str,
    model_text: str,
    calibrator: Calibrator,
    thresholds: Thresholds,
    rules: PolicyRules,
    feature_range: dict[str, tuple[float, float]],
    status: str,
    cfg: dict[str, Any],
    pharma: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(status)
    out.mkdir(parents=True, exist_ok=False)
    contents = {
        "model.txt": model_text.encode("utf-8"),
        "calibrator.json": _dump({"method": calibrator.method, "params": calibrator.params}),
        "policy.json": _dump(
            {
                "policy_version": POLICY_VERSION,
                "tau_alert": thresholds.tau_alert,
                "tau_watch": thresholds.tau_watch,
                "strict": thresholds.strict,
                "rules": {
                    "low_mgdl": rules.low_mgdl,
                    "post_episode_s": rules.post_episode_s,
                    "cooldown_s": rules.cooldown_s,
                    "max_gap_s": rules.max_gap_s,
                },
            }
        ),
        "feature_range.json": _dump({k: list(v) for k, v in sorted(feature_range.items())}),
    }
    for name, data in contents.items():
        (out / name).write_bytes(data)
    files = {name: sha256_bytes(data) for name, data in contents.items()}
    manifest = {
        "format_version": FORMAT_VERSION,
        "level": level,
        "features": list(level_names(level)),
        "status": status,
        "model_version": f"{level}-{status.lower()}-{files['model.txt'][:12]}",
        "files": files,
        "compatibility": compatibility(cfg, pharma),
        "provenance": provenance,
    }
    (out / "manifest.json").write_bytes(_dump(manifest))
    return manifest


@dataclass(frozen=True)
class RuntimeModel:
    """A verified artefact, ready for single-reading inference. The booster is parsed once."""

    directory: Path
    manifest: dict[str, Any]
    manifest_sha256: str
    level: str
    features: tuple[str, ...]
    booster: Any
    calibrator: Calibrator
    thresholds: Thresholds
    rules: PolicyRules
    range_index: npt.NDArray[np.intp]
    range_lo: npt.NDArray[np.float64]
    range_hi: npt.NDArray[np.float64]

    @property
    def model_version(self) -> str:
        return str(self.manifest["model_version"])

    @property
    def status(self) -> str:
        return str(self.manifest["status"])

    def _check(self, s: FeatureSnapshot) -> npt.NDArray[np.float64]:
        if s.level != self.level or s.names != self.features:
            raise FeatureSpecMismatch(f"snapshot level {s.level} != model level {self.level}")
        if s.spec_sha256 != self.manifest["compatibility"]["feature_spec_sha256"]:
            raise FeatureSpecMismatch("snapshot built with another feature specification")
        return s.values.reshape(1, -1)

    def predict(self, s: FeatureSnapshot) -> tuple[float, float]:
        """(raw score, calibrated probability). Raises on any malformed output."""
        raw = float(self.booster.predict(self._check(s), num_threads=1)[0])
        p = float(self.calibrator.apply(np.array([raw]))[0])
        if not (math.isfinite(raw) and math.isfinite(p) and 0.0 <= p <= 1.0):
            raise ArithmeticError(f"malformed inference output raw={raw} p={p}")
        return raw, p

    def out_of_range(self, s: FeatureSnapshot) -> tuple[str, ...]:
        """Inputs outside the development 0.5th-99.5th percentile range (Table 14.1 tag).
        Missing values are not out of range (they carry their own quality flags)."""
        v = s.values[self.range_index]
        bad = ~np.isnan(v) & ((v < self.range_lo) | (v > self.range_hi))
        return tuple(self.features[i] for i in self.range_index[bad])

    def contributions(self, s: FeatureSnapshot) -> dict[str, float]:
        """TreeSHAP contributions on the raw margin (pre-calibration; §4.9), per feature."""
        c = self.booster.predict(self._check(s), pred_contrib=True, num_threads=1)[0]
        return {f: float(x) for f, x in zip(self.features, c[:-1], strict=True)}


def _read(directory: Path, name: str) -> bytes:
    path = directory / name
    if not path.is_file():
        raise ArtifactMissing(f"artefact file missing: {name}")
    return path.read_bytes()


def load_artifact(
    directory: Path,
    cfg: dict[str, Any],
    pharma: dict[str, Any],
    expected_manifest_sha256: str | None = None,
) -> RuntimeModel:
    """Verify and load. `expected_manifest_sha256` pins the whole bundle (the manifest lists the
    hash of every other file). A CONFIRMATORY artefact is refused unless it is pinned (the pin
    comes from the freeze record), so an edited manifest cannot relabel a DEVELOPMENT model."""
    import lightgbm as lgb

    raw_manifest = _read(directory, "manifest.json")
    if (
        expected_manifest_sha256 is not None
        and sha256_bytes(raw_manifest) != expected_manifest_sha256
    ):
        raise ArtifactHashMismatch("manifest.json differs from the pinned SHA-256")
    try:
        manifest = json.loads(raw_manifest)
        files: dict[str, str] = manifest["files"]
        level = str(manifest["level"])
        status = str(manifest["status"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ArtifactIncompatible(f"unreadable manifest: {exc}") from exc
    if manifest.get("format_version") != FORMAT_VERSION:
        raise ArtifactIncompatible(f"artefact format {manifest.get('format_version')!r}")
    if set(files) != set(FILES):
        raise ArtifactIncompatible(f"manifest lists {sorted(files)}, expected {sorted(FILES)}")
    if status not in STATUSES:
        raise ArtifactIncompatible(f"unknown status {status!r}")
    if status == "CONFIRMATORY" and expected_manifest_sha256 is None:
        raise ArtifactIncompatible("a CONFIRMATORY artefact must be pinned by its manifest SHA-256")
    data = {}
    for name in FILES:
        data[name] = _read(directory, name)
        if sha256_bytes(data[name]) != files[name]:
            raise ArtifactHashMismatch(f"{name}: SHA-256 differs from the manifest")
    current = compatibility(cfg, pharma)
    for key, value in current.items():
        if manifest.get("compatibility", {}).get(key) != value:
            raise ArtifactIncompatible(f"{key} of the artefact differs from the running system")
    try:
        names = level_names(level)
    except (KeyError, FeatureSpecMismatch) as exc:
        raise ArtifactIncompatible(f"unknown model level {level!r}") from exc
    if tuple(manifest.get("features", ())) != names:
        raise ArtifactIncompatible("artefact feature list differs from the specification")
    try:
        booster = lgb.Booster(model_str=data["model.txt"].decode("utf-8"))
        cal = json.loads(data["calibrator.json"])
        calibrator = Calibrator(str(cal["method"]), dict(cal["params"]))
        pol = json.loads(data["policy.json"])
        ranges = json.loads(data["feature_range.json"])
    except Exception as exc:
        raise ArtifactIncompatible(f"corrupted artefact content: {exc}") from exc
    if tuple(booster.feature_name()) != names:
        raise ArtifactIncompatible("model.txt feature names differ from the specification")
    if pol.get("policy_version") != POLICY_VERSION:
        raise ArtifactIncompatible(f"policy version {pol.get('policy_version')!r}")
    rules = PolicyRules(**pol["rules"])
    if rules != PolicyRules.from_config(cfg):
        raise ArtifactIncompatible("policy rules differ from the configuration")
    try:
        thresholds = Thresholds(float(pol["tau_alert"]), pol["tau_watch"], bool(pol["strict"]))
    except (ValueError, TypeError) as exc:
        raise ArtifactIncompatible(f"invalid thresholds: {exc}") from exc
    if not 0.0 <= thresholds.tau_alert <= 1.0 or thresholds.strict:
        raise ArtifactIncompatible("learned models need 0 <= tau <= 1 and the >= comparator")
    probe = calibrator.apply(np.linspace(0.0, 1.0, 101))
    if (
        not np.all(np.isfinite(probe))
        or np.any(np.diff(probe) < 0)
        or probe.min() < 0.0
        or probe.max() > 1.0
    ):
        raise ArtifactIncompatible("calibrator is not a monotone map into [0, 1]")
    idx = [i for i, f in enumerate(names) if BY_NAME[f].dtype in RANGE_DTYPES and f in ranges]
    return RuntimeModel(
        directory=directory,
        manifest=manifest,
        manifest_sha256=sha256_bytes(raw_manifest),
        level=level,
        features=names,
        booster=booster,
        calibrator=calibrator,
        thresholds=thresholds,
        rules=rules,
        range_index=np.array(idx, dtype=np.intp),
        range_lo=np.array([ranges[names[i]][0] for i in idx], dtype=np.float64),
        range_hi=np.array([ranges[names[i]][1] for i in idx], dtype=np.float64),
    )
