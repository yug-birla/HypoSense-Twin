"""`hyposense audit features`: run the S4 feature audit on the TUNING partition and write evidence.

Outputs:
- experiments/runs/T-AGG-audit-features-<UTC>/audit_features.json and .md: aggregate only.
  These are committed evidence; they hold no row-level values.
- data/processed/features/v<spec>/tuning_features.parquet + provenance: row-level, git-ignored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hyposense.audit.features import run_feature_audit
from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.data.manifest import read_manifest
from hyposense.data.source import dataset_config
from hyposense.features.export import SPEC_PATH, provenance, write_matrix
from hyposense.features.spec import spec_sha256


def _md(run_id: str, det: dict[str, Any], timing: dict[str, Any], sha: str) -> str:
    fl = det["statistics"]["flags"]
    lines = [
        f"# S4 feature audit — {run_id}",
        "",
        "Scope: TUNING partition only (aggregate statistics; no row-level values).",
        "",
        f"- results_sha256: `{sha}`",
        f"- table_sha256: `{det['table_sha256']}` (two builds identical: "
        f"{det['determinism_two_builds_identical']})",
        f"- recordings {det['recordings']}, patients {det['patients']}, readings "
        f"{det['readings']}, label-eligible {det['eligible_rows']} "
        f"(positive {det['eligible_positive_rows']}), L1 episodes {det['l1_episodes_T']}",
        f"- level sizes: {det['level_sizes']}",
        "",
        "## Causality",
        f"- truncation equality: {det['truncation']['comparisons']} comparisons, "
        f"{det['truncation']['mismatches']} mismatches",
        f"- offline vs replay parity: {det['parity']['comparisons']} snapshot comparisons, "
        f"{det['parity']['mismatches']} mismatches",
        "- future perturbation: "
        + ", ".join(
            f"{k} {v['mismatches']}/{v['comparisons']}" for k, v in det["perturbation"].items()
        ),
        f"- causal tracker vs label builder: {det['tracker_vs_label_builder']}",
        "",
        "## Flags (label-eligible T rows)",
        *[f"- {k}: {v}" for k, v in fl.items()],
        "",
        "## Redundancy",
        f"- named pairs: {det['redundancy']['named']}",
        f"- |rho| >= 0.95 pairs: {len(det['redundancy']['pairs_abs_ge_0.95'])}; identical "
        f"columns: {len(det['redundancy']['identical_columns'])}",
        "",
        "## Performance",
        *[f"- {k}: {v}" for k, v in timing.items()],
        "",
    ]
    return "\n".join(lines)


def run_features_audit(workers: int | None = None) -> dict[str, Any]:
    cfg = load_config()
    committed = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    if committed.get("sha256") != spec_sha256(cfg["features"]):
        raise RuntimeError(
            "artifacts/features/feature_spec.json is stale: run "
            "`hyposense features spec` and commit it"
        )
    started = utc_now_iso()
    res = run_feature_audit(workers=workers)
    df = res.pop("table")
    det, timing = res["deterministic"], res["timing"]
    manifest = read_manifest(REPO_ROOT / dataset_config()["paths"]["manifest_json"])
    prov = provenance(str(manifest["files_sha256"]))
    prov["table_sha256"] = det["table_sha256"]
    prov["rows"] = det["readings"]
    matrix = write_matrix(df, prov)
    run_id = make_run_id("T-AGG-audit-features")
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    sha = sha256_json(det)
    doc = {
        "run_id": run_id,
        "started_utc": started,
        "finished_utc": utc_now_iso(),
        "provenance": prov,
        "results_sha256": sha,
        "deterministic": det,
        "timing": timing,
        "matrix_path": str(Path(matrix).relative_to(REPO_ROOT)).replace("\\", "/"),
    }
    (out / "audit_features.json").write_text(
        json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    (out / "audit_features.md").write_text(
        _md(run_id, det, timing, sha), encoding="utf-8", newline="\n"
    )
    return {
        "run_id": run_id,
        "results_sha256": sha,
        "git": prov["git"],
        "truncation": det["truncation"],
        "parity": det["parity"],
        "perturbation": det["perturbation"],
        "tracker_vs_label_builder": det["tracker_vs_label_builder"],
        "determinism_two_builds_identical": det["determinism_two_builds_identical"],
        "flags": det["statistics"]["flags"],
        "timing": timing,
    }
