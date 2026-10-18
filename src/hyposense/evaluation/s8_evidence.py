"""Aggregate evidence for the Evidence View (DEVELOPMENT, T only; E sealed).

Operating curves (FA/day vs sensitivity) of the official S6 out-of-fold predictions, computed
with the canonical S5 harness (`patient_curves` + `curve`, ANALYSIS_PLAN §3). Nothing is re-fitted
or re-selected. The OOF table is verified against the hash recorded by the S6 run before use.
Output is aggregate only (no patient-level values):
experiments/runs/T-AGG-dev-evidence-<ts>/results.json.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_bytes, sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.evaluation.devdata import load_dev
from hyposense.evaluation.m0_run import provenance
from hyposense.evaluation.metrics import EventRules, curve, patient_curves
from hyposense.evaluation.s7_artifact import S6_RUN, frozen_s6
from hyposense.models.m0 import M0_STRICT

MODELS = ("M0", "M1", "M2", "M3r", "M3")
FA_MAX = 3.0  # display range of the operating curves (FA per patient-day)
MAX_POINTS = 5000


def _thin(f: np.ndarray, s: np.ndarray) -> tuple[list[float], list[float]]:
    keep = f <= FA_MAX
    f, s = f[keep], s[keep]
    if len(f) > MAX_POINTS:  # display thinning; first and last points always kept
        idx = np.unique(np.linspace(0, len(f) - 1, MAX_POINTS).round().astype(int))
        f, s = f[idx], s[idx]
    return [round(float(x), 5) for x in f], [round(float(x), 5) for x in s]


def build_evidence() -> dict[str, Any]:
    started = utc_now_iso()
    cfg = load_config()
    s6 = frozen_s6()
    oof = pd.read_parquet(REPO_ROOT / "data" / "processed" / "dev" / S6_RUN / "oof.parquet")
    names = sorted(c for c in oof.columns if c not in ("recording_key", "ts"))
    arr = np.column_stack([oof[n].to_numpy(np.float64) for n in names])
    if sha256_bytes(np.ascontiguousarray(arr).tobytes()) != s6["results"]["oof_sha256"]:
        raise RuntimeError("OOF predictions differ from the hash recorded by the S6 run")
    dev = load_dev()
    t = dev.table
    if not (
        np.array_equal(oof["ts"].to_numpy(), t["ts"].to_numpy())
        and (oof["recording_key"].to_numpy() == t["recording_key"].to_numpy()).all()
    ):
        raise AssertionError("OOF rows are not aligned with the development table")
    er = EventRules.from_config(cfg)
    pops = {"treated": dev.treated & set(dev.strata), "all": set(dev.strata)}
    curves: dict[str, Any] = {}
    for pop, pset in pops.items():
        curves[pop] = {}
        for m in MODELS:
            recs = [r for r in dev.recs if r.patient_key in pset]
            if m != "M0":
                recs = [
                    r.with_scores(
                        m,
                        oof[m].to_numpy(np.float64)[
                            dev.offsets[r.recording_key][0] : dev.offsets[r.recording_key][1]
                        ],
                    )
                    for r in recs
                ]
            strict = M0_STRICT if m == "M0" else False
            c = curve(patient_curves(recs, m, strict, er))
            f, s = _thin(c.fa_per_day, c.sensitivity)
            curves[pop][m] = {"fa_per_day": f, "sensitivity": s, "episodes": c.n_episodes}
    det = {
        "status": "DEVELOPMENT",
        "partition": "T",
        "source_run": S6_RUN,
        "source_results_sha256": s6["results_sha256"],
        "oof_sha256_verified": s6["results"]["oof_sha256"],
        "display": {"fa_max": FA_MAX, "max_points": MAX_POINTS},
        "curves": curves,
    }
    run_id = make_run_id("T-AGG-dev-evidence")
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    doc = {
        "run_id": run_id,
        "created_utc": started,
        "finished_utc": utc_now_iso(),
        "status": "DEVELOPMENT",
        "results_sha256": sha256_json(det),
        "provenance": provenance({"s6_run": S6_RUN}),
        "results": det,
    }
    (out / "results.json").write_text(json.dumps(doc) + "\n", "utf-8", newline="\n")
    return {"run_id": run_id, "results_sha256": doc["results_sha256"]}
