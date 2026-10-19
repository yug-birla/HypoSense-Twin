"""SYNTHETIC model artefacts for S7 tests: a small LightGBM on random data with the real feature
names of a level, written through the production writer. No patient data; never evidence."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from hyposense.calibration.methods import fit
from hyposense.features.spec import level_names
from hyposense.models.artifact import write_artifact
from hyposense.models.lgbm import base_params, train
from hyposense.policy.decide import PolicyRules, Thresholds
from tests.unit.state_helpers import CFG, PHARMA


def synthetic_artifact(
    out: Path, level: str = "M1", tau_alert: float = 0.5, tau_watch: float | None = 0.2
) -> Path:
    names = level_names(level)
    rng = np.random.default_rng(7)
    X = pd.DataFrame(rng.normal(100.0, 30.0, (600, len(names))), columns=list(names))
    # risk rises as CGM level falls, so synthetic streams produce every forecast state
    y = (X["cgm"] + rng.normal(0, 20, 600) < 90).astype(np.int64).to_numpy()
    params = {**base_params(CFG), "num_leaves": 4, "min_data_in_leaf": 20, "learning_rate": 0.1}
    m = train(X, y, params, 20)
    cal = fit("isotonic_interp_floored", m.predict(X), y)  # canonical (DEC-2026-10-19-M)
    write_artifact(
        out,
        level=level,
        model_text=m.model_text,
        calibrator=cal,
        thresholds=Thresholds(tau_alert, tau_watch),
        rules=PolicyRules.from_config(CFG),
        status="DEVELOPMENT",
        cfg=CFG,
        pharma=PHARMA,
        provenance={"synthetic": True},
    )
    return out
