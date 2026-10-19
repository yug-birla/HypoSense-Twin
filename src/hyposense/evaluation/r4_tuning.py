"""R4 (Blueprint Table 20.3; ANALYSIS_PLAN §5.7 item 27): per-model hyperparameter tuning for
M2, M3r and M3, on the TUNING partition only and BEFORE freeze, with exactly the S6 M1 procedure
(`s6_run.tune_m1`, Optuna TPE seed 2026, same space and trial count, 4 grouped inner folds).
The resulting parameters are frozen and used only by the confirmatory R4 robustness analysis.

Output: experiments/runs/T-AGG-dev-r4-<ts>/results.json (DEVELOPMENT; aggregate only).
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from hyposense.common.config import REPO_ROOT, load_config
from hyposense.common.hashing import sha256_json
from hyposense.common.provenance import make_run_id, utc_now_iso
from hyposense.common.runtime import disable_power_throttling, single_threaded_math_env
from hyposense.evaluation import s6_run
from hyposense.evaluation.devdata import load_dev, save_inputs
from hyposense.evaluation.m0_run import provenance

R4_LEVELS = ("M2", "M3r", "M3")


def run_r4(workers: int = 4) -> dict[str, Any]:
    started = utc_now_iso()
    t0 = time.perf_counter()
    cfg = load_config()
    disable_power_throttling()
    single_threaded_math_env()
    dev = load_dev()
    save_inputs(dev, s6_run.INPUTS)
    out: dict[str, Any] = {}
    with ProcessPoolExecutor(workers, initializer=s6_run._init) as pool:
        for level in R4_LEVELS:
            a = time.perf_counter()
            tuned = s6_run.tune_m1(pool, dev, cfg, level=level)
            best = tuned["best"]
            out[level] = {
                "best_trial": best["number"],
                "params": {k: tuned["params"][k] for k in cfg["model"]["search_space"]},
                "num_boost_round": tuned["num_boost_round"],
                "cv_logloss": best["objective"],
                "cv_logloss_sd": best["objective_sd"],
                "trials": [
                    {"number": t["number"], "params": t["params"], "objective": t["objective"]}
                    for t in tuned["trials"]
                ],
                "seconds": round(time.perf_counter() - a, 1),
            }
    det = {
        "status": "DEVELOPMENT (R4 parameters, frozen before E)",
        "partition": "T",
        "procedure": "s6_run.tune_m1 (Optuna TPE, seed model.seed, config search_space)",
        "levels": out,
    }
    run_id = make_run_id("T-AGG-dev-r4")
    d = REPO_ROOT / "experiments" / "runs" / run_id
    d.mkdir(parents=True, exist_ok=False)
    doc = {
        "run_id": run_id,
        "created_utc": started,
        "finished_utc": utc_now_iso(),
        "status": "DEVELOPMENT",
        "results_sha256": sha256_json(det),
        "provenance": provenance({"workers": workers, "cpu_count": os.cpu_count()}),
        "results": det,
        "timing": {"total_s": round(time.perf_counter() - t0, 1)},
    }
    (d / "results.json").write_text(json.dumps(doc, indent=1) + "\n", "utf-8", newline="\n")
    return {
        "run_id": run_id,
        "results_sha256": doc["results_sha256"],
        **{
            k: {"num_boost_round": v["num_boost_round"], "cv_logloss": v["cv_logloss"]}
            for k, v in out.items()
        },
    }
