"""S4 feature audit (OFFLINE; TUNING partition only; aggregate output only).

Checks, all on T:
1. Determinism: two independent builds of the tuning feature table give identical hashes.
2. Offline vs replay parity: event-by-event replay through `PatientState.update` and
   `FeatureBuilder.snapshot(state, level)` for every level at every CGM reading, compared
   bitwise with the offline table.
3. Truncation equality at EVERY label-eligible prediction time: the raw recording is truncated at
   t (rows with ts <= t), passed through the full pipeline (adapter -> stream -> replay ->
   features), and compared bitwise with the full-record row.
4. Future perturbation (sample of eligible t): future CGM, future medication, future meal and a
   future outcome (an induced low in (t, t + 60]) are altered after t. The features at t must not
   change.
5. Causal episode tracker vs the offline label builder at every reading.
6. Distributions at label-eligible times, missingness, constants, impossible values, REQUIRED
   violations, redundancy (Spearman), within/between-patient variation, and a univariate AUC
   smell test for leakage (a sanity check, never feature selection).
7. Medication behaviour: event study around logged doses.
8. Performance and memory.

The labels package is imported here (offline audit), never by `state/` or `features/`.
"""

from __future__ import annotations

import math
import os
import sys
import time
import tracemalloc
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from dataclasses import replace
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from hyposense.common.config import load_config
from hyposense.common.runtime import disable_power_throttling, single_threaded_math_env
from hyposense.data.dataset import AccessScope, load_dataset
from hyposense.data.records import Recording
from hyposense.features.build import META_COLUMNS, RecordingFeatures, build_recording
from hyposense.features.export import frame_sha256
from hyposense.features.snapshot import LEVEL_INDEX, FeatureBuilder, FeatureInputs
from hyposense.features.spec import BY_NAME, LEVELS, UNION_NAMES, Group, Missing, level_names
from hyposense.labels.annotations import floor_runs
from hyposense.labels.build import label_recording
from hyposense.labels.config import LabelConfig
from hyposense.labels.episodes import EndReason
from hyposense.medication.dictionary import load_dictionary
from hyposense.medication.events import MedicationEvent
from hyposense.medication.timing import category
from hyposense.state.events import CGMReading
from hyposense.state.patient import EngineConfig, PatientState
from hyposense.state.stream import RecordingStream, recording_stream

SMELL_AUC = 0.95  # pre-set: a single feature this predictive at 60 min would suggest leakage

# ---------------------------------------------------------------- worker context
_W: dict[str, Any] = {}


def _init_worker() -> None:
    disable_power_throttling()  # S4: Windows EcoQoS confined the workers to the E-cores
    cfg, pharma = load_config(), load_config("pharma.yaml")
    ds = load_dataset(AccessScope.TUNING_ONLY)
    _W["cfg"] = cfg
    _W["rules"] = pharma["formulation_rules"]
    _W["d"] = load_dictionary()
    _W["plaus"] = {
        k: (float(v[0]), float(v[1])) for k, v in cfg["features"]["static_plausible"].items()
    }
    _W["engine"] = EngineConfig.from_config(cfg, pharma)
    _W["builder"] = FeatureBuilder(cfg)
    _W["recs"] = {r.identity.recording_key: r for r in ds.recordings}
    frame = ds.summary.frame
    _W["rows"] = {k: frame.loc[k].to_dict() for k in frame.index}


def _stream(rec: Recording) -> RecordingStream:
    key = rec.identity.recording_key
    return recording_stream(rec, _W["d"], _W["rules"], _W["rows"].get(key), _W["plaus"])


def truncate_recording(rec: Recording, t: int) -> Recording:
    """The raw recording truncated exactly at t: rows with a valid timestamp <= t."""
    f = rec.frame
    keep = f["ts_valid"].to_numpy(bool) & (f["ts"].fillna(2**62).to_numpy(np.int64) <= t)
    return replace(rec, frame=f.loc[keep].reset_index(drop=True))


def features_at(
    stream: RecordingStream, engine: EngineConfig, builder: FeatureBuilder, t: int | None = None
) -> npt.NDArray[np.float64]:
    """Union features at reading t (default: the stream's last reading), computed by replaying
    the stream through every event with ts <= t, exactly as the offline builder does there."""
    state = PatientState.start(stream.context, engine)
    for e in stream.events:
        if t is not None and e.ts > t:
            break
        state = state.update(e)
    if not state.at_cgm_reading or (t is not None and state.ts != t):
        raise AssertionError(f"no CGM reading at t={t}")
    out: npt.NDArray[np.float64] = builder.union(FeatureInputs.of(state))
    return out


def _features_at_end(rec: Recording) -> npt.NDArray[np.float64]:
    return features_at(_stream(rec), _W["engine"], _W["builder"])


def task_build(key: str) -> RecordingFeatures:
    return build_recording(_stream(_W["recs"][key]), _W["engine"], _W["builder"])


def task_parity(key: str) -> dict[str, int]:
    rec = _W["recs"][key]
    s = _stream(rec)
    offline = build_recording(s, _W["engine"], _W["builder"])
    state = PatientState.start(s.context, _W["engine"])
    k = 0
    comparisons = mismatches = 0
    for e in s.events:
        state = state.try_update(e)
        if state.error is not None:
            return {"comparisons": comparisons, "mismatches": -1}
        if not isinstance(e, CGMReading):
            continue
        for lvl in LEVELS:
            snap = _W["builder"].snapshot(state, lvl)
            comparisons += 1
            vals = snap.values  # noqa: PD011 - FeatureSnapshot.values is a numpy array
            if vals.tobytes() != offline.X[k, LEVEL_INDEX[lvl]].tobytes():
                mismatches += 1
        k += 1
    return {"comparisons": comparisons, "mismatches": mismatches}


def _diff(a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]) -> list[str]:
    bad = np.flatnonzero(a.view(np.uint64) != b.view(np.uint64))
    return [UNION_NAMES[i] for i in bad]


def task_truncation(args: tuple[str, list[int], npt.NDArray[np.float64]]) -> dict[str, Any]:
    key, times, expected = args
    rec = _W["recs"][key]
    mism: dict[str, int] = {}
    n_bad = 0
    for t, row in zip(times, expected, strict=True):
        got = _features_at_end(truncate_recording(rec, t))
        names = _diff(got, row)
        if names:
            n_bad += 1
            for nm in names:
                mism[nm] = mism.get(nm, 0) + 1
    return {"comparisons": len(times), "mismatches": n_bad, "features": mism}


PERTURBATIONS = ("future_cgm", "future_medication", "future_meal", "future_outcome")


def _perturb(rec: Recording, t: int, kind: str) -> Recording:
    f = rec.frame.copy()
    ts = f["ts"].fillna(2**62).to_numpy(np.int64)
    fut = f["ts_valid"].to_numpy(bool) & (ts > t)
    idx = np.flatnonzero(fut)
    if not len(idx):
        return rec
    if kind == "future_cgm":
        f.loc[fut & f["cgm"].notna().to_numpy(), "cgm"] = 300.6
    elif kind == "future_medication":
        f.loc[idx[0], "insulin_sc"] = "insulin aspart 70/30 30 IU"
        f.loc[idx[0], "oral_agents"] = "gliclazide 80 mg"
    elif kind == "future_meal":
        f.loc[idx[0], "diet_en"] = "rice 100 g"
        f.loc[idx[0], "diet_cn"] = "rice 100 g"
    elif kind == "future_outcome":
        window = fut & (ts <= t + 3600) & f["cgm"].notna().to_numpy()
        f.loc[window, "cgm"] = 50.4  # an induced L1 onset inside the label window
    return replace(rec, frame=f)


def _features_at(rec: Recording, t: int) -> npt.NDArray[np.float64]:
    """Features at t from the FULL (perturbed) record: future rows are present but unused."""
    return features_at(_stream(rec), _W["engine"], _W["builder"], t)


def task_perturbation(args: tuple[str, list[int], npt.NDArray[np.float64]]) -> dict[str, Any]:
    key, times, expected = args
    rec = _W["recs"][key]
    out: dict[str, Any] = {k: {"comparisons": 0, "mismatches": 0} for k in PERTURBATIONS}
    for t, row in zip(times, expected, strict=True):
        for kind in PERTURBATIONS:
            out[kind]["comparisons"] += 1
            if _diff(_features_at(_perturb(rec, t, kind), t), row):
                out[kind]["mismatches"] += 1
    return out


# ---------------------------------------------------------------- statistics (main process)
def _r(x: float | None, nd: int = 4) -> float | None:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return None
    return round(float(x), nd)


def _bounds(name: str, cfg: dict[str, Any]) -> tuple[float, float] | None:
    f = BY_NAME[name]
    plaus = cfg["features"]["static_plausible"]
    if f.dtype == "binary":
        return (0.0, 1.0)
    if f.dtype == "categorical":
        return (0.0, 5.0)
    if name in plaus:
        return (float(plaus[name][0]), float(plaus[name][1]))
    if name.startswith(("cgm_lag", "cgm_mean_")) or name in (
        "cgm",
        "cgm_min_2h",
        "cgm_min_6h",
        "cgm_min_24h",
    ):
        return (20.0, 600.0)
    if name == "cgm_pct_own":
        return (0.0, 100.0)
    if name in ("hour_sin", "hour_cos"):
        return (-1.0, 1.0)
    if name == "cgm_min_below80_24h":
        return (0.0, 1440.0)
    if "min_since" in name:
        return (0.0, 720.0 if name.startswith("meal") else 1440.0)
    if name.startswith(("act_", "iob", "insulin_p", "su_p", "glinide_p")) or name.endswith(
        ("_dose", "_dose_24h", "_per_kg", "rate_iu_h", "_sd_2h", "_sd_6h", "_sd_24h", "_cv_24h")
    ):
        return (0.0, math.inf)
    if f.dtype == "count":
        return (0.0, math.inf)
    return None


def _auc(x: npt.NDArray[np.float64], y: npt.NDArray[np.int8]) -> float | None:
    ok = np.isfinite(x)
    yy = y[ok]
    if ok.sum() < 50 or yy.min() == yy.max():
        return None
    r = pd.Series(x[ok]).rank().to_numpy()
    n1 = int(yy.sum())
    n0 = len(yy) - n1
    return float((r[yy == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def feature_statistics(
    df: pd.DataFrame, elig: npt.NDArray[np.bool_], y: npt.NDArray[np.int8], cfg: dict[str, Any]
) -> dict[str, Any]:
    e = df.loc[elig]
    pid = e["patient_key"].to_numpy()
    yy = y[elig]
    stats: dict[str, Any] = {}
    flags: dict[str, list[str]] = {
        "constant": [],
        "near_constant": [],
        "mostly_missing": [],
        "required_violation": [],
        "impossible_values": [],
        "no_within_patient_variation": [],
        "smell_auc": [],
    }
    for name in UNION_NAMES:
        v = e[name].to_numpy(np.float64)
        fin = v[np.isfinite(v)]
        f = BY_NAME[name]
        n_nan = int(len(v) - len(fin))
        s: dict[str, Any] = {
            "group": f.group.value,
            "n": len(v),
            "missing_share": _r(n_nan / len(v)) if len(v) else None,
            "zero_share": _r(float(np.mean(fin == 0))) if len(fin) else None,
            "unique": len(np.unique(fin)),
        }
        if len(fin):
            if f.group is Group.G5:  # ~34 recordings: extremes would be individual values
                s["p25_p50_p75"] = [_r(x) for x in np.percentile(fin, [25, 50, 75])]
            else:
                q = np.percentile(fin, [0, 1, 5, 25, 50, 75, 95, 99, 100])
                s["min_p1_p5_p25_p50_p75_p95_p99_max"] = [_r(x) for x in q]
            s["mean"] = _r(float(fin.mean())) if f.dtype != "categorical" else None
            top = float(pd.Series(fin).value_counts(normalize=True).iloc[0])
            s["top_value_share"] = _r(top)
            sub = pd.DataFrame({"p": pid, "v": v}).dropna()
            g = sub.groupby("p")["v"]
            within = g.std(ddof=0)
            s["patients_with_within_variation"] = int((within > 0).sum())
            s["patients_observed"] = int(g.ngroups)
            s["within_patient_sd_median"] = _r(float(within.median()))
            s["between_patient_sd_of_means"] = _r(float(g.mean().std(ddof=0)))
            s["univariate_auc"] = _r(_auc(v, yy), 3)
            if len(np.unique(fin)) == 1:
                flags["constant"].append(name)
            elif top > 0.99:
                flags["near_constant"].append(name)
            if s["patients_with_within_variation"] == 0 and len(np.unique(fin)) > 1:
                flags["no_within_patient_variation"].append(name)
            b = _bounds(name, cfg)
            if b is not None and (fin.min() < b[0] or fin.max() > b[1]):
                flags["impossible_values"].append(name)
            auc = s["univariate_auc"]
            if auc is not None and abs(auc - 0.5) >= SMELL_AUC - 0.5:
                flags["smell_auc"].append(name)
        else:
            flags["constant"].append(name)
        if len(v) and n_nan / len(v) > 0.9:
            flags["mostly_missing"].append(name)
        if f.missing is Missing.REQUIRED and n_nan:
            flags["required_violation"].append(name)
        stats[name] = s
    return {"features": stats, "flags": flags}


def redundancy(df: pd.DataFrame, elig: npt.NDArray[np.bool_]) -> dict[str, Any]:
    e = df.loc[elig, list(UNION_NAMES)]
    keep = [c for c in e.columns if len(np.unique(e[c].dropna().to_numpy())) > 1]
    ranks = e[keep].rank()
    rho = ranks.corr(min_periods=200)
    rv = rho.to_numpy()
    pos = {c: i for i, c in enumerate(rho.columns)}
    pairs = []
    cols = list(rho.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1 :]:
            r = rv[pos[a], pos[b]]
            if np.isfinite(r) and abs(r) >= 0.95:
                pairs.append({"a": a, "b": b, "spearman": _r(float(r), 3)})
    identical = []
    for i, a in enumerate(keep):
        va = e[a].to_numpy()
        for b in keep[i + 1 :]:
            if np.array_equal(va, e[b].to_numpy(), equal_nan=True):
                identical.append([a, b])
    g7 = [c for c in cols if BY_NAME[c].group is Group.G7]
    g8 = [c for c in cols if BY_NAME[c].group is Group.G8]
    m3_vs_m3r: dict[str, Any] = {}
    for a in g8:
        r7 = np.abs(np.array([rv[pos[a], pos[b]] for b in g7], dtype=np.float64))
        if np.isfinite(r7).any():
            j = int(np.nanargmax(r7))
            m3_vs_m3r[a] = {"best_g7": g7[j], "abs_spearman": _r(float(r7[j]), 3)}
    named = {}
    for a, b in (
        ("insulin_p60", "act_insulin_total"),
        ("insulin_p30", "act_insulin_total"),
        ("su_p60", "act_su"),
        ("act_insulin_total", "insulin_bolus_dose_24h"),
        ("act_su", "su_min_since_last"),
        ("cgm_m0_proj60", "cgm_slope30"),
        ("act_insulin_total", "act_insulin_total_per_kg"),
    ):
        if a in rho.index and b in rho.columns:
            named[f"{a}~{b}"] = _r(float(rv[pos[a], pos[b]]), 3)
    return {
        "pairs_abs_ge_0.95": pairs,
        "identical_columns": identical,
        "m3_feature_best_m3r_match": m3_vs_m3r,
        "named": named,
    }


def event_study(
    streams: Sequence[RecordingStream], parts: dict[str, RecordingFeatures]
) -> dict[str, Any]:
    """Median feature values around logged administrations (T): doses must raise exposure only
    after the dose time."""
    offsets = (-15, 0, 30, 60, 120, 240)
    col = {n: i for i, n in enumerate(UNION_NAMES)}
    res: dict[str, Any] = {}
    for label, cat, feats in (
        (
            "insulin_bolus_sc",
            "insulin_bolus",
            ("act_insulin_total", "iob_insulin", "insulin_bolus_min_since_last"),
        ),
        ("sulfonylurea", "su", ("act_su", "su_min_since_last")),
    ):
        vals: dict[str, dict[int, list[float]]] = {f: {o: [] for o in offsets} for f in feats}
        n = 0
        for s in streams:
            rf = parts[s.identity.recording_key]
            for e in s.events:
                if not isinstance(e, MedicationEvent) or category(e) != cat or e.route == "csii":
                    continue
                n += 1
                for o in offsets:
                    k = int(np.searchsorted(rf.ts, e.ts + o * 60))
                    if k < len(rf.ts) and abs(int(rf.ts[k]) - (e.ts + o * 60)) <= 420:
                        for f in feats:
                            vals[f][o].append(float(rf.X[k, col[f]]))
        res[label] = {
            "administrations": n,
            "median_by_offset_min": {
                f: {str(o): _r(float(np.nanmedian(v[o]))) if v[o] else None for o in offsets}
                for f, v in vals.items()
            },
        }
    return res


def tracker_agreement(
    recs: Sequence[Recording], parts: dict[str, RecordingFeatures], lc: LabelConfig
) -> dict[str, int]:
    k_onsets = UNION_NAMES.index("cgm_prior_l1_onsets")
    readings = mism = 0
    for r in recs:
        lab = label_recording(r, lc)
        rf = parts[r.identity.recording_key]
        assert np.array_equal(lab.series.ts, rf.ts)
        onset_idx = np.array([e.onset_index for e in lab.l1], dtype=np.int64)
        for k in range(len(rf.ts)):
            readings += 1
            if rf.X[k, k_onsets] != float(np.sum(onset_idx + 1 <= k)):
                mism += 1
        # causal "in episode" agrees with offline after confirmation lag
        live = np.zeros(len(rf.ts), dtype=bool)
        for e in lab.l1:
            end = (
                len(rf.ts)
                if e.end_reason is EndReason.RECORD_END
                else (e.end_index + 1 if e.end_reason is EndReason.RECOVERED else e.end_index)
            )
            live[e.onset_index + 1 : end] = True
        mism += int(np.sum(live != rf.meta["in_episode_causal"]))
    return {"readings": readings, "mismatches": mism}


# ---------------------------------------------------------------- orchestration
_T_START = time.perf_counter()


def _log(msg: str) -> None:
    """Progress on stderr (stdout carries the JSON summary)."""
    print(
        f"[audit features +{time.perf_counter() - _T_START:7.1f}s] {msg}",
        file=sys.stderr,
        flush=True,
    )


def _pmap(
    pool: ProcessPoolExecutor,
    fn: Callable[[Any], Any],
    items: Sequence[Any],
    phase: str,
    phases: dict[str, float],
) -> list[Any]:
    """pool.map with progress logging. Results come back in INPUT order (deterministic)."""
    t = time.perf_counter()
    futs: dict[Future[Any], int] = {pool.submit(fn, it): i for i, it in enumerate(items)}
    out: list[Any] = [None] * len(items)
    step = max(1, len(items) // 10)
    _log(f"{phase}: {len(items)} tasks submitted")
    for done, f in enumerate(as_completed(futs), start=1):
        out[futs[f]] = f.result()
        if done % step == 0 or done == len(items):
            _log(f"{phase}: {done}/{len(items)} done ({time.perf_counter() - t:.1f}s)")
    phases[phase] = round(time.perf_counter() - t, 1)
    return out


def run_feature_audit(
    workers: int | None = None, perturbation_sample: int = 300, seed: int = 2026
) -> dict[str, Any]:

    global _T_START
    _T_START = time.perf_counter()
    throttling_off = disable_power_throttling()
    single_threaded_math_env()  # inherited by the spawned workers (no BLAS oversubscription)
    phases: dict[str, float] = {}
    cfg = load_config()
    lc = LabelConfig.from_config(cfg)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    _log(f"start: {workers} workers, power throttling disabled={throttling_off}")
    ds = load_dataset(AccessScope.TUNING_ONLY)
    _init_worker()  # the main process also needs the context (streams, event study)
    keys = sorted(_W["recs"])
    t0 = time.perf_counter()
    with ProcessPoolExecutor(workers, initializer=_init_worker) as pool:
        build_a = dict(zip(keys, _pmap(pool, task_build, keys, "build_a", phases), strict=True))
        t_build = time.perf_counter() - t0
        build_b = dict(zip(keys, _pmap(pool, task_build, keys, "build_b", phases), strict=True))
        from hyposense.features.build import to_frame

        order = [k for k in keys]
        df_a = to_frame([build_a[k] for k in order])
        df_b = to_frame([build_b[k] for k in order])
        hash_a, hash_b = frame_sha256(df_a), frame_sha256(df_b)

        # labels (offline) aligned with the table
        elig_parts, y_parts = [], []
        floor_overlap = 0
        for k in order:
            lab = label_recording(_W["recs"][k], lc).prediction
            assert np.array_equal(lab.ts, build_a[k].ts)
            elig_parts.append(lab.eligible)
            y_parts.append(lab.y)
            runs = floor_runs(lab.ts, lab.value)
            if runs:
                starts = np.array([lab.ts[a] for a, _ in runs])
                ends = np.array([lab.ts[b - 1] for _, b in runs])
                t_el = lab.ts[lab.eligible]
                floor_overlap += int(
                    sum(np.any((starts <= t + 3600) & (ends > t)) for t in t_el.tolist())
                )
        elig = np.concatenate(elig_parts)
        y = np.concatenate(y_parts)

        # parity
        par = _pmap(pool, task_parity, keys, "parity", phases)
        parity = {
            "comparisons": sum(p["comparisons"] for p in par),
            "mismatches": sum(p["mismatches"] for p in par),
        }

        # truncation equality at EVERY eligible time
        tasks = []
        for k, el in zip(order, elig_parts, strict=True):
            rf = build_a[k]
            idx = np.flatnonzero(el)
            for c in range(0, len(idx), 60):
                ch = idx[c : c + 60]
                tasks.append((k, rf.ts[ch].tolist(), rf.X[ch]))
        t1 = time.perf_counter()
        tr = _pmap(pool, task_truncation, tasks, "truncation", phases)
        t_trunc = time.perf_counter() - t1
        trunc_feats: dict[str, int] = {}
        for x in tr:
            for nm, c in x["features"].items():
                trunc_feats[nm] = trunc_feats.get(nm, 0) + c
        truncation = {
            "comparisons": sum(x["comparisons"] for x in tr),
            "mismatches": sum(x["mismatches"] for x in tr),
            "mismatching_features": dict(sorted(trunc_feats.items())),
            "wall_seconds": _r(t_trunc, 1),
        }

        # future perturbation on a seeded sample of eligible times
        rng = np.random.default_rng(seed)
        all_el = [
            (k, i)
            for k, el in zip(order, elig_parts, strict=True)
            for i in np.flatnonzero(el).tolist()
        ]
        pick = sorted(
            rng.choice(
                len(all_el), size=min(perturbation_sample, len(all_el)), replace=False
            ).tolist()
        )
        by_key: dict[str, list[int]] = {}
        for p in pick:
            k, i = all_el[p]
            by_key.setdefault(k, []).append(i)
        ptasks = [(k, build_a[k].ts[ix].tolist(), build_a[k].X[ix]) for k, ix in by_key.items()]
        pres = _pmap(pool, task_perturbation, ptasks, "perturbation", phases)
        perturbation = {
            kind: {
                "comparisons": sum(p[kind]["comparisons"] for p in pres),
                "mismatches": sum(p[kind]["mismatches"] for p in pres),
            }
            for kind in PERTURBATIONS
        }

    _log("statistics, redundancy, event study, tracker agreement (main process)")
    t2 = time.perf_counter()
    streams = {k: _stream(_W["recs"][k]) for k in order}
    stats = feature_statistics(df_a, elig, y, cfg)
    red = redundancy(df_a, elig)
    evs = event_study([streams[k] for k in order], build_a)
    trk = tracker_agreement([_W["recs"][k] for k in order], build_a, lc)
    phases["statistics"] = round(time.perf_counter() - t2, 1)

    # performance (single-threaded per recording, measured inside workers)
    upd = sum(p.seconds["update"] for p in build_a.values())
    fea = sum(p.seconds["features"] for p in build_a.values())
    nev = sum(p.seconds["events"] for p in build_a.values())
    nrd = len(df_a)
    longest = max(order, key=lambda k: len(streams[k].events))
    tracemalloc.start()
    s = PatientState.start(streams[longest].context, _W["engine"])
    for ev in streams[longest].events:
        s = s.update(ev)
        if isinstance(ev, CGMReading):
            _W["builder"].union(FeatureInputs.of(s))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    positives = int((y[elig] == 1).sum())
    level_sizes = {lvl: len(level_names(lvl)) for lvl in LEVELS}
    episodes_t = sum(len(label_recording(_W["recs"][k], lc).l1) for k in order)
    meta_counts = {c: int(df_a[c].sum()) for c in META_COLUMNS}
    deterministic = {
        "scope": ds.scope.value,
        "recordings": len(order),
        "patients": len({build_a[k].patient_key for k in order}),
        "readings": nrd,
        "eligible_rows": int(elig.sum()),
        "eligible_positive_rows": positives,
        "l1_episodes_T": episodes_t,
        "eligible_rows_with_label_window_overlapping_floor_run": floor_overlap,
        "level_sizes": level_sizes,
        "table_sha256": hash_a,
        "determinism_two_builds_identical": hash_a == hash_b,
        "parity": parity,
        "truncation": {k: v for k, v in truncation.items() if k != "wall_seconds"},
        "perturbation": perturbation,
        "tracker_vs_label_builder": trk,
        "metadata_counts": meta_counts,
        "statistics": stats,
        "redundancy": red,
        "event_study": evs,
    }
    timing = {
        "workers": workers,
        "power_throttling_disabled": throttling_off,
        "phase_wall_seconds": phases,
        "total_wall_seconds": _r(time.perf_counter() - _T_START, 1),
        "build_wall_seconds": _r(t_build, 1),
        "truncation_wall_seconds": truncation["wall_seconds"],
        "update_us_per_event": _r(upd / nev * 1e6, 1),
        "features_ms_per_reading": _r(fea / nrd * 1e3, 3),
        "combined_ms_per_reading": _r((upd + fea) / nrd * 1e3, 3),
        "events": int(nev),
        "longest_recording_events": len(streams[longest].events),
        "replay_peak_traced_memory_mb": _r(peak / 2**20, 2),
        "table_memory_mb": _r(df_a.memory_usage(deep=True).sum() / 2**20, 1),
    }
    return {"deterministic": deterministic, "timing": timing, "table": df_a}
