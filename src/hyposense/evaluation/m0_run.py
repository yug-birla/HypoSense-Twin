"""`hyposense eval m0`: S5 M0 evaluation on the TUNING partition (OFFLINE; DEVELOPMENT only).

1. LEGACY REPRODUCTION (harness verification): figshare v2 (mirror-equivalent, 48/48 event
   values in S2), TUNING patients, decision times = label-eligible times (the executable spec's
   semantics). Compared with Blueprint Table A.2 (configs/reference/blueprint_m0_table_a2.yaml).
2. CANONICAL: official v5 TUNING, approved protocol semantics (ANALYSIS_PLAN §2-3: policy replay at
   every reading via policy.decide.gate). Outputs: full operating curve, sens@1FA by first crossing,
   τA / τW, partial area, operating points, and a paired patient-cluster bootstrap.
3. DECOMPOSITION: v5 with legacy semantics, and v2 with protocol semantics, at the Table A.2 θ.
   This separates data-version effects from semantics effects.

Every number is computed by `evaluation.metrics` / `evaluation.bootstrap`; nothing is retyped.
Status: EXPLORATORY / DEVELOPMENT (T only). Never confirmatory.
"""

from __future__ import annotations

import csv
import json
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from hyposense.common.config import REPO_ROOT, config_hash, load_config, load_yaml
from hyposense.common.hashing import sha256_file, sha256_json
from hyposense.common.provenance import environment, git_state, make_run_id, utc_now_iso
from hyposense.data.dataset import AccessScope, load_dataset, load_legacy_tuning
from hyposense.data.manifest import read_manifest
from hyposense.data.records import Recording
from hyposense.data.source import dataset_config
from hyposense.data.summary import SummaryTable
from hyposense.evaluation.bootstrap import (
    paired_bootstrap,
    partial_area_stat,
    sens_at_budget_stat,
    summary,
)
from hyposense.evaluation.data import (
    EvalRecording,
    as_label_eligible_decisions,
    build_eval_recording,
)
from hyposense.evaluation.metrics import (
    EventRules,
    curve,
    operating_point,
    partial_area,
    patient_curves,
    select_threshold,
)
from hyposense.evaluation.registry import registry_sha256
from hyposense.features.cgm import CGMFeatureConfig
from hyposense.features.spec import spec_sha256
from hyposense.labels.config import LabelConfig
from hyposense.medication.dictionary import load_dictionary
from hyposense.models.m0 import M0_STRICT, M0Scorer, tau_to_theta, theta_to_tau
from hyposense.policy.decide import PolicyRules
from hyposense.state.patient import EngineConfig
from hyposense.state.stream import recording_stream

MODEL = "M0"
REFERENCE = REPO_ROOT / "configs" / "reference" / "blueprint_m0_table_a2.yaml"
TREATED = REPO_ROOT / "artifacts" / "population" / "treated_patients.csv"
PLAN = REPO_ROOT / "docs" / "protocol" / "ANALYSIS_PLAN.md"
RESULT_SCHEMA_VERSION = "1.0.0"


def treated_patient_keys() -> set[str]:
    with TREATED.open(encoding="utf-8") as fh:
        return {
            f"shanghai_t2dm:{r['patient_id']}" for r in csv.DictReader(fh) if r["treated"] == "1"
        }


def eval_recordings(
    recordings: Sequence[Recording], summary: SummaryTable | None
) -> list[EvalRecording]:
    cfg, pharma = load_config(), load_config("pharma.yaml")
    engine = EngineConfig.from_config(cfg, pharma)
    rules = PolicyRules.from_config(cfg)
    lc = LabelConfig.from_config(cfg)
    d = load_dictionary()
    plaus = {k: (float(v[0]), float(v[1])) for k, v in cfg["features"]["static_plausible"].items()}
    scorer = M0Scorer(CGMFeatureConfig.from_config(cfg))
    out = []
    for rec in sorted(recordings, key=lambda r: r.identity.recording_key):
        key = rec.identity.recording_key
        row = (
            {str(c): v for c, v in summary.frame.loc[key].items()}
            if summary is not None and key in summary.frame.index
            else None
        )
        stream = recording_stream(rec, d, pharma["formulation_rules"], row, plaus)
        out.append(build_eval_recording(rec, stream, engine, rules, lc, {MODEL: scorer}))
    return out


def _r(x: Any, nd: int = 4) -> Any:
    if isinstance(x, float):
        return None if not np.isfinite(x) else round(x, nd)
    if isinstance(x, dict):
        return {k: _r(v, nd) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_r(v, nd) for v in x]
    return x


def table_rows(
    recs: Sequence[EvalRecording],
    thetas: Sequence[int],
    er: EventRules,
    treated: set[str],
    offset: float = 0.0,
) -> list[dict[str, Any]]:
    sub = {"treated": [r for r in recs if r.patient_key in treated], "all": list(recs)}
    rows = []
    for th in thetas:
        row: dict[str, Any] = {"theta": th}
        for name, rr in sub.items():
            o = operating_point(rr, MODEL, theta_to_tau(th + offset), M0_STRICT, er)
            row[name] = {
                k: o[k]
                for k in (
                    "episodes",
                    "hits",
                    "sensitivity",
                    "fa_per_day",
                    "monitored_days",
                    "notifications",
                    "alert_precision",
                    "lead_min",
                    "warnable_ceiling",
                )
            }
        rows.append(row)
    return rows


TIE_EPS = 1e-6  # mg/dL: separates an exact tie at theta from any distinct projection


def exact_ties(recs: Sequence[EvalRecording], theta: float) -> int:
    """Queried readings whose projection is exactly theta (score == -theta, exact arithmetic)."""
    return int(sum(int(np.sum(r.queried & (r.scores[MODEL] == -float(theta)))) for r in recs))


def compare(
    rows: list[dict[str, Any]],
    ref: dict[str, Any],
    tie_rows: list[dict[str, Any]],
    ties: dict[int, int],
) -> list[dict[str, Any]]:
    """Per theta:
    - MATCH: warned episodes, episodes and median lead equal, and FA/day equal at the
      reference's 2-dp precision.
    - EXPECTED DIFFERENCE (exact-tie resolution): not a match, readings with projection exactly
      theta exist, and every reference warned / FA value lies between the protocol value (exact
      tie: no alert, strict rule) and the tie-inclusive value (all exact ties alert). This is how
      the reference's float noise could resolve them (np.polyfit, ~1e-13).
    - UNEXPLAINED DIFFERENCE: anything else.
    """
    out = []
    for row, trow in zip(rows, tie_rows, strict=True):
        r = ref["rows"][row["theta"]]
        checks: dict[str, Any] = {}
        bracket = True
        for i, name in ((0, "treated"), (4, "all")):
            m, mt = row[name], trow[name]
            checks[name] = {
                "warned": [r[i], m["hits"]],
                "episodes": [ref["episodes"][name], m["episodes"]],
                "sensitivity": [r[i + 1], round(m["sensitivity"], 3)],
                "fa_per_day": [r[i + 2], round(m["fa_per_day"], 2)],
                "median_lead": [r[i + 3], m["lead_min"]["median"]],
                "days": [ref["days"][name], round(m["monitored_days"], 1)],
                "tie_inclusive": {
                    "warned": mt["hits"],
                    "fa_per_day": round(mt["fa_per_day"], 2),
                    "median_lead": mt["lead_min"]["median"],
                },
            }
            lo_w, hi_w = sorted((m["hits"], mt["hits"]))
            lo_f, hi_f = sorted((round(m["fa_per_day"], 2), round(mt["fa_per_day"], 2)))
            bracket &= lo_w <= r[i] <= hi_w and lo_f <= r[i + 2] <= hi_f
        ok = all(
            v[0] == v[1]
            for c in checks.values()
            for k, v in c.items()
            if k not in ("days", "tie_inclusive")
        )
        status = (
            "MATCH"
            if ok
            else "EXPECTED DIFFERENCE"
            if ties[row["theta"]] > 0 and bracket
            else "UNEXPLAINED DIFFERENCE"
        )
        out.append(
            {
                "theta": row["theta"],
                "status": status,
                "exact_ties_at_theta": ties[row["theta"]],
                "checks": checks,
            }
        )
    return out


def curve_rows(recs: Sequence[EvalRecording], er: EventRules, cap: float = 4.0) -> dict[str, Any]:
    pc = patient_curves(recs, MODEL, M0_STRICT, er)
    c = curve(pc)
    sa = select_threshold(c, 1.0, "fa")
    sw = select_threshold(c, 3.0, "notifications")
    tau_w = min(sw.tau_a, sa.tau_a)
    area, reached = partial_area(c.fa_per_day, c.sensitivity)
    over = np.flatnonzero(c.fa_per_day > cap)
    end = int(over[0]) + 1 if len(over) else len(c.tau)
    pts = [
        {
            "tau": float(c.tau[k]),
            "theta": float(tau_to_theta(c.tau[k])),
            "fa_per_day": float(c.fa_per_day[k]),
            "sensitivity": float(c.sensitivity[k]),
            "notifications_per_day": float(c.notif_per_day[k]),
        }
        for k in range(end)
    ]
    return {
        "pc": pc,
        "summary": {
            "grid_points": len(c.tau),
            "non_monotone_fa_steps": c.non_monotone_steps,
            "monitored_days": c.days,
            "episodes": c.n_episodes,
            "sens_at_1fa": sa.value,
            "first_crossing": {
                "a": sa.a,
                "k_star": sa.k_star,
                "f_a": sa.f_a,
                "s_a": sa.s_a,
                "budget_not_reached": sa.budget_not_reached,
                "k_star_is_1": sa.k_star_is_1,
            },
            "tau_alert": sa.tau_a,
            "theta_alert": tau_to_theta(sa.tau_a),
            "tau_watch": tau_w,
            "theta_watch": tau_to_theta(tau_w),
            "watch_band_empty": tau_w == sa.tau_a,
            "partial_area_0.5_2.0": area,
            "partial_area_hi_reached": reached,
        },
        "points": pts,
    }


def provenance(extra: dict[str, Any]) -> dict[str, Any]:
    cfg = load_config()
    lc = LabelConfig.from_config(cfg)
    plan_text = PLAN.read_text(encoding="utf-8")
    plan_version = plan_text.split("DRAFT ", 1)[1].split(" ")[0] if "DRAFT " in plan_text else "?"
    manifest = read_manifest(REPO_ROOT / dataset_config()["paths"]["manifest_json"])
    return {
        "git": git_state(),
        "environment": environment(),
        "config_sha256": config_hash(cfg),
        "partition_sha256": cfg["partition"]["sha256"],
        "label_config_sha256": lc.sha256,
        "analysis_plan_sha256": sha256_file(PLAN),
        "analysis_plan_version": plan_version,
        "metric_registry_sha256": registry_sha256(),
        "feature_spec_sha256": spec_sha256(cfg["features"]),
        "reference_sha256": sha256_file(REFERENCE),
        "treated_population_sha256": sha256_file(TREATED),
        "dataset_v5_files_sha256": manifest["files_sha256"],
        **extra,
    }


def run_m0(resamples: int | None = None) -> dict[str, Any]:
    cfg = load_config()
    er = EventRules.from_config(cfg)
    boot_cfg = cfg["bootstrap"]
    B = int(resamples or boot_cfg["resamples"])
    seed = int(boot_cfg["seed"])
    ref = load_yaml(REFERENCE)
    thetas = sorted(int(t) for t in ref["rows"])
    treated = treated_patient_keys()
    timings: dict[str, float] = {}
    started = utc_now_iso()

    t0 = time.perf_counter()
    legacy = load_legacy_tuning(2)
    v2 = eval_recordings(legacy.recordings, legacy.summary)
    ds = load_dataset(AccessScope.TUNING_ONLY)
    v5 = eval_recordings(ds.recordings, ds.summary)
    timings["build_eval_inputs_s"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    v2_legacy = as_label_eligible_decisions(v2)
    legacy_rows = table_rows(v2_legacy, thetas, er, treated)
    timings["table_a2_eval_s"] = time.perf_counter() - t0
    tie_rows = [table_rows(v2_legacy, [th], er, treated, offset=TIE_EPS)[0] for th in thetas]
    ties = {th: exact_ties(v2_legacy, th) for th in thetas}
    reproduction = compare(legacy_rows, ref, tie_rows, ties)

    decomposition = {
        "v5_legacy_semantics": table_rows(as_label_eligible_decisions(v5), thetas, er, treated),
        "v2_protocol_semantics": table_rows(v2, thetas, er, treated),
    }
    t0 = time.perf_counter()
    canonical_rows = table_rows(v5, thetas, er, treated)
    timings["one_threshold_eval_s"] = (time.perf_counter() - t0) / (2 * len(thetas))

    subsets = {"treated": [r for r in v5 if r.patient_key in treated], "all": v5}
    curves: dict[str, Any] = {}
    boots: dict[str, Any] = {}
    for name, rr in subsets.items():
        t0 = time.perf_counter()
        cr = curve_rows(rr, er)
        timings[f"curve_{name}_s"] = time.perf_counter() - t0
        pc = cr.pop("pc")
        th_a = cr["summary"]["theta_alert"]
        cr["operating_point_at_tau_alert"] = (
            operating_point(rr, MODEL, cr["summary"]["tau_alert"], M0_STRICT, er)
            if np.isfinite(th_a)
            else None
        )
        if cr["operating_point_at_tau_alert"] is not None:
            cr["operating_point_at_tau_alert"].pop("per_patient")
        curves[name] = cr
        t0 = time.perf_counter()
        b = paired_bootstrap(
            {"sens_at_1fa": sens_at_budget_stat(pc, 1.0), "partial_area": partial_area_stat(pc)},
            len(pc.patients),
            B,
            seed,
        )
        timings[f"bootstrap_{name}_s"] = time.perf_counter() - t0
        boots[name] = summary(b)

    per_patient = {
        name: operating_point(rr, MODEL, curves[name]["summary"]["tau_alert"], M0_STRICT, er)[
            "per_patient"
        ]
        if np.isfinite(curves[name]["summary"]["theta_alert"])
        else {}
        for name, rr in subsets.items()
    }
    deterministic = _r(
        {
            "status": "EXPLORATORY / DEVELOPMENT (tuning partition only; not confirmatory)",
            "model": {
                "id": MODEL,
                "version": M0Scorer.version,
                "strict": M0_STRICT,
                "score": "-projection(t+60); projection = g(t) + 60 x LS slope over "
                "(t-35 min, t], >= 3 readings (ANALYSIS_PLAN §0d)",
            },
            "event": {
                "definition": "L1 CGM-detected episode (ANALYSIS_PLAN §0)",
                "horizon_min": 60,
                "min_lead_min": 15,
                "cooldown_min": 60,
                "fa_budget_per_day": 1.0,
            },
            "population": {
                "v5": {
                    "recordings": len(v5),
                    "patients": len({r.patient_key for r in v5}),
                    "treated_patients": len({r.patient_key for r in subsets["treated"]}),
                    "readings": int(sum(len(r.ts) for r in v5)),
                    "label_eligible_times": int(sum(int(r.eligible.sum()) for r in v5)),
                    "policy_queried_readings": int(sum(int(r.queried.sum()) for r in v5)),
                },
                "v2": {"recordings": len(v2), "patients": len({r.patient_key for r in v2})},
            },
            "legacy_reproduction": {
                "data": "figshare v2, TUNING patients",
                "decision_times": "label-eligible (audit2.py)",
                "rows": legacy_rows,
                "comparison": reproduction,
                "summary": {
                    s: sum(1 for c in reproduction if c["status"] == s)
                    for s in ("MATCH", "EXPECTED DIFFERENCE", "UNEXPLAINED DIFFERENCE")
                },
            },
            "canonical_v5": {
                "decision_times": "policy replay (ANALYSIS_PLAN §2)",
                "table_a2_thetas": canonical_rows,
                "curves": curves,
                "bootstrap": boots,
            },
            "decomposition": decomposition,
        },
        6,
    )
    run_id = make_run_id("T-AGG-eval-m0")
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    prov = provenance(
        {
            "dataset_v2_tuning_files_sha256": sha256_json(legacy.files_sha256),
            "bootstrap": {"resamples": B, "seed": seed, "unit": "patient"},
        }
    )
    sha = sha256_json(deterministic)
    doc = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "run_id": run_id,
        "created_utc": started,
        "finished_utc": utc_now_iso(),
        "status": "EXPLORATORY",
        "partition": "T",
        "results_sha256": sha,
        "provenance": prov,
        "results": deterministic,
        "timing_s": _r(timings, 3),
    }
    (out / "results.json").write_text(
        json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    _write_tables(out, deterministic)
    private = REPO_ROOT / "data" / "processed" / "evaluation" / run_id
    private.mkdir(parents=True, exist_ok=True)
    (private / "per_patient_T.json").write_text(
        json.dumps(_r(per_patient), indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    return {
        "run_id": run_id,
        "results_sha256": sha,
        "git": prov["git"],
        "legacy_reproduction": deterministic["legacy_reproduction"]["summary"],
        "sens_at_1fa": {k: v["summary"]["sens_at_1fa"] for k, v in curves.items()},
        "timing_s": _r(timings, 3),
    }


def _write_tables(out: Path, det: dict[str, Any]) -> None:
    """Human-readable tables generated from the result document (never retyped)."""
    lines = [
        f"# M0 evaluation (S5) — {det['status']}",
        "",
        "## Legacy Table A.2 reproduction (v2, label-eligible decision times)",
        "",
        "| θ | status | warned T-treated ref/meas | FA/day treated ref/meas | lead ref/meas "
        "| warned all ref/meas | FA/day all ref/meas |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in det["legacy_reproduction"]["comparison"]:
        t, a = c["checks"]["treated"], c["checks"]["all"]
        lines.append(
            f"| {c['theta']} | {c['status']} | {t['warned'][0]}/{t['warned'][1]} | "
            f"{t['fa_per_day'][0]}/{t['fa_per_day'][1]} | {t['median_lead'][0]}/"
            f"{t['median_lead'][1]} | {a['warned'][0]}/{a['warned'][1]} | "
            f"{a['fa_per_day'][0]}/{a['fa_per_day'][1]} |"
        )
    lines += [
        "",
        "## Official v5 TUNING, protocol semantics (DEVELOPMENT; not confirmatory)",
        "",
        "| θ | sens treated | FA/day treated | precision treated | unknown | sens all | "
        "FA/day all |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in det["canonical_v5"]["table_a2_thetas"]:
        t, a = r["treated"], r["all"]
        lines.append(
            f"| {r['theta']} | {t['sensitivity']} | {t['fa_per_day']} | "
            f"{t['alert_precision']} | {t['notifications']['outcome_unknown']} | "
            f"{a['sensitivity']} | {a['fa_per_day']} |"
        )
    lines += ["", "## sens@1FA (first crossing) with patient-cluster bootstrap", ""]
    for name, cr in det["canonical_v5"]["curves"].items():
        s = cr["summary"]
        b = det["canonical_v5"]["bootstrap"][name]
        lines.append(
            f"- {name}: sens@1FA {s['sens_at_1fa']} (95% CI "
            f"{b['ci95']['sens_at_1fa']}), θA {s['theta_alert']} mg/dL, partial area "
            f"{s['partial_area_0.5_2.0']} (CI {b['ci95']['partial_area']}), "
            f"non-monotone FA steps {s['non_monotone_fa_steps']}"
        )
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    for name, cr in det["canonical_v5"]["curves"].items():
        with (out / f"m0_v5_curve_{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(cr["points"][0]), lineterminator="\n")
            w.writeheader()
            w.writerows(cr["points"])
