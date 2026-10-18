"""DEVELOPMENT model artefact for the S7 service (T only; E sealed).

It mirrors the confirmatory deployment procedure (Blueprint §11.1, §14.3; ANALYSIS_PLAN §3.5-3.6)
on the tuning partition, with the frozen S6 choices (DEC-2026-10-18-H):
1. hyperparameters and num_boost_round from the official S6 run (verified by its results hash);
2. grouped out-of-fold raw predictions over T (the S6 outer folds, seed 2026);
3. the P-B1 rule-selected calibrator fitted on the eligible OOF predictions;
4. τA (dev FA <= 1.0 / patient-day) and τW (notification rate <= 3.0, then min(τW, τA)) chosen
   on the calibrated OOF predictions of ALL T patients (the training patients) with the S5
   harness;
5. the final model fitted on every eligible T row;
6. development ranges (0.5th-99.5th percentile, eligible rows) for the LOW CONFIDENCE tag.

Canonical training: P-B6 exclusion NOT applied (pending, DEC-2026-10-18-I F2); M3_baseline
features (P-B8 pending). The result is labelled DEVELOPMENT and is never evidence.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np

from hyposense.calibration.methods import fit
from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.evaluation.devdata import load_dev
from hyposense.evaluation.folds import grouped_folds
from hyposense.evaluation.m0_run import provenance
from hyposense.evaluation.metrics import EventRules, curve, patient_curves, select_threshold
from hyposense.evaluation.s6_run import model_sets
from hyposense.features.spec import BY_NAME
from hyposense.models.artifact import RANGE_DTYPES, write_artifact
from hyposense.models.lgbm import base_params, train
from hyposense.policy.decide import PolicyRules, Thresholds

S6_RUN = "T-AGG-dev-s6-20261018T144427Z"  # official S6 run (results e81268ae…)
MODELS_DIR = REPO_ROOT / "artifacts" / "models"


def frozen_s6(run: str = S6_RUN) -> dict[str, Any]:
    doc: dict[str, Any] = json.loads(
        (REPO_ROOT / "experiments" / "runs" / run / "results.json").read_text("utf-8")
    )
    if sha256_json(doc["results"]) != doc["results_sha256"]:
        raise RuntimeError(f"{run}: results do not match their recorded hash")
    return doc


def build_dev_artifact(level: str = "M3", out_root: Path = MODELS_DIR) -> dict[str, Any]:
    started = utc_now_iso()
    t0 = time.perf_counter()
    cfg, pharma = load_config(), load_config("pharma.yaml")
    s6 = frozen_s6()
    tuning = s6["results"]["tuning"]
    method = s6["results"]["pb1_calibration"]["decision"]
    dev = load_dev()
    t = dev.table
    spec = model_sets()[level]
    feats, cat = list(spec["features"]), spec["categorical"]
    params = {**base_params(cfg), **tuning["best_params"]}
    rounds = int(tuning["num_boost_round"])
    elig = t["eligible"].to_numpy(bool)
    y = t["y"].to_numpy(np.int64)
    pk = t["patient_key"].to_numpy()
    folds = grouped_folds(
        sorted(dev.strata), dev.strata, int(cfg["cv"]["folds"]), int(cfg["model"]["seed"])
    )  # as S6
    fold_of = np.array([folds[p] for p in pk])
    oof = np.full(len(t), np.nan)
    for k in sorted(set(folds.values())):
        tr = elig & (fold_of != k)
        m = train(t.loc[tr, feats], y[tr], params, rounds, cat)
        te = fold_of == k
        oof[te] = m.predict(t.loc[te, feats])
    if np.isnan(oof).any():
        raise AssertionError("some readings have no out-of-fold prediction")
    calibrator = fit(method, oof[elig], y[elig])
    p_oof = calibrator.apply(oof)
    er = EventRules.from_config(cfg)
    recs = [
        r.with_scores(
            level, p_oof[dev.offsets[r.recording_key][0] : dev.offsets[r.recording_key][1]]
        )
        for r in dev.recs
    ]
    c = curve(patient_curves(recs, level, False, er))
    sel_a = select_threshold(c, float(cfg["policy"]["fa_budget_alert"]), "fa")
    sel_w = select_threshold(c, float(cfg["policy"]["fa_budget_watch"]), "notifications")
    if sel_a.budget_not_reached or not np.isfinite(sel_a.tau_a):
        raise RuntimeError("τA: the development budget is not reached; refusing to build")
    th = Thresholds(sel_a.tau_a, min(sel_w.tau_a, sel_a.tau_a))
    final = train(t.loc[elig, feats], y[elig], params, rounds, cat)
    ranges: dict[str, tuple[float, float]] = {}
    for f in feats:
        if BY_NAME[f].dtype in RANGE_DTYPES:
            v = t.loc[elig, f].to_numpy(np.float64)
            v = v[~np.isnan(v)]
            if len(v):
                lo, hi = np.percentile(v, cfg["policy"]["range_pct"])
                ranges[f] = (float(lo), float(hi))
    prov = provenance(
        {
            "partition": "T",
            "feature_table_sha256": dev.provenance["table_sha256"],
            "s6_run": S6_RUN,
            "s6_results_sha256": s6["results_sha256"],
            "calibrator": method,
            "training_rows": int(elig.sum()),
            "training_patients": len(dev.strata),
            "pb6_applied": False,
            "dev_sens_at_1fa_oof": sel_a.value,
            "dev_fa_at_tau_alert": sel_a.f_a,
            "tau_alert_budget_not_reached": sel_a.budget_not_reached,
            "tau_watch_budget_not_reached": sel_w.budget_not_reached,
            "tau_watch_capped_at_tau_alert": sel_w.tau_a > sel_a.tau_a,
            "created_utc": started,
        }
    )
    out = out_root / make_run_id(f"{level}-dev")
    manifest = write_artifact(
        out,
        level=level,
        model_text=final.model_text,
        calibrator=calibrator,
        thresholds=th,
        rules=PolicyRules.from_config(cfg),
        feature_range=ranges,
        status="DEVELOPMENT",
        cfg=cfg,
        pharma=pharma,
        provenance=prov,
    )
    return {
        "directory": (
            out.relative_to(REPO_ROOT).as_posix() if out.is_relative_to(REPO_ROOT) else str(out)
        ),
        "files": manifest["files"],
        "model_version": manifest["model_version"],
        "tau_alert": th.tau_alert,
        "tau_watch": th.tau_watch,
        "oof_sens_at_1fa_all_T": sel_a.value,
        "seconds": round(time.perf_counter() - t0, 1),
    }
