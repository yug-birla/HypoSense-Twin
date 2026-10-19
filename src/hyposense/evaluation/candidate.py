"""Freeze-candidate workflow on T (DEC-2026-10-19-M; E sealed). Run twice on one clean commit;
every deterministic output must be identical before a freeze may be attempted.

1. Integrity gate: the canonical S6 configuration (fold seed 2026, model seed 2026, full-precision
   hyperparameters, 113 rounds) refits every S6 model, and the S6 `isotonic_interp` OOF scores are
   reproduced bitwise (the S6 `oof_sha256`).
2. Canonical T evaluation: the same fits with the canonical calibrator (`calibration.method`),
   ladder M0, M1, M2, M3r, M3 on treated and all patients through the S5/S6 harness, compared
   with the S6 values. The CGM-level reference is reported as POST-HOC (P-C9).
3. Candidate artefact: `build_dev_artifact` with the canonical calibrator (format 2).
4. Replay: every T recording replayed through the candidate artefact (sessions of <= 12), with
   the decision-log SHA-256 per session and the count of states.

Output: experiments/runs/T-AGG-candidate-<ts>/results.json; artefact
artifacts/models/M3-candidate-<ts>/.
"""

from __future__ import annotations

import json
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_bytes, sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.common.runtime import disable_power_throttling, single_threaded_math_env
from hyposense.evaluation import s6_run
from hyposense.evaluation.devdata import load_dev
from hyposense.evaluation.folds import grouped_folds
from hyposense.evaluation.m0_run import provenance
from hyposense.evaluation.metrics import EventRules
from hyposense.evaluation.prefreeze import _metrics, task_fit
from hyposense.evaluation.s7_artifact import S6_RUN, build_dev_artifact, frozen_params, frozen_s6

LADDER = ("M1", "M2", "M3r", "M3")


def run_candidate(workers: int = 4) -> dict[str, Any]:
    started = utc_now_iso()
    t_all = time.perf_counter()
    cfg = load_config()
    disable_power_throttling()
    single_threaded_math_env()
    er = EventRules.from_config(cfg)
    canonical_cal = str(cfg["calibration"]["method"])
    s6 = frozen_s6()
    params, rounds = frozen_params(cfg)
    seed = int(cfg["model"]["seed"])
    dev = load_dev()
    from hyposense.evaluation.devdata import save_inputs

    save_inputs(dev, s6_run.INPUTS)
    sets = s6_run.model_sets()
    outer = grouped_folds(sorted(dev.strata), dev.strata, int(cfg["cv"]["folds"]), seed)
    tasks = []
    for name in sorted(sets):
        for k in sorted(set(outer.values())):
            train_p = {p for p, f in outer.items() if f != k}
            test_p = {p for p, f in outer.items() if f == k}
            inner = grouped_folds(sorted(train_p), dev.strata, int(cfg["cv"]["inner_folds"]), seed)
            tasks.append(
                (
                    (seed, seed),
                    name,
                    sets[name],
                    {**params, "seed": seed},
                    rounds,
                    train_p,
                    test_p,
                    inner,
                )
            )
    timing: dict[str, Any] = {}
    a = time.perf_counter()
    with ProcessPoolExecutor(workers, initializer=s6_run._init) as pool:
        results = list(pool.map(task_fit, tasks, chunksize=2))
    timing["fits_s"] = round(time.perf_counter() - a, 1)
    n = len(dev.table)
    scores: dict[str, dict[str, Any]] = {}
    for r in results:
        sc = scores.setdefault(r["name"], {})
        for c, v in r["cal"].items():
            sc.setdefault(c, np.full(n, np.nan))[r["idx"]] = v
    gate = sha256_bytes(
        np.ascontiguousarray(
            np.column_stack([scores[m]["isotonic_interp"] for m in sorted(scores)])
        ).tobytes()
    )
    if gate != s6["results"]["oof_sha256"]:
        raise RuntimeError("integrity gate failed: the S6 fits are not reproduced bitwise")

    # ---- canonical T evaluation (ladder with the canonical calibrator) vs S6
    pops = {"treated": dev.treated & set(dev.strata), "all": set(dev.strata)}
    lad = s6["results"]["ladder"]
    evaluation: dict[str, Any] = {}
    for pop, pset in pops.items():
        rows: dict[str, Any] = {}
        for m in LADDER:
            new = _metrics(dev, scores[m][canonical_cal], m, pset, er)
            old = lad[pop]["models"][m]
            rows[m] = {
                "candidate": new,
                "s6": {
                    "sens_at_1fa": old["sens_at_1fa"],
                    "partial_area": old["partial_area"],
                    "log_loss": (old.get("window") or {}).get("log_loss"),
                    "ece": (old.get("calibration") or {}).get("ece"),
                },
                "delta_sens_at_1fa": new["sens_at_1fa"] - old["sens_at_1fa"],
                "delta_partial_area": new["partial_area"] - old["partial_area"],
            }
        rows["M0"] = {
            "s6": {"sens_at_1fa": lad[pop]["models"]["M0"]["sens_at_1fa"]},
            "note": "no probabilities; unaffected by the calibrator",
        }
        ref = s6["results"]["diagnostic_simple_rules"].get(f"{pop}:level_-cgm")
        rows["CGM_level_reference"] = {
            "status": "POST-HOC DEVELOPMENT REFERENCE (P-C9; not pre-specified; not retuned)",
            **(
                {"sens_at_1fa": ref["sens_at_1fa"], "alert_below_mgdl": -ref["tau_alert"]}
                if ref
                else {}
            ),
        }
        evaluation[pop] = rows
    treated = evaluation["treated"]
    delta_m3_m2 = {
        "candidate": treated["M3"]["candidate"]["sens_at_1fa"]
        - treated["M2"]["candidate"]["sens_at_1fa"],
        "s6": treated["M3"]["s6"]["sens_at_1fa"] - treated["M2"]["s6"]["sens_at_1fa"],
    }

    # ---- candidate artefact
    a = time.perf_counter()
    run_id = make_run_id("T-AGG-candidate")
    art = build_dev_artifact("M3", name=f"M3-candidate-{run_id.split('-')[-1]}")
    timing["artifact_s"] = round(time.perf_counter() - a, 1)
    art_dir = REPO_ROOT / art["directory"]
    manifest = json.loads((art_dir / "manifest.json").read_text("utf-8"))

    # ---- full-T replay through the candidate artefact
    from hyposense.api.service import load_tuning_streams
    from hyposense.features.snapshot import FeatureBuilder
    from hyposense.models.artifact import load_artifact
    from hyposense.replay.runner import Pipeline
    from hyposense.replay.session import DecisionLog, ReplaySession
    from hyposense.state.patient import EngineConfig

    pharma = load_config("pharma.yaml")
    model = load_artifact(art_dir, cfg, pharma)
    pipe = Pipeline(EngineConfig.from_config(cfg, pharma), FeatureBuilder(cfg), model)
    streams = load_tuning_streams(cfg, pharma)
    groups = [streams[i : i + 12] for i in range(0, len(streams), 12)]
    log_hashes: list[str] = []
    states: Counter[str] = Counter()
    tags: Counter[str] = Counter()
    notifications = 0
    a = time.perf_counter()
    with tempfile.TemporaryDirectory() as tmp:
        for g, sel in enumerate(groups):
            log = DecisionLog(Path(tmp) / f"g{g}", {"group": g})
            s = ReplaySession(sel, pipe, log)
            s.step(10**7)
            log_hashes.append(log.sha256())
            log.close()
            for runner in s.runners:
                for x in runner.decisions:
                    states[x.decision.state.value] += 1
                    notifications += int(x.decision.notify)
                    for tg in x.decision.tags:
                        tags[tg.split(":")[0]] += 1
    timing["replay_s"] = round(time.perf_counter() - a, 1)

    det = {
        "status": "DEVELOPMENT (freeze candidate; T only)",
        "partition": "T",
        "source_run": S6_RUN,
        "integrity_gate": {"oof_sha256": gate, "matches_s6": True},
        "canonical": {
            "model": "M3 (full; 100 features)",
            "calibrator": canonical_cal,
            "hyperparameters": {k: params[k] for k in sorted(params)},
            "num_boost_round": rounds,
            "model_seed": seed,
            "fold_seed": seed,
            "pb6_exclusion": False,
        },
        "evaluation": evaluation,
        "delta_m3_m2_treated": delta_m3_m2,
        "artifact": {
            "files": manifest["files"],
            "compatibility": manifest["compatibility"],
            "format_version": manifest["format_version"],
            "model_version": manifest["model_version"],
            "tau_alert": art["tau_alert"],
            "tau_watch": art["tau_watch"],
            "calibrator_p_lo": json.loads((art_dir / "calibrator.json").read_text("utf-8"))[
                "params"
            ]["p_lo"],
        },
        "replay": {
            "sessions": len(groups),
            "decision_log_sha256": log_hashes,
            "states": dict(sorted(states.items())),
            "tags": dict(sorted(tags.items())),
            "notifications": notifications,
        },
    }
    timing["total_s"] = round(time.perf_counter() - t_all, 1)
    out = REPO_ROOT / "experiments" / "runs" / run_id
    out.mkdir(parents=True, exist_ok=False)
    doc = {
        "run_id": run_id,
        "created_utc": started,
        "finished_utc": utc_now_iso(),
        "status": "DEVELOPMENT",
        "results_sha256": sha256_json(det),
        "provenance": provenance({"s6_run": S6_RUN, "artifact_directory": art["directory"]}),
        "results": det,
        "timing": timing,
    }
    (out / "results.json").write_text(
        json.dumps(doc, indent=1, default=float) + "\n", "utf-8", newline="\n"
    )
    return {
        "run_id": run_id,
        "results_sha256": doc["results_sha256"],
        "artifact": art["directory"],
        "timing": timing,
    }
