"""Feature-specification export and tuning-matrix generation with provenance (CLAUDE.md §13).

- `write_spec()` writes artifacts/features/feature_spec.json, the generated export of
  `features.spec`. It is committed, and a test fails if it drifts from the registry.
- `build_tuning_matrix()` replays every TUNING recording and returns the per-reading table
  (identifiers + metadata + union features) and its provenance. The table holds row-level
  patient data, so it is written under data/processed/ (git-ignored), never committed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from hyposense.common.config import REPO_ROOT, config_hash, load_config
from hyposense.common.hashing import canonical_json, sha256_bytes, sha256_file
from hyposense.common.provenance import environment, git_state, utc_now_iso
from hyposense.data.dataset import AccessScope, load_dataset
from hyposense.features.build import RecordingFeatures, build_recording, to_frame, tuning_streams
from hyposense.features.snapshot import FeatureBuilder
from hyposense.features.spec import spec_document, spec_sha256
from hyposense.medication.dictionary import load_dictionary
from hyposense.state.patient import EngineConfig

SPEC_PATH = REPO_ROOT / "artifacts" / "features" / "feature_spec.json"
MATRIX_DIR = REPO_ROOT / "data" / "processed" / "features"


def write_spec(path: Path = SPEC_PATH) -> str:
    cfg = load_config()
    doc = spec_document(cfg["features"])
    doc["sha256"] = spec_sha256(cfg["features"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return str(doc["sha256"])


def frame_sha256(df: pd.DataFrame) -> str:
    """Content hash of a feature table (column names, dtypes and raw bytes, in order)."""
    parts = [canonical_json([list(map(str, df.columns)), [str(t) for t in df.dtypes]]).encode()]
    for c in df.columns:
        col = df[c]
        parts.append(
            col.astype(str).str.cat(sep="|").encode()
            if col.dtype == object
            else col.to_numpy().tobytes()
        )
    return sha256_bytes(b"".join(parts))


def provenance(ds_hash: str) -> dict[str, Any]:
    cfg, pharma = load_config(), load_config("pharma.yaml")
    d = load_dictionary()
    return {
        "generated_utc": utc_now_iso(),
        "git": git_state(),
        "dataset_files_sha256": ds_hash,
        "partition_sha256": cfg["partition"]["sha256"],
        "config_sha256": config_hash(cfg),
        "feature_spec_version": cfg["features"]["spec_version"],
        "feature_spec_sha256": spec_sha256(cfg["features"]),
        "drug_dictionary_sha256": d.sha256,
        "pharma_version": pharma.get("version"),
        "pharma_sha256": sha256_file(REPO_ROOT / "configs" / "pharma.yaml"),
        "environment": environment(),
    }


def build_tuning_matrix() -> tuple[pd.DataFrame, list[RecordingFeatures], dict[str, Any]]:
    cfg, pharma = load_config(), load_config("pharma.yaml")
    ds = load_dataset(AccessScope.TUNING_ONLY)
    plaus = {k: (float(v[0]), float(v[1])) for k, v in cfg["features"]["static_plausible"].items()}
    streams = tuning_streams(ds, load_dictionary(), pharma["formulation_rules"], plaus)
    engine = EngineConfig.from_config(cfg, pharma)
    builder = FeatureBuilder(cfg)
    parts = [build_recording(s, engine, builder) for s in streams]
    df = to_frame(parts)
    prov = provenance(ds.manifest_files_sha256)
    prov.update(
        {
            "scope": ds.scope.value,
            "recordings": len(parts),
            "patients": len({p.patient_key for p in parts}),
            "rows": len(df),
            "table_sha256": frame_sha256(df),
            "stream_exclusions": {
                k: sum(s.excluded.get(k, 0) for s in streams)
                for k in sorted({k for s in streams for k in s.excluded})
            },
            "context_issues": sorted({i for s in streams for i in s.context.issues}),
        }
    )
    return df, parts, prov


def write_matrix(df: pd.DataFrame, prov: dict[str, Any]) -> Path:
    out = MATRIX_DIR / f"v{prov['feature_spec_version']}"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "tuning_features.parquet"
    df.to_parquet(path, index=False)
    (out / "tuning_features.provenance.json").write_text(
        json.dumps(prov, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    return path
