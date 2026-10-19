"""Fold fitting for the confirmatory run (ANALYSIS_PLAN §5.7 items 2-4, 21-23, 26-27).

One task = one (fit spec, outer fold): train on the label-eligible rows of the training patients,
produce inner out-of-fold predictions for ALL readings of the training patients (4 grouped inner
folds), fit the canonical calibrator on the inner OOF eligible rows, and score the held-out
patients. The policy thresholds are chosen in the main process from the returned inner OOF.

Learners: LightGBM (frozen hyperparameters) and, for R3 only, L2 logistic regression with
training-row median imputation, standardisation and one-hot categorical codes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from hyposense.calibration.methods import fit as fit_calibrator

F64 = npt.NDArray[np.float64]
_W: dict[str, Any] = {}


@dataclass(frozen=True)
class FitSpec:
    name: str  # result key, e.g. "M3", "SA8:M3", "R3:M2"
    level: str  # feature level the spec derives from (M1/M2/M3r/M3)
    features: tuple[str, ...]
    categorical: tuple[str, ...]
    learner: str = "lgbm"  # lgbm | lr
    params: dict[str, Any] = field(default_factory=dict)
    rounds: int = 0
    pb6_training_mask: bool = False
    table: str = "base"  # which input table the worker reads (base, sa6_0.75, sa6_1.5)
    keep_model: bool = False  # return the fold model text (R1/R2 rescoring, demo fold bundles)


def init(paths: dict[str, str], calibration_method: str) -> None:
    from hyposense.common.runtime import disable_power_throttling

    disable_power_throttling()
    _W["tables"] = {k: pd.read_parquet(v) for k, v in paths.items()}
    _W["cal"] = calibration_method


def _rows(t: pd.DataFrame, patients: set[str], eligible_only: bool, pb6: bool = False) -> Any:
    m = np.array(t["patient_key"].isin(patients).to_numpy(), dtype=bool)
    if eligible_only:
        m &= t["eligible"].to_numpy(bool)
    if pb6:
        m &= ~t["pb6_exclude"].to_numpy(bool)
    return m


class _LR:
    """R3 learner (§5.7 item 26)."""

    def __init__(self, X: pd.DataFrame, y: Any, categorical: tuple[str, ...]) -> None:
        from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]

        self.num = [c for c in X.columns if c not in categorical]
        self.cat = [c for c in X.columns if c in categorical]
        num = X[self.num].astype(float)
        self.median = num.median().fillna(0.0)
        Z = num.fillna(self.median)
        self.mean, self.sd = Z.mean(), Z.std(ddof=0).replace(0.0, 1.0)
        self.levels = {c: sorted(X[c].dropna().unique().tolist()) for c in self.cat}
        self.lr = LogisticRegression(C=1.0, solver="lbfgs", max_iter=2000).fit(self._design(X), y)

    def _design(self, X: pd.DataFrame) -> Any:
        Z = ((X[self.num].astype(float).fillna(self.median) - self.mean) / self.sd).to_numpy()
        hot = [
            (X[c].to_numpy()[:, None] == np.array(lv)[None, :]).astype(float)
            for c, lv in self.levels.items()
        ]
        return np.hstack([Z, *hot]) if hot else Z

    def predict(self, X: pd.DataFrame) -> F64:
        out: F64 = self.lr.predict_proba(self._design(X))[:, 1]
        return out

    @property
    def model_text(self) -> str:
        return json.dumps(
            {"coef": self.lr.coef_.tolist(), "intercept": self.lr.intercept_.tolist()}
        )


def _train(spec: FitSpec, X: pd.DataFrame, y: Any) -> Any:
    if spec.learner == "lr":
        return _LR(X, y, spec.categorical)
    from hyposense.models.lgbm import train

    return train(X, y, spec.params, spec.rounds, spec.categorical)


def task_fit(args: tuple[FitSpec, int, set[str], set[str], dict[str, int]]) -> dict[str, Any]:
    spec, k, train_p, test_p, inner = args
    assert not train_p & test_p and set(inner) == train_p, "fold isolation violated"
    t = _W["tables"][spec.table]
    feats = list(spec.features)
    y = t["y"].to_numpy(np.int64)
    tr = _rows(t, train_p, True, spec.pb6_training_mask)
    model = _train(spec, t.loc[tr, feats], y[tr])
    train_all = _rows(t, train_p, False)
    inner_raw = np.full(len(t), np.nan)
    for j in sorted(set(inner.values())):
        itr = {p for p, f in inner.items() if f != j}
        ite = {p for p, f in inner.items() if f == j}
        r_tr = _rows(t, itr, True, spec.pb6_training_mask)
        mj = _train(spec, t.loc[r_tr, feats], y[r_tr])
        r_te = _rows(t, ite, False)
        inner_raw[r_te] = mj.predict(t.loc[r_te, feats])
    elig = t["eligible"].to_numpy(bool)
    cal_rows = train_all & elig
    if np.isnan(inner_raw[train_all]).any():
        raise AssertionError("inner OOF incomplete")
    cal = fit_calibrator(_W["cal"], inner_raw[cal_rows], y[cal_rows])
    te = _rows(t, test_p, False)
    raw = model.predict(t.loc[te, feats])
    return {
        "name": spec.name,
        "fold": k,
        "test_idx": np.flatnonzero(te),
        "test_raw": raw,
        "test_p": cal.apply(raw),
        "train_idx": np.flatnonzero(train_all),
        "inner_p": cal.apply(inner_raw[train_all]),
        "calibrator": {"method": cal.method, "params": cal.params},
        "model_text": model.model_text if spec.keep_model else None,
    }
