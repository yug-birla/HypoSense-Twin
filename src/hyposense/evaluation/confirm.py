"""S9 confirmatory evaluation, run ONCE after freeze (Blueprint §15, Tables 20.2-20.4, §23.1;
ANALYSIS_PLAN §5 incl. §5.7 operational definitions).

Modes:
- `official`: verifies artifacts/freeze/FREEZE.json (`freeze.verify_freeze_record`), unlocks E
  (`data.dataset.unlock_sealed_partition`), refuses if an official run already exists, then runs
  every step below on E (training on T + (E minus fold k)).
  Output: experiments/runs/E-AGG-confirm-<ts>/.
- `rehearsal`: the IDENTICAL code on T only (folds over T, training on T minus fold k), without
  freeze or unlock. Output: experiments/runs/T-AGG-rehearsal-<ts>/, labelled REHEARSAL
  (development). It exists to exercise and debug S9 before E is opened; it is never evidence.

Steps: population (canonical modules) -> integrity check against the S4 tuning feature table ->
5 grouped folds -> fold fits (primary + SA6, SA7, SA8, P-B6, R3, R4) -> fold thresholds ->
pooled OOF -> primary + S1-S7 + SA1-SA9 + R1-R4 through the S5/S6 harness -> G5, H1 -> model
selection (§6) -> interpretation rows (Table 20.4) -> final model (all patients) -> fold bundles
for the replay demo -> demo cases (§23.1) -> results.json (aggregate) + private outputs.
Nothing is tuned, chosen or re-run on the basis of the results.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_bytes, sha256_file, sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.common.runtime import disable_power_throttling, single_threaded_math_env
from hyposense.evaluation import confirm_data as CD
from hyposense.evaluation import confirm_fit as CF
from hyposense.evaluation.bootstrap import paired_bootstrap
from hyposense.evaluation.data import EvalRecording
from hyposense.evaluation.devdata import DevData
from hyposense.evaluation.folds import grouped_folds
from hyposense.evaluation.m0_run import provenance
from hyposense.evaluation.metrics import (
    EventRules,
    curve,
    operating_point,
    patient_curves,
    select_threshold,
    sens_at_budget,
)
from hyposense.evaluation.s6_run import evaluate, model_sets
from hyposense.evaluation.s7_artifact import S6_RUN, frozen_params

F64 = npt.NDArray[np.float64]
LADDER = ("M1", "M2", "M3r", "M3")
LAB_FEATURES = (
    "hba1c_mmol_mol",
    "c_peptide_fasting_nmol_l",
    "egfr",
    "hba1c_mmol_mol_missing",
    "c_peptide_fasting_nmol_l_missing",
    "egfr_missing",
)
OFFICIAL_PREFIX = "E-AGG-confirm"
REHEARSAL_PREFIX = "T-AGG-rehearsal"
PRIVATE = REPO_ROOT / "data" / "processed" / "confirm"


class ConfirmRefused(RuntimeError):
    pass


# ---------------------------------------------------------------- pure rules (unit-tested)
def h1_supported(ci95: Sequence[float]) -> bool:
    """§5.1: H1 iff the lower bound of the 95 % paired interval of Δ > 0."""
    return bool(ci95[0] > 0)


def select_model(
    h1: bool, sens: dict[str, float], logloss: dict[str, float], m0_sens: float
) -> dict[str, Any]:
    """§6 (Blueprint §15; literal reading approved, DEC-2026-10-19-N), applied mechanically.
    Point estimates on E-treated; 'log-loss not worse' = <=; ties go to the simpler model (M2);
    M0 only if no learned model has a higher sens@1FA point estimate than M0."""
    steps = []
    if h1:
        chosen = "M3"
        steps.append("H1 supported -> M3")
    else:
        if sens["M3"] > sens["M2"] and logloss["M3"] <= logloss["M2"]:
            chosen = "M3"
            steps.append("H1 not supported; M3 higher sens@1FA and log-loss not worse -> M3")
        else:
            chosen = "M2"
            steps.append(
                "H1 not supported; M3 not (higher sens@1FA with log-loss not worse) -> M2 "
                "(simpler model; ties go to M2)"
            )
    if not any(sens[m] > m0_sens for m in LADDER):
        steps.append("no learned model beats M0 -> M0")
        chosen = "M0"
    return {"selected": chosen, "steps": steps}


def contrast_reading(ci95: Sequence[float], point: float) -> str:
    """§5.7 item 31: '≈' = the paired 95 % CI includes 0."""
    if ci95[0] > 0:
        return "first better (CI > 0)"
    if ci95[1] < 0:
        return "second better (CI < 0)"
    return "≈ (CI includes 0; point " + ("> 0" if point > 0 else "<= 0") + ")"


def interpretation_rows(c: dict[str, Any], learned_vs_m0: bool) -> list[str]:
    """Blueprint Table 20.4 rows whose conditions hold (≈ per §5.7 item 31)."""
    d, s3 = c["preview_M3-M2:sens1"], c.get("preview_M3-M2:logloss")
    rows: list[str] = []

    def incl(x: dict[str, Any]) -> bool:
        return bool(x["ci95"][0] <= 0 <= x["ci95"][1])

    if d["ci95"][0] > 0:
        m3r = c.get("C2b_M3-M3r:sens1")
        rows.append("Δ CI > 0; M3 ≈ M3r" if m3r and incl(m3r) else "Δ CI > 0")
    elif d["point"] > 0 and s3 and s3["point"] < 0:
        rows.append("Δ point estimate > 0, CI includes 0; S3 favours M3")
    elif incl(d) and (s3 is None or incl(s3)):
        rows.append("Δ ≈ 0; S3 ≈ 0")
    m21 = c.get("C1_M2-M1:sens1")
    if m21 and incl(m21):
        rows.append("M2 ≈ M1")
    if not learned_vs_m0:
        rows.append("Learned models ≤ M0")
    return rows or ["no Table 20.4 row matches exactly; reported as measured"]


def fa_at_sensitivity(F: F64, S: F64, target: float) -> float:
    """S2 (§5.7 item 9): FA/day where the first-crossing path first reaches S >= target, linearly
    interpolated between the bracketing grid points; NaN if never reached."""
    k = np.flatnonzero(target <= S)
    if not len(k):
        return math.nan
    i = int(k[0])
    if i == 0 or S[i] == target:
        return float(F[i])
    f0, s0 = float(F[i - 1]), float(S[i - 1])
    return f0 + (target - s0) * (float(F[i]) - f0) / (float(S[i]) - s0)


# ---------------------------------------------------------------- helpers
def _thresholds_task(args: tuple[list[EvalRecording], str, dict[str, Any]]) -> dict[str, Any]:
    recs, name, cfg_policy = args
    er = EventRules(**cfg_policy["rules"])
    c = curve(patient_curves(recs, name, False, er))
    a = select_threshold(c, float(cfg_policy["fa_budget_alert"]), "fa")
    w = select_threshold(c, float(cfg_policy["fa_budget_watch"]), "notifications")
    return {
        "tau_alert": a.tau_a,
        "tau_watch": min(w.tau_a, a.tau_a),
        "alert_budget_not_reached": a.budget_not_reached,
        "watch_budget_not_reached": w.budget_not_reached,
        "inner_sens_at_1fa": a.value,
    }


def _evaluate_task(args: tuple[Any, ...]) -> tuple[str, dict[str, Any]]:
    key, dev, scores, rules, B, seed, population = args
    return key, evaluate(dev, scores, EventRules(**rules), B, seed, set(population))


def _scores_to(dev: DevData, base: DevData, scores: dict[str, F64]) -> dict[str, F64]:
    """Re-index full-population score arrays onto a variant table that keeps a row subset."""
    out = {}
    key = pd.MultiIndex.from_frame(base.table[["recording_key", "ts"]])
    pos = pd.Series(np.arange(len(base.table)), index=key)
    idx = pos.loc[pd.MultiIndex.from_frame(dev.table[["recording_key", "ts"]])].to_numpy()
    for k, v in scores.items():
        out[k] = v[idx]
    return out


def _subset_dev(base: DevData, recs: list[EvalRecording], keep_rows: Any) -> DevData:
    table = base.table.loc[keep_rows].reset_index(drop=True)
    offsets, start = {}, 0
    for r in recs:
        n = len(r.ts)
        sub = table.iloc[start : start + n]
        rk = sub["recording_key"].to_numpy()
        if len(rk) != n or not (rk == r.recording_key).all():
            raise AssertionError("variant table misaligned with its recordings")
        offsets[r.recording_key] = (start, start + n)
        start += n
    return DevData(table, recs, offsets, base.strata, base.treated, base.provenance, {})


def _trim(r: EvalRecording, cut: int) -> EvalRecording | None:
    keep = r.ts >= cut
    if not keep.any():
        return None
    ok = r.onsets >= cut
    return replace(
        r,
        ts=r.ts[keep],
        gate_code=r.gate_code[keep],
        eligible=r.eligible[keep],
        onsets=r.onsets[ok],
        warnable=r.warnable[ok],
        first_ts=int(max(cut, r.first_ts)),
        scores={k: v[keep] for k, v in r.scores.items()},
    )


def _relabelled(pop: CD.Population, *, min_run: int | None = None, level2: bool = False) -> DevData:
    """S5 / SA1: episode set changes; eligibility, policy and models do not (§5.7 items 12, 15)."""
    from hyposense.labels.build import label_recording
    from hyposense.labels.config import LabelConfig
    from hyposense.labels.eligibility import warnable_onsets

    cfg = load_config()
    lc0 = LabelConfig.from_config(cfg)
    lc = replace(lc0, min_run=min_run) if min_run is not None else lc0
    recs = []
    for r in pop.dev.recs:
        lab0 = label_recording(pop.records[r.recording_key], lc0)
        lab = label_recording(pop.records[r.recording_key], lc)
        eps = lab.l2 if level2 else lab.l1
        on = np.array(sorted(e.onset_ts for e in eps), dtype=np.int64)
        recs.append(
            replace(
                r, onsets=on, warnable=warnable_onsets(lab0.prediction, on, lc0), notif_onsets=None
            )
        )
    return replace(pop.dev, recs=recs)


def _excluded(pop: CD.Population, which: str) -> DevData:
    """SA4 / SA5 / SA9 (§5.7 items 18-19)."""
    from hyposense.data.loader import cgm_series
    from hyposense.labels.annotations import annotate, floor_runs
    from hyposense.labels.build import label_recording
    from hyposense.labels.config import LabelConfig
    from hyposense.labels.validity import cbg_series, episode_cbg_status

    cfg = load_config()
    lc = LabelConfig.from_config(cfg)
    off = _utc_offset_s(cfg)
    recs = []
    for r in pop.dev.recs:
        rec = pop.records[r.recording_key]
        lab = label_recording(rec, lc)
        s = cgm_series(rec)
        runs = floor_runs(s.ts, s.value)
        drop = set()
        excl: list[tuple[int, int]] = []
        for e in lab.l1:
            if which == "SA4" and annotate(e, s.ts, s.value, off, runs).compression_candidate:
                drop.add(e.onset_ts)
            if which == "SA5":
                st = episode_cbg_status(
                    e,
                    cbg_series(rec),
                    int(cfg["gates"]["g3b"]["episode_cbg_tail_min"]) * 60,
                    lc.l1_threshold_mgdl,
                )
                if st is False:
                    drop.add(e.onset_ts)
            if which == "SA9" and annotate(e, s.ts, s.value, off, runs).sensor_floor_run:
                drop.add(e.onset_ts)
        if which == "SA9":
            excl = [(int(s.ts[a]), int(s.ts[b - 1])) for a, b in runs]
        keep = np.array([o not in drop for o in r.onsets.tolist()], dtype=bool)
        recs.append(
            replace(
                r,
                onsets=r.onsets[keep],
                warnable=r.warnable[keep],
                notif_onsets=r.onsets,
                notif_exclude=tuple(excl) if excl else None,
            )
        )
    return replace(pop.dev, recs=recs)


def _utc_offset_s(cfg: dict[str, Any]) -> int:
    s = str(cfg["time"]["assumed_utc_offset"])
    sign = -1 if s.startswith("-") else 1
    h, m = s.lstrip("+-").split(":")
    return sign * (int(h) * 3600 + int(m) * 60)


def _has_pump_or_iv(stream: Any) -> bool:
    from hyposense.medication.events import MedicationEvent

    return any(isinstance(e, MedicationEvent) and e.route in ("csii", "iv") for e in stream.events)


# ---------------------------------------------------------------- main
def run_confirm(
    mode: str,
    workers: int | None = None,
    freeze_path: Path | None = None,
    smoke_resamples: int | None = None,
) -> dict[str, Any]:
    """`smoke_resamples` (rehearsal ONLY) shortens the bootstrap for debugging; the official run
    always uses the frozen B."""
    if smoke_resamples is not None and mode != "rehearsal":
        raise ConfirmRefused("bootstrap overrides are refused outside the rehearsal")
    started = utc_now_iso()
    t_all = time.perf_counter()
    timing: dict[str, float] = {}
    cfg = load_config()
    disable_power_throttling()
    single_threaded_math_env()
    workers = workers or CD.default_workers()
    runs_dir = REPO_ROOT / "experiments" / "runs"
    freeze_record: dict[str, Any] | None = None
    from hyposense.data.dataset import (
        AccessScope,
        load_dataset,
        partition_labels,
        unlock_sealed_partition,
    )

    if mode == "official":
        from hyposense.freeze import FREEZE_JSON, verify_freeze_record

        if any(runs_dir.glob(f"{OFFICIAL_PREFIX}-*")):
            raise ConfirmRefused("an official confirmatory run already exists: S9 runs once")
        verified = verify_freeze_record(freeze_path or FREEZE_JSON)  # BEFORE any E access
        unlock_sealed_partition(verified)
        freeze_record = verified.record
        ds = load_dataset(AccessScope.ALL_AFTER_FREEZE)
        prefix = OFFICIAL_PREFIX
    elif mode == "rehearsal":
        ds = load_dataset(AccessScope.TUNING_ONLY)
        prefix = REHEARSAL_PREFIX
    else:
        raise ValueError(mode)
    run_id = make_run_id(prefix)
    private = PRIVATE / run_id
    private.mkdir(parents=True, exist_ok=False)
    part = partition_labels(ds)

    # ---- population + integrity against the S4 tuning feature table (T rows)
    a = time.perf_counter()
    pop = CD.assemble(ds.recordings, ds.summary, part, mode, workers)
    timing["population_s"] = round(time.perf_counter() - a, 1)
    integrity = _check_t_features(pop)
    t = pop.dev.table
    strata = pop.dev.strata
    seed = int(cfg["cv"]["seed"])
    evalp = list(pop.evaluation_patients)
    treated_eval = sorted(set(evalp) & pop.dev.treated)

    def folds_for(s: int) -> dict[str, int]:
        return grouped_folds(sorted(evalp), strata, int(cfg["cv"]["folds"]), s)

    params, rounds = frozen_params(cfg)
    sets = model_sets()
    r4 = _frozen_r4(freeze_record)

    def spec(name: str, level: str, **kw: Any) -> CF.FitSpec:
        feats = kw.pop("features", sets[level]["features"])
        return CF.FitSpec(
            name=name,
            level=level,
            features=tuple(feats),
            categorical=tuple(f for f in sets[level]["categorical"] if f in feats),
            params=kw.pop("params", params),
            rounds=kw.pop("rounds", rounds),
            **kw,
        )

    specs: list[tuple[CF.FitSpec, int]] = []  # (spec, fold seed)
    for m in LADDER:
        specs.append((spec(m, m, keep_model=m in ("M2", "M3")), seed))
    for f in (0.75, 1.5):
        specs.append((spec(f"SA6x{f}:M3", "M3", table=f"sa6_{f}"), seed))
    for s in cfg["sensitivity"]["fold_seeds_sa7"]:
        for m in ("M2", "M3"):
            specs.append((spec(f"SA7s{s}:{m}", m), int(s)))
    for m in ("M2", "M3"):
        nolab = tuple(x for x in sets[m]["features"] if x not in LAB_FEATURES)
        specs.append((spec(f"SA8:{m}", m, features=nolab), seed))
        specs.append((spec(f"PB6:{m}", m, pb6_training_mask=True), seed))
        specs.append((spec(f"R3:{m}", m, learner="lr"), seed))
    for m in ("M2", "M3r", "M3"):
        specs.append((spec(f"R4:{m}", m, params=r4["params"][m], rounds=r4["rounds"][m]), seed))

    # ---- input tables (base + SA6 rebuilt features)
    a = time.perf_counter()
    paths = {"base": private / "base.parquet"}
    t.to_parquet(paths["base"], index=False)
    for f in (0.75, 1.5):
        tf = CD.rebuild_features(pop, CD.scaled_pharma(f), workers)
        paths[f"sa6_{f}"] = private / f"sa6_{f}.parquet"
        tf.to_parquet(paths[f"sa6_{f}"], index=False)
    timing["sa6_features_s"] = round(time.perf_counter() - a, 1)

    # ---- fold fits
    tasks = []
    folds_by_seed = {s: folds_for(s) for s in {s for _, s in specs}}
    for sp, s in specs:
        outer = folds_by_seed[s]
        for k in sorted(set(outer.values())):
            test_p = {p for p, f in outer.items() if f == k}
            train_p = set(pop.always_train) | {p for p in evalp if p not in test_p}
            inner = grouped_folds(sorted(train_p), strata, int(cfg["cv"]["inner_folds"]), s)
            tasks.append((sp, k, train_p, test_p, inner))
    a = time.perf_counter()
    with ProcessPoolExecutor(
        workers,
        initializer=CF.init,
        initargs=({k: str(v) for k, v in paths.items()}, str(cfg["calibration"]["method"])),
    ) as pool:
        fits = list(pool.map(CF.task_fit, tasks, chunksize=1))
    timing["fits_s"] = round(time.perf_counter() - a, 1)
    timing["fit_tasks"] = len(tasks)

    n = len(t)
    scores: dict[str, F64] = {}
    raw_scores: dict[str, F64] = {}
    by_fold: dict[str, dict[int, dict[str, Any]]] = {}
    for fr in fits:
        scores.setdefault(fr["name"], np.full(n, np.nan))[fr["test_idx"]] = fr["test_p"]
        raw_scores.setdefault(fr["name"], np.full(n, np.nan))[fr["test_idx"]] = fr["test_raw"]
        by_fold.setdefault(fr["name"], {})[fr["fold"]] = fr
    eval_rows = t["patient_key"].isin(evalp).to_numpy()
    for sname, sv in scores.items():
        if np.isnan(sv[eval_rows]).any():
            raise AssertionError(f"{sname}: missing out-of-fold predictions")

    # ---- fold thresholds (primary ladder)
    pol = {
        "rules": {
            "horizon_s": int(cfg["event"]["horizon_min"]) * 60,
            "min_lead_s": int(cfg["event"]["min_lead_min"]) * 60,
            "cooldown_s": int(cfg["policy"]["cooldown_min"]) * 60,
        },
        "fa_budget_alert": cfg["policy"]["fa_budget_alert"],
        "fa_budget_watch": cfg["policy"]["fa_budget_watch"],
    }
    th_tasks, th_keys = [], []
    for m in LADDER:
        for k, r in sorted(by_fold[m].items()):
            inner_scores = np.full(n, np.nan)
            inner_scores[r["train_idx"]] = r["inner_p"]
            train_patients = set(t["patient_key"].to_numpy()[r["train_idx"]])
            recs = [
                rr.with_scores(
                    m,
                    inner_scores[
                        pop.dev.offsets[rr.recording_key][0] : pop.dev.offsets[rr.recording_key][1]
                    ],
                )
                for rr in pop.dev.recs
                if rr.patient_key in train_patients
            ]
            th_tasks.append((recs, m, pol))
            th_keys.append((m, k))
    a = time.perf_counter()
    with ProcessPoolExecutor(workers) as pool:
        ths = list(pool.map(_thresholds_task, th_tasks, chunksize=1))
    timing["thresholds_s"] = round(time.perf_counter() - a, 1)
    thresholds: dict[str, dict[int, dict[str, Any]]] = {}
    for (m, k), v in zip(th_keys, ths, strict=True):
        thresholds.setdefault(m, {})[k] = v
    fold_of = folds_by_seed[seed]

    # ---- perturbation variants (R1, R2) scored by the primary fold models
    import lightgbm as lgb

    from hyposense.calibration.methods import Calibrator
    from hyposense.features.spec import UNION_NAMES

    def fold_scorer(m: str, k: int) -> Any:
        fit_res = by_fold[m][k]
        booster = lgb.Booster(model_str=fit_res["model_text"])
        cal = Calibrator(fit_res["calibrator"]["method"], fit_res["calibrator"]["params"])
        feats = list(sets[m]["features"])
        idx = [list(UNION_NAMES).index(f) for f in feats]

        def score(X: F64) -> F64:
            raw = np.asarray(booster.predict(X[:, idx], num_threads=1), dtype=np.float64)
            out: F64 = cal.apply(raw)
            return out

        return score

    test_keys = [r.recording_key for r in pop.dev.recs if r.patient_key in set(evalp)]
    variants: dict[str, tuple[DevData, dict[str, F64]]] = {}
    a = time.perf_counter()
    for minutes in (30, 60):
        st = {
            rk: CD.jitter_doses(pop.streams[rk], minutes, seed + i)
            for i, rk in enumerate(test_keys)
        }
        res = CD.rebuild_streams(st, workers, reduced=False)
        sc = {m: scores[m].copy() for m in ("M2", "M3")}
        for rk in test_keys:
            feat = res[rk][0]
            lo, hi = pop.dev.offsets[rk]
            pk = str(t["patient_key"].iloc[lo])
            sc["M3"][lo:hi] = fold_scorer("M3", fold_of[pk])(feat.X)
        variants[f"R1_{minutes}min"] = (pop.dev, sc)
    for share in (0.1, 0.2):
        for blocks in (False, True):
            st = {
                k: CD.drop_cgm(pop.streams[k], share, blocks, seed + i)
                for i, k in enumerate(test_keys)
            }
            res = CD.rebuild_streams(st, workers, reduced=True)
            dev_r, sc_r = _reduced_variant(pop, test_keys, res, fold_of, fold_scorer)
            variants[f"R2_{'block' if blocks else 'random'}{int(share * 100)}"] = (dev_r, sc_r)
    timing["perturbations_s"] = round(time.perf_counter() - a, 1)

    # ---- evaluations (S5/S6 harness; B = 2000, seed 2027)
    B, bseed = int(smoke_resamples or cfg["bootstrap"]["resamples"]), int(cfg["bootstrap"]["seed"])
    rules = pol["rules"]
    rules30 = {**rules, "min_lead_s": 30 * 60}

    def sub(names: Sequence[str]) -> dict[str, F64]:
        return {nm: scores[nm] for nm in names}

    two = ("M2", "M3")
    jobs: list[tuple[Any, ...]] = [
        ("primary", pop.dev, sub(LADDER), rules, B, bseed, treated_eval),
        ("S6_all_patients", pop.dev, sub(LADDER), rules, B, bseed, evalp),
        ("S1_lead30", pop.dev, sub(two), rules30, B, bseed, treated_eval),
        ("S5_L2", _relabelled(pop, level2=True), sub(two), rules, B, bseed, treated_eval),
        (
            "SA1_single_reading",
            _relabelled(pop, min_run=1),
            sub(two),
            rules,
            B,
            bseed,
            treated_eval,
        ),
        ("SA4_compression", _excluded(pop, "SA4"), sub(two), rules, B, bseed, treated_eval),
        ("SA5_cbg_contradicted", _excluded(pop, "SA5"), sub(two), rules, B, bseed, treated_eval),
        ("SA9_sensor_floor", _excluded(pop, "SA9"), sub(two), rules, B, bseed, treated_eval),
    ]
    # SA2: drop the first 24 h
    recs2: list[EvalRecording] = []
    rows2 = np.zeros(n, dtype=bool)
    for erec in pop.dev.recs:
        rr = _trim(erec, erec.first_ts + 86400)
        if rr is not None:
            recs2.append(rr)
            lo, hi = pop.dev.offsets[erec.recording_key]
            rows2[lo:hi] = t["ts"].to_numpy()[lo:hi] >= erec.first_ts + 86400
    dev2 = _subset_dev(pop.dev, recs2, rows2)
    jobs.append(
        ("SA2_first24h", dev2, _scores_to(dev2, pop.dev, sub(two)), rules, B, bseed, treated_eval)
    )
    # SA3: no CSII / i.v. insulin recordings
    keep3 = [x for x in pop.dev.recs if not _has_pump_or_iv(pop.streams[x.recording_key])]
    rows3 = t["recording_key"].isin({x.recording_key for x in keep3}).to_numpy()
    dev3 = _subset_dev(pop.dev, keep3, rows3)
    jobs.append(
        ("SA3_no_pump_iv", dev3, _scores_to(dev3, pop.dev, sub(two)), rules, B, bseed, treated_eval)
    )
    for f in (0.75, 1.5):
        jobs.append(
            (
                f"SA6_x{f}",
                pop.dev,
                {"M2": scores["M2"], "M3": scores[f"SA6x{f}:M3"]},
                rules,
                B,
                bseed,
                treated_eval,
            )
        )
    for s in cfg["sensitivity"]["fold_seeds_sa7"]:
        jobs.append(
            (
                f"SA7_seed{s}",
                pop.dev,
                {m: scores[f"SA7s{s}:{m}"] for m in two},
                rules,
                B,
                bseed,
                treated_eval,
            )
        )
    for tag in ("SA8", "PB6", "R3"):
        jobs.append(
            (tag, pop.dev, {m: scores[f"{tag}:{m}"] for m in two}, rules, B, bseed, treated_eval)
        )
    jobs.append(
        (
            "R4",
            pop.dev,
            {m: scores[f"R4:{m}"] for m in ("M2", "M3r", "M3")},
            rules,
            B,
            bseed,
            treated_eval,
        )
    )
    for name, (dv, sc) in variants.items():
        jobs.append((name, dv, sc, rules, B, bseed, treated_eval))
    a = time.perf_counter()
    with ProcessPoolExecutor(workers) as pool:
        evaluated = dict(pool.map(_evaluate_task, jobs, chunksize=1))
    timing["evaluations_s"] = round(time.perf_counter() - a, 1)

    # ---- S2 (matched sensitivity FA difference), S7, deployed operating point
    er = EventRules(**rules)
    recs_t = [r for r in pop.dev.recs if r.patient_key in set(treated_eval)]
    pcs = {}
    for m in two:
        rs = [
            r.with_scores(
                m,
                scores[m][
                    pop.dev.offsets[r.recording_key][0] : pop.dev.offsets[r.recording_key][1]
                ],
            )
            for r in recs_t
        ]
        pcs[m] = patient_curves(rs, m, False, er)

    def s2_stat(w: F64) -> float:
        c2, c3 = curve(pcs["M2"], w), curve(pcs["M3"], w)
        if not (c2.n_episodes > 0 and c2.days > 0):
            return math.nan
        target = sens_at_budget(c2.fa_per_day, c2.sensitivity, c2.tau, 1.0).value
        return fa_at_sensitivity(c3.fa_per_day, c3.sensitivity, target) - fa_at_sensitivity(
            c2.fa_per_day, c2.sensitivity, target
        )

    s2_stat.patients = pcs["M2"].patients  # type: ignore[attr-defined]
    s2 = paired_bootstrap({"S2": s2_stat}, len(pcs["M2"].patients), B, bseed)
    deployed: dict[str, Any] = {}
    per_patient_private: dict[str, Any] = {}
    for m in LADDER:
        shifted = scores[m].copy()
        for p, k in fold_of.items():
            rows = t["patient_key"].to_numpy() == p
            shifted[rows] = scores[m][rows] - thresholds[m][k]["tau_alert"]
        rs = [
            r.with_scores(
                m,
                shifted[pop.dev.offsets[r.recording_key][0] : pop.dev.offsets[r.recording_key][1]],
            )
            for r in recs_t
        ]
        op = operating_point(rs, m, 0.0, False, er)
        per_patient_private[m] = op.pop("per_patient")
        deployed[m] = op

    # ---- primary decision, G5, selection, interpretation
    prim = evaluated["primary"]
    comp = prim["comparisons"]
    delta = comp["preview_M3-M2:sens1"]
    g5 = all(prim["intervals"][f"{m}:sens1"]["undefined_resamples"] == 0 for m in two)
    h1 = h1_supported(delta["ci95"]) if g5 else False
    sens = {m: prim["models"][m]["sens_at_1fa"] for m in LADDER}
    ll = {m: prim["models"][m]["window"]["log_loss"] for m in LADDER}
    m0_sens = prim["models"]["M0"]["sens_at_1fa"]
    selection = select_model(h1, sens, ll, m0_sens)
    learned_beat_m0 = any(sens[m] > m0_sens for m in LADDER)
    interp = interpretation_rows(comp, learned_beat_m0)

    # ---- final model (all patients) and fold bundles for the replay demo
    a = time.perf_counter()
    final = _final_artifacts(
        mode, run_id, pop, selection["selected"], by_fold, thresholds, fold_of, freeze_record
    )
    timing["final_model_s"] = round(time.perf_counter() - a, 1)
    cases = _demo_cases(pop, scores, thresholds, fold_of, treated_eval, er, seed)

    # ---- private outputs (row-level; never committed)
    oof = t[["patient_key", "recording_key", "ts", "eligible", "y"]].copy()
    for m in LADDER:
        oof[m] = scores[m]
        oof[f"{m}_raw"] = raw_scores[m]
    oof["fold"] = t["patient_key"].map(fold_of)
    oof.loc[eval_rows].to_parquet(private / "oof.parquet", index=False)
    (private / "per_patient.json").write_text(
        json.dumps(per_patient_private, default=float), "utf-8"
    )
    for tmp_path in paths.values():
        tmp_path.unlink(missing_ok=True)

    def strip(e: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in e.items() if k != "models"}
        out["models"] = {
            m: {k: v for k, v in row.items() if k != "operating_point"}
            | (
                {
                    "operating_point": {
                        k: v for k, v in row["operating_point"].items() if k != "per_patient"
                    }
                }
                if "operating_point" in row
                else {}
            )
            for m, row in e["models"].items()
        }
        return out

    det = {
        "status": "CONFIRMATORY"
        if mode == "official"
        else "REHEARSAL (development; never evidence)",
        "mode": mode,
        "freeze": None
        if freeze_record is None
        else {
            "freeze_id": freeze_record["freeze_id"],
            "record_sha256": freeze_record["record_sha256"],
            "source_commit": freeze_record["source_commit"],
        },
        "integrity": integrity,
        "population": {
            "evaluation_patients": len(evalp),
            "evaluation_treated": len(treated_eval),
            "training_always": len(pop.always_train),
            "episodes_treated": int(sum(len(r.onsets) for r in recs_t)),
            "readings": int(eval_rows.sum()),
        },
        "folds": {
            "seed": seed,
            "sizes": {
                str(k): sum(v == k for v in fold_of.values()) for k in sorted(set(fold_of.values()))
            },
        },
        "thresholds": {m: {str(k): v for k, v in th.items()} for m, th in thresholds.items()},
        "primary": {
            "endpoint": "sens@1FA, CGM-detected L1 episode, horizon 60 min, min lead 15 min",
            "population": "evaluation-partition treated patients",
            "M2_sens_at_1fa": sens["M2"],
            "M3_sens_at_1fa": sens["M3"],
            "delta": delta["point"],
            "delta_ci95": delta["ci95"],
            "undefined_resamples": delta["undefined_resamples"],
            "g5_pass": g5,
            "h1_supported": h1,
        },
        "evaluations": {k: strip(v) for k, v in evaluated.items()},
        "S2_matched_sensitivity_fa_delta": {
            "point": s2.point["S2"],
            "ci95": list(s2.ci95["S2"]),
            "undefined_resamples": s2.undefined_resamples["S2"],
        },
        "deployed_operating_point": deployed,
        "model_selection": selection,
        "interpretation_table_20_4": interp,
        "final_model": final,
        "demo_cases": cases,
    }
    timing["total_s"] = round(time.perf_counter() - t_all, 1)
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    doc = {
        "run_id": run_id,
        "created_utc": started,
        "finished_utc": utc_now_iso(),
        "status": det["status"],
        "results_sha256": sha256_json(det),
        "provenance": provenance(
            {
                "s6_run": S6_RUN,
                "workers": workers,
                "private_dir": private.relative_to(REPO_ROOT).as_posix(),
            }
        ),
        "results": det,
        "timing": timing,
    }
    (out / "results.json").write_text(
        json.dumps(doc, indent=1, default=float) + "\n", "utf-8", newline="\n"
    )
    return {
        "run_id": run_id,
        "results_sha256": doc["results_sha256"],
        "status": det["status"],
        "primary": det["primary"],
        "selection": selection,
        "timing": timing,
    }


# ---------------------------------------------------------------- pieces
def _check_t_features(pop: CD.Population) -> dict[str, Any]:
    """T rows of the S9 table must equal the S4 tuning feature table (same modules, same data)."""
    from hyposense.evaluation.devdata import load_dev
    from hyposense.features.spec import UNION_NAMES

    dev = load_dev()
    t = pop.dev.table
    tt = t[t["patient_key"].isin(set(dev.table["patient_key"]))].reset_index(drop=True)
    ref = dev.table.reset_index(drop=True)
    same_ids = tt[["recording_key", "ts"]].equals(ref[["recording_key", "ts"]])
    a = tt[list(UNION_NAMES)].to_numpy(np.float64)
    b = ref[list(UNION_NAMES)].to_numpy(np.float64)
    feats_equal = bool(same_ids and a.shape == b.shape and np.array_equal(a, b, equal_nan=True))
    labels_equal = bool(
        same_ids and tt["y"].equals(ref["y"]) and tt["eligible"].equals(ref["eligible"])
    )
    if not (feats_equal and labels_equal):
        raise AssertionError("S9 table T rows differ from the S4/S6 development table")
    return {"t_rows": len(tt), "features_equal_s4": True, "labels_equal_s6": True}


def _frozen_r4(freeze_record: dict[str, Any] | None) -> dict[str, Any]:
    runs = sorted((REPO_ROOT / "experiments" / "runs").glob("T-AGG-dev-r4-*"))
    if freeze_record is not None:
        want = freeze_record.get("r4_run")
        runs = [r for r in runs if r.name == want]
    if not runs:
        raise ConfirmRefused("no frozen R4 tuning run (hyposense dev r4)")
    doc = json.loads((runs[-1] / "results.json").read_text("utf-8"))
    if sha256_json(doc["results"]) != doc["results_sha256"] or doc["provenance"]["git"]["dirty"]:
        raise ConfirmRefused("R4 run fails its integrity check")
    from hyposense.models.lgbm import base_params

    cfg = load_config()
    lv = doc["results"]["levels"]
    return {
        "run_id": doc["run_id"],
        "params": {m: {**base_params(cfg), **v["params"]} for m, v in lv.items()},
        "rounds": {m: int(v["num_boost_round"]) for m, v in lv.items()},
    }


def _reduced_variant(
    pop: CD.Population, keys: list[str], res: dict[str, Any], fold_of: dict[str, int], scorer: Any
) -> tuple[DevData, dict[str, F64]]:
    """R2 (§5.7 item 25): decisions only at remaining readings; onsets, eligibility and monitored
    days from the full record."""
    t = pop.dev.table
    recs: list[EvalRecording] = []
    parts: list[pd.DataFrame] = []
    sc: dict[str, list[F64]] = {"M2": [], "M3": []}
    for r in pop.dev.recs:
        if r.recording_key not in res:
            continue
        f, (ts, codes), m0 = res[r.recording_key]
        pos = np.searchsorted(r.ts, ts)
        if not np.array_equal(r.ts[pos], ts):
            raise AssertionError("reduced readings are not a subset of the record")
        recs.append(replace(r, ts=ts, gate_code=codes, eligible=r.eligible[pos], scores={"M0": m0}))
        lo, _ = pop.dev.offsets[r.recording_key]
        parts.append(t.iloc[lo + pos])
        pk = r.patient_key
        sc["M2"].append(scorer("M2", fold_of[pk])(f.X))
        sc["M3"].append(scorer("M3", fold_of[pk])(f.X))
    table = pd.concat(parts, ignore_index=True)
    offsets, start = {}, 0
    for r in recs:
        offsets[r.recording_key] = (start, start + len(r.ts))
        start += len(r.ts)
    dev = DevData(table, recs, offsets, pop.dev.strata, pop.dev.treated, {}, {})
    return dev, {k: np.concatenate(v) for k, v in sc.items()}


def _final_artifacts(
    mode: str,
    run_id: str,
    pop: CD.Population,
    selected: str,
    by_fold: dict[str, dict[int, dict[str, Any]]],
    thresholds: dict[str, dict[int, dict[str, Any]]],
    fold_of: dict[str, int],
    freeze_record: dict[str, Any] | None,
) -> dict[str, Any]:
    """§5.7 item 29 (final model on all patients) and fold bundles (replay of held-out patients
    with their own fold model, Blueprint §15). Rehearsal writes only to the private directory."""
    from hyposense.calibration.methods import Calibrator
    from hyposense.evaluation.s7_artifact import build_artifact_from
    from hyposense.models.artifact import write_artifact
    from hyposense.policy.decide import PolicyRules, Thresholds

    cfg, pharma = load_config(), load_config("pharma.yaml")
    status = "CONFIRMATORY" if mode == "official" else "DEVELOPMENT"
    root = (
        (REPO_ROOT / "artifacts" / "models")
        if mode == "official"
        else (PRIVATE / run_id / "models")
    )
    root.mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {"selected": selected}
    if selected == "M0":
        out["note"] = "M0 selected: no learned final model is built"
        return out
    final = build_artifact_from(
        pop.dev,
        selected,
        root,
        f"{selected}-final-{run_id.split('-')[-1]}",
        status,
        {
            "confirm_run": run_id,
            "training_population": "all patients" if mode == "official" else "T",
            "freeze_id": None if freeze_record is None else freeze_record["freeze_id"],
        },
    )
    out["final"] = final
    bundles = {}
    for m in sorted({selected, "M2", "M3"}):
        mdir = root / f"{m}-folds-{run_id.split('-')[-1]}"
        files = {}
        for k, r in sorted(by_fold[m].items()):
            th = thresholds[m][k]
            man = write_artifact(
                mdir / f"fold-{k}",
                level=m,
                model_text=r["model_text"],
                calibrator=Calibrator(r["calibrator"]["method"], r["calibrator"]["params"]),
                thresholds=Thresholds(th["tau_alert"], th["tau_watch"]),
                rules=PolicyRules.from_config(cfg),
                status=status,
                cfg=cfg,
                pharma=pharma,
                provenance={"confirm_run": run_id, "fold": k},
            )
            files[str(k)] = man["files"]
        (mdir / "fold_map.json").write_text(
            json.dumps({p: k for p, k in sorted(fold_of.items())}, indent=1) + "\n", "utf-8"
        )
        bundles[m] = {
            "directory": mdir.relative_to(REPO_ROOT).as_posix(),
            "fold_files": files,
            "fold_map_sha256": sha256_file(mdir / "fold_map.json"),
        }
    out["fold_bundles"] = bundles
    return out


def _demo_cases(
    pop: CD.Population,
    scores: dict[str, F64],
    thresholds: dict[str, dict[int, dict[str, Any]]],
    fold_of: dict[str, int],
    treated_eval: list[str],
    er: EventRules,
    seed: int,
) -> dict[str, Any]:
    """§23.1 / §5.7 item 30: TP, FN, FP of M3 at fold-frozen τA; eligibility fixed in advance and
    independent of model outputs; shuffle with seed 2026; first eligible case per category."""
    from hyposense.evaluation.metrics import (
        FALSE,
        classify_notifications,
        episode_window_readings,
        notification_indices,
        passes,
    )

    cands: dict[str, list[tuple[str, int]]] = {"TP": [], "FN": [], "FP": []}
    for r in pop.dev.recs:
        if r.patient_key not in set(treated_eval):
            continue
        lo, hi = pop.dev.offsets[r.recording_key]
        s = scores["M3"][lo:hi]
        tau = thresholds["M3"][fold_of[r.patient_key]]["tau_alert"]
        alert = r.queried & passes(s, tau, False)
        for o in r.onsets.tolist():
            w = episode_window_readings(r, o, er)
            cands["TP" if alert[w].any() else "FN"].append((r.recording_key, int(o)))
        nidx = notification_indices(r.ts, alert, er.cooldown_s)
        c = classify_notifications(r.ts[nidx], r.onsets, r.last_ts, er.horizon_s)
        for tn in r.ts[nidx][c == FALSE].tolist():
            cands["FP"].append((r.recording_key, int(tn)))

    def eligible(key: str, ev: int) -> bool:
        r = next(x for x in pop.dev.recs if x.recording_key == key)
        if ev - r.first_ts < 86400:
            return False
        lo, hi = ev - 3 * 3600, ev + 3 * 3600
        ts = r.ts[(r.ts >= lo) & (r.ts <= hi)]
        if len(ts) < 2 or ts[0] - lo > 1200 or hi - ts[-1] > 1200 or np.any(np.diff(ts) > 1200):
            return False
        a, b = pop.dev.offsets[key]
        g = pop.dev.table["cgm"].to_numpy()[a:b][(r.ts >= lo) & (r.ts <= hi)]
        return bool(np.all(g > 40))

    rng = np.random.default_rng(seed)
    chosen: dict[str, Any] = {}
    for cat in ("TP", "FN", "FP"):
        items = sorted(cands[cat])
        order = rng.permutation(len(items)).tolist() if items else []
        pick = next((items[i] for i in order if eligible(*items[i])), None)
        chosen[cat] = (
            {"recording_key": pick[0], "event_ts": pick[1]}
            if pick
            else {"absent": f"no eligible {cat} case in the evaluation population"}
        )
    return {
        "seed": seed,
        "model": "M3",
        "rule": "ANALYSIS_PLAN §5.7 item 30 (Blueprint §23.1)",
        "candidates": {k: len(v) for k, v in cands.items()},
        "selected": chosen,
        "selection_code_sha256": sha256_bytes(Path(__file__).read_bytes()),
    }
