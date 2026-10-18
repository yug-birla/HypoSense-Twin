"""`hyposense dev s6`: S6 development workflow on the TUNING partition (DEC-2026-10-18-G).

1. M1 tuning: Optuna TPE (seed 2026, 30 trials), 4 patient-grouped folds over T. Every trial is
   recorded. num_boost_round = the median per-fold best iteration of the winning trial (P-B2).
2. Ladder: 5 outer patient-grouped folds. Per outer fold and model:
   - train on the outer-train eligible rows with the shared hyperparameters;
   - 4 inner folds give inner out-of-fold raw predictions, on which the calibrators are fitted
     (isotonic canonical; Platt and interpolated isotonic for P-B1);
   - predict EVERY reading of the held-out patients.
   Models: M1, M2, M3r, M3 (canonical); M3_compact (P-B8a); M1_pb6 (P-B6 training variant).
3. Evaluation through the S5 harness (unchanged), on pooled outer-OOF calibrated predictions,
   plus window metrics, paired patient-cluster bootstrap, the pre-registered decision rules,
   overfitting checks, grouped TreeSHAP and inert columns.

Status of every number: DEVELOPMENT (T only; tuning overlaps the outer CV, see the
pre-registration). E is never accessed.
"""

from __future__ import annotations

import json
import math
import os
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from hyposense.calibration.methods import METHODS, fit
from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_bytes, sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.common.runtime import disable_power_throttling, single_threaded_math_env
from hyposense.evaluation.bootstrap import paired_bootstrap, partial_area_stat, sens_at_budget_stat
from hyposense.evaluation.devdata import DevData, load_dev
from hyposense.evaluation.folds import grouped_folds
from hyposense.evaluation.m0_run import provenance
from hyposense.evaluation.metrics import (
    EventRules,
    calibration,
    curve,
    operating_point,
    partial_area,
    patient_curves,
    select_threshold,
    window_metrics,
)
from hyposense.features.spec import BY_NAME, level_names
from hyposense.models.lgbm import base_params, train
from hyposense.models.m0 import M0_STRICT

F64 = npt.NDArray[np.float64]
INPUTS = REPO_ROOT / "data" / "processed" / "dev" / "s6_inputs.parquet"
COMPACT_DROP = (
    "insulin_p30",
    "insulin_p60",
    "su_p30",
    "su_p60",
    "glinide_p30",
    "glinide_p60",
    "act_insulin_total_per_kg",
)
CANONICAL = ("M1", "M2", "M3r", "M3")


def model_sets() -> dict[str, dict[str, Any]]:
    m3 = level_names("M3")
    sets: dict[str, dict[str, Any]] = {
        name: {"features": level_names(name), "pb6": False} for name in CANONICAL
    }
    sets["M3_compact"] = {"features": tuple(f for f in m3 if f not in COMPACT_DROP), "pb6": False}
    sets["M1_pb6"] = {"features": level_names("M1"), "pb6": True}
    for v in sets.values():
        v["categorical"] = tuple(f for f in v["features"] if BY_NAME[f].dtype == "categorical")
    return sets


# ---------------------------------------------------------------- worker side
_W: dict[str, Any] = {}


def _init() -> None:
    disable_power_throttling()
    _W["t"] = pd.read_parquet(INPUTS)


def _rows(
    patients: set[str], eligible_only: bool, exclude_pb6: bool = False
) -> npt.NDArray[np.bool_]:
    t = _W["t"]
    m = np.array(t["patient_key"].isin(patients).to_numpy(), dtype=bool)  # writable copy
    if eligible_only:
        m = m & t["eligible"].to_numpy(bool)
    if exclude_pb6:
        m = m & ~t["pb6_exclude"].to_numpy(bool)
    out: npt.NDArray[np.bool_] = m
    return out


def task_tune_fold(
    args: tuple[dict[str, Any], set[str], set[str], tuple[str, ...], int, int],
) -> dict[str, Any]:
    params, train_p, valid_p, feats, max_rounds, es = args
    assert not train_p & valid_p, "tuning fold overlap"  # nested isolation, fail fast
    t = _W["t"]
    a = time.perf_counter()
    tr, va = _rows(train_p, True), _rows(valid_p, True)
    m = train(
        t.loc[tr, list(feats)],
        t.loc[tr, "y"].to_numpy(np.int64),
        params,
        max_rounds,
        valid=(t.loc[va, list(feats)], t.loc[va, "y"].to_numpy(np.int64)),
        early_stopping_rounds=es,
    )
    return {**m.history, "seconds": time.perf_counter() - a}


def task_outer(
    args: tuple[str, dict[str, Any], dict[str, Any], int, set[str], set[str], dict[str, int]],
) -> dict[str, Any]:
    name, spec, params, rounds, train_p, test_p, inner = args
    t = _W["t"]
    feats, cat, pb6 = list(spec["features"]), spec["categorical"], spec["pb6"]
    assert not train_p & test_p and set(inner) == train_p, "nested fold isolation violated"
    a = time.perf_counter()
    tr = _rows(train_p, True, pb6)
    model = train(t.loc[tr, feats], t.loc[tr, "y"].to_numpy(np.int64), params, rounds, cat)
    # inner out-of-fold raw predictions (eligible rows, no exclusion: calibration targets the
    # canonical labels)
    oof_p, oof_y = [], []
    for k in sorted(set(inner.values())):
        itr = {p for p, f in inner.items() if f != k}
        ite = {p for p, f in inner.items() if f == k}
        rtr, rte = _rows(itr, True, pb6), _rows(ite, True)
        mk = train(t.loc[rtr, feats], t.loc[rtr, "y"].to_numpy(np.int64), params, rounds, cat)
        oof_p.append(mk.predict(t.loc[rte, feats]))
        oof_y.append(t.loc[rte, "y"].to_numpy(np.int64))
    ip, iy = np.concatenate(oof_p), np.concatenate(oof_y)
    cals = {m: fit(m, ip, iy) for m in METHODS}
    te = _rows(test_p, False)
    idx = np.flatnonzero(te)
    raw = model.predict(t.loc[te, feats])
    elig_te = t.loc[te, "eligible"].to_numpy(bool)
    yte = t.loc[te, "y"].to_numpy(np.int64)
    contrib = model.booster().predict(
        t.loc[te, feats].to_numpy(np.float64)[elig_te], pred_contrib=True
    )
    abs_contrib = np.abs(contrib[:, :-1]).sum(axis=0)
    splits = model.booster().feature_importance("split")
    trp = model.predict(t.loc[tr, feats])
    ytr = t.loc[tr, "y"].to_numpy(np.int64)
    return {
        "name": name,
        "idx": idx,
        "raw": raw,
        "cal": {m: c.apply(raw) for m, c in cals.items()},
        "cal_params": {m: c.params for m, c in cals.items()},
        "model_sha256": model.sha256,
        "train_logloss": float(window_metrics(ytr, np.clip(trp, 1e-15, 1 - 1e-15))["log_loss"]),
        "heldout_raw_logloss": float(
            window_metrics(yte[elig_te], np.clip(raw[elig_te], 1e-15, 1 - 1e-15))["log_loss"]
        ),
        "abs_contrib": abs_contrib,
        "n_contrib_rows": int(elig_te.sum()),
        "zero_split_features": [f for f, s in zip(feats, splits, strict=True) if s == 0],
        "seconds": time.perf_counter() - a,
    }


# ---------------------------------------------------------------- main side
def tune_m1(
    pool: ProcessPoolExecutor, dev: DevData, cfg: dict[str, Any], n_trials: int | None = None
) -> dict[str, Any]:
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    m = cfg["model"]
    seed = int(m["seed"])
    space = m["search_space"]
    folds = grouped_folds(sorted(dev.strata), dev.strata, int(cfg["cv"]["inner_folds"]), seed)
    feats = level_names("M1")
    base = base_params(cfg)
    trials: list[dict[str, Any]] = []

    def objective(trial: Any) -> float:
        p = {
            **base,
            "learning_rate": trial.suggest_float("learning_rate", *space["learning_rate"]),
            "num_leaves": trial.suggest_int("num_leaves", *space["num_leaves"]),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", *space["min_data_in_leaf"]),
            "feature_fraction": trial.suggest_float("feature_fraction", *space["feature_fraction"]),
            "bagging_fraction": trial.suggest_float("bagging_fraction", *space["bagging_fraction"]),
            "lambda_l2": trial.suggest_float("lambda_l2", *space["lambda_l2"]),
        }
        tasks = [
            (
                p,
                {q for q, f in folds.items() if f != k},
                {q for q, f in folds.items() if f == k},
                feats,
                int(m["max_rounds"]),
                100,
            )
            for k in sorted(set(folds.values()))
        ]
        res = list(pool.map(task_tune_fold, tasks))
        val = float(np.mean([r["valid_logloss"] for r in res]))
        trials.append(
            {
                "number": trial.number,
                "params": {k: p[k] for k in space},
                "folds": res,
                "objective": val,
                "objective_sd": float(np.std([r["valid_logloss"] for r in res], ddof=1)),
                "status": "COMPLETE",
            }
        )
        return val

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=int(n_trials or m["optuna_trials"]))
    best = min(trials, key=lambda r: (r["objective"], r["number"]))
    rounds = int(np.median([r["best_iteration"] for r in best["folds"]]))
    return {
        "folds": folds,
        "trials": trials,
        "best": best,
        "num_boost_round": rounds,
        "params": {**base, **best["params"]},
    }


def pb1_decide(pb1: dict[str, dict[str, float]]) -> str:
    """P-B1: a challenger replaces isotonic iff log-loss >= 1 % lower AND ECE not higher."""
    iso = pb1["isotonic"]
    winners = [
        m
        for m in ("platt", "isotonic_interp")
        if pb1[m]["log_loss"] <= iso["log_loss"] * 0.99 and pb1[m]["ece"] <= iso["ece"]
    ]
    return min(winners, key=lambda m: pb1[m]["log_loss"]) if winners else "isotonic"


def pb6_decide(ll_canonical: float, ll_pb6: float) -> str:
    """P-B6 (c): adopt iff unaffected-patient log-loss improves by >= 1 %."""
    return "ADOPT for training" if ll_pb6 <= 0.99 * ll_canonical else "KEEP canonical training"


def pb8_decide(ll_m3: float, ll_compact: float, sens_m3: float, sens_compact: float) -> str:
    """P-B8 (a): compact preferred iff log-loss >= 1 % lower AND sens@1FA not lower."""
    if ll_compact <= 0.99 * ll_m3 and sens_compact >= sens_m3:
        return "candidate preferred (owner approval needed to change M3)"
    return "M3_baseline retained"


def _assemble(dev: DevData, outs: list[dict[str, Any]], method: str) -> F64:
    p = np.full(len(dev.table), np.nan)
    for o in outs:
        p[o["idx"]] = o["cal"][method] if method != "raw" else o["raw"]
    return p


def _per_patient_loss(dev: DevData, p: F64, patients: tuple[str, ...]) -> tuple[F64, F64]:
    t = dev.table
    e = t["eligible"].to_numpy(bool)
    y = t["y"].to_numpy(np.int64)
    pc = np.clip(p, 1e-15, 1 - 1e-15)
    ll = -(y * np.log(pc) + (1 - y) * np.log(1 - pc))
    s = pd.DataFrame({"p": t["patient_key"], "ll": np.where(e, ll, 0.0), "n": e.astype(float)})
    g = s.groupby("p").sum()
    return (g.loc[list(patients), "ll"].to_numpy(), g.loc[list(patients), "n"].to_numpy())


def evaluate(
    dev: DevData, scores: dict[str, F64], er: EventRules, B: int, seed: int, population: set[str]
) -> dict[str, Any]:
    recs = [r for r in dev.recs if r.patient_key in population]
    t = dev.table
    for name, p in scores.items():
        recs = [
            r.with_scores(
                name, p[dev.offsets[r.recording_key][0] : dev.offsets[r.recording_key][1]]
            )
            if name != "M0"
            else r
            for r in recs
        ]
    out: dict[str, Any] = {"models": {}, "comparisons": {}}
    stats: dict[str, Any] = {}
    pcs = {}
    names = ["M0", *scores]
    for name in names:
        strict = M0_STRICT if name == "M0" else False
        pc = patient_curves(recs, name, strict, er)
        pcs[name] = pc
        c = curve(pc)
        sa = select_threshold(c, 1.0, "fa")
        area, _reached = partial_area(c.fa_per_day, c.sensitivity)
        opp = operating_point(recs, name, sa.tau_a, strict, er) if math.isfinite(sa.tau_a) else None
        row: dict[str, Any] = {
            "sens_at_1fa": sa.value,
            "tau_alert": sa.tau_a,
            "budget_not_reached": sa.budget_not_reached,
            "partial_area": area,
            "non_monotone_fa_steps": c.non_monotone_steps,
            "grid_points": len(c.tau),
        }
        if opp is not None:
            pp = opp.pop("per_patient")
            sens_pp = [v["hits"] / v["episodes"] for v in pp.values() if v["episodes"]]
            row["operating_point"] = opp
            row["patient_weighted_sensitivity"] = float(np.mean(sens_pp)) if sens_pp else None
        if name != "M0":
            m = t["patient_key"].isin(population).to_numpy() & t["eligible"].to_numpy(bool)
            y = t.loc[m, "y"].to_numpy(np.int64)
            row["window"] = window_metrics(y, scores[name][m])
            cal = calibration(y, scores[name][m])
            row["calibration"] = {k: cal[k] for k in ("ece", "slope", "intercept")}
            row["reliability"] = cal["reliability"]
            row["unique_values"] = len(np.unique(scores[name][m]))
            ll, n = _per_patient_loss(dev, scores[name], pc.patients)

            def ll_stat(w: F64, ll: F64 = ll, n: F64 = n) -> float:
                return float(w @ ll / (w @ n)) if w @ n > 0 else float("nan")

            ll_stat.patients = pc.patients  # type: ignore[attr-defined]
            stats[f"{name}:logloss"] = ll_stat
        stats[f"{name}:sens1"] = sens_at_budget_stat(pc, 1.0)
        stats[f"{name}:area"] = partial_area_stat(pc)
        out["models"][name] = row
    pairs = {
        "C0_M1-M0": ("M1", "M0"),
        "C1_M2-M1": ("M2", "M1"),
        "C2a_M3r-M2": ("M3r", "M2"),
        "C2b_M3-M3r": ("M3", "M3r"),
        "preview_M3-M2": ("M3", "M2"),
        "PB8_M3compact-M3": ("M3_compact", "M3"),
        "PB6_M1pb6-M1": ("M1_pb6", "M1"),
    }
    diffs = {}
    for label, (a, b) in pairs.items():
        if (a not in scores and a != "M0") or (b not in scores and b != "M0"):
            continue
        for metric in ("sens1", "area", "logloss"):
            if metric == "logloss" and "M0" in (a, b):
                continue
            diffs[f"{label}:{metric}"] = (f"{a}:{metric}", f"{b}:{metric}")
    patients = pcs["M0"].patients
    res = paired_bootstrap(stats, len(patients), B, seed, differences=diffs, patients=patients)
    out["intervals"] = {}
    for k in res.point:
        target = out["comparisons"] if k in diffs else out["intervals"]
        target[k] = {
            "point": res.point[k],
            "ci95": list(res.ci95[k]),
            "undefined_resamples": res.undefined_resamples[k],
        }
    out["patients"] = len(patients)
    out["episodes"] = int(sum(len(r.onsets) for r in recs))
    return out


def _r(x: Any, nd: int = 6) -> Any:
    if isinstance(x, float | np.floating):
        return None if not math.isfinite(float(x)) else round(float(x), nd)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, dict):
        return {str(k): _r(v, nd) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_r(v, nd) for v in x]
    if isinstance(x, np.ndarray):
        return [_r(v, nd) for v in x.tolist()]
    return x


def run_s6(
    workers: int | None = None, resamples: int | None = None, trials: int | None = None
) -> dict[str, Any]:
    """`trials` / `resamples` overrides are for smoke tests only; evidence runs use the config."""
    cfg = load_config()
    disable_power_throttling()
    single_threaded_math_env()
    er = EventRules.from_config(cfg)
    B = int(resamples or cfg["bootstrap"]["resamples"])
    bseed = int(cfg["bootstrap"]["seed"])
    seed = int(cfg["model"]["seed"])
    started = utc_now_iso()
    timing: dict[str, float] = {}
    t0 = time.perf_counter()
    dev = load_dev()
    from hyposense.evaluation.devdata import save_inputs

    save_inputs(dev, INPUTS)
    timing["dev_data_s"] = time.perf_counter() - t0
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    sets = model_sets()
    with ProcessPoolExecutor(min(workers, 15), initializer=_init) as pool:
        t0 = time.perf_counter()
        tuned = tune_m1(pool, dev, cfg, trials)
        timing["tuning_s"] = time.perf_counter() - t0
        outer = grouped_folds(sorted(dev.strata), dev.strata, int(cfg["cv"]["folds"]), seed)
        tasks = []
        for name, spec in sets.items():
            for k in sorted(set(outer.values())):
                train_p = {p for p, f in outer.items() if f != k}
                test_p = {p for p, f in outer.items() if f == k}
                inner = grouped_folds(
                    sorted(train_p), dev.strata, int(cfg["cv"]["inner_folds"]), seed
                )
                tasks.append(
                    (name, spec, tuned["params"], tuned["num_boost_round"], train_p, test_p, inner)
                )
        t0 = time.perf_counter()
        results = list(pool.map(task_outer, tasks))
        timing["ladder_fits_s"] = time.perf_counter() - t0
    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_model.setdefault(r["name"], []).append(r)
    t = dev.table
    elig = t["eligible"].to_numpy(bool)
    y = t["y"].to_numpy(np.int64)
    # P-B1 decides ONE calibrator for every model, on M1 only (pre-registered rule)
    # P-B1 calibration benchmark on M1 (pooled held-out eligible rows)
    pb1 = {}
    for method in ("raw", *METHODS):
        p = _assemble(dev, by_model["M1"], method)[elig]
        wm = window_metrics(y[elig], np.clip(p, 0, 1))
        cal = calibration(y[elig], np.clip(p, 1e-9, 1 - 1e-9))
        pb1[method] = {
            "log_loss": wm["log_loss"],
            "brier": wm["brier"],
            "ece": cal["ece"],
            "slope": cal["slope"],
            "intercept": cal["intercept"],
            "unique_values": len(np.unique(p)),
        }
    pb1_decision = pb1_decide(pb1)
    band_rule = {
        "calibrator": pb1_decision,
        "m1_heldout_slope": pb1[pb1_decision]["slope"],
        "ui": "percentages" if 0.8 <= pb1[pb1_decision]["slope"] <= 1.25 else "risk bands",
    }
    scores = {name: _assemble(dev, outs, pb1_decision) for name, outs in by_model.items()}
    if any(np.isnan(v).any() for v in scores.values()):
        raise AssertionError("some readings have no out-of-fold prediction")

    t0 = time.perf_counter()
    pops = {"treated": dev.treated & set(dev.strata), "all": set(dev.strata)}
    ladder = {k: evaluate(dev, scores, er, B, bseed, v) for k, v in pops.items()}
    timing["evaluation_s"] = time.perf_counter() - t0

    # POST-HOC DIAGNOSTIC (not pre-registered; never used for selection): non-learned CGM-level
    # rules through the same harness, to test whether a large M1-over-M0 gain is signal or leakage
    diag_rules: dict[str, Any] = {}
    level_scores = {
        "level_-cgm": -t["cgm"].to_numpy(),
        "level15_-(cgm+15*slope30)": -(t["cgm"] + 15 * t["cgm_slope30"].fillna(0.0)).to_numpy(),
    }
    for pname, pset in pops.items():
        sub_recs = [r for r in dev.recs if r.patient_key in pset]
        for rname, sc in level_scores.items():
            rr = [
                r.with_scores(
                    rname, sc[dev.offsets[r.recording_key][0] : dev.offsets[r.recording_key][1]]
                )
                for r in sub_recs
            ]
            c = curve(patient_curves(rr, rname, False, er))
            b = select_threshold(c, 1.0, "fa")
            diag_rules[f"{pname}:{rname}"] = {"sens_at_1fa": b.value, "tau_alert": b.tau_a}
    # P-B6: unaffected patients
    affected = set(dev.pb6_summary["affected_patient_keys_private"])
    unaff = elig & ~t["patient_key"].isin(affected).to_numpy()
    ll_m1 = window_metrics(y[unaff], scores["M1"][unaff])["log_loss"]
    ll_pb6 = window_metrics(y[unaff], scores["M1_pb6"][unaff])["log_loss"]
    pb6 = {
        "m1_logloss_unaffected": ll_m1,
        "m1_pb6_logloss_unaffected": ll_pb6,
        "relative_improvement": (ll_m1 - ll_pb6) / ll_m1,
        "decision": pb6_decide(ll_m1, ll_pb6),
        **{k: v for k, v in dev.pb6_summary.items() if not k.endswith("_private")},
    }
    # P-B8 compact M3
    lm3 = ladder["all"]["models"]["M3"]["window"]["log_loss"]
    lc = ladder["all"]["models"]["M3_compact"]["window"]["log_loss"]
    s3 = ladder["treated"]["models"]["M3"]["sens_at_1fa"]
    sc = ladder["treated"]["models"]["M3_compact"]["sens_at_1fa"]
    pb8 = {
        "m3_logloss_all": lm3,
        "m3_compact_logloss_all": lc,
        "m3_sens1_treated": s3,
        "m3_compact_sens1_treated": sc,
        "decision": pb8_decide(lm3, lc, s3, sc),
    }
    # overfitting and behaviour
    overfit = {
        name: {
            "train_logloss": [o["train_logloss"] for o in outs],
            "heldout_raw_logloss": [o["heldout_raw_logloss"] for o in outs],
        }
        for name, outs in by_model.items()
    }
    groups = {}
    for name, outs in by_model.items():
        feats = sets[name]["features"]
        tot = np.sum([o["abs_contrib"] for o in outs], axis=0) / sum(
            o["n_contrib_rows"] for o in outs
        )
        g: dict[str, float] = {}
        for f, v in zip(feats, tot, strict=True):
            g[BY_NAME[f].group.value] = g.get(BY_NAME[f].group.value, 0.0) + float(v)
        groups[name] = dict(sorted(g.items(), key=lambda kv: -kv[1]))
    inert = {
        name: sorted(set.intersection(*[set(o["zero_split_features"]) for o in outs]))
        for name, outs in by_model.items()
    }
    oof = np.column_stack([scores[n] for n in sorted(scores)])
    oof_sha = sha256_bytes(np.ascontiguousarray(oof).tobytes())
    deterministic = _r(
        {
            "status": "DEVELOPMENT (tuning partition only; not confirmatory)",
            "protocol": "DEC-2026-10-18-G",
            "tuning": {
                "best_trial": tuned["best"]["number"],
                "best_params": tuned["best"]["params"],
                "cv_logloss_mean": tuned["best"]["objective"],
                "cv_logloss_sd": tuned["best"]["objective_sd"],
                "best_fold_iterations": [f["best_iteration"] for f in tuned["best"]["folds"]],
                "num_boost_round": tuned["num_boost_round"],
                "trials": len(tuned["trials"]),
            },
            "folds": {"tuning": tuned["folds"], "outer": outer},
            "models": {
                n: {
                    "features": len(sets[n]["features"]),
                    "categorical": list(sets[n]["categorical"]),
                    "outer_model_sha256": [o["model_sha256"] for o in by_model[n]],
                    "inert_columns": len(inert[n]),
                }
                for n in sets
            },
            "ladder": ladder,
            "pb1_calibration": {"methods": pb1, "decision": pb1_decision, "band_rule": band_rule},
            "pb6": pb6,
            "pb8": pb8,
            "pb7": "NOT RUN: 0 glinide patients in T (identical to baseline by construction)",
            "diagnostic_simple_rules": diag_rules,
            "overfitting": overfit,
            "grouped_shap_mean_abs": groups,
            "inert_columns": inert,
            "oof_sha256": oof_sha,
        }
    )
    run_id = make_run_id("T-AGG-dev-s6")
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    sha = sha256_json(deterministic)
    prov = provenance(
        {
            "feature_table_sha256": dev.provenance["table_sha256"],
            "s6_inputs_sha256": sha256_bytes(INPUTS.read_bytes()),
            "model_seed": seed,
            "bootstrap": {"resamples": B, "seed": bseed},
        }
    )
    doc = {
        "run_id": run_id,
        "created_utc": started,
        "finished_utc": utc_now_iso(),
        "status": "DEVELOPMENT",
        "partition": "T",
        "results_sha256": sha,
        "provenance": prov,
        "results": deterministic,
        "timing_s": _r(timing, 2),
    }
    (out / "results.json").write_text(
        json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    trials_df = pd.DataFrame(
        [
            {
                "trial": r["number"],
                **r["params"],
                "cv_logloss": r["objective"],
                "cv_logloss_sd": r["objective_sd"],
                "fold_best_iterations": ";".join(str(f["best_iteration"]) for f in r["folds"]),
                "fold_logloss": ";".join(f"{f['valid_logloss']:.6f}" for f in r["folds"]),
                "seconds": round(sum(f["seconds"] for f in r["folds"]), 2),
                "status": r["status"],
            }
            for r in tuned["trials"]
        ]
    )
    trials_df.to_csv(out / "trials.csv", index=False, lineterminator="\n")
    (out / "ladder.md").write_text(ladder_table(deterministic), encoding="utf-8", newline="\n")
    priv = REPO_ROOT / "data" / "processed" / "dev" / run_id
    priv.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        {
            "recording_key": t["recording_key"],
            "ts": t["ts"],
            **{n: scores[n] for n in sorted(scores)},
        }
    ).to_parquet(priv / "oof.parquet", index=False)
    return {
        "run_id": run_id,
        "results_sha256": sha,
        "git": prov["git"],
        "num_boost_round": tuned["num_boost_round"],
        "best": tuned["best"]["params"],
        "sens_at_1fa_treated": {
            n: deterministic["ladder"]["treated"]["models"][n]["sens_at_1fa"]
            for n in deterministic["ladder"]["treated"]["models"]
        },
        "timing_s": _r(timing, 1),
    }


def ladder_table(det: dict[str, Any]) -> str:
    """Generated from the result document (never retyped)."""
    lines = ["# S6 development ladder (DEVELOPMENT ONLY; tuning partition; not confirmatory)", ""]
    for pop in ("treated", "all"):
        L = det["ladder"][pop]
        lines += [
            f"## {pop} T patients ({L['patients']} patients, {L['episodes']} episodes)",
            "",
            "| Model | sens@1FA (95% CI) | partial area (CI) | lead median | precision | "
            "log-loss | Brier | AUPRC | ECE | slope | intercept |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name, m in L["models"].items():
            ci = L["intervals"].get(f"{name}:sens1", {}).get("ci95")
            ca = L["intervals"].get(f"{name}:area", {}).get("ci95")
            op = m.get("operating_point") or {}
            w = m.get("window") or {}
            c = m.get("calibration") or {}
            lines.append(
                f"| {name} | {m['sens_at_1fa']} ({ci}) | {m['partial_area']} ({ca}) | "
                f"{(op.get('lead_min') or {}).get('median')} | {op.get('alert_precision')} | "
                f"{w.get('log_loss', 'n/a')} | {w.get('brier', 'n/a')} | {w.get('auprc', 'n/a')} | "
                f"{c.get('ece', 'n/a')} | {c.get('slope', 'n/a')} | {c.get('intercept', 'n/a')} |"
            )
        lines += ["", "| Paired difference | point | 95% CI |", "|---|---|---|"]
        for k, v in L["comparisons"].items():
            lines.append(f"| {k} | {v['point']} | {v['ci95']} |")
        lines.append("")
    return "\n".join(lines) + "\n"
