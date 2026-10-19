"""Pre-freeze Class B development runs on T (P-B10 calibration, P-B11 fit stability, P-B12
LOW_CONFIDENCE). Protocol and decision rules were committed before any run (docs/PROPOSALS.md,
DEC-2026-10-19-L; commit 6b1ad05). E is never loaded (`load_dev` is TUNING_ONLY).

Fits reuse the S6 worker machinery unchanged (`s6_run._init`, `_rows`, nested folds, frozen
hyperparameters at full precision from the S6 trials table, 113 rounds). The canonical
configuration (fold seed 2026, model seed 2026) must reproduce the S6 `oof_sha256` bitwise
before any result is computed (integrity gate).

Output: experiments/runs/T-AGG-dev-prefreeze-<ts>/results.json (+ prefreeze.md tables).
All results are DEVELOPMENT; P-B6 (M1_pb6) is SENSITIVITY.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from typing import Any

import numpy as np
import numpy.typing as npt

from hyposense.calibration.methods import CHALLENGERS, METHODS, fit
from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_bytes, sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.common.runtime import disable_power_throttling, single_threaded_math_env
from hyposense.evaluation import s6_run
from hyposense.evaluation.devdata import DevData, load_dev
from hyposense.evaluation.folds import grouped_folds
from hyposense.evaluation.m0_run import provenance
from hyposense.evaluation.metrics import (
    EventRules,
    calibration,
    curve,
    partial_area,
    patient_curves,
    select_threshold,
    window_metrics,
)
from hyposense.evaluation.s7_artifact import S6_RUN, frozen_params, frozen_s6
from hyposense.features.spec import BY_NAME, Group, level_names
from hyposense.medication.exposure import QualityState
from hyposense.models.artifact import RANGE_DTYPES
from hyposense.models.lgbm import train

F64 = npt.NDArray[np.float64]

# ---------------------------------------------------------------- pre-specified (6b1ad05)
FOLD_SEEDS = (2026, 2028, 2029)
MODEL_SEEDS = (2026, 2028, 2029, 2030, 2031)
CANONICAL = (2026, 2026)
GRID_MODELS = ("M1", "M2", "M3r", "M3", "M3_compact")
SENSITIVITY_MODELS = ("M1_pb6",)  # canonical configuration only
CALS = ("raw", *METHODS, *CHALLENGERS)
CURRENT, FLOORED, PLATT = "isotonic_interp", "isotonic_interp_floored", "platt"
CONTRASTS = {
    "M2-M1": ("M2", "M1"),
    "M3r-M2": ("M3r", "M2"),
    "M3-M3r": ("M3", "M3r"),
    "M3-M2": ("M3", "M2"),
    "M3_compact-M3": ("M3_compact", "M3"),
}
PB12_CANDIDATES = {
    "C0_current": ("all", (0.5, 99.5)),
    "C1_key_inputs": ("key", (0.5, 99.5)),
    "C2_wider_range": ("all", (0.1, 99.9)),
}
KEY_GROUPS = (Group.G1, Group.G2, Group.G8)
PB12_RATE = (0.01, 0.10)
PB12_B = 1000
TIMING_UNKNOWN_CODE = float(list(QualityState).index(QualityState.TIMING_UNKNOWN))


# ---------------------------------------------------------------- pure decision rules
def ll_unclipped(y: npt.NDArray[np.int64], p: F64) -> float:
    """Log-loss without clipping: +inf if a positive gets 0 or a negative gets 1."""
    if np.any((y == 1) & (p <= 0.0)) or np.any((y == 0) & (p >= 1.0)):
        return math.inf
    terms = np.where(
        y == 1, -np.log(np.where(y == 1, p, 1.0)), -np.log(np.where(y == 0, 1 - p, 1.0))
    )
    return float(terms.mean())


def pb10_outcome(cur: dict[str, float], flo: dict[str, float], platt: dict[str, float]) -> str:
    """R1/R2 of the pre-specified P-B10 rule (one configuration, M1)."""
    if math.isinf(cur["ll_u"]):
        for name, m in (("ADOPT floored", flo), ("ADOPT platt", platt)):
            if math.isfinite(m["ll_u"]) and m["ece"] <= 1.10 * cur["ece"]:
                return name
        return "INCONCLUSIVE"
    if flo["ll_u"] <= 0.99 * cur["ll_u"] and flo["ece"] <= cur["ece"]:
        return "ADOPT floored"
    if flo["ll_u"] >= 1.01 * cur["ll_u"] or flo["ece"] > 1.10 * cur["ece"]:
        return "KEEP CURRENT"
    return "NO MATERIAL DIFFERENCE"


def pb10_integrity(per_model: dict[str, dict[str, dict[str, float]]]) -> bool:
    """R0: floored vs current within 0.01 on sens@1FA and partial area for every grid model."""
    return all(
        abs(m[FLOORED]["sens_at_1fa"] - m[CURRENT]["sens_at_1fa"]) <= 0.01
        and abs(m[FLOORED]["partial_area"] - m[CURRENT]["partial_area"]) <= 0.01
        for m in per_model.values()
    )


def pb10_decision(canonical: str, integrity: bool, per_config: Sequence[str]) -> str:
    if not integrity:
        return "INCONCLUSIVE"
    if sum(o == canonical for o in per_config) < 10:  # R3
        return "INCONCLUSIVE"
    return {"ADOPT floored": "ADOPT", "ADOPT platt": "ADOPT"}.get(canonical, canonical)


def stability_label(deltas: Sequence[float]) -> str:
    """P-B11 reading: stable if one sign in >= 13/15; unstable if the minority sign >= 4/15."""
    pos = sum(d > 0 for d in deltas)
    neg = sum(d < 0 for d in deltas)
    if pos == neg == 0:
        return "tied"  # every configuration tied (reported separately; not "leaning")
    if max(pos, neg) >= 13:
        return "stable"
    if min(pos, neg) >= 4:
        return "unstable"
    return "leaning"


def pb12_criteria(
    rate: float, separation: float, ci95: Sequence[float], positive_configs: int
) -> dict[str, bool]:
    """Pre-specified P-B12 criteria: (a) rate in [1 %, 10 %]; (b) separation > 0 with the 95 %
    CI excluding 0; (c) separation > 0 in >= 12/15 configurations."""
    return {
        "a_rate": PB12_RATE[0] <= rate <= PB12_RATE[1],
        "b_separation": separation > 0 and ci95[0] > 0,
        "c_stability": positive_configs >= 12,
    }


def pb12_decision(
    useful: dict[str, bool],
    sep_ok: dict[str, bool],
    stable: dict[str, bool],
    separation: dict[str, float],
) -> str:
    """Pre-specified P-B12 rule. useful = (a)+(b)+(c); sep_ok = (b); stable = (c)."""
    revised = [c for c in ("C1_key_inputs", "C2_wider_range") if useful[c]]
    if revised:
        best = max(revised, key=lambda c: (separation[c], c == "C1_key_inputs"))
        return f"ADOPT REVISED RULE ({best})"
    if sep_ok["C0_current"] and stable["C0_current"]:
        return "KEEP CURRENT"
    if not any(sep_ok.values()):
        return "REMOVE TAG"
    return "INCONCLUSIVE"


LADDER = ("M1", "M2", "M3r", "M3")


def ladder_order(metrics: dict[str, Any], ck: str, cal: str) -> list[str]:
    """Models by sens@1FA, best first (ties broken by ladder order, deterministically)."""
    return sorted(LADDER, key=lambda m: (-metrics[ck][m][cal]["sens_at_1fa"], LADDER.index(m)))


# ---------------------------------------------------------------- inputs
# ---------------------------------------------------------------- worker
def task_fit(args: tuple[Any, ...]) -> dict[str, Any]:
    key, name, spec, params, rounds, train_p, test_p, inner = args
    t = s6_run._W["t"]
    feats, cat, pb6 = list(spec["features"]), spec["categorical"], spec["pb6"]
    assert not train_p & test_p and set(inner) == train_p, "nested fold isolation violated"
    a = time.perf_counter()
    tr = s6_run._rows(train_p, True, pb6)
    model = train(t.loc[tr, feats], t.loc[tr, "y"].to_numpy(np.int64), params, rounds, cat)
    oof_p, oof_y = [], []
    for k in sorted(set(inner.values())):
        itr = {p for p, f in inner.items() if f != k}
        ite = {p for p, f in inner.items() if f == k}
        rtr, rte = s6_run._rows(itr, True, pb6), s6_run._rows(ite, True)
        mk = train(t.loc[rtr, feats], t.loc[rtr, "y"].to_numpy(np.int64), params, rounds, cat)
        oof_p.append(mk.predict(t.loc[rte, feats]))
        oof_y.append(t.loc[rte, "y"].to_numpy(np.int64))
    ip, iy = np.concatenate(oof_p), np.concatenate(oof_y)
    cals = {m: fit(m, ip, iy) for m in (*METHODS, *CHALLENGERS)}
    te = s6_run._rows(test_p, False)
    raw = model.predict(t.loc[te, feats])
    return {
        "key": key,
        "name": name,
        "idx": np.flatnonzero(te),
        "cal": {"raw": raw, **{m: c.apply(raw) for m, c in cals.items()}},
        "p_lo": cals[FLOORED].params["p_lo"],
        "lowest_block": cals[FLOORED].params["lowest_block"],
        "seconds": time.perf_counter() - a,
    }


# ---------------------------------------------------------------- metrics
_M: dict[str, Any] = {}


def _init_metrics() -> None:
    disable_power_throttling()
    _M["dev"] = load_dev()
    _M["er"] = EventRules.from_config(load_config())


def task_metrics(args: tuple[Any, ...]) -> tuple[Any, ...]:
    key, p, name, pset = args
    return key, _metrics(_M["dev"], p, name, pset, _M["er"])


def _metrics(
    dev: DevData, p: F64, name: str, pset: set[str], er: EventRules, window: bool = True
) -> dict[str, Any]:
    t = dev.table
    recs = [
        r.with_scores(name, p[dev.offsets[r.recording_key][0] : dev.offsets[r.recording_key][1]])
        for r in dev.recs
        if r.patient_key in pset
    ]
    c = curve(patient_curves(recs, name, False, er))
    sa = select_threshold(c, 1.0, "fa")
    area, _ = partial_area(c.fa_per_day, c.sensitivity)
    out: dict[str, Any] = {"sens_at_1fa": sa.value, "partial_area": area, "tau_alert": sa.tau_a}
    if window:
        m = t["patient_key"].isin(pset).to_numpy() & t["eligible"].to_numpy(bool)
        y, q = t.loc[m, "y"].to_numpy(np.int64), p[m]
        wm = window_metrics(y, q)
        cal = calibration(y, q)
        out.update(
            ll_u=ll_unclipped(y, q),
            log_loss=wm["log_loss"],
            brier=wm["brier"],
            auprc=wm["auprc"],
            ece=cal["ece"],
            slope=cal["slope"],
            intercept=cal["intercept"],
            exact0=int((q == 0.0).sum()),
            exact1=int((q == 1.0).sum()),
            unique=len(np.unique(q)),
        )
    return out


def _window(y: npt.NDArray[np.int64], q: F64) -> dict[str, Any]:
    wm = window_metrics(y, q)
    cal = calibration(y, q)
    return {
        "ll_u": ll_unclipped(y, q),
        "log_loss": wm["log_loss"],
        "brier": wm["brier"],
        "auprc": wm["auprc"],
        "ece": cal["ece"],
        "slope": cal["slope"],
        "intercept": cal["intercept"],
        "exact0": int((q == 0.0).sum()),
        "exact1": int((q == 1.0).sum()),
        "positives_at_exact0": int(((q == 0.0) & (y == 1)).sum()),
        "unique": len(np.unique(q)),
    }


def _subset(
    y: npt.NDArray[np.int64], p: F64, m: npt.NDArray[np.bool_], tau: float
) -> dict[str, Any]:
    n = int(m.sum())
    if n == 0:
        return {"n": 0}
    yy, pp = y[m], p[m]
    pi = float(yy.mean())
    brier = float(((pp - yy) ** 2).mean())
    out: dict[str, Any] = {
        "n": n,
        "positives": int(yy.sum()),
        "base_rate": pi,
        "mean_p": float(pp.mean()),
        "brier": brier,
        "bss": 1 - brier / (pi * (1 - pi)) if 0 < pi < 1 else None,
        "log_loss": float(window_metrics(yy, pp)["log_loss"]),
        "sens_at_tau_reading": float((pp[yy == 1] >= tau).mean()) if yy.sum() else None,
    }
    if 0 < yy.sum() < n:
        out["ece"] = calibration(yy, pp)["ece"]
    return out


def _separation_ci(
    pk: npt.NDArray[Any], y: npt.NDArray[np.int64], p: F64, tag: npt.NDArray[np.bool_], seed: int
) -> tuple[float, list[float]]:
    pats, inv = np.unique(pk, return_inverse=True)
    sums = np.zeros((len(pats), 6))
    for col, mask in ((0, tag), (3, ~tag)):
        np.add.at(sums[:, col], inv[mask], 1.0)
        np.add.at(sums[:, col + 1], inv[mask], y[mask].astype(float))
        np.add.at(sums[:, col + 2], inv[mask], (p[mask] - y[mask]) ** 2)

    def sep(w: F64) -> float:
        s = w @ sums
        out = []
        for col in (3, 0):  # untagged, tagged
            n, k, sq = s[col], s[col + 1], s[col + 2]
            pi = k / n if n else float("nan")
            out.append(1 - (sq / n) / (pi * (1 - pi)) if n and 0 < pi < 1 else float("nan"))
        return float(out[0] - out[1])

    point = sep(np.ones(len(pats)))
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(PB12_B):
        w = np.bincount(rng.integers(0, len(pats), len(pats)), minlength=len(pats)).astype(float)
        v = sep(w)
        if math.isfinite(v):
            boots.append(v)
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return point, [float(lo), float(hi)]


def _tags(dev: DevData, outer: dict[str, int]) -> dict[str, npt.NDArray[np.bool_]]:
    """OOF tags: ranges from each outer fold's TRAINING eligible rows, applied to held-out rows."""
    t = dev.table
    feats = [f for f in level_names("M3") if BY_NAME[f].dtype in RANGE_DTYPES]
    key = [f for f in feats if BY_NAME[f].group in KEY_GROUPS]
    elig = t["eligible"].to_numpy(bool)
    fold = t["patient_key"].map(outer).to_numpy()
    out = {c: np.zeros(len(t), dtype=bool) for c in PB12_CANDIDATES}
    for k in sorted(set(outer.values())):
        tr, te = elig & (fold != k), fold == k
        for c, (which, (plo, phi)) in PB12_CANDIDATES.items():
            cols = feats if which == "all" else key
            X = t[cols].to_numpy(np.float64)
            lo = np.nanpercentile(X[tr], plo, axis=0)
            hi = np.nanpercentile(X[tr], phi, axis=0)
            Xe = X[te]
            bad = ~np.isnan(Xe) & ((Xe < lo) | (Xe > hi))
            out[c][te] = bad.any(axis=1)
    return out


# ---------------------------------------------------------------- run
def run_prefreeze(workers: int = 6) -> dict[str, Any]:
    started = utc_now_iso()
    t_all = time.perf_counter()
    cfg = load_config()
    disable_power_throttling()
    single_threaded_math_env()
    s6 = frozen_s6()
    params, rounds = frozen_params(cfg)
    dev = load_dev()
    from hyposense.evaluation.devdata import save_inputs

    save_inputs(dev, s6_run.INPUTS)
    sets = s6_run.model_sets()
    nf, nif = int(cfg["cv"]["folds"]), int(cfg["cv"]["inner_folds"])
    configs = [(fs, ms) for fs in FOLD_SEEDS for ms in MODEL_SEEDS]
    outers = {fs: grouped_folds(sorted(dev.strata), dev.strata, nf, fs) for fs in FOLD_SEEDS}
    tasks = []
    for fs, ms in configs:
        outer = outers[fs]
        # canonical: all six S6 models (the integrity gate hashes them; includes M1_pb6)
        models: tuple[str, ...] = tuple(sorted(sets)) if (fs, ms) == CANONICAL else GRID_MODELS
        for name in models:
            for k in sorted(set(outer.values())):
                train_p = {p for p, f in outer.items() if f != k}
                test_p = {p for p, f in outer.items() if f == k}
                inner = grouped_folds(sorted(train_p), dev.strata, nif, fs)
                tasks.append(
                    (
                        (fs, ms),
                        name,
                        sets[name],
                        {**params, "seed": ms},
                        rounds,
                        train_p,
                        test_p,
                        inner,
                    )
                )
    timing: dict[str, float] = {}
    a = time.perf_counter()
    with ProcessPoolExecutor(workers, initializer=s6_run._init) as pool:
        results = list(pool.map(task_fit, tasks, chunksize=2))
    timing["fits_s"] = round(time.perf_counter() - a, 1)
    timing["fits"] = len(tasks) * (1 + nif)
    n = len(dev.table)
    scores: dict[tuple[int, int], dict[str, dict[str, F64]]] = {}
    floors: dict[tuple[int, int], dict[str, list[dict[str, Any]]]] = {}
    for r in results:
        sc = scores.setdefault(r["key"], {}).setdefault(
            r["name"], {c: np.full(n, np.nan) for c in CALS}
        )
        for c in CALS:
            sc[c][r["idx"]] = r["cal"][c]
        floors.setdefault(r["key"], {}).setdefault(r["name"], []).append(
            {"p_lo": r["p_lo"], **r["lowest_block"]}
        )
    # ---- integrity gate: canonical isotonic_interp reproduces S6 bitwise
    can = scores[CANONICAL]
    arr = np.column_stack([can[m][CURRENT] for m in sorted(can)])
    gate = sha256_bytes(np.ascontiguousarray(arr).tobytes())
    if gate != s6["results"]["oof_sha256"]:
        raise RuntimeError(
            f"integrity gate failed: OOF {gate[:12]} != S6 {s6['results']['oof_sha256'][:12]}"
        )
    for by_m in scores.values():
        for by_c in by_m.values():
            if any(np.isnan(v).any() for v in by_c.values()):
                raise AssertionError("missing out-of-fold predictions")

    treated = dev.treated & set(dev.strata)
    everyone = set(dev.strata)
    a = time.perf_counter()
    mtasks = [
        (("treated", f"f{fs}_m{ms}", name, c), p, name, treated)
        for (fs, ms), by_model in scores.items()
        for name, by_cal in by_model.items()
        for c, p in by_cal.items()
    ] + [
        (("all", "canonical", name, c), p, name, everyone)
        for name, by_cal in scores[CANONICAL].items()
        for c, p in by_cal.items()
    ]
    with ProcessPoolExecutor(workers, initializer=_init_metrics) as pool:
        done = list(pool.map(task_metrics, mtasks, chunksize=4))
    metrics: dict[str, dict[str, dict[str, Any]]] = {}
    all_pop: dict[str, dict[str, Any]] = {}
    for (pop, ck, name, c), res in done:
        if pop == "treated":
            metrics.setdefault(ck, {}).setdefault(name, {})[c] = res
        else:
            all_pop.setdefault(name, {})[c] = res
    timing["metrics_s"] = round(time.perf_counter() - a, 1)
    ckeys = [f"f{fs}_m{ms}" for fs, ms in configs]
    canon = f"f{CANONICAL[0]}_m{CANONICAL[1]}"

    # ---- P-B10: LL_u / ECE on the P-B1 set = ALL patients' pooled outer held-out eligible
    # rows (pre-specified); sens@1FA / partial area on treated patients (R0)
    elig_all = dev.table["eligible"].to_numpy(bool)
    y_all = dev.table["y"].to_numpy(np.int64)
    pb1_set: dict[str, dict[str, dict[str, Any]]] = {}
    for (fs, ms), by_model in scores.items():
        for name in ("M1", "M1_pb6"):
            if name in by_model:
                pb1_set.setdefault(f"f{fs}_m{ms}", {})[name] = {
                    c: _window(y_all[elig_all], p[elig_all]) for c, p in by_model[name].items()
                }

    def outcome(ck: str, model: str = "M1") -> str:
        m = pb1_set[ck][model]
        return pb10_outcome(m[CURRENT], m[FLOORED], m[PLATT])

    integrity = pb10_integrity({m: metrics[canon][m] for m in GRID_MODELS})
    per_cfg = [outcome(ck) for ck in ckeys]
    pb10 = {
        "evaluation_set": (
            "M1, canonical configuration: LL_u/LL/Brier/ECE/slope/exact-0/1 on ALL patients' "
            "pooled outer held-out eligible rows (P-B1 set); sens@1FA/area/tau on treated"
        ),
        "candidates": {
            c: {
                **pb1_set[canon]["M1"][c],
                **{
                    k: metrics[canon]["M1"][c][k]
                    for k in ("sens_at_1fa", "partial_area", "tau_alert")
                },
            }
            for c in CALS
        },
        "r0_integrity": integrity,
        "canonical_outcome": per_cfg[ckeys.index(canon)],
        "per_configuration_outcome": dict(zip(ckeys, per_cfg, strict=True)),
        "r3_agreement": sum(o == per_cfg[ckeys.index(canon)] for o in per_cfg),
        "floors_canonical_M1": floors[CANONICAL]["M1"],
        "sensitivity_M1_pb6": {
            c: {
                **pb1_set[canon]["M1_pb6"][c],
                **{k: metrics[canon]["M1_pb6"][c][k] for k in ("sens_at_1fa", "partial_area")},
            }
            for c in (CURRENT, FLOORED, PLATT)
        },
        "sensitivity_M1_pb6_outcome": outcome(canon, "M1_pb6"),
    }
    canonical_outcome = per_cfg[ckeys.index(canon)]
    pb10["decision"] = pb10_decision(canonical_outcome, integrity, per_cfg)
    decided = CURRENT
    if pb10["decision"] == "ADOPT":
        decided = FLOORED if canonical_outcome == "ADOPT floored" else PLATT
    pb10["calibrator_for_pb12"] = decided

    # ---- P-B11
    pb11: dict[str, Any] = {"configurations": ckeys, "calibrators": {}}
    for cal in (CURRENT, FLOORED, "raw"):
        summ: dict[str, Any] = {}
        for name in GRID_MODELS:
            per = {
                k: [metrics[ck][name][cal][k] for ck in ckeys]
                for k in (
                    "sens_at_1fa",
                    "partial_area",
                    "log_loss",
                    "brier",
                    "auprc",
                    "ece",
                    "slope",
                )
            }
            summ[name] = {
                k: {
                    "mean": float(np.mean(v)),
                    "sd": float(np.std(v, ddof=1)),
                    "min": float(np.min(v)),
                    "max": float(np.max(v)),
                }
                for k, v in per.items()
            }
        ranks: dict[str, dict[int, int]] = {m: {} for m in LADDER}
        for ck in ckeys:
            for i, m in enumerate(ladder_order(metrics, ck, cal)):
                ranks[m][i + 1] = ranks[m].get(i + 1, 0) + 1
        contrasts: dict[str, Any] = {}
        for label, (x, z) in CONTRASTS.items():
            for metric in ("sens_at_1fa", "partial_area", "log_loss"):
                d = [metrics[ck][x][cal][metric] - metrics[ck][z][cal][metric] for ck in ckeys]
                better = [-v for v in d] if metric == "log_loss" else d  # >0 = first model better
                contrasts[f"{label}:{metric}"] = {
                    "deltas": d,
                    "first_better": sum(v > 0 for v in better),
                    "second_better": sum(v < 0 for v in better),
                    "ties": sum(v == 0 for v in better),
                    "median": float(np.median(d)),
                    "min": float(np.min(d)),
                    "max": float(np.max(d)),
                    "reading": stability_label(better),
                }
        pb11["calibrators"][cal] = {
            "summary": summ,
            "rank_frequency_sens1": ranks,
            "contrasts": contrasts,
        }
    pb11["ranking_changed_by_calibrator"] = sum(
        ladder_order(metrics, ck, CURRENT) != ladder_order(metrics, ck, FLOORED) for ck in ckeys
    )

    # ---- P-B12
    t = dev.table
    elig = t["eligible"].to_numpy(bool)
    y = t["y"].to_numpy(np.int64)
    pk = t["patient_key"].to_numpy()
    timing_unknown = np.zeros(len(t), dtype=bool)
    for c in ("insulin", "sulfonylurea", "glinide"):
        timing_unknown |= t[f"quality_{c}"].to_numpy() == TIMING_UNKNOWN_CODE
    sensor = t["pb6_exclude"].to_numpy(bool)
    pb12: dict[str, Any] = {"calibrator": decided, "candidates": {}}
    seps: dict[str, list[float]] = {c: [] for c in PB12_CANDIDATES}
    for fs, ms in configs:
        ck = f"f{fs}_m{ms}"
        tags = _tags(dev, outers[fs])
        p = scores[(fs, ms)]["M3"][decided]
        for c, tg in tags.items():
            ut, uu = _subset(y, p, elig & tg, 0.0), _subset(y, p, elig & ~tg, 0.0)
            ok = ut.get("bss") is not None and uu.get("bss") is not None
            seps[c].append(uu["bss"] - ut["bss"] if ok else float("nan"))
        if (fs, ms) == CANONICAL:
            tau = metrics[canon]["M3"][decided]["tau_alert"]
            for c, tg in tags.items():
                te = elig & tg
                sep, ci = _separation_ci(
                    pk[elig], y[elig], p[elig], tg[elig], int(cfg["bootstrap"]["seed"])
                )
                pats_all = set(pk[elig])
                pb12["candidates"][c] = {
                    "definition": PB12_CANDIDATES[c],
                    "rate": float(te.sum() / elig.sum()),
                    "patients_affected": len(set(pk[te])) / len(pats_all),
                    "tagged": _subset(y, p, te, tau),
                    "untagged": _subset(y, p, elig & ~tg, tau),
                    "separation_bss": sep,
                    "separation_ci95": ci,
                    "overlap_timing_unknown": float((te & timing_unknown).sum() / max(te.sum(), 1)),
                    "overlap_sensor_artefact_pb6": float((te & sensor).sum() / max(te.sum(), 1)),
                    "within_timing_known": {
                        "tagged": _subset(y, p, te & ~timing_unknown, tau),
                        "untagged": _subset(y, p, elig & ~tg & ~timing_unknown, tau),
                    },
                }
    useful, sep_ok, stable, separation = {}, {}, {}, {}
    for c, d in pb12["candidates"].items():
        d["separation_per_configuration"] = seps[c]
        d["separation_positive_configs"] = sum(v > 0 for v in seps[c] if math.isfinite(v))
        crit = pb12_criteria(
            d["rate"], d["separation_bss"], d["separation_ci95"], d["separation_positive_configs"]
        )
        sep_ok[c], stable[c] = crit["b_separation"], crit["c_stability"]
        useful[c] = all(crit.values())
        d["criteria"] = crit
        separation[c] = d["separation_bss"]
    pb12["decision"] = pb12_decision(useful, sep_ok, stable, separation)

    det = {
        "status": "DEVELOPMENT",
        "partition": "T",
        "protocol_commit": "6b1ad05",
        "source_run": S6_RUN,
        "source_results_sha256": s6["results_sha256"],
        "integrity_gate": {"oof_sha256": gate, "matches_s6": True},
        "grid": {
            "fold_seeds": FOLD_SEEDS,
            "model_seeds": MODEL_SEEDS,
            "models": GRID_MODELS,
            "sensitivity_models": SENSITIVITY_MODELS,
        },
        "frozen_hyperparameters": {k: params[k] for k in s6["results"]["tuning"]["best_params"]},
        "num_boost_round": rounds,
        "score_sha256": {
            f"f{k[0]}_m{k[1]}": {
                m: sha256_bytes(np.ascontiguousarray(v[CURRENT]).tobytes()) for m, v in by.items()
            }
            for k, by in scores.items()
        },
        "metrics_treated": metrics,
        "metrics_all_canonical": all_pop,
        "pb1_set_windows": pb1_set,
        "pb10": pb10,
        "pb11": pb11,
        "pb12": pb12,
    }
    timing["total_s"] = round(time.perf_counter() - t_all, 1)
    run_id = make_run_id("T-AGG-dev-prefreeze")
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    doc = {
        "run_id": run_id,
        "created_utc": started,
        "finished_utc": utc_now_iso(),
        "status": "DEVELOPMENT",
        "results_sha256": sha256_json(det),
        "provenance": provenance(
            {"s6_run": S6_RUN, "workers": workers, "cpu_count": os.cpu_count()}
        ),
        "results": det,
        "timing": timing,
    }
    (out / "results.json").write_text(
        json.dumps(doc, indent=1, default=float) + "\n", "utf-8", newline="\n"
    )
    (out / "prefreeze.md").write_text(tables(det), "utf-8", newline="\n")
    return {
        "run_id": run_id,
        "results_sha256": doc["results_sha256"],
        "timing": timing,
        "pb10": pb10["decision"],
        "pb12": pb12["decision"],
    }


def tables(det: dict[str, Any]) -> str:
    """Decision tables generated from the artefact (no hand-copied numbers)."""
    L: list[str] = [f"# Pre-freeze Class B (DEVELOPMENT, T) — {det['source_run']}", ""]
    p10 = det["pb10"]
    L += [
        "## P-B10 calibration (M1, canonical)",
        "",
        "| Calibrator | LL_u | LL | Brier | ECE | slope | exact 0 | sens@1FA | area |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c, m in p10["candidates"].items():
        L.append(
            f"| {c} | {m['ll_u']:.5f} | {m['log_loss']:.5f} | {m['brier']:.5f} | {m['ece']:.5f} "
            f"| {m['slope']:.3f} | {m['exact0']} | {m['sens_at_1fa']:.4f} | {m['partial_area']:.4f} |"  # noqa: E501
        )
    L += [
        "",
        f"R0 integrity: {p10['r0_integrity']} · canonical outcome: {p10['canonical_outcome']} · "
        f"R3 agreement {p10['r3_agreement']}/15 · **decision: {p10['decision']}**",
        "",
    ]
    for cal, block in det["pb11"]["calibrators"].items():
        if cal == "raw":
            continue
        L += [
            f"## P-B11 stability ({cal}, treated)",
            "",
            "| Model | sens@1FA mean ± SD [min, max] | area mean ± SD | log-loss mean ± SD |",
            "|---|---|---|---|",
        ]
        for name, s in block["summary"].items():
            a, b, c = s["sens_at_1fa"], s["partial_area"], s["log_loss"]
            L.append(
                f"| {name} | {a['mean']:.3f} ± {a['sd']:.3f} [{a['min']:.3f}, {a['max']:.3f}] | "
                f"{b['mean']:.3f} ± {b['sd']:.3f} | {c['mean']:.4f} ± {c['sd']:.4f} |"
            )
        L += [
            "",
            "| Contrast | first better / second better / ties (of 15) | median Δ | range | reading |",  # noqa: E501
            "|---|---|---|---|---|",
        ]
        for k, v in block["contrasts"].items():
            L.append(
                f"| {k} | {v['first_better']} / {v['second_better']} / {v['ties']} | "
                f"{v['median']:+.4f} | [{v['min']:+.4f}, {v['max']:+.4f}] | {v['reading']} |"
            )
        L += [
            "",
            "Rank frequency (sens@1FA, rank 1 = best): "
            + json.dumps(block["rank_frequency_sens1"]),
            "",
        ]
    p12 = det["pb12"]
    L += [
        f"## P-B12 LOW_CONFIDENCE (M3, {p12['calibrator']})",
        "",
        "| Candidate | rate | patients | BSS tagged | BSS untagged | separation [95% CI] | +configs | criteria |",  # noqa: E501
        "|---|---|---|---|---|---|---|---|",
    ]
    for c, d in p12["candidates"].items():
        bt, bu = d["tagged"].get("bss"), d["untagged"].get("bss")
        L.append(
            f"| {c} | {d['rate']:.3%} | {d['patients_affected']:.0%} | "
            f"{'—' if bt is None else f'{bt:.3f}'} | {'—' if bu is None else f'{bu:.3f}'} | "
            f"{d['separation_bss']:+.3f} [{d['separation_ci95'][0]:+.3f}, {d['separation_ci95'][1]:+.3f}] | "  # noqa: E501
            f"{d['separation_positive_configs']}/15 | {d['criteria']} |"
        )
    L += ["", f"**Decision: {p12['decision']}**", ""]
    return "\n".join(L) + "\n"
